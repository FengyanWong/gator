# Plan: a finalist Monte Carlo check at reduced cost, and its box in Run configuration

**Status: PLAN.** Nothing here is built.
* Drafted 2026-09-29 by the session "Chat analog design bench review" (status record 7.103) on the request "... add monte
  carlo to some recommended runs with reduced resources needed and add the option box in run configuration".
* Redrafted the same day without the gm/ID starting design, on "redraft the plan to remove the gm id start" (record
  7.104). It was `plan-gmid-start-and-monte-carlo.md` before.

Every Spectre call below is a budget you authorize at the time. No stage edits `src/analog_optimizer/`.

## 0. In plain words

* **What it checks.** After a run, the few best designs are simulated again with random transistor mismatch (Monte
  Carlo), to see whether they still meet the specs that mismatch actually moves.
* **Where it saves.**
  - **Designs:** only designs that already passed the Corner check (or, on a circuit without corners, the run's best
    nominal designs, marked as judged at nominal).
  - **Specs:** only the specs mismatch moves materially: an output level or offset, a regulation error, PSRR. Gain,
    bandwidth, phase margin and power move far more with corners, so they are not judged.
  - **One job per design:** a single Spectre launch per design at its worst corner, with only the analyses those specs
    need.
  - **Fixed seed:** every design sees the same samples.
  - **Samples:** 32 first, and 68 more only when the result is borderline.
* **At most per run:** 3 designs, 6 launches, 300 samples.
* **The box.** A "Checks after the run" part in Run configuration: Corner check and Monte Carlo on or off, and one cost
  line. The Start press authorizes the run and its checks together.
* **Budget before any real use:** 2 Spectre calls, to qualify the Monte Carlo reader.

## 1. What exists today (facts, with the code; line numbers at commit 73f1668)

**Corner check** (`src/gator_workbench/corner_check.py`, record 7.62).
* **How it runs:** a detached worker with routes `/api/runs/corner-check/{plan,start,status,stop}`. It asks "Authorize N
  simulations?" and restores the cell and reads it back.
* **Which designs:** at most 3 nominal-feasible ones (`MAX_DESIGNS`), identical widths counted once, ranked by the largest
  smallest margin.
* **What it records per design:** disposition, passed / failed corners, `worst_case_metrics` (value and `corner_id` per
  spec), `min_margin`, and a nominal repeat compared at rel 1e-6.
* **Where it applies:** only profiles that accept corners, today `real:gpdk045_ota7` (and MOCK). The LDO, VCO, generated
  and ngspice profiles refuse them (`backends/gpdk045_ldo.py:31-34`, `gpdk045_vco.py:35-38`, `generic_profile.py:127-130`).

**Monte Carlo** exists as interfaces only.
* **Interfaces:**
  - `MonteCarloConfig(samples, seed ∈ [1, 2^31-1], variation mismatch|process|all, model_section='mc')`
    (`backends/conditions.py:42-60`), allowed only with the purpose `mc_validation` (`:75-76`);
  - `MonteCarloResult`, every sample with its index (`backends/backend.py:85-114`);
  - `run_monte_carlo()`, which raises `UnsupportedCapability` (`:160-162`).
* **Refusals:** every analyzer refuses MC (`measurements/opamp.py:33-34`, `ldo.py:80`, `vco.py:109`), and so does the
  environment (`envs/sizing.py:394-395`). `configs/gpdk045_conditions.json` says `monte_carlo_execution_implemented:
  false` and `post_validation.monte_carlo: null`.
* **The bridge** (updated to 168943c in 7.103) reads sweeps (`spectre/parsers.py:200-269`) but has no Monte Carlo reader.
  `psf.result_file` expects exactly one match (`spectre/psf.py:24-40`), so per-sample results must be picked explicitly.

**GPDK045 statistics** (read on the VM, 2026-09-21).
* **Mismatch** statistics are included by every standard section (tt/ff/ss/fs/sf/mc), so mismatch Monte Carlo can run at
  any corner. **Process** statistics exist only in `mc`.
* **Pelgrom coefficients:** σ(Vth) ≈ 0.94 mV·µm (NMOS) and 1.48 mV·µm (PMOS). MIM capacitors have mismatch; resistors,
  diodes and bipolars have process variation only.

**Specs of record.** No task has an offset or CMRR spec.
* **OTA7** (`configs/gpdk045_ota7_transfer.json`): gain ≥ 53.3 dB, UGB ≥ 3.24 MHz, phase margin ≥ 30°, power ≤ 3.24 µW,
  `output_dc_v` ∈ [0.3, 0.5] V, one downward crossing.
* **LDO** (`configs/m6_real_cross_category.json`): power, Iq, line and load regulation, `ldo_psrr_1khz_db` ≥ 35,
  step deviation, tail ripple, `ldo_output_error_v` ≤ 7.5 mV.

**Run configuration and the Start question.**
* **Panel:** `RunPanel` in `frontend/src/panels/Right.tsx` (`<Module id="run" title="Run configuration">`, line 266),
  with "Training conditions" at 284 and a launches table at 294-298.
* **Start dialog:** asks only for the evaluation count (`App.tsx:113-115`).
* **Adding a field without moving hashes:** a sub-model with defaults, popped in `schema._hashed` when it equals the
  default (as `run.reward` / `run.conditions` are). The page omits it at the default, as it does for `vocabulary`
  (`Right.tsx:167-172`).
* **Resume:** a resume refuses changes to reward / conditions / operating points (`runs.py:403-406`).

## 2. Monte Carlo for recommended finalists

### 2.1 Which designs, which specs, and a warning

* **Designs.** When the circuit has corners, only designs the Corner check ACCEPTED (every corner passed), at most 3, in
  order of their smallest corner margin. A design that fails a corner needs no Monte Carlo to be rejected. When the
  circuit has no corners yet (the LDO today), the run's nominal-feasible designs are chosen the way the Corner check
  chooses them, and the result says "judged at nominal only".
* **Specs.** A spec is judged under Monte Carlo only if mismatch moves it materially. The default table, by result name:

  | Judged | Not judged (mismatch moves them far less than corners do) |
  |---|---|
  | `ldo_output_error_v`, `ldo_psrr_1khz_db`; an output level or offset measured in closed loop; a mirror's current accuracy | gain, UGB, phase margin, power, crossings, regulation, step response; `output_dc_v` of an open-loop bench (below) |

  For the LDO: an error-amplifier offset of about 1.4 mV × (1 + RUP/RDN) = 1.33 is about 1.9 mV σ at the output, against
  a 7.5 mV limit: about 4σ of room, so a real question.
* **Warning, OTA7.** Its bench measures `output_dc_v` open loop. The window of ±0.1 V at the output is only about
  ±0.22 mV at the input (gain ≈ 460 V/V), while σ(Vos) is about 1-1.4 mV. That is a hand estimate from the Pelgrom
  coefficients, with the input pair at 4 × 0.5 µm and the PMOS mirror at 8 × 0.5 µm, each contributing about 1 mV. About
  9 samples in 10 would fail the spec whatever the design.
  - **So:** the spec is not judged. OTA7 then has no judged spec left, and "recommended" skips it.
  - **Unless:** Monte Carlo gets a bench with a DC servo loop (decision 3).

### 2.2 Qualification (2 Spectre calls, the LDO at nominal)

* **(1) An 8-sample job:** `montecarlo variations=mismatch numruns=8 seed=12345 { <the analyses of the judged specs> }`.
  It proves the output layout through the bridge (files or folders per sample), that the samples differ, and that each
  sample is measured.
* **(2) Identity job:** the same deck with `variations=process` at tt, where tt carries no process statistics, so each
  sample must equal the deterministic nominal at rel 1e-6.
* **Both are gates.** Nothing else runs before they pass.

### 2.3 The job per design, and how its cost is kept down

* **Setup:** one Spectre launch at the design's worst corner (the corner of its smallest margin in the Corner check;
  nominal when the circuit has no corners), mismatch only.
* **Only needed analyses:** the `montecarlo` block holds only the analyses the judged specs need (e.g. the LDO's DC and
  the 1 kHz AC point, not its load-step transient).
* **Fixed seed:** the same for every design and every run of a task, so designs are compared on the same samples (common
  random numbers).
* **Sequential sampling:** 32 samples first.
  - **Clear pass:** no sample fails, and every judged spec keeps mean − 3σ (upper limits: mean + 3σ) inside its limit.
  - **Clear fail:** 4 or more of 32 samples fail.
  - **Otherwise borderline:** one continuation of 68 samples. `firstrun=33` with the same seed gives samples 33-100 of
    one 100-sample job. The decision is made at 100: the yield count with its 95 % Wilson bound, plus mean ± 3σ.
* **Limits:** at most 100 samples in 2 launches per design, and 6 launches / 300 samples per run.
* **What the cut costs.** The robust-reward plan of record (2.6) and `docs/brief-reward-v2.1-for-astra.md` (section 9)
  give each finalist 300 samples: 0 failures in 300 bounds the failure rate at about 1 % at 95 % confidence. 0 failures in
  100 bounds it at about 3 %. Anyone who needs the 1 % statement sets "up to" to 300 (decision 2); the seed and the
  stream stay the same.
* **Verdict** (decision 1): mean ± 3σ of every judged spec, with the yield count reported. That is the same rule the
  reward-v2.1 brief sets for any later Monte Carlo in training.
* **Compared with Analog Design Bench's checker:**

  | | His checker | This plan |
  |---|---|---|
  | Launches | one ngspice process per sample | one launch per design (two if borderline) |
  | Samples | fixed 20-50 | 32, or 100 only when borderline |
  | Condition | nominal only | the design's worst corner |
  | Designs | every submission | only designs that passed every corner |
  | Specs | every one | only those mismatch moves materially |
  | Analyses | every one | only what the judged specs need |

### 2.4 Where it lives (workbench only)

* **Module:** `src/gator_workbench/monte_carlo.py`, a sibling of `corner_check.py`.
  - **Worker and routes:** a detached worker (`python -m gator_workbench.monte_carlo`) with routes
    `/api/runs/monte-carlo/{plan,start,status,stop}`.
  - **Files:** `<run>/monte_carlo/<id>/`, holding request.json, results.jsonl (one line per sample) and summary.json
    (one per design).
  - **Safety:** the bridge session lock, and restoration + read-back exactly as the Corner check does.
* **The deck and the reader:** a workbench profile subclass (the real-run code is duck-typed on the profile,
  `generic_profile.py:10-13`).
  - It accepts the `mc_validation` condition and wraps the judged specs' analyses in the `montecarlo` block.
  - It splits the output per sample and measures each sample with the package's own analyzer, as if it were one
    simulation. Whether each analyzer takes that is part of the qualification.
  - It returns the package's `MonteCarloResult`. Computed specs are extended per sample (`SpecPlan`, `spec_equations.py`).
  - Its grading is its own, because `summarize_corners` refuses Monte Carlo.
* **A package edit is needed only for Monte Carlo inside training** (stage 5b of
  `plan-robust-reward-and-network.md`), which this plan does not do.

### 2.5 Results

* **The tab:** a "Monte Carlo" part in the Corner check tab, one row per design: condition, N, verdict, and per judged spec
  mean / σ / worst sample / number of failing samples. Data only, exportable like the other tabs.
* **Plain words** for a design judged at nominal only, and for a task whose specs are all "not judged": "Nothing to
  judge: no spec of this task is moved much by mismatch" instead of a pass.

## 3. The box in Run configuration

**Place.** The Run configuration module (`Right.tsx`, `RunPanel`), below the "Training conditions" select:

```
Checks after the run
  Corner check    [ Off | Finalists: up to 3 designs x 5 corners ]       only circuits with corners (OTA7 today)
  Monte Carlo     [ Off | Recommended finalists | Every accepted finalist ]
                  mismatch, 32 samples, up to [100] when borderline; verdict [ mean ± 3σ ]; seed [12345]
                  Judged: ldo_output_error_v, ldo_psrr_1khz_db     Not judged: the other specs (mismatch moves them little)
  This run costs  up to 100 evaluations x 1 launch + Monte Carlo 6 launches (<= 300 samples)
```

**Schema.** One new sub-model, `run.after_run`:
* **Fields:** `corner_check: off | finalists`, `monte_carlo: off | recommended | all_accepted`, `samples` (32),
  `escalate_to` (100), `rule: mean_3sigma | yield_90`, `seed`.
* **Hashes:** popped in `_hashed` when it equals its default, so every existing configuration keeps its hash, and the page
  omits it at the default, so an older backend never sees an unknown key.
* **Resume:** it may change on resume, since it acts after the run.
* **No collision:** it touches neither `run.conditions` nor `run.reward`, which the reward-v2.1 brief extends in the same
  part of `Right.tsx` (`ConditionsConfig.policy: after_nominal`, `RewardConfig.nominal_gate_band` / `objective_shape`).
  Whoever builds second re-reads the file and keeps both.

**Readiness rows (free).**
* "Monte Carlo is on, but no Monte Carlo reader is qualified for this circuit yet".
* "Monte Carlo is on, but no spec of this task is judged under Monte Carlo: it will not run" (OTA7 today).
* "Not judged under Monte Carlo: output_dc_v (open-loop bench)".
* "Judged at nominal only: this circuit has no corners yet" (the LDO).
* "Monte Carlo judges the designs the Corner check accepts: the Corner check is turned on with it" (circuits with corners).

**Authorization.**
* **One question at Start:** the dialog asks "Authorize up to E evaluations, C corner simulations and M Monte Carlo
  launches (≤ S samples)?".
* **No later prompt:** the checks start from that press only, never by themselves later. A run that ends with no accepted
  design runs no Monte Carlo and says so.
* **Finished runs** get the same check from a button on the Corner check tab, with its own question (decision 6).

**Tests.**
* The hash pins (an old configuration keeps its hash, the `test_wb_retired_columns.py` pattern).
* Validation and readiness rows.
* The cost line.
* A hermetic browser check.

## 4. Stages, gates, budgets

| Stage | What | Package digest | Spectre calls | Gate |
|---|---|---|---|---|
| 0 | Your decisions (section 6) | - | 0 | answered |
| M1 | Monte Carlo deck + per-sample reader; qualification on the LDO at nominal | unchanged | 2 | samples differ; identity at rel 1e-6; every sample measured |
| M2 | Worker, grading, results in the Corner check tab | unchanged | 0 to build (MOCK spreads its toy score per sample) | tests, browser check |
| M3 | The box, readiness rows, the Start question, the cost line | unchanged | 0 | hash pins, browser check |
| M4 | First real use: the finalists of an LDO run | unchanged | ≤ 6 launches (≤ 300 samples), inside that run's authorized budget | report with the limits |
| R | Record, `docs/workbench.md`, memory | - | 0 | - |

Each stage follows the project loop: freeze, execute, independent audit, full regression, record.

## 5. Risks and limits

* **Statistics:** 32-100 samples resolve yields of about 90-97 %, not 99.9 %, and mean ± 3σ assumes a roughly Gaussian
  spec.
* **Coverage:** mismatch only, at one corner, misses process × mismatch interaction. The worst corner is chosen by corner
  margin, not proven worst under mismatch, and the LDO is judged at nominal only until it has corners.
* **Reuse of the analyzers:** reusing the package's analyzers per sample is unverified; that is what M1 is for.
* **Analyses left out:** a spec whose analysis is left out of the `montecarlo` block (the LDO's step response) is not
  judged under mismatch.
* **The open-loop OTA bench** cannot judge an offset-sensitive output level under mismatch.

## 6. Decisions for you (answer by number)

1. **Verdict:** mean ± 3σ with the yield reported (recommended), or a yield threshold.
2. **Samples:** 32, then up to 100 when borderline (recommended; bounds a failure rate at about 3 %), up to 300 as the
   plan of record has it (about 1 %), or a fixed number.
3. **OTA7's open-loop `output_dc_v`:** not judged (recommended for now; OTA7 then gets no Monte Carlo), or a new Monte
   Carlo bench with a DC servo loop (a new testbench cell).
4. **First circuit:** the LDO at nominal (recommended: it has the specs mismatch moves), or OTA7 at its worst corner
   (plumbing only while nothing of it is judged).
5. **How a spec is marked:** the default table by result name (recommended), or a new "Judged under Monte Carlo" column
   in Specs (under More columns).
6. **When it runs:** after a run from the Start press AND from a button on the Corner check tab for finished runs
   (recommended), or only one of the two.
7. **Budget now:** 2 calls for the qualification on the LDO.
8. **Order:** after the reward-v2.1 work (recommended: both touch the same part of `Right.tsx`), or side by side.

## 7. Not in this plan

* A gm/ID starting design (removed on the user's request, 2026-09-29).
* Monte Carlo inside training.
* Process + mismatch Monte Carlo.
* Corner support for the LDO, VCO or generated profiles (an item of the robust-reward plan).
* Any change under `src/analog_optimizer/`.

**Sources:**
* `docs/plan-robust-reward-and-network.md`: 2.6 (mean ± kσ, common random numbers), section 4 item 7, stages 5a/5b, 6.1
  and 6.5, decision 7.
* `docs/brief-reward-v2.1-for-astra.md`, section 9.
* `docs/workbench.md`: "Corner check".
* Token Zhang's Analog Design Bench checker: per-point text substitution, fixed seeds with `.option seed`, pass rules
  yield ≥ 90 % / mean ± 3σ / every seed, at nominal only.
