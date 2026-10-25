# Documentation index

Start with the [repository map](../README.md), then [workbench behavior](workbench.md) or the
[optimizer package](optimizer-package.md). The [functionality reference](functionality-reference.md) maps a feature
to its code, tests and records. The [development index](frontend_implementation_status.md) finds individual changes.

This index covers the documents directly in this folder and every file in workbench-log/.
**Kept current** marks a maintained reference or active protocol. **Frozen** marks dated scope, evidence or history;
later evidence does not rewrite an earlier result. A file may have a current contract and frozen result sections.

Plan status extracts below retain the document's date and first words. They describe that snapshot, not a live queue.
Some openings precede later execution sections: follow the plan's later records and the development index for those updates.

## Living references

| Document | What it holds | Kind | Maintenance |
|---|---|---|---|
| [README.md](README.md) | The document map, including plans, evidence, briefs and development records. | Living | Kept current |
| [workbench.md](workbench.md) | What the browser, run controls, saved tasks, settings and outputs do, with a code map. | Living | Kept current |
| [functionality-reference.md](functionality-reference.md) | Buttons, functions, routes, source files, tests and records, including removed features. | Living | Kept current |
| [frontend_implementation_status.md](frontend_implementation_status.md) | The one-line index of workbench records and the rules for appending a new entry. | Living index | Kept current; linked entries are historical |
| [decisions.md](decisions.md) | The dated project-state summary followed by the chronological research decisions. | Living summary / record | Summary kept current; historical decisions frozen |
| [optimizer-package.md](optimizer-package.md) | The optimizer's packages, backends, Spectre dialect and graph/parameter contracts. | Living | Kept current |
| [circuit-gps.md](circuit-gps.md) | CircuitGPS selection, representation, computation and saved-model compatibility. | Living | Kept current; read the stated architecture version |
| [global-encoders.md](global-encoders.md) | GraphGPS and parameter-group cross-attention architectures, structural inputs and comparison entrypoints. | Living | Kept current |
| [network-presets.md](network-presets.md) | Per-encoder preset controls, tested settings, sources and limitations. | Living | Kept current; historical preset evidence retained |
| [input-tensor-cache.md](input-tensor-cache.md) | Graph-input cache contents, invalidation, interfaces and dated verification results. | Living | Contract kept current; dated measurements frozen |
| [experiment-recording.md](experiment-recording.md) | The optional SQLite recording path, storage rules, replay recovery and exports. | Living | Contract kept current; dated acceptance evidence retained |
| [reward-v2.md](reward-v2.md) | The reward contract and the v2/v2.1 engineering qualification record. | Living / evidence | Contract kept current; dated results frozen |
| [performance-measurement.md](performance-measurement.md) | How to time work fairly on the shared machine without disturbing other sessions. | Living | Kept current |

## Plans

| Document | What it holds | Kind | Maintenance | Recorded State / Status / Outcome |
|---|---|---|---|---|
| [plan-bo-mobo-rl-archive-comparison.md](plan-bo-mobo-rl-archive-comparison.md) | Matched-archive TuRBO transfer, Pareto MOBO and SAC comparisons, budgets and optional RF follow-ups. | Plan | Kept current as the protocol develops | 2026-10-21: "planned; no implementation, training or simulation dispatched" (opening snapshot). |
| [plan-cheaper-check-before-write.md](plan-cheaper-check-before-write.md) | The preserved pre-write verification and the faster whole-cell read it uses. | Plan | Frozen completed scope and measurements | 2026-10-09: "done" (record 7.296). |
| [plan-encoder-baseline-abc.md](plan-encoder-baseline-abc.md) | Reusable six-circuit scratch, own-model transfer and pooled-model transfer protocol. | Plan | Frozen protocol version 1 | 2026-10-07: "plan written; no new runs started"; instantiated by the encoder-comparison plan. |
| [plan-encoder-comparison-additions.md](plan-encoder-comparison-additions.md) | AgenticSizing tasks, proposed reward steering and stage folders; the GCN arm is excluded. | Plan | Frozen dated proposal and updates | 2026-10-09: "Status at writing"; its table records excluded, built, proposed and done parts separately. |
| [plan-encoder-comparison.md](plan-encoder-comparison.md) | GraphGPS and cross-attention comparisons against GT, including the lean executed matrix. | Plan | Frozen protocol with execution records | 2026-10-07: "plan only; nothing started" is the original status; revision 4 and section 12 record execution. |
| [plan-finalist-monte-carlo.md](plan-finalist-monte-carlo.md) | A bounded finalist mismatch check and its proposed run-configuration controls. | Plan | Frozen proposal pending a new decision | 2026-09-29: "PLAN. Nothing here is built." |
| [plan-finetune-vs-scratch.md](plan-finetune-vs-scratch.md) | The twelve own-model fine-tuning and scratch runs from new starting designs, with results. | Plan | Frozen protocol and results | 2026-10-06: "the twelve runs ran ... and are all complete"; results in section 9. |
| [plan-frontend-run-workflow-v1.md](plan-frontend-run-workflow-v1.md) | The first draft of the task/model/run workflow, retained for comparison. | Plan | Frozen superseded draft | 2026-10-07: "Superseded" by plan-frontend-run-workflow.md. |
| [plan-frontend-run-workflow.md](plan-frontend-run-workflow.md) | Task, run and RL-model windows, loading a run and the run brief. | Plan | Frozen design; current behavior is in workbench.md | 2026-10-07: "plan, revised twice ... then extended. Nothing is built yet" is the dated opening status. |
| [plan-general-network.md](plan-general-network.md) | Training one model from saved experience, matched recipes and held-out circuit comparisons. | Plan | Frozen protocol and results | 2026-10-07 afternoon: "the required experiment ... are complete" (including the follow-ups named there). |
| [plan-general-seeds-starts.md](plan-general-seeds-starts.md) | The compact multi-seed and multi-start follow-up to the general-network comparison. | Plan | Frozen proposal pending authorization | 2026-10-07: "plan only, in its compact form"; nothing registered or started by that plan. |
| [plan-low-moderate-risk-performance.md](plan-low-moderate-risk-performance.md) | Six performance packages that preserve selected settings, results and recorded data. | Plan | Frozen implemented handoff | 2026-10-06: "Built ... as record 7.221"; A-F implemented and tested. |
| [plan-measurement-off-virtuoso.md](plan-measurement-off-virtuoso.md) | The attempted measurement process outside Virtuoso and the evidence for removing it. | Plan | Frozen rejected implementation and measurements | 2026-10-02: "built (G1), tried on Spectre (G2)"; identical values, no speed gain, then removed. |
| [plan-ota7-current-reference-variant.md](plan-ota7-current-reference-variant.md) | A proposed OTA7 current-reference testbench variant and its separate approval/budget boundaries. | Plan | Frozen proposal | 2026-09-29: "plan only"; the document authorizes no implementation or simulation. |
| [plan-performance-and-learning-efficiency.md](plan-performance-and-learning-efficiency.md) | Thirteen performance proposals, narrowed by the user to the six-package handoff. | Plan | Frozen review; narrower handoff takes precedence | 2026-10-05: "plan only; no runtime or training changes implemented by this review". |
| [plan-persistent-spectre.md](plan-persistent-spectre.md) | The staying-alive Spectre trial and why it was removed for the tested PDK. | Plan | Frozen rejected implementation and measurements | 2026-10-03 removal: "built (G1), tried on Spectre (G2): not usable for this PDK". |
| [plan-readability.md](plan-readability.md) | Document and code readability packages with per-package identity proofs and isolated landing rules. | Plan | Kept current while packages are executed | 2026-10-25, record 7.390: "plan only; no group chosen; nothing executed" is the input State line. |
| [plan-refactoring.md](plan-refactoring.md) | The structural refactoring packages, proof methods, landing rules and follow-up scope. | Plan | Frozen completed scope and proof record | 2026-10-09: "groups A, B, C ... and D are done"; subsequent State text records follow-up E and C11. |
| [plan-reward-settings-simplification.md](plan-reward-settings-simplification.md) | The simplified reward controls, tested defaults and saved-task follow-up. | Plan | Frozen implemented scope | 2026-10-05: "Built ... as record 7.183"; the opening also records S5 and S7 completion. |
| [plan-reward-v2-real-flow.md](plan-reward-v2-real-flow.md) | Reward-v2 implementation scope and bounded physical qualification stages. | Plan | Frozen qualification scope | 2026-09-30: "DONE"; the dated opening points to v2.1 as the later reward. |
| [plan-robust-reward-and-network.md](plan-robust-reward-and-network.md) | The earlier reasoning for robust reward, conditions and wider network inputs. | Plan | Frozen superseded reasoning | 2026-09-26: "Superseded for implementation" by the real-flow plan. |
| [plan-transfer-experiment.md](plan-transfer-experiment.md) | Encoder, target, optimizer, PDK and general-model comparisons, with later rounds and journal plans. | Plan | Kept current as the experiment develops | 2026-10-15 13:55 Europe/London: "Round 1 and all 24 Round 2 repeats are complete"; later sections and records update the campaign. |

## Milestone and engineering evidence

| Document | What it holds | Kind | Maintenance |
|---|---|---|---|
| [verification.md](verification.md) | The original offline parser, graph and synthetic acceptance, with environment and scope. | Evidence of M1 | Frozen dated acceptance |
| [m1-neural-inputs.md](m1-neural-inputs.md) | Fixed-semantics homogeneous/dense neural inputs, masks and parameter-group batching. | Evidence of M1 | Frozen dated acceptance |
| [opamp-baseline.md](opamp-baseline.md) | The real GPDK045 five-transistor OTA baseline, measurements, export and restoration. | Evidence of M2 | Frozen dated acceptance |
| [opamp-backend.md](opamp-backend.md) | The original bridge adapter's matched-width write, simulation and restore cycle. | Evidence of M3 | Frozen dated acceptance |
| [opamp-environment.md](opamp-environment.md) | The single-worker environment, legal actions and bounded real random-candidate acceptance. | Evidence of M3 | Frozen dated acceptance |
| [pvt-mc-interfaces.md](pvt-mc-interfaces.md) | Typed condition interfaces, chosen GPDK045 corners and pure post-check summaries. | Evidence of M3 | Frozen dated acceptance; no Monte Carlo execution |
| [m4-graph-sac.md](m4-graph-sac.md) | Graph SAC, action/state contracts, checkpoint recovery and the small real closed-loop acceptance. | Evidence of M4 | Dated acceptance frozen; later optimization notes retained |
| [parallel-spectre-sac.md](parallel-spectre-sac.md) | Native per-candidate CDF preparation and parallel Spectre collection with one learner. | Evidence of M4 extension | Frozen implementation and acceptance snapshot |
| [native-cdf-real-verification.md](native-cdf-real-verification.md) | The dated real acceptance of candidate CDF readback, native export and parallel collection. | Evidence of M4 extension | Frozen dated acceptance |
| [runtime-reliability.md](runtime-reliability.md) | Checkpoint continuation, worker cleanup, transfer entrypoints and long-run reporting checks. | Evidence of M4/M5 runtime work | Frozen verification snapshot |
| [m5-transfer.md](m5-transfer.md) | The first frozen transfer comparison, leakage controls, methods, costs and limitations. | Evidence of M5 | Frozen first-round acceptance |
| [m5-real-topology.md](m5-real-topology.md) | The real seven-transistor OTA holdout, parameter domains, frozen comparison and audit. | Evidence of M5 | Frozen new-topology acceptance |
| [encoder-ablation.md](encoder-ablation.md) | The pre-M6 encoder interface and transfer checks, with later encoder notes. | Evidence before M6 | Original acceptance frozen; dated interface updates retained |
| [m6-cross-category.md](m6-cross-category.md) | Category holdouts, synthetic cross-category protocol and offline acceptance. | Evidence of M6 | Dated acceptance frozen; later command-selection notes retained |
| [m6-ldo-baseline.md](m6-ldo-baseline.md) | The real LDO circuit, action and measurement qualification before the M6 pilot. | Evidence of M6 | Frozen dated acceptance |
| [m6-vco-baseline.md](m6-vco-baseline.md) | The real ring-VCO baseline under the original strict numerical settings. | Evidence of M6 | Frozen dated acceptance |
| [m6-vco-runtime.md](m6-vco-runtime.md) | The qualified fast VCO policy and its comparison with the strict reference. | Evidence of M6 | Frozen numerical qualification |
| [m6-real-protocol.md](m6-real-protocol.md) | The physical cross-category pilot's tasks, method matrix, budget and freeze contract. | Evidence of M6 | Frozen protocol history; later encoder-selection notes retained |
| [m6-real-results.md](m6-real-results.md) | Physical cross-category pilot results, cost, success rates and independent audit. | Evidence of M6 | Frozen pilot results |
| [m6-vco-requalification.md](m6-vco-requalification.md) | Strict rechecks of optimized VCO designs and the source-pinned revalidation procedure. | Evidence of M6 | Frozen requalification plans and results |
| [recording-verification.md](recording-verification.md) | Offline recording, recovery, export and storage acceptance, including the volume run. | Evidence of recording extension | Frozen dated acceptance |
| [recording-real-verification.md](recording-real-verification.md) | Real recording/learner recovery acceptance and the corresponding data/restoration audit. | Evidence of recording extension | Frozen dated acceptance |
| [recording-overhead.md](recording-overhead.md) | The controlled JSON-versus-SQLite mock recording cost comparison and its limits. | Evidence of recording extension | Frozen measurements |
| [recording-io-audit.md](recording-io-audit.md) | The audit of repeated recording, replay, checkpoint and export reads/writes. | Evidence of recording extension | Frozen audit record |

## Briefs

| Document | What it holds | Kind | Maintenance |
|---|---|---|---|
| [brief-llm-sizing-for-astra.md](brief-llm-sizing-for-astra.md) | The implemented 2026-09-30 LLM-sizing brief; the later removal is recorded in llm-sizing.md. | Brief | Frozen historical implementation instructions |
| [brief-reward-v2-for-astra.md](brief-reward-v2-for-astra.md) | The original reward-v2 brief, superseded by the real-flow qualification plan. | Brief | Frozen; superseded 2026-09-26 |
| [brief-reward-v2.1-for-astra.md](brief-reward-v2.1-for-astra.md) | Reward-v2.1 requirements, acceptance gates and completed steps; the matched comparison remained separate. | Brief | Frozen; status 2026-09-30 says done through step 6 |

## Histories, reports and dated guides

| Document | What it holds | Kind | Maintenance |
|---|---|---|---|
| [graph-transformers-reading-guide.md](graph-transformers-reading-guide.md) | An illustrated explanation of GraphGPS and CircuitGPS inputs, learning and transfer limits. | Record / dated guide | Frozen implementation snapshot: 2026-10-14 |
| [history-readme-milestones.md](history-readme-milestones.md) | The original README's milestone paragraphs and reference text, with an English guide. | Record | Frozen source snapshot: a82f950, archived 2026-10-25 |
| [llm-sizing.md](llm-sizing.md) | The former LLM sizing modes and their removal in favor of agent-launched work. | Record | Frozen; removed 2026-10-06, record 7.226 |
| [pdk-port-history.md](pdk-port-history.md) | The ordered circuit-porting history between GPDK045 and a second foundry's 0.18 um PDK. | Record | Frozen porting history: 2026-10-12 |
| [report-gt-experiments-2026-10-07.md](report-gt-experiments-2026-10-07.md) | Recorded GT learning and transfer results, caveats and later encoder comparisons. | Record / report | Frozen recorded results; dated additions retained |

## Workbench records

Existing entries are append-only. The current open file is named in [CLAUDE.md](../CLAUDE.md) and the
[development index](frontend_implementation_status.md); old rollover pointers remain for existing links.

| Document | What it holds | Kind | Maintenance |
|---|---|---|---|
| [7.01-7.20.md](workbench-log/7.01-7.20.md) | Chronological workbench entries 7.1-7.20. | Record | Frozen closed record |
| [7.101-7.118.md](workbench-log/7.101-7.118.md) | Chronological workbench entries 7.101-7.118. | Record | Frozen closed record |
| [7.101-and-later.md](workbench-log/7.101-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.101-7.118.md`, `7.119-and-later.md`. | Record | Frozen compatibility pointer |
| [7.119-7.265.md](workbench-log/7.119-7.265.md) | Workbench entries 7.119-7.265; entry 7.262 is in the next closed file. | Record | Frozen closed record |
| [7.119-and-later.md](workbench-log/7.119-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.119-7.265.md`, `7.266-and-later.md`. | Record | Frozen compatibility pointer |
| [7.21-7.40.md](workbench-log/7.21-7.40.md) | Chronological workbench entries 7.21-7.40. | Record | Frozen closed record |
| [7.266-7.278.md](workbench-log/7.266-7.278.md) | Workbench entries 7.266-7.278, plus entry 7.262 written after the prior file closed. | Record | Frozen closed record |
| [7.266-and-later.md](workbench-log/7.266-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.266-7.278.md`, `7.279-and-later.md`. | Record | Frozen compatibility pointer |
| [7.279-7.290.md](workbench-log/7.279-7.290.md) | Chronological workbench entries 7.279-7.290. | Record | Frozen closed record |
| [7.279-and-later.md](workbench-log/7.279-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.279-7.290.md`, `7.291-and-later.md`. | Record | Frozen compatibility pointer |
| [7.291-7.300.md](workbench-log/7.291-7.300.md) | Chronological workbench entries 7.291-7.300. | Record | Frozen closed record |
| [7.291-and-later.md](workbench-log/7.291-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.291-7.300.md`, `7.301-and-later.md`. | Record | Frozen compatibility pointer |
| [7.301-7.323.md](workbench-log/7.301-7.323.md) | Chronological workbench entries 7.301-7.323. | Record | Frozen closed record |
| [7.301-and-later.md](workbench-log/7.301-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.301-7.323.md`, `7.324-and-later.md`. | Record | Frozen compatibility pointer |
| [7.324-7.335.md](workbench-log/7.324-7.335.md) | Chronological workbench entries 7.324-7.335. | Record | Frozen closed record |
| [7.324-and-later.md](workbench-log/7.324-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.324-7.335.md`, `7.353-and-later.md`. | Record | Frozen compatibility pointer |
| [7.336-7.352.md](workbench-log/7.336-7.352.md) | Chronological workbench entries 7.336-7.352. | Record | Frozen closed record |
| [7.336-and-later.md](workbench-log/7.336-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.336-7.352.md`, `7.353-and-later.md`. | Record | Frozen compatibility pointer |
| [7.353-7.364.md](workbench-log/7.353-7.364.md) | Chronological workbench entries 7.353-7.364. | Record | Frozen closed record |
| [7.353-and-later.md](workbench-log/7.353-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.353-7.364.md`, `7.365-and-later.md`. | Record | Frozen compatibility pointer |
| [7.365-7.375.md](workbench-log/7.365-7.375.md) | Chronological workbench entries 7.365-7.375. | Record | Frozen closed record |
| [7.365-and-later.md](workbench-log/7.365-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.365-7.375.md`, `7.376-and-later.md`. | Record | Frozen compatibility pointer |
| [7.376-7.388.md](workbench-log/7.376-7.388.md) | Chronological workbench entries 7.376-7.388. | Record | Frozen closed record |
| [7.376-and-later.md](workbench-log/7.376-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.376-7.388.md`, `7.389-and-later.md`. | Record | Frozen compatibility pointer |
| [7.389-and-later.md](workbench-log/7.389-and-later.md) | Workbench entries 7.389 onwards; the open log at this index's creation. | Record | Append-only open record |
| [7.41-7.60.md](workbench-log/7.41-7.60.md) | Chronological workbench entries 7.41-7.60. | Record | Frozen closed record |
| [7.61-7.80.md](workbench-log/7.61-7.80.md) | Chronological workbench entries 7.61-7.80. | Record | Frozen closed record |
| [7.61-and-later.md](workbench-log/7.61-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.61-7.80.md`, `7.81-7.100.md`, `7.101-and-later.md`. | Record | Frozen compatibility pointer |
| [7.81-7.100.md](workbench-log/7.81-7.100.md) | Chronological workbench entries 7.81-7.100. | Record | Frozen closed record |
| [7.81-and-later.md](workbench-log/7.81-and-later.md) | Old rollover link, preserved for readers of earlier records; points to `7.81-7.100.md`, `7.101-and-later.md`. | Record | Frozen compatibility pointer |
| [first-build.md](workbench-log/first-build.md) | The original 2026-09-20 build description and its first next steps. | Record | Frozen first-build record |
| [record-history.md](workbench-log/record-history.md) | The record-reading history and chronological commit table. | Record | Historical text frozen; commit rows appended |
| [self-improving-frontend.md](workbench-log/self-improving-frontend.md) | The frontend branch's own SIF entries and merges, separate from the 7.N sequence. | Record | Kept current by that branch; earlier entries frozen |
