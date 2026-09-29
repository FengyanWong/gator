# Plan: OTA7 with a current-reference bias and supply-tracking input common mode

**Status: plan only, 2026-09-29.** The user replaced D7's three original choices with this experiment.
No implementation, task creation, Virtuoso read/write, connection probe or simulation is authorized by this document.
The user will make the new testbench copy in Virtuoso. Implementation approval and a separate five-launch budget
are still required. The completed reward-v2.1 check used 10 launches; its unused allowance is not reused here.

## 1. Purpose and evidence

Create a new OTA7 variant that tests whether a current-derived gate bias and input common mode equal to half the
supply reduce the corner misses, while retaining the existing design targets. Do not repeat the narrow-range
feasibility search, widen the size ranges or relax targets before measuring this variant.

Nine retained designs (the stage A reference and eight stage B steps) show similar misses:

| Condition and metric | Observed miss across the nine designs |
|---|---:|
| SS / 125 °C / 0.9 V gain | 3.661441–3.860192 dB below 53.3 dB |
| SS / 125 °C / 0.9 V unity-gain frequency | 0.969687–0.999504 MHz below 3.24 MHz |
| FS / 27 °C / 1.0 V core power | 1.002168–1.280706 µW above 3.24 µW |

Sources: [stage A](../artifacts/local/reward-v2-real/20260926-qualification-04/stage-a/report.json),
[stage B](../artifacts/local/reward-v2-real/20260926-qualification-05/stage-b/report.json).
These measurements support the user's decision to change the testbench before spending more calls on these ranges.
They are sampled evidence, not an exhaustive mathematical infeasibility proof. The fixed-bias explanation is the
hypothesis being tested. Changing both bias and common mode together will not isolate their separate contributions.

The exported [original testbench](../examples/circuits/gpdk045_ota7.scs) has `VB = 0.4 V`,
`VP = VN = 0.6 V` and `VDD = 1.0 V`. M5 and M7 share VBIAS. Their sources and bulks connect to VSS.
The existing `structure_for_condition` in [gpdk045.py](../src/analog_optimizer/backends/gpdk045.py)
changes only VDD in the circuit structure; model section and temperature change in the deck header.
It expressly retains the absolute input and bias voltages.

## 2. New identity and isolation

Proposed logical task ID: `real:gpdk045_ota7_iref_vcm_v1`. This is a name for the plan, not a registered task.
The exact new library/cell/view identities must come from the user's copied cells before any live access.

The frozen `real:gpdk045_ota7`, `ota7_m5_v2`, `tb_ota7_m5_ac_v2`, their saved task/configuration, targets,
netlists, readbacks, reference measurements and historical evidence remain untouched. New task files, reference
evidence and receipts get new paths and hashes. No old task overwrite, checkpoint-resume bypass or relabeling of
old measurements as results of the variant is allowed.

The user makes the new testbench in Virtuoso. Because the task runtime can write DUT sizes, the runnable variant
must also point to a private DUT copy before it can use that runtime. Merely copying a top-level testbench can
leave its DUT instance pointing to the original cell. Check that reference explicitly; never write through it.
The new DUT copy retains the original seven-MOS core and compensation capacitor. The extra reference NMOS is
in the new testbench. The complete variant graph includes that bias device and its connections.

First qualification uses only the reference sizes: M1/M2 4 µm, M3/M4 8 µm, M5 4 µm, M6 8 µm, M7 2 µm;
all existing lengths, multiplicities, fingers, compensation and load remain as recorded. No sizing search occurs.
If a later task exposes the existing two width groups, it retains their current bounds and M6/M7 ratio; bias
current, reference device and common-mode policy are fixed task settings, not new actions in this plan.

## 3. Bias circuit and nominal-current reference

Remove the ideal 0.4 V source from the new testbench only. Add a GPDK045 NMOS reference device, provisionally
`MREF`, with drain and gate tied to VBIAS and source and bulk tied to VSS. Feed an ideal, fixed reference current
into VBIAS. The gates of M5 and M7 remain connected to this same VBIAS node. The reference NMOS uses the same
NMOS model family as M5/M7, including the active process section at each condition.

The ideal reference current stays constant across all five conditions. VBIAS is a solved operating-point value,
not clamped to 0.4 V and not forced to a fixed fraction of VDD. Do not add corner-dependent current retuning.

The nominal target currents are from the reference design, not the later nominal-passing sized candidate:

| Device | Width / length | Recorded drain current | VGS | VDS |
|---|---:|---:|---:|---:|
| M5 | 4 µm / 1 µm | 1.956361054911864 µA | 0.3999999990 V | 0.2155015751 V |
| M7 | 2 µm / 1 µm | 1.165778491724812 µA | 0.3999999998 V | 0.3732184738 V |

Source: [recorded nominal measurements](../artifacts/local/reviews/astra-reward-v2.1/step6-20260929-01/starting_design_nominal/simulations/a21ff23c76cc4d2995c0d26dd32ec48e/measurements.json).
SHA-256: `13e6e190658cdcec222786421bd30efc01b56975cc377ddefaf57b25cd80f464`.
The final restored nominal run reproduced both currents exactly.

**Current selection is not yet a calibrated value.** A transparent starting proposal is a 4 µm / 1 µm reference
NMOS, fingers/multiplicity 1, with IREF initially anchored to recorded M5 current, 1.956361054911864 µA.
This is a recorded-current seed for review, not a claim that the changed circuit reproduces both currents.
The measured M5/M7 ratio is 1.678158, while their width ratio is 2. In an ideal width-ratio estimate that seed would
put M7 at 0.978181 µA, 16.09% below its recorded current. That estimate is not a prediction of the PDK model.
The recorded drain voltages also differ from the reference diode voltage, and the new input common mode changes
the operating point. One old operating-point sample cannot establish the new circuit's current match.

Before implementation, settle the acceptable relative error for **each** nominal drain current, with the user.
That question is pending. The first of the five launches measures both currents and their signed/relative errors.
If it fails the agreed bias-setup criterion, stop before the four corners and report it. No uncounted calibration,
extra nominal launch, silent current adjustment or second bias network is permitted. A calibration proposal, if
needed, has a separately approved design scope and launch ceiling. Exact simultaneous matching is not promised.

## 4. Input common mode and power boundary

Set both input DC levels to VDD/2 at every condition, retaining the original differential AC stimulus:
VP magnitude 0.5, phase 0°; VN magnitude 0.5, phase 180°. The nominal input DC level therefore changes from
0.6 V to 0.5 V. Check the executed deck and measured VINP/VINN; a changed UI label is insufficient.

**User-approved power decision:** retain the 3.24 µW **OTA-core-only** target and report the bias/reference branch
separately. This preserves the existing measurement boundary: the old op-amp analyzer expressly excludes bias
generator power. Do not silently add the reference branch to `supply_power_w` or drop its consumption from the report.

Use separately measurable supply branches in the proposed testbench:

| Branch | Connection / measurement |
|---|---|
| Core supply `VDD` | Supplies the OTA core; target metric remains −VDD × I(VDD), with verified sign convention. |
| Reference supply, provisional `VDD_BIAS` | Same voltage as VDD at every condition; supplies the ideal current reference into MREF. Measure its rail draw separately. |
| Reported total | Core power plus reference-branch supply power, explicitly labeled diagnostic rather than the unchanged target. |

For the proposed two-terminal current source fed from VDD_BIAS, branch supply power includes the entire branch;
do not substitute VBIAS × IREF, which measures only the diode dissipation. The reference remains ideal: this is
not a model of a realizable reference generator or its additional overhead. Preserve separate rails in the
exported connectivity and check that the reference branch is not accidentally counted in the core source.

## 5. Same specifications and explicit five-condition plan

Copy the values and scales into the new task from [targets of record](../configs/gpdk045_ota7_transfer.json):

| Metric | Hard target | Scale |
|---|---|---:|
| Gain at sweep start | ≥ 53.3 dB | 1 dB |
| Unity-gain frequency | ≥ 3.24 MHz | 1 MHz |
| Phase margin estimate | ≥ 30° | 10° |
| Core supply power | 0–3.24 µW | 1 µW |
| Output DC voltage | 0.3–0.5 V | 1 V |
| Downward unity crossings | Exactly 1 | 1 |

All six are checked at all five conditions. Do not convert the output window to a supply fraction, reinterpret
phase margin as an STB measurement, change a scale or drop a spec to obtain a pass. Keep the same AC sweep and
measurement equations; add bias/common-mode diagnostics without changing the six existing meanings.

| Launch | Condition | Model | Temperature | VDD and VDD_BIAS | VINP = VINN, DC |
|---:|---|---|---:|---:|---:|
| 1 | nominal | tt | 27 °C | 1.0 V | 0.50 V |
| 2 | ss_hot_low | ss | 125 °C | 0.9 V | 0.45 V |
| 3 | ff_cold_high | ff | −40 °C | 1.1 V | 0.55 V |
| 4 | fs_nominal | fs | 27 °C | 1.0 V | 0.50 V |
| 5 | sf_nominal | sf | 27 °C | 1.0 V | 0.50 V |

These are the existing engineering screening points, not an exhaustive PVT set. Model files and their existing
provenance stay pinned. Each request, deck, result and measurement carries the same condition identity.

This is a reference-design qualification, not `after_nominal` training: an ordinary nominal performance-spec miss
does **not** skip the corners. Subject to passing the agreed bias-setup check and a usable nominal measurement,
run all five conditions so the requested miss table is complete. No learner updates, checkpoint loading or MC.

## 6. Planned implementation boundary, after separate approval

The existing code cannot already run this new variant merely by changing its task name:

- Built-in OTA7 validates its frozen topology/testbench and only changes VDD in condition preparation.
- Generated workbench profiles currently refuse non-nominal conditions.
- Training-corner capability is currently restricted to the original OTA7 task.
- The old measurement notes say “ideal bias voltage source”; the variant needs accurate bias-power and OP reporting.

Plan a narrowly scoped, separately identified workbench profile using the existing backend interfaces. Its
condition preparation handles VDD, VDD_BIAS and both input DC levels together; it validates constant IREF, a
diode-connected MREF and unchanged core geometry. Its graph/mapping explicitly includes the reference NMOS and
current source (the shared graph vocabulary already contains `isource`). It reports the extra operating points
and branch powers, with a dedicated reference receipt and task capability. Do not enable corners for every
generated task or change the original OTA7 transformation.

Keep implementation outside `src/analog_optimizer/` where the existing profile hooks permit it. That remains a
design constraint, not a claim that this adapter is implemented. If implementation needs a package change, stop
and obtain separate scope/digest approval; the prior A1–A8 authorization does not cover this variant.

Offline validation before physical execution must cover variant topology and supply/current-source signs,
the five explicit condition transformations, new/old task identity separation, unchanged original target hashes,
separate power boundaries, correct nominal-current diagnostics, complete job accounting and original-cell write
refusal. Then run the repository's full suite with scratch settings and TypeScript if frontend code changes.
Those tests are not conducted during this documentation-only turn.

## 7. Readiness, approval and launch ceiling

Order of the future work:

1. Resolve the nominal-current tolerance and approve this plan/implementation scope. The core-only power decision
   is already approved and must not be asked again.
2. User supplies the exact identities of the new copied testbench and private DUT. Freeze permitted write targets.
   Prepare and review any proposed schematic edits; never discover write targets by guessing names.
3. After explicit write approval, implement only that copy's current-reference and common-mode setup, read back
   its connections/CDF values, export and freeze the reference task. Preserve original-cell and pinned-file hashes.
4. Complete offline validation and publish the concrete task/configuration/deck manifest and IREF setting.
5. **Ask:** “Do you approve at most five Spectre launches for this new OTA7 variant's frozen reference design,
   one nominal plus ss_hot_low, ff_cold_high, fs_nominal and sf_nominal, with no retries?” Do not execute until
   the user approves that separate budget. Plan approval alone is not simulation approval.
6. Run the workbench connection check first after authorization. Stop on a failed connection; do not start or
   restart a tunnel/daemon. If license status is unknown, disclose it in the launch manifest and follow the user's
   applicable explicit authorization; never treat unknown as a verified license.
7. Reserve the five-job ceiling before dispatch, run nominal first, check bias setup, then the four conditions
   in the stated order. Record durable launch intents, results, charged calls and unused reservations. No retries,
   no replacement candidates and no spending the earlier OTA7 check's remaining allowance.

Five means **five total simulator launches**, including the new nominal reference. There is no extra baseline,
calibration sweep or sixth restoration simulation. Keep PVT changes in immutable job-local decks and do not
change device sizes during this check. Verify the new cell's frozen reference snapshot and original-cell protection
on completion. If the implementation cannot preserve that state without another simulation, stop and revise the
plan/budget before executing; never hide an extra confirmation call inside the five.

Infrastructure failures, uncertain launches, unsupported topology/conditions, wrong units, missing required
measurements or a failed bias-setup criterion stop the check and leave remaining calls unused. Report incomplete
coverage honestly. A failed design specification with valid measurements is reported, not retried or tuned away.

## 8. Report, then decide about corner-specific limits

The first report contains the five-condition table of all six hard metrics, exact bounds, signed headroom/miss,
validity and nominal/full-plan verdicts. Also report, for every condition:

- M5/M7 drain currents and relative errors against today's recorded nominal references; MREF current and VBIAS.
- VINP/VINN DC levels, actual VDD/VDD_BIAS and the input common-mode check.
- Core power, reference-branch power and their total, with the target applied only to core power.
- M5/M7/MREF VGS, VDS, VDSAT, region and VDS−VDSAT as diagnostics; no new hard limits are invented.
- Reserved, charged, confirmed, uncertain, unused and retry counts; elapsed time; unique job IDs and deck hashes;
  unchanged original/pinned files and the copied reference state at the end.

Only if the valid completed variant measurements still miss the existing targets, propose corner-specific
limits using those numbers, with any added margin stated and justified. Keep nominal targets and the frozen
original task intact. Show current versus proposed limits and resulting verdicts on the same recorded data,
then ask for approval; no automatic application, no claimed yield and no claim that one design defines all
reachable performance. A bias-setup or infrastructure failure is not evidence for relaxing circuit specs.
If nominal itself misses, identify that separately; loosening corner-only limits cannot repair a nominal miss.

If all five pass, report that reference-design success and do not propose relaxed limits. A later matched-policy
study, other bias calibration, sizing search or Monte Carlo remains a separate request with its own budget.

## 9. Decisions and current status

| Item | State |
|---|---|
| New task; frozen original and pinned files untouched | Required by user |
| Ideal-current reference, diode NMOS feeding M5/M7 gates | Requested; not implemented |
| VCM = VDD/2 at every condition | Requested; not implemented |
| Same six hard targets | Required by user |
| Core-only power target, bias power separate | Approved by user |
| Exact copied cell identities | Needed before live read/write; not needed to draft this plan |
| MREF geometry / final IREF | Starting proposal only; not calibrated or approved as reproducing both currents |
| Nominal-current error tolerance | Asked; awaiting answer |
| Plan / implementation / copy-write approval | Not yet granted |
| Five-launch budget | Proposed; must be asked and approved before execution |
| New variant simulations, code or Virtuoso writes this turn | 0 |

This document and the accompanying decision/report records are the only deliverables of this planning request.
