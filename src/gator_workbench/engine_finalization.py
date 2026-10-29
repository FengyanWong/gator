"""Close a run in order: learning, lanes, preparation owner, outputs and status.

These functions receive the scheduler-owned context explicitly. Cleanup and output
failures keep their existing independent error handling; checkpoint coordination
remains with the scheduler so every save drains pending learner rows first.
"""
from __future__ import annotations

import shutil

from . import best_design
from .lanes import unlink_scratch
from .layout import build_artifact_manifest
from .run_lock import iso
from .security import redact
from .storage.atomic import write_json
from .storage.dataset import utcnow
from .summary import build_run_summary

# The summary's note when a run stopped while it was being prepared, before `engine_preparation.prepare` opened its save
# points (`engine.checkpoints`): there is nothing to save then. Trying anyway added a second error that hid the first:
# "final save failed: AttributeError: 'RunEngine' object has no attribute 'checkpoints'" after a resume refused for an
# unresolved launch lease (2026-10-23).
SAVE_SKIPPED_NOTE = ('No save point was written: the run stopped while it was being prepared, before it opened its '
                     'save points. Those already in the run folder are unchanged.')


def clear_scratch(engine):
    """Once the lanes and the preparation service are closed: the links in the lanes' folders, then the run's local
    scratch itself (`layout.local_scratch`). Each kept job folder moved to the run folder when its result was
    durable; the rest are temporaries, as in work/."""
    if engine._scratch is None:
        return
    for lane in engine.lanes:
        directory = (getattr(lane, 'info', None) or {}).get('directory')
        if directory:
            try:
                unlink_scratch(directory)
            except OSError:
                pass
    shutil.rmtree(engine._scratch, ignore_errors=True)
    try:
        engine._scratch.parent.rmdir()              # the experiment's folder, once none of its runs has scratch left
    except OSError:
        pass


def finalize(engine, final_state):
    """Close and restore run resources, persist final records, and return the resulting run state."""
    engine._write_timings()
    try:
        engine._run_pending_updates()                  # before the last save point and its "unchanged" check (7.281)
        engine._persist_waiting_rows()                 # no commit comes after them: their rows go as their own record (7.283)
    except Exception as exc:
        engine._log_error('pending_updates_failed', exc)
    # ---- Close lane resources and collect restoration failures before final persistence.
    problems = []
    for lane in engine.lanes:
        try:
            outcome = lane.close()
            if outcome.get('state') not in ('restored', 'not_connected', 'already_closed'):
                problems.append(f"lane {lane.lane_id}: environment restoration state {outcome.get('state')}")
        except BaseException as exc:
            problems.append(f'lane {lane.lane_id}: {type(exc).__name__}: {exc}')
    if engine._preparation is not None:                # after every lane: the owner restores the schematic and lets go
        try:
            engine._preparation.close()
            restoration = (engine.preparation_report or {}).get('preparation_restoration') or {}
            if restoration.get('state') != 'restored':
                problems.append(f"preparation service: restoration state {restoration.get('state')}")
        except BaseException as exc:
            problems.append(f'preparation service: {type(exc).__name__}: {exc}')
        engine._preparation = None
    engine._clear_scratch()
    try:                                             # every lane is closed: the host's dropped job folders go (7.282)
        engine._clean_host()
        engine._log_virtuoso_memory('end')
    except Exception as exc:
        engine._log_error('simulator_host_cleanup_failed', exc)
    # ---- Flush the dataset and save a final checkpoint when the run state permits it.
    checkpoint = None
    persistence_ok = engine.dataset is not None and engine.dataset.failed is None
    if persistence_ok and hasattr(engine, 'ledger'):
        try:
            engine.dataset.flush()
            if getattr(engine, 'checkpoints', None) is None:      # preparation stopped before it opened the save points
                engine.final_save_note = SAVE_SKIPPED_NOTE
            elif not engine.ledger.in_flight_ids():
                kind = {'paused': 'pause', 'stopped': 'stop', 'completed': 'final'}.get(final_state, 'safety')
                checkpoint = engine._relabel_unchanged(kind) or engine._checkpoint(kind)
        except BaseException as exc:
            persistence_ok = False
            problems.append(f'final save failed: {type(exc).__name__}: {exc}')
            engine._log_error('final_save_failed', exc)
    if problems and final_state == 'completed':
        final_state = 'failed'
    if problems:
        engine.error = redact('; '.join(filter(None, [engine.error, *problems])), 4000)
    try:
        if hasattr(engine, 'ledger'):
            engine._write_outputs(final_state, checkpoint, persistence_ok)
    except BaseException as exc:
        engine._log_error('summary_failed', exc)
        final_state = 'failed'
        engine.error = redact(f'{engine.error or ""} summary failed: {exc}', 4000)
    if engine.dataset is not None:
        try:
            engine.dataset.close()
        except BaseException:
            pass
    # ---- Publish the final segment state after output and dataset cleanup.
    ended = utcnow()
    segment = engine.manifest['segments'][-1]
    segment.update(ended_utc=iso(ended), end_state=final_state, stop_reason=engine.stop_reason,
                   active_seconds=engine.segment_seconds())
    engine.manifest['state'] = final_state
    engine._adopt_baseline()
    engine._calibrate()
    write_json(engine.layout.manifest, engine.manifest)
    engine._event('segment_ended', state=final_state, stop_reason=engine.stop_reason, error=engine.error)
    engine._write_status(final_state)
    try:
        build_artifact_manifest(engine.layout, run_id=engine.run_id, final=final_state in ('completed', 'stopped'),
                                dataset_status=None if engine.dataset is None else engine.dataset.status(),
                                notes=getattr(engine, 'manifest_notes', []))
    except BaseException as exc:
        engine._log_error('artifact_manifest_failed', exc)
    for stream in (engine.events, engine.errors, engine.dispatch_log):
        stream.close()
    return final_state


def adopt_baseline(engine):
    """A finished "Baseline simulation" of a generated task becomes the task's reference by itself
    (profiles.adopt_baseline_run, record 7.78) - only that run kind, after the tables are closed and the manifest
    says how the run ended, before it is written. What it did or why not goes into the manifest's notes. Nothing
    here may fail the run: a problem is logged and the run ends as it would have."""
    if engine.manifest.get('run_kind') != 'baseline_preflight':
        return
    try:
        from . import profiles  # lazy: in the try: a failure of the import is handled with the rest
        outcome = profiles.adopt_baseline_run(engine.layout.run_dir, manifest=engine.manifest)
    except BaseException as exc:
        engine._log_error('baseline_reference_failed', exc)
        return
    if outcome:
        engine.manifest.setdefault('notes', []).append(outcome['note'])
        engine.manifest_notes = [*getattr(engine, 'manifest_notes', []), outcome['note']]
        engine._event('baseline_reference', recorded=outcome['recorded'], task=f"real:{outcome['name']}", note=outcome['note'])


def calibrate(engine):
    """A baseline run asked to calibrate (record 7.197) writes its proposals - a Scale per Specs row and the Initial
    alpha, from its random designs - into calibration.json of the run folder, and says so in the manifest's notes.
    Nothing is applied: the page offers them. As with the baseline's adoption, nothing here may fail the run."""
    if not engine.manifest.get('calibration') or engine.dataset is None:
        return
    try:
        from . import calibration  # lazy: in the try: a failure of the import is handled with the rest
        result = calibration.from_run(engine.layout.run_dir, manifest=engine.manifest)
        write_json(engine.layout.run_dir / calibration.FILE, result)
    except BaseException as exc:
        engine._log_error('calibration_failed', exc)
        return
    note = calibration.sentence(result)
    engine.manifest.setdefault('notes', []).append(note)
    engine.manifest_notes = [*getattr(engine, 'manifest_notes', []), note]
    engine._event('calibration', status=result['status'], designs=result['designs'], note=note)


def write_outputs(engine, final_state, checkpoint, persistence_ok):
    """Write best-design exports and the run summary, with optional experiment aggregates."""
    task = engine.task
    reparse, exporter, netlist_name = None, None, 'optimized_dut.scs'
    if task.netlist_path and task.parser_config_path:
        def reparse(text):
            from analog_optimizer.netlist.config import ParserConfig
            from analog_optimizer.netlist.spectre_parser import SpectreParser
            return SpectreParser(ParserConfig.from_file(task.parser_config_path)).parse_text(
                text, source=task.netlist_path, top=task.circuit.get('dut_hierarchy'))
    elif task.circuit.get('simulator') == 'ngspice':          # a SPICE deck: its own writer, values also inside a once-used subcircuit
        from .ngspice_tasks import export_deck  # lazy: ngspice_tasks imports the optimizer
        exporter, netlist_name = export_deck(task), 'optimized_dut.cir'
    notes = best_design.write_outputs(
        engine.layout.best_design, engine.tracker,
        task=dict(task_id=engine.task_id, task_key=task.task_key, circuit=task.circuit, provenance=engine.provenance),
        config_summary=dict(targets=list(engine.compiled.targets), variables=list(engine.compiled.variables)),
        netlist_text=task.netlist_text, graph=engine.compiled.graph, reparse=reparse, exporter=exporter, netlist_name=netlist_name)
    engine.manifest_notes = [f'best_design/{k}: {v}' for k, v in notes.items()]
    summary = build_run_summary(engine, final_state, checkpoint, persistence_ok)
    write_json(engine.layout.summary, summary)
    if engine.config.output.export_summary_csv:
        try:                                  # derived CSVs only; a failure here never loses raw data
            # lazy: in the try: a failure of the import is handled with the rest
            from .aggregates import export_aggregates
            export_aggregates(engine.layout.experiment_dir)
        except BaseException as exc:
            engine._log_error('aggregate_export_failed', exc)
