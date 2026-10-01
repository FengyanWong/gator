"""A circuit measured inside the Virtuoso session (OCEAN) keeps Spectre's own binary results, so the bridge skips parsing
text it would never read (user decision of 2026-09-30); every other circuit still asks for PSF text, which it reads."""
import sys
from types import ModuleType, SimpleNamespace

from analog_optimizer.backends import virtuoso_bridge
from analog_optimizer.recording.remote import BridgeScratch


def test_only_a_circuit_measured_in_virtuoso_gives_up_the_text_format():
    raw_format = virtuoso_bridge.VirtuosoBridgeBackend._raw_format
    assert raw_format(SimpleNamespace(circuit=SimpleNamespace())) == 'psfascii'
    assert raw_format(SimpleNamespace(circuit=SimpleNamespace(measures_in_virtuoso=True))) is None


def test_both_simulator_paths_pass_the_format_on(monkeypatch, tmp_path):
    made = []

    class Simulator:
        def __init__(self, **options):
            made.append(options)

        @classmethod
        def from_env(cls, **options):
            return cls(**options)
    runner = ModuleType('virtuoso_bridge.spectre.runner')
    runner.SpectreSimulator = Simulator
    for name in ('virtuoso_bridge', 'virtuoso_bridge.spectre'):
        monkeypatch.setitem(sys.modules, name, sys.modules.get(name) or ModuleType(name))
    monkeypatch.setitem(sys.modules, 'virtuoso_bridge.spectre.runner', runner)
    scratch = BridgeScratch.__new__(BridgeScratch)
    scratch.remote, scratch.profile, scratch.workspace = False, 'fixture', None
    scratch.simulator(tmp_path, 30)
    scratch.simulator(tmp_path, 30, output_format=None)
    backend = virtuoso_bridge.VirtuosoBridgeBackend.__new__(virtuoso_bridge.VirtuosoBridgeBackend)
    backend.config, backend.circuit = SimpleNamespace(profile='fixture'), SimpleNamespace(measures_in_virtuoso=True)
    backend._new_simulator(tmp_path, 30)
    assert [m['output_format'] for m in made] == ['psfascii', None, None]
