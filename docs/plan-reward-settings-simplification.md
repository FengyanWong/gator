# Plan: fewer reward settings, same reward (2026-10-03)

A plan, nothing built. Written in the session "RL reward design" after the user asked why the reward needs two
"shape" settings and what a simpler set would still support. The reward arithmetic itself (reward v2.1,
`src/analog_optimizer/measurements/specs.py`, [reward-v2.md](reward-v2.md)) does not change: this is a workbench
change, no optimizer digest moves, and every saved configuration, task file and model keeps its hashes and its
behaviour. The settings page is [GATOR Reward Design](https://claude.ai/artifact/QjBEqoUNpBYfhKcGqSyaFN).

## 1. Today

Run settings, "Reward and training conditions" block of the RL panel (`RewardConfig`, `ConditionsConfig`):

| Setting | Values | Schema default | New page | Used by |
|---|---|---|---|---|
| Violation shape | capped, compressed | capped | compressed | every run |
| Worst hard-spec share | 0–1 | 0 | 0.5 | every run |
| Objective bonus weight | 0–1 | 0 | 0 | runs with an objective row |
| Objective shape | clipped, compressed | clipped | clipped | only when the weight is above 0 |
| Tightest-margin bonus weight | 0–1 | 0 | 0 | never so far |
| Nominal gate band | 0–1 | 0.5 | 0.5 | only with "corners after nominal passes" |
| Corner policy + corners | nominal only, every planned corner, corners after nominal passes | nominal only | nominal only | no task has corner decks since record 7.128 |

Per Specs row (`PerformanceTarget`): limits and tolerance, Scale, Hard, After feasible (objective), Judged at
(shown only with corners), and under "More columns": Weight, Active, Basis, Missing value = failed, Margin sides.

What is wrong with it: two settings do the same job on opposite sides of a limit (violation shape and objective shape),
two have never been exercised (margin weight, gate band), and the one per-row value that matters most, the Scale, is
allowed to stay empty, which makes a 6 % miss on the 5T OTA cost 0.011 of reward.

## 2. Target

### Run settings: two visible, three fixed, two advanced

| Setting | After the change | Why |
|---|---|---|
| Worst hard-spec share | visible, 0–1, new page 0.5 | the one lever that changes how many specs can be traded against each other |
| Objective bonus weight | visible, 0–1, new page 0 | the one lever for "keep improving after feasible"; the Specs row names the objective |
| Objective shape | control removed; new configurations use compressed | clipped only ever stopped the bonus after one scale; no recorded run used it |
| Nominal gate band | control removed; stays 0.5 | nobody has tuned it; its meaning is "pass nominal first", not a number to adjust |
| Corner policy | unchanged, shown only when the task has corner decks | no task has them today |
| Violation shape | moved to "Advanced", new page compressed | kept only to reproduce or continue runs made with capped |
| Tightest-margin bonus weight | moved to "Advanced", 0 | a tie-breaker among feasible designs, never studied; stays available |

The schema keeps every field with its current default, so `_hashed` is untouched: a configuration saved today hashes
the same tomorrow, and an old model's reward contract still matches its run. Only `frontend/src/store.ts`'s starting
values change (`objective_shape: 'compressed'` joins `violation_shape: 'compressed'` and `worst_spec_share: 0.5`).

### Per Specs row: the Scale is never empty

| Setting | After the change | Why |
|---|---|---|
| Scale | always filled: 3 dB for dB rows, 10° for phase, the tolerance for a target, half the width for an interval, 10 % of the limit for every other `>=` / `<=` row; a "Fill empty scales" button on the Specs tab for saved tasks | an empty scale falls back to the size of the limit, which hides every near-miss |
| Hard, After feasible, limits | unchanged | |
| Weight, Active, Missing value = failed, Margin sides | stay under "More columns" | already hidden by default |
| Judged at | shown only with corners (unchanged) | |

The backend fallback for a row saved with an empty scale (the size of the limit) stays as it is, so old task files keep
their hashes. Filling a scale is an edit of the task: a new revision, a new task hash, and a reference baseline recorded
before it no longer matches. That is why this plan goes before the first baselines (plan stage M2 of
[the MScR comparison](https://claude.ai/artifact/BmzGsJunusMSYqpMfyzk9o)).

## 3. Steps

| Step | What | Where | Check |
|---|---|---|---|
| S1 | Remove the Objective shape and Nominal gate band controls; put Violation shape and Tightest-margin weight into a collapsed "Advanced" group; add `objective_shape: 'compressed'` to the new-page start | `frontend/src/panels/Right.tsx`, `frontend/src/store.ts` | `tsc`; `reward_v21_check.mjs` and its fixture updated; the saved-model table still shows the loaded model's shapes |
| S2 | Scale suggestion for every row kind (the 10 % rule for plain `>=` / `<=` rows); "Fill empty scales" writes the suggestion into every empty row of the loaded task, then the usual Save task | `frontend/src/panels/Editors.tsx`, one route or none (the fill is a page edit) | the old-configuration hash fixture is unchanged (`test_wb_spec_equations.py`); a browser check fills a task with mixed rows |
| S3 | The agent's "Review settings" and the readiness brief describe the reduced set | `src/gator_workbench/agents/run_readiness.md`, `settings_review.py` | the settings-review test lists the removed names as absent |
| S4 | Docs: `workbench.md` reward section, `reward-v2.md` note, `decisions.md` entry; record entry + index row | docs | — |
| S5 | Tests: `test_wb_reward_v21.py`, `test_wb_reward_v2_mock.py` and `tests/test_reward_v21_properties.py` keep testing both objective shapes at the schema level (the arithmetic stays); page tests drop the control | tests | full suite green on a clean copy |
| S6 | Land hunk-exact from a private index when no other session is committing; frontend rebuilt and 8765 restarted on the user's word | — | the live page shows the new block |

No optimizer file is touched. Effort: a day, one session. Nothing paid, no simulator call.

## 4. What the simplified reward still carries

The information that reaches the learner, and which setting controls it afterwards:

| Level | Information in the reward | Controlled by | Default |
|---|---|---|---|
| Per spec | how far a measured value sits outside its limit, in units of the row's Scale | Scale (per row) | the suggestion, never empty |
| Per spec | whether the miss is penalised linearly to a cap or compressed | Violation shape (advanced) | compressed |
| Per spec | whether the row decides feasibility or only moves the reward | Hard (per row) | hard |
| Per spec | how much the row counts in the average | Weight (More columns) | 1 |
| Per spec | a finished simulation without this value counts as a miss, not as a fault | Missing value = failed (More columns) | off |
| Per condition | each spec keeps its worst violation over the planned conditions | Corner policy (only with corner decks) | nominal only |
| Whole design | the weighted average of the misses, blended with the single worst hard spec | Worst hard-spec share | 0.5 |
| Whole design | feasible = every hard row met at every planned condition; decided separately from the reward | Hard rows | — |
| Whole design | nominal-passing designs rank above nominal-failing ones when corners run after nominal | fixed band 0.5 | — |
| Feasible designs | improvement of the one objective row past its limit, compressed, times the weight | Objective weight + the row's After feasible | 0 |
| Feasible designs | clearance on the tightest hard spec, times the weight | Margin weight (advanced) | 0 |
| Failures | a design that cannot be simulated scores 1 on every hard spec and the episode continues | — | — |
| Failures | a simulator or measurement fault gives no reward and is not learned from | — | — |

What it gives up, deliberately: a bonus that stops after one scale (clipped), a tunable gate band, and the margin bonus
as a front-page setting. What it never carried and still does not: Monte Carlo or yield, corner-specific limits (the
old D7 question), and the operating points, which feed the network's inputs rather than the reward.

## 5. Decisions for the user

1. Violation shape: "Advanced" (recommended) or keep it on the front of the block.
2. Tightest-margin weight: "Advanced" (recommended) or remove the control until a study shows it helps.
3. The 10 % rule for plain `>=` / `<=` rows in units other than dB and degrees: accept, or name other values.
4. "Fill empty scales" as a button (recommended) or by hand on the seven MScR tasks.
5. Do it before the M2 baselines (recommended), since filled scales change each task's hash.

The SKY130 benchmark stays parked as decided: zero passes in its calibration, mostly from the 1 µs settling target and
the fixed low bias currents; its open choice (let SAC vary the bias current and recalibrate, or compare on the MScR
circuits only) is unchanged by this plan.
