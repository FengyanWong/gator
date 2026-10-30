# Plan for Claude: TuRBO transfer, Pareto MOBO and SAC on matched archives and budgets

Date: 2026-10-21 (Europe/London). Status: **planned; no implementation, training or simulation dispatched**.
User request: "make a plan for claude to compare TuRBO with transfer, Pareto MOBO and RL using the same archived data and simulation budget".
Refined 2026-10-21 using the chat **Compare random forest calibration**
(`01a15d81-cd22-7560-b946-457fbab6ab9f`), at the user's request. Section 1 separates the claims;
sections 4.3 and 5.1-5.2 add RF diagnostics and separately budgeted follow-up comparisons.

This is a separate development experiment linked from section 16 of `plan-transfer-experiment.md`.
It does not replace the running Round 3 repeats, change the workbench's default optimizer, or replace the
prospective journal protocol in that plan's section 14. The request authorizes preparing this plan; it does not
authorize new physical runs. Claude should prepare the implementation, offline checks, frozen manifest and exact
launch budget before seeking authorization for the physical campaign. No commit or push is requested.

## 1. Decisions this experiment should support

1. On a fixed circuit and testbench, does giving BO the same archived measurements as SAC remove SAC's advantage?
2. At equal new-simulation cost, which method reaches a specified target and improves its preferred objective?
3. At equal new-simulation cost, which method builds the best feasible power/performance trade-off set?
4. When historical data acquisition and model preparation are charged, how much reuse would repay the investment?
5. Would any benefit justify retaining SAC, or could a graph surrogate or a shared functioning-design screen
   provide it without policy learning? The primary matrix compares complete systems; the follow-ups isolate these
   questions more closely and are not included in its launch budget.

Separate two panels. **A: fixed target** measures feasibility and one preferred objective. **B: Pareto search**
measures a two-objective frontier. A first-feasible score alone cannot judge a frontier optimizer, and one
fixed-preference SAC run is not an adequate frontier baseline. Never merge these into one winner score.

The primary transfer claim is deliberately limited to **reuse on the same physical circuit with compatible
measurements**, including changed limits/preferences. This is a retrospective development suite, not evidence of
unseen topology or PDK transfer. Do not silently add mixed-topology data to SAC that the vector BO models cannot use.

Use **BO as the provisional engineering reference for a new expensive sizing task**, with Pareto MOBO considered
when a frontier is the required output. This is a starting judgment, not a predetermined experimental result or an
instruction to change the application default. The archive-reuse experiment asks whether SAC earns its additional
training and maintenance cost against **matched transfer BO**, not merely against scratch SAC or cold TuRBO.
Existing favorable SAC results and newer Round 3 results remain relevant evidence; their unequal source pools do
not answer this controlled question. Do not characterize the previous research as invalid or assume BO must win.

The source chat identifies three distinctions to preserve throughout the report:

- **Representation versus search:** graph inputs and variable-size parameter heads are capabilities, not evidence
  that RL is the best search algorithm. BO can use learned representations too. A SAC/vector-BO comparison alone
  cannot attribute a difference to the graph encoder; section 5.1 defines the missing graph-BO diagnostic.
- **Immediate proposals versus control:** these SAC runs use `gamma=0` and propose whole designs. They do not test
  delayed-reward planning. Measure any benefit of direct actor proposals after counting updates and pretraining.
- **Functioning-design screening versus calibration:** an RF classifier can bias search away from nonfunctional
  designs. Workbench Calibration proposes reward scales/initial alpha; probability calibration is another distinct
  operation. Neither a classifier's prediction nor simulator completion proves every performance limit is met.

The RF paper's abstract, as read in the source chat, reports 150 feasibility-discovery calls and 123 optimization
calls, **273 in total**, with unstable samples changing from 40/70 to 0/80. Treat these as that paper's reported
samples, not a stability guarantee or a fair speed comparison with GATOR's different circuit/bench. Its exact forest
and validation recipe were not verified from the full text; the proposed RF study is inspired by it, not a replication.

## 2. What exists, and what must be built

Read `CLAUDE.md`, the analog-optimizer skill's evaluation rules, `docs/performance-measurement.md`, and the current
source before implementation. Preserve other sessions' edits and active runs.

| Existing component/evidence | Use or limitation |
|---|---|
| `src/gator_workbench/bayes.py` | Torch-only TuRBO-1; scalar reward; new search per run. Current `max_fit_points=600` and restart behavior do not constitute persistent archive transfer. Preserve the ordinary baseline. |
| `src/gator_workbench/pretrain.py` | Archive identity/input checks, reward migration, target-limit relabelling, sampling and offline training. Existing target relabelling changes limits, not arbitrary objective equations or preference directions. |
| `src/gator_workbench/calibration.py` and `frontend/src/launch.ts` | Standalone Calibration uses 64 random designs to propose scales/initial alpha. `prepare(random_only=True)` disables transition archives; these records are not automatically SAC-replay eligible. |
| `src/gator_workbench/schema.py::PerformanceTarget` | One `direction_after_feasible` objective per configuration. Use several fixed goal configurations for the Pareto SAC/TuRBO portfolios. |
| `src/gator_workbench/storage/{dataset,tables}.py` | Measured metrics, executed parameters, validity masks, evaluation IDs and simulator-job records. These are the source of truth. |
| `src/gator_workbench/budget.py` | Separate candidate charges, physical launches, failures, retries, cache hits and first-feasible accounting. Reuse it; add a shared portfolio budget. |
| `artifacts/local/reviews/turbo-transfer-2026-10-19/results.{md,json}` | Earlier same-task BO/RL/hybrid comparisons; the RL-initialized BO arm is not a BO surrogate trained on a matched archive. |
| `thesis/figures/data/round3-results.json` and Round 3 repeat records | Newer RL reuse evidence. Existing models saw a much larger archive and are not eligible primary checkpoints for the smaller common pool below. |

New work belongs in workbench modules and experiment tooling outside `src/analog_optimizer/`. Do not modify
SAC, its action semantics, the core reward implementation or the optimizer digest for this study. New experiment
configurations and audited derived views are allowed implementation tasks; original evidence remains immutable.
No current UI/default change is needed. New script/CLI names below describe deliverables, not existing commands.

## 3. Cases and objective definitions

Use three existing circuits with actual archived measurements. Freeze the exact reference configuration files,
task identities, netlists/PDK identities, measurement programs, starting dimensions, legal parameter mappings,
grids, runtime and input-view hashes in `cases.json`. Do not trust a mutable task display name alone.

| Case / historical task | Panel A preference | Panel B objectives | Four portfolio goals for Panel B |
|---|---|---|---|
| Published LDO, `real:agentic_ldo_pub` | Minimize `power_w` under its saved hard limits | Minimize power; maximize `psrr_db` at the existing 1 kHz measurement | Minimize power with PSRR floors 50, 55, 60, 65 dB |
| Published amplifier, `real:agentic_fc_pub_far` | Minimize `power_w` under its saved hard limits | Minimize power; maximize `ugb_hz` | Minimize power with UGB floors 30, 36, 45, 60 MHz |
| DFFRX1, `real:dffrx1_t2` | Minimize `energy_int_j` under its saved hard limits | Minimize internal switching energy; minimize `tcq_mean` | Minimize energy with mean-delay ceilings 1.0, 0.9, 0.8, 0.7 times the saved base ceiling |

The DFF energy definition is the recorded `m_energy_j - 2e-14`; delay is the recorded average of four clock-to-output
delays. Keep these definitions and the existing individual-delay, logic-level, setup, leakage, capacitance and
area-proxy constraints. The last is a proxy, not measured layout area. Verify the stored equations and units.

All original hard limits remain active in both panels. The additional portfolio limits only tighten the second
objective's existing limit. For the MOBO frontier and all reporting, feasibility uses the **common base limits**;
the tighter portfolio thresholds do not redefine another method's pass. Portfolio thresholds are predefined here,
not selected after looking at competing runs. An unreachable strict threshold stays in the result.

The known telescopic OTA is excluded from the primary suite because its initial design already passes. Do not
replace a difficult case with it after seeing failures. If a listed measurement/bench is unavailable or incompatible,
resolve the case definition before freezing rather than inventing data or silently substituting a task.

Panel A and portfolio scalar rewards use the existing compressed reward, `worst_spec_share=0.5`,
`objective_shape=compressed`, `objective_weight=1`, `margin_weight=0`, `nominal_gate_band=0.5`.
Set the single preferred metric's direction explicitly; hold all scales and hard-spec weights fixed across methods.
The zero margin bonus makes the preferred objective interpretable; it is an experiment configuration, not a change
to production defaults. These runs are consequently not exact reruns of older margin-bonus experiments.

## 4. Freeze one common archive bundle per circuit

### 4.1 Identity, eligibility and selection

Inventory saved runs read-only using `DatasetReader`, recorded replay and the existing archive/input-view checks.
Freeze a source cutoff before this campaign. Exclude active/non-quiescent runs and every run of this new campaign.
Use only real nominal observations with the same circuit lineage, PDK/model sections, operating conditions,
measurement equations/analysis settings and compatible physical parameter domain. Different target limits are
allowed; different loads, supplies, benches or PDKs are not interchangeable observations of the same function.

For each case, build a source-training bundle with **at most 600 distinct executed physical designs**, selected by
a fixed hash order with seed 1729, without ranking by feasibility, reward, method or final quality. Select reusable
transition records and include their observation dependencies before enforcing the cap: current-state and
next-state measurements visible to SAC must also be available in the common BO bundle. Store both proposed actions
and executed parameters; the GP input is the executed physical design mapped to the frozen target domain.
Never assign a measured outcome to an unexecuted proposal after quantization/projection.

Deduplicate by physical design plus simulator/measurement context, not normalized action or task name. Preserve
repeat measurements and provenance separately; count each underlying acquisition once. Retain failed designs and
partial measurements with masks. Do not select only successful or SAC-generated records. Records that BO can use
but the current SAC replay cannot reconstruct belong in an exclusion inventory, not a BO-only primary supplement.

Create a separate source validation partition from eligible historical episodes/runs, with physical-overlap and
transition-dependency checks so no held-out design's measurements enter any training view. Use the same partition
for every method. Shared repeated starting designs must not masquerade as held-out examples. If a clean validation
partition cannot be constructed, resolve that before training; do not claim episode-only separation proves
independence. Freeze the selection before fitting any model. No smaller outcome-selected replacement pool.
Group near-duplicate sweeps/trajectories when possible and report residual similarity between partitions; distinct
physical hashes alone do not establish out-of-distribution generalization. Reserve this validation partition for
final diagnostics. Any fitting, probability calibration or parameter selection must use grouped inner splits of
the common training bundle, never its held-out labels or new campaign outcomes.

The 600-design cap bounds this first matched study. Record the eligible archive total and excluded coverage; do
not describe it as the full 187,407-transition archive. Fewer than 600 eligible designs is acceptable if every
primary method receives the same actual bundle and the shortfall is recorded before launch. Below 128 distinct
training designs, treat the case as unqualified for this protocol and resolve it before dispatch.

### 4.2 Equal access and transformations

Publish `source_manifest.json`, a source-ID ledger, partition membership and a checksummed common observation
table. Each method's training record must enumerate the exact underlying IDs it consumed. All four transfer arms
receive the same source-training bundle and metadata; the deliberately cold control receives none.

Recompute scalar rewards and feasibility for each of the four fixed goal configurations from raw recorded
measurements. Reconstruct both transition observations consistently; do not reuse historical scalar rewards after
changing goals. Reuse the compiler/spec/reward machinery. Extend the workbench's derived-view preparation only
where needed to set the selected preference direction, with exact-equivalence checks against a freshly compiled
configuration. MOBO uses the same raw objective/constraint outputs, not a fabricated inverse of scalar reward.

Missing outputs stay missing. Model valid outputs only; maintain an explicit validity/feasibility mechanism for
failed simulations. Infrastructure failures are not evidence of a physically bad circuit. No zero-filled gain,
power or delay, no imputed successful design, and no discarded charged failure.

All transfer methods may retrieve known designs from the common archive before any new simulation. Record the initial
feasible archive, its Pareto frontier and hypervolume `HV0`. **If the archive already meets the target, first-known
feasibility is zero new calls for every transfer method.** Report this separately from the first freshly simulated
passing design; do not hide the archive solution to manufacture a speed advantage. A known-target case then tests
improvement and confirmation cost, not discovery from nothing. Qualification data, if newly collected, is shared
with all methods and charged separately; record its contribution to the initial frontier too.

### 4.3 Archive-only functioning labels and RF diagnostic

Add this diagnostic during preparation, with **zero new physical calls**. It does not filter the primary archive,
change primary initialization or install screening in a primary optimizer. Freeze a per-case label specification:

| Label | Meaning and handling |
|---|---|
| Measurement valid | Required analyses/metrics were obtained; retain per-output masks for partial results. |
| Functioning | Recorded, circuit-specific operating checks pass independently of the optimization preferences; distinguish this from measurement availability. |
| Target feasible | All frozen base performance limits pass; this remains the optimization success criterion. |
| Unknown / infrastructure error | Missing evidence or failed execution infrastructure; do not label as a physically nonfunctional circuit. |

For example, an inactive regulator drawing little current must not become a good functioning example just because
power is low. Freeze any available regulation/logic/operating checks from the bench before fitting. Do not invent
stability labels from unrelated metrics or claim stability where the archive lacks the needed analysis. A missing
delay can establish measurement invalidity without establishing its physical cause. Record separate counts for each
category; define the RF's usable-design label from the checks actually available and name that scope precisely.

Fit only on the common up-to-600-design training bundle, with executed dimensions and known pre-simulation context
as features. Candidate measurements, reward, operating points and failure outcomes are labels or audit fields,
never prediction inputs. Standalone 64-design Calibration tables may inform a separate descriptive audit, but do
not add them to this training pool unless full replay eligibility and common access under section 4.1 are proved.
No validation label or additional calibration measurement may leak into training under another name.

Use one preregistered small classifier recipe: 200 trees, maximum depth 8, minimum leaf size 5, all input features
eligible at a split, bootstrap enabled, no class reweighting, one CPU thread, and the paired source seed. Freeze the
library version and exact semantics in the manifest. These are proposed study settings, not the paper's settings.
Raw forest vote fractions are scores, not assumed calibrated probabilities. The first ablation does not fit a
probability calibrator; any later calibrator must use grouped inner training folds and have a separate frozen recipe.

Report class prevalence, confusion counts at a fixed score of 0.5, functioning-design recall, false rejection of
measured functioning and target-feasible designs, Brier score/reliability with bin counts, and comparison with the
training-prevalence constant predictor. Report numerator/denominator and uncertainty, not just accuracy or AUROC.
Use the untouched historical validation partition once for these diagnostics. If labels, independent groups or
both classes are insufficient, mark screening unqualified; do not collect an unbudgeted calibration set to fix it.
An offline improvement does not establish an online simulation saving.

Retain the primary fixed scales, limits and initial alpha 0.01. No method gets per-arm recalibration. If a later
study derives rank-based target limits, use measured functioning designs and freeze those limits before optimizer
comparison; never move the present targets after RF screening. The LDO1 port's inactive-design calibration bias is
motivation for this rule, not evidence that this study's published LDO has the same defect.

## 5. Algorithms and frozen settings

| ID | Method | Source data | Panel A | Panel B |
|---|---|---|---|---|
| T0 | Ordinary TuRBO-1 | None, except shared qualification information | Cold control, 800-call cap | Not in primary panel |
| T+ | TuRBO with archived observations | Common bundle | One scalar search, 800 | Four epsilon-constraint searches, 200 each |
| M+ | Constrained Pareto MOBO, qLogNEHVI | Common bundle | Two-objective search under base constraints, 800 | One two-objective search, 800 |
| RA+ | Pretrained GraphGPS-SAC, adapt | Common bundle | One target, 800 | Four target-conditioned clones, 200 each |
| RF+ | Same pretrained GraphGPS-SAC, frozen | Same checkpoint as RA+ | No updates, 800 | Four target settings, 200 each; no updates |

Here **RF+ means frozen RL**, as in the original plan. Write the classifier as **RF-screen** throughout manifests
and reports so it cannot be mistaken for an optimizer arm.

**T+ is data transfer, not an RL-proposal warm start.** Import the source observations without incrementing new-call
budgets, consuming optimizer asks or triggering trust-region success/failure updates. Fit target-relabelled reward
and initialize from the best source design under that reward. Preserve the ordinary TuRBO region update rules.
Retain source information across restarts; do not let `start=len(X)` silently remove the prior archive.
For this bounded study, both BO arms must retain all up-to-600 source designs and up-to-800 online observations in
their available fitting data. Increase the experimental fit-data ceiling to at least 1,400 plus shared qualification
rows; no hidden newest-600 truncation. T0 uses the same experimental fitting ceiling but no archive.
This is a named, versioned TuRBO archive-reuse variant; report the differences from current production TuRBO.

**M+ is one specified algorithm.** Use BoTorch constrained `qLogNoisyExpectedHypervolumeImprovement`, with separate
ARD Matern-5/2 GP models for objectives/constraint outputs and an explicit simulation-validity treatment. Preserve
partial-output masks. Use batch size 4, fixed acquisition optimization settings/seeds and recorded observation-noise
assumptions. Freeze transforms, constraint signs and the reference point before target results. Do not also try
qNEHVI, MORBO and several kernels and report the winner. MORBO is a separately budgeted future arm if this global
GP method cannot meet the offline runtime/memory gate; it is not an unreported fallback during the campaign.

**SAC uses one architecture chosen now: GraphGPS**, with the existing transferable input build, family vocabulary
and mask rules. Freeze an exact compatible runtime and dependencies. Train a fresh model for each circuit and
pretraining seed on that circuit's common source bundle, balanced across its four goal views. Use 20,000 updates,
batch 8, learning rate 0.001, gamma 0, initial alpha 0.01, tau 0.005, and the existing GraphGPS 48/4/4 plus RWSE recipe.
Select the final fixed-budget checkpoint; do not pick an epoch by target results. Archive validation diagnoses
fitting and numerical health, not unseen-circuit generalization. No Round 3 checkpoint may replace this model.

RA+ loads the matching weights with fresh optimizers, reset alpha 0.01, empty target replay, eight updates per newly
collected transition, replay capacity 10,000 and otherwise matched online settings. RF+ samples the same actor with
all weights frozen and no updates. Source rehearsal is off. Record actual coverage of the source bundle, fitting
time, update time and peak memory; equal data does not mean equal compute. Nine source trainings are required:
three circuits times three pretraining seeds. RA+ and RF+ share each source checkpoint; Panel A and B start fresh
from it rather than carrying learned target weights between panels.

No hyperparameter optimization on target runs. Use synthetic functions and an explicitly separate development set
to freeze acquisition settings and implementation choices. Preserve all attempted configurations and their costs.
Compatibility with the pinned torch/PyG versions must be proved in an isolated environment; never upgrade the live
environment or relax checkpoint checks to install BoTorch/GPyTorch.

### 5.1 Separately budgeted graph-prior TuRBO diagnostic

Prepare **TG+**, a graph-prior variant of T+, to compare vector transfer BO, graph transfer BO and graph SAC.
Use a source-trained GraphGPS mean `m(G,x,goal)` plus a Matern-5/2 residual GP on the same normalized executed
parameter vector as T+: fit the residual `reward - m(G,x,goal)` and add the mean back for predictions. Keep the T+
trust-region/acquisition rules, archive retention, parameter projection, start, initialization and 800-call cap.
This proposed arm tests a particular graph prior; it is not a reproduction of KATO or a graph-Pareto method.

Build candidate graphs from known topology, legal proposed dimensions and fixed context/goals. Mask all candidate
post-simulation measurements/OP features, for source fitting and online queries alike. Never fill a candidate graph
from its archived outcome, or attach measurements from another design without identifying their context. Implement
the design-only encoder adapter outside `src/analog_optimizer/` and verify that unavailable features cannot leak.

Train the GraphGPS 48/4/4 RWSE encoder and a scalar linear mean head on the same source bundle/four goal views using
masked-input, supervised scalar-reward MSE, 20,000 updates, batch 8, learning rate 0.001, Adam and source seeds 0/1/2.
Freeze training-only normalization, final checkpoint and mean before target search; refit only the residual GP
online. Count all nine additional source-model trainings and prediction/fitting time. Do not import a much larger
Round 3 model or silently substitute an SAC-trained encoder. Failed rows use the same well-defined scalar reward
as T+; infrastructure errors are not fabricated physical outcomes.

Run TG+ in Panel A against its existing paired T+, RA+ and RF+ controls, with identical source IDs and budgets.
It can show whether this graph prior improves vector TuRBO and competes with the learned policy. Different training
objectives and available observation inputs still prevent a clean attribution to graph structure alone; a matched
non-graph neural prior or a full representation-by-search factorial would require another protocol. With fixed
topology per case, neither result proves variable-topology generalization. If implementing the mean changes the
acquisition/ranking semantics unexpectedly, resolve and freeze that before launch rather than changing T+ in place.

### 5.2 Separately budgeted RF-screen comparison

Keep every primary arm unscreened. Prepare paired screened versions **T+/screen, M+/screen, RA+/screen,
RF+/screen** for Panel A using the same frozen per-case/per-seed classifier from section 4.3. Use their primary
counterparts as controls. All four methods receive screening; do not selectively add it to rescue one method.
The classifier stays frozen online, so it cannot ingest another arm's target results.

Keep the eight common initialization designs untouched. Subsequently, generate at most four base-method proposals
per available simulation slot without treating any as executed. Select exactly one from each slot's own pool;
for SAC, preserve the originating lane, current observation and action-to-transition mapping. Never select a proposal
conditioned on another lane's state. With probability 0.2 take that slot's first base-method proposal, otherwise
sample within its pool with weight `RF_score + 1e-6`. For `q` slots the overall cap is `4q` internal proposals and
`q` selected candidates. Freeze BO batch/slot conditioning, order, seeds, duplicate handling and any short-pool
fallback before dispatch; joint batch acquisition requires an audited slot-preserving adapter. Do not shrink the
legal parameter bounds.
The bypass preserves base-method exploration; it does not guarantee uniform coverage of the physical domain.

Only selected designs become charged candidate evaluations and pending simulator jobs. Internal proposals are
logged as proposal-compute work, not simulations; cap them as above and include their time. Creating/discarding
them must not advance TuRBO success counters or SAC environment state. Store only actually executed actions and
measured outcomes in replay; no pseudo-rewards, fake observations or learning updates from RF scores. Verify this
contract with each proposer before launch. Save pool-selection RNG/state for exact resume.

Compare avoided invalid/nonfunctional calls, false-rejection evidence, cost to the same target/improvement,
feasible objective quality and end-to-end time. Preserve measured feasibility as the authority. This evaluates the
whole screening wrapper, including extra proposal compute; it does not isolate classifier benefit from larger
candidate pools. RF-screen does not replace MOBO's constrained acquisition or any method's existing invalid-output
handling. Any claim about RF probability calibration needs the separate evidence in section 4.3.

## 6. Fair online scheduling and portfolio accounting

Use replicate pairs `(pretrain_seed, rollout_seed) = (0,101), (1,102), (2,103)`. BO uses the corresponding rollout
seed. This is three independent paired replicates, not a fully crossed nine-run confirmatory design. The journal
study may later cross them; do not give this pilot the stronger interpretation.

Every method gets the same immutable start, legal domain, nominal testbench, four isolated simulator lanes, fixed
eight-design initialization and observation validity rules. Generate and freeze the initial legal designs by seed
before running a method; include necessary baseline/reset work in the limits. Keep the existing episode/reset
contract common to the methods, and report its cost. All target observations are local to that arm; never share
new results between competing methods or between distinct searches in the panels. Archive imports are not new
simulations. M+ has exactly the same search definition in A and B: execute it once per case/replicate and reuse that
trajectory for both analyses, with explicit manifest aliases. It is one observation, not two independent repeats.
Its scalar quality and Pareto quality are both scored after the run; neither analysis steers the other methods.

For Panel B, T+, RA+ and RF+ receive **800 total**, not 800 per preference. Each of the four goal configurations has
a 200-candidate/200-launch sub-cap. Four initializations/resets are included in that total. Keep at most four
simulator lanes across the entire portfolio, not four per child. Rotate the fixed goal order across replicates.
Union every child's measured feasible designs, and evaluate that union against the common base constraints.

For the primary portfolio recipe, each child starts from the same source bundle/checkpoint and keeps its own online
state. There is **no cross-child online learning or data exchange**. This makes a simple, auditable baseline with
fixed allocations; disclose that MOBO can use its whole online history jointly. It tests these specified methods,
not the best conceivable shared-data or preference-conditioned RL optimizer. A shared-online-data portfolio is an
optional future ablation and must not be introduced only for a losing method. Source data is equally available to
all children and its acquisition cost is counted once per portfolio, not four times.

All arms run their full allowed budgets even after a first pass, to expose quality/feasibility curves. Stop at the
first of 800 charged candidate evaluations or 800 counted physical launches (200/200 for a child). Pre-launch
failures consume candidate budget; retries consume launch budget; neither is refunded. No automatic retries by
default. For a nominal bench that requires more than one simulator invocation per design, the 800-launch limit
still applies and all arms receive the same bundle reservation rule. Freeze that fact before launch; do not call
800 multi-analysis invocations "800 equivalent designs" without defining the bundle.

Record first-pass charges including in-flight work, completed-design ordinal, counted launches and confirmed
launches separately. Drain/account for already launched jobs at a stop. Never use a fictitious 801st success for
an unsuccessful run: retain right censoring. A repeated existing source design is a cache hit only if its full
physical/measurement identity matches; it consumes proposal budget but no new launch, is deduplicated in quality
metrics and receives no duplicate observation weight. Final confirmation always bypasses the cache.

Run matched arms serially on a quiet host for valid wall-time comparisons, with one CPU learner thread and identical
Spectre resources. Counterbalance method order by case/seed. Do not interrupt the active Round 3 queue. If busy-host
parallel execution is later chosen, report simulation-count comparisons and label timing observational; do not
claim controlled wall-time speedups. Log model fitting/acquisition, learning, preparation, simulation, parsing,
queue wait and end-to-end time separately. A call ratio is only an estimate of simulation-time savings.

## 7. Outcomes and decision rules, fixed before execution

### Panel A

- Initial archive feasibility and quality at zero new calls; first freshly validated passing design; hard-pass
  probability by 100/200/400/800 calls; censored first-pass counts and time; final best preferred objective subject
  to all base constraints; full per-spec physical results and failure categories.
- If every transfer arm already knows a passing design, discovery speed is tied at zero. Report fresh confirmation
  cost and objective improvement over the common archive incumbent. Do not exclude that case silently.
- Use restricted mean calls-to-feasibility through the common budget and all three individual runs, alongside
  medians. Treat non-passing/infrastructure-stopped arms explicitly; do not average only successful runs.

### Panel B

- Feasible nondominated set, hypervolume `HV(n)`, gain `HV(n)-HV0`, and area under that gain curve against actual
  calls. Also report objective ranges, common-goal attainment and raw Pareto points, deduplicated by executed design.
- Use two objectives only. Fix objective orientation and scales from physical definitions/source training data.
  Set the hypervolume reference point to the base objective constraint limits in transformed coordinates (e.g.
  worst acceptable power and PSRR/UGB/delay). Verify signs on a hand-calculated two-dimensional fixture. Never
  derive the reference or normalization from the union of final test outputs. Boundary-only points may have zero HV.
- No feasible point means zero HV; retain the feasibility result. Do not divide by `HV0` when it is zero. Report
  the complete source-plus-online frontier and the incremental contribution of online designs separately.
- Re-score the MOBO observations for all four portfolio goal thresholds; it need not run four extra searches to
  receive this information. Threshold attainment is computed identically for every method's union of observations.

### Cost and recommendation

Report historical acquisition calls once per distinct source bundle, the broader archive acquisition cost if a
larger archive had to be collected to obtain it, qualification calls, offline compute, tuning, target calls,
failures/retries, confirmation and wall time. Provide both existing-archive marginal cost and total-build cost.
Do not assume historical data are free for BO but charge them to RL, or the reverse.

For a reusable model, show `source_cost + preparation_cost + sum(target_cost)` versus the alternative over repeated
tasks. Express call costs and compute/time costs separately unless a measured conversion is available. A break-even
task count is a scenario based on observed savings, not proof that new tasks will behave identically.

Practical development rule: recommend replacing an incumbent method only when it reduces median relevant search
cost by at least 20% on at least two of three cases, without fewer successful seeds or a greater than 5% loss in
final feasible objective quality on any case. If the incumbent objective is zero/nonpositive, use the frozen
normalization scale rather than an undefined percentage. For archive-feasible cases use cost to a predeclared
source-relative quality-improvement threshold instead of first feasibility: for these minimized objectives use
`q_goal = best_source_q - 0.05 * s_q`, where `s_q` is the positive frozen objective normalization scale. Freeze this
in `cases.json` before dispatch and include failures to reach it; do not relax it if all methods fail.

For the RL decision, **T+ is the matched archive-reuse reference**; outperforming T0 alone is insufficient.
Report RA+ and RF+ separately rather than selecting the better variant after seeing each seed. If neither clears
the practical rule against T+, retain BO as the general engineering recommendation and report any narrower,
replicated circuit-specific advantage. Do not expand RL pretraining solely because it loses this comparison.
If TG+ is elected, compare it with the same T+ reference and ask whether SAC adds value beyond that graph prior.
If a graph prior helps but SAC does not, retaining graph modeling while using BO is a legitimate outcome.

Recommend M+ for the Pareto mode only if median final feasible HV is at least 10% higher on at least two cases,
with no more than 5% HV loss on the remaining case and no reduction in base-feasibility success. When a comparator's
HV is zero, report absolute gains and feasibility; do not manufacture an infinite percentage. Show the full
trade-off table even if these practical rules fail. Three seeds support a development choice, not a universal or
statistically established superiority claim. Do not cherry-pick encoders, tasks, budgets, seeds or frontier regions.
State explicitly when evidence supports no change. RF-screen adoption requires savings under the same cost/quality
rule against each arm's unscreened counterpart, with failures and extra proposal time included; predictive accuracy
alone is not grounds to deploy it. Keep nominal functioning, base feasibility and PVT/yield claims separate.

## 8. Budget and stages

The caps below assume one physical nominal launch per candidate; the reservation audit must confirm this.

| Stage | Matrix | Maximum new search launches |
|---|---|---:|
| Offline preparation | Archive inventory, derived views, nine SAC source trainings, GP fits, mock checks | 0 |
| A, all three replicates | 3 cases x 5 methods x 3 replicates x 800 | 36,000 |
| B, additional searches | 3 cases x 3 portfolios x 3 replicates x 800; M+ reuses A | 21,600 |
| **Primary search total** | **81 analysis cells, 72 distinct method/case/replicate searches** | **57,600** |
| Shared physical qualification ceiling | At most 5 nominal launches per case, exact needs frozen first | 15 |
| Independent final confirmation | At most 3 distinct finalists per search x 72 searches x 1 nominal launch | 216 |
| **Maximum primary physical budget** | **Including qualification and confirmation** | **57,831** |

Stage seed 0 for **every method and every case in both panels** first: 19,200 search calls, up to 72 confirmations
and 15 qualification calls, maximum 19,287. Correctness/resource gates can stop the campaign; an unfavorable result
cannot selectively remove an arm. Once a complete-campaign budget is authorized and these gates pass, finish seeds
1 and 2 for the whole matrix: 38,400 search calls plus up to 144 confirmations. All nine source trainings should
be frozen before the first real comparison; do not tune seed-1/2 models after seed-0 outcomes.

The 72 searches are parent-level budget units. Panel A has 45 ordinary run jobs; Panel B adds 27 portfolios of four
200-call child jobs, giving 153 online run jobs in total. The nine M+ analysis aliases create no extra job. The
dispatcher must validate parent and child totals, not multiply the 800-call budget by the child count.

The per-search final confirmation allowance is identical. For every search, select the best feasible design for
each of the two objectives and a middle trade-off closest to the midpoint between those extremes in the fixed
normalized coordinates (break ties by canonical design hash). The preferred-objective extreme supplies Panel A's
best-design confirmation. M+ uses this same set for both panels. Select before rechecking. Reuse one confirmation
for an identical selected physical design only with explicit
provenance and equal rules; no freed budget is reassigned. Nominal confirmation does not establish PVT robustness
or yield. If an analysis package uses multiple launches, recalculate the complete ceiling before authorization.

Optional, excluded from the primary ceiling: add cold MOBO and scratch GraphGPS-SAC to Panel A to isolate the
transfer effect within every algorithm: `3 x 2 x 3 x 800 = 14,400` search launches plus at most 54 confirmations,
total 14,454 extra.

The source-chat refinements have these **separate** ceilings; they are not silently added to the primary request:

| Extension | Added matrix / search launches | Added confirmations | Maximum added launches |
|---|---|---:|---:|
| Archive-only RF diagnostic | Same existing source/validation records; no new acquisition | 0 | **0** |
| TG+ graph-prior TuRBO, Panel A | 3 cases x 3 paired seeds x 800 = 7,200; 9 new searches | 27 | **7,227** |
| RF-screen, Panel A | 4 transfer methods x 3 cases x 3 paired seeds x 800 = 28,800; 36 new searches | 108 | **28,908** |

Primary plus both physical extensions is at most **93,966 launches**: 93,600 search + 15 shared qualification +
351 confirmations, across 117 distinct searches. It excludes the optional cold-MOBO/scratch-SAC controls. The
extensions reuse eligible primary controls and qualification records; they do not combine RF-screen with TG+ or
add Pareto portfolios. For each extension retain the same three-finalist confirmation rule. Elect extensions and
freeze their recipes before reading primary target outcomes, then finish the complete elected matrix; do not pick
only favorable circuits. If added later with changed runtime/conditions, budget new matched controls/qualification
before launch and label timing appropriately instead of treating the old controls as automatically comparable.

There is **no additional 64-call Calibration or 150-call discovery allowance** in any of these ceilings. New
calibration/discovery calls must consume the same per-search 800-call budget, or be shared preparation visible in a
revised total before authorization. If shared data are used, every competing eligible method gets the same data and
their contribution is recorded at initialization. Do not compare "123 optimization calls" with another method's
all-inclusive count. RF labels and supervised graph fitting from existing data cost compute but no new simulation.

A 1,600-design source-size study, MORBO, RGCN/CircuitGPS arms, cross-topology/PDK transfer,
PVT and Monte Carlo require separate frozen protocols and budgets. Do not start them because one arm underperforms.

## 9. Implementation order and acceptance gates for Claude

1. **Read-only inventory.** Produce case/source manifests, exact compatible source counts, duplicate/failure/exclusion
   inventories and archive-only starting frontiers. Check whether the first-feasible question is already answered
   at zero cost. Include all underlying source dependencies, not only the selected replay's next states.
   Audit Calibration/replay eligibility, measured functioning labels and the source chat's distinct claims. Do not
   add a screening or graph-prior arm to the launch manifest merely because this document describes it.
2. **Derived data and budget contracts.** Build audited common parameter/metric records, four goal views, common
   initialization lists, portfolio aggregation and global/child launch reservations. Reproduce recorded rewards
   first, then prove new rewards match the compiled target configurations without altering stored observations.
3. **T+ and M+.** Implement archive imports, persistent source use across TuRBO restarts, multi-output constrained
   qLogNEHVI, legal mixed/discrete projection and full save/restore. Store GP data/parameters, trust regions,
   acquisition state, RNGs, pending work and ledgers; no fresh-budget restart after a crash. Keep source data immutable.
4. **SAC source models and portfolios.** Use isolated settings/output roots and compatible frozen runtime copies.
   Train/reload the nine source models, validate finiteness and pool identities, then prepare independent adapt/frozen
   child configurations. Enforce four simulator lanes across the whole portfolio.
   Ensure that a baseline or cache hit cannot accidentally trigger extra SAC updates or free budget.
5. **Offline acceptance.** Verify common source-ID membership; missing/failure handling; source-to-goal rescoring;
   no validation/target leakage; exact executed-parameter/outcome association; hypervolume orientation/reference;
   portfolio union and shared caps; source persistence after restart; resume/RNG/ledger equivalence; zero-cost
   archive-feasible reporting; and the 800/200 limits under pending jobs, failures, retries and duplicates.
   Use existing tests plus meaningful focused fixtures and synthetic constrained two-objective functions; all
   synthetic evidence is labelled. Never substitute synthetic outcomes for real-circuit results.
   Produce the RF diagnostic without extra simulations. For elected extensions, prove candidate-feature masking,
   grouped train/validation separation, RF pool accounting and originating-state/replay integrity, no hard domain pruning, and TG+
   supervised-mean/residual-GP prediction parity. Freeze all recipes before primary target outcomes are inspected.
6. **Resource and code freeze.** On archived/mock inputs, measure GP fitting/acquisition with the full allowed
   source-plus-online table, SAC learning, peak memory and serialized state. Freeze numerical settings and dependency
   lock files before any target outcome. If memory/time is infeasible, revise the protocol visibly before dispatch,
   not by silently discarding source rows or switching methods. Produce a machine-checked 81-analysis-cell,
   72-search matrix and budget, including the nine explicit shared-M+ aliases.
7. **Reviewable launch package.** Supply exact planned commands, immutable config/checkpoint hashes, simulator
   reservation totals, session/cell restoration rules and a resume recipe. Obtain authorization for the bounded
   physical stage; this document alone is not authorization. Use only a free authorized Virtuoso session; never
   change another queue, disconnect it, replace its runtime, or overwrite an original schematic.
8. **Execute and report when authorized.** Audit every cell from committed tables and simulator-job receipts,
   check restorations, run final confirmations, publish per-seed data and panel-specific conclusions. A stopped
   run's costs and reason remain in the denominator. Report any protocol deviation before interpreting outcomes.

Keep new experiment code in a dedicated workbench/experiment package and add its function map entries/tests when
implemented. Do not edit pinned historical `examples/` or evidence. Small tests may run beside the existing queue
under the repository's resource rules; full suites and timing runs wait for a suitable machine state.

## 10. Required evidence package and handoff completion

Suggested experiment root: `artifacts/local/reviews/bo-mobo-rl-archive-2026-10-21/` (create during implementation).
Keep experiment reports outside run directories; ordinary runs retain the existing data-only output contract.

- `protocol.json`, `cases.json`, `source_manifest.json`, source/validation ID ledgers and exclusion report;
- raw immutable source references, derived-view hashes, zero-call archive frontiers and reward-parity checks;
- functioning/validity/target-feasibility label definitions, Calibration exclusion ledger, RF diagnostic settings,
  held-out prediction scores and denominators; explicit evidence gaps where archive labels are unavailable;
- dependency locks, runtime/source hashes, exact GP/acquisition/SAC settings and resource checks;
- pretraining requests, per-seed checkpoints, consumed-source coverage and offline qualification;
- 81-analysis-cell/72-search matrix, shared-M+ aliases, portfolio-child definitions, common initialization IDs,
  launch-budget calculation and commands;
- per-run/portfolio candidate and simulator-job ledgers, cache/duplicate records, status, failures and restore audits;
- Panel A and B summaries in JSON/CSV, each seed's curves, final physical metrics and independently confirmed designs;
- marginal/total cost and conditional amortization tables; explicit scope limits and practical-rule verdicts.
- for elected extensions, classifier/graph-mean training manifests, checkpoints, extra compute, proposal-pool
  ledgers, matched-control identities and amended total budget; keep RF+ and RF-screen identifiers distinct.

Completion means all authorized cells and checks have a recorded disposition, source data remain unchanged, costs
reconcile to actual jobs, and the report recommends a fixed-target default and a Pareto-mode default separately.
A favorable offline critic error, a passing mock test, or a partial seed-0 matrix is not a completed circuit comparison.
The recommendation must separate the value of archive reuse, graph representation, policy learning, RF screening
and Pareto search; report untested factors as unresolved rather than assigning all benefit to RL or to BO.

## 11. Method references

Primary sources checked on 2026-10-21; pin actual implementation versions during preparation.

- Refinement provenance: Codex chat **Compare random forest calibration**, ID
  `01a15d81-cd22-7560-b946-457fbab6ab9f`, six turns read on 2026-10-21. This records the motivation, not new
  experimental evidence. Its abstract-only reading of the [staged LDO MOBO paper](https://ieeexplore.ieee.org/abstract/document/11727623)
  motivates RF-screen; full classifier settings and validation details remain unverified. Direct IEEE retrieval
  during this refinement was unavailable, so the reported sample counts above retain that attribution.
- [KATO](https://arxiv.org/html/2404.14433v1), especially sections 3.2-3.4: transfer BO can align differing parameter
  spaces and decline unhelpful source transfer. Its Pareto search over acquisition criteria is not, by itself,
  a circuit-performance Pareto-front experiment. It motivates a later cross-topology/PDK benchmark, not a claim
  that the primary same-function T+ or proposed TG+ implements KATO.
- Local calibration implementation: `src/gator_workbench/calibration.py`; its 64-design UI configuration:
  `frontend/src/launch.ts`; the historical inactive-LDO limitation: `thesis-phd/chapters/14-discussion.tex`,
  section "Process transfer and benchmark fidelity" (paragraph beginning "The LDO1 port").

- TuRBO: Eriksson et al., [Scalable Global Optimization via Local Bayesian Optimization](https://arxiv.org/abs/1910.01739).
- Pareto/noisy batch BO: Daulton et al., [Parallel Bayesian Optimization of Multiple Noisy Objectives](https://arxiv.org/abs/2105.08195).
- [BoTorch constrained MOBO tutorial](https://botorch.org/docs/tutorials/constrained_multi_objective_bo) and
  [qLogNEHVI implementation](https://botorch.readthedocs.io/en/latest/_modules/botorch/acquisition/multi_objective/logei.html).
- Potential later trust-region MOBO arm: [MORBO](https://proceedings.mlr.press/v180/daulton22a.html).
- Related-task surrogate transfer, outside this same-function reuse primary protocol:
  [Multi-Task Bayesian Optimization](https://proceedings.neurips.cc/paper_files/paper/2013/hash/f33ba15effa5c10e873bf3842afb46a6-Abstract.html)
  and [RGPE](https://botorch.org/docs/next/tutorials/meta_learning_with_rgpe).

## 12. Amendment A1 (2026-10-28): M0, the Pareto search without the archive

Written before any M0 run, on the user's word: "add M0 as a written plan amendment. run it for seed 0 now"
(2026-10-28). The original sections stay as they were; this section only adds an arm.

**Why.** TuRBO is run with and without the archive (T0, T+), so the archive's effect on it can be read off. M+ only
runs with the archive, so its seed-0 results mix the multi-objective method with the head start from the archived
designs. The seed-0 report shows the archive effect is not one-directional (amplifier: T0 reached the Panel A target,
T+ did not), and M+ was mixed across cases (Panel B flip-flop +17.8 %, amplifier -38 %, LDO -23 % against the T+
portfolio). M0 separates the two.

**Arm.** M0 is M+ with exactly one difference: no archive (`run.comparison.archive` and its sha256 absent). Everything
else is M+'s, unchanged: `mobo_qlognehvi_v1` and its frozen settings (WORKPLAN 6c), objectives, base constraints,
energy rule, failure handling (a failed design is a missing output), start design, the case's 8 common first designs
of the rollout seed, the 800-evaluation and 800-launch caps, lanes, reset contract, the frozen runtime
`gator-runtime-bmr-f143d691` and the comparison environment. Like M+, one M0 trajectory serves both panels. No code
changes: the frozen search already accepts no archive.

**Scope.** Seed 0 (replicate 0, rollout seed 101) now: three runs (amplifier, flip-flop, LDO), at most 2,400 charged
evaluations and launches. M0 joins seeds 1-2 only if those are authorized. No confirmation batch is part of this
amendment (the 74 seed-0 confirmations reproduced every selected value exactly); M0's values are reported as measured.

**Scoring, fixed now.**

- Panel A, exactly as the seed-0 report scores the other arms: best fresh base-feasible preferred metric, first reach
  of the frozen `q_goal` (right-censored at the cap) and the failure share. M0 is read against T0 (the other
  cold start) and against M+ (the archive's effect on MOBO).
- Panel B, two numbers per case with the frozen orientations, scales and base-limit reference:
  (1) online-only HV of M0's base-feasible designs, against M+'s online-only HV; (2) source-plus-online HV (the
  archive's front plus M0's designs) beside the existing Panel B rows, labelled as using a front M0 never saw.
- One replicate is descriptive only: no default changes on seed 0 alone. Under section 7 a Pareto-mode replacement
  needs replicated medians; M0 is judged by the same rule as M+ if seeds 1-2 run.

**Running it.** Configurations are the M+ seed-0 configurations with the two archive keys removed (checked by a
diff), in `step7/jobs-M0.json` and `step7/configs/<case>-A-M0-r0.json` of the experiment folder. A separate queue,
`step7/queue-seed-0-M0`, uses the existing queue script and gates (resume from save points, 5 GiB WSL admission);
M0 is not under the one-M+-at-a-time rule (no 600-row archive, much smaller memory). The run and its results are
recorded in the workbench log.

### Revision 2 (2026-10-28, before any complete M0 result; on the user's word "go on")

**What happened to the first attempt.** Unchanged, M could not run without the archive: on the amplifier and the
flip-flop it stopped with `OptimizationGradientError` (NaN gradients of the acquisition) after 51 and 23 designs
(OptimizationGradientError raised by BoTorch; its model held about 9-16 working designs for 19 and 22 parameter groups,
most early designs having failed measurement). The LDO run never started. Both stopped cleanly (no uncertain launch);
their 74 charged designs stay in the cost record, and the crash is itself reported: the frozen M needs the archive (or a
cold-start procedure) on circuits where many designs fail measurement. It is not reported as "did not reach the
target": it never used 94-97 % of its budget.

**The change (standard cold-start practice, code `archive_compare/mobo.py`).** Two optional settings, present only in
M0's configurations:

- `cold_start_designs`: space-filling (Sobol) designs until the search knows 2(d+1) designs, archive included: 40
  (amplifier, 19 groups), 46 (flip-flop, 22), 56 (LDO, 27). Charged like every design.
- `numerical_fallback`: a numerical breakdown of the model or its acquisition (NaN gradients, a matrix not positive
  definite, an output with fewer than 2 values) gives the next Sobol design instead of stopping the run, recorded as
  `sobol_fallback` with its reason.

**M+ is unchanged, proven.** Neither setting is in any M+ configuration, so M+ takes the old code path; its 600
archived designs exceed every cold-start size anyway. Replay check: one real save point of each M+ run (designs
1,314-1,335 known, 600 archived) proposes the identical next design and acquisition value in the frozen seed-0
runtime and in the changed code (`amendment-A1-M0/replay_mplus.py`, `replay-*.json`).

**Runtime and runs.** M0 runs in `gator-runtime-bmr-e7135c3c` (= branch commit 6bc49f4 + the change and its tests;
optimizer digest 6ebf5ba5 unchanged; 69 comparison tests pass from the copy; record `step6/runtime-M0.json`, locks
`step6/locks-M0/`, package versions as seed 0's). The three runs start fresh (`bmr-<case>-A-M0-r0-v2`,
`step7/jobs-M0-v2.json`, queue `step7/queue-seed-0-M0-v2`), never as a continuation of the first attempt.

**Reporting additions.** The number of `sobol_cold_start` and `sobol_fallback` designs per run; if fallbacks are more than
10 % of the designs after the cold start, M0's result is labelled as closer to space-filling search than to M. Panel B
has no T0 portfolio in this run: M0's trade-off result is compared with M+ only. The earlier from-scratch TuRBO runs of
2026-10-18/19 (`turbo-compare-2026-10-18`: amplifier, flip-flop, other code, goals and starts) are cited as unmatched
background only.

### Revision 3 (2026-10-28, before any complete M0 result; continuing on the user's "go on")

**What happened.** The revision-2 runs were stopped by VM freezes and a dropped `/mnt/d` link (clean stops, continued
from save points taken at the stop). Then the amplifier's run stopped at design 146 (143 measured, 93 of them failed
measurement) on `ModelFittingError` ("All attempts to fit the model have failed"). BoTorch raises it as a plain
exception, and revision 2's fallback only covered NaN gradients, a matrix that is not positive definite and an output
with fewer than 2 values. Before that, 18 of its proposals had already fallen back on "matrix not positive definite"
(from about 104 known designs on). The stop was clean (no uncertain launch). The flip-flop run went on.

**Two changes (code `archive_compare/mobo.py`, `engine_comparison.py`), both active only under M0's settings.**

- The fallback covers every model breakdown: every BoTorch error (`ModelFittingError` included) and every runtime or
  value error of the model step. Each fallback still records its reason, so a breakdown caused by a bug stays visible.
- A resume after a crash continues numbering proposals after the last number already used. After a crash, a run's
  newest save point is behind its tables: the resume restores the search from that save point, then tells it every
  design that came after. Revision 2 also restored the proposal count, so the proposals made after the save point
  would be numbered again, and each Sobol design among them proposed a second time. The amplifier's save point is at
  design 112 with 96 proposals, and all 18 of its fallback designs came after it (proposals 100-126). The count now goes
  on after the highest number in the run's event log (synced after every record), or, if higher, after one number per
  own design committed after the save point. On the mock task, a run resumed from a save point 12 proposals back
  proposed 6 of its 22 designs twice before this change and none after it (`test_archive_compare_engine.py`).

**M+ is unchanged.** Without the A1 settings, the resume change does nothing: tested, an M+ search resumed after a
crash keeps its restored count as before. The wider fallback acts only under `numerical_fallback`. Revision 2's
replay proof stands.

**Runtime and runs.** M0 now runs in `gator-runtime-bmr-93927147` (record `step6/runtime-M0-r3b.json`, locks
`step6/locks-M0-r3b/`; branch commit 6bc49f4 plus both changes and their tests; optimizer digest 6ebf5ba5 unchanged;
73 comparison tests pass from the copy). A first freeze of revision 3 with only the first change
(`gator-runtime-bmr-e47b7561`, `step6/runtime-M0-r3.json`) was replaced before any run used it, when the repeated
numbers were found while preparing the amplifier's resume. Jobs, names and configurations stay revision 2's
(`step7/jobs-M0-v3.json`, queue `step7/queue-seed-0-M0-v3`):

- the amplifier's run continues in place from its save point: designs 1-146 under revision 2, the rest under revision 3;
- the LDO run starts fresh under revision 3;
- the flip-flop run continues under revision 2 in its own queue. Its designs are the ones revision 3 would propose
  unless it meets a breakdown outside revision 2's list, or it needs a resume after a crash: if it stops, it continues
  under revision 3.

**Three launches settled by hand (zero cost).** The 20:57 stop left three start designs (resets) in flight. The first
resume under revision 3 (22:29) recorded them as interrupted (charged, no result) and refused to continue: their launches
were unresolved. Each lane's own launch record shows one simulation of the start design, completed with one confirmed
call (status ok), started 1-3 s after its dispatch. `step7/ops/reconcile_leases.py` checked this for each lease and
settled all three: the original lease journal is kept, `data/_journal/reconciled-launch-leases.json` holds the
evidence, and the queue resumes a stopped run only when such a record covers every uncertain launch. The run's own
ledger no longer counts these three launches, so the report adds them to its launch total.

**Reporting additions.** The runtime of each run segment, the fallback reasons by kind, any design proposed twice
(expected: none) and the three reconciled launches.
