"""The demo PDK of the PDK tests - its fixture folder, model files and a read of them - shared with other test modules (refactoring package D1)."""

from pathlib import Path
import json

from gator_workbench import pdk

from helpers import make_config, SMALL_NET


FIXTURE = Path(__file__).parent / 'fixtures' / 'pdk_demo'


MODEL_FILES = ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')


def raw_material():
    """What the reader process hands the backend (pdk.read_from_virtuoso), built from the fixture files."""
    scans = [pdk.scan_model_text((FIXTURE / 'models' / name).read_text(), f'/pdk/demo045/models/{name}') for name in MODEL_FILES]
    return dict(technology_library='demo045', cdf_text=(FIXTURE / 'cdf.txt').read_text(), scans=scans,
                ideal=dict(library='analogLib', cdf_text=(FIXTURE / 'ideal.txt').read_text()),
                sources=dict(model_files=[dict(path=f'/pdk/demo045/models/{n}', bytes=1, sha256='0' * 64) for n in MODEL_FILES]))


def load_demo():
    """Finish loading the demo PDK from local model and CDF fixtures."""
    return pdk.finish_load(raw_material())


def parser_config(tmp_path, record):
    """The parser configuration of the demo circuit: the PDK's own device mappings plus two analogLib sources, and the
    groups the starter configuration turns into Parameters rows."""
    models = pdk.parse_models(record)
    models['vsource'] = dict(kind='vsource', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'dc': 'dc'})
    models['capacitor'] = dict(kind='capacitor', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'c': 'c'})
    groups = [dict(id='input_w', parameter_kind='w', unit='m', lower=1e-6, upper=10e-6, members=[dict(device_id='XU1/M1', parameter='w')]),
              dict(id='input_nf', parameter_kind='nf', unit='count', lower=1, upper=4, step=1, domain='integer',
                   members=[dict(device_id='XU1/M1', parameter='nf')]),
              dict(id='coil_radius', parameter_kind='rad', unit='m', lower=5e-6, upper=20e-6,
                   members=[dict(device_id='XU1/L1', parameter='rad')])]
    path = tmp_path / 'demo_mapping.json'
    path.write_text(json.dumps(dict(mapping_version='demo045-test', models=models, global_nets=['0'],
                                    net_roles={'0': ['ground']}, parameter_groups=groups)))
    return path


def demo_config(root, vocabulary='pdk:demo045', **kwargs):
    """Build a synthetic demo-PDK configuration with the selected network vocabulary."""
    run = dict(kwargs.pop('run', {}))
    run['network'] = dict(SMALL_NET, vocabulary=vocabulary)
    return make_config(root, 'synthetic:pdk_demo', run=run, **kwargs)
