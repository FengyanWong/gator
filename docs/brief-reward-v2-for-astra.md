# Brief for Astra: reward v2 in the optimizer package (worst case across test conditions)

**Superseded for implementation on 2026-09-26:** use
[Reward v2 with real-flow qualification](plan-reward-v2-real-flow.md). The user rejected fictional
MOCK validation and requested a new plan with explicit permission to modify the optimizer.
The historical launch prompt, no-simulation rule, MOCK gates and conflicting requirements below
are no longer the implementation instructions. The new plan's scope, order and reporting apply.

Written 2026-09-24 for Astra (Codex, `gpt-6-astra`) by the Claude Code session "RL reward design". It turns section 2
(reward), the parts of sections 3–4 that the reward needs, and the workbench items that make it usable on MOCK, of
[`plan-robust-reward-and-network.md`](plan-robust-reward-and-network.md) into work. That plan holds the reasoning;
this brief holds the requirements. Where the two differ, this brief wins.

Updated 2026-09-26: operating points per device added as a network input on the user's request (requirements P1-P6,
gate G10, step 3 of section 6).

Updated 2026-09-26 (later): the reward's shape added on the user's request (requirements S1–S6, gate G11, steps 2
and 6 of section 6; the reasoning is plan section 2.9).

## 0. Launch prompt (paste into Astra)

```
Read /mnt/d/gator/docs/brief-reward-v2-for-astra.md and carry it out, in the order of its section 6.
You may edit src/analog_optimizer/ for exactly what the brief lists (section 1 records the permission).
No Spectre / Virtuoso / bridge call, no commit, no push, no live frontend build, no backend on 8765.
Stop and ask when a requirement cannot be met as written. Report as section 8 says.
```

## 1. Decision of record

On 2026-09-24 the user authorized changing the optimizer package `src/analog_optimizer/` **for the reward design
plan** ("write the plan with permission of changing the optimizer part for astra for the reward design plan").
Consequences, already stated to the user and accepted:

* `training/sac.py::source_digest()` changes again. HEAD `8d647cd` already left the M6 pin (`02127bc3…`) on the same
  day (`port_gnn` removed, record 7.83, digest `aa987cf0e3033d9c87b16693e10f8632eb69942d0d8d182ad7e3ac61ce9aecd1`);
  checkpoints saved before that and the M6 audit re-runs load only from commit
  `bbdfe365718bd0e780aecafd60eabd8f1306fdf0`. This brief adds the next digest step; nothing of the M6 evidence under
  `artifacts/` is touched.
* The reward change must land as **its own commit**, separate from any workbench commit and from the `port_gnn`
  commit, so that the digest history stays readable. The old and new digests go into `docs/decisions.md` (D2).
* Nominal behaviour stays **bit-identical** (gate G1). The user did not authorize simulator budget: every check in this
  brief runs on the synthetic MOCK backend.

## 2. Read first, and the ground rules of this repository

Read, in this order: `CLAUDE.md` (hard rules), `docs/frontend_implementation_status.md` (the index of the workbench's
record; its section 0 is the reading guide), `docs/decisions.md` (the last three entries), the plan named above,
`docs/pvt-mc-interfaces.md`, `docs/workbench.md` sections "Corner check" and "Specs are equations over Probes", and
`.agents/skills/analog-optimizer/SKILL.md` with `references/pvt-monte-carlo.md`.

Rules that bind this work (they are in `CLAUDE.md`; repeated because they are easy to break from the package side):

1. **Shared working tree.** Several Claude Code sessions edit `/mnt/d/gator` at once and share ONE git index. Stage
   explicit paths only, never `git add -A`; never reset, stash, amend or force-push; commit and push only when the
   user says so. Re-read a shared file right before each edit; keep your hunks apart from others'.
2. **Hash-pinned evidence.** The M5 / M6 audits re-hash `configs/*.json`, several `examples/*.py` and
   `tests/fixtures/synthetic/*.scs` by absolute path. Do not edit, reformat, rename or move them. New files next to them
   are fine. In particular: **do not edit `configs/gpdk045_conditions.json`**; corner metadata this brief adds goes into
   a NEW file (E2).
3. **Environment.** `~/analog-optimizer-venv/bin/python` (torch 2.14.0+cpu, torch-geometric 2.8.0.post1, pinned by
   `constraints.txt`). Tests: `OMP_NUM_THREADS=1 ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist load`
   (the full suite; 1,244 passed at record 7.83, about 2 min); `-m pytest tests/workbench -q` for the workbench alone.
   The suite redirects settings through `GATOR_WORKBENCH_SETTINGS_DIR`; any scratch script that prepares a run must set
   it too, or it overwrites the user's live `configs/local/workbench/settings.json`.
4. **The user's backend on 8765 is theirs.** Never start, stop or restart it. A live check of new routes uses a
   scratch port (check `ss -ltnp` first) and a scratch settings folder. `frontend/dist` is what 8765 serves: no
   `npm run build` unless the user asks; `npx tsc --noEmit` before any build. Browser checks in `frontend/scripts/`
   default to the live 8765; hermetic ones (fixtures) are safe.
5. **No simulation.** No Virtuoso, Spectre, bridge, SSH or agent CLI call. The real adapter's new code is tested
   against fakes only (see `tests/test_native_preparation.py`, `tests/test_bridge_adapter.py` for the pattern).
6. **Slow disk.** `/mnt/d` is a 9p mount: never `find`, `du` or unscoped grep across `artifacts/`; scope to the
   folders named here. Never edit one file from two tool calls at once.
7. **Language and tone of docs**: English, plain language first, limits stated bluntly, no claim the data does not
   support. Mock results are always labelled synthetic.

## 3. Scope

**In scope**

* Package: reward v2 (R), observation and replay (O), network input v2 (N), the environment step over several
  conditions with the adapters' derived decks and the synthetic backend's corner support (E), the checkpoint contract;
  operating points per device as node inputs (P, added 2026-09-26); the reward's shape settings (S, added 2026-09-26).
* Workbench (Python): run settings for test conditions, validation, engine / worker plumbing, the metrics table's
  condition column, verdicts in the run summary, the compatibility report (W1–W6).
* Workbench (frontend): the "Test conditions" module, the Specs-tab additions and the fact rows (W7), hermetic
  browser check included.
* Tests, the reward-identity gate script, docs and the record (D).

**Out of scope** (later decisions of the user; do not start them)

* Corner support for the LDO, VCO, generated and Maestro-measured profiles (a supply override that needs real
  qualification); `corner_check.checkable_real_tasks()` stays as it is.
* Any real simulation: stage 1 (first real corner check), stage 4 (real pilot), Monte Carlo execution
  (`run_monte_carlo` keeps raising), the Monte Carlo reward (only its reserved input columns exist, N3).
* Attributed design failures ("did not oscillate" → −1 without termination; plan 2.4 / decision 8.3). The existing
  `invalid_design` / `nonconverged` → −1-and-terminate branch stays byte-for-byte.
* Encoder changes, global attention, spec-by-quantity inputs, the PDK component list, the agent's `reward_review`
  kind (plan 6.6), the v1→v2 checkpoint migration tool (plan 3.8) — the last one only if time remains (section 6, step 9).

## 4. Requirements

Each requirement has an id used by the tests and the record. "Today" refers to HEAD `8d647cd`.

### R — reward (`measurements/specs.py`, `envs/sizing.py`)

* **R1 Unchanged nominal reward.** `SpecificationEvaluator.evaluate(metrics, units, validity)` keeps its signature,
  semantics and numbers: violation = (distance outside the range) / scale capped at 1; reward = −Σ w·v / Σ w with the
  weights rescaled by their maximum as today; success = every active hard spec valid with violation 0; missing
  optional specs excluded; `Evaluation` keeps its fields.
* **R2 Worst case over conditions.** New `SpecificationEvaluator.evaluate_conditions(results)`, where `results` is the
  ordered list of per-condition results of one candidate (the nominal first; each with metrics / units / validity /
  status / `candidate_evaluated`). Per active spec: v_s = max over the evaluated conditions of that condition's capped
  violation. Reward = the R1 formula on the v_s. Success = every active hard spec valid at **every** evaluated
  condition and v_s = 0, AND the evaluation was complete (R4). Property: the result on a one-element list equals
  `evaluate()` on that element, to the last bit.
* **R3 Skip-on-fail.** The environment simulates the corners only when the nominal result meets every active hard
  spec (validity and violation 0 for each). Otherwise the candidate's evaluated conditions are {nominal} and the reward
  is R1's. A run setting chooses `off` / `after_nominal` (default when any corner is on) / `always`.
* **R4 Failures.** (a) A corner with an infrastructure or measurement error (any status other than `ok`,
  `invalid_design`, `nonconverged`, or a required metric that does not validate): the whole step is truncated, no
  reward, no replay — as today at nominal — and every condition's outcome is recorded. (b) A corner with
  `invalid_design` / `nonconverged` and `candidate_evaluated`: violation 1 for every active hard spec at that corner
  (so it dominates the worst case); the episode continues; no termination. (c) At nominal, today's branches stay
  unchanged (R1, and the −1-and-terminate branch).
* **R5 Objective term (field now, effect off).** `MetricSpec` gains `objective: str = 'none'` (`'none'` / `'min'` /
  `'max'`), validated (at most one active spec with an objective; `min` needs an upper bound, `max` a lower bound),
  and `SpecificationEvaluator` gains `objective_weight` β ∈ [0, 1], default 0. When β > 0 and the evaluation is
  successful: t = clip((upper − value)/scale, 0, 1) for `min`, clip((value − lower)/scale, 0, 1) for `max`, and reward
  = R2's reward + β·t (so the range is [−1, β]); with β = 0 rewards are R2's exactly. The value used is the worst case
  over the evaluated conditions (the smallest margin). Success is unaffected. Default β = 0 everywhere; the workbench
  maps `direction_after_feasible` onto `objective` (W2) and exposes β (W7).
* **R6 Recomputable.** Every reward is a pure function of the next observation (its specs, its nominal metrics and its
  `conditions`, O1) and β; `Transition.validate` recomputes it (O3).
* **R7 Labels.** The environment's config `reward` label becomes `negative_weighted_mean_capped_violation_worst_case_v2`
  and `schema_version` `sizing-env-v3`; a run with corners off still writes these (the digest has changed anyway; the
  label says what the code computes). `budget_semantics` and `critic_action_semantics` unchanged.
* **R8 Ranking unchanged.** `evaluation/corners.py` (`select_top_designs`, `summarize_corners`, `robust_score`) is not
  changed; the Corner check tab keeps using it.

### S — reward shape (`measurements/specs.py`, `envs/sizing.py`, `training/replay.py`; added 2026-09-26, user request)

Facts. Plan 2.9 holds the reasoning: today a miss beyond one scale is flat (no direction), the mean with the cap makes
giving up one spec cheaper than missing three slightly, and every feasible design scores 0. Three settings act on the
per-spec violations after R2's worst case and before R5's objective term. At their defaults every number of R1, R2
and R5 is unchanged to the bit, and G1 stays the gate. They are keyword arguments with defaults, so R1's constructor
calls stay valid.

* **S1 Compressed ramp.** `SpecificationEvaluator` gains `violation_shape: str = 'capped'` (`'capped'` |
  `'compressed'`). With d = (distance outside the range) / scale: `capped` gives min(1, d) as today; `compressed`
  gives d / (1 + d). Applied inside the per-condition violation, before R2's max (the max of an increasing function is
  the function of the max, so the order does not matter for the numbers; applying it per condition keeps R4(b)'s
  "violation 1" dominant). Any other string is refused in words.
* **S2 Worst-spec share.** `worst_spec_share: float = 0.0` in [0, 1]. Reward = −[(1 − λ)·(R1's weighted mean) +
  λ·max of v_s over the active **hard** specs with a valid value], the max unweighted (success is independent of
  weights; a soft spec's weight is its price). λ = 0 reproduces R1 / R2 exactly. Applied before R5's term.
* **S3 Margin term.** `margin_weight: float = 0.0` in [0, 1]. Only when the evaluation is successful (R2's success):
  per active spec with a valid value and at least one finite limit, m_s = distance to the nearest limit / scale
  (≥ 0 inside, clipped at 0 for a violated soft spec) — the function `gator_workbench/corner_check.py::_margin` computes today; move it into the package
  (`measurements/specs.py`, a public `spec_margin(lower, upper, scale, value)`) and make `corner_check._margin` call
  it, so the tab and the reward never diverge (the tab's tests pin the numbers). μ_s = m_s / (1 + m_s);
  reward += γ·(weighted mean of μ_s over those specs, weights rescaled as in R1). Under R2 a spec's margin is the
  smallest over the evaluated conditions; a `nominal_only` spec uses its nominal margin; when β > 0 the objective
  spec is left out of the margin mean (R5 already rewards it). Range [−1, β + γ]; success unchanged. `Evaluation`
  gains `margins: dict[str, float | None]` (raw m_s; `None` for a spec without a valid value or without a limit) with
  a default, so existing constructions stay valid.
* **S4 Recomputable and recorded.** The three values travel with `objective_weight`: `Transition` gains
  `violation_shape`, `worst_spec_share`, `margin_weight` (defaults = off), `validate` recomputes with them (O3) and
  `from_step` fills them from the step's info; `CircuitSizingEnv.__init__` gains the three keyword arguments
  (defaults = off) and its config records `reward_shape = {violation_shape, worst_spec_share, margin_weight}` next to
  the `reward` label (R7's label is unchanged: the shape is a setting, not a formula version); the candidate journal
  carries it; `SACLearner.contract()` records `reward_shape` (with O5) and `checkpoints.check_compatibility` names a
  difference in words ("this model was trained with a compressed ramp and worst-spec share 0.5; this run uses the
  capped ramp and 0") as a warning, not a blocker.
* **S5 Workbench.** `RunSettings.reward: RewardShape` = `violation_shape` (default `'capped'`), `worst_spec_share`
  (0), `margin_weight` (0); hashed as absent when all three are at their defaults (W1's rule, so every existing
  configuration keeps its hashes); passed into the environment by W4's factories and recorded by `learner_experiment`;
  `evaluations` gains `min_margin` (the smallest hard-spec m_s, `None` unless successful; old runs read as `None`) and
  `aggregates.py` follows; β keeps its place in W1. Validation: a value outside [0, 1] or an unknown ramp name is
  refused per field in plain words (the 422 rule).
* **S6 Frontend.** In the Specs tab's header line (plan 6.2), next to the objective explanation: **Violation ramp**
  (`capped` / `compressed`) with "capped: a miss beyond one scale counts as a full miss, as before; compressed: a miss
  of one scale counts half, larger misses keep counting more, never quite a full miss"; **Worst-spec share** (0–1)
  with "0 = the average of the specs' misses, as before; 0.5 = half of the reward is the single worst hard spec, so no
  hard spec can be given up cheaply"; **Margin weight** (0–1) with "0 = every feasible design scores 0, as before;
  0.2 = a feasible design earns up to 0.2 for keeping every spec away from its limit". A saved model's facts gain
  **Reward shape** and show S4's sentence when it differs; the best-design box shows the design's smallest margin
  ("tightest: phase margin, 0.8 scales"). The hermetic browser check covers the three controls (in W7's file or its
  own).

### O — observation, replay, recorder, checkpoint

* **O1 `Observation.conditions`.** New field, default `()`: a tuple of `ConditionResult` (frozen dataclass:
  `condition: SimulationCondition`, `status: str`, `candidate_evaluated: bool`, `metrics`, `metric_validity`,
  `metric_units`, `job_id: str`, `reason_code: str | None`). The nominal result appears as the first entry whenever
  corners were planned; `Observation.metrics` / `metric_validity` / `metric_units` / `status` / `job_id` keep meaning the
  **nominal** result, so every nominal-only reader keeps working. `validate_observation` accepts an observation whose
  own `condition` is nominal and whose `conditions` carry purpose `pvt_training` (O2); it still refuses a non-nominal
  own condition; the graph-metadata check stays against the nominal condition.
* **O2 Purpose `pvt_training`.** `SimulationCondition.purpose` gains `'pvt_training'`; `nominal_only` stays
  `purpose == 'nominal' and monte_carlo is None`; `pvt_validation` keeps its post-check meaning (`summarize_corners`
  accepts only that); the OTA profiles' `validate_condition` accept `pvt_training` for the screening corners exactly as
  they accept `pvt_validation` (same bounds).
* **O3 Replay.** `Transition.validate` recomputes the expected reward with `evaluate_conditions` over
  `next_observation.conditions` when non-empty, else `evaluate()`, then applies R5 with the β recorded in the
  transition (new field `objective_weight: float = 0.0`); the `invalid_design`/`nonconverged`-and-terminated → −1 rule
  stays. `Transition.from_step` fills the new field from the step's info. `fingerprint()` covers the new fields
  (it hashes `vars(self)`). The candidate journal comparison in `from_step` gains `conditions` (the recorded list).
* **O4 Recorder.** `recording/store.py::_state` already stores every dataclass field of the observation except
  `graph` and `specs` and `_load_state` rebuilds with `**data['observation']`: make `conditions` round-trip through
  `recording/codec.py` (`tree` / `untree` of nested frozen dataclasses, or store plain dicts and rebuild), and add the
  per-condition job rows to the recorder's `finish` path so that `simulator_jobs` has one row per launch. The state id
  changes when `conditions` differ, as it must.
* **O5 Checkpoint contract.** `SACLearner.contract()` reports `checkpoint_version='graph-sac-v2'`, the
  `spec_schema` (whose `version` is `spec-input-v2`, N1) and a new key `reward='…_worst_case_v2'`. `load` refuses a
  v1 checkpoint with a sentence that names the version difference (the digest check already refuses it; the sentence
  must say why in words).

### N — network input (`models/inputs.py`)

* **N1 Layout v2.** `SpecSchema.version = 'spec-input-v2'`; `width = len(metrics) * 21 + 11`. Per slot, in this
  order: the 13 v1 numbers unchanged, then `objective_min`, `objective_max`, `worst_value` (signed log1p of the
  worst-case value over the evaluated conditions, 0 when none), `worst_valid`, `mc_mean`, `mc_sigma`, `mc_samples`
  (log1p), `mc_valid` — the four Monte Carlo numbers are always 0 in this brief (reserved). After the slots: the 7 v1
  numbers unchanged, then `log1p(planned corners)`, `evaluated fraction` (evaluated corners / planned, 0 when none
  planned), `nominal_passed` (every active hard spec valid with violation 0 at nominal), `all_planned_passed`.
* **N2 v1 preserved.** For an observation with empty `conditions`, the v2 vector restricted to the v1 positions equals
  the v1 vector exactly (test with a frozen copy of the v1 function kept inside the test module, not in the package).
* **N3 Worst value per spec.** For a `range` spec the worst value is the one with the largest violation; ties keep the
  nominal value. Values come from `evaluate_conditions` so that reward and input agree.
* **N4 Encoders.** The context change needs no encoder edit: the context MLP takes `spec_schema.width`, so the wider
  input reaches every encoder through the shared `context` path; `device_values`, kinds, roles, group features stay.
  The only encoder edit in this brief is P5 (one linear layer for the operating-point block, absent when the block
  is empty).

### E — environment step and backends

* **E1 Planned conditions.** `CircuitSizingEnv.__init__` gains `conditions: tuple[SimulationCondition, ...] = ()`
  (the corners to evaluate, purpose `pvt_training`, validated by the backend at construction) and
  `corner_policy: str = 'off'` (`off` / `after_nominal` / `always`); both go into the env config (hashed) and the
  candidate journal. With `()` / `off` the step is today's, byte for byte, except R7's labels.
* **E2 Corner metadata file.** New `configs/gpdk045_corner_speeds.json` (NOT the pinned conditions file):
  `{corner id: {"nmos": -1|0|1, "pmos": -1|0|1}}` for tt (0,0), ss (−1,−1), ff (+1,+1), fs (+1,−1), sf (−1,+1). Used by
  the workbench tables and the run status; not a model input (plan 3.3).
* **E3 Step over conditions.** In `_evaluate`, after the nominal result is complete and valid: if
  `corner_policy == 'always'`, or `after_nominal` and the nominal meets every active hard spec, then for each planned
  corner in order: derive the deck (E4), `run_simulation` with that artifact, extend with computed specs (the lane's
  `SpecPlan.wrap` already wraps `run_simulation`), classify (R4), append a `ConditionResult`. Serial inside the lane.
  The candidate journal records every condition (job id, status, reason, timings, netlist hash); `simulation_calls`
  counts every launch; a new `candidate_evaluations` counter counts candidates (one per step / reset).
* **E4 Derived decks, no Virtuoso call.** `VirtuosoBridgeBackend.derive_netlist(artifact, condition)`: the same text
  step `generate_netlist` performs after its export — `circuit.structure_for_condition(export text, condition)` then the
  deck builder with the corner's section and temperature — applied to the ORIGINAL export of `artifact` (kept next to
  it as evidence), written as a new `NetlistArtifact` with its own job id, sha256 and condition, registered in
  `_exports` so `run_simulation` accepts it. `NativeCandidateBackend.derive_netlist` does the same from the export in
  `self._exports`; its `validate_condition` accepts `pvt_training` corners the circuit accepts (its
  `prepare_candidate` stays nominal-only: sizes are written once). `generate_netlist` and the Corner check keep their
  re-export path.
* **E5 Synthetic backend.** `SyntheticSizingBackend` accepts conditions: `nominal_condition()` returns the project's
  nominal corner, `validate_condition` accepts the five screening corners with purpose `nominal` / `pvt_training` /
  `pvt_validation`, `derive_netlist` returns an artifact carrying the condition, and `run_simulation` shifts the toy
  optimum per corner by the same table the Corner check uses (`MOCK_CORNER_SHIFT` moves from
  `gator_workbench/corner_check.py` into the backend as a documented constant; the tab imports it from there). Results
  stay labelled synthetic.
* **E6 Reset.** Corners are never simulated on `reset()` (the baseline is nominal; the replay never takes resets).
* **E7 Collector.** `training/runner.py` and `training/parallel.py` need no scheduling change; they must report the
  new counters (`candidate_evaluations`, launches) in their histories and reports.
* **E8 Budget (workbench).** `gator_workbench/budget.py`: one evaluation per candidate, one launch per job;
  `max_spectre_launches` caps launches; `max_consecutive_infrastructure_failures` counts launches. The run's cost line
  reports both.
* **E9 Restoration unchanged.** The cell's sizes are the nominal ones throughout; corners write nothing.

### P — operating points per device as node inputs (added 2026-09-26, user request)

Facts. After every real simulation the analyzers already return the DC operating point of each transistor of the
profile's `mos_names`: `{'XU1.M1': {'ids', 'gm', 'gds', 'vgs', 'vds', 'vth', 'vdsat', 'region'}, ...}`
(`measurements/opamp.py:37-39`, `ldo.py:103`, `vco.py:154-155`; generated recipes in `gator_workbench/recipes.py:159`
with the DUT prefix). They travel in `SimulationResult.operating_points` (`backends/backend.py:82`); the bridge adapter
keeps the last set (`virtuoso_bridge.py:442`); the environment hands them to the recorder only (`sizing.py:320-328`,
`recording/session.py:72`); nothing reaches the network. Maestro-measured tasks (`recipes.py:221`) and the synthetic
backend give none. Graph device ids use `/` for hierarchy (`XU1/M1`, `backends/gpdk045.py:17`); the analyzers use `.`.
The feature costs no extra simulation: the values come from the DC analysis every evaluation already runs.

* **P1 Columns.** `FeatureSchema` gains `operating_columns: tuple[str, ...] = ()` and
  `operating_references: tuple[float, ...] = ()`, validated like `parameters` / `references`; empty by default, so the
  standard list keeps its content. A constant `OPERATING_POINT_COLUMNS` in `graph/pyg_converter.py` defines the
  standard block of 12 columns: `ids` (reference 1e-6 A), `gm` (1e-6 S), `gds` (1e-6 S), `vgs`, `vds`, `vth`, `vdsat`
  (1 V each), and the Spectre region code as five 0/1 flags `region_off`, `region_triode`, `region_sat`,
  `region_subth`, `region_breakdown` (codes 0-4, reference 1). Every column is normalized as the parameters are:
  signed log1p of value / reference.
* **P2 Source and mapping.** In `_evaluate`, right after the nominal simulation and before the observation is built (in
  both recorder branches): `points = result.operating_points`, else `backend.get_operating_points()`,
  `UnsupportedCapability` -> `None`. Keys map to graph devices by `device.id.replace('/', '.') == key`; a key that
  matches no device is listed in the journal as `operating_points_unmatched`, never an error; a device without an
  entry, a non-finite value or a `region` outside 0-4 gives mask 0 for the affected columns. The mapped dict, keyed by
  graph device id, is what the observation carries. A corner's operating points go into its `ConditionResult`
  (recorded, not an input).
* **P3 Observation.** `Observation.operating_points: dict[str, dict[str, float]] | None = None`;
  `validate_observation` checks keys within the device ids and finite values; the recorder's state stores it (O4); it
  enters the input-cache key (a pickle of the observation) and `Transition.fingerprint`; `None` on the synthetic
  backend and on tasks that return none.
* **P4 Tensors.** `to_pyg(graph, schema, operating_points=None, ...)` refreshes `data['device'].op` `[N_dev, K]` and
  `data['device'].op_mask` `[N_dev, K]` on every call, as it refreshes the sizes (K = `len(schema.operating_columns)`);
  `_prepare_observation` passes `observation.operating_points`; K = 0 gives `[N_dev, 0]` tensors and changes nothing
  else; the topology cache keeps only static parts, as today.
* **P5 Encoder.** `CircuitEncoder.__init__` adds `self.device_operating = nn.Linear(2 * K, h)` only when K > 0;
  `forward` adds `self.device_operating(torch.cat((device.op, device.op_mask.float()), dim=-1))` to the device nodes
  next to `device_values` and `device_kind`. With K = 0 the module does not exist and the `state_dict` keys are
  today's. All five encoders receive it through this shared input; the node-processing blocks are untouched.
* **P6 Workbench.** `run.network.operating_points: bool = False`, hashed as absent when false (W1's rule, so existing
  configuration hashes stay); when true the learner's `FeatureSchema` is the chosen component list (standard or PDK)
  plus the standard block (`pdk.py`: a helper `with_operating_points(schema)`); the checkpoint contract carries it in
  `feature_schema`; the compatibility report says in words when a model and a run differ on it. UI: a checkbox
  **Operating points as input** in the RL network block with one line of help ("after each simulation the network also
  sees every transistor's DC operating point - ids, gm, gds, vgs, vds, vth, vdsat, region; the OTA, LDO and VCO
  profiles and generated recipes provide it; MOCK and Maestro-measured tasks give none, and the block is then zero"),
  and a fact row in a saved model's facts. The graph view is unchanged.

### W — workbench

* **W1 Settings.** `RunSettings.conditions: TestConditions` = `corners: list[str]` (screening corner ids, default
  `[]`), `policy: Literal['off','after_nominal','always']` (default `off`), `monte_carlo: None` (reserved), and
  `objective_weight: float` (β, default 0). Hashed as absent when everything is at its default, the way
  `run.network.vocabulary` is (`schema.py` `_hashed`), so every existing configuration keeps its task / config hashes.
* **W2 Compile.** `compile.build_specs` sets `MetricSpec.objective` from `direction_after_feasible` (`minimize` → `min`,
  `maximize` → `max`); the existing "at most one preference" validation covers it. `PerformanceTarget` gains
  `conditions: Literal['all','nominal']` (default `all`): a spec judged at nominal only is excluded from the corners'
  violations (`evaluate_conditions` takes that per-spec flag through `MetricSpec.nominal_only: bool`).
* **W3 Validation.** Corners requested for a task whose profile refuses them → blocker in plain words ("this task's
  profile accepts the normal condition only"); the `nominal_only_backend` blocker on probes stays for probe-level
  `conditions` / `aggregation` (those fields remain as they are, derived: a run's conditions come from W1).
  `readiness.py` gains the checklist rows of plan 6.1, plus a warning (not a blocker) when operating points are on
  for a task that returns none (MOCK, Maestro-measured tasks): the block would be all zeros.
* **W4 Engine / worker / lanes.** `tasks.SyntheticEnvFactory`, `tasks._real_runtime` (`NativeEnvironmentFactory`),
  `ngspice_backend.py:336` pass `conditions` and `corner_policy` into `CircuitSizingEnv`; `learner_experiment` records
  them; `modes.current_contract` / `checkpoints.check_compatibility` compare reward and input versions and say the
  difference in words.
* **W5 Tables.** `storage/tables.py` `metrics` gains `condition` (text, default `'nominal'`; old runs read as
  nominal); `evaluations` gains `conditions_planned`, `conditions_evaluated`, `robust_feasible`, `launches`;
  `run_summary.json` gains `first_robust_feasible_eval_count` next to the nominal `first_feasible_eval_count`
  (spec section 9: the scheduler's receipt of a robust-feasible result); `aggregates.py` CSVs gain the same columns.
* **W6 Best design.** `best_design.py`: robust-feasible beats nominal-feasible beats infeasible; within a class the
  existing rules; the recorded selection rule text says so.
* **W7 Frontend.** A "Test conditions" module in the right column after RL network (plan 6.1): the corner table with
  a checkbox per corner, the policy choice, β, the cost line "1 launch per evaluation, up to 1 + K; budget E evaluations
  → at most L launches" (updates on edit, no timer), Launch cap = the existing `max_spectre_launches`, one plain line
  plus a closed `<details>` with the verdict rule and the limits. Specs tab: the "judged at" column (W2). RL network
  block: fact rows "Input v2", a saved model's "Reward" and "Trained at". Run status: nominal / corners k of K / robust
  verdict per evaluation; best design "robust at N conditions" or "nominal only". Follow the UI rules: modules fold
  but start open and remember their state, an error mark when folded, no new selector that duplicates an existing one,
  short captions with the detail as text beside them. Hermetic check `frontend/scripts/test_conditions_check.mjs` on
  the shared harness (fixtures; safe against 8765).
* **W8 Corner check tab.** Unchanged in behaviour; it reads `MOCK_CORNER_SHIFT` from the backend (E5).

### D — docs and the record

* **D1** A new page `docs/reward-v2.md`: what the reward computes now (R1–R5 and S1–S3 in plain words, with one worked
  example and the plan's (1, 0, 0) vs (0.4, 0.4, 0.4) example for the shape settings),
  the input layout (N1) and the operating-point block (P1, P2), how a candidate is evaluated (E3), the limits (five corners are a sample; 0.9 V is a project
  choice; nothing verified on real Spectre in this increment), and the commands of the gates (section 5).
* **D2** `docs/decisions.md`: a new entry "Reward v2: worst case across test conditions (2026-09-24)" in the style of
  the last entries: the user's decision (section 1, quoted), old digest `aa987cf0…` → new digest (full hash), what
  changed, what stayed byte-identical, the gates and their numbers, cost (zero simulator calls), limits.
* **D3** The workbench record: `docs/workbench-log/7.61-and-later.md` is past the rollover mark (135 kB, entries up
  to 7.83). Apply the index's rollover rule first (entries 7.61–7.80 into `docs/workbench-log/7.61-7.80.md`,
  `7.81-and-later.md` as the new open file, the two index rows changed) unless a session did it meanwhile; then append
  entry **7.84** (next free number — check the index table AND the open file) and its index row.
* **D4** `docs/workbench.md`: a section "Test conditions" (W7) and one paragraph in "Corner check" (W8).
* **D5** `CLAUDE.md` "Hard rules": the digest sentence stays; add one line that the reward is versioned
  (`reward-v2`) and that `docs/reward-v2.md` defines it.
* **D6** The skill references: `.agents/skills/analog-optimizer/references/pvt-monte-carlo.md` gets a dated
  paragraph that PVT-aware training exists (skip-on-fail, worst case), still unverified on real Spectre.

## 5. Acceptance: gates and tests

All gates run without a simulator. Numbers in the record are re-derived from the run, never copied from a plan.

* **G1 Reward identity on the M6 evidence** (the strongest regression). New script
  `examples/check_reward_identity.py` (new file; do not edit the pinned audit scripts) walks the M6 real pilot at
  `artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/{opamp,ldo,vco}` (layout: see
  `examples/audit_real_cross_category.py::audit_fold`; read only, scoped walk), rebuilds each fold's specs from
  `suite-protocol.json`, and for every completed candidate with `status == 'ok'`, `evaluation_valid` and a recorded
  `reward`, recomputes the reward with the new evaluator in nominal mode (`evaluate()` and `evaluate_conditions([one])`)
  from the saved metrics / units / validity. Expected: **2,811 candidates compared, 0 differences** at
  `abs_tol=1e-12`; the script prints the count and writes `artifacts/local/reward-v2-identity.json`. If the journals
  of the 28 requalification and 38 qualification packages carry rewards, include them and report their counts too.
* **G2 v1 ⊆ v2 input.** `tests/test_input_cache.py` / a new `tests/test_spec_inputs_v2.py`: for observations without
  conditions, the v2 vector restricted to the v1 positions equals a frozen in-test copy of the v1 `context_features`
  (bit-exact); width = 21N + 11; the objective flags follow `MetricSpec.objective`.
* **G3 Evaluator properties** (`tests/test_specs.py`): `evaluate_conditions([x]) == evaluate(x)` bit-exact; worst-case
  ≥ nominal violation per spec; reward in [−1, 0] (β = 0) and ≤ β with β > 0; success needs every evaluated condition;
  R4(b) dominates; `nominal_only` specs ignore corners; validation errors for two objectives / objective without the
  needed bound / β outside [0, 1].
* **G4 Environment** (`tests/test_sizing_env.py` with the synthetic backend): `off` = today's journal fields plus the
  new labels; `after_nominal` runs corners only after a nominal pass (count launches: 1 + K exactly when the nominal
  passes, 1 otherwise); `always` runs 1 + K; a corner infrastructure failure truncates and records every condition; a
  corner `invalid_design` gives R4(b) without termination; reset never runs corners; restoration unchanged; the journal
  and the observation agree (`from_step` accepts, a tampered reward or a dropped condition is refused).
* **G5 Replay / recorder / checkpoint** (`tests/test_recording.py`, `tests/test_graph_sac.py`): `conditions` round-trip
  through the store; a transition with corners validates and its fingerprint changes with `conditions`; a v2 learner
  saves and loads; the next sampled update reproduces exactly after reload (the existing audit pattern); a v1
  checkpoint file (a fixture written by the test with the old contract keys) is refused with the sentence of O5.
* **G6 Adapters against fakes** (`tests/test_bridge_adapter.py`, `tests/test_native_preparation.py`): `derive_netlist`
  makes no bridge call (the fake records every call), the derived deck carries section / temperature / supply of the
  corner and the original export stays byte-identical; `run_simulation` accepts the derived artifact and refuses a
  tampered one; `NativeCandidateBackend.prepare_candidate` still refuses a non-nominal condition.
* **G7 Workbench end to end on MOCK** (`tests/workbench/`): a run of `synthetic:gpdk045_ota5` with two corners on
  and `after_nominal`, scratch settings (`GATOR_WORKBENCH_SETTINGS_DIR`), through the engine: the metrics table has
  rows per condition, `evaluations` shows launches and robust verdicts, the run summary has both first-feasible fields,
  Save now / resume works, the compatibility report names the reward and input versions; a configuration with the
  defaults keeps its task and config hashes (compare against a hash recorded before the change); corners on a task whose
  profile refuses them is a blocker in words; hermetic browser check of W7 passes.
* **G8 Full suite** green: `OMP_NUM_THREADS=1 ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist load` on a
  clean snapshot of the tree (`git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - | tar -xf -
  -C /tmp/gator-check` with an absolute `PYTHONPATH=/tmp/gator-check/src`), report the counts; `npx tsc --noEmit`
  clean.
* **G9 Digest recorded**: `source_digest()` before and after, in D2 and in the 7.84 entry; `src/analog_optimizer/`
  edits limited to the files this brief names (list them in the entry).

* **G10 Operating points** (`tests/test_pyg.py`, `tests/test_graph_sac.py`, `tests/test_sizing_env.py`,
  `tests/workbench/`): the mapping `XU1.M1` <-> `XU1/M1`, unmatched keys reported, devices without an entry masked (a
  non-MOS device such as the two-stage OTA's `CC` has mask 0); tensor shapes `[N_dev, 12]` with the normalization and
  one-hot region flags, `[N_dev, 0]` when off; the encoder's `state_dict` keys identical to today's when off and a
  forward pass of all five encoders when on; with a fake backend returning operating points the observation carries
  them (nominal only), the recorder round-trips them, the transition validates and the input-cache key changes with
  them; on the synthetic backend `operating_points is None`; a configuration with the flag off keeps its hashes; the
  compatibility sentence; the hermetic browser check covers the checkbox.

* **G11 Reward shape** (`tests/test_specs.py`, `tests/test_sizing_env.py`, `tests/test_graph_sac.py`,
  `tests/workbench/`): at the defaults `evaluate()` and `evaluate_conditions()` are bit-identical to G3's numbers and
  G1 passes unchanged; `compressed`: v(0) = 0, v(1) = 0.5, strictly increasing, below 1, and R4(b) still gives 1 and
  dominates; λ: λ = 0 identical, reward in [−1, 0], non-increasing in every violation, 0 iff every active spec is met,
  a fully violated hard spec gives reward ≤ −λ, and the plan's example ranks (0.4, 0.4, 0.4) above (1, 0, 0) at
  λ = 0.5 and below it at λ = 0; γ: the term is 0 unless successful, in [0, γ], takes the smallest margin over the
  evaluated conditions, ignores corners for a `nominal_only` spec, leaves the objective spec out when β > 0, the
  range is [−1, β + γ], an unsuccessful evaluation scores < 0 with a margin term of 0 for every setting, and a
  successful one with every active spec met scores in [0, β + γ]; the
  package's `spec_margin` equals the tab's former `_margin` on the tab's fixtures; the environment passes the settings
  through and the journal carries them; a transition validates with its recorded settings and a tampered one is
  refused; a checkpoint records `reward_shape` and the compatibility sentence names a difference; a configuration with
  the defaults keeps its task and config hashes; `min_margin` round-trips through the tables; the hermetic browser
  check covers the three controls.

## 6. Order of work and commits

1. Read (section 2). Record `source_digest()` and the task / config hashes of a default configuration before touching
   anything (G7, G9).
2. R1–R8 and S1–S4 with G3 and G11 (evaluator first, in isolation).
3. O1–O2, N1–N3 with G2; then O3–O5 with G5; then P1–P6 with G10.
4. E1, E3–E6 on the synthetic backend with G4; E4 on the adapters with G6; E7–E8.
5. G1 (the identity script) — run it as soon as step 2 exists and again at the end.
6. W1–W6 and S5 with G7 (Python side), then W7–W8 and S6 with the hermetic browser check.
7. D1–D6, G8, G9.
8. Report (section 8). Commits only on the user's word, then: commit A = `src/analog_optimizer/` + `tests/test_*.py` +
   `examples/check_reward_identity.py` + `configs/gpdk045_corner_speeds.json` + `docs/reward-v2.md` +
   `docs/decisions.md` ("Optimizer: reward v2 - worst case across test conditions (record 7.84)"); commit B = the
   workbench, frontend, `docs/workbench.md`, the record. Explicit paths in both.
9. Only if everything above is done and the user agrees: the v1→v2 migration tool `examples/migrate_context_v1_to_v2.py`
   (zero rows for the new columns, re-ordered old ones, identical outputs on nominal observations, a test with a small
   v1 fixture).

## 7. Defaults chosen for the plan's open decisions

Chosen here so that the work does not stall; the user may change any of them, and the record must say which applied.

| Decision (plan section 8) | Default in this brief |
| --- | --- |
| 8.1 bundle generalization levers | No — reward, observation, input v2 only |
| 8.2 objective term | Field and β in v2; β = 0 by default |
| 8.3 design-failure attribution | Not in scope; today's −1-and-terminate branch untouched |
| 8.4 corner set | All screening corners selectable; none on by default |
| 8.5 budgets | None: no simulation in this brief |
| 8.7 Monte Carlo | Reserved input columns only; no execution, no reward |
| 8.8 UI placement | Plan section 6.1–6.4 as written in W7 |
| 8.9 migration tool | Last, optional (step 9) |
| operating points as input (added 2026-09-26) | Available to every run; off by default so that existing configuration hashes stay; the record names the runs that used it |
| 8.10 reward shape (added 2026-09-26) | Built (S1–S6); all three settings off by default, so existing rewards and configuration hashes stay; the stage-3 MOCK arms choose the run defaults later |

## 8. Reporting back

* The 7.84 entry and the decisions entry carry: files changed under `src/analog_optimizer/` (exact list), old / new
  digest, the gate results with their numbers (G1 count and differences, G8 counts and duration, G7 hash comparison),
  what was NOT done from this brief and why, and what remains unverified (everything on real Spectre).
* Findings about the plan or this brief (a requirement that contradicts the code, a better rule) go into
  `artifacts/local/reviews/astra-reward-v2.md` (git-ignored) with the requirement id, and are summarized in the entry.
* Say plainly when a gate fails; never relax a gate to pass it.
