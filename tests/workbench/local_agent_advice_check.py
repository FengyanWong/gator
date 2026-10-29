"""Opt-in supplement to local_agent_live_check.py: real local output, synthetic circuit validation.

Run only after the live lifecycle check verified the local weights. No simulation is performed.
"""
import json
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = str(root/'settings')
os.environ['GATOR_WORKBENCH_SYNTHETIC_FIXTURES'] = str(Path(__file__).parent/'fixtures'/'synthetic_fixtures.json')
from helpers import make_config
from gator_workbench import schema, tasks
from gator_workbench.local_agent import proposals
from gator_workbench.local_agent.catalog import CATALOG
from gator_workbench.local_agent.runtime import Runtime, asset_root, compatibility, hardware, prompt_text

model = CATALOG['bolt-74b']
engine = Runtime(asset_root()/'bin'/'llama-completion.exe')
engine.verify()
check = compatibility(model, hardware(root), installed=True, runtime_ready=True)
assert check['compatible'], check['errors']
config = make_config(root/'mock').model_dump(mode='json')
request = ('This is a synthetic software check, not a simulation. Propose only these two editor changes: '
           'reduce input_pair_width upper bound from 10 um to 9 um and set run.seed to 222. '
           'Keep the existing units, tied follower and all other settings unchanged. Explain briefly. '
           'Use the required JSON reply contract.')
prompt = prompt_text(model, [('user', proposals.INSTRUCTIONS + proposals.advisory_context(config)), ('user', request)])
print('Generating real 74B proposal against the synthetic GATOR fixture.', flush=True)
answer = engine.generate(model, asset_root()/'models'/model.filename, prompt, root/'answer', Event(), check['gpu_index'])
result = proposals.decode_reply(answer)
def load(raw):
    parsed = schema.WorkbenchConfig.model_validate(raw)
    return parsed, tasks.load_task(parsed.circuit), None
report = dict(origin='synthetic', provenance='mock', raw_answer=answer, parsed=result, passed=False)
try:
    assert result['proposal'] and not result['proposal_error'], result
    review = proposals.validate_proposal(config, result['proposal'], SimpleNamespace(load_config=load))
    assert len(review['changes']) == 2, review['changes']
    assert review['config']['run']['seed'] == 222
    assert abs(review['config']['parameters'][0]['upper'] - 9e-6) < 1e-12
    assert review['config']['parameters'][1] == config['parameters'][1]
    report.update(passed=True, review=review)
    print('PASS: actual model proposal passes circuit-aware validation; ties and unrelated settings preserved.', flush=True)
finally:
    (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
