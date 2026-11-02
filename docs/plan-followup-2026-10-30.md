# Plan: follow-up runs and analyses after thesis revision 25 (2026-10-30)

Written on 2026-10-30 from the user's decisions on the review of the completed experiments, and revised the same
day through three rounds of answers. Thesis revision 25 (the writing part) is done; no run has started. Every
number is a planning figure; the ledgers of the runs decide the final counts.

## 0. At a glance

| Part | What | Simulator cost | Other cost | State |
|---|---|---:|---|---|
| A | Matched-archive comparison, seeds 1 and 2, methods unchanged, no M0 | 38,500 evaluations, 4.3 to 6.0 days | none (source models exist) | done 2026-11-02: 38,400 + 144 confirmations, three-seed report (record 7.453) |
| B | Anytime metrics of the archive comparison | 0 | half a day of analysis | script and outputs in the thesis repository, three seeds (uncommitted) |
| C | The reverse port, second PDK to GPDK045 | 8,100 evaluations, 0.9 to 1.3 days | 9 offline trainings, 3 to 4 h CPU | running since 2026-11-02 03:22 (user: "Yes, run Part C") |
| D | Seed-by-seed differences instead of pass-or-fail rules | 0 | half a day of analysis | script and table in the thesis repository (uncommitted); reverse-port row after C |
| E | Best-so-far curves with bands, RQ2 and RQ3, appendix figures | 0 | half a day of analysis | scripts and figures in the thesis repository (uncommitted) |
| F | Word budget | 0 | done in revision 25 | done |
| G | Options explained, not scheduled | | | reference only |
| H | Where the files live since the repository separation | | | note |

Simulator total if everything runs: about 46,600 evaluations, 5.2 to 7.3 days. Throughput used: the seed-0
campaign charged 19,200 evaluations in about three days with interruptions (about 6,400 per day); Round 1 charged
55,200 evaluations in six days (about 9,000 per day). Times give both paces as a range.

## 1. Decisions recorded

| Item | Decision |
|---|---|
| Matched-archive comparison, seeds 1 and 2 | Run, unchanged methods (Part A; Amendment A2 of the archive plan) |
| M0 at seeds 1 and 2 | Not run: diagnostic only; declared in Amendment A2 before launch |
| Anytime metrics for the archive comparison | Report (Part B) |
| Target comparability across the three cases | Accepted as it is; no secondary thresholds |
| Pareto optimiser's failure handling (regression model on 0/1 validity labels) | Kept as run; no penalty arm; results count as they are |
| Larger archives | Not tested |
| Stronger BO reference (restarts, several trust regions) | Not added; results reported as they are |
| Classical baseline (differential evolution, CMA-ES) | Not added |
| RQ4 seeds 1 and 2 | Dropped; replaced by the reverse port (Part C; transfer plan Section 17) |
| RQ5 seeds | Already three seeds for both SAC arms; only the frozen probe is single (Part C) |
| Online against offline training explained in the thesis, with the LOADBench difficulty | Done in revision 25 (a872494) |
| Real PDK names in the thesis | Done in revision 25; the GATOR repository and GitHub descriptions keep the aliases |
| Seed-by-seed differences instead of bootstrap intervals | Do (Part D) |
| Best-so-far curves with bands, RQ2 and RQ3, in an appendix | Do (Part E) |
| RQ2 source-model retraining | Dropped |
| Pre-registered next held-out circuit | Naming costs nothing; running it is optional (Part G) |
| Step 4 targets changed with the process | Keep as is: PDK-A limits may be unreachable in PDK-B |
| Beyond nominal simulation | Not done |
| Rehearsal arm, offline-RL pretraining | Explained, not scheduled (Part G) |

## Part A. Matched-archive comparison, seeds 1 and 2

Protocol: `docs/plan-bo-mobo-rl-archive-comparison.md`, Sections 3 to 8 and Amendment A1 (Section 12), with
Amendment A2 (Section 13) recording this decision. Replicate pairs (pretrain seed, rollout seed) = (1, 102) and
(2, 103), as Section 6 fixed them.

| Stage | Matrix | Evaluations |
|---|---|---:|
| Panel A | 5 methods (T0, T+, M+, RA+, RF+) x 3 cases x 2 seeds x 800 | 24,000 |
| Panel B portfolios | 3 methods (T+, RA+, RF+) x 3 cases x 2 seeds x 4 children x 200 | 14,400 |
| M0 (Amendment A1) | not run at seeds 1 and 2: the user's decision of 2026-10-30, for cost; its seed-0 result stands | 0 |
| Confirmations | at most 3 finalists x 48 searches | at most 144 |
| Qualification | done at seed 0, shared | 0 |
| **Total** | | **about 38,500** |

Time: 4.3 to 6.0 days of simulator time. If the submission date does not allow six days, seed 1 first (about
19,300) and seed 2 when time remains; with two replicates "both replicates" replaces the median in the rules, and
the thesis says so.

Not available: a smaller budget per run. Seed 0's target reaches came as late as evaluation 546, so a 400-evaluation
run would censor them and would not be comparable with seed 0. Also not taken: dropping the frozen policy's Panel B
portfolios (4,800 evaluations), because removing a losing arm after seeing it lose is a post-hoc choice.

Fixed before launch:

- The source models are the nine already prepared (three cases x pretraining seeds 0, 1, 2; 7.78 h of training
  in total). No new training, no checkpoint selection by target results.
- Every seed-0 configuration is reused with only the seed pair changed. M0 is not run.
- Every seed-0 arm reruns; nothing is removed for its result.
- Memory rules of seed 0 stay: one M+ search at a time, the 12 GiB swap, the host-memory guard.
- Order counterbalanced by case and seed as Section 6 asks; timing stays observational on the shared host.
- Reading: with three replicates the Section 7 rules apply as written (replace T+ only on a median cost
  reduction of at least 20 % on two of three cases with no loss elsewhere; adopt the Pareto optimiser only on a
  median hypervolume gain of at least 10 % on two cases).

Pre-registration stays intact: no method changes, no arm removed for its result, and the reporting metrics of
Part B are labelled secondary and were declared before any seed-1 or seed-2 run.

## Part B. Anytime metrics for the archive comparison (reporting only, no simulation)

Sources, read by exact path in the GATOR checkout:
`artifacts/local/reviews/simulation-final-report-2026-10-28/search-curves.csv`, `panel-a.csv`, `panel-b.csv`,
and the amendment's `m0-results.json`; after Part A, the same files of its report.

For every arm, case and seed:

1. Target-reach probability by 100, 200, 400 and 800 evaluations (plan Section 7, Panel A).
2. Restricted mean evaluations to the target through 800, censored runs counted at 800 (plan Section 7).
3. Best-so-far preferred objective at 100, 200, 400 and 800 evaluations, as a percentage of the archive's best.
4. Panel B: hypervolume at 200, 400, 600 and 800 evaluations and the area under the hypervolume gain curve.
5. Failed-measurement share (already reported; kept beside the others).

The frozen targets demand 15.2 % (amplifier), 20.2 % (LDO) and 7.5 % (flip-flop) improvement over the archive's
best. The user accepted this as it is; no secondary thresholds are added, and the thesis reads the Target column
within a case only.

Output: one table and one figure in Appendix D of the thesis (uncounted), one sentence in Section 6.5.4
(about 25 words). Script: `thesis/figures/archive-compare-anytime.py` in the thesis repository, standard library
only, taking the GATOR checkout path as an argument (Part H), writing `thesis/figures/data/archive-compare-anytime.json`.
Effort: about half a day.

## Part C. The reverse port (replaces RQ4 seeds 1 and 2); RQ5 state

The user dropped the extra RQ4 seeds and chose the opposite direction instead: train on the second PDK's version
of each circuit and fine-tune on the GPDK045 original. The full specification is Section 17 of
`docs/plan-transfer-experiment.md`; the numbers:

| Item | Content | Cost |
|---|---|---:|
| Source archives | the Step 4 scratch run of each port (800 designs each; the fine-tuned Step 4 runs are excluded, since their proposals came from GPDK045-trained policies) | 0 |
| Source models | relative, absolute and first-build per circuit; Step 4's offline recipe (20,000 updates, batch 8, learning rate 0.001, gamma 0, alpha 0.01); final checkpoint | 9 trainings, 3 to 4 h CPU |
| Targets | `mscr_ota5t`, `mscr_ring3`, `graphgps_ldo1_t2` with their saved limits; scratch references = Step 3b `full` arm seeds 0 to 2 (649 / 572 / 601, 235 / 86 / 182, 9 / 0 / 0 feasible designs) | 0 |
| Runs | 3 circuits x (3 fine-tuned x 800 + 1 frozen probe x 300), rollout seed 0 | 8,100 evaluations, 0.9 to 1.3 days |
| Minimal variant | relative fine-tune and probe only | 3,300 evaluations, 0.4 to 0.5 day |
| Runtime | `gator-runtime-7317`, Step 4's online settings | |

Rules: the three predeclared rules (helps: early share at least 30 points above the median scratch early share;
ends as well: late share at most 5 points below the median scratch late share; does not deteriorate: late share at
least early share minus 10 points), with every scratch seed reported beside the median.

Two asymmetries with Step 4 are stated in the amendment and will be stated in the thesis: the reverse source holds
800 designs against the forward 2,400, and the reverse targets are the existing GPDK045 limits rather than rank-rule
limits. In return the reverse comparison has three scratch seeds per circuit where Step 4 had one.

RQ5 today: the telescopic cascode already has seeds 0, 1 and 2 for SAC from scratch (688, 564 and 647 feasible
designs) and for SAC from the general model (775, 753 and 765), from the TuRBO transfer comparison. Only the
300-evaluation frozen probe is single-seed. Optional: two more probes, 600 evaluations, about 0.1 day. The
remaining limit of RQ5 is the selection of the case after the pilot, which more seeds do not change.

## Part D. Seed-by-seed differences (analysis only, no simulation)

The thesis's rule "all three runs of one arm above all three of the other" is pass or fail. Three plain statistics
replace it, with no resampling:

1. **Every seed's value, side by side.** For each arm the per-seed first pass, late feasible share and feasible count
   (for RQ3 also the final best score), so the reader sees overlap directly.
2. **Median paired difference and its range.** For paired seeds (the same seed in both arms), the difference per
   seed, its median and its minimum and maximum. For unpaired arms, the median of all pairwise differences.
3. **Win count.** How many of the seed pairs the first arm wins, as "k of n". The old rule is "9 of 9" with three
   seeds; the two exact Mann-Whitney tests already in the thesis stay.

Comparisons and data (all in the thesis repository's `thesis/figures/data/`, no run archive needed):

| Comparison | Seeds per arm | Data file |
|---|---|---|
| RQ2: scratch vs fine-tuned, changed specification, OTA5t, RING3, LDO1, DFFRX1 | 3 paired | `current-transfer-results.json` |
| RQ3: BO vs GT-SAC, published LDO | 5 paired | `step3-sac-bo-results.json` |
| Step 3b: first build vs second build vs no ratios, three circuits | 3 | `round1-transfer-results.json` |
| TuRBO from nothing vs fine-tuned SAC, amplifier, flip-flop, cascode | 3 paired | `turbo-transfer-results.json` |
| Round 3 arms on seen circuits | 3 | `round3-results.json` |
| Reverse port, after Part C | 3 scratch seeds against each fine-tuned arm | new extract |

Output: Appendix D table "Seed-by-seed differences" (uncounted); the main-text sentences that now say "in every
seed pair" or "all three above all three" gain the median difference and range in a few words each (about 30
words in total). Script: `thesis/figures/seed-differences.py`, standard library only. Effort: half a day.

## Part E. Best-so-far curves with bands, RQ2 and RQ3 (analysis only, no simulation)

- RQ3: `step3-sac-bo-results.json` holds `cumulative_best_score_by_committed_ordinal` (800 values) for the five
  BO and five GT-SAC runs. Figure: median best-so-far score against evaluations, interquartile band and range,
  one line per method.
- RQ2: `current-transfer-results.json` holds `ordered_feasibility_bits` (800 bits) for all 81 runs. Figure: cumulative
  feasible designs against evaluations, median over the three seeds with min-max band, scratch against
  fine-tuned, one panel per circuit (OTA5t, RING3, LDO1, DFFRX1). The first pass is where a curve leaves zero.
- A best-objective curve for RQ2 would need the per-evaluation metric tables of 24 runs under `artifacts/` and is
  not planned.

Output: two figures in Appendix D (uncounted captions) with one pointer clause each in Sections 6.3 and 6.4
(about 20 words in total). Scripts: `thesis/figures/build-curves-rq2.py`, `build-curves-rq3.py`. Effort: half a day.

## Part F. Word budget (done)

Revision 25 moved the completed pilot's four subsections and four figures from Section 6.1 to Appendix D behind a
140-word summary, and added the online-against-offline paragraphs, the LOADBench sentences and the PDK names. The
conservative count went from 29,954 to 29,389 words, so about 610 words remain for Parts A to E, which need
about 75 in the main text. Further cuts, if ever needed: Section 2.2's derivations to Appendix F (about 340 words)
and Section 4.1's implementation steps to Appendix C (about 270).

## Part G. Options explained but not scheduled (costs for reference)

| Option | What it is | Evaluations for 3 seeds | Simulator time | Other cost |
|---|---|---:|---|---|
| Rehearsal arm (RA+ with the archive in replay) | the engine's rehearsal sampler mixes a pinned snapshot of the source transitions into every learner batch at a fixed fraction; a configuration change, no new code | 3 cases x 3 x 800 = 7,200 | 0.8 to 1.1 days | none |
| Offline-RL pretraining (TD3+BC or IQL) | replaces plain SAC offline updates; new RA and RF arms | 14,400 | 1.6 to 2.3 days | 9 trainings, about 8 h CPU; new code |
| Pre-registered next held-out circuit | naming the circuit and its pass rule in writing before any run costs nothing and can stand in the thesis as planned work; running it (general model vs scratch) is the 4,800 | 2 arms x 3 seeds x 800 = 4,800 | 0.5 to 0.75 day | plan text |

Any of these is a new, separately pre-registered arm or study. None changes the seed-0 arms or joins Part A.

## Part H. Where the files live (since 2026-10-30)

The thesis was separated into the private repository `FengyanWong/gator-thesis`, checked out at `D:\gator-thesis`
(record 7.445); `thesis/` and `thesis-phd/` no longer exist in the GATOR checkout. Consequences:

- Thesis scripts, data files, tables and figures named above live under `D:\gator-thesis\thesis\`. The campaign's
  result files stay under `D:\gator\artifacts\`. Every new or existing thesis extract script takes the GATOR
  checkout path as an argument (the existing ones already have `--root`).
- Since revision 25 the thesis's local-source links assume the GATOR checkout beside the thesis repository
  (`../../gator/...`), and the word counter's defaults follow the thesis folder.
- The Windows-side tooling that created the checkout wrote CRLF line endings into every text file, and the index kept
  their sizes, so the WSL git reported every file modified. Both were normalised on 2026-10-30 (content identical to the
  committed blobs). The same will happen after any further Windows-side checkout; normalise before committing from
  WSL, or settle `eol=lf` in a `.gitattributes` (a repository decision for the user).
- The thesis repository had no author identity; it now uses the same name and address as the GATOR repository.

## Order of work

1. Part A (simulator), with Part B's script written while it runs.
2. Parts D and E (analysis) in parallel with Part A; both can start before any run.
3. Part C (3 to 4 h of offline training first, then 8,100 evaluations) after Part A, or before it if the simulator
   is free, since it needs no archive-comparison result.
4. Thesis revision 26 after the runs: Parts A, B and C results in Chapter 6 and the discussion, the D and E tables
   and figures in Appendix D, the RQ4 answer extended to the reverse direction.

Both runs wait for the user's "run".
