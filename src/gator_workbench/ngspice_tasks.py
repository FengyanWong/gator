"""ngspice netlist tasks: ``ngspice:<name>`` in the Registered task list (2026-09-23, user request).

A task is a SPICE deck the user pasted or loaded in the ngspice window, kept by the workbench in its own folder
(``configs/local/workbench/ngspice/<name>/``: ``netlist.cir`` + ``task.json``), read into the optimizer's circuit
graph by ``ngspice_netlist`` and simulated by ``ngspice_backend`` through an ngspice connection (on this machine
or over ssh). Saving the same name again is the next revision of the task: runs made before keep their own
snapshot of the deck, and a changed deck is a changed task (its hash is part of the task definition).

What a task carries: the deck, where it came from (``source_path``, so relative ``.include`` paths resolve from
that folder), the kinds the user declared for models the deck does not define (``device_kinds``), the labels
(circuit class, PDK id) and what the deck can measure (its ``.meas`` names and printed values).

The starter rows: Parameters = every value the deck lets a run write (top-level elements, and elements inside a
subcircuit used once), widths / resistances / capacitances / inductances optimized within half..twice their value,
lengths / counts / sources fixed; Probes = one row per result; Specs = none (requirements are the user's).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from .analoggym import AnalogGymFactory, export_best_decks, physical_graph
from .connection import named_or_active
from .names import TASK_NAME, TRASH, TRASH_STAMP, WORKING_STATES
from .ngspice_backend import LOCAL_CONCURRENCY, NgspiceEnvFactory, NgspiceLink, NgspiceLinkError
from .ngspice_netlist import KINDS, NetlistError, Parsed, parse_text, rewrite
from .paths import inside, local_settings_dir
from .storage.atomic import UNREADABLE, publish, read_json_quiet, temporary_path, write_json
from .storage.dataset import utcnow
from .task_registry import REAL_AUTHORIZATION_REQUIRED, TaskBlocked, TaskRuntime, starter_project

PREFIX = 'ngspice'
FILES = dict(netlist='netlist.cir', entry='task.json')
NAME = re.compile(TASK_NAME)
MAX_NETLIST_BYTES = 8 * 1024 * 1024
OPTIMIZED_BY_DEFAULT = ('w', 'r', 'c', 'ind')          # lengths, counts and sources start fixed
ROW_UNITS = {'w': ('um', 1e6), 'l': ('um', 1e6), 'm': ('count', 1.0), 'nf': ('count', 1.0), 'r': ('ohm', 1.0),
             'c': ('pF', 1e12), 'ind': ('nH', 1e9), 'dc': ('V', 1.0)}
EVALUATION_BACKEND = 'ngspice (REAL circuit simulation: no license, counted and authorized like every real run)'
NEEDS_NGSPICE_CONNECTION = ('This task runs on ngspice. Choose an ngspice connection ("ngspice on this machine" or '
                            '"ngspice over SSH") in the Connection window, or add one there.')
_NOT_IN_AN_ID = re.compile(r'[^A-Za-z0-9_.\-]')


class NgspiceTaskError(ValueError):
    """Why the task cannot be saved, read or deleted, in words the window can show."""


# ------------------------------------------------------------------------------------------------ the store
def store_root() -> Path:
    return local_settings_dir() / PREFIX


def task_dir(name) -> Path:
    """Validate a task name and return its local storage directory."""
    if not isinstance(name, str) or not NAME.match(name):
        raise NgspiceTaskError('The task name must be lowercase letters, digits and "_" (2-40 characters, starting with a letter)')
    return store_root() / name


def list_tasks() -> dict:
    """{name: entry} of every saved ngspice task, by name."""
    found = {}
    root = store_root()
    for entry_file in sorted(root.glob(f'*/{FILES["entry"]}')) if root.is_dir() else ():
        entry = read_json_quiet(entry_file)            # None when unreadable: not a dict
        if isinstance(entry, dict) and entry.get('name') == entry_file.parent.name:
            found[entry['name']] = dict(entry, directory=str(entry_file.parent))
    return found


def load(name):
    """(entry, deck text) of a saved task; KeyError when there is none."""
    directory = task_dir(name)
    entry_file, netlist = directory / FILES['entry'], directory / FILES['netlist']
    if not entry_file.is_file() or not netlist.is_file():
        raise KeyError(name)
    entry = json.loads(entry_file.read_text())
    return dict(entry, directory=str(directory)), netlist.read_text(encoding='utf8', errors='replace')


def _include_root(entry) -> str | None:
    source = entry.get('source_path')
    return str(Path(source).parent) if source else None


def parse_entry(entry, text) -> Parsed:
    """Parse a saved task deck and apply its AnalogGym graph conversion when required."""
    parsed = parse_text(text, source=str(Path(entry['directory']) / FILES['netlist']) if entry.get('directory') else 'netlist.cir',
                      circuit_id=entry['name'], device_kinds=entry.get('device_kinds') or {}, include_root=_include_root(entry))
    if entry.get('analoggym'):
        physical_graph(parsed)
    return parsed


def check(text, *, device_kinds=None, include_root=None) -> dict:
    """What the window shows before a save: how the deck reads. Nothing is stored, nothing is run."""
    if not isinstance(text, str) or not text.strip():
        return dict(ok=False, problem='The netlist is empty.')
    if len(text.encode('utf8', errors='replace')) > MAX_NETLIST_BYTES:
        return dict(ok=False, problem=f'The netlist is larger than {MAX_NETLIST_BYTES // (1024 * 1024)} MB.')
    try:
        parsed = parse_text(text, source='netlist.cir', circuit_id='check', device_kinds=device_kinds or {}, include_root=include_root)
    except NetlistError as exc:
        return dict(ok=False, problem=str(exc))
    return dict(ok=True, **summary(parsed))


def summary(parsed: Parsed) -> dict:
    """Describe a parsed deck's circuit, writable parameters, measurements and reported problems."""
    graph = parsed.graph
    kinds = {}
    for device in graph.devices:
        kinds[device.kind] = kinds.get(device.kind, 0) + 1
    return dict(title=parsed.title.lstrip('* ').strip(), devices=len(graph.devices), nets=len(graph.nets), kinds=kinds,
                sizable=sorted(f'{d}.{p}' for d, p in parsed.sizables),
                measurements=[dict(name=m.name, analysis=m.analysis, unit=m.unit, line=m.line, text=m.text) for m in parsed.measurements],
                analyses=[a['text'] for a in parsed.analyses], includes=[dict(kind=k, path=p, line=n) for k, p, n in parsed.includes],
                unknown_models=list(parsed.unknown_models), subckt_uses=dict(parsed.subckt_uses),
                has_control=parsed.has_control, has_end=parsed.has_end,
                diagnostics=[dict(code=d.code, severity=d.severity, message=d.message) for d in graph.diagnostics],
                problems=_problems(parsed))


def _problems(parsed: Parsed) -> list:
    """What would stop a run, in plain words (the window shows them before a save)."""
    problems = []
    if not parsed.graph.devices:
        problems.append('No element was found: a deck needs at least one element line (the first line is the title).')
    if not parsed.measurements:
        problems.append('Nothing is measured: add .meas statements (or a .control block that prints named values), so that a '
                        'run has results to judge.')
    if not parsed.analyses and not parsed.has_control:
        problems.append('No analysis was found (.op, .ac, .tran ...): ngspice would simulate nothing.')
    if not parsed.sizables:
        problems.append('No value can be varied: every element sits in a subcircuit used more than once, or every model is unknown.')
    return problems


def save(name, text, *, device_kinds=None, source_path=None, circuit_class='unspecified', pdk_id='unspecified') -> dict:
    """Store the deck as task ngspice:<name> (a new task, or the next revision of an existing one). Returns the entry."""
    directory = task_dir(name)
    if not isinstance(text, str) or not text.strip():
        raise NgspiceTaskError('The netlist is empty.')
    if len(text.encode('utf8', errors='replace')) > MAX_NETLIST_BYTES:
        raise NgspiceTaskError(f'The netlist is larger than {MAX_NETLIST_BYTES // (1024 * 1024)} MB.')
    kinds = clean_kinds(device_kinds)
    root = str(Path(source_path).parent) if source_path else None
    try:
        parsed = parse_text(text, source=str(directory / FILES['netlist']), circuit_id=name, device_kinds=kinds, include_root=root)
    except NetlistError as exc:
        raise NgspiceTaskError(f'The netlist cannot be read: {exc}')
    if not parsed.graph.devices:
        raise NgspiceTaskError('No element was found in the netlist (the first line is the title; elements follow).')
    existing = list_tasks().get(name)
    now = utcnow().isoformat()
    entry = dict(name=name, task_key=f'{PREFIX}:{name}', revision=(existing or {}).get('revision', 0) + 1,
                 created_utc=(existing or {}).get('created_utc', now), updated_utc=now,
                 netlist_sha256=hashlib.sha256(text.encode('utf8', errors='replace')).hexdigest(),
                 source_path=source_path or None, device_kinds=kinds, circuit_class=circuit_class or 'unspecified',
                 pdk_id=pdk_id or 'unspecified', title=parsed.title.lstrip('* ').strip()[:200],
                 measurements=[dict(name=m.name, analysis=m.analysis, unit=m.unit) for m in parsed.measurements],
                 devices=len(parsed.graph.devices), sizable=len(parsed.sizables), simulator='ngspice')
    directory.mkdir(parents=True, exist_ok=True)
    if existing:                                        # the deck before, kept next to the task
        history = directory / 'history'
        history.mkdir(exist_ok=True)
        previous = directory / FILES['netlist']
        if previous.is_file():
            shutil.copy2(previous, history / f'r{existing.get("revision", 0)}.cir')
    netlist = directory / FILES['netlist']
    temporary = temporary_path(netlist)            # a crash mid-write leaves the deck before, never half of the new one
    temporary.write_text(text, encoding='utf8')
    publish(temporary, netlist)
    write_json(directory / FILES['entry'], entry)
    return dict(entry, directory=str(directory), created=existing is None)


def clean_kinds(device_kinds) -> dict:
    """Normalize declared model kinds and reject unsupported kind names."""
    cleaned = {}
    for key, value in (device_kinds or {}).items():
        key, value = str(key).strip().lower(), str(value).strip().lower()
        if not key:
            continue
        if value not in KINDS:
            raise NgspiceTaskError(f'{key}={value}: the kind must be one of {", ".join(KINDS)}')
        cleaned[key] = value
    return cleaned


def parse_kinds_text(text) -> dict:
    """`name=kind` per line (or blank-separated) from the window's box."""
    kinds = {}
    for word in re.split(r'[\s,]+', text or ''):
        if not word:
            continue
        key, equals, value = word.partition('=')
        if not equals or not key or not value:
            raise NgspiceTaskError(f'{word!r}: write model kinds as name=kind, e.g. sky130_fd_pr__nfet_01v8=nmos')
        kinds[key] = value
    return clean_kinds(kinds)


def delete(name, *, run_rows=()) -> dict:
    """Take the task out of the list: its folder is moved aside (never erased). Refused while a run of it works."""
    entry = list_tasks().get(name)
    if entry is None:
        raise NgspiceTaskError(f'Unknown ngspice task {name!r}')
    task_key = entry['task_key']
    for row in run_rows:                                # the run list's rows: only a live run's manifest is read
        if row.get('state') not in WORKING_STATES or not row.get('run_dir'):
            continue
        manifest = read_json_quiet(Path(row['run_dir']) / 'run_manifest.json', UNREADABLE)
        if manifest is UNREADABLE:
            continue
        if (manifest.get('circuit') or {}).get('task_key') == task_key:
            raise NgspiceTaskError(f'Run {row.get("run_id") or row["run_dir"]} of {task_key} is working right now: abort it or let it finish first')
    directory = Path(entry['directory'])
    kept = directory.parent / TRASH / f'{name}.{utcnow().strftime(TRASH_STAMP)}'
    kept.parent.mkdir(parents=True, exist_ok=True)
    directory.rename(kept)
    return dict(deleted=task_key, name=name, kept_copy=str(kept))


def read_file(path, roots) -> dict:
    """A deck read from a file on the backend machine, inside an allowed input root only."""
    if not isinstance(path, str) or not path.strip():
        raise NgspiceTaskError('Give the path of a netlist file on the backend machine.')
    resolved = Path(path).expanduser().resolve()
    if not inside(resolved, roots):
        raise PermissionError('The file is outside the allowed input roots. Roots are added by the backend operator '
                              '(--allow-input-root), never from the browser; or paste the netlist text instead.')
    if not resolved.is_file():
        raise NgspiceTaskError(f'{resolved} is not a file.')
    if resolved.stat().st_size > MAX_NETLIST_BYTES:
        raise NgspiceTaskError(f'{resolved.name} is larger than {MAX_NETLIST_BYTES // (1024 * 1024)} MB.')
    return dict(path=str(resolved), text=resolved.read_text(encoding='utf8', errors='replace'), size=resolved.stat().st_size)


# ------------------------------------------------------------------------------------------------ the connection
def connection_problem(profile_id=None) -> str | None:
    """Why the named (or the active) connection cannot run this task, or None."""
    # lazy: connection.KINDS, not this module's netlist KINDS
    from .connection import KINDS, entry_kind, family_of
    _, key, settings = named_or_active(profile_id)
    if settings is None:
        return NEEDS_NGSPICE_CONNECTION if not key else f'Connection {key!r} is not configured. ' + NEEDS_NGSPICE_CONNECTION
    kind = entry_kind(settings)
    if kind is None or family_of(kind) != 'ngspice':
        label = KINDS[kind]['label'] if kind in KINDS else 'of an unknown kind'
        return f'Connection {key!r} is "{label}". ' + NEEDS_NGSPICE_CONNECTION
    return None


def link_for(profile_id=None):
    """The validated NgspiceLink of the named (or active) connection; NgspiceLinkError otherwise."""
    settings = named_or_active(profile_id)[2]
    if settings is None:
        raise NgspiceLinkError(NEEDS_NGSPICE_CONNECTION)
    return NgspiceLink.from_settings(settings)


# ------------------------------------------------------------------------------------------------ the runtime
def runtime(task_key, name, profile_id=None, *, authorized=False):
    """The TaskRuntime of ngspice:<name>. Local files only; the connection is looked at for the notes and checked
    again when the environment is built (in the run worker)."""
    try:
        entry, text = load(name)
    except KeyError:
        raise TaskBlocked(f'Unknown ngspice task {task_key!r}: it was deleted or never saved.')
    try:
        parsed = parse_entry(entry, text)
    except NetlistError as exc:
        raise TaskBlocked(f'The netlist of {task_key} no longer reads: {exc}')
    graph = parsed.graph
    graph.parameter_groups = []
    problem = connection_problem(profile_id)
    directory = Path(entry['directory'])
    netlist_file = directory / FILES['netlist']

    # ---- Build the simulator environment later, after checking run authorization and connection.
    def builder(compiled, work_root, run_settings):
        if not authorized:
            raise TaskBlocked(REAL_AUTHORIZATION_REQUIRED)
        try:
            link = link_for(profile_id)
        except NgspiceLinkError as exc:
            raise TaskBlocked(str(exc))
        adv = run_settings.advanced
        units = {}
        for spec in compiled.specs:                    # a result-backed spec: the result carries the spec's own unit
            if spec.metric_id in parsed.result_names:
                units[spec.metric_id] = spec.unit
        for probe_id, source in compiled.plan.probes if compiled.plan is not None else ():
            if source in parsed.result_names and source not in units:
                units[source] = parsed.units.get(source) or '1'
        from analog_optimizer.measurements.specs import RewardSettings
        factory, options = NgspiceEnvFactory, {}
        if entry.get('analoggym'):
            factory, options = AnalogGymFactory, dict(bundle=entry['analoggym'])
        return factory(text, compiled.graph, compiled.specs, link, str(work_root), adv.episode_length,
                                 adv.simulation_timeout_seconds, adv.episode_terminates_on_success, units,
                                 dict(entry.get('device_kinds') or {}), _include_root(entry), name, str(netlist_file),
                                 plan=compiled.plan if compiled.plan is not None and compiled.plan.injected else None,
                                 reward_settings=RewardSettings(**run_settings.reward.model_dump()), **options)
    # ---- Describe the saved deck and connection limitations without building an environment.
    notes = [f'ngspice netlist task, revision {entry.get("revision")}: {len(graph.devices)} elements, '
             f'{len(parsed.measurements)} results ({", ".join(parsed.result_names[:8])}{"..." if len(parsed.result_names) > 8 else ""}).']
    if entry.get('source_path'):
        notes.append(f'Loaded from {entry["source_path"]}; relative .include paths resolve from that folder on this machine '
                     '(over SSH, paths in the deck are the other machine\'s).')
    if parsed.unknown_models:
        notes.append('Shown as unknown (simulated by ngspice, not sized): ' + ', '.join(parsed.unknown_models[:10])
                     + '. Declare their kinds in the ngspice window (name=nmos ...) to size them.')
    shared = [s for s, uses in parsed.subckt_uses.items() if uses > 1]
    if shared:
        notes.append('Values inside subcircuits used more than once cannot be varied for one instance alone: ' + ', '.join(shared))
    if problem:
        notes.append(problem)
    else:
        try:
            notes.append(f'Runs through {link_for(profile_id).label} (connection {profile_id or "in use"}).')
        except Exception:
            pass
    if not authorized:
        notes.append('Loaded for viewing and validation. Start asks you to confirm the number of ngspice simulations first.')
    try:
        link = link_for(profile_id)
        concurrency = link.max_concurrency
    except Exception:
        concurrency = LOCAL_CONCURRENCY
    provided = tuple(entry['analoggym']['metric_units']) if entry.get('analoggym') else tuple(parsed.result_names)
    circuit = dict(circuit_class=entry.get('circuit_class') or 'unspecified', pdk_id=entry.get('pdk_id') or 'unspecified',
                   dut_hierarchy=None, netlist_sha256=entry['netlist_sha256'], parser_config_sha256=None,
                   netlist_file=str(netlist_file), parser_config_file=None, topology_id=f'ngspice:{name}',
                   complete=graph.complete, evaluation_backend=EVALUATION_BACKEND, simulator='ngspice', ngspice_task=True,
                   analoggym_task=bool(entry.get('analoggym')),
                   title=entry.get('title'), revision=entry.get('revision'), source_path=entry.get('source_path'),
                   device_kinds=dict(entry.get('device_kinds') or {}), measurements=list(provided),
                   sizable=sorted(f'{d}.{p}' for d, p in parsed.sizables), connection_problem=problem,
                   unknown_models=list(parsed.unknown_models))
    return TaskRuntime(task_key, 'real', graph, provided, circuit, text, str(netlist_file), None, builder,
                       max_concurrency=concurrency, notes=notes, authorized=bool(authorized),
                       reference_metrics=None, connection_family='ngspice')


# ------------------------------------------------------------------------------------------------ the best design
def export_deck(task):
    """The best design's deck for best_design.write_outputs: (netlist text, graph, members) -> the outcome contract of
    export_netlist. Values are written into their own tokens (a once-used subcircuit included) and read back."""
    import math

    if (task.circuit or {}).get('analoggym_task'):
        entry, _ = load(task.task_key.partition(':')[2])
        def benchmark_exporter(netlist_text, graph, members):
            return export_best_decks(netlist_text, entry['analoggym'], entry['device_kinds'], members)
        benchmark_exporter.additional_filenames = ('transient.cir',)
        return benchmark_exporter

    def exporter(netlist_text, graph, members):
        kinds = (task.circuit or {}).get('device_kinds') or {}
        root = str(Path(task.circuit['source_path']).parent) if (task.circuit or {}).get('source_path') else None
        try:
            parsed = parse_text(netlist_text, source=task.netlist_path or 'netlist.cir', circuit_id=task.task_key.partition(':')[2] or 'ngspice',
                                device_kinds=kinds, include_root=root, scan_includes=False)
            assignments = {(m['instance_path'], m['parameter_name']): float(m['value']) for m in members}
            text, _ = rewrite(parsed, assignments)
            again = parse_text(text, source=task.netlist_path or 'netlist.cir', device_kinds=kinds, include_root=root, scan_includes=False)
        except (NetlistError, ValueError) as exc:
            return dict(status='unsupported', reason=str(exc))
        for (device, parameter), value in assignments.items():
            read = again.graph.parameters.get(device, {}).get(parameter)
            if read is None or not read.valid or not math.isclose(read.value, value, rel_tol=1e-9, abs_tol=1e-30):
                return dict(status='unsupported', reason=f'{device}.{parameter} did not read back as {value!r}')
        return dict(status='verified', text=text)
    return exporter


# ------------------------------------------------------------------------------------------------ starter rows
def _round(value, digits=6):
    return float(f'{value:.{digits}g}')


def parameter_rows(parsed: Parsed) -> list:
    """Build starter parameter rows with display units, ranges and default optimization choices."""
    rows = []
    for (device_id, parameter), sizable in sorted(parsed.sizables.items()):
        value = parsed.graph.parameters[device_id][parameter].value
        unit, scale = ROW_UNITS.get(parameter, ('1', 1.0))
        if parameter == 'dc' and next((d.kind for d in parsed.graph.devices if d.id == device_id), None) == 'isource':
            unit = 'A'                                   # a current source's value
        shown = value * scale
        integer = parameter in ('m', 'nf')
        row = dict(variable_id=f'{_NOT_IN_AN_ID.sub("_", device_id)}_{parameter}', instance_path=device_id, parameter_name=parameter,
                   unit=unit, scale='linear', value_type='integer' if integer else 'continuous',
                   optimized=parameter in OPTIMIZED_BY_DEFAULT and shown != 0,
                   notes=f'{sizable.source_name} on line {sizable.token.line}' + (f' of subcircuit {sizable.subckt}' if sizable.subckt else ''))
        if shown != 0:
            low, high = sorted((shown / 2, shown * 2))
            if integer:
                low, high = max(1, int(low)), max(int(high), int(shown) + 1)
                row.update(lower=low, upper=high, step=1)
            else:
                row.update(lower=_round(low), upper=_round(high))
        rows.append(row)
    return rows


def probe_rows(parsed: Parsed) -> list:
    """Build starter probe rows from the deck's recorded measurements."""
    rows = []
    for m in parsed.measurements:
        rows.append(dict(measurement_id=f'm_{m.name}', analysis=m.analysis, result_source='backend_profile', source_name=m.name,
                         unit=m.unit, notes=f'line {m.line}: {m.text}'[:1000]))
    return rows


def starter_config(task_key) -> dict:
    """The rows the editors start from: KeyError for a task that does not exist."""
    name = task_key.partition(':')[2]
    entry, text = load(name)
    if entry.get('starter') and entry.get('analoggym'):
        return entry['starter']
    parsed = parse_entry(entry, text)
    return dict(project=starter_project(task_key),
                circuit=dict(source='registered_task', task_id=task_key, circuit_class=entry.get('circuit_class') or 'unspecified',
                             pdk_id=entry.get('pdk_id') or 'unspecified'),
                parameters=parameter_rows(parsed), measurements=probe_rows(parsed), targets=[])


def task_entries() -> list:
    """What the Registered task list shows for the saved ngspice tasks."""
    problem = connection_problem(None)
    entries = []
    for name, entry in list_tasks().items():
        entries.append(dict(task_key=entry['task_key'], kind='ngspice', circuit_class=entry.get('circuit_class') or 'unspecified',
                            pdk_id=entry.get('pdk_id') or 'unspecified', available=problem is None, blocker=problem,
                            revision=entry.get('revision'), title=entry.get('title'), simulator='ngspice',
                            description=f"ngspice netlist ({entry.get('devices')} elements, {len(entry.get('measurements') or [])} results), "
                                        f"revision {entry.get('revision')}. Runs on an ngspice connection; no license."))
    return entries


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_clean_kinds = clean_kinds
