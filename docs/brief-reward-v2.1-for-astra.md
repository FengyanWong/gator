# Brief for Astra: reward improvements after the 2026-09-29 review (reward v2.1)

Written 2026-09-29 for Astra (Codex, `gpt-6-astra`) by the Claude Code session "Analog design bench review and reward
improvements", on the user's request "write an overall plan for the reward improvements based on the information for
astra to fix". It turns two reviews of that day into work: the reward review (section 1; every number comes from
recorded runs, no new simulation) and the Analog Design Bench review (Claude session "Chat analog design bench review").
It builds on what reward v2 built: [reward-v2.md](reward-v2.md), [plan-reward-v2-real-flow.md](plan-reward-v2-real-flow.md),
the audit fixes of records 7.97 / 7.98, commit `1135b8b`. Reasoning that still holds is in
[plan-robust-reward-and-network.md](plan-robust-reward-and-network.md) sections 2.3, 2.4 and 2.9. Where this brief and
that plan differ, this brief wins.

## 0. Launch prompt (paste into Astra)

```
Read /mnt/d/gator/docs/brief-reward-v2.1-for-astra.md and carry it out in the order of its section 7.
You may edit src/analog_optimizer/ for exactly the package items of section 4 (one digest step).
Before each step, ask the user the section 8 decisions that step needs.
No Spectre / Virtuoso / bridge call until the user approves the ceiling of section 7 step 6 in words.
No commit, no push, no live frontend build, no backend on 8765. Stop and ask when a requirement cannot be met as written.
Report as section 10 says.
```

## 1. What is wrong today (evidence)

The reward is the number the network tries to raise. Nine problems, most harmful first. The scripts and their outputs
are in `artifacts/local/reviews/reward-review-2026-09-29/` (read-only; they simulate nothing).

**F1 The reward is too small to steer SAC.** SAC chooses designs roughly in proportion to exp(Q/α). Its exploration
bonus, α·(−log π), is about 0.26 per step, far larger than the reward differences between designs, so the policy stays
close to random.
* M6 pilot, 2,808 real designs: best minus worst reward per circuit class 0.023 (OTA), 0.078 (LDO), 0.102 (VCO).
  At α = 0.2 the best design is only e^(0.023/0.2) ≈ 1.1× (OTA) to e^(0.10/0.2) ≈ 1.7× (VCO) as likely as the worst.
* 2,322 recorded SAC updates: median mean log π −1.29; α stayed between 0.1987 and 0.1999 for the whole pilot.
  The temperature uses the actor's Adam rate (`training/sac.py:92`, 3e-4 per update on log α), so a 10× change
  needs at least ≈7,700 updates, far more than any GATOR run gives it.
* Recomputed with the shape reward v2 already offers (compressed ramp, worst-spec share 0.5): 0.049 (OTA),
  0.217 (LDO), 0.408 (VCO). The shape helps the LDO and VCO; the OTA stays far below the bonus. Both halves need fixing:
  the shape (B7) and the temperature (A6).

**F2 Beyond one scale a spec gives no direction** (capped ramp, `measurements/specs.py:213`). In the M6 VCO test fold,
206 of 540 VCO designs (38 %) missed the frequency by more than one scale, and all 206 scored exactly −1/11 = −0.0909:
the reward could not tell a near miss from a far one. The `compressed` shape fixes this, but is off by default.

**F3 A design that stops working is thrown away, not penalized.** When Spectre finishes and the analyzer runs but a
required value is missing (for example, no unity-gain crossing), the adapter reports `measurement_error` with
`candidate_evaluated=True` (`backends/virtuoso_bridge.py:444-458`). The environment then stops the candidate
(`envs/sizing.py:444-449`) and truncates it with no reward and no replay (`sizing.py:479-482`). At a corner, one broken
condition drops the whole candidate. OTA7's spec "exactly one unity crossing" can never produce a violation: UGB and
phase margin exist only when there is exactly one crossing (`measurements/ac.py:43-44`), so a missing value discards the
row before that spec is scored. The network never learns where the circuit breaks. M6 never showed this (all 2,808
designs were `ok`); wide parameter ranges and corners will.

**F4 Crashing the simulator can become the best move.** Under `condition_policy='off'` (the default), an attributed
failure (`invalid_design` / `nonconverged`) scores −1 and ENDS the episode (`sizing.py:477-478`). The ngspice lane
already emits attributed `nonconverged` (`gator_workbench/ngspice_backend.py:280`). With the compressed shape and share
0.5, ordinary steps score about −0.3 to −0.6 (reward-v2 stage B: −0.58), so "−1 and stop" beats three more steps
(−0.9 to −1.8). At today's tiny rewards the trap is harmless; it goes live as soon as F1/F2 are fixed. So A2 must land
before or with B7.

**F5 Corners are simulated for every design, including designs that already failed nominal.** `always` costs 1 + K
launches per step. Reward-v2 stage B (OTA7, 4 corners): a design took 9.7 s and 5 launches against 3.5 s and 1 launch
at nominal only (each corner job ≈1.4 s; the nominal step also writes the sizes and exports). 7 of the 8 five-condition
steps failed nominal, so 28 of 32 corner launches bought nothing. Skip-on-fail (plan 2.3) was deferred.

**F6 The corner targets used so far are probably unreachable.** The OTA7 reference (stage A) has a nominal phase margin
of 27.2° (target ≥ 30°). At ss_hot_low it measures gain 49.5 dB (≥ 53.3), UGB 2.25 MHz (≥ 3.24 MHz) and phase margin
20.2° (≥ 30°); at fs_nominal its power is 4.38 µW (≤ 3.24 µW). The search space was two width groups at ±10 %. No
robust-feasible design was ever seen, so the bonus path never ran. Analog Design Bench ships every task with a
reference circuit that passes every check.

**F7 The bonus terms have flaws** (both were 0 in every real run so far):
* (a) The margin counts a lower limit of 0. OTA7's power is the window [0, 3.24 µW], so the clearance bonus prefers
  about 1.6 µW to a lower-power design, and so does the Corner check's "safest first" ranking (`specs.py:30-37`,
  `gator_workbench/corner_check.py:186-189`).
* (b) The objective term is clipped at one scale (`specs.py:260`): a power objective stops paying below
  (limit − scale). This is the same flatness F2 fixed for violations.
* (c) Clearance uses only the single tightest spec (a hard minimum that jumps between specs).

**F8 New tasks get weak default scales.** An empty scale is the size of the threshold
(`gator_workbench/compile.py:42-47`):
* gain ≥ 60 dB: a 6 dB miss costs 0.1;
* phase margin ≥ 60°: a 15° miss costs 0.25;
* a target of 1 GHz ± 10 MHz: a 100 MHz miss costs about 0.1.

**F9 Every corner-training experiment costs Spectre runs.** Corner plans are real-only (`sizing.py:163-164`,
deliberate: the user rejected fictional MOCK evidence on 2026-09-26). The ngspice backend runs only its own nominal
condition (`ngspice_backend.py:175-177`).

**What Analog Design Bench adds** (its verifiers, read 2026-09-29):
* **Gates, cheapest first.** In its op-amp task: nominal functional checks, then the rest of nominal, then the full
  27-point PVT grid, then CMRR/PSRR at three stress points. A failed gate blocks the later ones.
* **Pass rules.** The worst value over the grid decides. A missing or non-converged value never passes.
* **Monte Carlo** uses fixed seeds and one of three rules: yield ≥ 90 %, mean ± 3σ, or every sample passes.
* **Scoring.** Its score (the fraction of gates passed) is only for diagnosis; a pass needs every gate.

GATOR differs at F3 (missing values), F5 (no gating) and F6 (no reference that passes).

## 2. Decision of record and permissions

* **Package edits.** Requested by the user on 2026-09-29. The launch prompt grants package edits for section 4 only.
  * All package items land in ONE digest step. Record the old and new digest in `docs/decisions.md`.
  * The digest on 2026-09-29 is `f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a` (unchanged since
    `1135b8b`). Check it before the first edit.
* **Defaults stay bit-identical.** Every new setting defaults to today's behaviour and is hashed as absent at its default
  (the rule reward v2 used). Saved configurations keep their hashes, and the M6 identity gate still passes.
  * The one intended change is A2 (decision D1): attributed failures no longer end the episode. No recorded reward
    changes.
* **No simulation in steps 1-5.**
  * Step 6 is a small real check whose ceiling the user approves in words.
  * Mechanism checks run on scripted fake backends labelled `real` (the pattern of the 7.97 audit and
    `tests/test_native_preparation.py`) and are never presented as circuit evidence.
  * MOCK stays nominal-only.
* **Monte Carlo is not in this brief.** It is planned in
  [plan-finalist-monte-carlo.md](plan-finalist-monte-carlo.md) (Claude session "Chat analog design bench review",
  2026-09-29, untracked, nothing built): a finalist check after the run. It has one setting block of its own,
  `run.after_run`, hashed as absent at its defaults, and touches neither `ConditionsConfig` nor `RewardConfig`.
  * Leave the four reserved Monte Carlo input columns as they are.
  * Section 9 lists the reward rule Monte Carlo must follow if it ever enters training.

## 3. Read first; ground rules

Read, in this order:
* `CLAUDE.md`.
* The record index `docs/frontend_implementation_status.md` (its reading guide and commit table).
* The last four entries of `docs/decisions.md`.
* `docs/reward-v2.md` and `docs/plan-reward-v2-real-flow.md`.
* Plan sections 2.3, 2.4 and 2.9.
* Entries 7.94-7.98 in `docs/workbench-log/7.81-and-later.md`.
* `docs/workbench.md`, section "Corner check".

Rules. They are all in `CLAUDE.md` or the reward-v2 audit, repeated because they are easy to break from the package side:

1. **Shared working tree and git index.**
   * Stage explicit paths only. Never `git add -A`, reset, stash, amend or force-push.
   * Commit only when the user says so; then the package (A) and the workbench (B) as separate commits.
   * Re-read a shared file right before each edit. Other sessions are active: on 2026-09-29 the Analog Design Bench
     session added "Matched devices..." (record 7.103: `structures.py`, route `/api/parameters/matched`,
     `MatchedDevices.tsx`, `Editors.tsx`, `api.ts`, `styles.css`), and its plan puts a Monte Carlo box into
     `frontend/src/panels/Right.tsx`.
2. **Hash-pinned evidence.**
   * Never edit, reformat, rename or move `configs/*.json`, the pinned `examples/*.py` or
     `tests/fixtures/synthetic/*.scs`. New files beside them are fine.
   * The frozen OTA7 targets stay exactly as they are: F7a is fixed by a new field, not by editing them.
3. **Environment.**
   * Use `~/analog-optimizer-venv`.
   * Full suite: `OMP_NUM_THREADS=1 ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist load`, with a scratch
     `GATOR_WORKBENCH_SETTINGS_DIR`.
   * The evidence-dependent tests read `artifacts/`, so run them on the real tree.
4. **The user's backend on 8765 and `frontend/dist` are theirs.** Use a scratch port and scratch settings for live
   checks, run `npx tsc --noEmit`, and never run `npm run build`.
5. **Slow disk.** `/mnt/d` is a 9p mount: never walk `artifacts/`; read only the folders named here.
6. **Run the repository's FULL suite, not a selection.** The 7.97 audit found 130 failures that a 70-test selection had
   missed.
7. **Docs.** English, plain language first, limits stated bluntly, no claim the data does not support.

## 4. Package requirements (commit A, one digest step)

### A1 A missing value can count as a failure, opt-in per spec (fixes F3)

* **New field.** `MetricSpec` gains `missing_is_failure: bool = False`.
* **Evaluator.** A condition row with `candidate_evaluated=True` and status `ok` or `measurement_error` becomes
  scorable when every active required spec whose value is missing, non-finite or invalid in that row has
  `missing_is_failure=True`.
  * Those specs get violation 1.0 at that condition, the attributed maximum, under both shapes.
  * Every other spec uses its measured value.
  * A unit mismatch stays an error: it is a configuration fault, never the design's.
  * Any other missing required value keeps today's rule: the row is unavailable.
* **Environment.**
  * The stop rule (`sizing.py:444-449`) uses the same test, so a scorable row does not stop the candidate. The
    evaluation gets a reward, enters replay, and the episode continues.
  * The row keeps its honest status `measurement_error`. Record the reason `missing_counted_as_failure` and the metric
    ids per condition.
* **Unchanged.** These still truncate as today: infrastructure failures (the analyzer raised, so
  `candidate_evaluated=False`), timeouts, transport, licence and backend errors, and uncertain launches.
* **Why opt-in.** A missing UGB can also mean the AC sweep ends too early, which is a testbench limit. The user declares
  whose absence is the design's fault. Analog Design Bench applies the same rule to every value ("an absent value never
  passes").
* **Workbench side (no digest).** Check what the ngspice adapter reports as `candidate_evaluated` when ngspice ran but
  a `.meas` failed (`ngspice_backend.py:284-289`). A1 applies only when it is True.

### A2 Attributed failures never end the episode (fixes F4; decision D1)

* **The rule.** For `invalid_design` / `nonconverged` with `candidate_evaluated=True`:
  * The reward is the evaluator's. Today's numbers are kept: every required spec at that condition scores 1, which
    gives −1 when nothing was measured.
  * `terminated=False` in every policy. The observation carries the status and the step enters replay.
* **Recorded as** `failure_policy='continue_attributed'` in the environment config, for every policy.
* **Effect.** No recorded reward changes: M6 and reward v2 contain no attributed failure. Only whether the episode
  continues changes.

### A3 Condition policy `after_nominal`, with a nominal gate band (fixes F5 without rewarding a nominal fail)

* **New policy.** `condition_policy ∈ {'off', 'always', 'after_nominal'}`. Like `always`, `after_nominal` needs a real
  corner plan.
* **Execution.**
  * Nominal runs first. The corners run only when the nominal row meets every active hard spec: the evaluator's
    `nominal_success`, with A1's scoring.
  * Otherwise stop with reason `nominal_gate_not_met`. This is not a failure: the evaluation is scored.
  * Resets stay nominal-only.
  * A corner infrastructure failure after the gate truncates, as today.
* **Budget.** Reserve 1 + K launches per step before preparation (today's rule), and charge only the launches that
  happened. Check both the single-lane runner (`training/runner.py`) and the parallel coordinator
  (`training/parallel.py`).
* **Reward.** Let f be today's penalty (minus the reward before bonuses, in [0, 1]) and b be
  `RewardSettings.nominal_gate_band` (default 0.5, used only by `after_nominal`):
  * gate not met: R = −b − (1 − b)·f_nominal, in [−1, −b);
  * gate met, every corner evaluated: R = −b·f_worst, plus the bonuses on success, in [−b, 0].
* **Why the band (the guard).** Every gate-met evaluation now scores above every gate-not-met one. Without it, a
  design that barely fails nominal, and is never corner-tested, outscores a design that passes nominal and fails a
  corner. The network would learn to fail nominal on purpose.
* **Network input: nothing new.** The v2 coverage columns already show which planned conditions were evaluated.

### A4 Objective shape (fixes F7b)

`RewardSettings.objective_shape ∈ {'clipped' (default, today), 'compressed'}`.
* Compressed uses t/(1+t), with t ≥ 0 and no clip.
* It keeps today's least improvement over the applicable conditions.

### A5 Margin sides (fixes F7a)

`MetricSpec.margin_sides ∈ {'both' (default), 'lower', 'upper'}`. `spec_margin` ignores the excluded side.
* It applies everywhere that function is used: the evaluator's margins, the clearance bonus and the Corner check.
* Violations and feasibility are unaffected.

### A6 Temperature learning rate (fixes the α half of F1; decision D4)

`SACConfig.alpha_learning_rate: float | None = None`, where None means `learning_rate`, as today.
* A separate Adam rate for log α lets the temperature reach its entropy target within a GATOR-sized run. This is SAC's
  usual answer to reward scale.
* Record it in the checkpoint contract.

### A7 Recording, replay and contracts

* **Every new setting travels with:** the observation (spec dicts, reward settings, condition policy), the environment
  config, the transition and the checkpoint contract.
* **Replay admission** recomputes rewards with the new settings, at today's tolerance. That includes gate bands and
  rows where a missing value counts as a failure.
* **Resume and loading.** Exact resume across the digest step is refused, as today; `fine_tune` and `frozen` load as
  today.

### A8 Package tests

* **New tests.** Property tests for A1-A6 (gate G5) and scripted-backend episode tests (G6), in new test files.
* **Existing tests.** Change `tests/test_reward_v2*.py` only where a test states today's behaviour that A2 changes, and
  name each one in the report.

## 5. Workbench requirements (commit B, no digest change)

* **B1 Settings.**
  * Specs row: `missing_is_failure` (shown as "Missing value = failed") and `margin_sides` ("Margin sides").
  * `RewardConfig`: `nominal_gate_band` and `objective_shape`.
  * `ConditionsConfig.policy`: `after_nominal`.
  * `AdvancedRL`: `alpha_learning_rate` (empty = same as the learning rate).
  * Each is hashed as absent at its default, with plain-language validation; `compile.py` passes them on.
* **B2 Run configuration.**
  * "Training conditions" offers "Nominal only", "Corners after nominal passes" and "Every planned corner".
  * The launches line says "1 per design that fails nominal, 1 + K per design that passes".
  * Keep the OTA7-only limit, but read it from a capability the backend reports for the task, not the hard-coded id
    (`frontend/src/panels/Right.tsx:142`).
  * The Monte Carlo plan puts its box (`run.after_run`) under "Training conditions" in the same "Reward
    and conditions" section, and already names `after_nominal`. Whoever builds second re-reads the file and keeps both.
* **B3 Specs tab.**
  * The two new columns go under "More columns".
  * When an interval's lower limit is 0, show one hint line: "The margin also measures the distance to 0. If 0 is only
    a physical floor, choose Margin sides: upper."
* **B4 Scale suggestion (decision D5).** When a Specs row is created, or its unit or limits change, and its scale is
  empty, the editor proposes an explicit, editable scale:

  | Kind of spec | Suggested scale |
  |---|---|
  | unit dB | 3 dB |
  | unit deg | 10° |
  | target ± tolerance | the tolerance |
  | interval | half the window width |
  | anything else | today's rule (the size of the threshold) |

  Rows already saved with an empty scale keep today's rule, so neither their hash nor their behaviour changes.
* **B5 Steering check.**
  * Show in the run status, the Data tab and the reward-review digest (`agents/run_digest.py`):
    * the reward spread: p90 − p10 over the last 50 scored designs;
    * the exploration bonus: α × (− mean log π) of the latest update.
  * When the spread is below the bonus, add the plain verdict: "The network is still choosing close to random: the
    reward differences are smaller than its exploration bonus."
  * It is computed from existing tables; nothing new is recorded.
* **B6 Reachability warning.**
  * With corners on, the start checklist (`agents/readiness.py` / validation) warns when no recorded design of the task
    meets every hard spec at every planned condition. It names the worst misses of the best recorded design (for
    example "The reference misses gain at ss_hot_low by 3.8 dB…") and points to the Corner check.
  * The Corner check must accept the task's reference design even when that design fails nominal.
  * It warns; it does not block.
* **B7 Starting values (decision D3).** Only after A2 has landed: NEW configurations start with `compressed`,
  worst-spec share 0.5 and, if D4 says so, the chosen α learning rate. Saved configurations are untouched.

## 6. Acceptance gates

| Gate | Pass when |
|---|---|
| G1 | `examples/check_reward_identity.py` on the M6 pilot after the change: 2,811 / 2,811 bitwise, 0 exclusions |
| G2 | Reward-v2 stage A aggregates and stage B / C transition rewards recompute to their recorded values with their recorded settings (1e-12) |
| G3 | Unchanged: the default real OTA7 config hash `9a4deb7a…` and task hash `b9ca139a…`, every protected config/example hash, and the hashes of existing saved workbench configurations |
| G4 | Full suite green; `npx tsc --noEmit` clean; hermetic browser check of B2, B3 and B5 against a scratch backend with fixtures, never 8765 |
| G5 | Properties, fuzzed against a pre-edit evaluator snapshot where relevant, listed below the table |
| G6 | Scripted `real`-labelled backend episodes, listed below the table |
| G7 | The section 1 numbers reproduce from `artifacts/local/reviews/reward-review-2026-09-29/`; report any difference |
| G8 | Exactly the intended package files differ from a pre-edit snapshot (diff against the snapshot, not HEAD); digest before and after recorded |

G5 properties:
* Defaults reproduce today's evaluator exactly.
* Every gate-met evaluation scores above every gate-not-met one.
* A missing value counted as a failure never yields success. A row with an unflagged missing required value, or with a
  unit mismatch, is never scored.
* Attributed failures never terminate the episode.
* `after_nominal` makes 1 + K·[gate met] launches, and the ledger charges exactly the launches made.
* The compressed objective is strictly increasing and stays below 1.
* Margin sides never change violations or feasibility.

G6 episodes:
* Gate not met: no corner launch, and the step is scored.
* A corner with a flagged missing value: scored, in replay, and the worst case includes 1.0.
* An unflagged missing value, or an infrastructure error: truncated, as today.
* An attributed nominal failure: the episode continues.
* A stop request between conditions.
* Two parallel lanes.

## 7. Order of work

1. **Preflight.** Read section 3. Snapshot `src/analog_optimizer/` and record the digest. Reproduce section 1 (G7).
   Ask D1 and D4.
2. **Package.** A1-A7 with their tests; gates G1, G2, G5, G6, G8.
3. **Workbench.** B1-B6. Ask D3 and D5, then do B7 if D3 says yes. Gates G3 and G4.
4. **Suite and docs.** Full suite and `tsc`. Then the docs:
   * a "Reward v2.1" section in `docs/reward-v2.md`;
   * a `docs/decisions.md` entry with both digests;
   * the next free entry in `docs/workbench-log/7.101-and-later.md`, plus its row in the index.
5. **Report** as section 10 says, then stop.
6. **Short real check, only with a ceiling the user approves** (D6; proposal: at most 30 Spectre launches on OTA7).
   * One short run with `after_nominal`: resets, steps whose gate fails (1 launch each), and at least one step whose
     gate passes (1 + K).
   * The bridge was updated on 2026-09-29 (`~/virtuoso-bridge-lite` at upstream `168943c`, with a stricter tunnel
     check). Run the workbench's connection test before the first real call.
   * Audit launches charged against launches made, and recompute the rewards.
   * A1 is not forced physically: no deliberately broken designs. Its real check waits for a run that meets a broken
     design naturally.
7. **Not in this brief (a separate decision).** The matched comparison: `off` vs `after_nominal` vs `always`, 3 seeds,
   equal launch budget, on a task whose corner targets are reachable (see B6).
   * Measure robust-feasible designs per 100 launches, and launches to the first one.
   * The 999-call study of `plan-reward-v2-real-flow.md` section 6.4 is the template.

## 8. Decisions for the user (ask before the step that needs them)

| # | Question | Recommendation |
|---|---|---|
| D1 | Should attributed failures continue the episode in every policy (A2)? | Yes |
| D2 | Nominal gate band b | 0.5 |
| D3 | Should NEW configurations start with compressed + share 0.5 (B7)? | Yes, once A2 has landed |
| D4 | Temperature: (a) nothing; (b) a separate α learning rate (A6); (c) a lower initial α only | (b). Choose the rate with a unit-level check (synthetic transitions, no run) that α reaches its entropy target within 200-500 updates; B5 then shows it on real runs. Until A6 exists, (c) is the only lever and needs no code: initial α 0.02-0.05 in Advanced |
| D5 | Scale suggestions (B4) | As listed |
| D6 | Ceiling for step 6 | At most 30 launches on OTA7 |
| D7 | OTA7 corner targets (F6): keep them, relax them at the corners, or widen the parameter ranges? | Decide after B6's warning; not part of this build |

## 9. Later, and the rules it must follow (not in this brief)

* **Monte Carlo.** The finalist check comes first, as
  [plan-finalist-monte-carlo.md](plan-finalist-monte-carlo.md) designs it: after the run, at each
  finalist's worst corner, mismatch only, fixed seed, 32 samples and up to 100 when borderline, verdict mean ± 3σ with
  the yield count reported. A claim like "failure rate at most 1 % at 95 % confidence" needs 300 failure-free samples;
  that plan keeps 300 as a setting. Monte Carlo enters training only if finalists keep failing, and then under these
  rules:
  * The same fixed seeds for every design (common random numbers).
  * Per spec, mean − kσ for a lower limit or mean + kσ for an upper limit, with k = 3, entering the worst case as one
    more condition row.
  * Mismatch at the worst corner.
  * Never a yield fraction as the training reward.
* **Corners on the ngspice lane**, with SKY130 models and deck substitution as Analog Design Bench does it: the free
  test bed F9 asks for.
* **Corner-specific limits** for specs, if D7 asks for them.
* **Clearance as a soft minimum** over the specs (F7c): revisit after the first run with a margin weight above 0.
* **Saturation margins** from the operating points (vds − vdsat) as cheap robustness specs at nominal.

## 10. Reporting back

Write `artifacts/local/reviews/astra-reward-v2.1.md` (gitignored) with:
* each requirement: done, not done or changed, and why;
* every gate with its numbers;
* the digest before and after;
* the changed files;
* the decisions asked and the answers;
* anything left open.

Then write the record entries of step 4.
