"""Measurement recipes of generated profiles: which analyses run, and how waveforms become numbers.

A recipe belongs to a TYPE of circuit, not to one circuit. ``opamp_ac`` is the adapter's own deck and
``analog_optimizer.measurements.opamp.analyze`` (it expects the op-amp testbench conventions: nets VOUT,
VINP, VINN, VDD, VBIAS). ``ring_oscillator`` is defined here, for a free-running ring without a control
voltage - the verified VCO recipe sweeps a control source that such a cell does not have. It reuses
the VCO's verified waveform checks (``measurements.vco.oscillation_metrics``: sustained, full-swing,
regular cycles from a declared initial condition) and mirrors its deck and result handling.

Nothing here is tuned to make a circuit pass: a transient that does not show sustained oscillation is a
failed measurement, never a number.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
from statistics import mean

from analog_optimizer.backends.gpdk045 import number

from . import model_library, ocean, units
from .deck_ops import has_dc_operating_point, with_dc_operating_point
from .psf_binary import PsfError, read_file
from .generic_profile import GenericMosWidthProfile, RulesError
from .virtuoso_setup import DECK_FORMAT

RING = 'ring_oscillator'
RING_METRICS = dict(osc_frequency_hz='Hz', supply_power_w='W', supply_current_a='A', osc_minimum_swing_v='V',
                    osc_duty_cycle='1', osc_max_period_spread='1', osc_max_window_drift='1',
                    osc_startup_detection_s='s')
OPAMP_METRICS = ('gain_db_at_start', 'gain_reference_hz', 'bandwidth_3db_hz', 'unity_gain_hz',
    'phase_margin_estimate_deg',
                 'unity_downward_crossings', 'supply_current_a', 'supply_power_w', 'output_dc_v')
CONTRACT = dict(minimum_cycles=8, minimum_swing_fraction=0.8, maximum_period_spread=0.02,
    maximum_half_window_drift=0.01)
_NET = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$')


MAESTRO = 'maestro'


def provided_metrics(recipe) -> tuple:
    """The results a circuit type computes. A Maestro-measured task names its own (its outputs: the registry entry)."""
    return tuple(RING_METRICS) if recipe == RING else () if recipe == MAESTRO else OPAMP_METRICS


def spec_registry(recipe, design):
    """The RL specification registry a generated profile brings along: every result of its circuit type, with a
    fixed physical reference of the right order of magnitude (targets are normalized by it). Without it a target on
    e.g. `osc_frequency_hz` is refused - the default registry only knows the op-amp results - and the UI has no
    editor for the registry. None = the default registry fits (op-amp)."""
    if recipe != RING:
        return None
    supply, frequency = number(design['supply_v']), float(design['expected_frequency_hz'])
    references = dict(osc_frequency_hz=frequency, supply_power_w=1e-4, supply_current_a=1e-4,
                      osc_minimum_swing_v=supply,
                      osc_duty_cycle=1.0, osc_max_period_spread=CONTRACT['maximum_period_spread'],
                      osc_max_window_drift=CONTRACT['maximum_half_window_drift'],
                      osc_startup_detection_s=number(design['measurement_start']))
    return [dict(metric_id=name, unit=unit, reference=references[name]) for name, unit in RING_METRICS.items()]


def ring_timing(expected_frequency_hz) -> dict:
    """Transient window from a ROUGH expected frequency. Sized so the measurement contract still holds when the
    sizes move the frequency between about 0.6x and 1.5x: 8 full cycles are needed in each half of the window
    (40 expected periods cover that at 0.6x), startup must be over before it (20 periods), and the waveform needs
    more than 40 points per fastest period (100 points per expected period)."""
    f = float(expected_frequency_hz)
    if not math.isfinite(f) or not 1e3 <= f <= 1e11:
        raise RulesError('The expected oscillation frequency must lie between 1 kHz and 100 GHz')
    return dict(tran_stop=format(60 / f, '.6g'), measurement_start=format(20 / f, '.6g'),
        tran_maxstep=format(1 / (100 * f), '.6g'))


def ring_metrics(time, traces, supply_current, *, supply, start, stop, contract):
    """Pure: {net: samples} of the ring's stage nets (output first) + the supply source current -> metrics."""
    from analog_optimizer.measurements.vco import checked_trace, oscillation_metrics, window_mean
    stages = {name: oscillation_metrics(time, values, supply=supply, start=start, stop=stop, **contract)
              for name, values in traces.items()}
    frequencies = [s['frequency_hz'] for s in stages.values()]
    if (max(frequencies) - min(frequencies)) / mean(frequencies) > .01:
        raise ValueError('Ring stages have inconsistent frequencies')
    checked_trace(time, supply_current)
    # a source delivers power with a negative :p current
    current = -window_mean(time, supply_current, start, stop)
    if current <= 0:
        raise ValueError('Invalid mean supply current')
    output = next(iter(stages.values()))
    every = list(stages.values())
    return stages, dict(osc_frequency_hz=output['frequency_hz'], supply_power_w=supply * current,
                        supply_current_a=current,
                        osc_minimum_swing_v=min(s['minimum_cycle_swing_v'] for s in every),
                        osc_duty_cycle=output['duty_cycle'],
                        osc_max_period_spread=max(s['period_spread'] for s in every),
                        osc_max_window_drift=max(s['half_window_drift'] for s in every),
                        osc_startup_detection_s=max(s['startup_detection_s'] for s in every))


class GenericRingOscillatorProfile(GenericMosWidthProfile):
    """A generated MOS-width profile using the ring-oscillator transient measurement recipe."""
    recipe = RING

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        design = self.design
        nets = design.get('stage_nets')
        if (not isinstance(nets, list) or len(nets) < 3 or len(nets) % 2 == 0 or len(set(nets)) != len(nets)
                or any(not isinstance(n, str) or not _NET.match(n) for n in nets)):
            raise RulesError(
                'stage_nets must list the ring nets in ring order, output first: an odd number, at least three')
        conditions = design.get('initial_conditions')
        if not isinstance(conditions, dict) or set(conditions) != set(nets):
            raise RulesError('initial_conditions must give every stage net a start voltage')
        for key in ('supply_source', 'supply_net'):
            if not isinstance(design.get(key), str) or not _NET.match(design[key]):
                raise RulesError(f'{key} must be a plain Spectre name')
        if any(design.get(k) != v for k, v in CONTRACT.items()):
            raise RulesError(
                'The oscillation contract of a generated profile is fixed (the VCO profile\'s verified values)')
        start, stop, step = (number(design[k]) for k in ('measurement_start', 'tran_stop', 'tran_maxstep'))
        if not 0 < step < start < stop:
            raise RulesError('Invalid transient window')
        self.deck_name = 'ring_osc.scs'

    @property
    def analysis_settings(self):
        """Describe the ring recipe's transient timing and solver settings."""
        design = self.design
        return dict(version=1, recipe=RING, stop_s=number(design['tran_stop']),
                    start_s=number(design['measurement_start']),
                    maxstep_s=number(design['tran_maxstep']), errpreset='conservative', reltol=1e-5, vabstol=1e-8,
                    iabstol=1e-13)

    def build_deck(self, structure, model_file, section='tt', *, temperature_c=27.):
        """Build the ring-oscillator deck: circuit, DC operating point, initial conditions, saves, transient."""
        from analog_optimizer.backends.virtuoso_bridge import build_deck_header
        design, settings = self.design, self.analysis_settings
        deck = model_library.apply(build_deck_header(structure, model_file, section, temperature_c=temperature_c),
                                   model_file, section, getattr(self, 'model_library', None))
        conditions = ' '.join(f'{net}={number(design["initial_conditions"][net]):.12g}' for net in design['stage_nets'])
        return deck + ('dcOp dc\ndcOpInfo info what=oppoint where=rawfile\n'
                       f'ic {conditions}\n'
                       f'save {design["supply_net"]} {" ".join(design["stage_nets"])} {design["supply_source"]}:p\n'
                       'saveOptions options save=selected\n'
                       f'tranNom tran stop={settings["stop_s"]:.12g} maxstep={settings["maxstep_s"]:.12g} '
                       f'errpreset={settings["errpreset"]} ic=all skipdc=no\n')

    def analyze(self, job, *, result_name='bridge_result.json', mos_names=()):
        """The result handling of `measurements.vco.analyze`, for one transient and no control source."""
        from virtuoso_bridge.spectre.psf import read_psf_ascii, result_file, scalar, vector
        from analog_optimizer.backends.spectre_validation import validate_completion
        from analog_optimizer.measurements.ldo import real_vector
        from analog_optimizer.measurements.vco import checked_trace
        job, design, settings = Path(job), self.design, self.analysis_settings
        result = json.loads((job / result_name).read_text())
        if result.get('analysis_settings') != settings:
            raise ValueError('Ring oscillator analysis settings differ from executed manifest')
        condition = result['condition']
        if result['status'] != 'success' or condition['purpose'] != 'nominal' or condition.get(
            'monte_carlo') is not None:
            raise ValueError('Ring oscillator measurements require a successful nominal execution')
        evidence = validate_completion((job / 'results/spectre.out').read_text(), result['metadata']['returncode'],
            result['errors'])
        raw = Path(result['metadata']['output_dir'])
        dc = read_psf_ascii(result_file(raw, 'dcOp.dc'))
        op = read_psf_ascii(result_file(raw, 'dcOpInfo.info'))
        supply = number(design['supply_v'])
        if not math.isclose(scalar(dc, design['supply_net']), supply, rel_tol=1e-7, abs_tol=1e-12):
            raise ValueError('Ring oscillator DC testbench stimulus mismatch')
        data = read_psf_ascii(result_file(raw, 'tranNom.tran.tran'))
        time = real_vector(vector(data, 'time'), 'time')
        _, rail = checked_trace(time, vector(data, design['supply_net']))
        if any(not math.isclose(v, supply, rel_tol=1e-6, abs_tol=1e-9) for v in rail):
            raise ValueError('Incorrect transient supply')
        stages, metrics = ring_metrics(time, {net: vector(data, net) for net in design['stage_nets']},
                                       vector(data, f'{design["supply_source"]}:p'), supply=supply,
                                       start=settings['start_s'], stop=settings['stop_s'],
                                       contract={k: design[k] for k in CONTRACT})
        prefix = self.core_instance
        operating_points = {f'{prefix}.{name}': {key: scalar(op, f'{prefix}.{name}:{key}')
                                                 for key in ('ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat',
                                                     'region')} for name in mos_names}
        summary = dict(origin='real', job_id=result['job_id'], condition=condition, metrics=metrics,
                       analysis_settings=settings,
                       metric_units=dict(RING_METRICS), metric_validity={k: math.isfinite(v) for k,
                           v in metrics.items()},
                       operating_points=operating_points, execution_evidence=evidence, stages=stages,
                       notes=[
                           'Oscillation is started from declared initial conditions; this is not unassisted '
                           'or noise-driven startup.',
                              'Operating points are the DC equilibrium, not phase-resolved oscillation values.',
                              'Deterministic transient period spread is not physical jitter or phase noise.'])
        (job / 'measurements.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
        return summary


# Maestro's info outputs that no measurement reads (record 7.157): Spectre spent about 0.36 s of every job on them, and
# they were 232 of the 268 kB a job downloaded. The operating points (`dcOpInfo`, `finalTimeOP`, read by OP and OPT)
# stay.
UNREAD_INFO = ('modelParameter', 'element', 'outputParameter', 'designParamVals', 'primitives', 'subckts')
INFO_ENV, INFO_MODES = 'GATOR_INFO_OUTPUTS', ('drop', 'keep')
_UNREAD_INFO = re.compile(r'^\s*(' + '|'.join(UNREAD_INFO) + r')\s+info\b')


def without_unread_info(tail, outputs):
    """A Maestro deck's tail without the info outputs no output reads, a comment line where they were (record 7.157).
    The tail stays as it is with GATOR_INFO_OUTPUTS=keep, when it has none of them, or when an output expression uses
    VAR (a design variable) or names one of them (`getData(... ?result "element")`)."""
    mode = os.environ.get(INFO_ENV, 'drop')
    if mode not in INFO_MODES:
        raise ValueError(f'{INFO_ENV} must be one of {", ".join(INFO_MODES)}, not {mode!r}')
    expressions = ' '.join(str(o.get('spectre_expression') or o.get('expression') or '') for o in outputs or ())
    if mode == 'keep' or re.search(r'\bVAR\s*\(', expressions) or any(name in expressions for name in UNREAD_INFO):
        return tail
    kept, removed, at, continued = [], [], None, False
    for line in tail.split('\n'):
        if continued:                                  # a continuation line of a statement left out
            continued = line.rstrip().endswith('\\')
            continue
        match = _UNREAD_INFO.match(line)
        if match:
            removed.append(match.group(1))
            at = len(kept) if at is None else at
            continued = line.rstrip().endswith('\\')
            continue
        kept.append(line)
    if not removed:
        return tail
    kept.insert(at,
        f"// GATOR: Maestro's info outputs {' '.join(removed)} left out - no output reads them (record 7.157)")
    return '\n'.join(kept)


class GenericMaestroProfile(GenericMosWidthProfile):
    """A task whose probes are the Maestro outputs of its working copy (task flow part 5). The same verified width
    writing and checks as every generated profile; the deck is Maestro's own deck of the copy's test - netlisted once,
    at Save task (`maestro_deck.json`) - around the circuit the run adapter exports on every evaluation, and the outputs
    are measured with OCEAN on that run's results (`ocean.py`): the calculator Maestro itself uses, the signal names
    translated by Maestro's own name maps. The deck is read when a run needs it, so a task saved before this part still
    opens (its builder says to save it once)."""
    recipe = MAESTRO
    # OCEAN measures in the Virtuoso session, which takes one command at a time: this task's condition jobs never run
    # side by side (native_preparation.NativeCandidateBackend.concurrent_condition_jobs, 2026-09-30).
    measures_in_virtuoso = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._deck_file, self._deck = Path(kwargs['design_file']).parent / 'maestro_deck.json', None
        self.deck_name = 'input.scs'
        self.bridge = {}                          # how OCEAN reaches Virtuoso (tasks.generated_bridge_config sets it)
        self.read_operating_points = False        # set for a run whose network reads them (record 7.298)

    @property
    def maestro(self) -> dict:
        """Load and cache the stored Maestro deck after checking its format and required content."""
        if self._deck is None:
            try:
                deck = json.loads(self._deck_file.read_text())
            except (OSError, ValueError):
                raise RulesError(
                    'This task has no Maestro deck yet: save it as a new task (Save as) - Maestro then netlists '
                                 'its test')
            if deck.get('format') != DECK_FORMAT or not deck.get('outputs') or not deck.get('head') or not deck.get(
                'tail'):
                raise RulesError('The Maestro deck of this task is not one this workbench reads: save it as a new task '
                                 '(Save as)')
            self._deck = deck
        return self._deck

    def check_deck(self):
        """Require a readable Maestro deck and return the checked profile."""
        self.maestro
        return self

    @property
    def analysis_settings(self):
        """Describe the stored Maestro analyses, outputs and any operating-point readout."""
        deck = self.maestro
        settings = dict(version=1, recipe=MAESTRO, deck_sha256=deck['sha256'], analyses=list(deck['analyses']),
                        outputs=[dict(name=o['name'], expression=o['spectre_expression'],
                            analysis=o['analysis']) for o in deck['outputs']])
        if self.read_operating_points:            # the deck then also solves and saves the DC operating point (7.298)
            settings['operating_points'] = 'dcOpInfo' if has_dc_operating_point(deck[
                'tail']) else 'added dcOp + dcOpInfo'
        return settings

    def build_deck(self, structure, model_file, section='tt', *, temperature_c=27.):
        """Maestro's head (header, design variables, its model include) + the exported circuit + Maestro's tail (options,
        analyses, info, saves). The model include must be the connection's file and section: one deck, one model. A run's
        trimmed model library (record 7.154) then takes the place of that include, and the info outputs no output reads
        are left out of the tail (`without_unread_info`, record 7.157)."""
        deck = self.maestro
        if (deck['model_file'], deck['section']) != (str(model_file), section):
            raise RulesError(
                f'The Maestro test includes {deck["model_file"]} (section {deck["section"]}); the connection names '
                             f'{model_file} (section {section}): make them the same, then save the task again')
        head = model_library.apply(deck['head'], str(model_file), section, getattr(self, 'model_library', None))
        tail = without_unread_info(deck['tail'], deck['outputs'])
        if self.read_operating_points:
            tail = with_dc_operating_point(tail)
        return head + str(structure).strip('\n') + '\n' + tail

    def analyze(self, job, *, result_name='bridge_result.json', mos_names=()):
        """The outputs of one finished run, measured with OCEAN on the run's own results on the simulator host (the
        bridge keeps them). Values in the canonical unit of each probe - what OCEAN returns, and what the compiled
        specs compare with. Operating points only for a run whose network reads them (`read_operating_points`, record
        7.298): read from the run's own downloaded results, without Virtuoso (`maestro_operating_points`)."""
        from analog_optimizer.backends.spectre_validation import validate_completion
        job, deck, settings = Path(job), self.maestro, self.analysis_settings
        result = json.loads((job / result_name).read_text())
        if result.get('analysis_settings') != settings:
            raise ValueError('The Maestro deck differs from the one the executed netlist was built with')
        condition = result['condition']
        if result['status'] != 'success' or condition['purpose'] != 'nominal' or condition.get(
            'monte_carlo') is not None:
            raise ValueError('Maestro outputs are measured on a successful nominal run only')
        evidence = validate_completion((job / 'results/spectre.out').read_text(), result['metadata']['returncode'],
            result['errors'])
        raw = ocean.remote_raw_dir(result['metadata'])
        values = ocean.measure(self.bridge, raw, deck['outputs'])
        metrics = {o['name']: values.get(o['name']) for o in deck['outputs']}
        metric_units = {o['name']: units.canonical_unit(o['unit']) if units.known(o['unit']) else o[
            'unit'] for o in deck['outputs']}
        notes = ['Measured with OCEAN in Virtuoso on this run\'s own results: the output expressions of the copy\'s '
                 'Maestro test, their signal names translated by Maestro\'s name maps.']
        operating_points = {}
        if self.read_operating_points:
            operating_points, note = maestro_operating_points(result['metadata'].get('output_dir'), self.core_instance,
                mos_names)
            notes.append(note)
        summary = dict(origin='real', job_id=result['job_id'], condition=condition, metrics=metrics,
                       metric_units=metric_units,
                       metric_validity={k: v is not None and math.isfinite(v) for k, v in metrics.items()},
                       operating_points=operating_points, execution_evidence=evidence, analysis_settings=settings,
                       results_on_host=raw, notes=notes)
        (job / 'measurements.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
        return summary


# The operating-point outputs a Maestro deck may hold, in the order they are preferred: the DC equilibrium, else the
# point at the end of the transient (record 7.298). Both are Spectre `info what=oppoint` results without a sweep. A run
# whose network reads operating points gets the DC one added to its deck when the test saves none
# (`with_dc_operating_point`): one DC solve more per evaluation, every other analysis and output unchanged.
OPERATING_POINT_FILES = ('dcOpInfo.info', 'finalTimeOP.info')
OPERATING_POINT_KEYS = ('ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat', 'region')


def maestro_operating_points(results_dir, core_instance, mos_names):
    """({'<core>.<mos>': {key: number}}, a note) from a Maestro run's downloaded results (binary PSF, `psf_binary`).
    Missing files, devices or keys are left out (the network masks them); a file that does not parse gives none."""
    folder = Path(results_dir) if results_dir else None
    found = next((folder / name for name in OPERATING_POINT_FILES if folder is not None and (folder / name).is_file()),
        None)
    if found is None:
        return {}, 'No operating points: the Maestro deck saves neither dcOpInfo nor finalTimeOP for this run.'
    try:
        _, values = read_file(found)
    except (OSError, PsfError) as exc:
        return {}, f'No operating points: {found.name} could not be read ({exc}).'
    points = {}
    for name in mos_names:
        key = f'{core_instance}.{name}'
        record = values.get(key)
        if not isinstance(record, dict):
            continue
        kept = {k: record[k] for k in OPERATING_POINT_KEYS
                if isinstance(record.get(k), (int, float)) and not isinstance(record.get(k),
                    bool) and math.isfinite(record[k])}
        if kept:
            points[key] = kept
    return points, f'Operating points from {found.name}: {len(points)} of {len(mos_names)} transistors.'


PROFILE_CLASSES = {'opamp_ac': GenericMosWidthProfile, RING: GenericRingOscillatorProfile,
    MAESTRO: GenericMaestroProfile}
