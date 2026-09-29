# Reward v2: Implementation and Qualification Status

Latest: [Reward v2.1](#reward-v21-2026-09-29) is implemented, verified offline and checked physically under the approved 30-launch ceiling. The original v2 real qualification below is historical.

Status, 2026-09-26: **implemented; bounded real-flow engineering qualification passed**. The user authorized
implementation with "go on build the reward", under [the real-flow plan](plan-reward-v2-real-flow.md).
Its package-edit permission and no-MOCK requirement control this work. No claim of a better optimizer,
robust circuit, manufacturing yield or encoder advantage follows from the software checks below.

## Authorization and Resolved Failures

The user acknowledged `license_not_checkable` and permitted the read-side `recording/reader.py`
repair. The `lab` profile used the existing unknown-license acknowledgement gate and normal Spectre
licensing. No license check was bypassed, tunnel/daemon replaced, or live backend restarted.

A pre-dispatch journal counting error consumed zero calls; its prepared design was restored before
a corrected freeze. A then passed with 21 calls. The first B attempt consumed one valid nominal
call before `_commit` hit a missing `json` import. Its charged ledger and raw measurement survive;
the failed commit produced no evaluation/job table row. The import was fixed and the user explicitly
approved **B cumulative ceiling 44, total ceiling still 77** before the replacement B execution.
Passed A evidence and the failed B cost remain linked and hashed in the final manifest.

The replacement B also exposed two acceptance-driver errors: missing same-process resume lock
handoff and a legacy attention alias in the cross-encoder replay check. They were corrected with
no additional physical retry: the prepared run continued at its existing checkpoint, and only the
recorded-real replay check was repeated. Before/after driver and report evidence is retained.
An initial browser assertion used CSS-transformed text; the corrected check passed against the
same real run. A scratch API interruption was detected by the URL guard, then only that scratch
API was restarted. These failures are not hidden successes or uncounted simulations.

## Reward Contract

`constraint_violation_v2` stores its settings explicitly:

| Setting | Compatibility Default | Initial Robust Choice |
| --- | --- | --- |
| `violation_shape` | `capped`: min(1,d) | `compressed`: d/(1+d) |
| `worst_spec_share` | 0 | 0.5 |
| `objective_weight` | 0 | 0 |
| `margin_weight` | 0 | 0 |
| Condition policy | `off` | `always`, nominal + four screening corners |
| Operating-point input | off | on for the completed real learning check |

Each spec uses its worst applicable condition violation. The penalty combines the weighted mean
with the unweighted largest hard-spec violation. `nominal_only` targets use nominal measurements.
Missing optional coverage excludes that spec completely; required invalid measurements or
infrastructure failures produce no reward/replay entry. Hard feasibility is checked against actual
bounds and validity, independently of reward sign and complete-plan coverage.

Only complete hard-feasible observations may receive bonuses. The objective uses its least
improvement across applicable conditions. Clearance uses the tightest eligible hard-spec signed
margin, compressed by m/(1+m). Zero-width equalities remain hard constraints but are excluded from
clearance. The public `spec_margin` retains its signed arithmetic; the Corner check's old `min_margin`
meaning is unchanged. Extreme diagnostic margins saturate to the largest finite float and explicitly
name `saturated_margins`, keeping records JSON-finite without inventing a measurement.

At share 1, soft violations do not affect the penalty. A zero penalty therefore does not mean every
soft spec passes. Finite underflow can also erase a tiny scalar penalty; actual-bound checks still
report the correct infeasible verdict. Reward is never a substitute for that verdict.

## Data and Execution

Observations contain an ordered result tuple, a separate complete planned-condition tuple, reward
settings and policy, plus mapped nominal operating points. Corners never replace nominal graph or OP
inputs. Missing/nonfinite OP quantities are masked. The optional common projection takes 12 values
and 12 masks, with no added encoder layer/state keys when disabled. GT, RGCN and GATv2 node-processing
blocks and SAC update equations remain unchanged.

`spec-input-v2` has 21N+11 columns: the original per-metric 13 and global 7 positions are preserved
within their blocks; added columns expose objective, adverse values, plan coverage and verdicts.
Four per-metric MC columns remain zero. MC execution and `after_nominal` training are not implemented.
Checkpoints are `graph-sac-v2`; environments are `sizing-env-v3`. Exact resume rejects changed
reward/condition/schema/source/dependency contracts. V1 migration is explicitly unsupported. A
compatible fine-tuned actor may transfer; changed reward semantics reset critics, targets and replay.

The real implementation reserves the whole candidate plan before dispatch, gives each lane a finite
allowance, records intent before each physical invocation and completion afterward, and checks stop
requests between jobs. Native preparation is nominal only; derived corner decks use the original
verified export without a corner sizing write. Unknown worker leases are retained conservatively,
separate from confirmed jobs; automatic resume refuses them until reconciled. Missing conditions
are candidate outcomes, not invented simulator job rows.

Workbench settings, compiler, real factories, checkpoint compatibility, tables, summary, best-design
selection and current frontend source carry these contracts. Classes are complete feasible, observed
nominal feasible, then valid infeasible. Best-design selection is separate from best-policy checkpoints.
Old table rows have unknown robust coverage, not a fabricated pass. The standalone SQLite reader
now restores stored v2 observations, reports condition coverage/binding conditions and actual bound
verdicts, and exports actual stored job rows. Its report distinguishes nominal from robust feasibility.
The physical workbench flow and current-source browser presentation passed the checks below.

## Real Qualification

All calls used the dedicated real OTA7 task, its existing two width groups and the frozen six
historical hard targets. No target was relaxed and no measurement was fabricated.

| Stage | Planned / Started / Completed | Uncertain | Result |
| --- | ---: | ---: | --- |
| A | 21 / 21 / 21 | 0 | Repeated nominal, four derived/fresh-export corner comparisons, two legal perturbations, restored-baseline confirmation |
| B, first attempt | 43 planned; 1 started/completed | 0 | Stopped at the recording error; no transition/update; physical restore verified |
| B, repaired run | 43 / 43 / 43 | 0 | Two resets + eight five-condition steps + final confirmation; cumulative B = 44 |
| C | 8 / 8 / 8 | 0 | Two resets + one five-condition step + final confirmation; another full step refused with four slots remaining |
| Total spent | 73 started / 73 completed | 0 | Below total ceiling 77; unused calls were not spent |

A verified semantic deck equality, independent export provenance, actual measured supply, PSF
reparse and frozen scalar tolerances. B completed 10 evaluations, 42 durable simulator-job rows,
8 transitions and 7 on-policy SAC updates across pause/save/resume. C completed 3 evaluations,
7 job rows and 1 transition, with zero updates. The final audit matched job and condition tables
to raw real results, independently recomputed all nine transition rewards/verdicts, and verified
each preparation restoration plus A/B/C final baseline measurements. Per-stage wall times and
segment times, raw paths, reservations and calls are retained in the machine report.
Stage wall times were A 58.52 s, failed B 15.33 s, repaired B 190.18 s and C 37.48 s;
these are driver/segment measurements, not total human waiting time or simulator-only throughput.

One B candidate was nominal-feasible; none was robust-feasible. This is not proof that the domain
is infeasible. All three encoders with OP off/on passed forward/update/exact-next-update checks
using B's recorded real transitions, not fresh on-policy training for RGCN/GATv2.

## Evidence

- **70 selected tests passed**, 0 failures/errors/skips, 12.14 s. They are pure arithmetic/schema/budget
  checks and processing of recorded REAL data. One upstream Torch deprecation warning remains.
- Final-source M6 identity: **2,811 eligible / 2,811 bitwise identical / 2,811 within absolute 1e-12**;
  verdicts and violations also match. Coverage is 2,808 fold records plus 3 final checks, zero exclusions.
  This is not a fresh simulation, PSF re-audit or loading of the historical learners.
- All three current encoders with OP off/on ran actual SAC updates on recorded real transitions;
  duplicate saved state produced equal next-update diagnostics and actor/critic tensors. Original
  v1 input columns match the frozen function. Objective/clearance arithmetic was also recomputed
  on a saved real feasible record without changing its measurements or physical target limits.
- TypeScript passed using the existing Windows Node executable and `tsc --noEmit`. **18 browser
  checks passed** using current Vite source on 5187 and the scratch API on 8837, real B tables,
  controls, model facts, coverage/verdicts/clearance and launch accounting. Desktop screenshots
  were inspected; no route interception, fake response, simulator start or request to 8765 occurred.
  Both scratch services were stopped afterward. No production build was performed. The old full suite was not run because
  it includes synthetic/fake backends; the unrun test-file list is in the software manifest.
- The default real OTA7 config hash remains
  `9a4deb7aa143c9cf3063cac7b05f4db61148746885bfe6f0e46d73e86ff3c568`;
  task hash remains `b9ca139a4c4a40223bb5379bfaf9a58cba6a809f61063b4ab90d3f26a586f6dd`.

Optimizer digest: `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54` ->
`3473ed9c8336e0a01e82bb84d13f4ea416961024092810c22cd4ce8ce58f8731`.
The recoverable pre-edit source snapshot is retained. Exactly these 19 optimizer files differ
from that snapshot (paths relative to `src/analog_optimizer/`):

```text
backends/backend.py
backends/conditions.py
backends/gpdk045.py
backends/gpdk045_two_stage.py
backends/native_preparation.py
backends/virtuoso_bridge.py
envs/sizing.py
graph/pyg_converter.py
measurements/specs.py
models/encoders.py
models/inputs.py
recording/reader.py
recording/report.py
recording/session.py
recording/store.py
training/parallel.py
training/replay.py
training/runner.py
training/sac.py
```

All 63 protected config/example hashes match the pre-edit baseline. The shared repository received independent
commits and a frontend build during this task (records 7.90-7.93); this task issued neither, and did
not start/stop/restart a backend on 8765. Those peer actions are not this task's acceptance evidence.

Artifacts:
[acceptance summary](../artifacts/local/reward-v2-real/20260926-qualification-05/acceptance-summary.json),
[software manifest](../artifacts/local/reward-v2-real/20260926-qualification-05/software-check-manifest.json),
[final identity](../artifacts/local/reward-v2-real/20260926-implementation-01/identity-reader-final.json),
[final execution manifest](../artifacts/local/reward-v2-real/20260926-qualification-05/manifest.json),
[browser checks](../artifacts/local/reward-v2-real/20260926-qualification-05/ui/browser-report.json).
The final manifest SHA-256 is `dd0c2355f25801e73d21614715b313e827a314a436af3eab23f9acdeb796e88c`.
Earlier blocked/failed reports are preserved as historical evidence, not overwritten with passes.

## Gates and Limits

| Gate | Current Result |
| --- | --- |
| A1 Compatibility | Passed on recorded data/default hashes/v1 columns |
| A2 Semantics | Passed pure arithmetic and recorded-data bonus checks |
| A3 Conditions | Passed real A deck/export/measurement/PSF/supply checks |
| A4 Learning flow | Passed real B updates, persistence and pause/resume |
| A5 Budgets/recovery | Passed real C shared admission and all physical restorations; failure-branch gaps below |
| A6 Network/contracts | Passed six encoder/OP combinations on B real replay and exact next-update recovery |
| A7 Workbench/UI | TypeScript and 18 current-source scratch browser checks passed against real API/data |
| A8 Provenance | Final source/default/protected hashes, tables/raw data and cost audit passed |

Not implemented: Monte Carlo, `after_nominal` skip-on-fail training, v1 checkpoint migration and the
separate reward-comparison study. No fresh robust-feasible design or physical bonus path was observed;
bonus arithmetic was checked on historical real measurements. Attributed physical failure,
mid-corner cancellation, uncertain launch and worker-loss recovery were not deliberately induced;
their pure contract coverage is not a physical claim. The unfiltered legacy suite remains unrun.

The next research step is the separately proposed 999-call matched three-arm/three-seed study in
plan section 6.4, with a new frozen task and explicit budget decision. It has not started. Passing
this bounded qualification establishes working machinery, not improved optimization, worst-case
coverage, mismatch yield or manufacturing readiness.

## Frontend Follow-Up

After qualification, the user requested a matching frontend update (record 7.96). This changed
frontend files only: `Right.tsx`, `Editors.tsx`, `RunTabs.tsx` and scoped control widths in
`styles.css`. Reward/condition edits now refresh saved-model compatibility, Specs has readable
Objective/Judged at controls with unchanged backend types, all saved reward coefficients and
condition identities are visible, and run status separates nominal/full-plan feasibility and values.
Launch costs and invalid robust settings are explicit; current draft settings never replace saved
executed-reward facts. No optimizer/backend change, new physical call or live build was needed.

TypeScript and 40 real-data/API browser checks pass at 1680x1050 and 1100x800. The new evidence is
[frontend browser report](../artifacts/local/reward-v2-frontend/20260926-01/attempt-05/browser-report.json).
Earlier qualification reports and frontend hashes remain historical snapshots, not rewritten to
claim these later UI changes were part of the physical run. All 73 raw result hashes and the frozen
backend/configuration hashes still match. The scratch preview remains on 5187/8837 for this follow-up.

## Audit Fixes (2026-09-26, record 7.98)

An independent audit (record 7.97, `artifacts/local/reviews/fable-audit-reward-v2.md`) ran the repository's full
regression suite, which the qualification above had replaced by a 70-test selection, and found it red (130 failed,
115 errors). Three behaviour regressions were fixed on the user's request; nothing above about the reward arithmetic,
the real stages or their evidence changes.

- `envs/sizing.py`: a result whose `simulator_invocations` is `None` was treated as an uncertain physical launch and
  the candidate truncated. The synthetic and MOCK backends never report that field, so every MOCK evaluation was
  truncated and every MOCK run failed. A synthetic result is now a complete call with zero real invocations, and a
  pending launch is marked "uncertain" only for a real task (the recorder's `simulation_jobs` intent accepts 0 or 1).
  `None` on a real result is still uncertain, and a real job that reports zero invocations still costs no call.
- `models/inputs.py`: `SpecSchema` refused every `version` label but `spec-input-v2`, which broke the untouched M6
  modules (`evaluation/cross_category.py`, `real_category.py`) that name their registries. The label is identity again
  (the default registry keeps its name `spec-input-v1`); the column layout is the new `SpecSchema.layout` field,
  fixed at `spec-input-v2`, recorded in every checkpoint contract and refused for any other value. Workbench
  registries keep their names and the registry suffix (`compile.py`).
- `gator_workbench/tasks.py`: MOCK runs now receive the run's reward settings (before, the learner enforced the
  configured settings against a replay produced with the defaults). Also: MOCK job rows count the toy call again;
  a killed, failed or force-cancelled MOCK evaluation is no longer an "unresolved physical launch" that blocks the
  resume (`engine.py`); the objective-row checks moved from the schema to the plain-language checklist
  (`validation.py`, `objective_without_limit`, next to `multiple_preferences`); `analog_optimizer.backends.conditions`
  is preloaded; the `best_*.json` status text says "nominal evaluation only" for a run without corners.

Optimizer digest after the fixes: `f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a`. The real
stages A/B/C above ran at `3473ed9c...`; the evaluator's arithmetic is unchanged since, and the identity check was
re-run on the final source: 2,811 / 2,811 bitwise, 0 exclusions. New tests: `tests/test_reward_v2_audit_fixes.py`
(the invocation rule on both origins, the label/layout rule, the M6 registries load) and
`tests/workbench/test_wb_reward_v2_mock.py` (a MOCK run with a compressed ramp, share and bonus completes, its
learner accepts the replay, one job row per toy call). The full-suite result is in record 7.98.

## Reward v2.1 (2026-09-29)

The [reward v2.1 brief](brief-reward-v2.1-for-astra.md), section 7 steps 1–5, is implemented and verified offline.
The older qualification above remains historical evidence. The offline work made no physical calls (record 7.106).
The user subsequently approved D6 with a 30-launch ceiling. Its first full workbench connection check passed all
layers except unknown license status (`license_not_checkable`), so the physical check stopped with zero simulations
and zero parameter writes (record 7.107). The user then approved proceeding with that unknown status. The real
after_nominal check completed with 10/30 launches: two nominal failures skipped their corners and qualification-05
stage B’s last design ran nominal plus all four corners. Cumulative reservations were 18, charges/made 10, unused
slots released 8, retries/uncertain/outstanding 0. All six rewards recompute exactly, and the starting snapshot plus
six nominal metrics were restored exactly (record 7.108). This fixed-action check made no learner updates; the
last design still fails the full corner plan, and no missing-value failure was forced.
The [section 10 report](../artifacts/local/reviews/astra-reward-v2.1.md) gives the changes, decisions and retained failures.

A completed simulation may count a missing required value as violation 1 only when that spec opts into
`missing_is_failure`. Other measured specs retain their values. Unit errors, unflagged missing values and
infrastructure faults remain unavailable. The row keeps its honest status, reason and affected metric IDs.
Attributed design failures now continue the episode in every policy. The user explicitly retained normal termination
without bootstrap at the final allowed step and existing configured success termination.

`after_nominal` runs corners only when nominal passes every active hard spec. Resets cost one launch; a failing
nominal step costs one, and a passing step costs 1 + K. Admission reserves the full plan before preparation and charges
only launches made. With gate band b (default 0.5), failed nominal rewards lie below −b, while scored gate-passing
rewards start at −b. The approved next-representable-float guard prevents a rounded tie. Complete feasible designs
retain their bonuses. Coverage uses existing inputs; no network column or Monte Carlo behavior was added.

`objective_shape='compressed'` keeps paying for further improvement, using the least improvement over applicable
conditions. It is capped at the representable value below 1; monotonicity is non-decreasing everywhere and strict
where precision distinguishes results. The compatibility default is still `clipped`. `margin_sides` selects both,
lower or upper for clearance and Corner check ranking; both applicable bounds still govern violations/feasibility.

New browser configurations start with compressed violations and worst-spec share 0.5 (D3). Saved configurations and
schema compatibility defaults stay unchanged. Optional Specs columns expose the two per-spec settings and a zero-floor
hint. Creating a row or editing its unit/limits with an empty scale suggests 3 dB, 10 degrees, the target tolerance,
half an interval width, or the existing threshold fallback. Loading a saved empty scale does not fill it (D5).

SAC now accepts an independent `alpha_learning_rate`; empty means the actor's rate. **No separate starting rate is
shipped.** The user rejected 0.0065 from the preliminary 500-update check. A 1,000-update repeat on fixed algebraic
synthetic transitions tested 0.003, 0.005, 0.0065 and 0.01. None reached the ±0.15-nat target band by update 500 and
kept every later trailing-50 mean in it through 1,000 without any individual entropy below −2. The 0.005 rate settles
in band only after update 695; 0.0065 leaves the band after crossing it. These are unit-check observations, not circuit
tuning. Every update and the superseded preliminary evidence are retained in the report's evidence directory.

Status, Data tables and the reward-review digest show p90−p10 over the last 50 scored designs and the latest
alpha*(−mean log probability). The brief's warning appears when the former is smaller. Both come from existing tables.
A separate, non-blocking corner-target warning rejudges recorded measurements and names worst misses of the best
recorded design. Corner check can include the real task reference even if nominal fails. No observed full-plan pass
is not a proof of infeasibility; D7, changing targets or ranges, remains outside this build.

Validation: **1,414 passed, 24 warnings**, 134.82 seconds, full `-n 12 --dist load` suite on the shared tree with scratch
settings; `npx tsc --noEmit` clean; **27/27** hermetic checks against current Vite source on 5191 and scratch API 8841.
Both services stopped; no live frontend build or 8765 operation. An existing cancellation timing test failed once
under concurrent validation, passed alone unchanged, and passed in the final full suite. Earlier failures remain logged.

G1: **2,811/2,811 bitwise identities**, zero exclusions. G2: 3 A aggregates + 8 B + 1 C transitions, maximum delta 0.
G3: both pinned OTA7 hashes, 68 protected files, 16 saved configurations and 12 task files unchanged. G5/G6 property,
fuzz and scripted episode checks pass; G7 recorded review numbers reproduce. G8: exactly eight package files changed
against the pre-edit snapshot. One digest step:

`f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a` →
`3f00832c89c1cf7af5cbc5ab6dac74c20250a76ea7bfa3a2df06717087fdd6f4`.

Old checkpoints still need their exact source/dependency contract. Physical after-nominal execution is verified by
record 7.108; naturally occurring missing-value failures, a matched optimization comparison and Monte Carlo remain
unverified or out of scope. No
optimizer superiority, robust-feasible circuit, yield or manufacturing-readiness claim follows. The user authorized
separate package and workbench commits after completion; pushing remains outside that authorization.

**Audit and fixes (2026-09-29, record 7.112).** The commits were later pushed on the user's request (`63883d3`). An
independent audit (`artifacts/local/reviews/audit-reward-v2.1.md`) re-ran the suite (1,417) and the M6 identity
(2,811 / 2,811 bitwise) and re-derived the step-6 rewards; "old checkpoints" above means exact resume only, since
fine-tune and frozen still load older models with warnings. It found two workbench faults, now fixed: a new Specs row
froze the fallback scale 1 (1 W, 1 Hz) before its limits were typed, and equation specs were blanked on any
measurement_error row, which defeated "Missing value = failed" for specs computed from probes.


### D7 follow-up: new testbench variant, plan only

The user replaced the original D7 choices with a [new OTA7 current-reference variant plan](plan-ota7-current-reference-variant.md).
The variant uses an ideal current reference and diode-connected NMOS for M5/M7 bias, VDD/2 input common mode,
the same hard targets and new user-copied cells. The original task and evidence remain unchanged. The user chose
core-only power for the existing target, with bias power reported separately. Nominal-current tolerance is pending.
First qualification is proposed as five launches only after separate approval, followed by a miss report; any
corner-specific limit proposal comes only after those results. No implementation or new physical calls in this plan.
