# What the Graph Transformer learned, and what it carries over (report, 2026-10-07)

The GATOR sizing experiments of 2026-10-05 to 2026-10-07: SAC with a Graph Transformer encoder on six GPDK045 circuits on
Spectre, then one network trained from all recorded experience and tested on new starts and on circuits it never saw.
Charts: the private page https://claude.ai/artifact/SzmRbjD1boc7CpR5axdPvx. Sources: `docs/plan-finetune-vs-scratch.md`
(record 7.229), `docs/plan-general-network.md` sections 12-23 (7.233-7.243, 7.262), `docs/plan-general-seeds-starts.md`
(7.266). Every number is from recorded runs; one seed per arm unless said otherwise.

## In three sentences

1. **It learns on four of six circuits.** From scratch, the amplifiers and the VCO end their 800 launches with 92-95 % of
   the last 266 designs passing; the ring oscillator stays at 12-33 %; the two LDOs pass nothing at their original -5 dB
   high-frequency PSRR row, and only with a relaxed row (-3 / -2.3 dB) does any model pass at all.
2. **Experience carries to a new start of the same circuits.** A model of the same circuit, or one general network trained
   offline from all 22 recorded runs (17,124 evaluations, 41-metric registry), passes 83-93 % of its first 100 own
   proposals on ota5t, ota7t_w and vco_lin_c where scratch passes 0-11 %; on ring3 and the LDOs the gain is real but
   below the pre-set 30-point bar, so the fixed rule says "3 of 6" every time.
3. **To circuits it never saw: one yes, two no.** Negative on OTA8m (a variant of a pooled circuit), small on a folded
   cascode of our own (whose fold sits in a pooled LDO's error amplifier); on a published telescopic cascode with no
   relative in the pool the loaded network passes 73 % of its first 100 own proposals against 8 % from scratch and ends
   at 100 % against 89 %. One seed.

## How the runs are read

800 Spectre launches per run: 8 random warm-ups, then the policy's own proposals, the start re-evaluated at every episode
reset. Early share = passing designs among designs 9-108; last third = passing share of the final 266. Criteria fixed
before each study: C1 a 30-point early head start, C2 the last third within 5 points of scratch or above, C3 the LDOs pass
at the relaxed row, C4 no loss of the head start while training. Recipes for a loaded model: "anti-drift" (learning rate
2e-4, two updates, half of every batch from the archive) or the scratch recipe (1e-3, eight updates, target-only).

## Head start: own model (start B, 7.229) and general network (start C, 7.262), scratch recipe

| Circuit | Scratch early / late (B) | Own model early / late (B) | Scratch early / late (C) | General early / late (C) |
|---|---|---|---|---|
| ota5t | 11 % / 95 % | 90 % / 96 % | 2 % / 95 % | 88 % / 95 % |
| ota7t_w | 1 % / 95 % | 93 % / 95 % | 0 % / 93 % | 88 % / 94 % |
| ring3 | 2 % / 33 % | 16 % / 32 % | 4 % / 12 % | 24 % / 30 % |
| vco_lin_c | 5 % / 80 % | 89 % / 95 % | 4 % / 92 % | 83 % / 95 % |
| ldo1_rgcn | 0 % / 0 % | 27 % / 7 % | 0 % / 0 % | 2 % / 8 % |
| ldo2_rgcn | 0 % / 0 % | 4 % / 12 % | 0 % / 0 % | 0 % / 14 % |

The general network gives the same head start as the circuit's own model. The recipe does not make the head start
(anti-drift 83 / 91 / 24 / 80 / 4 / 0 %, scratch recipe 88 / 88 / 24 / 83 / 2 / 0 %); it decides the late phase: on ring3
and ldo1 the slower recipe with rehearsal ends at 63 and 37 % against 30 and 8 %. C1 on three circuits in every study;
C2 and C4 on all six.

## Circuits the network never saw

| Circuit | Zero-shot probe (own proposals) | Scratch early / last third | General early / last third | C1 / C2 / C4 |
|---|---|---|---|---|
| OTA8m, anti-drift recipe (Codex, 7.241) | 0 % | 1 % / 92 % | 0 % / 8 % | fail / fail / pass |
| OTA8m, scratch recipe (7.243) | 0 % | 1 % / 92 % | 0 % / 82 % | fail / fail / pass |
| Folded cascode, own design (7.262) | 21 % | 13 % / 93 % | 20 % / 95 % | fail (+7) / pass / pass |
| Telescopic cascode, Analog Design Bench port (7.262) | 2 % | 8 % / 89 % | 73 % / 100 % | pass / pass / pass |

Zero-shot probes on the pooled circuits' start-B tasks (own proposals): ota5t 70 %, ota7t_w 95 %, ring3 6 %, vco_lin_c
95 %, ldo1 4 %, ldo2 0 %. The pattern fits what the network holds: a map from a circuit's graph and goal rows to sizes
it has seen work. Where the map covers the circuit the frozen network already passes a fifth or more of its proposals;
where it does not (the telescopic) the frozen network knows nothing, yet its weights make the adaptation fast.


## The reward where the pass rate says "not learned"

A pass rate is a threshold view. The step reward is continuous: a compressed distance to feasibility plus margin and
objective bonuses once every row is met. Mean reward of the policy's own proposals (resets and random warm-ups excluded):

| Run | Own proposals | Passing | Mean reward, first 100 | Mean reward, last 266 | Change |
|---|---|---|---|---|---|
| ring3: A (original start, scratch) | 751 | 82 | -0.219 | -0.057 | +0.162 |
| ring3: B scratch | 752 | 208 | -0.212 | -0.014 | +0.198 |
| ring3: B own model | 752 | 222 | -0.047 | -0.014 | +0.033 |
| ring3: C scratch | 752 | 76 | -0.170 | -0.080 | +0.090 |
| ring3: C general anti-drift | 752 | 395 | -0.014 | +0.011 | +0.025 |
| ring3: C general scratch recipe | 752 | 245 | -0.020 | -0.022 | -0.002 |
| ldo1: A (original start, scratch, -5 dB) | 1413 | 0 | -0.439 | -0.165 | +0.274 |
| ldo1: B scratch | 749 | 0 | -0.421 | -0.118 | +0.303 |
| ldo1: B own model | 750 | 89 | -0.040 | -0.055 | -0.015 |
| ldo1: C scratch | 752 | 0 | -0.434 | -0.167 | +0.267 |
| ldo1: C general anti-drift | 752 | 155 | -0.075 | -0.013 | +0.062 |
| ldo1: C general scratch recipe | 752 | 34 | -0.110 | -0.058 | +0.052 |
| ldo2: A (original start, scratch, -5 dB) | 1418 | 0 | -0.467 | -0.195 | +0.272 |
| ldo2: B scratch | 749 | 0 | -0.465 | -0.124 | +0.341 |
| ldo2: B own model | 750 | 58 | -0.074 | -0.036 | +0.038 |
| ldo2: C scratch | 752 | 0 | -0.405 | -0.115 | +0.290 |
| ldo2: C general anti-drift | 752 | 87 | -0.111 | -0.026 | +0.085 |
| ldo2: C general scratch recipe | 752 | 80 | -0.061 | -0.048 | +0.013 |
| OTA8m: scratch | 752 | 486 | -0.352 | +0.106 | +0.458 |
| OTA8m: general anti-drift | 752 | 24 | -0.227 | -0.114 | +0.113 |
| OTA8m: general scratch recipe | 752 | 491 | -0.178 | +0.079 | +0.257 |
| folded cascode, first goals: scratch | 752 | 0 | -0.305 | -0.039 | +0.266 |
| folded cascode, first goals: general scratch recipe | 752 | 0 | -0.176 | -0.022 | +0.154 |

Every one of these runs learns: the mean reward rises through the run, by 0.25-0.34 on the LDOs from scratch where not
one design passes, by 0.09-0.20 on ring3, by 0.27 on the folded cascode's unreachable first goals, by 0.46 on OTA8m
from scratch. "Not learned" in the pass-rate sense is "did not reach the goals": the policy moves toward the rows and
stalls under the one it cannot meet. The loaded models start where scratch ends (first 100 proposals at -0.01 to
-0.11 against -0.40 to -0.47 from scratch): the head start seen in the reward; from there they gain little. OTA8m's
anti-drift arm is the one slow learner (+0.11 in 800 designs), the recipe-bound result of record 7.243.

## Caveats

- One seed per arm: the 60-90 point head starts are far outside any plausible seed spread; the 7-point one and the ring3
  / LDO results are not. The seeds-and-starts plan (7.266) turns these into distributions.
- Held-out goals come from each circuit's 64 random designs by a rank rule; on the folded cascode the rule alone asked for
  a phase margin above 90 degrees that no design met, so that row is at the 60-degree floor for both new circuits, and
  their start designs pass by a 1-2 % power margin (resets counted alike in every arm).
- Held-out means an unseen circuit, bench and metric set, not an unseen building block: no pooled amplifier core embeds
  in either new circuit as a labelled subgraph, but LDO2's error amplifier is a folded cascode.
- C1's 30-point bar was set before the first study and kept; the ring3 and LDO gains are reported, and the rule says no.
  "Not learned" in the pass-rate sense means "did not reach the goals": the reward rises in every such run (section above).

## Cost and next

About 36,000 new Spectre launches over two days: 9,600 (own-model study), 15,944 (general network and the OTA8m
follow-up), 10,632 (equal-recipe arms and the two held-out circuits). Open, on the user's word: the seeds-and-starts plan
(24,390 launches, about 11 h) and a second seed on the telescopic cascode (1,600 launches).

<!-- encoder-comparison-section:start -->
## 9. The other encoders through the same stages (added 2026-10-08, running)

Plan 7.256 (record 7.273) runs GraphGPS (the GT block plus a full within-circuit attention in parallel) and the
cross-attention readout (the GT blocks plus one query per parameter group over the nodes) at the same size (48 / 4 / 4)
through stages A (scratch, original starts), C (scratch against that encoder's offline general model on start C) and D
(the folded and the telescopic cascode) on the same six circuits, reward, preset, starts and goals; the GT arms are the
recorded runs above. Rules fixed before the run: A1 last third within 10 points of GT, A2 the 50 % point not later than
GT + 100, A3 an LDO pass at the relaxed row; C1, C2, C4 as in section 2.

**Stage A (complete, record 7.277):** GraphGPS keeps up with GT on all six circuits (ahead on ring3 +14 points and on the
VCO); the cross-attention readout keeps up on five and is slower on the OTA7t width task (50 % point 189 designs later);
GraphGPS's 3 late passes on LDO1 trigger the GT reference runs at the relaxed rows. Parameters: GT 355,157; GraphGPS
469,925; cross-attention 412,325.

| Circuit | GT (last third · 50 % by) | GraphGPS | Cross-attention | Rules |
|---|---|---|---|---|
| ota5t | 95 % · 50 % by 191 | 95 % · 50 % by 176 | 94 % · 50 % by 232 | GraphGPS: A1 yes, A2 yes; cross-attention: A1 yes, A2 yes |
| ota7t_w | 94 % · 50 % by 254 | 94 % · 50 % by 336 | 94 % · 50 % by 443 | GraphGPS: A1 yes, A2 yes; cross-attention: A1 yes, A2 no |
| ring3 | 15 % · 50 % by never | 29 % · 50 % by never | 10 % · 50 % by never | GraphGPS: A1 yes, A2 yes; cross-attention: A1 yes, A2 yes |
| vco_lin_c | 94 % · 50 % by 291 | 98 % · 50 % by 222 | 92 % · 50 % by 361 · 725 (failed) | GraphGPS: A1 yes, A2 yes |
| ldo1 | 0 % · 50 % by never | 1 % · 50 % by never | 0 % · 50 % by never | GraphGPS: A1 yes, A2 yes, A3 yes; cross-attention: A1 yes, A2 yes, A3 no |
| ldo2 | 0 % · 50 % by never | 0 % · 50 % by never | 0 % · 50 % by never | GraphGPS: A1 yes, A2 yes, A3 no; cross-attention: A1 yes, A2 yes, A3 no |

**Stage C (12 of 24 runs complete at 2026-10-08 15:57):** scratch -> general model, early share and last third.

| Circuit | GT | GraphGPS | Cross-attention | Rules |
|---|---|---|---|---|
| ota5t | early 2 -> 88 % · late 95 -> 95 % | early 6 -> 90 % · late 96 -> 95 % | early 1 -> 92 % · late 95 -> 95 % | GT: C1 yes, C2 yes, C4 yes; GraphGPS: C1 yes, C2 yes, C4 yes; cross-attention: C1 yes, C2 yes, C4 yes |
| ota7t_w | early 0 -> 88 % · late 93 -> 94 % | early 0 -> 83 % · late 96 -> 95 % | early 1 -> 84 % · late 95 -> 95 % | GT: C1 yes, C2 yes, C4 yes; GraphGPS: C1 yes, C2 yes, C4 yes; cross-attention: C1 yes, C2 yes, C4 yes |
| ring3 | early 4 -> 24 % · late 12 -> 30 % | early 1 -> 28 % · late 18 -> 32 % | early 5 -> 33 % · late 34 -> 35 % | GT: C1 no, C2 yes, C4 yes; GraphGPS: C1 no, C2 yes, C4 yes; cross-attention: C1 no, C2 yes, C4 yes |
| vco_lin_c | early 4 -> 83 % · late 92 -> 95 % | running (S 3 %, G - %) | not run yet | GT: C1 yes, C2 yes, C4 yes; GraphGPS: not judged yet; cross-attention: not judged yet |
| ldo1 | early 0 -> 2 % · late 0 -> 8 % | not run yet | not run yet | GT: C1 no, C2 yes, C4 yes, C3 yes; GraphGPS: not judged yet; cross-attention: not judged yet |
| ldo2 | early 0 -> 0 % · late 0 -> 14 % | not run yet | not run yet | GT: C1 no, C2 yes, C4 yes, C3 yes; GraphGPS: not judged yet; cross-attention: not judged yet |

On the finished circuits every encoder's general model gives the same head start as GT's, with the same C1 verdict per
circuit.

**Stage D (stage D not started):** 8 runs queued after stage C (otafc, otatc x GraphGPS, cross-attention x scratch, general; seed 0,
four lanes, the 7.262 goals). GT references (7.262): folded cascode probe 21 %, scratch 13 % / 93 %, general 20 % / 95 %
(C1 fail +7, C2 and C4 pass); telescopic cascode probe 2 %, scratch 8 % / 89 %, general 73 % / 100 % (C1, C2, C4 pass).


Status: Stage A complete (12 runs). Stage C: 12 of 24 runs complete. Stage D not started. Last chain line: [10-08 15:35:04] START graphgps-vco-lin-c-c-s: graph_gps scratch seed 2 800 launches 4 lane(s) from random weights. Sources: artifacts/local/reviews/encoder-comparison-2026-10-07/ (results-A.md, results-C.md, notes.md),
docs/plan-encoder-comparison.md.
<!-- encoder-comparison-section:end -->
