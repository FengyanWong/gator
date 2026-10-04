"""Specs are equations over Probes.

A Probes row names one measured quantity: a result the simulation returns (``source_name``: a Maestro output or a
profile metric). A Specs row judges ONE value, its ``equation``, written
over Probe IDs: ``m_supply_power_w / m_osc_frequency_hz``, or simply ``m_osc_frequency_hz``. That value -
and nothing else - is what the reward, the network's goal input, the independent pass/fail check and the
tables see under the spec's name (``metric_id``).

How the value reaches the optimizer without a change to ``analog_optimizer`` (its source digest gates the
checkpoints): the environment scores its ``MetricSpec``s by looking their names up in the simulation result.
A spec whose equation is exactly the probe of a simulator result, and which carries that result's name, is
"result-backed": the environment finds it there, as before. Every other spec is COMPUTED here, from the valid
values of the result, and added to that result under the spec's name (``SpecPlan.extend``), inside the lane
and before the environment reads it. So the reward, the observation, the recorded candidate and the
workbench's own feasibility check (``engine``) all see the same number, made by the same code. For the same
reason a spec may not borrow the name of a simulator result unless it IS that result (``validation``).

The arithmetic is a whitelist evaluator (the Probes' own expressions used it until 2026-10-03, when a probe computed from
other probes was retired: that is a spec equation's job): numbers (SI suffixes such as ``2u``),
Probe IDs, ``+ - * / **`` and parentheses; no function calls, never ``eval()``. A missing or invalid input,
or arithmetic that fails (a division by zero), makes the value invalid - never a number.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import dataclass, replace
import math

MAX_LENGTH = 512                                                      # schema.PerformanceTarget.equation
_ALLOWED = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.UnaryOp, ast.UAdd, ast.USub,
            ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
REGISTRY_SUFFIX = '+spec-equations-v1'
# Size of a quantity in its canonical unit: only for scaling the network's input of a spec the result registry
# does not know yet, when its inputs give no better size. Order of magnitude of analog IC work; never a threshold.
UNIT_MAGNITUDE = {'m': 1e-6, 'F': 1e-12, 'ohm': 1e3, 'H': 1e-9, 'V': 1.0, 'A': 1e-6, 'W': 1e-6, 'J': 1e-12, 'Hz': 1e6,
                  's': 1e-9, 'deg': 90.0, 'rad': 1.0, 'dB': 20.0, 'dBc/Hz': 100.0, 'V/sqrt(Hz)': 1e-8,
                  'A/sqrt(Hz)': 1e-12, 'V^2/Hz': 1e-16, 'Vrms': 1e-3, 'V/s': 1e6, 'Hz/V': 1e9, 'V/V': 1e-2,
                  'V/A': 100.0, '%': 1.0, 'count': 1.0, '1': 1.0, 'fixture': 1.0}


class _Missing(Exception):
    pass


def parse(text):
    """(names used, None) when `text` is an equation the evaluator accepts, else (None, why). Nothing is evaluated,
    so a formula that divides by a difference is judged by its form, not by trial values."""
    from analog_optimizer.netlist.expressions import NUMBER, SCALES
    source = (text or '').strip() if isinstance(text, str) else ''
    if not source:
        return None, 'the equation is empty'
    if len(source) > MAX_LENGTH:
        return None, f'longer than {MAX_LENGTH} characters'

    def number(match):
        suffix = match[2]
        if suffix and suffix not in SCALES:
            raise ValueError(f'unsupported number suffix {suffix!r}')
        value = float(match[1]) * SCALES.get(suffix, 1.0)
        if not math.isfinite(value):
            raise ValueError('a number is too large')
        return repr(value)
    try:
        tree = ast.parse(NUMBER.sub(number, source), mode='eval')
    except SyntaxError:
        return None, 'not a formula (check the brackets and operators)'
    except (ValueError, RecursionError) as exc:
        return None, str(exc)
    nodes = list(ast.walk(tree))
    if len(nodes) > 128:
        return None, 'too complex'
    for node in nodes:
        if not isinstance(node, _ALLOWED) or (isinstance(node, ast.Constant) and type(node.value) not in (int, float)):
            what = {ast.Call: 'a function call', ast.Attribute: 'a dotted name', ast.Compare: 'a comparison'}.get(type(node), type(node).__name__)
            return None, f'{what} is not allowed'
    return list(dict.fromkeys(node.id for node in nodes if isinstance(node, ast.Name))), None


def evaluate(text, lookup):
    """The value of `text`, or None. `lookup(name)` gives a number, or None for a missing/invalid input."""
    from analog_optimizer.netlist.expressions import UnresolvedExpression, evaluate as whitelist

    def value_of(name):
        value = lookup(name)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise _Missing()
        return value
    try:
        value = whitelist(text, value_of)
    except (_Missing, UnresolvedExpression, ArithmeticError, KeyError, RecursionError):
        return None
    return value if math.isfinite(value) else None


def _finite(value):
    return value is not None and not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


@dataclass(frozen=True)
class SpecEntry:
    spec_id: str
    equation: str
    unit: str                 # canonical unit of the spec
    required: bool            # active and hard: the evaluation only counts when this value is valid
    probe: str | None         # the Probe ID when the equation is exactly one probe
    result_backed: bool       # that probe reads the simulator result of the SAME name: the result itself carries the value


@dataclass(frozen=True)
class SpecPlan:
    """Picklable: goes to every lane with the environment factory."""
    probes: tuple             # (probe_id, source_name | None), in table order
    specs: tuple              # SpecEntry, in table order

    @classmethod
    def from_config(cls, config) -> 'SpecPlan':
        from . import units
        probes = tuple((m.measurement_id, m.source_name) for m in config.measurements)
        table = {p[0]: p for p in probes}
        specs = []
        for t in config.targets:
            text = t.equation.strip()
            probe = text if text in table else None
            specs.append(SpecEntry(t.metric_id, text, units.canonical_unit(t.unit) if units.known(t.unit) else t.unit,
                                   bool(t.active and t.hard), probe, probe is not None and table[probe][1] == t.metric_id))
        return cls(probes, tuple(specs))

    @property
    def injected(self) -> tuple:
        """Names the lanes add to a simulation result: every spec that is not result-backed."""
        return tuple(s.spec_id for s in self.specs if not s.result_backed)

    # ------------------------------------------------------------------ values
    def probe_values(self, raw) -> dict:
        """{probe ID: value | None} from `raw` = the VALID simulator results (name -> number)."""
        values = {}
        for probe_id, source in self.probes:
            value = raw.get(source) if source is not None else None   # no result named: never a number
            values[probe_id] = value if _finite(value) else None
        return values

    def spec_values(self, raw=None, *, probes=None) -> dict:
        """{spec name: value | None}, each spec's equation over the probe values."""
        probes = self.probe_values(raw or {}) if probes is None else probes
        values = {}
        for spec in self.specs:
            value = probes.get(spec.probe) if spec.probe is not None else evaluate(spec.equation, probes.get)
            values[spec.spec_id] = value if _finite(value) else None
        return values

    # ------------------------------------------------------------------ what a spec reads
    def raw_inputs(self, spec) -> tuple:
        """The simulator results a spec's value is made of."""
        table = dict(self.probes)
        names = [spec.probe] if spec.probe is not None else parse(spec.equation)[0] or ()
        return tuple(dict.fromkeys(table[name] for name in names if table.get(name) is not None))

    def request_names(self, required) -> tuple:
        """The results a simulation request insists on: a computed spec stands for the results its equation reads."""
        computed = {s.spec_id: s for s in self.specs if not s.result_backed}
        names = []
        for name in required:
            names.extend(self.raw_inputs(computed[name]) if name in computed else (name,))
        return tuple(dict.fromkeys(names))

    # ------------------------------------------------------------------ inside a lane
    def extend(self, result):
        """`result` plus the value of every computed spec under its own name (unit: the spec's canonical unit)."""
        injected = [s for s in self.specs if not s.result_backed]
        if not injected:
            return result
        clash = [s.spec_id for s in injected if s.spec_id in result.metrics]
        if clash:                                                  # validation refuses this; never overwrite a measurement
            raise ValueError(f'Spec(s) {clash} carry the name of a simulator result but are computed by an equation: rename them')
        usable = {name: value for name, value in result.metrics.items()
                  if result.metric_validity.get(name) is True and _finite(value)}
        values = self.spec_values(usable)
        # A completed simulation with a missing probe (measurement_error) blanks only the specs that read that probe; the
        # others keep their measured values, which a spec's "Missing value = failed" relies on (record 7.112).
        evaluated = result.status in ('ok', 'measurement_error') and bool(result.candidate_evaluated)
        metrics, units, validity = dict(result.metrics), dict(result.metric_units), dict(result.metric_validity)
        for spec in injected:
            value = values[spec.spec_id] if evaluated else None
            metrics[spec.spec_id], units[spec.spec_id], validity[spec.spec_id] = value, spec.unit, value is not None
        return replace(result, metrics=metrics, metric_units=units, metric_validity=validity)

    def wrap(self, backend):
        """Make `backend` answer every simulation with the computed specs added. A no-op when every spec is result-backed."""
        if not self.injected:
            return backend
        simulate, plan = backend.run_simulation, self

        def run_simulation(request):
            return plan.extend(simulate(replace(request, required_metrics=plan.request_names(request.required_metrics))))
        backend.run_simulation = run_simulation
        return backend


@dataclass(frozen=True)
class EquationNativeFactory:
    """The verified real-circuit factory (``training.parallel.NativeEnvironmentFactory``) with computed specs. It builds
    the SAME environment and backend; the backend's answers get the computed specs added (``SpecPlan.wrap``). The
    worker's first-evaluation check against the recorded real baseline is kept, on the simulator's own results: a
    computed spec is arithmetic on them, and its rounding would only make that check stricter than the measurement."""
    inner: object
    plan: SpecPlan

    @property
    def condition_policy(self):
        return self.inner.condition_policy

    @property
    def output(self):
        return self.inner.output

    @contextmanager
    def preparation_context(self, limits, report):
        with self.inner.preparation_context(limits, report) as prepared:
            yield replace(self, inner=prepared)

    def __call__(self, lane):
        return self.create_recorded(lane, None)

    def create_recorded(self, lane, recorder):
        reference = self.inner.reference_metrics
        env = replace(self.inner, reference_metrics=None).create_recorded(lane, recorder)
        self.plan.wrap(env.backend)
        if reference is not None:
            computed, reset = set(self.plan.injected), env.reset

            def checked_reset():                                   # = NativeEnvironmentFactory's check, on the results only
                observation, info = reset()
                if observation is not None and info['evaluation_valid']:
                    measured = {k: v for k, v in observation.metrics.items() if k not in computed}
                    if measured.keys() != reference.keys() or any(
                            not ((a is None and reference[k] is None) or
                                 (a is not None and reference[k] is not None and
                                  math.isclose(a, reference[k], rel_tol=1e-6, abs_tol=1e-12)))
                            for k, a in measured.items()):
                        raise RuntimeError('Worker baseline differs from verified real measurements')
                return observation, info
            env.reset = checked_reset
        return env


# ---------------------------------------------------------------------------------- the result registry
def magnitude(unit) -> float:
    from . import units
    canonical = units.canonical_unit(unit) if isinstance(unit, str) and units.known(unit) else unit
    return float(UNIT_MAGNITUDE.get(canonical, 1.0))


def registry_entries(config, base) -> tuple:
    """Entries the network's result registry gains for this configuration: one per spec whose name it does not know.
    base = ((name, unit, reference), ...). The reference (it only scales the network input, as for every entry) is
    the spec's equation evaluated on the references of its inputs - the registry's own for a result it knows, else the
    size of the probe's unit - so it depends on WHAT the spec computes, never on its thresholds: changing a limit
    keeps saved models of the task loadable. Adding, removing or renaming such a spec changes the registry."""
    known = {name: reference for name, _, reference in base}
    plan = SpecPlan.from_config(config)
    table = {p[0]: p for p in plan.probes}
    probe_units = {m.measurement_id: m.unit for m in config.measurements}

    def size(probe_id):
        if probe_id not in table:
            return None
        _, source = table[probe_id]
        if source is not None and source in known:
            return known[source]
        return magnitude(probe_units.get(probe_id))
    added = []
    for spec in plan.specs:
        if spec.spec_id in known:
            continue
        value = size(spec.probe) if spec.probe is not None else evaluate(spec.equation, size)
        reference = abs(value) if _finite(value) and value != 0 else magnitude(spec.unit)
        added.append((spec.spec_id, spec.unit, float(reference)))
        known[spec.spec_id] = reference
    return tuple(added)
