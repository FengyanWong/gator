"""A trimmed model library for real Spectre runs, built for whatever circuit a task holds (record 7.154, user request of
2026-10-03: "build the trimmed library for any circuit").

Every fresh Spectre reads the deck's ``include "<model file>" section=<corner>``. A PDK's corner section usually loads
every device family of the PDK - GPDK045's ``tt``: 23 parts from 9 files, every transistor family, diodes, bipolars,
capacitors, resistors, an inductor - while a circuit uses a few, and reading the others costs about 0.25 s of each job
(record 7.153). Here, for any circuit and every section (corner) of the model file:

1. ``read_structure`` reads the library's layout on the simulator host BY NAMES ONLY, with an awk script (``AWK``): its
   sections, the includes in each, the subcircuits and models each defines, the masters its subcircuits use, and how
   many other statements it has. No model text leaves the host.
2. ``devices_used`` lists the masters of a deck's instances.
3. ``plan_library`` keeps, of the parts a section includes, those that define a device the circuit uses, those that
   these need, and every part that defines no device at all (switches such as GPDK045's SOA checks), in the library's
   own order. A section with statements of its own besides its includes, or one from which nothing could be left out,
   is not trimmed.
4. ``apply`` puts the kept parts' include lines - the library's own files, absolute paths - in place of the deck's one
   model include, for the deck's own section: a corner deck gets that corner's parts.

When (``attach``, called where a real run's environment is built): only for a task whose baseline was recorded, which
was simulated with the full library (a task's Baseline simulation has none yet, so it keeps the full library,
and a reference is never replaced). Every simulated reset of the start design is compared with that baseline at 1e-6
(``NativeEnvironmentFactory``), so a part left out that mattered stops the run instead of passing unnoticed; a part
missing for a device makes Spectre stop with an undefined-subcircuit error. The corner check keeps the full library:
it has no baseline at the corners. Anything that goes wrong while reading or planning leaves the full library in place
and says why in the run's ``model_library`` event. ``GATOR_MODEL_LIBRARY=full`` turns it off.
"""
from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import posixpath
import re
import subprocess
from time import perf_counter

from .pdk import REMOTE_PATH

ENV = 'GATOR_MODEL_LIBRARY'
MODES = ('trimmed', 'full')
MAX_FILES = 64                         # model files read, includes followed
SECTION = re.compile(r'^[A-Za-z0-9_]{1,128}$')
_INSTANCE = re.compile(r'^\s*([^\s(]+)\s*\(([^)]*)\)\s*([^\s=()]+)')


class LibraryError(Exception):
    """The error raised when a model library cannot be read or trimmed for a circuit."""
    pass


# One line per fact, names and numbers only: S file section first last | I file section target target-section |
# D file section name (a subcircuit or model defined outside any subcircuit) | R file section master (used inside a
# subcircuit) | O file section count (statements other than structure: definitions, parameters, options ...).
# Section "-" is a file's top level. POSIX awk: the host's gawk and the mawk of the tests run it alike.
AWK = r'''
function bare(s) { gsub(/["']/, "", s); return s }
function ref(name) { if (name != "") refs[sec SUBSEP name] = 1 }
function spectre_master(s,   p, q, rest, n, w, i) {
  p = index(s, "("); q = index(s, ")")
  if (p > 0 && q > p) { rest = substr(s, q + 1); n = split(rest, w); return (n >= 1 && w[1] !~ /=/) ? w[1] : "" }
  n = split(s, w)
  for (i = 2; i <= n; i++) if (w[i] ~ /=/) break
  return (i - 1 >= 2) ? w[i - 1] : ""
}
function emit(   s, n, w, k, t, i, name, at) {
  if (pending == "") return
  s = pending; pending = ""; at = pline
  sub(/[ \t]+\/\/.*$/, "", s)
  if (lang == "spice") sub(/[ \t]+\$.*$/, "", s)
  n = split(s, w)
  if (n == 0) return
  k = tolower(w[1])
  if (k == "simulator") {
    if (s ~ /lang[ \t]*=[ \t]*spice/) lang = "spice"; else if (s ~ /lang[ \t]*=[ \t]*spectre/) lang = "spectre"
    return
  }
  if (lang == "spectre") {
    if (k == "section" && n >= 2 && depth == 0) { sec = w[2]; start = at; return }
    if (k == "endsection" && depth == 0) { if (sec != "-") print "S", F, sec, start, at; sec = "-"; return }
    if (k == "library" || k == "endlibrary") return
    if (k == "include" && n >= 2) {
      t = "-"
      if (match(s, /section[ \t]*=[ \t]*[A-Za-z0-9_]+/)) { t = substr(s, RSTART, RLENGTH); sub(/section[ \t]*=[ \t]*/, "", t) }
      print "I", F, sec, bare(w[2]), t; return
    }
    if (k == "subckt" || (k == "inline" && n >= 3 && tolower(w[2]) == "subckt")) {
      name = (k == "subckt") ? w[2] : w[3]; sub(/\(.*$/, "", name)
      if (depth == 0) { print "D", F, sec, name; own[sec]++ }
      depth++; return
    }
    if (k == "ends") { if (depth > 0) depth--; return }
    if (k == "model" && n >= 3) { if (depth == 0) { print "D", F, sec, w[2]; own[sec]++ } return }
    if (depth > 0) { ref(spectre_master(s)); return }
    own[sec]++; return
  }
  if (k == ".lib" && n == 2 && depth == 0) { sec = w[2]; start = at; return }
  if (k == ".endl" && depth == 0) { if (sec != "-") print "S", F, sec, start, at; sec = "-"; return }
  if (k == ".lib" && n >= 3) { print "I", F, sec, bare(w[2]), w[3]; return }
  if (k == ".include" || k == ".inc") { print "I", F, sec, bare(w[2]), "-"; return }
  if (k == ".subckt" && n >= 2) { if (depth == 0) { print "D", F, sec, w[2]; own[sec]++ } depth++; return }
  if (k == ".ends") { if (depth > 0) depth--; return }
  if (k == ".model" && n >= 2) { if (depth == 0) { print "D", F, sec, w[2]; own[sec]++ } return }
  if (k == ".end") return
  if (depth > 0) { for (i = 2; i <= n; i++) if (w[i] !~ /=/ && w[i] !~ /^[-+0-9.]/) ref(w[i]); return }
  own[sec]++
}
BEGIN { lang = "spectre"; sec = "-"; depth = 0; pending = ""; cont = 0 }
{
  line = $0; sub(/\r$/, "", line)
  if (!cont && lang == "spice" && line ~ /^[ \t]*\+/) { sub(/^[ \t]*\+/, " ", line); pending = pending " " line; next }
  if (!cont && (line ~ /^[ \t]*\/\// || line ~ /^\*/ || line ~ /^[ \t]*$/)) next
  if (cont) pending = pending " " line; else { emit(); pending = line; pline = NR }
  cont = 0
  if (pending ~ /\\[ \t]*$/) { sub(/\\[ \t]*$/, "", pending); cont = 1 }
}
END {
  emit()
  for (k in own) print "O", F, k, own[k]
  for (k in refs) { split(k, parts, SUBSEP); print "R", F, parts[1], parts[2] }
}
'''


def structure_script(files) -> str:
    """The bash script that reads `files` on the host: an F line (size, modification time) or an X line (unreadable)
    per file, then the awk lines. Every path passed `REMOTE_PATH` - no shell character - and is quoted anyway."""
    for path in files:
        if not REMOTE_PATH.match(path) or '/../' in path:
            raise LibraryError(f'not a plain absolute path on the simulator host: {path!r}')
    listed = ' '.join(f"'{path}'" for path in files)
    return ('set -u\nprog=$(mktemp) || exit 97\ntrap \'rm -f "$prog"\' EXIT\n'
            "cat > \"$prog\" <<'GATOR_MODEL_LIBRARY_AWK'\n" + AWK.strip('\n') + '\nGATOR_MODEL_LIBRARY_AWK\n'
            f'for f in {listed}; do\n'
            '  if [ -r "$f" ] && [ -f "$f" ]; then\n'
            '    echo "F $f $(stat -c \'%s %Y\' "$f" 2>/dev/null || echo \'? ?\')"\n'
            '    awk -v F="$f" -f "$prog" "$f"\n'
            '  else echo "X $f"; fi\n'
            'done\n')


def host_runner(config, *, timeout=120):
    """run(script) -> its output, run by bash on the Spectre host through the bridge's own SSH runner - the one its
    SpectreSimulator uses - or locally when that host is this machine. The bridge settings it loads are put back."""
    def run(script):
        from virtuoso_bridge.env import get_runtime_env_file, load_vb_env, set_runtime_env_file
        from virtuoso_bridge.transport.remote_roles import remote_host_roles_from_os
        from virtuoso_bridge.transport.tunnel import SSHClient, _is_localhost
        prior_file, prior_env = get_runtime_env_file(), {k: v for k, v in os.environ.items() if k.startswith('VB_')}
        set_runtime_env_file(config.env_file.resolve())
        try:
            load_vb_env()
            if _is_localhost(remote_host_roles_from_os(config.profile, load=False).spectre_host):
                done = subprocess.run(['bash'], input=script, capture_output=True, text=True, timeout=timeout)
                code, out, err = done.returncode, done.stdout, done.stderr
            else:
                if not SSHClient.is_running(config.profile):
                    raise LibraryError('the bridge connection to the simulator host is not running')
                runner = SSHClient.from_env(profile=config.profile).spectre_runner
                if runner is None:
                    raise LibraryError('the bridge has no SSH runner for the Spectre host')
                command = f"echo {base64.b64encode(script.encode()).decode()} | base64 -d | bash"
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):     # the runner echoes its command
                    code, out, err = runner.run_command(command, timeout=timeout)
            if code != 0:
                raise LibraryError(
                    f'reading the model library on the simulator host failed (exit {code}): {err.strip()[-300:]}')
            return out
        finally:
            set_runtime_env_file(prior_file)
            for key in [k for k in os.environ if k.startswith('VB_') and k not in prior_env]:
                del os.environ[key]
            os.environ.update(prior_env)
    return run


def _read_structure_section(tag, rest, entry):
    """Apply a section record to the collected model-library structure."""
    if tag == 'S' and len(rest) == 4:
        entry(rest[0], rest[1])['span'] = (int(rest[2]), int(rest[3]))
    elif tag == 'I' and len(rest) == 4:
        entry(rest[0], rest[1])['includes'].append((rest[2], None if rest[3] == '-' else rest[3]))
    elif tag == 'D' and len(rest) == 3:
        entry(rest[0], rest[1])['defines'].add(rest[2])
    elif tag == 'R' and len(rest) == 3:
        entry(rest[0], rest[1])['refs'].add(rest[2])
    elif tag == 'O' and len(rest) == 3:
        entry(rest[0], rest[1])['own'] = int(rest[2])


def parse_structure(text):
    """(files, sections) from the script's output. files: {path: (size, mtime) or None when unreadable};
    sections: {(file, section or '-'): dict(includes=[(target as written, section or None)], defines, refs, own, span)}."""
    files, sections = {}, {}

    def entry(file, section):
        return sections.setdefault((file, section), dict(includes=[], defines=set(), refs=set(), own=0, span=None))
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        tag, rest = words[0], words[1:]
        if tag == 'F' and len(rest) >= 1:
            files[rest[0]] = tuple(rest[1:3])
        elif tag == 'X' and len(rest) == 1:
            files[rest[0]] = None
        else:
            _read_structure_section(tag, rest, entry)
    return files, sections


def resolve(including, target):
    """An include's file as an absolute path: relative to the including file's folder, as Spectre resolves it. None
    when it is not a plain path."""
    path = posixpath.normpath(target if target.startswith('/') else posixpath.join(posixpath.dirname(including),
        target))
    return path if REMOTE_PATH.match(path) else None


def read_structure(run, model_file):
    """(files, sections) of the model file and everything it includes, read in rounds: the files named so far, then the
    ones their includes add. `run(script) -> output` (`host_runner`)."""
    if not REMOTE_PATH.match(model_file or '') or '/../' in model_file:
        raise LibraryError('The model file must be a plain absolute path on the simulator host')
    files, sections, wanted = {}, {}, [model_file]
    while wanted:
        if len(files) + len(wanted) > MAX_FILES:
            raise LibraryError(f'the model file includes more than {MAX_FILES} files; not read further')
        new_files, new_sections = parse_structure(run(structure_script(wanted)))
        for path in wanted:
            files[path] = new_files.get(path)
        sections.update(new_sections)
        wanted = []
        for (file, _), info in new_sections.items():
            for target, _ in info['includes']:
                path = resolve(file, target)
                if path is not None and path not in files and path not in wanted:
                    wanted.append(path)
    if files.get(model_file) is None:
        raise LibraryError(f'{model_file} cannot be read on the simulator host')
    return files, sections


def devices_used(deck):
    """The masters a Spectre deck's instances name, at every level, without the subcircuits the deck defines itself.
    Sources, primitives and the like are among them; the library defines none of them, so they keep no part."""
    from analog_optimizer.backends.native_preparation import netlist_statements
    masters, defined = set(), set()
    for statement in netlist_statements(deck):
        words = statement.split()
        if words[0] == 'simulator' and re.search(r'lang\s*=\s*spice', statement):
            raise LibraryError('the deck has parts in SPICE syntax, whose devices are not read here')
        if words[0] == 'subckt' or (words[0] == 'inline' and len(words) > 2 and words[1] == 'subckt'):
            defined.add(words[1 if words[0] == 'subckt' else 2].split('(')[0])
            continue
        match = _INSTANCE.match(statement)
        if match:
            masters.add(match.group(3))
    return masters - defined


def plan_library(structure, model_file, devices) -> dict:
    """What a run of a circuit with `devices` keeps of every section of `model_file` (see the module text): dict(
    model_file, sections={section: [include lines]}, parts={section: [kept, of]}, not_trimmed={section: why},
    devices=[the used devices the library defines])."""
    files, sections = structure
    used = {d.lower() for d in devices}

    def closure(file, section, seen):
        key = (file, section or '-')
        if key in seen:
            return
        seen.add(key)
        info = sections.get(key)
        if info is None:
            if section is not None or files.get(file) is None:
                raise LibraryError(f'{file} has no section {section}' if files.get(file) is not None
                                   else f'{file} cannot be read')
            return                                         # a file without top-level statements
        for target, inner in info['includes']:
            path = resolve(file, target)
            if path is None:
                raise LibraryError(f'{file} includes {target!r}, not a plain path')
            closure(path, inner, seen)

    # ---- Plan each top-level section separately and retain reasons a section cannot be trimmed.
    found, plans, parts, why = set(), {}, {}, {}
    for (file, section), info in sections.items():
        if file != model_file or section == '-':
            continue
        try:
            if info['own']:
                raise LibraryError(f'it has {info["own"]} statements of its own besides its includes')
            units = []
            for target, inner in info['includes']:
                path = resolve(file, target)
                if path is None:
                    raise LibraryError(f'it includes {target!r}, not a plain path')
                if inner is not None and not SECTION.match(inner):
                    raise LibraryError(f'it includes section {inner!r} of {target}')
                seen = set()
                closure(path, inner, seen)
                defines = {d.lower() for key in seen for d in sections.get(key, {}).get('defines', ())}
                refs = {r.lower() for key in seen for r in sections.get(key, {}).get('refs', ())}
                units.append(dict(path=path, section=inner, defines=defines, refs=refs))
            keep = [bool(u['defines'] & used) or not u['defines'] for u in units]
            while True:                                    # what the kept parts' subcircuits use, defined elsewhere
                kept = [u for u, k in zip(units, keep) if k]
                missing = set().union(*(u['refs'] for u in kept)) - set().union(*(u['defines'] for u in kept))
                more = [i for i, u in enumerate(units) if not keep[i] and u['defines'] & missing]
                if not more:
                    break
                for i in more:
                    keep[i] = True
            if all(keep):
                raise LibraryError('the circuit needs every part it includes')
            found |= set().union(*(u['defines'] & used for u, k in zip(units, keep) if k))
            plans[section] = [f'include "{u["path"]}"' + (f' section={u["section"]}' if u['section'] else '')
                              for u, k in zip(units, keep) if k]
            parts[section] = [sum(keep), len(units)]
        except LibraryError as exc:
            why[section] = str(exc)
    return dict(model_file=model_file, sections=plans, parts=parts, not_trimmed=why, devices=sorted(found))


def apply(deck, model_file, section, library):
    """`deck` with its model include replaced by the trimmed one of `section`; the deck unchanged when there is no
    library, no trimmed section of that name, or not exactly one include line of that file and section."""
    lines = (library or {}).get('sections', {}).get(section)
    if not lines or library.get('model_file') != model_file:
        return deck
    old = f'include "{model_file}" section={section}'
    rows = deck.split('\n')
    at = [i for i, row in enumerate(rows) if row.strip() == old]
    if len(at) != 1:
        return deck
    kept, of = library['parts'][section]
    note = f'// GATOR trimmed model library: {kept} of the {of} parts of {model_file} section {section} (record 7.154)'
    return '\n'.join(rows[:at[0]] + [note, *lines] + rows[at[0] + 1:])


def summary(library, note=None) -> dict:
    """What the run's `model_library` event says."""
    if library is None:
        return dict(trimmed=False, note=note)
    return dict(trimmed=True, model_file=library['model_file'], parts=library['parts'], devices=library['devices'],
                not_trimmed=library['not_trimmed'], read_seconds=round(library.get('read_seconds', 0.0), 3),
                note='The decks load only these parts of the model file. Each simulated reset of the start design is '
                     'compared with the task\'s recorded baseline (full library) at 1e-6.')


def attach(profile, config, *, reference, structure, run=None):
    """Give `profile` the trimmed library its run's decks use (`profile.model_library`, None for the full library) and
    the run event's content (`profile.model_library_event`). Never fails the run: a problem leaves the full library."""
    mode = os.environ.get(ENV, 'trimmed')
    if mode not in MODES:
        raise ValueError(f'{ENV} must be one of {", ".join(MODES)}, not {mode!r}')
    library, note = None, None
    profile.model_library = None
    if mode == 'full':
        note = f'{ENV}=full: the decks include the whole model file'
    elif reference is None:
        note = ('No recorded baseline yet: this run includes the whole model file (a Baseline simulation records '
                'the baseline that later runs, with the trimmed library, compare with)')
    else:
        started = perf_counter()
        try:
            text = structure
            try:                                           # a Maestro deck's head and tail, around the exported circuit
                text += '\n' + profile.maestro['head'] + '\n' + profile.maestro['tail']
            except Exception:
                pass
            library = plan_library(read_structure(run or host_runner(config), config.model_file), config.model_file,
                                   devices_used(text))
            if not library['sections']:
                note = ('Nothing to leave out of the model file, so the decks include all of it: ' + '; '.join(
                    f'section {s}: {w}' for s, w in sorted(library['not_trimmed'].items()))
                    if library['not_trimmed'] else 'The model file has no sections, so the decks include all of it')
                library = None
            else:
                library['read_seconds'] = perf_counter() - started
        except Exception as exc:                          # the run goes on with the whole model file
            library, note = None, (
                f'The model library could not be read, so the decks include the whole model file: {exc}'
            )
    profile.model_library = library
    profile.model_library_event = summary(library, note)
    return library
