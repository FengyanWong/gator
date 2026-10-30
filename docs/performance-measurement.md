# Measuring performance on the shared machine

How to time something in this project so that the numbers mean what they say (record 7.221, item C of
record 7.220's plan, `docs/plan-low-moderate-risk-performance.md`). The machine is shared: other Claude sessions run
test suites, browser checks, MOCK and ngspice studies and real Spectre queues, whose lanes and parsers use this host's
CPU too. On 2026-10-05 a peer's 12-worker test suite pushed the load average to 60-90 and made 1-thread learner timings
about 40 % slower; an overnight Spectre queue kept it at 10-15. A timing taken then measures the neighbours.

## Before a timed measurement

1. Look at the load and what makes it: `uptime` and `ps -eo pcpu,etime,args --sort=-pcpu | head`. Ask busy sessions
   what they run (ListAgents / SendMessage). Never kill, suspend, renice or re-pin other jobs, never change the VM, and
   never lower a run's lanes to make room: that changes its collection order and throughput.
2. Fix the resources and write them down: torch threads, `OMP_NUM_THREADS`, Spectre lanes, test workers, the load
   before and after each timed arm.
3. Time the arms one after another, each on a quiet machine: wait until the 1-minute load average is below a threshold
   (for example 6 on this 24-thread host) before each arm, not just before the first one. Compare arms only when their
   loads were alike; repeat an arm whose load moved.
4. Report the median and a tail (p90) of repeated samples, cold start separately from steady state, with the exact code
   (git revision + optimizer source digest), fixture and dependency versions. Never add up phase shares from different
   runs as if they were one end-to-end gain, and never claim a simulator or learning effect from a microbenchmark.
5. Keep timing out of unit tests: a timing threshold belongs in a benchmark report, not in an assertion that flakes.

## Resource settings that exist

- **Learner threads.** A run's worker trains with ONE torch thread (`gator_workbench/worker.py`, `cli.py`). Measured on
  2026-10-05: 4 threads made a GATv2 (192 wide) update ~20 % faster and did nothing for GT or RGCN; the RTX 4090 with a
  scratch CUDA build of the same torch was 1.6x faster for GATv2 but slower for GT (1.5x) and RGCN (2.7x) - batches of 8
  small graphs are bound by launch and synchronization, not arithmetic. So the learner stays on one CPU thread.
- **Launchers without a thread option** - the `examples/` benchmarks are hash-pinned evidence (the M5/M6 audits and the
  reward-v2 freeze re-hash `examples/*.py`), so they are not edited: run them with `OMP_NUM_THREADS=1` (torch's default
  thread count follows it).
- **Test concurrency.** The full regression is `-n 12 --dist loadgroup` (~1 min on a quiet machine). While another
  session measures or simulates, use `-n 4 --dist loadgroup` (about 1.5-2 min); never start the 12-worker suite beside a
  timed experiment. Browser checks: `bash frontend/scripts/run_checks.sh --lanes 2` instead of the default 4.

## The learner-step timing fixture

`tests/perf/learner_update_profile.py` (not a test; pytest collects only `test_*.py`) times one learner step exactly as
the workbench engine records it (`update_seconds`: sampling plus `learner.update`), once uninstrumented for the totals
and once with the phases wrapped (replay sampling, validation, current and next-state batches, actor samples, target
critics), for the three starting presets (GT 48/4/4, RGCN 32/4, GATv2 192/3/4). It warms the input cache with every
replay observation first, as a live run does, and records threads, `OMP_NUM_THREADS`, CPUs, the load before and after
each arm, the git revision and the optimizer source digest.

```bash
OMP_NUM_THREADS=1 PYTHONPATH=src ~/analog-optimizer-venv/bin/python tests/perf/learner_update_profile.py \
    --wait-load 6 --json /tmp/profile-synthetic.json
OMP_NUM_THREADS=1 PYTHONPATH=src ~/analog-optimizer-venv/bin/python tests/perf/learner_update_profile.py \
    --checkpoint <run>/checkpoints/<save point>/training_state.pt --wait-load 6 --json /tmp/profile-real.json
```

Fixtures: the default synthetic op-amp replay (16 transitions, `origin=synthetic`) and any workbench save point's
`training_state.pt` with its embedded replay. Measure on both: a recorded Spectre transition is about 41 kB pickled, a
synthetic one a few kB, so replay copying and cache keys weigh about four times more on real data (record 7.221 found
the replay copy at 8-9 ms on the synthetic fixture and 27-30 ms on the recorded `mscr_ota7t` runs). The `--checkpoint`
file is a trusted local save point (it is unpickled); the script writes nothing into the run.
