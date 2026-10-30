# Plan: reward v2 with real-flow qualification

> **Status (2026-09-30): DONE.** Stage A/B/C qualification passed on 2026-09-26 with 73 Spectre calls (A 21, B 44,
> C 8; record 7.95); audit fixes in records 7.97-7.98; committed in `1135b8b`. The current reward is v2.1
> ([reward-v2.md](reward-v2.md)).

Status: **implementation plan, 2026-09-26**. It was subsequently invoked by "go on build the reward".
The code is integrated, but physical acceptance stopped before Stage A at `license_not_checkable`;
see [implementation status and evidence](reward-v2.md). This plan itself remains the frozen scope,
not a claim that its physical gates passed.
Follow-up authorization: the user subsequently said "permit all actions without license. and fix the problem".
This permits acknowledging `license_not_checkable` and trying the normal licensed Spectre flow;
it does not disable or bypass licensing. It also permits the identified `recording/reader.py` repair.
All existing launch ceilings, no-retry rules and shared-service protections remain in force.
After A passed (21 calls), B stopped after one nominal call at a missing `json` import in the
workbench commit branch. The user explicitly approved **B cumulative ceiling 44, total ceiling 77**.
Preserve that failed call in the ledger and the passed A evidence; refreeze repaired code before a
replacement B execution. C remains bounded by both its original ceiling and the remaining total.
This replaces the implementation instructions in
[the earlier plan](plan-robust-reward-and-network.md) and
[the Astra brief](brief-reward-v2-for-astra.md). Historical statements in those documents remain historical.
This document controls scope, ordering, validation and reporting when they disagree.

## 0. User decision and permission

The user said: "Dont use fictional MOCK, run real flow if test is needed. Consider the project, give a new plan with permission to modify optimizer code."

**Permission to modify `src/analog_optimizer/` is explicit for the reward, condition evaluation,
observations, network inputs, replay, recording and checkpoint changes specified here.** This is an
intentional optimizer change under `CLAUDE.md`, not a workbench-only feature. It may change the source
digest and invalidate exact loading of older checkpoints. Preserve the existing source and evidence;
record the measured before/after digest. Do not ask again merely because a necessary edit is inside
the optimizer package.

The request authorizes using the real flow for necessary verification. The old brief's prohibition
on Spectre/bridge calls and its MOCK acceptance stages no longer apply to implementation of this plan.
Use the existing authorized test circuit, connection and parameter permissions. No fabricated circuit
responses, `SyntheticSizingBackend`, corner-shift toy, fake backend or silent fallback may qualify
this work. Algebraic checks are calculations, not circuit experiments; recorded real measurements may
be read and processed again without spending another simulator call.

The deliverable of the current request is this plan. No code implementation or simulation is launched
while writing it. A later instruction to implement it includes its bounded real verification; it does
not require repeating the package-edit or real-versus-MOCK decision. The numerical caps in section 6
are conservative engineering limits proposed here, not numbers supplied by the user. A larger reward
comparison study is separately identified and is not automatically started as a software test.

Still in force: **no commit, no push, no live frontend build, no starting/stopping/restarting the user's
backend on 8765**. Preserve the shared dirty tree and index. Do not modify pinned historical configs,
examples or evidence. Use scratch settings/outputs. If a requirement or real prerequisite cannot be
met, stop the affected work and report the concrete conflict; do not substitute MOCK or weaken a gate.

## 1. Project facts that determine the design

These facts come from the current repository, not a fresh inspection of the running simulator:

| Fact | Consequence |
| --- | --- |
| Current encoders are `graph_transformer`, `rgcn`, `gatv2` (`models/encoders.py`; records 7.86-7.87). | Cover all three. Do not restore deleted encoders. |
| Measured optimizer digest at the preceding preflight was `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54`. | Re-measure before editing; `aa987cf0...` is historical. |
| `real:gpdk045_ota7` has a qualified nominal native CDF/export/Spectre flow. OTA5/VCO registered examples were withdrawn (7.73). | Start with OTA7; verify its configured binding/receipt still identifies the dedicated test design. |
| OTA7's declared action space is two matched width groups: M1/M2 3.6-4.4 um in 5 nm steps; M6 7.2-8.8 um in 20 nm steps, M7=M6/4. | Keep this domain. Do not add length, bias or compensation actions to obtain a favorable result. |
| The Corner check code supports OTA7 screening conditions, but its real PVT path is documented as unverified. | Physical corner qualification is an early gate, not an assumed capability. |
| Native preparation is nominal-only; it already retains the original export and its hash. | Implement derived corner decks from that export without another sizing write. |
| The budget currently reserves one launch per attempt and receives the final launch count afterward. | Multi-corner execution needs reservations covering the entire candidate before dispatch. Counting afterward cannot enforce the cap. |
| OTA7 requires `unity_downward_crossings == 1`. Its nearest-limit margin is always zero when satisfied. | Equality constraints stay hard pass/fail constraints but are excluded from the clearance bonus. |
| Operating points already come from real DC measurements. | Carry those real values into the network; do not manufacture operating points for missing devices. |

Sources: [OTA7 qualification](m5-real-topology.md), [native execution](parallel-spectre-sac.md),
[real native verification](native-cdf-real-verification.md), [workbench](workbench.md),
`configs/gpdk045_ota7_transfer.json`, `configs/gpdk045_conditions.json`, and the source modules above.
Historical OTA7 specs are engineering targets from a narrow nominal study, not established robust
specs or product requirements. Qualification may find them unattainable at some corners. That is a
result to report, never a reason to silently relax them.

## 2. Scope and permitted implementation files

Package edits are limited to the following files and the purposes below. A newly needed package file
or a change to another algorithm requires identifying the need before widening this list.

| Files under `src/analog_optimizer/` | Permitted change |
| --- | --- |
| `measurements/specs.py` | Versioned reward settings, condition aggregation, objective and clearance terms, diagnostics, shared signed margin helper. |
| `envs/sizing.py` | Planned/evaluated conditions, real step scheduling, nominal operating points, counters and v2 failure semantics. |
| `backends/backend.py`, `backends/conditions.py` | Derived-artifact capability and typed training-condition contracts. |
| `backends/gpdk045.py`, `backends/gpdk045_two_stage.py` | Accept the explicit training purpose within the existing OTA screening envelope; no new action permissions. |
| `backends/virtuoso_bridge.py`, `backends/native_preparation.py` | Derive and register immutable decks, preserve export evidence, job identity and real launch accounting. |
| `graph/pyg_converter.py` | Optional operating-point columns, masks, normalization and dynamic tensor refresh. |
| `models/inputs.py` | Input v2, complete observation validation, planned coverage and cache identity. |
| `models/encoders.py` | Only the optional common operating-point projection; retain all three node-processing blocks. |
| `training/replay.py`, `training/sac.py` | Reward recomputation, settings/failure contracts, v2 checkpoint metadata and exact recovery. SAC update equations are unchanged. |
| `training/runner.py`, `training/parallel.py` | Factory plumbing, candidate/launch counts and reserved per-candidate launch limits. |
| `recording/codec.py`, `recording/store.py`, `recording/session.py`, `recording/checkpoint.py`, `recording/report.py` | Round-trip observations/settings, record every actual job and restore/reconcile transitions and costs. |

Workbench changes belong in `src/gator_workbench/`: schema, compile/validation/readiness, tasks,
spec equations, modes/checkpoints/PDK feature selection, engine/lanes/worker/budget, storage tables,
aggregates and best-design reporting. Follow the current split API modules; do not put the whole
feature back into `api/app.py`. Frontend changes belong in the existing Specs, RL network, settings,
run-status and model-facts components and their shared descriptors.

New scripts/tests/configuration files and documentation are permitted outside the package. Use new
files for the frozen real-validation manifest and corner metadata. Existing `configs/*.json`, pinned
examples and historical artifacts remain untouched. `evaluation/corners.py` remains unchanged:
post-check verdicts and `robust_score` are not training rewards.

Not included: Monte Carlo execution, new circuit/profile qualification for LDO/VCO/generated/Maestro/
ngspice corner training, new encoders, global attention, a surrogate, topology changes, broad parameter
permission changes, v1 checkpoint migration, agent reward-review tools or encoder superiority studies.
Existing synthetic code is preserved but is not extended or used to validate this plan.

## 3. Reward contract

### 3.1 Two explicit configurations

- **Compatibility default:** corners off, capped ramp, worst-spec share 0, objective weight 0,
  margin weight 0, operating-point inputs off. The evaluator's nominal arithmetic remains bit-identical.
- **Initial robust configuration:** nominal plus the four non-nominal screening corners, policy
  `always`, compressed ramp, worst-spec share 0.5, objective weight 0, margin weight 0. Operating-point
  inputs are available and explicitly recorded; the real smoke enables them. These are starting
  settings for qualification, not empirically established optimal settings.

Old configuration hashes remain unchanged when all newly introduced fields have their compatibility
defaults. Store the selected settings in every run and checkpoint. Do not change settings during a
run, adapt scales online or silently select the robust configuration for an old saved task.

### 3.2 Violations and aggregation

For metric value x at an applicable condition, lower limit L, upper limit U and scale a > 0:

```text
d = max(0, (L - x)/a if L exists, (x - U)/a if U exists)
v(d) = min(1, d)             for capped
v(d) = d/(1 + d)             for compressed
v_s = max of v(d) over the spec's applicable evaluated conditions
P = (1 - lambda) * weighted_mean(v_s) + lambda * max_hard(v_s)
base_reward = -P
```

Weights are finite and positive, rescaled by their maximum exactly as today. The hard maximum is
unweighted. An attributed design failure contributes violation 1 even with a compressed ramp and
without a numeric measurement; it must participate in the penalty. Inactive specs contribute nothing.
`nominal_only` specs are evaluated only at nominal. For optional specs, use values only when valid
at every applicable evaluated condition; otherwise exclude the spec and record its missing coverage.
Nominal-only evaluation therefore keeps today's missing-optional rule. Objective bonuses require
complete valid objective coverage and are zero when it is absent.

Robust feasibility is an independent boolean: every active hard spec is valid and satisfied at every
applicable planned condition, and the plan is complete. Infrastructure and required-measurement
failures produce no reward or replay entry. Optional missing values do not create a hard pass/fail
claim about that optional spec. Reward sign is never used for feasibility or best-design class.

Mathematical acceptance properties (valid evaluations, bonuses off): range [-1, 0]; per-spec worst
violation does not improve when another applicable condition is added; lambda=0 reproduces the old
aggregation; lambda=1 ignores soft penalties. With lambda<1, zero means every included valid spec is
met; with lambda=1, zero means every hard spec is met. Do not assert aggregate reward monotonicity
when optional coverage changes the included set or its denominator.

Keep success tests against the actual bounds/validity, not an underflowed or rounded compressed
value. Implement stable finite arithmetic; a very large finite miss must not yield NaN. Strict
monotonicity of the real-valued formula is not a promise to distinguish every float at saturation.

### 3.3 Objective and clearance after feasibility

Only a complete, robust-feasible evaluation may earn a bonus:

```text
reward = -P + beta * objective_improvement + gamma * clearance
```

Beta and gamma are each in [0, 1], default 0. There is at most one active objective.
For `min`, an upper limit is required and improvement is
`clip((upper - value)/scale, 0, 1)`; for `max`, a lower limit is required and it is
`clip((value - lower)/scale, 0, 1)`. Use the smallest improvement across applicable planned conditions.

**Replace the old S3 mean-margin bonus with tightest-hard-spec clearance.** For each eligible hard
spec, take the smallest signed distance to a finite limit divided by scale across its applicable
conditions. Eligibility requires a one-sided limit or a nonzero-width interval. Exact equalities
such as the OTA7 crossing count are excluded from this bonus, but remain hard feasibility checks.
Then `m = min(eligible margins)` and `clearance = m/(1+m)`; if there are no eligible specs, the term
is 0 and the reported clearance margin is null. A `nominal_only` spec uses its nominal margin.
Include an objective spec if it is also an eligible hard constraint; protecting its nearest limit
is intentional. This supersedes the old objective-exclusion rule for the mean-margin bonus.

Keep a public signed `spec_margin(lower, upper, scale, value)` compatible with the existing tab's
arithmetic, including negative margins outside limits. Do not clip that helper globally. Bonus
eligibility/compression is a separate step. Report both raw per-spec margins and
`clearance_margin`/`tightest_clearance_spec`, with equality exclusions visible. Do not silently
relabel the old `min_margin` statistic: old runs and their Corner check ranking retain their meaning;
new v2 runs explicitly record which clearance rule is used for selection/display.

Range: [-1, beta + gamma]. A valid hard-infeasible evaluation gets no bonus and has a negative
penalty in ordinary representable arithmetic; a hard-feasible evaluation can still have a negative
reward because of violated soft specs. A scalar reward is a learning signal, not an absolute
guarantee of hard-constraint priority across an entire discounted trajectory.

Implement both bonus settings, initially exercise their arithmetic on recorded real measurements,
and leave them off in the first live learning smoke. Any later comparison adds one at a time. The
minimum-clearance bonus can be flat while another spec improves; do not claim it solves all credit
assignment problems. SAC reward/entropy scale diagnostics remain part of the record.

### 3.4 Conditions and failures

V2 training policies are `off` and `always`. **Defer `after_nominal` training.** Its skipped-corner
reward is optimistic and can punish crossing the nominal boundary by revealing an adverse corner.
Making coverage visible does not remove that change of objective. A future staged policy needs its
own reward contract and real comparison; it is not part of this delivery.

With `always`, a valid but nominal-infeasible candidate still runs every planned corner. Do not stop
the corner list at a spec violation. Reset remains a nominal baseline only, is charged, is never
inserted into replay and cannot be called robust-feasible while corners are unmeasured.

At infrastructure/ambiguous/required-measurement failure: preserve every completed job and mark
remaining conditions not run; truncate, no reward, no transition, no bonus. Stop new work on an
uncertain launch until reconciled. Do not manufacture a full corner pass rate from a partial list.

An explicitly attributed `invalid_design`/`nonconverged` result receives hard violation 1. In v2
robust mode it does not end the episode solely for that reason, at nominal or at a corner. An
attributed nominal failure may end that candidate's corner work, with known-failed verdict, incomplete
coverage and a bounded penalty; it can never earn a bonus or count as robust success. Preserve the
actual sizes/topology and mask unavailable measurements; allow the next action from that declared
failure state in replay validation. Never use stale values to make it look like a valid measurement.
This explicitly supersedes the old brief's unchanged nominal failure branch for robust mode only.
The compatibility default retains the old -1-and-terminate branch and its historical identity.

Do not add new heuristic attribution to the analyzers. Missing crossover or an ambiguous simulator
error stays a measurement/infrastructure failure unless the existing real evidence supports an
explicit candidate-failure classification. A branch not naturally reached in live verification is
reported as not live-exercised; never deliberately break the user's simulator to exercise it.

## 4. Real execution, budgets and records

Use the existing preparation owner, session lock and native CDF transaction. Per candidate:

1. Reserve one candidate evaluation and enough launch capacity for its entire plan (1 for reset or
   nominal-only, 5 for the proposed robust step). If capacity is insufficient, do not start it.
2. Write the complete legal width assignment once, run the existing callbacks, read back and verify
   it, export natively and bind candidate identity to the actual sizes and original export hash.
3. Run nominal. Derive corner decks from the **original** export, changing only the profile-approved
   section, temperature and supply; do not derive one corner from an already conditioned deck.
4. Register every derived artifact with a distinct job ID/hash/condition; never re-export or modify
   schematic sizes to run a corner. Feed every result through the existing computed-spec wrapper.
5. Record and reconcile every launch, result, measurement, spec value, validity, operating-point set,
   reason, timing and provenance. Finish the candidate only after its declared conditions finish or
   an explicitly recorded stop occurs. Release only unused reservations, never actual launches.
6. Close lanes before the preparation owner restores and verifies the complete physical snapshot.
   Include any final nominal confirmation simulation in the manifest's launch ceiling.

The launch reservation is a global allocation, not one independent cap per lane. Pass each worker
its finite allowance and enforce it before every physical invocation. Persist launch intent and
completion; reconcile uncertain launches conservatively so a crash cannot create free budget.
Report confirmed calls and unresolved intents separately. No automatic retries in initial validation.
Infrastructure streaks count launches in the coordinator's receipt order, with their order recorded.
Support timely stop between corner jobs without pretending the interrupted candidate is complete.

Store one candidate row and one job row per actual launch, not one job row per candidate. Conditions
not launched are outcomes in the candidate record, not invented simulator jobs. Distinguish
`candidate_evaluations`, `simulation_calls`, nominal feasibility, complete coverage and robust feasibility.
Keep both first-feasible receipt events and their launch counts. Baselines count toward cost but
nominal-only resets do not establish robust success.

Best design classes: complete robust-feasible, then observed nominal-feasible, then valid infeasible.
An incomplete candidate is never in the first class. Within each class use the declared objective
(worst applicable value for a robust design), existing reward/violation rules and stable ties;
explicitly record the resulting rule. Keep design selection separate from best-policy checkpoints.
Post-check verdicts remain those of `evaluation/corners.py`.

## 5. Observation, network and checkpoint contracts

Carry raw data needed to recompute the reward, not just an aggregated reward or worst number:

- `Observation` keeps nominal graph/metrics/status/job identity, plus ordered per-condition results,
  an explicit immutable `planned_conditions` list, policy/coverage and mapped nominal operating
  points. Plans cannot be inferred from completed results: dropped corners must be detectable.
- Each condition result carries status, `candidate_evaluated`, metrics/units/validity, job identity,
  reason and its measured operating points. Actual result identities must be unique, belong to the
  plan and match exported artifacts. Graph metadata still describes nominal, not the last corner.
- `evaluate_conditions(results, *, planned_conditions=None)` supports the one-element equivalence
  check when the plan is omitted; environment and replay always provide the full stored plan.
  `nominal_only` spec flags, failure sentinels and complete-coverage decisions are recomputable.
- Preserve input v1 columns exactly. Input v2 stays `21 * N + 11`: original 13 columns per metric,
  objective-min/max, worst value/validity and four zero reserved MC columns; original 7 global
  columns plus planned count, evaluated fraction, nominal pass and all-planned pass. Count only
  non-nominal corners; nominal appears once. The planned manifest makes these numbers well-defined.
- Derive worst-value selection in the evaluator: for one-sided specs the adverse extreme; for a
  range, largest shaped violation, ties prefer nominal then condition order. Report the binding
  condition. A failure penalty without a measured value has worst-valid=0, not a fictitious number.
- Implement the earlier P1-P6 operating-point block for the **three current encoders**: 7 normalized
  quantities plus 5 region flags, masks, `XU1.M1` to `XU1/M1` mapping, unmatched-key reporting,
  finite-value filtering, nominal-only network source, optional feature schema and projection.
  Invalid quantities are removed/masked before observation validation. Corner values remain recorded.
  Missing CC/source entries are masked, not extrapolated from MOS devices. With the block off,
  encoder state-dict keys remain unchanged. Cache identity includes all dynamic observations.
- Replay stores reward version/settings, plan, coverage and raw results. `validate` recomputes reward
  and verdicts, and `from_step` checks the journal's complete condition list and settings. Recording
  and `transition_from_data`/store reconstruction must restore all new fields, not their defaults.
- Use checkpoint version `graph-sac-v2`, spec version `spec-input-v2`, environment schema
  `sizing-env-v3`, and the explicit reward identifier `constraint_violation_v2`. Shape, bonus rule,
  failure policy and condition plan are separate contract fields. This replaces the old brief's
  label that incorrectly describes every selected ramp as capped.
- **Exact resume blocks changes** to reward settings, condition plan/policy, schemas, failure policy
  and source/dependencies. A warning is insufficient when restoring replay/critics for a different
  reward. Fine-tune may change reward settings with a clear warning, new replay/optimizers and
  reset critics/targets by default; copy an actor only if its input/model schemas are compatible.
  A v1 input/checkpoint is explicitly refused without the separately deferred migration tool.

Workbench fields retain the old brief's objective, judged-at, conditions, reward and operating-point
controls, updated for these semantics. Show `off`/`always`, the actual launch budget, full/partial
coverage, nominal/robust verdicts and the tightest eligible clearance spec. Explain equality exclusions
and checkpoint incompatibilities in plain words. No duplicate beta or launch-cap selector. Historical
tables load with explicit nominal/default values and unknown robust coverage, never fabricated pass.

## 6. Real validation protocol and cost

### 6.1 Freeze before touching the circuit

Write a new manifest under a new `artifacts/local/reward-v2-real/<id>/` directory before execution.
It pins source/dependencies, task/profile/creation receipt, graph/parameter domain, condition list,
numeric policy, measurement definition, specification limits/scales/weights, selected seeds/settings,
candidate assignments, stopping rules, comparison tolerances and launch ceilings. Read bindings from
the user's existing profile; do not invent hostnames or print credentials. Protect the original
schematic and use only the dedicated verified design identified by the receipt. Do not auto-start
a tunnel/daemon or displace another live run. An unavailable connection is a real blocker, not a
reason to claim end-to-end success from an offline replacement.

Start with the inherited six OTA7 hard targets, documented as historical study targets, in a NEW
configuration; preserve the pinned original file. Keep every spec/scale fixed for an experiment.
Qualification may motivate a subsequent reviewed task/domain revision, but its measurements are
then development data and cannot be called an independent evaluation of the revised task.

The initial commissioning tests deliberately change real measurements through legal sizes and
conditions. They do not require inventing a successful design. Freeze the target configuration and
enumerate which checks need only valid measurements and which require observed feasibility before
starting; an unobserved success/bonus path remains a declared physical coverage gap.

### 6.2 Initial acceptance envelope: at most 77 new Spectre invocations

These stages are sequential, stopping at the first unresolved correctness, measurement, budget or
restoration failure. The numbers are ceilings, not instructions to spend unused calls. Every call,
including reset, repeat, failed invocation and final confirmation, belongs to a named stage.

| Stage | Real work | Maximum launches |
| --- | --- | ---: |
| A: qualify decks and measurements | Two nominal baseline measurements; four derived baseline corners; four independently re-exported corners at the same sizes; two predeclared legal perturbations with all five conditions; one restored-baseline confirmation. | 2 + 4 + 4 + 2*5 + 1 = **21** |
| B: full workbench learning and recovery | Graph Transformer, operating points enabled, two four-step episodes: two nominal resets plus eight complete five-condition steps. Save/pause/restart at the episode boundary; resume the same run. One restored-baseline confirmation. | 2 + 8*5 + 1 = **43** |
| C: shared launch accounting | Two lanes, at most one nominal reset and one full five-condition candidate each; admission must refuse another candidate when fewer than five reserved slots remain. One restored-baseline confirmation. | 2*(1+5) + 1 = **13** |
| Total | No retries or unlisted baselines. Restored-baseline calls have their own reserved capacity. | **77** |

Use the profile's existing limits and callbacks. Predeclare the two perturbations as one legal grid
step on each independent width group from baseline, inward if already at a bound. A and B run one
lane. C follows only after serial checks pass; it proves shared accounting, not four-worker throughput.
At every stage honor any lower user/project cap. Refuse a run configuration that cannot enforce its
declared ceiling, and stop rather than silently enlarging the envelope.

For C, set the training sub-run's launch cap to 11: after two resets, at most one five-launch step
may be admitted, leaving four slots that cannot admit the other full step. Expected cost is then
7 training calls plus 1 restoration confirmation, below C's conservative 13-call ceiling. Check
the same admission rule on the persisted ledger before live dispatch. The validation must not
deliberately issue an over-cap call to demonstrate that it would have been an error.

The native-derived/re-exported comparison uses the same profile/model/analysis settings, sizes and
conditions. Compare prepared circuit text and semantic deck contents, not job-specific directory
names; independently inspect the executed section, temperature and measured VDD. Check size/CDF and
original-export hashes. Use existing qualified numerical tolerances where applicable; where none
exist, the proposed same-deck scalar check is `abs(a-b) <= 1e-8 * max(abs(a), abs(b), reference)`
with each positive physical reference frozen from the metric registry before simulation. Counts
and validity flags must match exactly. Record each actual comparison limit; discrepancies stop
qualification for diagnosis. This is an engineering repeatability threshold, not measured simulator
accuracy. Never pick a tolerance after seeing the difference just to pass it.

Reparse the actual PSF with the production analyzer and independently recompute the scalar specs,
violations, reward and verdict from the saved real metrics. A required metric without a valid value
blocks that acceptance case; a valid metric missing its target is a legitimate infeasible design.
No-feasible-design outcomes do not imply the domain was proven infeasible, and do not authorize
relaxed targets or a fabricated feasible result. Do not run the larger study merely to hide failed
measurement qualification.

Use B's real transitions to check forward passes and at least one learner update for each of GT,
RGCN and GATv2, both with and without the operating-point block as applicable, without new simulation.
Label this **replay of recorded real data**, not new on-policy training by those other encoders.
For checkpoint recovery, duplicate a quiescent saved learner/RNG state and compare its next sampled
update on the identical recorded replay. Live resume uses fresh real evaluations and is not asserted
to reproduce simulator output bit-for-bit.

Checkpoint/save/export/browser actions consume the same B/C budgets if they start work. Use a scratch
backend on a verified free port and, when needed, an isolated frontend dev server serving current
source; never build/serve over the user's `frontend/dist` or touch port 8765. Pass URLs explicitly
through WSL/Windows environment boundaries and verify the destination before browser actions.
No route interception or invented measurements may stand in for the real acceptance run.

### 6.3 No-call checks and existing evidence

- Run pure evaluator/property, parser/schema, budget-state and serialization checks. Arithmetic
  examples are clearly mathematical; they do not claim circuit performance. Do not invoke a fake
  simulator to make a failure-path check look like a physical experiment.
- Build the nominal reward-identity checker against the recorded M6 real pilot. Enumerate the saved
  manifest/report, including the three final checks outside fold runs; do not assume walking only
  `{opamp,ldo,vco}` accounts for the whole reported 2,811 calls. Count eligible records and exclusions
  explicitly, require all eligible comparisons to match, and reconcile total coverage with evidence.
  Report absolute differences and bitwise equality separately; use the old gate's 1e-12 threshold
  without presenting it as proof of bit identity. Qualification/requalification records are additional
  evidence only when they actually contain a comparable reward.
- Preserve the historical artifacts and audit scripts. New read-only tooling independently recomputes
  rewards without loading old incompatible learners or bypassing historical digest checks.
- Verify input-v1 column identity using saved real observations and a frozen v1 function in the test.
  Exercise invalid-input rejection and failure-state algebra directly; state which failure branches
  lack observed physical records. Do not cause license, transport or convergence faults on purpose.
- Type-check the frontend without a production build. Select and record a non-MOCK software test
  manifest; the old unfiltered full suite contains synthetic backends and is not this plan's gate.
  List unrun legacy tests and the resulting regression-coverage gap. Do not claim a full-suite pass.

### 6.4 Optional reward study after acceptance

Functional acceptance does not establish a better optimizer. A separate study proposal uses the real
OTA7 flow, GT only initially, three fixed seeds (17, 29, 43), and these matched arms:

| Arm | Ramp | Worst-hard share | Margin weight | Objective weight | Conditions |
| --- | --- | ---: | ---: | ---: | --- |
| A | capped | 0 | 0 | 0 | all five, always |
| B | compressed | 0.5 | 0 | 0 | all five, always |
| C | compressed | 0.5 | 0.1 | 0 | all five, always |

This first study compares the combined ramp/share change, then the added clearance term; it cannot
attribute a gain separately to ramp versus share. An additional arm needs a new counted budget.
Hold specs, action domain, operating-point choice, network/SAC settings, reset policy and stopping
rules fixed. Do not compare nominal-only A against robust B and call the difference a reward-shape effect.

Proposed pilot allocation: five four-step episodes per run = 5 resets + 20*5 = 105 calls; reserve
five fresh-condition checks of one predeclared selected finalist plus one restored-baseline call
per run. Maximum `(105 + 5 + 1) * 3 arms * 3 seeds = 999` new calls, separate from acceptance.
Unused finalist calls are not reallocated. Do not launch this study on the basis of the permission
for necessary software tests; present its frozen task and budget when the user requests the study.

Compare robust-feasible discovery, launches/evaluations/time to first robust feasibility, uncapped
hard violations, eligible clearance, optional objective value, failures, reward components and SAC
entropy/alpha diagnostics. Do not rank arms by raw reward values from different formulas. Keep
right-censored failures at their budgets; do not average only successful runs. Three seeds, one
known topology and narrow width ranges are pilot evidence, not proof of generalization, yield or
an encoder advantage. Validation used to choose a reward is not a held-out performance claim.

## 7. Implementation order

1. **Freeze the current baseline.** Re-read the dirty tree and current record; save a recoverable
   optimizer source snapshot without a commit. Record measured digest/dependencies, real OTA7
   default task/config hashes and the exact serialized configuration. Do not reuse the earlier MOCK
   starter hash as the real baseline. Check local evidence/bindings before scheduling any live work.
2. **Implement the pure evaluator and contracts.** Compatibility defaults, conditions/coverage,
   compressed ramp, worst-hard share, objective, eligible-clearance helper and diagnostics. Resolve
   float edge cases and corrected zero-reward properties. Run the historical real reward-identity
   checker now; it needs no simulator.
3. **Implement observations, inputs, recording, replay and checkpoints together.** Preserve nominal
   readers and v1 columns; add actual operating-point tensors/projection, settings propagation and
   exact-resume checks. Validate on saved real observations/transitions; never fake circuit outputs.
4. **Implement real derived decks and complete step execution.** Add `pvt_training`, keep native
   candidate preparation nominal, use original export evidence, implement failure/partial coverage
   rules and separate candidate/job counts. Add global full-plan reservations before any live run.
5. **Wire the workbench and current frontend source.** Settings/validation/compile, every real
   factory and computed-spec wrapper, ledger/lanes, job/metric tables, summaries/best design,
   model compatibility and the UI. Nominal-only profiles reject corners before writes or launches.
   Existing defaults keep hashes. Use a new corner-metadata file, never modify the pinned one.
6. **Freeze and execute real acceptance A, B, C in order.** Use the existing task approval/connection
   mechanisms with this conversation's authorization, explicit stage manifests and the bounded
   cost above. Do not restart shared services. Stop on a failed gate and report saved evidence.
7. **Audit and record.** Re-run reward identity on final source; verify real run/table/job/replay/
   checkpoint consistency, counts, hashes and restoration. Record all non-MOCK checks, failures and
   coverage gaps. Update current docs and local skill references to distinguish implemented and
   physically verified capabilities. No commit/push unless later requested.
8. **Only then consider the study.** Prepare the separate experiment proposal; do not call successful
   plumbing evidence a demonstrated reward improvement or automatically spend the pilot budget.

## 8. Acceptance and reporting

| Gate | Required evidence |
| --- | --- |
| A1 Compatibility | Default nominal reward identity, measured real-record coverage/exclusions, unchanged default real task/config hashes, preserved v1 input positions. |
| A2 Reward semantics | Pure properties including mixed soft/hard endpoint, range specs, optional coverage, equality exclusion, failure penalty, bonus gates and overflow handling. |
| A3 Real conditions | Stage A job/deck/measurement provenance, native-derived versus fresh-export agreement, no corner sizing writes, actual measured supply and condition labels. |
| A4 Real data and learning | Stage B real observations/operating points, condition tables, per-job persistence, valid replay, actual SAC updates, save/resume and exact next-update replay check. |
| A5 Budgets and recovery | Stage C shared reservations, no cap overrun or hidden retries, candidate/job counts, partial/uncertain launch handling, verified physical restoration. |
| A6 Network and compatibility | All three encoders on real-derived inputs/replay, op-mask/cache behavior, no layer when off, clear version/settings refusal or permitted transfer warning. |
| A7 Workbench/UI | TypeScript, current-source scratch UI against real run data/API, settings and cost line, coverage/verdicts/clearance/model facts; no live dist or 8765 changes. |
| A8 Final provenance | Before/after digest, exact optimizer edit list, final source/config/environment identity, protected artifacts unchanged, selected software check manifest and declared gaps. |

Produce an acceptance summary under the new real-output directory with `origin=real`, manifest hash,
per-stage planned/started/completed/uncertain calls, candidates/resets/transitions/updates, wall time,
source and configuration hashes, raw evidence paths, gate results and restoration state. No secret
connection values, model text or raw license output in summaries. Keep diagrams/plots out of the
workbench output flow under the repository's existing rule.

Update `docs/reward-v2.md` once implemented, `docs/workbench.md`, the decisions log and the next free
workbench record/index entry. Report what was not implemented, what was not exercised physically,
which pure/recorded-data checks were used, any failed gate, and any real cost. A recorded-data check
does not become a fresh physical test by renaming it. Do not rewrite M6 conclusions or claim that
passing five conditions proves worst-case coverage, mismatch yield or manufacturable silicon.

## 9. How this replaces the previous brief

| Earlier requirement | Replacement |
| --- | --- |
| Section 1 optimizer permission | Reaffirmed with the explicit package scope in section 2 and a current measured digest. |
| R1/G1 | Preserve nominal arithmetic; reconcile actual saved real evidence, including final checks; report bitwise and tolerance results distinctly. |
| R3/E3/W1 after-nominal default | Off or full `always`; skip-on-fail training deferred. |
| R4 nominal attributed failure unchanged everywhere | Old branch retained only for compatibility mode; robust mode permits a masked failure state and another action. No new heuristic attribution. |
| S2/G11 | Correct endpoint and optional-coverage properties; reward sign is not the feasibility verdict. |
| S3/G11 mean margin | Tightest eligible hard-spec clearance; equality constraints excluded from clearance, never from feasibility. |
| R7 reward label | `constraint_violation_v2` plus explicit shape/bonus/failure settings. |
| O1/R6/N1 | Add the planned manifest as well as results so coverage, success and reward can be audited. |
| O5/S4/W4 warning-only comparison | Exact resume blocks changed reward/condition contracts; permitted fine-tune changes clear replay and reset critics. |
| E5/W8 toy corner support | No new synthetic backend work or mock-shift acceptance. Preserve existing code without using it here. |
| P5/G10 five encoders | GT, RGCN and GATv2 only, on recorded/fresh real data. |
| G4-G7 fake/synthetic end-to-end gates | Real acceptance stages A-C plus explicitly labeled pure and recorded-real checks. |
| G8 unfiltered full suite | Audited non-MOCK software selection plus real-flow gates; report the remaining full-suite regression gap. |
| D2/D3 old digest and record 7.84 | Actual before/after hashes; next free append-only record. |
| Section 6 order and stage-3 MOCK study | Section 7 here; bounded real qualification before any optional real reward study. |

The design choices and budgets above are this plan's proposals within the user's requested scope.
They are not reports of implemented behavior, simulator availability or measured improvement.
