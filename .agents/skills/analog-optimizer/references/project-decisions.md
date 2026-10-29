# Project decisions and context

Synchronized: 2026-09-19. Updated from later user authorization and the project's `docs/decisions.md` and `docs/encoder-ablation.md`. Encoder, training-condition, PVT/MC and LLM rules were synchronized on 2026-09-30 (sections 1, 4, 8, 9 and 10); see the start of the project's `docs/decisions.md` for the current state.
This is a snapshot of project status; the latest user request, actual code and corresponding acceptance records take precedence. The historical M3 scope no longer limits M4/M5 work that has been authorized and completed.

## 1. Current direction

| Item | Current agreement | Boundary |
|---|---|---|
| Optimization task | Analog/mixed-signal circuit sizing and explicitly allowed bias parameters | The first version does not generate topologies or optimize layouts |
| Circuit platform | Cadence Virtuoso + Spectre | The local installation determines the real PDK/testbench |
| Interface choice | The user specified Virtuoso bridge; the repository discussed is `Arcadia-1/virtuoso-bridge-lite` | Do not automatically migrate back to SkillBridge; an LLM inner loop follows only `docs/brief-llm-sizing-for-astra.md` (the user's 2026-09-29 decision, replacing the earlier prohibition on an LLM agent inner loop for that work) |
| Circuit representation | A common, port-aware device-net graph | Preserve terminal information and pass it to the model; more than simple adjacency |
| Encoder | Local terminal Graph Transformer by default; RGCN and GATv2 optional (port-GNN removed 2026-09-24; MLP/GCN removed 2026-09-26, GATv1 replaced by GATv2 that day) | Common node/parameter-group interface; runnable does not mean transfer effectiveness has been demonstrated |
| Optimizer | Goal-conditioned SAC | Other algorithms may be baselines, but do not replace it by default |
| Surrogate in the first version | None | May be added later only as a separate experiment |
| Current training conditions | Nominal only by default; since reward v2 / v2.1, `real:gpdk045_ota7` can explicitly select `always` or `after_nominal`, with each condition's results entering reward and replay (real acceptance results in `docs/reward-v2.md`) | Post-validation (Corner check) results do not enter reward, replay or normalizer; MC is unimplemented |
| PVT screening | Nominal top 3 independent designs × 5 representative conditions | Configuration, data contract and pure summary functions exist; workbench Corner check (2026-09-22) resimulates a run's 1-3 best designs under 5 conditions; general top-k scheduling in the package is not yet implemented |
| Monte Carlo | Types, sample identity and an explicitly unsupported interface retained | Post-validation first in future, then consider a limited-budget training extension; only `docs/plan-finalist-monte-carlo.md` exists now |
| Transfer goal | Parameter-group actions, common schema, specification conditioning | No promise of zero-shot operation on arbitrary circuits |
| Current stage | M1–M5 and the encoder interface before M6 completed; M6 closed at pilot scale on 2026-09-20 | Cross-category transfer has pilot evidence only; a GT/transfer advantage remains unproven; larger prospective experiments and optional extensions have not started |

## 2. Historical experience: retain compatibility without turning it into defaults

The user has experience with Python, DDPG/RGCN, SkillBridge, Virtuoso ADE Assembler/OCEAN/Spectre, and sizing VCO/ring-oscillator and LDO circuits.
Past discussions included shared experience pools and multiple simulation instances, retaining policy and representation, and reducing Spectre calls and total runtime.

Therefore:

- Prefer reusing the user's existing circuit configurations, measurement scripts and tested simulation flows.
- Support replacing the interface layer, but do not turn one old project's W/L, VDD, reward, episode length or noise settings into constants across circuits.
- Old DDPG exploration noise is not SAC's default exploration mechanism.
- Timings/parallel speedups from an old project or another machine are historical measurements, not new performance promises for this machine.
- Do not assume an available CUDA GPU from historical machine specifications; verify the current hardware and environment first.

## 3. Deployment context

Two paths recently discussed by the user:

```text
A. Python / Codex in WSL or Linux
   → SSH / bridge
   → Virtuoso / Spectre in a Linux VM

B. Python and Virtuoso / Spectre in the same Linux VM
   → local bridge / local runner
```

Both should connect to the same project Backend through configuration.
Measure which of paths A/B is faster; do not conclude from network round trips or the label "local" alone.
The user's machine, SSH account and paths can change; do not hard-code them in the skill.

## 4. What the first version does not do by default

- Do not add a surrogate, diffusion, Mamba, multi-agent competition or a distributed training cluster. LLM search follows only `docs/brief-llm-sizing-for-astra.md` (the user's 2026-09-29 decision; for that work, the brief replaces this rule's earlier prohibition on LLM search).
- Do not make all device sizes, biases and integer parameters adjustable at once.
- Do not force different circuits into one padded fixed topology or maintain a separate model output layer for each circuit.
- Do not replace Graph Transformer with an "easier" GNN and still claim the original design is complete.
- Do not discuss convergence over thousands of training steps before basic simulation is reliable.
- Do not treat another skill's workflow as a required installation dependency. This skill includes its own task-breakdown and technical-review requirements.

## 5. Implemented engineering choices and items to validate

The current code uses PyG `HeteroData`/packed batches, a fixed specification registry and masks, fixed physical reference normalization, absolute normalized proposals with legalization projection, and separate actor/Q1/Q2 encoders. The real baseline is a GPDK045 five-transistor OTA; do not extend its parameter permissions to other circuits.

GT uses local `TransformerConv`; the benchmark entry point defaults to 32 hidden, 2 layers and 4 heads, explicitly configurable by the user. Global attention, structural distances, surrogates, additional action domains and multiple workers remain later options. Network size, formal budgets and comparative transfer performance across architectures require separate experiments and are not confirmed performance findings.

Without a real PDK/netlist, first produce **structural tests explicitly labelled synthetic**, rather than inventing "commercial-circuit results".

## 6. Working hypothesis for generalization

The research goal is for a common representation and shared policy to reduce real simulations needed for new specifications or topologies.
Test in this order: a single-circuit loop → specification transfer within a category → new topology within a category → cross-category LDO/VCO/OpAmp transfer.
A common graph can represent different circuits; that alone does not demonstrate learned transferable optimization. Judge acceleration on an independent test set.

## 7. Change-record requirements

Record significant changes in the project's own decision file, including date, reason, affected modules, tests and a way to undo them.
Do not silently change other projects by modifying a global skill; save project-specific decisions in the project repository first.

## 8. M3 condition-interface decision (user revision, 2026-09-19)

Historically, the user limited that condition-interface change to M3 and earlier; M4/M5 were later explicitly authorized and completed. The still-applicable condition constraints are: adding a condition interface does not change action dimensions, does not enable PVT/MC training, and retains goal-conditioned SAC as the main optimizer. (2026-09-30 note: the user later authorized reward v2 / v2.1, allowing `real:gpdk045_ota7` to explicitly enable PVT training conditions; see section 1. MC training remains disabled.)

The project already represents conditions with `SimulationCondition/PVTCorner/MonteCarloConfig` and retains an interface for per-sample results of statistical batches. The current default remains TT/27°C/1.0 V: this is the validated OTA baseline, and device names or documentation tables do not authorize changing nominal automatically.

After reading the installed GPDK045 v6.0, the selected conditions were TT/27°C/1.0 V, SS/125°C/0.9 V, FF/−40°C/1.1 V, FS/27°C/1.0 V and SF/27°C/1.0 V. The model entry provides five process sections; the model report gives −40..125°C; the SOA file explicitly limits `max_vdd_1v=1.1`. The project chose 0.9 V for screening, 10% below the original baseline; it is not a PDK-specified minimum operating voltage. These five combinations are neither a full combination set nor a proven worst-case set.

The authoritative project configuration and source summary are in `configs/gpdk045_conditions.json`. This paragraph is a context snapshot: consult the actual configuration and user authorization before future changes, and do not copy this circuit's values to another PDK. Detailed rules and future compute suggestions are in [Conditions and statistical validation](pvt-monte-carlo.md).

## 9. M4/M5 and the encoder interface before M6 (current state)

- M4 implemented nominal SAC, a parameter-group actor, independent action-conditioned twin critics, replay and complete checkpoints. M5 implemented frozen task splits, leakage prevention, independent per-task fine-tuning and cost reports; the real specification pilot did not demonstrate a transfer advantage, and real new-topology and cross-category transfer had not yet been validated.
- The user requested GT/MLP/RGCN/GAT comparisons before M6. `ModelConfig.encoder_type` and `CircuitEncoder/build_encoder` are connected; at that time `port_gnn` remained for compatibility. Synchronized 2026-09-30: only `graph_transformer`, `rgcn` and `gatv2` remain now; `port_gnn` (2026-09-24), `mlp` and `gcn` (2026-09-26) were removed, and `gat` was replaced by `gatv2` that day; all those old names are explicitly rejected. Definitions and shared contracts are in [Learning and actions](learning-and-actions.md); fair comparison is in [Experiments and review](evaluation.md).
- `examples/benchmark_transfer.py --encoders ...` runs scratch/frozen/adapt for every explicitly selected architecture and freezes validation diagnostics for each. Without that argument, it runs only `graph_transformer` scratch/frozen/adapt plus random search and coordinate pattern search (the M5 six-method comparison included the removed port-GNN and runs only at source commit bbdfe36; synchronized 2026-09-30). `examples/train_synthetic_sac.py --encoder ...` selects the encoder of a single learner.
- Pretrain architectures separately; transfer copies same-architecture networks and alpha, while recreating optimizers/replay. Checkpoints save the encoder and configuration and strictly match code/schema/dependencies; M4/M5 checkpoints made before the code change are not automatically migrated, and loading weights across architectures is rejected.
- Acceptance for that code change: 296 offline tests passed, zero failed, zero skipped; the four-architecture smoke test completed 116 synthetic evaluations, covering specifications on the same topology and a new topology with 2→3 action dimensions; new real calls: 0. Records and reproduction commands are in the project's `docs/encoder-ablation.md`; this is interface evidence, not evidence of an advantage in circuit-knowledge transfer.
- That documentation and skill synchronization did not start M6 or new training/simulation. Later stages follow new user requests and actual acceptance results.

## 10. M1 neural-input review (latest addition)

The user later requested a check of M1 support for networks such as GCN/GAT. The original graph information was sufficient; the work added the fixed-semantics homogeneous view `circuit-neural-v1` (49 node columns and 15 edge-feature columns by default), masked dense node inputs and correct group batch offsets for ordinary operators, without rewriting the parser. SAC and the new export share terminal-packing logic; see the [Graph contract](graph-contract.md).

An ordinary `gcn` was added as a control that reads connectivity but not terminal labels, distinct from `rgcn` (`gcn` was removed on 2026-09-26). The latest acceptance result was 319 offline tests passed, zero failed, zero skipped; the six-encoder smoke test made 168 synthetic evaluations, all recovered, with 0 new real calls. Direct-input tests cover opamp/LDO/VCO, a two-stage opamp and an existing real OTA export snapshot. The record is in the project's `docs/m1-neural-inputs.md`; it does not signify completion of M6 or validation of real transfer effectiveness.

## 11. Training-input cache (latest addition)

The user later requested optimization of repeated graph conversions within each update. The learner now enables two bounded LRU levels by default (2048 complete-observation raw inputs, 64 static topology templates), shared by six encoders; deep-copied replay entries hit by content, changes to sizes/specifications/measurements/schema refresh inputs, and network representations are always recomputed with current weights. Real readback and netlist verification remain; M6 was not started.

All 354 offline tests passed, zero failed, zero skipped; losses and parameters agree with caching on/off for six encoders, and cold checkpoints restore exactly. On a CPU synthetic batch=32, the input stage was about 35.66→10.86 ms and the complete GT update about 112.22→62.31 ms; these timings exclude replay deep copies and the backend and are not Spectre speedups. Timing generated 18 synthetic analytical evaluations and 0 new real calls. Interfaces and evidence are in the project's `docs/input-tensor-cache.md`; lasting conventions are in the [Graph contract](graph-contract.md).


## 12. M5 additional real same-category new-topology validation (latest state)

The user requested completion of M5. The work added an independent core/testbench for a GPDK045 seven-transistor Miller two-stage OTA, a strict CDF width-group profile and a serial multi-circuit experiment entry point. Permissions on the original five-transistor circuit's actions are unchanged; the new topology has two action groups: matched input widths and output widths with M6/M7=4:1. Every write, export, measurement and final restoration was verified for both circuits.

Full regression: 440 passed, zero failed/skipped. This round used 7 circuit-acceptance calls + 576 frozen-experiment calls + 2 final requalification calls, totaling 585 real Spectre calls and 288 SAC updates; 3 seeds × 6 methods covered new specifications on the source topology and the new topology. Audits passed for the provenance/isolation of 24 checkpoints, frozen weights and exact recovery of the next update. Final full CDF snapshots, baseline netlists, metrics and PDK entry/MOS digests all matched.

On the new topology, GT scratch/frozen achieved 0/3, GT adaptation 1/3, random 1/3, coordinate 3/3 and port-GNN adaptation 2/3. There is still no evidence of a GT transfer advantage; with only one held-out topology and targets frozen after baseline/parameter-domain acceptance, this is not broad or blind-test generalization. M6, PVT/MC and surrogates were not started in this round. The evidence for this round is the project's `docs/m5-real-topology.md` and `artifacts/local/m5-topology-acceptance-summary.json`; this fills the real-topology gap noted in the earlier first-round record.
