"""Pure launch-journal arithmetic; these dictionaries are not simulator results."""
import importlib.util
from pathlib import Path


def test_unresolved_intent_is_not_a_confirmed_call():
    path = Path(__file__).resolve().parents[1] / 'examples/qualify_reward_v2_real.py'
    spec = importlib.util.spec_from_file_location('reward_v2_qualification', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.call_counts([]) == dict(started_calls=0, completed_calls=0, uncertain_calls=0)
    assert module.call_counts([dict(confirmed_calls=None)]) == dict(
        started_calls=1, completed_calls=0, uncertain_calls=1)
    assert module.call_counts([dict(confirmed_calls=1), dict(confirmed_calls=None)]) == dict(
        started_calls=2, completed_calls=1, uncertain_calls=1)
