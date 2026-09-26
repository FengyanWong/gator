# Plan: a robust reward and a wider RL-network input (PVT corners, Monte Carlo, the PDK component list)

Status: **PLAN, written 2026-09-24. Nothing in it is built.** Every stage that edits `src/analog_optimizer/` or
spends Spectre calls needs an explicit user decision (section 8). The facts in section 1 were checked in the working
tree at commit `bbdfe36` (branch `workbench`), whose optimizer digest is the M6 pin `02127bc3…`; line numbers refer to
that commit. Later the same day another session removed the `port_gnn` encoder from the package (commit `8d647cd`,
record 7.83, digest `aa987cf0…`), so HEAD's digest is **no longer the M6 pin** and models saved before that load only
from a checkout of `bbdfe36`. Section 3.7 says what that means for stage 2.

**Decision of 2026-09-24 (later the same day):** the user authorized changing the optimizer package for the reward
design. The executable version of sections 2–4 (reward, observation, input v2, environment step) with the
workbench items that make it usable on MOCK is the brief [`brief-reward-v2-for-astra.md`](brief-reward-v2-for-astra.md),
addressed to Astra; where the two differ, the brief wins. Simulator budget (stages 1, 4, 5) stays undecided.

**Added 2026-09-26 (user request, conversation "what is the problem with the −1…0 capped reward"):** section 2.9
(Change D — the reward's shape: a compressed violation ramp, a worst-spec share in the aggregation, a margin term
inside the specs), consequences 5–6 in 1.1, the stage-3 arms, decision 8.10, and the brief's requirements S1–S6 with
gate G11. Nothing of it is built either.

## 0. What this plan is made from

1. The conversation **"corners / PVT / Monte Carlo"** (2026-09-21 21:24 – 22:04, continued 2026-09-22): what the
   optimizer allows (nothing but nominal), whether support differs by PDK (yes), how the encoder and the reward should
   change (worst case across corners through the unchanged formula; mean ± kσ for Monte Carlo; the shared context
   input, not the encoders), whether MLP / GCN should skip PVT (no: robustness lives in the reward and skipping would
   confound the encoder comparison), whether the cost forbids it (no, in stages; only Monte Carlo at every step is
   too expensive); then "what is the top-3 × 5-corner post-check like" and "build the corner post-check with a
   workbench button" (status record 7.62, commit `12ea4f4`).
2. The conversation **"Load PDK in the RL network block"** (2026-09-21 21:20 – 2026-09-23): the network's component
   list built from one PDK without touching the package (record 7.54, commit `f713cea`); "real runs still write MOS
   widths only" (true then, superseded by 7.66: a real run now writes any value the PDK's property form allows); "do
   designers change length" (yes).
3. The conversation **"should circuit type be trained into GAT / GT"** (2026-09-21): no type label; the spec slots
   already act as a hidden type label; what helps generalization instead.
4. **This conversation** (2026-09-24): the reward as it is today and its four consequences (no drive past the specs,
   the scale is the main knob, failing designs teach nothing, a terminal −1 would reward crashing).
5. **The conversation "what is the problem with the −1…0 capped reward"** (2026-09-26): the cap and the mean make
   giving up one spec cheaper than missing three slightly; one scale per spec sets both the ramp's reach and its
   resolution; every feasible design scores the same 0. Section 2.9.

Also: `docs/pvt-mc-interfaces.md` (M3), `configs/gpdk045_conditions.json`, `docs/workbench.md` ("Corner check",
"Load PDK"), `.agents/skills/analog-optimizer/references/pvt-monte-carlo.md`, and the GPDK045 model files read on the
VM on 2026-09-21 (never copied into the repository).

## 1. Where things stand (verified 2026-09-24)

### 1.1 The reward today

| Piece | Rule | Where |
| --- | --- | --- |
| Violation of one spec | (distance outside the allowed range) / `normalization_scale`, capped at 1; 0 inside | [specs.py:82-87](../src/analog_optimizer/measurements/specs.py) |
| Reward | −(Σ weight × violation) / Σ weight over the active specs with a valid value; always in [−1, 0] | [specs.py:90-96](../src/analog_optimizer/measurements/specs.py) |
| Success | every active **hard** spec has violation 0; weights play no part; no success bonus | [specs.py:88-89](../src/analog_optimizer/measurements/specs.py) |
| `direction_after_feasible` | chooses the best design after the run; **never enters the reward** | [schema.py:101](../src/gator_workbench/schema.py), [best_design.py](../src/gator_workbench/best_design.py) |
| Simulation OK, all hard specs valid | the reward above; the step enters replay | [sizing.py:294-296](../src/analog_optimizer/envs/sizing.py) |
| `invalid_design` / `nonconverged`, attributed to the candidate | −1 and the episode ends. **No backend ever emits these two statuses**, so this path never fires | [sizing.py:297-298](../src/analog_optimizer/envs/sizing.py) |
| Anything else (measurement error, timeout, transport, license, backend) | no reward, episode cut short, nothing enters replay | [sizing.py:299-302](../src/analog_optimizer/envs/sizing.py) |
| Condition | nominal only; a non-nominal condition is refused by the environment and by the model inputs | [sizing.py:100-101](../src/analog_optimizer/envs/sizing.py), [inputs.py:55-56](../src/analog_optimizer/models/inputs.py) |
| SAC target | r + γ·(next value), γ = 0.99; no bootstrap at the end of the 4-step episode (or at success when `episode_terminates_on_success`) | [sac.py:118-125](../src/analog_optimizer/training/sac.py) |
| Replay admission | **recomputes the reward from the stored next observation** and refuses a mismatch (1e-10) | [replay.py:62-68](../src/analog_optimizer/training/replay.py) |

Consequences (from this conversation; 5–6 added 2026-09-26): (1) once every spec is met the reward is 0 and stays 0, so nothing pulls the
agent further; (2) beyond one scale of miss a spec is stuck at 1 and gives no direction; (3) on real Spectre a broken
design is `backend_error` and an unmeasurable required spec (a VCO that does not oscillate) is `measurement_error`:
both are dropped, deliberately, so the agent never learns to avoid the regions that break the circuit; (4) with 4-step
episodes a terminal −1 (return −1) beats four steps at −0.3 (return −1.2), so a terminating failure penalty would
reward crashing the simulator; (5) the cap and the mean together make giving up one spec (violations 1, 0, 0 → reward
−0.33) score better than missing all three slightly (0.4, 0.4, 0.4 → −0.40); (6) one scale per spec sets both how far
the ramp reaches and how finely the last stretch is resolved, and a linear distance treats 2 µW and 200 µW alike
against a 1 µW bound with a 1 µW scale.

### 1.2 The network's input today

* `context_features` ([inputs.py:74-106](../src/analog_optimizer/models/inputs.py)): per result-registry slot 13
  numbers (present, hard, min/max/range flags, lower, upper, scale, weight, measured value, valid, has-lower,
  has-upper; values as signed log1p of value/reference), then 7 more: log1p(remaining steps), 3 status flags, and the
  condition as [1, T/100, VDD]. Width = 13·N + 7 (N = 7 in the default registry → 98; M6's 23-slot registry → 306).
* The context is one MLP ([encoders.py:176](../src/analog_optimizer/models/encoders.py)) whose output is **added to
  every node** (198-199) and to the group readout (221). All encoders (graph_transformer, gat, rgcn, gcn, mlp;
  `port_gnn` was removed from the package on 2026-09-24) share it; they differ only in the node-processing block.
* There is no process-corner input, no per-corner value, no "stage" flag, no Monte Carlo statistic. The 3 condition
  numbers are constant within a run today.
* The spec slots are a hidden circuit-type label (M6's three classes share only `supply_power_w`); slots never
  active in training keep their random initial weights (plain Adam, no weight decay), which fits "all six frozen
  encoders failed every M6 held-out target" without proving it (18 source calls per run).
* Each checkpoint records `feature_schema`, `spec_schema`, the code digest and the torch / PyG versions
  ([sac.py:149-156](../src/analog_optimizer/training/sac.py)).

### 1.3 Conditions, corners, Monte Carlo

* Types exist since M3: `PVTCorner` (model section, temperature, supply), `SimulationCondition` with purpose
  `nominal` / `pvt_validation` / `mc_validation`, `MonteCarloConfig` (samples, seed, process / mismatch / all,
  section) — [conditions.py](../src/analog_optimizer/backends/conditions.py). `run_monte_carlo()` raises
  `UnsupportedCapability`; nothing writes a Monte Carlo analysis or reads per-sample results.
* Screening set, [gpdk045_conditions.json](../configs/gpdk045_conditions.json): nominal TT 27 °C 1.0 V, `ss_hot_low`
  SS 125 °C 0.9 V, `ff_cold_high` FF −40 °C 1.1 V, `fs_nominal`, `sf_nominal`. 0.9 V is a project −10 % choice, not
  a PDK minimum; the OTA testbenches keep a fixed 0.4 V gate bias, so corners swing the tail current more than a real
  bias circuit would.
* Corner support by circuit: the OTA profiles accept the screening corners and rewrite the supply
  ([gpdk045.py:63-99](../src/analog_optimizer/backends/gpdk045.py)); LDO, VCO and generated profiles refuse anything
  but nominal ([gpdk045_ldo.py:31-33](../src/analog_optimizer/backends/gpdk045_ldo.py),
  [gpdk045_vco.py:35-37](../src/analog_optimizer/backends/gpdk045_vco.py),
  [generic_profile.py:127-129](../src/gator_workbench/generic_profile.py)). The real-run adapter used by every
  workbench run, `NativeCandidateBackend`, refuses non-nominal conditions outright
  ([native_preparation.py:231-235](../src/analog_optimizer/backends/native_preparation.py)) and has no
  `generate_netlist`. The plain `VirtuosoBridgeBackend` supports corners end to end, but each corner **re-exports the
  netlist from Virtuoso** (~1 s) before substituting section / temperature / supply
  ([virtuoso_bridge.py:271-312](../src/analog_optimizer/backends/virtuoso_bridge.py)).
* The **Corner check** tab (record 7.62) re-simulates a finished run's safest feasible designs at the five corners:
  MOCK verified end to end, real path only against a fake adapter — **no real Spectre corner simulation has ever
  run**. Today the only real circuit it can check is `real:gpdk045_ota7` (the OTA5 cells were deleted, 7.73).
  Selection ranks feasible designs by their smallest spec margin because every feasible design scores 0.
* GPDK045 v6.0 statistics (read on the VM 2026-09-21): process (chip-to-chip) variation exists **only in section
  `mc`**, centred on TT, four shared random factors for NMOS and PMOS; **mismatch statistics are loaded by every
  section** (tt/ff/ss/fs/sf/mc), so mismatch Monte Carlo can run at any corner; σ(Vth) ≈ 0.94 mV·µm (NMOS) /
  1.48 mV·µm (PMOS) scaling as 1/√(m·nf·W·L). MIM capacitors have mismatch; resistors, diodes, BJTs, MOS caps and
  the inductor have process variation only. GPDK045 cannot be manufactured: any yield figure demonstrates the method,
  not silicon.

### 1.4 The PDK component list (Load PDK, records 7.54 / 7.66)

* The list of device kinds, terminal roles, net roles and parameter columns is `FeatureSchema`, an **argument** of
  `SACLearner` / the encoders / `batch_observations`, recorded in every checkpoint's contract. Only the 8 group kinds a
  varied parameter may have (w, l, m, nf, r, c, ind, dc) are package code ([inputs.py:164-170](../src/analog_optimizer/models/inputs.py)).
* `run.network.vocabulary` = `standard` (hashed as absent) or `pdk:<technology library>`; a run keeps its own copy;
  loading modes follow the model's list; `pdk.learner_class` is `SACLearner` with `batch()` shown the PDK's view
  ([pdk.py:1003-1099](../src/gator_workbench/pdk.py)). GPDK045: 54 components, 62 kinds, 12 roles, 28 columns.
* Since 7.66 a real run writes any value the PDK's property form allows (not widths only).

### 1.5 What the workbench already anticipates

* `MeasurementDefinition.conditions` / `aggregation` (`nominal_only`, `worst_case`, `mean`, `min`, `max`) exist in
  the schema ([schema.py:177-179](../src/gator_workbench/schema.py)) and are blocked by `nominal_only_backend`
  ([validation.py:465-468](../src/gator_workbench/validation.py)).
* The budget counts candidate evaluations and simulator launches separately (spec section 9,
  [budget.py](../src/gator_workbench/budget.py)); `max_spectre_launches` is an optional hard cap.
* Spec section 8D asks for a metrics table with one row per evaluation / test condition / metric; today every row is
  nominal.
* Specs are equations over probes (7.52); the lane injects computed specs into every simulation result
  ([spec_equations.py:194-221](../src/gator_workbench/spec_equations.py)) — a per-corner result would be extended the
  same way.

### 1.6 Measured costs

M6 pilot means per candidate package: OTA 3.35 s, LDO 3.94 s, VCO 8.01 s (fast policy; strict VCO 59.4 s). Strict VCO
split: Spectre 41.6 s, download 5.9 s, bridge parse 3.1 s, GATOR analyze 8.2 s, Virtuoso edit + netlist ~1 s. A corner
job needs no CDF write; with a derived deck (section 4) it needs no Virtuoso export either — Spectre time only.

## 2. Reward design

### 2.1 Keep

The capped weighted violation mean, success independent of weights, no success bonus, and **bit-identical nominal
rewards**: with corners and Monte Carlo off, the new code must reproduce every recorded reward of the M6 evidence
(2,811 pilot + 28 requalification + 38 qualification candidate packages) from their saved metrics, offline, with
zero simulation. That is the regression gate of stage 2.

### 2.2 Change A — worst case across the evaluated conditions (PVT)

For a candidate evaluated at the planned conditions C (nominal, plus K corners):

* per spec s: **v_s = max over c ∈ C of violation_s(c)**, each violation computed and capped exactly as today (for a
  `range` spec the worst violation may sit at either end — take the worst violation, never "the smallest value");
* reward = −Σ w_s·v_s / Σ w_s, over the active specs that have a valid value at every evaluated condition;
* success = every active hard spec valid at every planned condition and v_s = 0.

Properties to test: v_s ≥ the nominal violation, so the robust reward is never above the nominal one; still in
[−1, 0]; a pure function of what the observation stores (2.8), so replay admission keeps recomputing it. This is what
the PVT conversation recommended and what PPAAS (ICCAD 2025, goal-conditioned SAC) does. The M3 `robust_score`
(nominal reward − λ × failed corners) stays a ranking key of the Corner check tab; a count of failed corners says
nothing about how close a corner is to passing, so it is never a training reward.

Optional, default off: a spread penalty α·σ_s of the spec's value across corners (PPAAS). Not in the first version.

### 2.3 Skip-on-fail

Corners are simulated **only when the nominal result meets every hard spec**. If not, the planned conditions of that
evaluation are {nominal} and the reward is today's nominal reward: the design fails anyway, and the network sees why
it was not checked further (the stage flags of 3.2). Expected cost per evaluation: 1 + K × P(nominal feasible)
launches. "Always" (all corners for every candidate) stays available for studies only.

### 2.4 Failures at a corner, and design failures in general

* A corner with an **infrastructure or measurement error** (timeout, transport, license, backend, a required
  measurement that does not validate): the whole step is cut short and enters no replay — the same rule as today at
  nominal. Honest but wasteful; it is recorded per condition so the loss is visible.
* A corner where the backend **attributes** a failure to the candidate (`invalid_design` / `nonconverged` with
  `candidate_evaluated`): violation 1 for every hard spec at that corner, the episode continues. Today no backend emits
  such a status; giving the profiles' analyzers an attributed "did not oscillate" / "did not converge" verdict is a
  separate decision (8.3), and the only way the agent can learn to stay away from regions that break the circuit.
* If that attribution is added at nominal too, **do not terminate** on it (consequence 4 of 1.1): give −1 for the
  step and continue with an observation whose status flag says `invalid_design` (the inputs already accept that
  status). The current "−1 and terminate" branch is kept as it is for compatibility until that decision.

### 2.5 Change C — an objective term after feasibility (optional, default off)

Addresses consequence 1 of 1.1. The one spec allowed to carry `direction_after_feasible` gets a bounded term:

* minimize: t = clip((upper − value) / scale, 0, 1); maximize: t = clip((value − lower) / scale, 0, 1);
* reward = −violation_mean + β·t·[feasible], with β a run setting in [0, 1], **default 0** (reward exactly as today);
* the reward's range becomes [−1, β]; success and the best-design rule are unchanged.

The flag "this spec is the objective (min / max)" becomes part of `MetricSpec` and of the context (3.2), so switching
β on later needs no second contract change. Decision 8.2.

### 2.6 Change B — Monte Carlo margin (last, if ever)

Never train on yield (flat 0 % / 100 % with small samples). Per spec: value_eff = mean − k·σ for a lower bound,
mean + k·σ for an upper bound (k default 3), from N mismatch samples with **common random numbers** (one fixed seed
set per run, so differences come from the design, not the draw); the violation is computed from value_eff and enters
2.2 as one more "condition". N = 16–32 for training (σ is accurate to about 18 % / 13 %, since SE(σ)/σ ≈ 1/√(2(N−1)));
finalists are checked with fresh seeds and N = 300: **0 failures in 300 → failure rate ≤ 1.0 % at 95 % confidence**
(Clopper–Pearson, 1 − 0.05^(1/300)), i.e. yield ≥ 99 %. Mismatch only, at the worst corner; process variation is
covered by the corners (GPDK045 has it only in `mc`, centred on TT). Order: the finalist check first (stage 5a), the
training reward only if finalists keep failing yield (5b).

### 2.7 After the run: best design and ranking (unchanged rules, one more verdict)

Best design = feasible at every planned condition ("robust-feasible") > nominal-feasible > infeasible with the smallest
uncapped violation; among robust-feasible designs the declared preference metric, then the earliest. `stop_at_first_feasible`
and `episode_terminates_on_success` mean robust success when corners are on; the nominal first-feasible event is still
recorded separately (spec section 9).

### 2.8 Versioning

Environment `reward` label `negative_weighted_mean_capped_violation` → `…_worst_case_v2`; `schema_version`
`sizing-env-v2` → `sizing-env-v3`; `SpecSchema.version` `spec-input-v1` → `spec-input-v2`; `checkpoint_version`
`graph-sac-v1` → `graph-sac-v2`; the replay `Transition` validation and the recorder's observation codec change with
them. The `Observation` keeps `metrics` / `metric_validity` / `metric_units` / `status` as the **nominal** result (every
nominal-only table keeps its meaning) and gains `conditions`: one record per evaluated condition (condition, status,
metrics, validity, units, job id). The reward and the context are recomputed from that; nothing aggregated is stored twice.

### 2.9 Change D — the reward's shape: ramp, worst-spec share, margin (added 2026-09-26, user request)

Three run settings, each **default off = today's formula to the bit**, hashed as absent at their defaults so that every
existing configuration keeps its hashes (the `vocabulary` rule). They act on the per-spec violations v_s **after**
Change A's worst case over conditions and **before** Change C's objective term; with corners off they act on the
nominal violations. Nothing in the context (3.2) changes: the settings are constant within a run, so they carry no
information for the policy; they are recorded in the environment config, the transition and the checkpoint contract
instead, and the compatibility report names a difference in words.

**D1 Compressed ramp** (`violation_shape`: `capped` = today | `compressed`). With d_s = (distance outside the range)
/ scale ≥ 0, today v_s = min(1, d_s): beyond one scale the spec is flat and gives no direction (consequence 2).
Compressed: **v_s = d_s / (1 + d_s)**. Properties: v(0) = 0, so success is unchanged; slope 1 at 0, so a small miss
costs what it costs today to first order; v(1) = 0.5; strictly increasing for every d and below 1 for every finite d,
so the range stays [−1, 0] and every design keeps a direction; v(9) = 0.9 and v(99) = 0.99, so a decade of miss is
still worth 0.09 of reward. Rejected: tanh(d) and 1 − e^(−d), which are flat again within three scales
(tanh′(3) ≈ 0.01). The scale's meaning changes from "the miss beyond which nothing counts" to "the miss that costs
half"; the reward review's rule of thumb (6.6) says so. An attributed failure (2.4) stays violation 1 and still
dominates. A per-spec log-ratio distance for decade-spanning metrics (|ln(value / bound)|) is **not** in v2: the
compression already keeps the ordering across decades; revisit only if stage 3 shows it is needed (8.10).

**D2 Worst-spec share** (`worst_spec_share` λ ∈ [0, 1], default 0). Today reward = −mean_w(v), the weighted mean over
the active specs with a valid value (weights rescaled by their maximum). New: **reward = −[(1 − λ)·mean_w(v) +
λ·max_s v_s over the active hard specs]**, the max unweighted, because success is independent of weights (2.1): a
soft spec's weight is its price and it may be traded away, a hard spec may not. Properties: λ = 0 is today; range
[−1, 0]; non-increasing in every v_s; reward 0 iff every active spec is met (the feasibility signal is unchanged); a
fully violated hard spec costs at least λ whatever the other specs do. Consequence 5 with λ = 0.5: (1, 0, 0) → −0.67,
(0.4, 0.4, 0.4) → −0.40 — the design that keeps all three close now wins. With corners on the max is over the
worst-case v_s, so one corner that breaks one hard spec costs at least λ. This also answers the dilution of the mean
with many specs: the worst hard spec always keeps a share λ of the reward, however many rows there are.

**D3 Margin inside the specs** (`margin_weight` γ ∈ [0, 1], default 0). For a successful evaluation (the same gate as
Change C's β), per active spec with a valid value and at least one finite limit: m_s = (distance to the nearest
limit) / scale — the Corner check's margin ([corner_check.py:187](../src/gator_workbench/corner_check.py)), the
number that already ranks feasible designs "safest first" — clipped at 0 (a violated soft spec contributes no margin;
its violation is already in the mean) and compressed the same way, **μ_s = m_s / (1 + m_s)** in [0, 1);
**reward += γ·mean_w(μ_s)·[successful]**. Under Change A the margin is the smallest over the evaluated
conditions (as Change C takes the worst-case value); a spec judged at nominal only uses its nominal margin; when β > 0
the objective spec is left out of the margin mean (Change C already rewards it, in the same direction, so the two
never conflict). The range becomes [−1, β + γ]; success, the best-design rule and the Corner check's ranking are
unchanged — training now pulls where that ranking already points, and a nominal-only run (stage 1, corners off) stops
leaving zero-margin designs for the Corner check to fail. An unsuccessful evaluation scores < 0 and gets no margin
term, so the margin never lifts an infeasible design above 0; a successful design with a violated soft spec keeps its
negative violation term, as today. γ is a tie-breaker among feasible designs, 0.1–0.2: it pulls every
spec inward at once, including pairs that trade against each other (phase margin against bandwidth), and the mean
balances them.

Together: a direction everywhere outside the specs (D1), no cheap abandonment of a hard spec (D2), and a preference
inside the specs that matches the ranking the Corner check already uses (D3). Any one alone leaves the other two holes.

Where the settings live: `RunSettings.reward` (new block: `violation_shape`, `worst_spec_share`, `margin_weight`),
hashed as absent at the defaults; β keeps its place in the Test-conditions settings (brief W1).
`SpecificationEvaluator(specs, objective_weight, violation_shape, worst_spec_share, margin_weight)`; `Evaluation`
gains `margins` (raw m_s per active spec with a valid value, `None` otherwise) for the tables and the reward review.
The transition records the three values next to `objective_weight` and replay recomputes with them (brief O3); the
checkpoint contract records `reward_shape`; the environment config records it next to the reward label (the label
stays `…_worst_case_v2`: the shape is a recorded setting, not a formula version). Regression gate: at the defaults,
bit-identical rewards on the M6 evidence (brief G1 unchanged); the properties above as tests (brief G11).

Tables, tabs, review: `evaluations` gains `min_margin` (the smallest m_s over the hard specs, the Corner check's
number) for every successful evaluation; the Specs tab's header line (6.2) gets the three controls with one plain
sentence each; a saved model's facts gain **Reward shape** (6.3); the reward review's digest (6.6) gains per spec the
share of misses beyond three scales, the share of evaluations where the worst hard spec exceeds the mean by more than
0.2, and the mean margin among feasible evaluations, so the agent can say when λ or γ would have changed the ranking.

Defaults for runs: off in code, always. Stage 3 runs three shape arms (table in section 5, decision 8.10); the stage-4
pilot uses the same shape in both of its arms, chosen from stage 3, so that the pilot still compares corners only.

## 3. Network-input design

### 3.1 One observation per candidate (chosen), not one per corner

Option A: the observation carries the nominal values plus, per spec, the worst-case value over the evaluated conditions
(PPAAS). Option B: one transition per corner with the corner as part of the state (RobustAnalog). A multiplies the input
by a small constant and keeps the finite-horizon MDP and the replay as they are; B multiplies the replay and makes the
critic learn Q(state, corner, action) although the policy acts on one design. **A.**

### 3.2 Context v2

| Block | v1 | v2 additions |
| --- | --- | --- |
| per registry slot | 13 | + objective-min, objective-max flags (2.5); + worst-case value (signed log1p), worst-case valid; + Monte Carlo mean, σ, log1p(samples), valid (zeros until 2.6 is used) → **21** |
| after the slots | log1p(remaining), 3 status flags, [1, T/100, VDD] = 7 | + log1p(planned corners), evaluated fraction, "nominal passed", "all planned passed" (the PPAAS 2-bit stage flag) → **11** |

Width = 21·N + 11 (N = 7 → 158; N = 23 → 494). With corners off, the new columns are zeros; the v1 columns keep
their exact values — test: v2 features restricted to the v1 columns == v1 features. The Monte Carlo columns go in now
so that stage 5b needs no second contract bump; zero inputs contribute nothing (their weights simply stay untrained
until used). Change D (2.9) adds no column: its three settings are constant within a run and live in the contract,
not in the input.

### 3.3 Process-corner encoding — in the conditions file, not in the model

Each corner gets `{"nmos": ±1|0, "pmos": ±1|0}` in a NEW file `configs/gpdk045_corner_speeds.json`: tt (0, 0),
ss (−1, −1), ff (+1, +1), fs (+1, −1), sf (−1, +1); a second PDK's file gives its own. Not in
`gpdk045_conditions.json`: that file is hash-pinned by the M5 / M6 audits (`CLAUDE.md`, "evidence files"). The data tables and the tabs use it; under option A the
model does not need to know **which** corner was worst, only how bad, so it is not an input (it would be, per corner,
if option B were ever chosen).

### 3.4 No mismatch feature

The suggested per-device 1/√(W·L) is unnecessary: the device features are signed logs of w, l, m, nf, so
log(1/√(m·nf·W·L)) is a linear combination the first layer can form.

### 3.5 The PDK component list

Orthogonal to the reward and to the conditions. Rules: choose the list **before** the first robust run (a checkpoint
pins it); use `pdk:gpdk045` for robust runs on circuits with resistors, diodes or bipolars; never add a PDK id or a
circuit-type label as an input (the type conversation: a label is a lookup row that is noise for a type never seen).
A corner's speed encoding is PDK-independent by construction.

### 3.6 The same input, reward and budget for every encoder

Robustness comes from the reward, not the encoder; giving MLP / GCN the easier nominal task would confound the encoder
comparison. Where the architecture might matter (mismatch is about matched pairs; the MLP ignores wiring, GCN ignores
pin types) is a result to measure, not a reason to exclude them.

### 3.7 Generalization items from the type conversation — which ones are free

| Lever | Package change? | Plan |
| --- | --- | --- |
| net roles feedback / reference / control | no (`net_roles` is in `FeatureSchema`; roles are assigned by the profiles / the PDK view) | workbench, any time |
| more layers (receptive field) | no (`run.network.layers`) | a preset, any time |
| a graph-wide node / global attention | yes | not in v2 unless decided (8.1) |
| specs by quantity / unit / target instead of per-name slots | yes (`context_features`) | not in v2 unless decided (8.1) |

Two digest changes are worse than one: whatever is bundled goes into stage 2 together. The `port_gnn` removal of
2026-09-24 has already moved the digest off the M6 pin; if stage 2 is decided soon, the two package changes land as
separate, clearly labelled commits inside the same "no earlier checkpoint survives" window, before any model is
trained under the intermediate digest.

### 3.8 Checkpoint contract and migration

Old checkpoints do not load under the new digest in any case. The model chooser's compatibility report must name the
reward version and the input version of a saved model. A **migration tool in `examples/`** (never in the package) can
turn a v1 model into a v2 model by inserting **zero** rows into the context MLP's first layer for the new columns and
re-ordering the old ones: identical outputs on nominal data, so an M6-style pretrained encoder can be reused in a
robust `fine_tune`. Zero, not random: with zero inputs a random weight is silent, but it would speak the moment corners
are switched on. Decision 8.9.

### 3.9 Operating points per device (added 2026-09-26, user request)

What a designer reads after a simulation - each transistor's ids, gm, gds, vgs, vds, vth, vdsat and region - is
already measured on every real evaluation (the OTA, LDO and VCO analyzers and the generated recipes return it; only
the recorder keeps it). It changes with every candidate, so unlike PDK constants it carries information (3.5). v2 adds
it as a per-device node input: a 12-column block (7 quantities + the region code as 5 flags), signed-log normalized
like the sizes, with a mask for devices without an entry; keyed by mapping the simulator's `XU1.M1` to the graph's
`XU1/M1`. Zero on MOCK and on Maestro-measured tasks, which return none: the block is then all zeros with mask 0. Off
by default so that existing configuration hashes stay; on for the pilot runs. One linear layer in the shared input
path; the encoder blocks are untouched. Zero extra simulation. Details: the brief, requirements P1-P6 and gate G10.

## 4. How one candidate is evaluated (execution)

1. Nominal, exactly as today (write the sizes, export, graph contract check, simulate, measure, computed specs).
2. If corners are on and the nominal result meets every hard spec (skip-on-fail): for each planned corner, derive the
   deck from the **same export** (`structure_for_condition` for the supply + `build_deck` with section / temperature —
   the text step the plain backend already does after its re-export; a new `derive_netlist(artifact, condition)` on the
   adapters does it without a Virtuoso call), run Spectre, measure, extend with computed specs. First version: serially
   inside the lane; later: fan the K jobs out to idle lanes (they are independent).
3. Record: one candidate record with a `conditions` list (job ids, timings, status per condition); one `simulator_jobs`
   row per launch; `metrics` rows per condition.
4. Budget: **one evaluation** charged per candidate; **one launch per job**; `max_spectre_launches` caps launches;
   `max_consecutive_infrastructure_failures` counts launches.
5. Profiles: LDO, VCO, generated and Maestro-measured tasks need `structure_for_condition` (the supply source's dc
   value; the generic profile already knows `supply_source` / `supply_v`) and `validate_condition` accepting the
   screening corners; control voltages and biases stay absolute, as for the OTA (a stated limit). LDO and VCO are
   package profiles (stage 2); the generic profile is workbench code (stage 1).
6. Restoration unchanged: the cell holds the nominal sizes; corners never write to Virtuoso.
7. Monte Carlo (stage 5): a deck with a `montecarlo variations=mismatch numruns=N seed=S savefamilyplots=no { … }`
   block around the profile's analyses, at the chosen corner's section; per-sample psf directories measured one by one;
   `run_monte_carlo()` implemented on the bridge backend returning the existing `MonteCarloResult`. Whether the pinned
   bridge library handles Monte Carlo output directories is **unverified** and part of the qualification job.

## 5. Stages, gates, budgets, tests

Each stage follows the project loop: freeze → execute → independent audit → full regression → record
(`docs/decisions.md`, a doc page, `artifacts/local/*-acceptance-summary.json`).

| Stage | What | Package digest | Spectre cost | Gate to the next stage |
| --- | --- | --- | --- | --- |
| 0 | Decisions of section 8; freeze this plan (hash in `decisions.md`) | — | 0 | decisions recorded |
| 1 | Corner support for generated profiles (supply override, workbench side); a nominal OTA7 run + the **first real corner check** (3 designs × 5); the ring oscillator once its override exists; frontend items of 6.1 that need no package change | unchanged | ≈ 60 nominal + 15 + 15 ≈ 90 calls (≈ 5 min at 3.4 s) | the share of nominal-feasible designs that fail a corner. Near 0 → stop at post-check + Monte Carlo; substantial → stage 2 |
| 2 | Package v2: reward 2.2–2.5 and 2.9, context 3.2, `Observation.conditions`, condition-aware env step, adapters' `derive_netlist`, LDO / VCO corner support, recorder v3, replay v2, checkpoint v2, migration tool in `examples/`; workbench: run settings, tables, tabs of 6 | **new digest** (record old → new; the `port_gnn` removal is a separate commit; tag `bbdfe36` as the last M6-digest commit, e.g. `m6-evidence-02127bc3`, for re-audits from a worktree) | 0 | tests: bit-identical nominal rewards on all recorded M6 packages (offline); v2 ⊇ v1 features with corners off; worst-case ≥ nominal; the shape properties of 2.9 (brief G11); MOCK training with `MOCK_CORNER_SHIFT` end to end incl. checkpoint / resume / audit replay; full regression |
| 3 | MOCK robust-training study (free): nominal-only vs skip-on-fail vs always, × reward shape (today / `compressed` + λ 0.5 / `compressed` + λ 0.5 + γ 0.2), every encoder the package still has, 3 seeds; does the robust policy's best design pass the (MOCK) corner check more often, and which shape reaches feasibility in the fewest evaluations | unchanged from 2 | 0 | the machinery works and the robust reward changes behaviour on MOCK; the shape for stage 4 is chosen here (8.10) |
| 4 | Real PVT-aware pilot on OTA7: arms = nominal-only + corner check vs skip-on-fail robust; per run 100 evaluations, launch cap 500 (100 + 4 × feasible); 3 seeds × 2 arms, the same reward shape (stage 3's choice) in both arms | unchanged from 2 | ≤ 3,000 launches ≈ 2.8 h at 3.4 s (+ Virtuoso overhead) | pre-declared: robust-feasible found (yes / no), evaluations and launches to first robust-feasible, corner-check pass rate of each arm's best design |
| 5a | Mismatch Monte Carlo check on finalists: qualification job (8 samples, prove samples differ and N = 1 without variation equals the deterministic corner), then 300 samples at the worst corner per accepted design | `run_monte_carlo` on the bridge backend = package | 1 job + 1 job of 300 samples per design (≈ 5–10 min each, batched) | finalists' yield bound |
| 5b | Monte Carlo margin in training (2.6), only after corners pass (skip-on-fail extended: nominal → corners → MC), N = 32, k = 3, common random numbers | unchanged from 5a | N × per robust-feasible candidate | only if 5a shows finalists failing yield |
| 6 | Record: results page, `decisions.md`, acceptance summaries, memory | — | 0 | — |

Statistics: with 3 seeds a 3/3 result has a Wilson 95 % interval of about 0.44–1.00; stage 4 is engineering evidence,
not a proof. Everything reports launches and evaluations separately and states its limits (five corners are a sample;
0.9 V is a project choice; the OTA bias is a fixed 0.4 V; GPDK045 is not silicon).

## 6. Frontend specification

Written to the workbench spec's conventions (one schema for forms, agent output and backend; semantic validation; hard
constraints judged independently of the reward) and to the UI rules in force: actions on explicit buttons, nothing
polls, compact panels with help folded into closed `<details>` lines, headlines / warnings / buttons in view, settings
modules fold but start open and are remembered in the browser with an error mark when folded, no control that
duplicates an existing selector, double click chooses a list row.

### 6.1 "Test conditions" — a new module in the right column (Run configuration › after RL network)

* A table of the task's screening corners from its profile's conditions file, read-only facts (id, section, °C, V,
  speed), one checkbox per corner **use in training**; all off = today's nominal-only run (the field is hashed as
  absent when off, like `vocabulary`, so every existing configuration keeps its hashes).
* **Corners during the run**: `off` / `after the design passes at nominal` (skip-on-fail, default when any corner is
  on) / `always` (studies).
* **Monte Carlo during the run** (stage 5b): `off` / `mismatch, N samples, k sigma, after the corners pass`.
* A cost line that updates on edit, never on a timer: "1 launch per evaluation, up to 1 + K (+ 1 Monte Carlo job of
  N samples); budget E evaluations → at most L launches"; the existing `max_spectre_launches` shown here as
  **Launch cap**.
* One line of plain language + a closed `<details>` with the verdict rule (2.2 / 2.7) and the limits (1.3).
* Readiness checklist rows (`readiness.py`): "corners chosen but this task's profile accepts nominal only" (LDO / VCO
  before stage 2), "Monte Carlo on but no Monte Carlo backend is qualified", "corners on with a saved v1 model
  (migration needed)".
* Start's authorization states the maximum launches, not only evaluations: "Authorize up to L launches (E evaluations)?".

### 6.2 Specs tab

* Columns unchanged; the row-level **objective** (`direction_after_feasible`) keeps its meaning (one row at most).
* New per-row field **judged at**: `all conditions` (default) / `nominal only` — for a spec that only makes sense at
  the normal point (an assisted-startup check); validation: a hard spec judged at nominal only cannot be the reason a
  corner passes.
* New run-level number in the Specs tab's header line, next to the objective explanation: **objective weight in the
  reward β** (0–1, default 0, "0 = the reward is 0 for every feasible design, as before"), with the plain sentence
  "β > 0 rewards a feasible design for being further inside its objective's limit, by up to β".
* Three more run-level controls in the same header line (Change D, 2.9), each with one plain sentence:
  **Violation ramp** `capped` / `compressed` — "capped: a miss beyond one scale counts as a full miss, as before;
  compressed: a miss of one scale counts half, larger misses keep counting more, never quite a full miss";
  **Worst-spec share** (0–1, default 0) — "0 = the average of the specs' misses, as before; 0.5 = half of the reward is
  the single worst hard spec, so no hard spec can be given up cheaply"; **Margin weight** (0–1, default 0) — "0 = every
  feasible design scores 0, as before; 0.2 = a feasible design earns up to 0.2 for keeping every spec away from its
  limit". All three hashed as absent at their defaults.
* The Probes tab keeps `conditions` / `aggregation` as they are; validation derives them from 6.1; the
  `nominal_only_backend` blocker becomes the plain "this task's profile accepts nominal only" when corners are requested.

### 6.3 RL network block

* A fact row **Input**: "v2: N result slots × 21 + 11 = width" (v1 for old models).
* A fact row **Reward shape** in a saved model's facts ("capped ramp, worst-spec share 0, margin 0" = today); the
  compatibility report says a difference in words ("this model was trained with a compressed ramp and worst-spec
  share 0.5; this run uses the capped ramp and 0") — a warning, not a blocker (2.9).
* A checkbox **Operating points as input** (added 2026-09-26, section 3.9): one line of help, the note that MOCK and
  Maestro-measured tasks give none, and a fact row in a saved model's facts saying whether it was trained with them.
* A saved model's facts gain **Reward** (`nominal v1` / `robust v2`) and **Trained at** (nominal | nominal + the corner
  ids). The compatibility report says, in words, "this model was trained with the v1 input; this run needs v2 —
  migrate (fine_tune only) or choose Mode scratch", with a **Migrate…** button that runs the `examples/` tool on a copy
  and shows the new model's path (decision 8.9). Components / Load PDK unchanged.

### 6.4 Run status and Data tables

* Per evaluation: nominal verdict, corners evaluated (k of K), robust verdict with the first failing spec and corner
  ("power at ss_hot_low"); the best-design box says "robust at 5 conditions" or "nominal only — not checked at corners".
* `metrics` gains a `condition` column (old runs read as `nominal`); `evaluations` gains `conditions_planned`,
  `conditions_evaluated`, `robust_feasible`; `run_summary.json` and the aggregate CSVs gain
  `first_robust_feasible_eval_count` next to the nominal `first_feasible_eval_count`, launches per evaluation, corner
  launches.
* `evaluations` gains `min_margin` (the smallest hard-spec margin in scale units, the Corner check's number; `None`
  unless the evaluation succeeded; old runs read as `None`); the best-design box shows it ("tightest: phase margin,
  0.8 scales") (2.9).

### 6.5 Corner check tab

* On a robust run: first a free grid **Recorded during the run** (the run's own corner results for its best designs),
  then the existing **Check** as "Simulate again" (fresh, costs, independent).
* Stage 5a adds **Monte Carlo check**: designs × N samples at each design's worst corner; verdict "0 of 300 failed →
  failure rate ≤ 1.0 % (95 %)" or "3 of 300 failed → 0.2–2.9 %" (Clopper–Pearson); the cost line and
  "Authorize 1 Monte Carlo job of 300 samples per design (D designs)?" before anything starts; Stop after the job in
  flight; files under `<run>/corner_checks/<id>/`.

### 6.6 The agent's conversation window — reward review

A new request kind **`reward_review`** (button **Review reward** beside "Review settings", above the conversation;
the same chat window, detachable as today):

* The agent is handed **data, no files**: the Specs rows (thresholds, tolerance, scale, weight, hard, objective), the
  Test-conditions settings, β, and — when a run is shown — a reward digest computed by the backend
  (`agents/run_digest.py` extended): per spec the share of evaluations where it was the largest violation, the share of
  its violations sitting at the cap 1, the share of feasible evaluations (reward exactly 0), per-corner failure counts
  by spec, and the reward's distribution over the run.
* With Change D (2.9) the digest also carries, per spec, the share of misses beyond three scales, the share of
  evaluations where the worst hard spec's violation exceeds the mean by more than 0.2, and the mean margin among
  feasible evaluations; the rule of thumb for `normalization_scale` under the compressed ramp reads "the miss that
  should cost half".
* It answers in plain language ("your reward is stuck at −1 because the gain spec's scale is 1 dB and every design
  misses by 6–12 dB") and proposes rows: `normalization_scale` (rule of thumb it is told: the miss you still want to
  feel, typically 10–30 % of the threshold or the baseline's distance), `soft_weight`, which spec carries the objective
  and β, whether to switch corners / Monte Carlo on and with which k. Each row is tried on a copy by the backend and
  applied **by the user**, as in "Review settings"; the agent applies nothing and never sees the circuit.
* Not a tool kind (no Virtuoso tools), no web. The brief `agents/run_readiness.md` gains one short paragraph on the
  reward (paid for on every request — keep it short). The conversation also takes free questions about the reward.
* Basis rule kept: suggestions must state their basis; requirements are never inferred from the circuit alone.

### 6.7 Checks

Hermetic browser checks on the harness (`frontend/scripts/lib/harness.mjs`) for 6.1–6.6 with fixtures (safe against
the live backend); `tests/workbench` for the schema, validation, digest and tables; `tests/` for the package (stage 2).
Live order: restart 8765 first, then rebuild `dist` (a new page on an old backend sends fields the old schema rejects).

## 7. Risks and traps

* **Replay recomputation**: the reward must be a function of the stored observation; `Observation.conditions`,
  `validate_observation`, `context_features`, the recorder codec and `Transition.validate` change together, and the
  input cache keys (a pickle of the observation) follow by themselves.
* **Graph metadata**: `simulation_condition` in the graph is the nominal export's; it stays nominal, the per-corner
  conditions live in `Observation.conditions`, and the metadata check ([inputs.py:59-63](../src/analog_optimizer/models/inputs.py)) keeps comparing against the nominal condition.
* **The −1 trap** (1.1, consequence 4): never add a terminating failure penalty to a 4-step episode.
* **The scale under the compressed ramp** (2.9): it becomes the half-penalty miss. A scale chosen for the capped ramp
  ("the miss you still want to feel") is a reasonable half-point too, but every help text and the review agent's
  brief must stop describing a cap.
* **Margin against the objective** (2.9): γ pulls every spec inward, including ones that trade against the objective;
  keep γ ≤ 0.2, leave the objective spec out of the margin mean when β > 0, and never let a shape setting differ
  between the two arms of the stage-4 pilot.
* **Zero-input weights stay random** (no weight decay): pad migrations with zeros; expect columns first used late in a
  run to start from random weights.
* **Corner harshness**: the OTA bias is a fixed 0.4 V gate voltage (Vth ≈ 0.35 V); corners swing its current. Many
  corner failures on OTA7 would say as much about the testbench as about the sizing — a bias-policy decision outside
  this plan.
* **Monte Carlo in GPDK045**: process variation only in `mc` (centred on TT), so "process Monte Carlo at SS" does not
  exist; mismatch does, at any corner. Save no waveform families (the strict VCO writes 116 MB per call; the VM's
  scratch grows unbounded).
* **Shared Virtuoso session**: corner jobs run in the same session; the adapter's `session.lock` mutual exclusion with
  the Corner check stays; no ADE / Maestro window may be open.
* **Budget accounting**: an evaluation that fails at a corner has still spent 1 + k launches; the tables must show it.
* **Digest**: every package edit invalidates the loading of existing checkpoints and the in-tree re-run of the M5 / M6
  audits; keep a tagged commit and a worktree recipe; bundle all package changes into one stage.
* **Two-source truth**: the workbench's `SpecPlan` injects computed specs per result; each corner result goes through
  `extend` too, or a formula spec would be judged at nominal only.

## 8. Decisions needed (with the recommendation)

1. **Stage 2 go / no-go**, and whether to bundle package-level generalization levers (global node, specs by quantity).
   Recommendation: only the robustness contract; net roles and layers are free anyway.
2. **Objective term after feasibility**: put the objective flag into v2 with β default 0? Recommendation: yes.
3. **Design-failure attribution** (a profile's analyzer says "did not oscillate / converge" → −1 without termination):
   Recommendation: later, per profile, after stage 1 shows how often it happens.
4. **Corner set for training**: all four screening corners vs the two extremes. Recommendation: all four in the
   pilot; the data says which are binding.
5. **Budgets**: stage 1 ≈ 90 calls; stage 4 ≤ 3,000 launches (or 1 seed ≤ 1,000). Never spent on a bare "go on".
6. **First circuit**: OTA7 (the only real corner-qualified one), then the ring oscillator via the generic override.
7. **Monte Carlo parameters**: mismatch only, worst corner, k = 3, N = 32 in training, N = 300 for finalists.
8. **UI placement** as in section 6, or different.
9. **Migration tool** for v1 models (zero-padded context): build it, or scratch only.
10. **Reward shape** (2.9, added 2026-09-26): build D1–D3 in stage 2 (off in code), which arms in stage 3, and the
    defaults for the stage-4 pilot. Recommendation: build all three; stage 3 arms as in the table; the pilot with
    `compressed`, λ = 0.5, γ = 0 unless stage 3 shows γ = 0.2 raises the corner-check pass rate; the log-ratio distance
    stays out.

## 9. What does not change

The M6 evidence and its digest; `plan-feasible-r2.json`; the Corner check's verdict rules; the best-design rule; specs
as equations over probes; the PDK component-list mechanism; the agent's limits (proposes, never applies, never sees
the design); the nominal-only run: with every new control off, rewards, hashes, tables and behaviour are today's.
