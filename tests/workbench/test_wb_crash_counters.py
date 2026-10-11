"""What a run knows of its own evaluations after a crash (record 7.322): the evaluations committed after the last save
point are in the tables, and the run's failure count and its first passing design are taken from them - not left as
the save point had them. A real worker process on the MOCK backend, killed at a chosen commit."""
from pathlib import Path
import subprocess
import sys

import pytest

from gator_workbench import runs
from gator_workbench.storage.atomic import read_jsonl
from helpers import REPO, make_config, roots_for, rows, run_prepared, summary

pytestmark = pytest.mark.xdist_group('test_wb_crash_counters')

# A worker of its own process that ends by SIGKILL right after its Nth evaluation is committed: no finally, no flush, no
# save point - the crash a frozen machine or a killed process leaves.
CRASH_SCRIPT = '''
import os, signal, sys
sys.path[:0] = [{src!r}, {tests!r}]
import torch; torch.set_num_threads(1)
from gator_workbench.layout import RunLayout
from gator_workbench.storage import dataset
from helpers import run_prepared
commit, committed = dataset.RawDataset.commit, [0]
def commit_then_crash(self, bundle):
    done = commit(self, bundle)
    if (bundle.get('rows') or {{}}).get('evaluations'):
        committed[0] += 1
        if committed[0] == {crash_after}:
            os.kill(os.getpid(), signal.SIGKILL)
    return done
dataset.RawDataset.commit = commit_then_crash
run_prepared(RunLayout({run_dir!r}), scripts={{'0': {script!r}}})
'''


def crashed_run(tmp_path, *, script, crash_after, threshold=0.0, run=None):
    """A run of one lane that saves every 4 evaluations and is killed after `crash_after` committed ones."""
    config = make_config(tmp_path, threshold=threshold, run=dict(dict(max_evaluations=12), **(run or {})),
                         output=dict(checkpoint_every_evaluations=4, flush_every_evaluations=1))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    code = CRASH_SCRIPT.format(src=str(REPO / 'src'), tests=str(Path(__file__).parent), run_dir=str(layout.run_dir),
                               script=script, crash_after=crash_after)
    process = subprocess.run([sys.executable, '-c', code], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
    assert process.returncode == -9, process.stderr.decode()[-2000:]
    assert runs.run_status(layout.run_dir)['state'] == 'interrupted'
    return config, layout


def resume(config, layout, tmp_path, **options):
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))
    return run_prepared(again, **options)


def test_a_success_committed_after_the_save_point_still_ends_the_row_of_failures(tmp_path):
    """Four failures, the save point, one passing design, the crash. The save point's count of four failures in a row
    was restored as it was, so the next single failure read as the fifth and stopped the run; and the run's first
    passing design, found after the save point, was forgotten - its summary said none was found."""
    config, layout = crashed_run(tmp_path, script={1: 'nan', 2: 'nan', 3: 'nan', 4: 'nan'}, crash_after=5)
    before = sorted(rows(layout, 'evaluations'), key=lambda row: row['commit_seq'])
    assert [row['valid'] for row in before] == [False] * 4 + [True] and before[4]['all_hard_constraints_satisfied']
    assert resume(config, layout, tmp_path, scripts={'0': {1: 'nan'}}) == 'completed'       # one failure: not the fifth
    result = summary(layout)
    assert result['stop_reason'] == 'budget_exhausted' and result['error'] is None
    assert result['totals']['candidate_evaluations_charged'] == 12
    first = result['first_feasible']
    assert result['feasibility']['found'] and result['censoring']['status'] == 'observed'
    assert (first['evaluation_id'], first['first_feasible_eval_count'], first['commit_seq']) == (before[4]['evaluation_id'], 5, 5)
    evaluations = sorted(rows(layout, 'evaluations'), key=lambda row: row['commit_seq'])
    assert [row['after_first_feasible'] for row in evaluations[:6]] == [False] * 5 + [True]     # the sixth came after it
    # an episode begun between the save point and the crash keeps its number: no episode after the resume took it again
    episodes = {}
    for row in evaluations:
        episodes.setdefault(row['episode_id'], []).append(row['commit_seq'])
    assert not any(min(seqs) <= 5 < max(seqs) for seqs in episodes.values())
    # the counts of the summary are the table's own, the evaluations between the save point and the crash included
    real = [row for row in evaluations if row['status'] != 'interrupted']
    assert result['feasibility']['valid_evaluations'] == sum(row['valid'] for row in real)
    assert result['feasibility']['feasible_evaluations'] == sum(bool(row['all_hard_constraints_satisfied']) for row in real)
    assert result['totals']['failures'] == sum(not row['valid'] for row in real) == 5
    resumed = next(event for event in read_jsonl(layout.logs / 'events.jsonl') if event['event'] == 'resumed')
    assert resumed['checkpoint_commit_seq'] == 4 and resumed['post_checkpoint_evaluations'] >= 1
    assert resumed['counters_after_checkpoint'] == dict(evaluations=1, consecutive_failures=0, first_feasible=before[4]['evaluation_id'])


def test_failures_committed_after_the_save_point_still_count(tmp_path):
    """The other way round: the save point saw no failure, four failures follow it, the crash. The next failure is the
    fifth in a row and stops the run, as it would have without the crash; before, the count started over at the save
    point's zero and four more failures were needed."""
    config, layout = crashed_run(tmp_path, script={5: 'nan', 6: 'nan', 7: 'nan', 8: 'nan'}, crash_after=8,
                                 threshold=1.5, run=dict(max_evaluations=30))
    # the kill is right after the eighth commit, which is also where a save point is due: the newest one is the fourth's
    assert resume(config, layout, tmp_path, scripts={'0': {1: 'nan'}}) == 'failed'
    result = summary(layout)
    assert result['stop_reason'] == 'consecutive_failures' and '5 consecutive failed evaluations' in result['error']
    assert not result['feasibility']['found']
    real = [row for row in rows(layout, 'evaluations') if row['status'] != 'interrupted']
    assert len(real) == 9 and result['totals']['failures'] == 5


def test_a_run_that_stops_at_its_first_passing_design_stops_when_that_design_came_before_the_crash(tmp_path):
    """With "stop at the first passing design" the run was ending when it was killed: resumed, it ends - it does not go
    on to a second passing design and call that one its first."""
    config, layout = crashed_run(tmp_path, script={1: 'nan', 2: 'nan', 3: 'nan', 4: 'nan'}, crash_after=5,
                                 run=dict(stop_at_first_feasible=True))
    passing = next(row for row in rows(layout, 'evaluations') if row['all_hard_constraints_satisfied'])
    assert resume(config, layout, tmp_path) == 'completed'
    result = summary(layout)
    assert result['stop_reason'] == 'first_feasible' and result['first_feasible']['evaluation_id'] == passing['evaluation_id']
    real = [row for row in rows(layout, 'evaluations') if row['status'] != 'interrupted']
    assert len(real) == 5                                             # nothing was simulated after the resume
