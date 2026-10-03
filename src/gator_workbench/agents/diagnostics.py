"""Integration diagnostics for the BACKEND process environment.

A working interactive Claude/Codex session does not prove that a background web process has
the same HOME, PATH, authentication context or skills. These checks run inside the backend
process and expose the differences. They make no model request and read no credential:
  * CLI presence and ``--version`` (local, non-billable);
  * authentication: reported as ``unknown`` - no documented non-billable check exists, so it is
    only learned from the first real request. No undocumented subcommand is probed;
  * skill visibility: the documented discovery locations are inspected ON DISK. That proves a
    file exists, not that a session loaded it, and is labelled accordingly;
  * nested-session hints: reported, never worked around by deleting environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from .. import directories
from ..paths import repo_root
from ..security import redact

BRIDGE_SKILL_NAMES = ('virtuoso', 'spectre', 'netlist', 'optimizer', 'virtuoso-bridge', 'analog-optimizer')
NESTED_HINTS = ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_SSE_PORT')


def _version(executable):
    try:
        done = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL, shell=False)
        return dict(ok=done.returncode == 0, text=redact((done.stdout or done.stderr).strip(), 200))
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(ok=False, text=f'{type(exc).__name__}: {exc}')


def skill_visibility(home=None, project=None) -> dict:
    home = Path(home or os.path.expanduser('~'))
    project = Path(project or repo_root())
    locations = [('project', project / '.claude' / 'skills'), ('user', home / '.claude' / 'skills')]
    found = []
    for scope, directory in locations:
        if directory.is_dir():
            for child in sorted(directory.iterdir()):
                if (child / 'SKILL.md').is_file():
                    found.append(dict(scope=scope, name=child.name, path=str(child / 'SKILL.md')))
    plugins = home / '.claude' / 'plugins'
    other = []
    for label, directory in (('project .agents/skills (Codex/agents convention)', project / '.agents' / 'skills'),
                             ('~/.codex/skills', home / '.codex' / 'skills'),
                             ('bridge checkout skills/', directories.local_path('bridge_checkout', home) / 'skills')):
        if directory.is_dir():
            names = sorted(c.name for c in directory.iterdir() if (c / 'SKILL.md').is_file())
            if names:
                other.append(dict(location=label, path=str(directory), skills=names))
    bridge = [s for s in found if s['name'] in BRIDGE_SKILL_NAMES]
    summary = (f"{len(bridge)} bridge-related skill(s) present in Claude discovery locations"
               if bridge else 'No bridge skill exists in a Claude Code discovery location '
                              '(.claude/skills/<name>/SKILL.md in the project or in ~).')
    if other and not bridge:
        summary += (' Skills DO exist elsewhere (' + '; '.join(f"{o['location']}: {', '.join(o['skills'])}" for o in other)
                    + '), but a skill installed for Codex or lying in another repository is not loaded by Claude Code.')
    return dict(claude_discovery_locations=[dict(scope=s, path=str(p), exists=p.is_dir()) for s, p in locations],
                plugins_directory=dict(path=str(plugins), exists=plugins.is_dir()),
                claude_visible_on_disk=found, bridge_skills_visible_on_disk=bridge,
                any_visible_on_disk=bool(bridge), skills_elsewhere_not_loaded_by_claude=other, summary=summary,
                verification_level='file_present_on_disk_only; whether a running session actually loaded a skill is '
                                   'NOT verified by this check',
                install_proposal=None if bridge else install_proposal(other, project))


def install_proposal(other, project):
    """A non-destructive way to make an existing skill visible. Proposed, never executed."""
    source = next((o for o in other if 'bridge checkout' in o['location']), None)
    if source is None:
        return None
    target = Path(project) / '.claude' / 'skills'
    return dict(
        action='proposal_only', executed=False,
        reason='Make the upstream bridge skills discoverable by Claude Code for this project without copying or '
               'editing the originals.',
        commands=[f'mkdir -p {target}'] + [f"ln -s {source['path']}/{name} {target}/{name}" for name in source['skills']],
        notes=['Symbolic links keep the upstream files as the single source; nothing is overwritten.',
               'Review first: a project skill is loaded into every Claude Code session started in this repository.',
               'Afterwards confirm in a NEW session that the skill is listed; a file on disk is not proof of loading.',
               'Do not create a differently-named fake skill, and do not use Codex `$skill` syntax in Claude.'])


def environment_report() -> dict:
    nested = {name: os.environ[name] for name in NESTED_HINTS if name in os.environ}
    return dict(
        python=sys.executable, cwd=os.getcwd(), home=os.path.expanduser('~'), user_id=os.getuid(),
        path=os.environ.get('PATH', '').split(os.pathsep),
        nested_session_suspected=bool(nested), nested_session_variables=sorted(nested),
        nested_session_note=('The backend appears to have been started from inside a Claude Code session. A nested '
                             '`claude` may be restricted. Start the backend from a separate normal terminal instead. '
                             'Protective environment variables are never removed to work around this.') if nested else None,
        note='These values describe the BACKEND process. An interactive terminal may differ in PATH, HOME, '
             'authentication and skills.')


def diagnose() -> dict:
    report = dict(environment=environment_report(), skills=skill_visibility(), providers={})
    for name, binary in (('claude_code', 'claude'), ('codex', 'codex')):
        path = shutil.which(binary)
        entry = dict(executable=path, installed=path is not None)
        if path:
            entry['version'] = _version(path)
        entry['authentication'] = dict(status='unknown', basis='No documented non-billable authentication check; '
                                       'learned from the first real request. Tokens are never read or displayed.')
        entry['model_availability'] = dict(status='unknown', basis='Not probed: probing would make paid requests.')
        report['providers'][name] = entry
    report['providers']['disabled'] = dict(installed=True, note='Manual task export / structured-result import.')
    return report
