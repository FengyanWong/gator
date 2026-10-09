"""The folders outside the repository that the simulator connection uses, as settings of the connection module (record
7.168; user: "the project might be used by others. Add directory settings for necessary files in the connection module
with current setting as default").

Each folder's default is the value the code used before this record. A changed value lives in the connection file's
`"directories"` block (`connection.connection_file()`, next to the connections; only values that differ from the default
are written) and is edited in the Connection window. Three folders are on this machine, two on the simulator host
(`~` there is the simulator user's home, read from Virtuoso when the folder is used). Precedence: a field's environment
variable, then the file, then the default. A value in the file that fails its check is not used: the default applies
and the window says why.

Not here: the settings folder itself (it holds the connection file: `GATOR_WORKBENCH_SETTINGS_DIR`), the output root (the
output panel), and Spectre's job folders on the simulator host, which are the bridge's own setting
(`VB_REMOTE_SCRATCH_ROOT` in the bridge env file, `/tmp` when unset)."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from .paths import connection_file
from .storage.atomic import read_json

LOCAL, SIMULATOR = 'local', 'simulator'
BLOCK = 'directories'


@dataclass(frozen=True)
class Folder:
    side: str
    label: str
    default: str
    used_for: str
    takes_effect: str
    env: str | None = None
    writable: bool = False            # GATOR writes into it: checked by writing a file there before it is saved


FIELDS = {
    'adapter_state': Folder(
        LOCAL, 'Adapter state', '~/.local/state/gator/bridge-state',
        'The session lock that runs, corner checks and Save task take, so that two never work on a cell at once, and the '
        'crash journal of every write to a cell. Every GATOR process of this machine must use the same folder. Keep it on '
        'the local disk (on D: from WSL a candidate\'s journal writes took 16 ms instead of 1) and out of /tmp, which a '
        'restart empties.',
        'the next run, corner check or Save task', env='GATOR_BRIDGE_STATE_DIR', writable=True),
    'local_scratch': Folder(
        LOCAL, 'Simulator scratch', '/tmp/gator-work',
        'Export packages and Spectre job folders of a run whose output folder is on a slow mount (D: from WSL). Each run '
        'gets a folder of its own there, removed when the run ends; kept job folders move to the run folder. On a slow '
        'mount itself it would gain nothing and is refused.',
        'the next run', writable=True),
    'bridge_checkout': Folder(
        LOCAL, 'virtuoso-bridge checkout', '~/virtuoso-bridge-lite',
        'Where "Add a connection" looks for the bridge package (its .venv) when the backend\'s Python cannot import it, '
        'and where the agent diagnostics look for the bridge\'s skills. A connection keeps the package folder it was '
        'created with.',
        'the next "Add a connection"'),
    'simulator_ic': Folder(
        SIMULATOR, 'Initial-condition files', '~/.gator/ic',
        'Save task writes a Maestro test\'s initial conditions there, as a file the test includes; the folder is made '
        'when missing. Files already registered in a test - also in the default folder - are still recognized.',
        'the next Save task'),
    'maestro_netlist': Folder(
        SIMULATOR, 'Maestro netlists', '/tmp/gator_maestro_netlist',
        'Maestro writes a test\'s netlist there when a task is saved, and GATOR downloads it. On a host shared with other '
        'users, or where Virtuoso\'s /tmp is not the one SSH sees, choose a folder of your own (e.g. ~/gator/netlists).',
        'the next Save task'),
}
REMOTE_PATH = re.compile(r'^~?(?:/[A-Za-z0-9_.+\-]+)+$')      # characters that pass SKILL strings and shell commands as they are


class InvalidDirectory(ValueError):
    def __init__(self, key, message):
        super().__init__(f'{FIELDS[key].label if key in FIELDS else key}: {message}')
        self.key = key


def normalized(key, raw) -> str | None:
    """The value as stored, or None for the default (empty, or the default itself). Checks the spelling only; what a
    local folder holds is checked by `check_local` when it is saved."""
    if key not in FIELDS:
        raise InvalidDirectory(key, f'unknown folder; known: {", ".join(FIELDS)}')
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidDirectory(key, 'a folder is a text')
    text = raw.strip()
    if len(text) > 1 and text.endswith('/'):
        text = text.rstrip('/') or '/'
    if not text or text == FIELDS[key].default:
        return None
    if len(text) > 1024 or any(ord(c) < 32 for c in text):
        raise InvalidDirectory(key, 'a folder is one line of at most 1024 characters')
    if FIELDS[key].side == SIMULATOR:
        if not REMOTE_PATH.match(text) or any(part in ('.', '..') for part in text.split('/')):
            raise InvalidDirectory(key, f'{text!r} is not a folder on the simulator host as GATOR can pass it: start with / or '
                                        '~/ (the simulator user\'s home) and use letters, digits and _ . + - only, no "..".')
        return text
    if not (text.startswith('/') or text == '~' or text.startswith('~/')):
        raise InvalidDirectory(key, f'{text!r} is not a full path: start with / or ~/ (the home folder of the backend user).')
    path = Path(text).expanduser()
    if path == Path('/') or path == Path.home() or any(part == '..' for part in path.parts):
        raise InvalidDirectory(key, 'choose a folder of its own - not /, not the home folder itself, no "..".')
    return text


def check_local(key, text) -> None:
    """What a local folder must offer before it is saved: one that GATOR writes into is made when missing and written
    once; the scratch must not be on a slow mount; the bridge checkout must exist."""
    from .layout import SLOW_FILESYSTEMS, filesystem_type
    path, field = Path(text).expanduser(), FIELDS[key]
    if key == 'local_scratch' and filesystem_type(path) in SLOW_FILESYSTEMS:
        raise InvalidDirectory(key, f'{text} is on a slow mount ({filesystem_type(path)}): a scratch there would gain '
                                    'nothing. Choose a folder on the local disk.')
    if field.writable:
        probe = path / f'.gator-write-test-{os.getpid()}'
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe.write_text('GATOR folder check\n')
            probe.unlink()
        except OSError as exc:
            raise InvalidDirectory(key, f'{text} cannot be written: {exc.strerror or exc}.') from None
    elif not path.is_dir():
        raise InvalidDirectory(key, f'there is no folder at {text}.')


def saved() -> tuple[dict, dict]:
    """({key: value} from the connection file, {key: why the file's value is not used}). A missing or unreadable file
    holds nothing; the connection checks say what is wrong with it."""
    try:
        data = read_json(connection_file(), default=None)
    except (OSError, ValueError):
        data = None
    block = data.get(BLOCK) if isinstance(data, dict) else None
    values, problems = {}, {}
    for key, raw in (block.items() if isinstance(block, dict) else ()):
        if key not in FIELDS:
            continue
        try:
            text = normalized(key, raw)
        except InvalidDirectory as exc:
            problems[key] = f'{exc} The default is used.'
            continue
        if text is not None:
            values[key] = text
    return values, problems


def value(key, values=None) -> str:
    """The folder in use, as written (`~` unexpanded): the field's environment variable, else the connection file, else
    the default."""
    field = FIELDS[key]
    if field.env and os.environ.get(field.env):
        return os.environ[field.env]
    return (saved()[0] if values is None else values).get(key) or field.default


def local_path(key, home=None) -> Path:
    """A local folder in use, with `~` expanded - as `home` when given (the functions that take a home for their tests)."""
    if FIELDS[key].side != LOCAL:
        raise ValueError(f'{key} is a folder on the simulator host')
    text = value(key)
    if home is not None and (text == '~' or text.startswith('~/')):
        return Path(home) / text[2:]
    return Path(text).expanduser()


def describe() -> dict:
    """What the Connection window shows: every folder with its default, the value in use and where it comes from."""
    values, problems = saved()
    fields = []
    for key, field in FIELDS.items():
        env = field.env if field.env and os.environ.get(field.env) else None
        fields.append(dict(key=key, side=field.side, label=field.label, default=field.default, saved=values.get(key),
                           value=value(key, values), source='environment' if env else 'file' if key in values else 'default',
                           environment_variable=field.env, set_by_environment=env, problem=problems.get(key),
                           used_for=field.used_for, takes_effect=field.takes_effect))
    return dict(fields=fields, connection_file=str(connection_file()),
                note='Spectre\'s job folders on the simulator host are the bridge\'s own setting: VB_REMOTE_SCRATCH_ROOT in '
                     'the bridge env file (/tmp when unset). The settings folder, which holds the connection file, is '
                     'moved with GATOR_WORKBENCH_SETTINGS_DIR; the output folder is chosen in the output panel.')
