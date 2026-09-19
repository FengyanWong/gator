"""Offline table integrity tests. Callback values below are synthetic fixtures."""
from copy import deepcopy
from dataclasses import replace
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_bridge_adapter import profile, adapter, changing_writer
from analog_optimizer.backends import virtuoso_bridge as bridge
from analog_optimizer.backends.cdf_table import (CdfTable, CdfTableBackend, build_cdf_table,
                                                render_structure, structures_equal, width_grid,
                                                content_hash)
from analog_optimizer.backends.gpdk045 import GEOMETRY

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prepared(adapter, monkeypatch, tmp_path):
    adapter.circuit.width_bounds = (3.995e-6, 4.005e-6)
    writer, _ = changing_writer(adapter)
    monkeypatch.setattr(bridge, 'set_gpdk_mos', writer)
    source = (ROOT / 'examples/circuits/gpdk045_ota5.scs').read_text()
    def export(lib, cell, output, timeout):
        output.mkdir()
        text = source
        for name in ('M1', 'M2'):
            params = adapter.circuit.instances(adapter.test_state)[name]['params']
            first = text.index('    ' + name + ' (')
            last = text.index('\n    M', first + 1)
            statement = text[first:last]
            # Independent test-only export, deliberately different formatting.
            for key in ('w',) + GEOMETRY:
                statement = re.sub(r'\b' + key + r'=(?:\([^)]*\)|\S+)',
                                   lambda _: key + '=(' + str(params[key]) + ')', statement)
            text = text[:first] + statement + text[last:]
        (output / 'netlist').write_text(text)
        return {'input_file': str(output / 'input.scs')}
    adapter.test_client.schematic.export_netlist = export
    with adapter:
        path = build_cdf_table(adapter, tmp_path / 'table',
                               pdk={'root': '/models', 'sha256': 'offline-fixture', 'files': 1})
        assert adapter.read_parameters() == adapter.circuit.assignments(4e-6)
    return path, adapter


def test_all_rows_match_native_exports_and_include_derived_geometry(prepared):
    path, adapter = prepared
    table = CdfTable(path, adapter.circuit, model_file=adapter.config.model_file)
    assert len(table.data['rows']) == 3
    assert json.loads(path.with_name('preparation.json').read_text())['simulation_calls'] == 0
    for width in width_grid(adapter.circuit):
        row = table.lookup(adapter.circuit.assignments(width))
        text = render_structure(table.template, row['snapshot'], adapter.circuit)
        native = (path.parent / row['native_structure']).read_text()
        assert structures_equal(adapter.circuit, text, native)
        assert not structures_equal(adapter.circuit, text, native.replace('c=1p', 'c=2p'))


@pytest.mark.parametrize('kind', ['hash', 'template', 'missing_row', 'stale_geometry', 'model', 'bounds'])
def test_table_refuses_tamper_and_configuration_drift(prepared, kind):
    path, adapter = prepared
    data = json.loads(path.read_text())
    model = adapter.config.model_file
    if kind == 'template':
        path.with_name('template.scs').write_text('changed')
    elif kind == 'bounds':
        adapter.circuit.width_bounds = (3.99e-6, 4.01e-6)
    elif kind == 'model':
        model = '/models/other.scs'
    else:
        if kind == 'hash':
            data['rows'][0]['width'] = 0
        elif kind == 'missing_row':
            data['rows'].pop()
        else:
            snapshot = data['rows'][0]['snapshot']
            adapter.circuit.instances(snapshot)['M1']['params']['sca'] = '999'
        if kind != 'hash':
            data['sha256'] = content_hash({k: v for k, v in data.items() if k != 'sha256'})
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        CdfTable(path, adapter.circuit, model_file=model)


def test_python_backend_generates_isolated_decks_without_schematic_calls(prepared, tmp_path, monkeypatch):
    import os
    import threading
    from analog_optimizer.backends.virtuoso_bridge import digest
    path, adapter = prepared
    backend = CdfTableBackend(adapter.config, adapter.circuit, path)
    # Offline connection only. Real connect/version/PDK checks are tested in
    # acceptance; this fixture never pretends to execute real Spectre.
    backend._active = True
    backend._thread, backend._pid = threading.get_ident(), os.getpid()
    backend._env_hash = digest(adapter.config.env_file)
    backend._bound_env = backend._vb_env()
    first = backend.generate_netlist(tmp_path / 'exports')
    backend.set_parameters(adapter.circuit.assignments(4.005e-6))
    second = backend.generate_netlist(tmp_path / 'exports')
    assert first.path != second.path and first.sha256 != second.sha256
    assert backend.get_circuit_graph(first).parameter_groups[0].value == pytest.approx(4e-6)
    assert backend.get_circuit_graph(second).parameter_groups[0].value == pytest.approx(4.005e-6)
    with pytest.raises(ValueError):
        backend.set_parameters(adapter.circuit.assignments(4e-6) | {('XU1/M3', 'w'): 8e-6})
    second.path.write_text('modified')
    with pytest.raises(ValueError, match='modified'):
        backend.get_circuit_graph(second)
    backend.restore()
    backend.close()


def test_template_rejects_missing_or_duplicate_fields(profile):
    text = (ROOT / 'examples/circuits/gpdk045_ota5.scs').read_text()
    with pytest.raises(ValueError, match='M1.w'):
        render_structure(text.replace('w=(4u)', 'w=(4u) w=4u'), profile.reference, profile)
    with pytest.raises(ValueError, match='M1.sca'):
        render_structure(text.replace('sca=22.49589', 'other=22.49589'), profile.reference, profile)


def test_failed_native_comparison_restores_and_does_not_publish(prepared, tmp_path, monkeypatch):
    import analog_optimizer.backends.cdf_table as module
    _, adapter = prepared
    monkeypatch.setattr(module, 'structures_equal', lambda *args: False)
    output = tmp_path / 'failed'
    with pytest.raises(ValueError, match='native export'):
        with adapter:
            build_cdf_table(adapter, output, pdk={'root': '/models', 'sha256': 'test', 'files': 1})
    assert not (output / 'table.json').exists()
    assert json.loads((output / 'preparation.json').read_text())['state'] == 'failed'
    assert adapter.circuit.validate_readback(adapter.test_state) == adapter.circuit.assignments(4e-6)


def test_pdk_changed_during_preparation_rejects_publication(prepared, tmp_path):
    _, adapter = prepared
    output = tmp_path / 'changed-pdk'
    with pytest.raises(ValueError, match='PDK files changed'):
        with adapter:
            build_cdf_table(adapter, output, pdk={'root': '/models', 'sha256': 'test', 'files': 1},
                            verify_pdk=lambda: {'root': '/models', 'sha256': 'changed', 'files': 1})
    assert not (output / 'table.json').exists()
    assert adapter.circuit.validate_readback(adapter.test_state) == adapter.circuit.assignments(4e-6)


def test_pdk_digest_detects_content_and_filename_changes_but_ignores_locks(tmp_path):
    import subprocess
    import sys
    from analog_optimizer.backends.cdf_table import _FINGERPRINT_SCRIPT
    pdk = tmp_path / 'pdk'
    pdk.mkdir()
    model = pdk / 'model.scs'
    model.write_text('first')
    def fingerprint():
        result = subprocess.run([sys.executable, '-c', _FINGERPRINT_SCRIPT, str(pdk)],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    first = fingerprint()
    (pdk / 'data.dm.cdslck').write_text('transient')
    assert fingerprint() == first
    model.write_text('second')
    second = fingerprint()
    assert second['sha256'] != first['sha256']
    model.rename(pdk / 'renamed.scs')
    assert fingerprint()['sha256'] != second['sha256']
