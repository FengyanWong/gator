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
import fnmatch
import math
import re
from . import units

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


def is_finite_number(value):
    return value is not None and not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


# ---------------------------------------------------------------------------------- a probe that measures the sizes
# Record 7.308. A Probes row with result_source "size_estimate" is not measured by the simulator: its `signal` is a
# formula over the widths the task varies, worked out in the lane from the candidate's own parameters and added to the
# simulation result under the probe's source name - a result of its own, so the reward, the independent pass/fail check
# and the tables read it as they read any other result. First use: a standard cell's width before layout (the number
# of gate columns), plan-transfer-experiment.md section 6.2.1.
#
#   fingers("pattern", limit)   sum over the matching instances of ceil(width / limit): the fingers they fold into
#   width("pattern")            sum of the matching instances' widths
#   count("pattern")            how many instances match
#   larger(a, b), smaller(a, b)
#
# with numbers (SI suffixes), + - * / ** and brackets. A pattern is a shell-style pattern ("mn*") on the instance's
# path as the Parameters rows write it ("DUT/mn20") or on its last part ("mn20"). Only instances whose width
# (parameter `w`) the task varies are seen: a fixed transistor adds a constant, which the formula can state itself.
SIZE_SOURCE = 'size_estimate'
SIZE_FUNCTIONS = {'fingers': 2, 'width': 1, 'count': 1, 'larger': 2, 'smaller': 2}
_SIZE_ALLOWED = _ALLOWED + (ast.Call,)
_STRING = re.compile(r'"([^"\\]*)"')


def _size_tree(text):
    """(syntax tree, patterns, None) of a size formula, or (None, None, why)."""
    from analog_optimizer.netlist.expressions import NUMBER, SCALES
    source = (text or '').strip() if isinstance(text, str) else ''
    if not source:
        return None, None, 'the formula is empty'
    if len(source) > 300:                                              # schema.MeasurementDefinition.signal
        return None, None, 'longer than 300 characters'
    patterns = []

    def keep(match):                                                   # a pattern holds digits and letters: keep the
        patterns.append(match[1])                                      # number reader away from it
        return f'"{len(patterns) - 1}"'

    def number(match):
        suffix = match[2]
        if suffix and suffix not in SCALES:
            raise ValueError(f'unsupported number suffix {suffix!r}')
        value = float(match[1]) * SCALES.get(suffix, 1.0)
        if not math.isfinite(value):
            raise ValueError('a number is too large')
        return repr(value)
    try:
        pieces = _STRING.split(_STRING.sub(keep, source))              # text, index, text, index, ...
        tree = ast.parse(''.join(NUMBER.sub(number, piece) if i % 2 == 0 else f'"{piece}"' for i, piece in enumerate(pieces)),
                         mode='eval')
    except SyntaxError:
        return None, None, 'not a formula (check the brackets, quotes and operators)'
    except (ValueError, RecursionError) as exc:
        return None, None, str(exc)
    nodes = list(ast.walk(tree))
    if len(nodes) > 128:
        return None, None, 'too complex'
    used = []
    for node in nodes:
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name not in SIZE_FUNCTIONS or node.keywords or len(node.args) != SIZE_FUNCTIONS[name]:
                return None, None, (f'{name}() takes {SIZE_FUNCTIONS[name]} value(s)' if name in SIZE_FUNCTIONS else
                                    f'only {", ".join(sorted(SIZE_FUNCTIONS))} may be called')
            if name in ('fingers', 'width', 'count'):
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    return None, None, f'{name}() needs an instance pattern in double quotes first, e.g. {name}("mn*"...)'
                used.append(patterns[int(first.value)])
    calls = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
    firsts = {id(n.args[0]) for n in nodes if isinstance(n, ast.Call) and n.func.id in ('fingers', 'width', 'count')}
    for node in nodes:
        if id(node) in calls or id(node) in firsts:
            continue
        if isinstance(node, ast.Name):
            return None, None, f'{node.id!r}: a size formula reads sizes only, no Probe and no other name'
        if not isinstance(node, _SIZE_ALLOWED) or (isinstance(node, ast.Constant) and type(node.value) not in (int, float)):
            what = {ast.Attribute: 'a dotted name', ast.Compare: 'a comparison', ast.Constant: 'a text outside a pattern'}.get(type(node), type(node).__name__)
            return None, None, f'{what} is not allowed'
    if not used:
        return None, None, 'the formula reads no size: use fingers("..." ...), width("...") or count("...")'
    return (tree, tuple(patterns)), tuple(dict.fromkeys(used)), None


def parse_size_formula(text):
    """(instance patterns the formula reads, None) when `text` is a size formula, else (None, why)."""
    _, used, why = _size_tree(text)
    return used, why


def size_matches(pattern, instance):
    """Does `pattern` name the instance written `instance` ("DUT/mn20")? On the whole path or on its last part."""
    path = str(instance).replace('.', '/')
    return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path.rsplit('/', 1)[-1], pattern)


def instance_widths(parameters):
    """{instance: width in m} from a candidate's parameters {(instance, parameter name): value}."""
    return {instance: value for (instance, name), value in (parameters or {}).items() if name == 'w' and is_finite_number(value)}


def size_value(text, widths):
    """The value of a size formula for `widths` = {instance: width in m}, or None: a formula that does not parse, a
    pattern that matches no varied width, a limit that is not positive, arithmetic that fails."""
    parsed, _, why = _size_tree(text)
    if why is not None:
        return None
    tree, patterns = parsed

    def matching(node):
        found = [w for instance, w in widths.items() if size_matches(patterns[int(node.value)], instance)]
        if not found:
            raise _Missing()
        return found

    def value(node):
        if isinstance(node, ast.Expression):
            return value(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            return -value(node.operand) if isinstance(node.op, ast.USub) else value(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = value(node.left), value(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return a / b
            return a ** b
        name = node.func.id
        if name == 'fingers':
            limit = value(node.args[1])
            if not limit > 0:
                raise _Missing()
            return float(sum(math.ceil(w / limit - 1e-9) for w in matching(node.args[0])))
        if name == 'width':
            return float(sum(matching(node.args[0])))
        if name == 'count':
            return float(len(matching(node.args[0])))
        a, b = value(node.args[0]), value(node.args[1])
        return max(a, b) if name == 'larger' else min(a, b)
    try:
        result = value(tree)
    except (_Missing, ArithmeticError, ValueError, OverflowError, RecursionError):
        return None
    return result if isinstance(result, float) and math.isfinite(result) else None


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
    sizes: tuple = ()         # (source_name, formula, canonical unit) of the probes that measure the sizes (record 7.308)

    @classmethod
    def from_config(cls, config) -> 'SpecPlan':
        probes = tuple((m.measurement_id, m.source_name) for m in config.measurements)
        sizes = tuple((m.source_name, m.signal or '', units.canonical_unit(m.unit) if units.known(m.unit) else m.unit)
                      for m in config.measurements if m.result_source == SIZE_SOURCE and m.source_name)
        table = {p[0]: p for p in probes}
        specs = []
        for t in config.targets:
            text = t.equation.strip()
            probe = text if text in table else None
            specs.append(SpecEntry(t.metric_id, text, units.canonical_unit(t.unit) if units.known(t.unit) else t.unit,
                                   bool(t.active and t.hard), probe, probe is not None and table[probe][1] == t.metric_id))
        return cls(probes, tuple(specs), sizes)

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
            values[probe_id] = value if is_finite_number(value) else None
        return values

    def spec_values(self, raw=None, *, probes=None) -> dict:
        """{spec name: value | None}, each spec's equation over the probe values."""
        probes = self.probe_values(raw or {}) if probes is None else probes
        values = {}
        for spec in self.specs:
            value = probes.get(spec.probe) if spec.probe is not None else evaluate(spec.equation, probes.get)
            values[spec.spec_id] = value if is_finite_number(value) else None
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
        sized = {source for source, _, _ in self.sizes}                # worked out here, never asked of the simulator
        return tuple(name for name in dict.fromkeys(names) if name not in sized)

    def size_results(self, parameters) -> dict:
        """{source name: value | None} of the probes that measure the sizes, for a candidate's parameters
        {(instance, parameter name): value}."""
        widths = instance_widths(parameters)
        return {source: size_value(formula, widths) for source, formula, _ in self.sizes}

    # ------------------------------------------------------------------ inside a lane
    def extend(self, result, parameters=None):
        """`result` plus the value of every computed spec under its own name (unit: the spec's canonical unit), and
        before that the value of every probe that measures the sizes under its source name - a result of its own, which
        a spec may then read through that probe. `parameters` is the candidate's {(instance, parameter name): value}."""
        if self.sizes:
            taken = [source for source, _, _ in self.sizes if source in result.metrics]
            if taken:                                              # validation refuses this; never overwrite a measurement
                raise ValueError(f'Size probe(s) {taken} carry the name of a simulator result: rename their source')
            values = self.size_results(parameters)
            metrics, sized_units, validity = dict(result.metrics), dict(result.metric_units), dict(result.metric_validity)
            for source, _, unit in self.sizes:
                metrics[source], sized_units[source], validity[source] = values[source], unit, values[source] is not None
            result = replace(result, metrics=metrics, metric_units=sized_units, metric_validity=validity)
        injected = [s for s in self.specs if not s.result_backed]
        if not injected:
            return result
        clash = [s.spec_id for s in injected if s.spec_id in result.metrics]
        if clash:                                                  # validation refuses this; never overwrite a measurement
            raise ValueError(f'Spec(s) {clash} carry the name of a simulator result but are computed by an equation: rename them')
        usable = {name: value for name, value in result.metrics.items()
                  if result.metric_validity.get(name) is True and is_finite_number(value)}
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
        """Make `backend` answer every simulation with the computed specs and the size results added. A no-op when every
        spec is result-backed and no probe measures the sizes."""
        if not self.injected and not self.sizes:
            return backend
        simulate, plan = backend.run_simulation, self

        def run_simulation(request):
            return plan.extend(simulate(replace(request, required_metrics=plan.request_names(request.required_metrics))),
                               getattr(request, 'parameters', None))
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
        reference = abs(value) if is_finite_number(value) and value != 0 else magnitude(spec.unit)
        added.append((spec.spec_id, spec.unit, float(reference)))
        known[spec.spec_id] = reference
    return tuple(added)


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_finite = is_finite_number
