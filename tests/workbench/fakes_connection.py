"""Fake connection layers, probes and bridges that several test modules share (refactoring package D1)."""

import sys
from pathlib import Path
import shutil

from gator_workbench.connection import ConnectionMonitor, LAYERS, NGSPICE_LAYERS
from gator_workbench import connection
from gator_workbench.storage.atomic import write_json


LICENSE_OK = ['Users of Virtuoso_Multi_mode_Simulation:  (Total of 10 licenses issued;  Total of 3 licenses in use)']


class FakeBridge:
    """Configurable stand-in for the bridge facade. It has NO start/stop/restart method at all."""
    def __init__(self, settings=None, **behaviour):
        self.b = dict(version='0.8.0', resolved='__same__', roles=dict(daemon_host='eda-host', spectre_host='eda-host',
                                                                       remote_user='alice'),
                      local=False, state=dict(port=65432), running=True, skill=(True, []), client_error=None,
                      user=dict(ok=True, skipped=False, error=''), windows=None, license=dict(
                          spectre_path='/cad/spectre', version='@(#)$CDS: spectre 23.1', licenses=LICENSE_OK))
        self.b.update(behaviour)
        self.calls = []

    def __call__(self, settings):                  # used as the factory
        if self.b.get('import_error'):
            raise ModuleNotFoundError("No module named 'virtuoso_bridge'")
        return self

    def version(self):
        self.calls.append('version'); return self.b['version']

    def bind_env(self, env_file):
        self.calls.append('bind_env')

    def resolve_profile(self, explicit):
        return explicit if self.b['resolved'] == '__same__' else self.b['resolved']

    def roles(self, profile):
        return dict(self.b['roles'])

    def is_local(self, host):
        return self.b['local']

    def tunnel_state(self, profile):
        self.calls.append('tunnel_state'); return self.b['state'], self.b['running']

    def client(self, profile, timeout):
        self.calls.append('client')
        if self.b['client_error']:
            raise self.b['client_error']
        return self

    def skill_ok(self, client, timeout):
        self.calls.append('skill'); return self.b['skill']

    def daemon_user(self, client, profile, timeout):
        return dict(self.b['user'])

    def readiness(self, client):
        self.calls.append('readiness')
        if self.b['windows']:
            raise RuntimeError('Active ADE/Maestro window conflicts with OCEAN export: ' + '; '.join(self.b['windows']))

    def license(self, profile):
        self.calls.append('license'); return dict(self.b['license'])

    def close(self):
        self.calls.append('close')


def states(layers):
    return {item['layer']: item['state'] for item in layers}


def reasons(layers):
    return {item['layer']: item['reason_code'] for item in layers if item['reason_code']}


# ------------------------------------------------------------------------------- monitor (probe process)
def fake_probe(tmp_path, body):
    script = tmp_path / 'fake_probe.py'
    script.write_text('import sys, json, time, os\n' + body)
    return [sys.executable, str(script)]


def layers_json(**overrides):
    return [dict(layer=n, state=overrides.get(n, 'ok'), reason_code=None, diagnostic=None, details={}) for n in LAYERS]


def monitor_for(tmp_path, body, **kwargs):
    return ConnectionMonitor(probe_command=fake_probe(tmp_path, body), **kwargs)


OK_BODY = f'print(json.dumps(dict(layers={layers_json()!r})))'


REPO = Path(__file__).resolve().parents[2]


EXAMPLE = REPO / 'examples/circuits/ngspice_ota5_level1.cir'


NGSPICE = shutil.which('ngspice')


def ngspice_probe(tmp_path, **states):
    """A probe process that answers the four ngspice layers (ok unless stated)."""
    layers = [dict(layer=n, state=states.get(n, 'ok'), reason_code=None, diagnostic=None, details={}) for n in NGSPICE_LAYERS]
    script = tmp_path / 'probe.py'
    script.write_text(f'import json\nprint(json.dumps(dict(layers={layers!r})))\n')
    return ConnectionMonitor(probe_command=[sys.executable, str(script)])


def write_profiles(**profiles):
    write_json(connection.connection_file(), dict(active=next(iter(profiles)), profiles=profiles))


SETUP = '/tmp/virtuoso_bridge_alice/38094/virtuoso_bridge/virtuoso_setup.il'


class FakeTunnel(FakeBridge):
    """The check's fake plus the one starting call. It has NO stop/restart method at all."""
    def __init__(self, **behaviour):
        super().__init__(**dict(dict(start_error=None, comes_up=True, state=dict(port=65432, setup_path=SETUP)), **behaviour))

    def start_tunnel(self, profile):
        self.calls.append('start_tunnel')
        if self.b['start_error']:
            raise self.b['start_error']
        self.b['running'] = self.b['comes_up']
