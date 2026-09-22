"""The TASK FILE: one readable file that says everything a saved task is (`profiles.save_task` writes it as
``configs/local/workbench/profiles/<name>/task.json``).

It is the reference the three sides are compared with: the editors show its rows, the working copy in Virtuoso holds
what its ``maestro`` part says, and the profile files next to it are generated from it on every "Save task". A user (or
the agent) may open it and change it by hand; ``parse`` checks every part with the same schema the editors use, and
"Apply" puts the rows back into the editors - nothing is saved until "Save task" is pressed.

Parts:
* ``cell`` - the cell the user drew (never written) and ``copy`` - the working copy the task simulates;
* ``measurement`` - ``kind``: ``maestro`` (the copy's Maestro outputs, measured with OCEAN) or one of the two verified
  circuit types (``ring_oscillator``, ``opamp_ac``, measured by the workbench); ``expected_frequency_hz`` for the
  ring oscillator (a rough value; it sizes the transient);
* ``maestro`` - the copy's Maestro test: analyses (name -> options), design variables, bindings (instance parameter ->
  variable; analogLib R, C, L and sources only), and - taken from the Probes and Specs rows - outputs and specs;
* ``parameters`` / ``probes`` / ``specs`` - the rows of the three editors;
* ``notes`` - free text for the user's records.

``_help`` says the same in the file itself, so an opened file explains itself (JSON has no comments); it is ignored when
the file is read back.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

FORMAT = 'gator-task-1'
HELP = {
    'what this is': 'The task file: everything this task is, in one place. Edit it here or in the three editors. '
                    '"Apply to editors" checks it and puts the rows into the editors; "Save task" stores it. Nothing is '
                    'written to Virtuoso or saved until you press "Save task".',
    'cell': 'The cell you drew. Never written.',
    'copy': 'The working copy in Virtuoso that the task simulates (made by "Make a working copy" / "Save as").',
    'measurement': 'kind = maestro: the Maestro outputs of the copy are the probes. kind = ring_oscillator or opamp_ac: '
                   'the two verified circuit types, measured by the workbench. Found from the probes when you save. '
                   'expected_frequency_hz (ring_oscillator only): a rough oscillation frequency; it sizes the transient.',
    'maestro': 'The copy\'s Maestro test. Edit analyses (e.g. {"tran": {"stop": "50n"}}), variables '
               '({"VSUP": "1.0"}) and bindings ([{"cell": ..., "instance": "V0", "parameter": "vdc", "variable": "VSUP"}]; '
               'only analogLib resistors, capacitors, inductors and sources) here. Outputs and specs come from the '
               'Probes and Specs rows.',
    'parameters': 'Parameters rows: what may vary - instance path as in the circuit (e.g. XU1/MN1), parameter, unit, '
                  'range, step, grouping. In Virtuoso a run writes any value the property form of the instance lets you '
                  'type (read with the cell): widths, lengths, finger counts, multipliers, capacitor sides ...',
    'probes': 'Probes rows: what is measured. result_source ade_output = a Maestro output (source_name = its name, '
              'signal = its expression); backend_profile = a result of the circuit type; expression = arithmetic over '
              'other probes.',
    'specs': 'Specs rows: equation over probe IDs, constraint and limits, plus what only the optimizer uses (hard, '
             'soft_weight, direction_after_feasible, normalization_scale).',
    'notes': 'Free text for your records.',
}


def build(*, name, revision, cell, copy, measurement, maestro, parameters, probes, specs, notes='', saved_utc=None,
          virtuoso=None) -> dict:
    return dict(_help=HELP, format=FORMAT, name=name, revision=revision, saved_utc=saved_utc, cell=cell, copy=copy,
                measurement=measurement, maestro=maestro, parameters=parameters, probes=probes, specs=specs,
                notes=notes or '', virtuoso=virtuoso or {})


def draft(config, *, name, cell, copy, saved=None, extras=None, setup=None) -> dict:
    """The task file of the CURRENT editors - what "Save task" would store: the rows of `config`, the extras the page
    holds (analyses, variables, bindings, expected frequency, notes), else those of the saved task `saved`, else the
    analyses the copy's Maestro test has (`setup`, a read-back)."""
    saved, extras = saved or {}, extras or {}
    base_maestro = saved.get('maestro') or {}
    if setup and setup.get('test'):
        base_maestro = dict(base_maestro, analyses=base_maestro.get('analyses') or setup.get('analyses'),
                            variables=base_maestro.get('variables') or setup.get('variables'),
                            bindings=base_maestro.get('bindings') or setup.get('bindings'),
                            model_files=base_maestro.get('model_files') or setup.get('model_files'))
    maestro = dict(analyses=extras.get('analyses', base_maestro.get('analyses') or {}),
                   variables=extras.get('variables', base_maestro.get('variables') or {}),
                   bindings=extras.get('bindings', base_maestro.get('bindings') or []),
                   model_files=extras.get('model_files', base_maestro.get('model_files') or []))
    measurement = dict(saved.get('measurement') or {})
    if 'expected_frequency_hz' in extras:
        measurement['expected_frequency_hz'] = extras['expected_frequency_hz']
    rows = config.model_dump(mode='json') if hasattr(config, 'model_dump') else config
    return build(name=name, revision=saved.get('revision', 0), cell=cell, copy=copy, measurement=measurement,
                 maestro=maestro, parameters=rows.get('parameters', []), probes=rows.get('measurements', []),
                 specs=rows.get('targets', []), notes=extras.get('notes', saved.get('notes', '')),
                 saved_utc=saved.get('saved_utc'), virtuoso=saved.get('virtuoso'))


def render(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + '\n'


def parse(text) -> tuple[dict, dict, list[str]]:
    """(rows, extras, problems) of a task file someone edited. rows = {parameters, measurements, targets} as the
    configuration spells them; extras = what the page keeps beside the rows. Every row is checked with the schema of
    the editors; nothing is saved here."""
    from .schema import MeasurementDefinition, OptimizationParameter, PerformanceTarget
    try:
        data = json.loads(text)
    except ValueError as exc:
        return {}, {}, [f'Not valid JSON: {exc}']
    if not isinstance(data, dict):
        return {}, {}, ['The task file must be one JSON object']
    problems = []
    if data.get('format', FORMAT) != FORMAT:
        problems.append(f'format is {data.get("format")!r}; this workbench reads {FORMAT!r}')
    rows = {}
    for part, key, model in (('parameters', 'parameters', OptimizationParameter), ('probes', 'measurements', MeasurementDefinition),
                             ('specs', 'targets', PerformanceTarget)):
        items = data.get(part, [])
        if not isinstance(items, list):
            problems.append(f'{part} must be a list of rows')
            continue
        good = []
        for index, item in enumerate(items):
            try:
                good.append(model.model_validate(item).model_dump(mode='json', exclude_unset=True, exclude_none=True))
            except ValidationError as exc:
                problems += [f'{part}[{index}] {".".join(map(str, e["loc"]))}: {e["msg"]}' for e in exc.errors()[:4]]
        rows[key] = good
    extras = {}
    measurement = data.get('measurement') or {}
    if not isinstance(measurement, dict):
        problems.append('measurement must be an object')
    elif measurement.get('expected_frequency_hz') is not None:
        try:
            value = float(measurement['expected_frequency_hz'])
            if not 1e3 <= value <= 1e11:
                raise ValueError
            extras['expected_frequency_hz'] = value
        except (TypeError, ValueError):
            problems.append('measurement.expected_frequency_hz must be a number between 1e3 and 1e11 (Hz)')
    maestro = data.get('maestro') or {}
    if not isinstance(maestro, dict):
        problems.append('maestro must be an object')
    else:
        analyses, variables, bindings = maestro.get('analyses', {}), maestro.get('variables', {}), maestro.get('bindings', [])
        if not isinstance(analyses, dict) or any(not isinstance(v, dict) for v in analyses.values()):
            problems.append('maestro.analyses must map an analysis name to its options, e.g. {"tran": {"stop": "50n"}}')
        else:
            extras['analyses'] = {str(k): {str(o): str(v) for o, v in options.items()} for k, options in analyses.items()}
        if not isinstance(variables, dict):
            problems.append('maestro.variables must map a variable name to its value')
        else:
            extras['variables'] = {str(k): str(v) for k, v in variables.items()}
        if not isinstance(bindings, list) or any(not isinstance(b, dict) or set(b) != {'cell', 'instance', 'parameter', 'variable'}
                                                   for b in bindings):
            problems.append('maestro.bindings must list {"cell", "instance", "parameter", "variable"} objects')
        else:
            extras['bindings'] = [dict(b) for b in bindings]
        if isinstance(maestro.get('model_files'), list):
            extras['model_files'] = [list(item) for item in maestro['model_files'] if isinstance(item, (list, tuple)) and len(item) == 2]
    if isinstance(data.get('notes'), str):
        extras['notes'] = data['notes'][:4000]
    return rows, extras, problems


def what_changed(old, new) -> set[str]:
    """Which parts of a task differ between two task files: parameters, probes, measurement, analyses, variables,
    bindings, specs, notes. A recorded baseline stays valid only when none of the first six changed."""
    old, new = old or {}, new or {}
    changed = set()
    for part in ('parameters', 'probes', 'specs', 'notes'):
        if json.dumps(old.get(part), sort_keys=True) != json.dumps(new.get(part), sort_keys=True):
            changed.add(part)
    om, nm = old.get('measurement') or {}, new.get('measurement') or {}
    if (om.get('kind'), om.get('expected_frequency_hz')) != (nm.get('kind'), nm.get('expected_frequency_hz')):
        changed.add('measurement')
    oa, na = old.get('maestro') or {}, new.get('maestro') or {}
    for part in ('analyses', 'variables', 'bindings'):
        if json.dumps(oa.get(part) or None, sort_keys=True) != json.dumps(na.get(part) or None, sort_keys=True):
            changed.add(part)
    return changed


BASELINE_PARTS = {'parameters', 'probes', 'measurement', 'analyses', 'variables', 'bindings'}
