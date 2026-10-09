"""The demo PDK of the PDK tests - its fixture folder, model files and a read of them - shared with other test modules (refactoring package D1)."""

from pathlib import Path
from gator_workbench import pdk


FIXTURE = Path(__file__).parent / 'fixtures' / 'pdk_demo'


MODEL_FILES = ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')


def raw_material():
    """What the reader process hands the backend (pdk.read_from_virtuoso), built from the fixture files."""
    scans = [pdk.scan_model_text((FIXTURE / 'models' / name).read_text(), f'/pdk/demo045/models/{name}') for name in MODEL_FILES]
    return dict(technology_library='demo045', cdf_text=(FIXTURE / 'cdf.txt').read_text(), scans=scans,
                ideal=dict(library='analogLib', cdf_text=(FIXTURE / 'ideal.txt').read_text()),
                sources=dict(model_files=[dict(path=f'/pdk/demo045/models/{n}', bytes=1, sha256='0' * 64) for n in MODEL_FILES]))
