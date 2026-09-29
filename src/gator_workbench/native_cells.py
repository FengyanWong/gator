"""A cell read from Virtuoso, kept on the backend host so the workbench can show it, validate a
configuration against it and hand its summary to the agent WITHOUT contacting Virtuoso again.

This is the first half of "create a circuit profile from a Virtuoso cell": an explicit, gated,
READ-ONLY import (``bridge_read`` op ``import_cell``) - Virtuoso's own netlist export of the testbench
(or of the cell itself when no testbench is named) plus the parameter readback of the cell - stored
under ``configs/local/workbench/native_cells/<library>/<cell>/``. Nothing here edits a cellview or
starts a simulation, and nothing here makes the cell executable: a draft has no circuit profile, and
every attempt to run it is refused with that reason (``tasks.load_task``, ``runs.prepare_run``, the
static validation).

Device mapping: pin order and parameter meaning are never guessed. The models a draft may use are
the ones already verified in this repository's GPDK045 mappings (``configs/gpdk045_*.json``) and, once
the cell's technology library was loaded with "Load PDK" (``pdk.py``), every component that PDK's own
description names - pins and parameters as the PDK states them. Any other model stays ``unknown`` -
shown, flagged, its pins unnamed. A profile for real runs takes the same models (``profiles._checked_import``).
Net roles are not guessed either: only Spectre's global net ``0`` is marked as ground.

The import also records what the property form of every instance lets a user type (``core_cdf.json``,
``cdf_facts``): the basis of which values a real run may write besides transistor widths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil

from .paths import local_settings_dir, repo_root
from .storage.atomic import sha256_file as _sha256, write_json
from .storage.dataset import utcnow

NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,127}$')          # a plain Cadence name; the same rule as bridge_read.NAME
FILES = dict(netlist='netlist.scs', mapping='mapping.json', core_readback='core_readback.json',
             testbench_readback='testbench_readback.json', meta='meta.json', form_rules='core_cdf.json')
FORMAT = 'gator-native-cell-1'


def store_root() -> Path:
    return local_settings_dir() / 'native_cells'


def cell_dir(library, cell) -> Path:
    for value in (library, cell):
        if not isinstance(value, str) or not NAME.match(value):
            raise ValueError('library and cell must be plain Cadence names')
    return store_root() / library / cell


def verified_models() -> dict:
    """Device models whose pin order and parameters this project has verified, taken from its own
    GPDK045 mappings. A model defined differently in two files is left out rather than chosen."""
    models, conflicting = {}, set()
    for path in sorted((repo_root() / 'configs').glob('gpdk045_*.json')):
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for name, entry in (raw.get('models') or {}).items() if isinstance(raw, dict) else ():
            clean = dict(kind=entry['kind'], terminals=list(entry['terminals']), roles=list(entry['roles']),
                         parameters=dict(entry.get('parameters') or {}))
            if models.setdefault(name, clean) != clean:
                conflicting.add(name)
    return {name: entry for name, entry in models.items() if name not in conflicting}


def build_mapping(netlist_text, *, circuit_id='native', technology_library=None) -> tuple:
    """(parser configuration, models left unverified) for an exported netlist: the verified models it
    actually uses, then - with `technology_library` loaded as a PDK - the components that PDK describes
    (in the standard list's terms, pdk.parse_models). No parameter groups - which sizes move, and how, is
    decided in the editors."""
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    survey = SpectreParser(ParserConfig(models={})).parse_text(netlist_text, source='<virtuoso-export>', circuit_id=circuit_id)
    used = sorted({device.model_ref for device in survey.devices})
    verified, described, version = verified_models(), {}, 'native-draft-1'
    if technology_library:
        from .pdk import load_record, parse_models
        record = load_record(technology_library)
        if record is not None:
            described = parse_models(record)
            if any(name in described and name not in verified for name in used):
                version = f"native-draft-1+pdk-{record['pdk_id']}-{record['sha256'][:12]}"
    models = {name: verified.get(name) or described[name] for name in used if name in verified or name in described}
    mapping = dict(mapping_version=version, models=models, global_nets=['0'], net_roles={'0': ['ground']}, parameter_groups=[])
    return mapping, [name for name in used if name not in models]


def finish_import(directory, *, library, cell, testbench_cell=None, technology_library=None, profile_id=None) -> dict:
    """Runs in the backend after the reader process wrote the export and the readbacks into `directory`:
    builds the mapping, proves that the export parses, records what was read, then moves the directory
    into place (an earlier import of the same cell is replaced only now)."""
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    directory = Path(directory)
    netlist = directory / FILES['netlist']
    text = netlist.read_text()
    mapping, unverified = build_mapping(text, circuit_id=f'{library}__{cell}', technology_library=technology_library)
    write_json(directory / FILES['mapping'], mapping)
    described = sorted(set(mapping['models']) - set(verified_models()))
    graph = SpectreParser(ParserConfig.from_file(directory / FILES['mapping'])).parse_file(netlist)
    try:
        facts = json.loads((directory / FILES['form_rules']).read_text())
        form_rules = (dict(read=False, reason=facts['error']) if facts.get('error') else
                      dict(read=True, instances=len(facts.get('instances') or {}), modified_after=bool(facts.get('modified_after'))))
    except (OSError, ValueError, KeyError):
        form_rules = None                                  # a reader older than the form rules
    meta = dict(format=FORMAT, library=library, cell=cell, testbench_cell=testbench_cell or None, form_rules=form_rules,
                exported_cell=testbench_cell or cell, technology_library=technology_library, profile_id=profile_id,
                imported_utc=utcnow().isoformat(), netlist_sha256=_sha256(netlist),
                mapping_sha256=_sha256(directory / FILES['mapping']), device_count=len(graph.devices),
                net_count=len(graph.nets), unverified_models=unverified, pdk_described_models=described,
                origin='virtuoso netlist export + schematic readback through the bridge (read-only)')
    write_json(directory / FILES['meta'], meta)
    target = cell_dir(library, cell)
    target.parent.mkdir(parents=True, exist_ok=True)
    retired = target.with_name(f'.{target.name}.replaced-{os.getpid()}')
    if target.exists():
        target.rename(retired)
    directory.rename(target)
    shutil.rmtree(retired, ignore_errors=True)
    return dict(meta, directory=str(target))


def load_import(library, cell) -> dict | None:
    """The stored import of a cell, or None. A directory whose netlist no longer matches its record is
    treated as absent: what is shown must be what Virtuoso exported."""
    try:
        directory = cell_dir(library, cell)
        meta = json.loads((directory / FILES['meta']).read_text())
    except (OSError, ValueError, TypeError):
        return None
    netlist, mapping = directory / FILES['netlist'], directory / FILES['mapping']
    if meta.get('format') != FORMAT or not netlist.is_file() or not mapping.is_file():
        return None
    if _sha256(netlist) != meta.get('netlist_sha256') or _sha256(mapping) != meta.get('mapping_sha256'):
        return None
    return dict(meta, directory=str(directory), netlist_path=str(netlist), mapping_path=str(mapping))


def draft_graph(imported):
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    return SpectreParser(ParserConfig.from_file(imported['mapping_path'])).parse_file(imported['netlist_path'])
