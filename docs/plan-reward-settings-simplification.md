# Plan: a simpler reward (revision 5, 2026-10-05: built)

**Built on 2026-10-05 as record 7.183** (user: "update the reward plan according to finding and build it"): steps S0 to
S4 and S6, with the recommended choice of decisions 1 to 4, 6 and 7. Not done: S5 (decision 5, the 13 dB rows of four
saved tasks) and S7 (commit, frontend rebuild and restart of 8765, on the user's word). What the build did differently
from this text is under "State" in section 5. Session "RL reward design". Revision 1 (2026-10-03) hid a few controls and left two run settings
on the page; the user still found the reward too complicated. Revision 2 took every reward setting off the front of the
page and gave the reward one sentence. Revision 3 withdrew revision 2's scale rule. **Revision 4 follows the tests of
2026-10-05** ("check and test other default setting values", then "test with Spectre"): 175 SAC runs on ngspice and
1,925 Spectre launches on `real:mscr_ota7t`. Three things changed:

- **Section 0 is new and comes first:** with today's SAC settings the optimizer is a random search and no reward
  setting changes what it does. Three SAC defaults have to change before anything below matters.
- **The margin bonus joins the fixed set** (it lifted the pass rate from about 90 % to 99 % at no cost).
- **"Missing value = failed" stays off** (on, it learned more slowly), and the objective's shape no longer matters.

The reward arithmetic underneath (reward v2.1, `src/analog_optimizer/measurements/specs.py`,
[reward-v2.md](reward-v2.md)) is not changed: no optimizer file is touched, no digest moves, and every saved
configuration, task file and model keeps its hashes and its behaviour. Pictures of the current reward:
[GATOR Reward Design](https://claude.ai/artifact/QjBEqoUNpBYfhKcGqSyaFN). Every number of this revision:
`artifacts/local/reviews/defaults-study-2026-10-05/README.md`.

## 0. First: three SAC defaults

| Setting (Run, advanced) | Today | Becomes | What the tests showed |
|---|---|---|---|
| Starting temperature (`initial_alpha`) | 0.2 | 0.01 | At 0.2 the exploration term (about 1.2) is several times any reward difference (0.1 to 0.3), and the temperature cannot come down within a run (0.200 to 0.192 in 131 updates). 0.05 learns as early but ends lower (88 % against 97 %); 0.002 learns twice as late. |
| Updates per evaluation (`updates_per_transition`) | 1 | 8 | With 1 nothing learns, whatever the temperature, batch or learning rate (at most 15 % passing). 4 learns at about evaluation 1,000, 8 at about 470, 16 at about 330. One update takes 0.1 to 0.15 s, so 8 add about 0.9 s per design. |
| Discount (`gamma`) | 0.99 | 0 | An action is a whole design and its reward is that design's own measurement, so later steps add nothing but noise. With 8 updates: learned at 269 instead of 466 evaluations (ngspice OTA), at 367 instead of 686 (two-stage OTA). Not run on Spectre. |

- **On Spectre** (`real:mscr_ota7t`): two reward settings as different as "capped, share 0" and "compressed, share 0.5"
  gave the same design in 147 of 150 positions with today's settings; 922 designs with today's settings, none passes;
  with temperature 0.01 and 8 updates, 36 of 760 designs pass (the first at design 591; 30 % of the last 60).
- **Budget:** learning starts after 250 to 600 evaluations. The page's default of 60 is a random search under any
  setting; a from-scratch SAC run needs several hundred.
- **Left as they are:** batch 8 (32 costs four times as much per update for the same result), learning rate 3e-4,
  warm-up 8, episode length 4. The temperature's own learning rate stays empty: 3e-3 and 1e-2 gave nothing alone, were
  worse with more updates, and two runs ended early with a collapsed policy.
- The LLM-against-SAC comparison ([llm-sizing.md](llm-sizing.md), pilot on `mscr_ota7t`) must use these values, or
  its SAC arms are a random search.

## 1. The reward, in one sentence

> **Minus half the average miss, minus half the worst miss. A design that meets every row scores above 0: up to +1 for
> the room it leaves on its tightest row, and up to +1 more when one row is marked as the objective and the design
> improves on it.**

Four ideas, nothing else:

1. **A miss** is how far a measured value sits outside its limit, as a fraction of the limit, then compressed to
   between 0 and 1 (`x / (1 + x)`): 10 % outside costs 0.09, 50 % costs 0.33, 100 % costs 0.5. Inside the limit the
   miss is 0.
2. **The reward** is −½ × (average miss over the rows) − ½ × (the worst miss). The average gives credit for every row
   that improves; the worst keeps one failing row from hiding among many passing ones.
3. **Passing** means every row is met. That verdict is separate from the reward.
4. **Among passing designs** the reward keeps rising: with the room left on the tightest row (so the optimizer does not
   settle on the edge of the limits), and with the one objective row, if there is one.

## 2. What you set, what is fixed, what moves out of sight

**You set, per Specs row:** the limit (or the two limits of an interval). On at most one row: "minimise" or
"maximise" after feasible. Nothing per run.

**Fixed by the page for new configurations and new rows** (each is a setting today; "tested" = compared in training on
2026-10-05):

| Today a setting | Becomes | Why this value |
|---|---|---|
| Scale (per row) | left empty, as in every task today: the miss is measured against the size of the limit | the recorded designs sit 0.5 to 2.7 limits from their worst row, where this scale is sensitive; a tighter scale flattens the reward there (section 3) |
| Violation shape | compressed | tested: no difference from capped in training; capped is flat once a row is a full scale away, and 48 of the 227 recorded Spectre designs have such a row |
| Worst hard-spec share | 0.5 | tested: 0 ends with fewer passing designs (76 to 86 % against 88 to 94 %), 1 is slower and failed to learn in 2 of 6 runs |
| Objective bonus weight | 1, switched on by marking a row | tested: 27 to 30 % lower power among passing designs, no slower; 0.5 does the same |
| Objective shape | compressed | tested: no difference from clipped on a "minimise" row; compressed also keeps paying on a "maximise" row beyond twice its limit |
| Margin bonus weight | 1 | tested: 99 % of the last designs pass against 88 to 94 %, no slower, also together with the objective bonus; without it every passing design scores 0 and the policy settles on the edge |
| Hard or soft | every row is hard | a preference is expressed by the objective; no task uses a soft row |
| Missing value = failed | off, as today | tested: on, it never learned faster and was slower on 7 of 9 paired runs. To switch on for a row whose missing value is the failure itself (an oscillator that does not start has no frequency) |
| Nominal gate band | 0.5 | not testable today (no task has corner decks); nobody has tuned it |
| Corner policy | shown only when the task has corner decks; then "corners after nominal passes" | not testable today; "every corner" spent 28 of 32 corner runs on designs that had already failed nominal |

**Out of sight, still available** (one collapsed "Advanced" group in the run panel, and "More columns" in Specs), for
reproducing old runs and for experiments: violation shape, worst-spec share, objective weight and shape, the margin
bonus, the gate band, and per row the scale, the weight, hard/soft, the missing-value flag and margin sides.

## 3. Why this is the better set

- **Nothing you use is lost.** The seven MScR tasks have 51 Specs rows: 0 soft, 0 weighted, 0 with the missing-value
  flag, 0 with margin sides, 0 with a scale typed in, 1 objective.
- **It was tested where SAC learns** (ngspice OTA, 5 design rows, about 1 % of random designs pass; 4 to 6 seeds per
  setting, under two SAC settings; pass rate and power over each run's last 200 designs):

  | Reward | Learned at (evaluation) | Passing at the end | Power of passing designs |
  |---|---|---|---|
  | compressed, share 0.5, no bonus (the page's start) | 462 / 278 | 94 % / 88 % | 103 / 106 µW |
  | capped, share 0.5 | 478 / 254 | 91 % / 91 % | 101 / 103 |
  | compressed, share 0 | 398 / 287 | 84 % / 76 % | 107 / 107 |
  | compressed, share 1 | 617 / 313 | 68 % / 91 % | 99 / 101 |
  | + objective bonus 1 | 402 / 248 | 97 % / 97 % | 75 / 74 |
  | + margin bonus 1 | 444 / 270 | 99 % / 99 % | 86 / 90 |
  | + objective 1 + margin 1 | – / 249 | – / 99 % | – / 76 |
  | missing value = failed, on | 621 / 326 | 83 % / 90 % | 114 / 108 |

  First number: temperature 0.01 + 8 updates; second: the same with discount 0. One circuit, so indicative; the two
  SAC settings agree on every row but "share 1".
- **The scale is not a lever.** The scale says at which size of miss the reward is most sensitive: a miss of one scale
  costs half. The 227 distinct designs already simulated on the seven tasks (1 passes, 15 are within 30 % of every
  limit, 48 miss a row by more than the limit's own size) were scored again under several rules. Reward spread, 90th
  minus 10th percentile over a task's designs:

  | Task (designs) | Worst miss, median, in limits | Empty box (the limit) | Half the limit | 10 % of the limit |
  |---|---|---|---|---|
  | `mscr_ota7t` (125) | 0.66 | 0.164 | 0.197 | 0.196 |
  | `mscr_ring3` (42) | 1.27 | 0.348 | 0.347 | 0.188 |
  | `mscr_vco_lin` (25) | 0.96 | 0.477 | 0.456 | 0.301 |
  | `mscr_ldo1_rgcn` (8) | 1.00 | 0.268 | 0.234 | 0.105 |
  | `mscr_ldo2_rgcn` (9) | 2.68 | 0.412 | 0.346 | 0.209 |
  | `mscr_ota5t` (9) | 0.52 | 0.112 | 0.150 | 0.200 |
  | `mscr_ldo_basic` (9) | 0.66 | 0.221 | 0.302 | 0.374 |

  10 % is better on three tasks and worse on four; at 10 %, 71 of the 227 designs have a worst miss above 0.9, against 3
  with the empty box; the order of the designs hardly moves (same best design on 6 of 7 tasks). Half the limit is the
  best single value, but the gain is small. The one soft spot is a dB row: each dB of a 30 or 40 dB limit counts three
  to five times less, close to the limit, than the same spec typed in V/V; a fixed 6 dB was better on three of the four
  tasks with dB rows and the same on the fourth (decision 5). Data: `artifacts/local/reviews/scale-study-2026-10-05/`.
- **Half average, half worst** also raised the best-to-worst reward spread on the recorded M6 runs from 0.023 / 0.078 /
  0.102 to 0.049 / 0.217 / 0.408 (OTA / LDO / VCO).
- **It matches what the literature's closest relative does, without its hand-coding.** The ICCAD 2023 LDO reward
  (Li and Chan Carusone) scores each spec with the same compressed curve at a scale of twice the target, sums the
  scores, and adds penalties written into the environment for each circuit.

## 4. Simple, but what it still tells the optimizer

| Information | Still in the reward? | How |
|---|---|---|
| How far each row is from its limit, not just pass or fail | yes | the miss, as a fraction of the limit, compressed |
| Progress on every row at once | yes | the average half |
| Which row blocks the pass | yes | the worst half |
| Pass or fail | yes, as a separate verdict | every row met; never decided by the reward's sign or by a weight |
| How much room a passing design leaves | yes | the margin bonus on the tightest row, 0 to +1 |
| How much better a passing design is | yes, for one chosen row | the objective bonus, 0 to +1 |
| A design that cannot be simulated | yes | counted as a full miss and learned from |
| A value that cannot be measured | only on a row with the flag | elsewhere the design is dropped: 1 % of the designs in the tests |
| Behaviour at corners | yes, when a task has corner decks | each row keeps its worst condition; nominal-passing designs rank first |

Left out on purpose, and still reachable under "Advanced" if a study needs it: different importance per row (weights
and scales) and preferences that are not requirements (soft rows). Not in any version: Monte Carlo or yield, and
corner-specific limits.

## 5. Steps

| Step | What | Where | Check |
|---|---|---|---|
| S0 | The three SAC values of section 0 become the starting values of a new configuration and of the "GATOR baseline" preset; a from-scratch SAC run with fewer than 300 evaluations gets a warning. Saved configurations and the saved network settings keep what they hold (their hashes must not move); the package's own `SACConfig` defaults are not touched. | `src/gator_workbench/schema.py` (`AdvancedRL`), `network_presets.py`, `frontend/src/store.ts`, `validation.py` | an old configuration's two hashes are unchanged; one ngspice run of 600 evaluations passes half of its last 100 designs |
| S1 | The run panel's reward block shrinks to the sentence of section 1 plus one collapsed "Advanced" group holding today's seven controls. New pages start with compressed violations, share 0.5, objective weight 1, compressed objective, margin weight 1. The "no active objective" warning goes. | `frontend/src/panels/Right.tsx`, `frontend/src/store.ts` | `tsc`; `reward_v21_check.mjs` and `reward_v2_frontend_check` updated; the saved-model table still names a loaded model's settings |
| S2 | The Specs column headed `normalization_scale` gets the header "Scale" and joins "More columns" with the Hard tick. A new row starts with an empty scale, like the tasks' rows: the page stops writing 10° into phase rows and half the width into intervals. A new dB row gets 6 dB instead of 3 (decision 5). | `frontend/src/panels/Editors.tsx`, `schema.ADVANCED_COLUMNS` | the frozen old-configuration hash fixture is unchanged; a browser check adds one row of each kind |
| S3 | Validation blocks a row whose limit is 0 with no scale (today it silently divides by 1), and names the Scale column | `src/gator_workbench/validation.py` | one validation test |
| S4 | The agent's "Review settings" and readiness brief describe the reduced set and the SAC values | `src/gator_workbench/agents/` | settings-review test |
| S5 | Only if decision 5 says so: 6 dB typed into the 13 dB rows of four tasks (`mscr_ota5t`, `mscr_ldo1_rgcn`, `mscr_ldo2_rgcn`, `mscr_ldo_basic`), saved as four new task revisions. The pilot task `mscr_ota7t` has no dB row and is not touched. | the page, on the user's word | each task's validation clean; the `ldo2_rgcn` baseline is recorded again (one Spectre launch) |
| S6 | Docs (`network-presets.md` too), record entry, index row; the reward page republished to the simple form | `docs/`, the artifact | — |
| S7 | Land hunk-exact when no other session is committing; frontend rebuilt and 8765 restarted on the user's word | — | the live page shows the new block |

About a day and a half, one session. No simulator or model call, unless decision 5 fills the existing dB rows (one
re-recorded baseline).

**State (record 7.183).**
- **S0, built, in one way other than written.** The schema's own defaults stay 0.2 / 1 / 0.99: changing them would have
  changed what every configuration without an Advanced block means, and made every test eight times slower. The three
  values are the GATOR baseline (`network_presets.TESTED`), which is where the page takes a new configuration's training
  values from; an encoder that was on the old baseline follows it; validation warns wherever the old values would train,
  the command line included. The page's starting budget stays 60 (each evaluation is a simulation the user authorizes)
  and carries the budget warning.
- **S1, built**, with one addition: a configuration that holds other reward values is not rewritten; the block names
  the values that differ and offers **Use the tested reward**.
- **S2, built**, with one difference: a new row's scale is written as the size of its limit (the number an empty box
  stands for) rather than left empty, as before; only the 10 degrees and the half interval are gone, and a dB row gets 6.
- **S3, S4, S6 built.** The reward page (artifact) was not republished.
- **S5 not done** (decision 5 is open). **S7 not done.**

## 6. What was tested, and what was not

- Tested in training: the three SAC values (two ngspice circuits and Spectre), the violation shape, the worst-spec
  share, the objective bonus and its shape, the margin bonus, the missing-value flag (one ngspice circuit).
- Tested on recorded designs only: the scale.
- Not tested: discount 0 on Spectre; the reward settings on Spectre (the hour went into the SAC settings); the nominal
  gate band and the corner policy (no corner decks); weights and soft rows (no task uses them); encoders other than the
  graph transformer; circuits with more than 10 design rows.
- Found on the way, and in the way of the next real runs: a six-lane Spectre run failed after 225 designs with
  "nonce cache at capacity". The bridge daemon in Virtuoso remembers each request's one-time number for at least 15
  minutes and holds 4,096 of them; a design costs about five requests, so about 820 designs per 15 minutes - under one
  per second - is the limit, whatever the request timeouts. One lane ran 800 designs. Lifted for the running Virtuoso
  on 2026-10-05 (decision 8).

## 7. What stays out

- A scale rule for ordinary rows (10 % of the limit, or half): tried on the recorded designs, section 3.
- A larger batch, a faster temperature learning rate, a longer warm-up: tried, section 0.
- A fixed bonus for the first pass (the ICCAD 2023 paper's +10): an optimizer change, and an experiment arm at most.
- Monte Carlo and corner-specific limits.
- The SKY130 benchmark stays parked: zero passes in its calibration, mostly from the 1 µs settling target and the
  fixed low bias currents; its open choice (let SAC vary the bias current and recalibrate, or compare on the MScR
  circuits only) is not touched by this plan. Its zero passes were measured with today's SAC settings, so section 0
  applies to it too.

## 8. Decisions for the user

1. The SAC defaults: temperature 0.01, 8 updates per evaluation and discount 0 (recommended), or the first two only
   (the pair that was run on Spectre).
2. The formula: half average + half worst (recommended, tested), or worst only.
3. The objective: marking a row switches the bonus on at weight 1 (recommended, tested), or keep a weight box on the page.
4. The margin bonus on at 1 for new configurations (recommended, tested), or left at 0.
5. dB rows: 6 dB for new rows, and for the 13 existing ones when the cohort's baselines are prepared (recommended; it
   changes four task hashes, not the pilot's), or leave every scale empty.
6. "Missing value = failed": off for new rows, on by hand for an oscillator's frequency (recommended), or on everywhere.
7. Soft rows, weights and scales: out of sight (recommended), or removed from the page altogether.
8. The bridge limit of section 6: enlarge the daemon's cache (`RB_NONCE_CACHE_MAX`, e.g. 32768, set in Virtuoso's
   environment; the daemon is restarted, Virtuoso need not be). Shorter request timeouts do not help: the daemon keeps
   every number 15 minutes regardless. Before the pilot.

Decisions 1 to 4, 6 and 7 were taken as recommended with the build (record 7.183). Decision 8 was taken and applied
on 2026-10-05, on the user's word: 32768 in the running Virtuoso, the daemon restarted, 4,500 requests in 19 s all
answered. It is not yet in Virtuoso's start-up (the VM's `.cdsinit` belongs to root): a restarted Virtuoso needs the
line typed before the bridge is loaded (record 7.183, "The bridge setting"). Open: 5.
