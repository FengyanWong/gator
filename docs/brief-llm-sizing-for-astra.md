# Brief for Astra: SAC and LLM sizing modes, with a free SKY130 benchmark

> **Status (2026-09-30): IMPLEMENTED; free baseline calibration complete; comparison protocol revised; paid slices unapproved.**
> Its precondition, reward v2.1 finished and committed, was met on 2026-09-29
> (`8cf53ae`, `8db46b8`, audit fixes `7d365c3`). For this work it overrides the no-LLM rule ("no LLM search / no LLM inner
> loop") of the Codex skill `.agents/skills/analog-optimizer`.

Written 2026-09-29 for Astra (Codex, `gpt-6-astra`) by the Claude Code session "LLM+RL sizing plan", on the user's
requests "Give a plan over current repo to add LLM support over sizing", then "modify the plan: options from the Codex
or Claude list (so you can choose Fable 5.1 and Astra), add the recommended SKY130 benchmark, the code should go to
analog_optimizer", then "what file should I give to astra". The plan also exists as a private claude.ai page that you
cannot open; this file carries everything you need. Where the page and this brief differ, this brief wins.

**Revised 2026-09-30 after the user added LLM only and SAC with LLM rescue.**
There are exactly four workbench search choices: **SAC**, **LLM warm start → SAC**, **LLM only**, and
**SAC with LLM rescue**. Warm start collects simulated LLM designs, explicitly trains SAC on that experience,
then hands control to SAC. LLM only proposes every search design. Rescue keeps SAC running and asks the LLM
for suggestions when progress stalls. This supersedes the previous two-mode scope and its rescue deferral.
This is an implementation plan, not a claim that the feature or its performance has been verified.

**User's calibration decisions, 2026-09-30:** calibration and comparison use feasibility-only scoring and the
upstream pass rule. There is no after-feasible objective and no reward change. Every metric remains a Probe;
FOML, FOMS, Power, GBW and all other outputs are descriptive on the best feasible design. With feasible rewards
tied at zero, the existing workbench selects the earliest passing design. Bias currents are fixed at upstream
starting values for **every** arm, including every LLM arm; record this benchmark deviation in `plan-benchmark.json`.
Do not extend the optimizer package for current units. Separately assess a workbench-created current FeatureSchema
read-only. During calibration **and every comparison arm**, independently re-simulate **every** GATOR-passing design in the original
upstream evaluator: all values must agree at 1e-9 relative tolerance and verdicts must match. Any disagreement stops
comparison or calibration; report the positive-design checks under G9 (the original 205 comparisons contained zero passes).
Verification launches and elapsed time are separate overhead, never extra search candidates or learning data.
Zero observed passes means positive parity is unqualified; it does not disqualify a circuit from further search.
Before any commit, run the complete suite on the final tree. Audit all sizing and Agent-tab Codex schemas for
strict object rules; sizing must pass, while Agent-tab changes are only to be listed, not implemented. G10's earlier
unauthorized, server-rejected request remains a failed gate; an offline schema audit does not erase it.

**User's benchmark revision, 2026-09-30:** the completed 60-evaluation random/pattern runs are short baseline
evidence, not a reachability test or a circuit selection requirement. Eligible imports must still pass B3. Compare
all four methods with the same longer per-run budget and report uncapped constraint-violation progress alongside
success. The planning default is **2,000 candidate evaluations per circuit/method/seed**, including resets and
failures, with no success-based early stop; this is an engineering starting budget, not a guarantee of feasibility
or approval to spend on LLM calls. The user's optional budget choice remains open until execution is frozen.
Keep the completed calibration evidence unchanged and record this prospective protocol separately in the plan.

It comes AFTER [brief-reward-v2.1-for-astra.md](brief-reward-v2.1-for-astra.md). Both change `src/analog_optimizer/`,
and both touch `ngspice_backend.py`, `frontend/src/panels/Right.tsx` and `agents/run_digest.py`. Start this brief only
when reward v2.1 is finished and committed.

## 0. Launch prompt (paste into Astra)

```
Read /mnt/d/gator/docs/brief-llm-sizing-for-astra.md and carry it out in the order of its section 7.
Precondition: reward v2.1 (docs/brief-reward-v2.1-for-astra.md) is finished and committed. If it is not, stop and say so.
You may edit src/analog_optimizer/ for exactly the package items of section 4 (one digest step).
No real LLM call (claude or codex, including from tests) and no Spectre / Virtuoso / bridge call until the user
approves a ceiling in words (section 8). ngspice simulations on this machine are free and allowed.
No commit, no push, no live frontend build, no backend on 8765. Stop and ask when a requirement cannot be met as written.
Report as section 10 says.
```

## 1. Goal and decisions of record

**Goal.** Compare plain SAC, LLM warm start followed by SAC, LLM-only sizing, and SAC with occasional LLM rescue.
Every proposed design is simulated and judged by the existing evaluation contract. SAC-based modes keep the
selected graph encoder and learn from eligible simulated experience. Compare fairly on a free SKY130 benchmark.

**User decisions of 2026-09-29, extended 2026-09-30.**
- **Four search choices.** `sac` stays the default; add `llm_warmstart`, `llm`, and `sac_llm_rescue`. These search
  choices are separate from the existing scratch / fine_tune / frozen / resume model-loading modes.
- **Learning before warm-start handover.** LLM examples produce explicit SAC updates before SAC selects its first action.
  A successful LLM start replaces random warm-up; there is no second random warm-up block afterward.
- **LLM only.** After the task's baseline measurement, the LLM proposes every search design. There is no SAC training
  or numeric fallback. Simulation feedback informs the next batch.
- **SAC with LLM rescue.** Keep normal SAC warm-up and learning. When progress stalls, request suggestions
  asynchronously; SAC keeps searching while the LLM works. Eligible rescue results enter the same replay buffer.
- **Scope.** Keep the existing graph encoder, SAC losses, reward, replay eligibility and action semantics. Random
  search, pattern search and matched initialization controls belong in benchmark scripts, not the method selector.
- **Code location.** The method logic goes in `src/analog_optimizer/`, as ONE digest step.
- **Models.** Each run chooses its model from either CLI's current list. The measured runs use Fable 5.1 (through
  Claude Code) and `gpt-6-astra` (through Codex) as two separate arms.
- **Benchmark.** The recommended SKY130 benchmark: AnalogGym-Opt now (MIT). AMS-SizingBench only after its authors
  grant a licence; its repository has none.
- **The Agent tab.** Sizing calls use the Agent tab's provider layer. Their live replies appear in the Agent tab as one
  thread per run. The user may type hints into that thread, which marks the run "steered". A run never continues the
  tab's own CLI session.

**Evidence and limits, checked 2026-09-29.** No inspected paper establishes a universally best LLM/RL combination.
- [LORO (2025)](https://arxiv.org/html/2505.10861v1) collects experience using an LLM, pretrains a separate RL agent,
  then continues online learning; continuous-action experiments use SAC. Its ablations found initial training
  important compared with simply mixing the examples into replay. These are control/game tasks, not analog circuits.
  This supports testing a learning-before-handover schedule; it does not establish a suitable circuit sample count
  or justify copying its training budget.
- [ORACLE (August 2026 preprint)](https://arxiv.org/html/2608.04999v1) uses LLM action masking for discrete circuit
  adjustments. LLM guidance helps its cosine variant, but its non-LLM normalized-weight variant also beats the LLM
  variant on reported metrics. This is evidence to test LLM contributions, not a reason to assume they always help
  or to change GATOR's continuous SAC action contract.
- AnaFlow-RF appears in the [MLCAD 2026 program](https://mlcad.org/symposium/2026/program/). Its
  [author's description](https://www.linkedin.com/posts/kaichang-chen_mlcad-analogdesign-rfic-activity-7503354074961080322-tNtR)
  describes initial sizing guidance and selective help when RL stagnates. The full paper was not available for
  inspection here; its experimental comparisons remain unverified. It motivates testing the requested rescue mode.
- [TopoSizing](https://arxiv.org/abs/2509.14169) combines LLM guidance with Bayesian optimization. It is not evidence
  for LLM + SAC or LLM + pattern search. The earlier brief's blanket superiority claims are withdrawn.

**Project hypothesis.** Diverse, simulation-verified starting experience plus bounded initial SAC training may help
under a small simulation budget. This remains to be measured against controls with the same data and update budgets.
Eight starting transitions and eight initial updates below are engineering defaults, not publication-backed optima.
Handover is based on completed experience and training, never a 30-second timer.
Rescue is a separate experiment with bounded interventions; neither it nor LLM-only sizing is assumed to beat SAC.

## 2. What exists (facts, line numbers at commit `73f1668`; they will have moved after reward v2.1)

- `src/gator_workbench/engine.py:513` `_dispatch` picks every candidate: a reset, a random warm-up action, SAC's action,
  or a frozen policy's action.
- `engine.py` `_commit`: steps marked `replay_eligible` become SAC transitions (`Transition.from_step` →
  `replay.add`), whoever chose the action. A finite reward alone is not the admission rule. LLM steps must follow
  the same rule, including eligible simulation failures; they are not automatically successful demonstrations.
- `_maybe_update` requires at least `advanced.batch_size` replay entries. `ReplayBuffer.sample` samples without
  replacement. Current defaults are batch size 8, warm-up 8, and one update per admitted transition. Merely queuing
  LLM designs does not initialize the policy; S6 defines an explicit initial learning phase.
- `src/analog_optimizer/parameters/actions.py:35` `ActionMapper`: actions are absolute, one value in [-1, 1] per
  mutable parameter group, mapped linearly or logarithmically onto its bounds and snapped to its grid
  (`ParameterGroup.project`). `engine.decode_action` mirrors it.
- `src/analog_optimizer/evaluation/benchmark.py:119` `PatternSearch`: existing coordinate-search benchmark. M6's
  small pilot does not establish superiority over SAC or LLM-assisted SAC; repeated deterministic trajectories are
  not independent success evidence. Leave it as a benchmark baseline.
- `src/gator_workbench/agents/`:
  - `claude_code.py` runs `claude -p` with `--json-schema`, no tools and an empty strict MCP config.
  - `codex.py` runs `codex exec` with `--output-schema` and `--output-last-message`, and `--json` if
    `codex exec --help` lists it. Codex is not on the PATH: the user's build is
    `/mnt/c/Users/38094/.codex/bin/wsl/<hash>/codex`, and the hash changes with app updates.
  - `live.py` translates CLI events for the page.
  - `run_digest.py` condenses a run into about 1.9 k tokens.
  - `prompts.circuit_summary` lists devices, terminals, nets and sizes.
  - `catalog.py` is the model list the Agent tab offers. It is STALE (verified 2026-09-20; see W7).
- Measured Claude Code agent calls took 21-87 s and cost $0.17-0.53 notional each. The Codex provider has never
  answered a real request.
- `src/gator_workbench/storage/tables.py:13` `ACTION_SOURCES` allows only `reset`, `random_warmup`, `sac_policy`,
  `mean_policy` and `sampled_policy`.
- `src/gator_workbench/schema.py` `_hashed` leaves `run.reward` and `run.conditions` out of the configuration hash
  while they are at their defaults. New settings follow the same rule.
- `src/gator_workbench/checkpoints.py:318-323`: a source-digest mismatch is fatal for `resume` only. `fine_tune` and
  `frozen` still load, with a recorded warning.
- `src/analog_optimizer/envs/sizing.py:241`: a reset re-simulates the starting design. The default `episode_length` is
  4, so one evaluation in five of a default SAC run repeats the same simulation. Keep this; report it.
- ngspice tasks:
  - Each task lives in `configs/local/workbench/ngspice/<name>/`, as `netlist.cir` plus `task.json`: one deck per task.
  - Results are the deck's `.meas` names and the `let` + `print` names of a `.control` block, read from
    `ngspice -b` output.
  - ngspice-47 is at `~/.local/bin/ngspice`.
- M6 physical runs were a reset plus 8 steps, at 3.4-8.0 s per candidate. Random search met the targets in 2-5 calls in
  6 of 9 runs. Those targets are too easy to separate methods, hence the calibration of section 6.

## 3. Read first; ground rules

Read, in this order:
1. `CLAUDE.md`.
2. The record index `docs/frontend_implementation_status.md`.
3. The last entries of `docs/decisions.md`, including reward v2.1's.
4. `docs/workbench.md`, sections "Start, Pause, Resume, Abort", "Output layout", "An ngspice netlist as a task" and
   "Agent providers".
5. The code named in section 2.

Rules:

1. **Shared working tree and git index.**
   - Stage explicit paths only. Never `git add -A`, reset, stash, amend or force-push.
   - Re-read a shared file right before each edit. Claude sessions are active in this tree.
   - If `git status` shows another session's uncommitted edits in a file this brief needs, stop and ask.
2. **Hash-pinned evidence.** Never edit, reformat, rename or move `configs/*.json`, the pinned `examples/*.py` or
   `tests/fixtures/synthetic/*.scs`. New files beside them are fine.
3. **CLAUDE.md hard rule.** Do not change the SAC algorithm, the reward or the action semantics. `ActionMapper.legalize`
   stays as it is; you only ADD its inverse.
4. **Environment.**
   - Use `~/analog-optimizer-venv`.
   - Full suite: `OMP_NUM_THREADS=1 ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist load`, with a scratch
     `GATOR_WORKBENCH_SETTINGS_DIR`. A script that prepares a run must set it too.
   - Run the evidence-dependent tests on the real tree.
5. **The user's backend on 8765 and `frontend/dist` are theirs.**
   - Use scratch ports and scratch settings.
   - For browser checks, export `GATOR_WORKBENCH_URL` and add it to `WSLENV`.
   - Run `npx tsc --noEmit`, and never `npm run build`.
6. **Slow disk.** `/mnt/d` is a 9p mount: never walk `artifacts/`.
7. **Run the FULL suite, not a selection.** The reward-v2 audit (7.97) found 130 failures that a selection missed.
8. **Paid calls.**
   - Tests use the fake CLI in `tests/workbench/fixtures/fake_cli.py` and the replay or fake clients of S11. They
     never use a real `claude` or `codex`.
   - A real LLM call happens only in section 7 step 7, within the ceiling the user approved.
9. **What may reach an LLM.** Allowed: the circuit summary, the variables with their bounds, the specs, simulation
   results, and operating points of the user's own circuits. Never allowed:
   - credentials or tokens;
   - licence-server output;
   - PDK model files, or tables derived from them (for example gm/ID tables);
   - raw netlist text, because comments can carry instructions.
   Every circuit-derived text is wrapped as DATA with a statement that it carries no instructions.
10. **Docs.** English, plain language first, limits stated bluntly, no claim the data does not support.

## 4. Package requirements (commit A, ONE digest step)

A new subpackage `src/analog_optimizer/search/`, plus one addition in `parameters/actions.py`. No subprocess, network
or CLI code in the package, and no import of `gator_workbench`. With its defaults, nothing behaves differently.

**S1 Proposer interface.** `propose(n, state) -> list[Candidate]` and `observe(result)`.
- A `Candidate` holds the proposal `{group_id: z}`, a source label and optional metadata (for example `call_id`).
- A result holds the proposal, reward, validity, feasibility, normalized violation, metrics, and the per-condition and
  operating-point data when present.
- Given a seed, everything is deterministic except the LLM's text.

**S2 `RandomProposer`.** Seeded and uniform in [-1, 1]. Used as SAC's warm-up, it must draw exactly what the engine
draws today: `rng.uniform(-1, 1)` per group, in `group_ids` order. Gate G1 depends on it.

**S3 Benchmark initialization helper.** A deterministic source of initial candidates for matched controls: either
uniform normalized actions or the task's starting design followed by a seeded Latin hypercube in normalized group
space. This uses the same S6 schedule and legal mapping as the LLM arm, through dependency injection in the benchmark
driver. It is not an additional workbench method or a hidden production setting. Leave the existing `PatternSearch` and
its benchmark API unchanged; do not add a pattern-search wrapper to this package change.

**S4 `SacProposer`.** An adapter around `learner.act` (sampled, or deterministic when frozen). SAC itself does not
change.

**S5 `LlmProposer`.**
- It builds the context (S7), calls an injected `LlmClient` (S11), checks the answer (S8), maps values to actions (S9)
  and queues the accepted candidates.
- Invalid output gets at most ONE repair request. It is counted, and a second failure is recorded as `invalid_output`.
- A refusal, timeout or cancellation is recorded. Apply the method-specific stop or fallback rules in S6;
  never silently change methods.

**S6 Methods and handover.** These four methods are implemented in this digest step.

| method | behaviour |
|---|---|
| `sac` | Today's random warm-up, ordinary update scheduling and SAC exploration, unchanged. The default. |
| `llm_warmstart` | Collect W admitted transitions using LLM designs; run U initial SAC updates; then continue normal SAC exploration and online learning. |
| `llm` | The LLM proposes every search design, k per call, using simulation feedback from earlier batches. No SAC learner. |
| `sac_llm_rescue` | Normal SAC runs; after S evaluations without progress, request k LLM suggestions while SAC continues. Simulate accepted suggestions and learn from eligible results, then continue SAC. |

**Warm start (`llm_warmstart`).** Three persisted phases; the workbench executes learner and simulation operations:

1. **Collect starting designs.** Ask for varied, legal designs, k per call (default 4), and simulate them. Resolve W
   from `warm_start_count`; when unset, use `max(8, advanced.batch_size, advanced.warmup_transitions)`. Explicit W
   must be at least the batch size, and replay capacity must accommodate W. Count only newly admitted transitions,
   not proposals, rejected outputs, reset evaluations or infrastructure failures. Preserve normal eligibility for
   failed circuit simulations. Do not train during this phase; defer the ordinary per-transition updates.
2. **Learn from the starting designs.** When W transitions have committed and their in-flight work has drained,
   run U calls to the existing `learner.update(replay.sample(batch_size))` (default U = 8, positive and bounded).
   These are the initial updates, not additions to deferred updates. Reuse the existing encoder-freeze handling,
   losses, sampling and update logs. No simulation or LLM call is needed in this phase. Do not copy LORO's update
   count onto a tiny circuit dataset or claim that this schedule is a reproduction of LORO.
3. **SAC search.** Only after all U updates commit may SAC choose its first policy action. There is no second
   uniform warm-up, even if the ordinary warm-up setting is larger than an explicitly chosen W. Keep the LLM
   transitions in replay and restore the ordinary online update schedule for subsequent admitted transitions.
   SAC's stochastic policy continues exploring. No further LLM calls occur in this mode.

Resolve W and U before the run starts and record them. Reserve remaining seed slots across lanes so dispatch cannot
overshoot W; an ineligible result releases its slot. Check simulation, call and wall-clock budgets throughout.
Request at most the remaining unreserved slots from the LLM. Wait for a batch's outcomes before requesting the
next batch, so its prompt includes feedback and collection cannot leave an unnecessary call running at handover.
If a limit or `stop_at_first_feasible` ends the run before handover, record that phase as incomplete; do not invent
data, exceed the budget or claim that SAC took control.

**Warm-start failure fallback.** After a terminal provider error, refusal, timeout, exhausted repair, or exhausted LLM ceiling,
retain completed LLM experience and finish accepted queued/in-flight designs within remaining slots and budgets.
If W is still incomplete, fill only its remaining slots using the seeded uniform source, then perform the same
initial learning phase. Record `warmstart_degraded`, the reason
and the LLM/random counts; report such runs separately. This is a fallback, not a second warm-up after success.
Pause/Stop/Force cancellation never activates fallback or starts new work; resume uses the saved phase and budgets.
Warm start supports scratch and fine_tune; resume restores its phase. Reject frozen evaluation because the required
initial learning would violate the frozen-policy contract.

**LLM only (`llm`).**
- Measure the task's starting design once as a baseline, then use only accepted LLM candidates. The baseline is
  labelled `reset`; every search design is labelled `llm_proposal`. No random warm-up, SAC updates or policy checkpoint.
- Use one lane and one long episode in this first version, avoiding SAC's repeated resets. Reject concurrency > 1
  explicitly for this mode. Run the same reward/spec evaluation without constructing an unused SAC learner.
- Simulate each accepted batch before asking again so the next prompt includes its outcomes. Wait responsively when
  no candidate is ready. All baselines, candidates, failures, repairs and calls count against their respective budgets.
- When the LLM ceiling is exhausted, evaluate any accepted queued candidates within the remaining simulation budget,
  then stop with the reason recorded. A terminal provider error, refusal, timeout or exhausted repair also stops
  the mode after already accepted work; it never falls back to SAC or random search. User cancellation starts no new work.
- Persist the queue, history/notes, budgets, current environment state and call records for resume without needing
  neural-network weights. New runs use scratch; resume restores this method's saved state. Reject fine_tune/frozen
  and saved RL model inputs because this method has no policy to load or train.

**SAC with LLM rescue (`sac_llm_rescue`).**
- Start with today's SAC random warm-up and ordinary online updates. There is no LLM warm-start phase and no extra
  U-update block. Arm stall detection only after SAC starts choosing policy actions, using the best result already
  observed during baseline/warm-up as its initial reference.
- Progress means a first valid result, lower best normalized violation before feasibility, first feasibility, or
  higher best reward after feasibility under the fixed reward configuration. Invalid results cannot count as progress.
  Count completed non-reset search evaluations without such progress; circuit failures count, infrastructure errors
  do not. Reset the counter on progress. The threshold S defaults to 8; record the trigger and its best-design snapshot.
- After S consecutive evaluations without progress, request up to k candidates in the background. SAC continues
  dispatching and learning while the call runs. Once ready, valid LLM candidates take the next available search slots;
  required episode resets still run normally. All suggestions use the unchanged action mapping and actual current
  transition state, and eligible results use the ordinary replay admission and update schedule.
- Allow at most one rescue batch pending or in flight. A round includes its initial request and at most one repair;
  both consume call budget. Default maximum R = 2 rounds per run. After its queued/in-flight candidates finish, or a
  failed round ends, require a fresh S-evaluation window before another request. No repeated calls on every stalled step.
- A failed request, exhausted round/call/cost ceiling or rejected candidate leaves SAC running. Never reserve a
  simulation slot while waiting for text. If the run ends before suggestions arrive or can be evaluated, cancel the
  call, record unused candidates and end normally; do not prolong the run or exceed its budget to consume suggestions.
- Persist stall counters, best progress, round/call counts, queue and the learner/replay/RNG together. Scratch and
  fine_tune may use rescue; resume restores progress. Reject rescue with frozen evaluation. Pause/Stop/Force still
  cancel the call and block new work, rather than continuing SAC as a provider-error fallback.

Not built: LLM-to-pattern handover, continuous advisor scheduling, combined warm-start-plus-rescue mode, LLM action
masking, LLM-generated rewards or narrowed bounds. Keep these four choices distinct for interpretable comparisons.

**S7 Context builder.** Inputs:
- the circuit graph (devices, terminals, nets, sizes);
- the mutable groups (id, members, unit, bounds, scale, step, initial value);
- spec rows given by the host as plain rows (id, readable equation, constraint, thresholds, unit, hard, judged at);
- the history (every evaluation's values, metrics, per-spec violations, feasibility and source);
- operating points and per-condition results when present;
- the LLM's previous notes, and user hints.

Output: bounded, deterministic prompt sections.
- Rules and task first.
- The circuit, variables and specs as DATA.
- A digest of the best 8 and last 8 evaluations, with who proposed each.
- Each variable's explored range; failures.
- The worst corner per spec.
- The operating points of the best design: region and vds − vdsat per device. Wrong-region devices are listed first,
  and the instructions ask the LLM to fix the bias before chasing AC or transient specs.
- Repeated designs flagged.
- The method and current phase; starting-transition count for warm start, or stall/round counts and trigger snapshot
  for rescue. Describe observed parameter changes and outcomes
  when available; do not manufacture coordinate-poll evidence or imply causal sensitivities from unrelated designs.
- The budget left.

Keep it under about 12 k tokens (use a character-based estimate) and truncate the history, never the rules.

**S8 Output schema and checks.** The schema, with the limits the checks enforce:
- `analysis`: at most 3,000 characters.
- `notes`: a list, each note with its cited `evaluation_ids`.
- `candidates`: 1 to k. Each gives `values` (every mutable group id, a number in the group's unit), a `rationale` of at
  most 300 characters, and optional `expected` spec values.

The checks:
- A candidate missing a group, with a non-finite value, or with a value outside the bounds is REJECTED, with a reason
  shown to the LLM on the next call. Never clip or rescale silently.
- Snapping to the grid is recorded as snapped.
- Duplicates of an evaluated design are rejected as repeats.
- Check duplicates after legal grid projection, including already queued or in-flight candidates. Request variation
  among starting designs; diversity is a design requirement, not a guarantee that the proposals are useful.

**S9 Inverse mapping.** Add `ActionMapper.encode(values) -> {group_id: z}`, the exact inverse of `legalize`'s mapping
for values inside the bounds, for linear and log scales. Tests:
- `legalize(encode(v)).group_values == project(v)` for random v, linear, log and gridded.
- `encode` of a decoded `z` gives back `z` to 1e-12.
- The bounds map to -1 and +1 exactly.

**S10 Notes rule.** A note is kept only if it cites at least one existing evaluation ID. Dropped notes are counted.
Kept notes are returned to the LLM next call, 1,500 characters at most.

**S11 `LlmClient` interface, clients and the call record.**
- `complete(prompt, schema, *, on_event) -> reply`.
- `ReplayClient` serves the recorded replies in call order. It checks that each prompt's SHA-256 equals the recorded
  one; a mismatch is an error ("the run diverged").
- For asynchronous rescue, record request and reply-release positions in the scheduler event sequence. Deterministic
  replay uses those positions, not real elapsed time, to reproduce interleaving with SAC and the prompt snapshots.
- `FakeClient` serves scripted replies for tests.
- `CallRecord` holds call_id, method, provider, model, effort, timestamps, latency, prompt and reply SHA-256, tokens
  (input, output, cache read, cache write, each null when unknown), notional cost (null when unknown, never 0),
  candidates returned / accepted / rejected with reasons, status, repair flag, notes kept / dropped, and hints included.

**S12 Package tests** under `tests/`: every item above, determinism, replay, and the "defaults change nothing" rule. No
network and no CLI. Include phase transitions, seed-slot accounting, insufficient data, fallback, cancellation and
restored progress. Include LLM-only stopping and rescue progress/round logic. Actual engine behavior is checked
by G11, G13 and G14.

## 5. Workbench requirements (commit B, no digest change)

**W1 Engine.**
- `_dispatch` takes the next candidate from the configured method (S1/S6) through a queue.
- Method `sac` must reproduce today's runs row for row (G1).
- LLM calls run in a background thread, with at most one call in flight per run. Wait for candidates in `llm` and
  `llm_warmstart`'s collection phase; `sac_llm_rescue` continues SAC while waiting. Waiting never consumes a simulation
  reservation or starts a timer-based handover. This resolves the earlier S6/W1 conflict about waiting.
- Pause, Stop and Force cancel an in-flight LLM call by stopping its process. No simulation starts after that, and the
  call is recorded as `cancelled`.
- Replay admission in SAC-based methods is unchanged; warm start changes update scheduling only as S6 defines. Plain SAC's
  dispatch, random-number sequence and update triggers stay unchanged.
- The three SAC-based methods retain `episode_length`, starting-design resets and stop rules. Resets count toward the
  simulation budget but not W; no synthetic transition is created for a reset.
- During initial learning, keep control polling responsive and dispatch no simulation. Record phase, W, U, completed
  initial updates, source counts, fallback status and episode handling in the run manifest/status and checkpoints.
  Save phase progress with the learner, replay and RNG state. Resume from the same durable boundary without repeating
  acknowledged updates or losing queued candidates; test interruption at every phase, including mid-training.
- LLM-only runs use a single baseline and one long episode, no learner/replay updates, and a durable search-state
  save for resume. Preserve evaluation/history records and make all run tabs work without a policy checkpoint.
- Rescue runs persist stall/round state and request/reply event positions along with their normal learner state.
  Cancel unfinished LLM calls on normal run completion too; accepted but unused proposals are recorded as unused.

**W2 Tables.**
- `ACTION_SOURCES` gains `llm_proposal` and the benchmark-only `seeded_warmup`; fallback and the uniform control
  keep `random_warmup`. These source labels do not add workbench methods.
- `evaluations` gains a nullable `llm_call_id` (null means "not chosen by an LLM").
- A new `llm_calls` table follows S11, declared in `storage/tables.py` style so the data dictionary follows.
- Old run folders still load in every tab.
- `agents/run_digest.py` counts rewards by the new sources.
- Tag initial versus online learner updates so U and the first policy version can be audited. Initial updates
  reference the existing data cursor; never create fake evaluations to log training. Old update rows remain readable.
- Rescue records link each round's trigger, call IDs and suggested/evaluated/unused candidates. LLM-only runs have
  zero learner updates and no learning replay admissions; do not fabricate policy versions or weights.

**W3 Run folder.**
- `llm/calls/<call_id>/prompt.txt`, `response.json` and `record.json`.
- `llm/live.jsonl`: run-wide, append-only, every event tagged with its `call_id`, in the event shapes of
  `agents/live.py`, plus one `outcome` event per candidate once it is simulated.

**W4 Settings.** A `run.search` block:
- method; provider; model; effort; candidates per call (default 4); `max_llm_calls`; `max_llm_notional_usd`;
  `llm_call_timeout_seconds` (default 600); `warm_start_count` (unset resolves as S6); `initial_sac_updates`
  (default 8, integer 1-1024); `rescue_stagnation_evaluations` (default 8, positive integer);
  `rescue_max_rounds` (default 2, positive integer); `hints_allowed` (default true).
- It is hashed as absent while at its defaults, added to `_hashed` like `run.reward`.
- All three LLM methods require an enabled provider and both LLM ceilings. W/U and seed capacity checks apply only
  to warm start; stall/round settings only to rescue. Enforce S6's model-loading and concurrency restrictions and
  reject unknown methods. There are no radius, advisor-share or masking settings. Show the resolved W/U and a budget
  warning if warm-start collection plus resets cannot fit; never silently increase simulation authorization.

**W5 Authorization.**
- The Start question states the LLM ceiling (calls, and notional cost where known) next to the simulation budget.
- `runs.prepare_run` records `authorization.llm_calls`, and the run never exceeds it.
- Codex reports no cost here, so for Codex the call ceiling binds alone.

**W6 Clients in `agents/`.** `LlmClient` implementations for `claude -p` and `codex exec`:
- Reuse the providers' argument builders, with a per-kind schema (S8), no tools and no web.
- Use a FIXED working directory per run (`/tmp/gator-llm-<run_id>/`, empty), so the CLI's own prompt can be read from
  the cache on later calls.
- Codex is found through `AgentSettings.cli_path`, or the newest `/mnt/c/Users/38094/.codex/bin/wsl/*/codex`.
- Stream the live events into `llm/live.jsonl`.
- The provider, model and effort default to the Agent tab's current choice.

**W7 Refresh `agents/catalog.py`** to what the vendors' pages said on 2026-09-29. Set `verified='2026-09-29'`.
- **Claude Code** ([model config](https://code.claude.com/docs/en/model-config)):
  - Aliases: `fable` = Fable 5.1, `opus` = Opus 5.5, `sonnet` = Sonnet 5.5, `haiku` = Haiku 4.5, `best`.
  - Pinned IDs: `claude-fable-5-1`, `claude-fable-5`, `claude-opus-5-5`, `claude-opus-5`, `claude-sonnet-5-5`,
    `claude-sonnet-5`, `claude-haiku-4-5`.
  - Efforts: `low`, `medium`, `high`, `xhigh`, `max`; none on Haiku.
  - API list prices, in / out per million tokens: Fable $10/$50, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku $1/$5.
- **Codex** ([models](https://learn.chatgpt.com/docs/models)):
  - `gpt-6-astra` (efforts Light, Medium, High, Extra High, Max, Ultra).
  - `gpt-6-sol` and `gpt-6-luna` (Light to Max).
  - Legacy `gpt-5.5` retires on 2026-10-14. `gpt-5.4` and `gpt-5.4-mini` were retired on 2026-08-31. The table's
    `gpt-5.6-*` entries go.
  - Find the exact effort words the CLI accepts from the local `codex exec --help` (free, no model call) and the Codex
    docs, and update `CODEX_EFFORTS` to match.

**W8 UI** (in `frontend/src/panels/Right.tsx`, Run configuration). Re-read the file first: reward v2.1 and the Monte
Carlo plan also edit it.
- A "Search method" module with short captions and a closed "▸ What each method does" line:
  - The method select contains exactly **SAC** (default), **LLM warm start → SAC**, **LLM only**, and
    **SAC with LLM rescue**.
  - Captions: "Random starting designs, then SAC learns and explores" and "LLM starting designs, initial SAC
    training, then SAC learns and explores" for the first two; "AI proposes every search design" and
    "SAC runs; AI contributes suggestions when progress stalls" for the new modes.
  - SAC-based modes use the selected graph encoder. LLM only hides inactive RL settings/model controls and policy
    checkpoint actions; it still supports saving search progress and resuming the run.
  - Provider, Model and Effort drop-downs from the catalog, with "Same as the Agent tab" as the default.
  - The two ceilings.
  - The rest under a closed "More settings".
- The header shows "LLM n / N" during an LLM run.
- Show the current phase in plain language: "Collecting starting designs", "Learning from starting designs" or
  "SAC search" for warm start, "AI proposing designs" / "Simulating AI designs" for LLM only, and
  "SAC search — AI suggestions pending" while a rescue call runs. Show rescue rounds used and stall progress under
  details. Counts and completed updates explain handover and rescue; elapsed time is not their trigger.
- The user's style rules:
  - Buttons, not timers.
  - Headlines, warnings and buttons stay visible; explanations fold.
  - Plain-language messages, with developer detail under "Technical details".

**W9 The run's thread in the Agent tab.**
- One thread per LLM run, built from `llm/live.jsonl` through a new read-only route. It survives a page reload.
- It follows the run only while that run is active, the way the run tabs follow a running run. Nothing polls when no
  run is active.
- It shows each call's thinking summary, reply and candidates, then each candidate's simulated outcome.

**W10 Hints.**
- A text box in the thread appends to `control/llm_hints.jsonl` through a new route.
- The next call includes the unread hints as the user's own messages. They cannot change bounds, specs or budget:
  S8 still applies.
- Accept hints only while another LLM call is possible. For warm start, disable hints after handover. For LLM only,
  use them in the next batch; for rescue, in the next stall-triggered call. Hints never force a rescue call, bypass
  the stall/round limits or add rescue behavior to warm start.
- The run manifest and summary say `steered: true`, with the hint count.
- The comparison reports steered runs separately.

**W11 `run_review`.** The digest it gets includes the LLM calls' summaries and outcomes, so the Agent tab can answer
"why did it choose that?".

**W12 Operating points on the ngspice lane.**
- The ngspice backend reads each MOS device's operating point (ids, gm, gds, vgs, vds, vth, vdsat, and the region)
  from a control-block readout, keyed to the graph's device IDs.
- It reports them in the raw form `envs/sizing.py` `mapped_operating_points` expects: a dict keyed by the device name
  with `.` for `/` (for example `XU1.M1`), each holding finite numbers per quantity. The native analyzers produce the
  same form. It does not invent a device the graph lacks.
- Test it on `examples/circuits/ngspice_ota5_level1.cir` and on one imported SKY130 circuit.

## 6. Benchmark requirements (free simulations; nothing from the benchmark committed)

**B1 Get AnalogGym-Opt.**
- Clone [AnalogGym-Opt](https://github.com/Computing-Intelligent-Decision-Team/AnalogGym-Opt) OUTSIDE the repository,
  for example to `~/benchmarks/AnalogGym-Opt`, at a pinned commit.
- Check its LICENSE text says MIT. Record the commit and the licence in the plan file (B4).
- Its SKY130 models are bundled under `simulation_files/`.
- Circuits: 16 amplifiers (`amp_acbc`, `amp_affc`, `amp_az`, `amp_azc`, `amp_cfcc`, `amp_clia`, `amp_dacfc`,
  `amp_dfcfc1`, `amp_dfcfc2`, `amp_iac`, `amp_nmcf`, `amp_nmcnr`, `amp_pfc`, `amp_raffc`, `amp_smc`, `amp_tcfc`) and
  `ldo_basic`, each a YAML in `circuit_configs/`.
- Example, `amp_nmcf`:
  - 24 variables over 11 devices: W and L on 0.1 µm steps, integer multipliers, a bias current and a compensation cap.
  - 14 targets, including phase margin ≥ 60°, GBW ≥ 1.2 MHz and power ≤ 0.3 mW.
  - A 100 pF load.
  - An AC/DC testbench and a transient testbench.

**B2 Importer**, a NEW file `examples/import_analoggym.py`. It turns a circuit's YAML and testbenches into an
`ngspice:<name>` task:
- The deck.
- Parameter rows: W and L on their grid; multipliers as `integer` rows. Bias currents stay fixed at the upstream
  starting values and are absent from the mutable domain in every arm (the user-authorized deviation).
- Probe rows: every value the benchmark measures.
- Spec rows: the benchmark's own pass rule, read from its evaluator code (`AmpEnv.py`, `LdoEnv.py`), not guessed from
  the YAML. Under the 2026-09-30 decision, all after-feasible directions are `none`; former objective metrics
  remain Probes and are reported descriptively for the best feasible design.

If a circuit needs both of its decks in one evaluation, merge them into one control block if parity holds. Otherwise
extend the ngspice backend to run several decks per candidate (a W item, covered by tests).

**B3 Parity gate.**
- For 20 seeded random designs per imported circuit, GATOR's measured values must equal AnalogGym-Opt's own evaluator,
  run locally, to 1e-9 relative. The benchmark's pass/fail verdict must match too.
- A circuit that fails is left out and reported. Never loosen the comparison to make it pass.

**B4 Baseline evidence and circuit selection.** The completed free calibration used five random runs and
three deterministic pattern runs of 60 evaluations per B3-eligible circuit. Preserve its 80 runs / 4,800 candidates
and zero passes as historical evidence. The three pattern seed labels produced the same trajectory; they are not
three independent repeats. Do not repeat those short runs to qualify a circuit.

Eligibility is based on B3 import/domain correctness and evaluator agreement. Neither a pattern-search pass within
60 evaluations nor a random-success threshold is a selection requirement. Failure to find a feasible design in
those short runs is not proof of unreachability. Keep real parity failures and invalid starting domains excluded.
Use the first three B3-eligible amplifiers alphabetically as the planned cohort, independently of search outcomes;
the first is the single-circuit pilot. The remaining B3-eligible circuits stay eligible, not failed. Include LDO
only after its B3 problems are resolved. The planned cohort is `amp_acbc`, `amp_affc`, `amp_az`; pilot `amp_acbc`.

Write the current protocol to `artifacts/local/llm-sizing/plan-benchmark.json`: benchmark commit, licence, eligible
pool, deterministic selection rule, seeds, common budget, fixed domain/scoring, verification policy and model-call
ceilings. Preserve the original `calibration/summary.json` and plan snapshot; their old selection result is historical.

**B5 Where the data goes.** Imported tasks stay in `configs/local` and are not committed; committing them is decision L3.
Do not clone, copy or run anything from AMS-SizingBench (`yuxi120407/AutoSizer`). It has no licence file.

**B6 Matched warm-start comparison.** A NEW benchmark driver, `examples/benchmark_llm_sizing.py`, uses the same
collection / initial learning / SAC schedule with an injected candidate source for controls. It does not add public
workbench method values or fabricate LLM call records for controls. Its internal setup records the benchmark arm
and uses the shared scheduler without requiring a real provider. Freeze these arms in `plan-benchmark.json` before
measuring LLM performance:

| arm | initial data | learning schedule |
|---|---|---|
| Plain SAC | Existing uniform random warm-up | Existing scheduling, unchanged |
| Matched random start | W uniform random transitions | U initial updates, then normal SAC |
| Matched seeded start | Starting design, then seeded Latin-hypercube proposals until W admissions | Same U initial updates, then normal SAC |
| LLM warm start → SAC, each provider separately | W LLM transitions, with any fallback disclosed | Same U initial updates, then normal SAC |

The matched random arm separates the effect of LLM data from the extra initial training. The seeded arm tests
whether a simple designed initialization suffices. The starting design already measured by a reset is not free
replay data: the seeded control's action and resulting transition require an actual, budgeted step. Uniform controls
retain the baseline's distribution, including any projected repeats; report duplicate rates for all arms.

Use the same circuit, starting design, parameter domain, targets, reward, episode/reset rules, graph encoder, model
initialization seed, batch size, W, U, online update schedule, concurrency and stopping rules across matched arms.
Keep plain SAC's existing schedule intact and disclose that difference. Report initial and online updates separately.
Pin W/U on development runs before held-out comparisons; do not tune them on the reported evaluation runs. Calibration
is descriptive baseline evidence and must be disclosed; it neither proves reachability nor establishes superiority.

Use a common planning budget of **2,000 candidate evaluations per run** for SAC, every LLM mode and numeric
controls/references, with seeds 17, 29 and 43, concurrency 1 and no first-feasible early stop. Freeze the chosen
budget before starting a comparison; never extend only a failing method or tune the budget from reported outcomes.
The driver requires the saved comparison plan and rejects a different candidate budget or a competing wall/launch
limit. Runs execute serially under one shared output root. The larger budget gives a longer search opportunity;
it does not establish that these targets are reachable with the fixed bias domain.

Count every candidate evaluation, including resets, initial data, repeated designs and failures. A retry retains its
evaluation ID; count every simulator launch/analysis and retry separately. Independently re-simulate **every**
GATOR-passing evaluation (including a passing reset or repeat) in both original upstream testbenches. Compare all
metrics at 1e-9 relative tolerance, no absolute floor, and require identical verdicts. Record false-negative verdict
disagreements too. A disagreement or unresolved verification stops the comparison and blocks subsequent arms.
Verification has separate launch/time accounting and never enters replay, reward, normalization or proposal feedback.
Report total wall time including verification and search/learning time excluding it. No passing design means zero
verification launches and unqualified positive parity, not a failed circuit eligibility gate.

Report success rates **and constraint-violation progress**. At each evaluation retain the current valid design's
uncapped normalized violations for every hard spec and its largest violation. Track the lowest such largest
violation achieved by a single complete valid design, its evaluation ID and its per-spec values. Invalid designs
still consume budget but cannot improve that incumbent. Report baseline-to-best improvement and checkpoints at
60, 100, 250, 500, 1,000 and 2,000 evaluations when reached; an unreached checkpoint is null, not a carried-forward
full-budget result. Keep all runs, including no-feasible and early-ending runs, in the success-rate denominator,
and report budget completion separately. Never combine individually best specs from different designs into a pass.

Also report evaluations/time to first feasible, all Probes for the best feasible design (or null), calls/tokens/cost,
LLM waiting time, initial training time, failures and retries. Unknown token/cost values remain null. Keep circuits,
providers/models, seeds, budgets, steered runs and degraded starts explicit; do not pool unlike groups or claim a
ranking from three seeds. Standalone random and pattern search remain optional reference methods, not selection gates.

Build and verify this harness with FakeClient/ReplayClient and free non-LLM simulations before requesting paid calls.

**B7 LLM-only and rescue comparison.** Extend that driver to run `llm` and `sac_llm_rescue` against the same plain
SAC reference, with providers reported separately. Keep task/spec/reward settings, seeds, concurrency 1 and total
evaluation budget fixed. Disclose the one-baseline LLM-only episode policy and its zero learner updates. Rescue
keeps plain SAC's warm-up, resets and online learning; freeze S/R and the call ceilings before measuring outcomes.
Count suggestions that arrive too late, failed calls, actual rescue evaluations and time spent waiting for proposals.
Do not slow SAC artificially to let a rescue reply arrive; whether latency leaves useful intervention time is part
of the result. All B6 cost, feasibility, failure and steering reporting rules also apply. Free checks use fake or
replayed responses; paid runs remain behind section 7's explicit authorization.

## 7. Order of work

**Preflight already completed before this plan revision.** Reward v2.1 commits are `8cf53ae` and `8db46b8`; the
user-authorized shared baseline is `5a39f89`. The full suite passed 1,417 tests and TypeScript passed. The frozen
baseline and seeded SAC output are under `artifacts/local/llm-sizing/baseline/` and `g1-before/`; the historical
`acceptance-summary.json` records pre-implementation checks, not acceptance of this revised feature. Its old
scheduling question is resolved by S6/W1 here. That historical preflight predates implementation and the G10 rejected-call incident. Recheck
status and relevant source hashes before reusing this evidence; if they match, continue from step 2 without
repeating completed preflight work. Preserve the historical record and update the acceptance summary when resuming.

1. **Preflight.**
   - Confirm that reward v2.1 is committed.
   - Run `git status`. Stop on another session's uncommitted edits in files you need.
   - Record `source_digest()`, and snapshot `src/analog_optimizer/` and the tree for G1.
   - Run the full suite once, and write down any failures that already exist.
2. **Package (implemented in `4634200`).** S1-S12 for the four methods, with gates G2 and G5, G1's package half and
   G11/G13/G14 schedule tests. Initial training uses existing SAC operations; do not edit SAC or replay algorithms.
3. **Workbench (implemented in `7c7a0ff`).** W1-W12, including warm-start learning, LLM-only state and asynchronous rescue,
   with gates G1, G3, G4, G6, G7, G11, G13 and G14.
4. **Benchmark.** B1-B7, with gates G9 and G12. Prepare the controls and all four modes before any paid experiment.
5. **Checks and docs.**
   - Full suite and `tsc`.
   - Browser checks for W8-W10 against a scratch backend (G8), then G10.
   - Docs as section 10 lists.
6. **Report**, then stop.
7. **Only with a ceiling the user approved in words** (section 8):
   - (a) **Measured calls.** At most 2 calls with Fable 5.1 through Claude Code, and at most 2 with `gpt-6-astra`
     through Codex, from the fixed working directory. The second call of each shows whether the prompt was cached.
     Record latency, tokens and notional cost. A successful response would be the first validated live sizing
     response; G10 retains its earlier rejected request.
   - (b) **Warm-start pilot.** One chosen circuit, seeds 17, 29, 43; `llm_warmstart` with each of the two providers
     is six runs. Proposed settings: W = 8, U = 8, batch size 8, k = 4, concurrency 1, the B6 common
     budget (planning default 2,000 candidates per run, including resets), and no early stop, so handover and
     subsequent SAC behavior can be observed. The planned
     successful path needs two LLM calls per run; propose a hard ceiling of four per run, including repairs and
     replacements: **24 calls total**, separate from 7a's four. These are proposed limits, not authorization. If
     data are insufficient inside the ceiling, apply and disclose S6 fallback; do not expand the limit.
   - Run B6's plain SAC and both matched non-LLM controls on the same circuit and seeds. Include standalone random
     and pattern search with the same candidate-evaluation budget. Report their reset/update differences.
   - (c) **LLM-only and rescue pilot, separately approved.** Use the same circuit, seeds, providers, k = 4,
     concurrency 1 and the same B6 budget, with no early stop. Each added method has six runs. At 2,000 evaluations
     and k = 4, LLM only needs at least 500 full-batch calls per run after its baseline. Propose **550 calls per
     LLM-only run** (3,300 total, including repairs/replacements), and S = 8, R = 2 with four calls per rescue run
     (24 total). This is **3,324 proposed additional calls**, not included in 7a/7b and not authorized. A smaller
     call ceiling can end LLM only early and must be labelled budget-incomplete, not a completed 2,000-evaluation run. Stop or
     continue SAC at exhausted ceilings as S6 specifies. User approval can authorize a smaller slice; this plan
     does not authorize any calls. Report the actual evaluated candidates if a call ceiling ends LLM-only early.
   - Report per run, with no pooling and no ranking claim at n = 3. Then stop.

Not in this brief:
- A larger multi-circuit paid study or a claim of superiority from three repeats.
- Pattern-search hybrids, combined warm-start-plus-rescue, continuous LLM advice, action masking and reward/bounds generation.
- Additional ablations of W/U, operating points, notes, batch proposal size or model strength. A later study can
  include a no-initial-training control; it is not an additional UI mode or a reason to omit the required initial phase.
- Any Spectre run (a later stage: OTA7 and LDO, on a budget the user sets).
- AMS-SizingBench.

## 8. Decisions for the user (ask before the step that needs them)

- **L1**, before each paid slice: explicit call and notional-cost ceilings. Proposed call caps are 4 for 7a,
  24 for 7b, and 3,324 for 7c (3,300 LLM-only plus 24 rescue at the provisional 2,000-evaluation budget). These are separate ceilings; approving one does not
  approve the others. A notional-cost cap must be agreed where cost is known. No paid calls are yet approved.
- **L2**, with L1: confirm the measured model IDs and effort after checking CLI support; proposed effort is `high`
  for both requested models. Free implementation and fake/replay checks do not need a development-model decision
  or real sizing-model calls; keep the current coding session's settings.
- **L3**: imported benchmark tasks remain uncommitted by default. Ask only if the user later requests a change to
  that choice; do not block free import or calibration on it.

Defaults already chosen; do not ask:
- Keep upstream pass targets unchanged; B4 short-run outcomes do not gate eligibility.
- Operating points go to the LLM; no PDK-derived tables.
- Resets are kept for SAC methods.
- Hints are allowed and mark the run steered.
- Exactly four workbench search choices, with waiting, initial learning and rescue scheduling as S6/W1 specify.
- W/U are counts, not a handover timer; defaults are provisional and recorded.
- Rescue is included as a separate mode; LLM action masks and bound/reward changes are not built.

## 9. Acceptance gates

- **G1: SAC unchanged.** Two scratch settings folders run the same seeded MOCK config (method `sac`) on the pre-change
  snapshot and on the new tree. The raw tables must be equal row for row. Ignore only timestamps, durations, run IDs,
  paths and the recorded code digest.
- **G2: Replay.** Each of `llm_warmstart`, `llm` and `sac_llm_rescue` runs on MOCK with `FakeClient`, then with
  `ReplayClient`, with identical proposals, phases, update counts and rows under a deterministic scheduler.
  Rescue replays recorded request/reply-release event positions, not provider wall-clock timing.
- **G3: Ceilings and cancelling.** Calls never exceed the ceilings. Pause, Stop and Force during an in-flight call start
  no simulation, and the call is recorded as `cancelled`.
- **G4: Links.** Every LLM-chosen evaluation links to a complete call record.
- **G5: One digest step.** The digest before and after are recorded. `git diff --stat -- src/analog_optimizer`
  lists only the planned files.
- **G6: Injection.** A spec, probe or variable named "ignore previous instructions and ..." stays DATA, and the output
  is still checked by S8.
- **G7: Old data.** An existing MOCK run folder loads in every tab. `fine_tune` and `frozen` load a pre-change
  checkpoint with the warning recorded; `resume` refuses it in words.
- **G8: Suites.** The full suite and `tests/workbench` pass, `tsc --noEmit` is clean, and the browser checks for W8-W10
  pass on scratch ports. The method selector has exactly four choices; phase progress, rescue status, hint rules
  and LLM-only tabs without policy checkpoints are verified. S6 compatibility rules hold in both schema and UI.
- **G9: Benchmark.** B3 parity and historical B4 baselines are recorded, including real import/parity exclusions.
  No 60-evaluation reachability selection rule remains. All comparison passes require independent two-deck
  verification with strict values/verdicts and stop-on-disagreement; positive parity stays unqualified until observed.
  G12 also checks the common per-run budget and progress reporting for no-feasible and incomplete runs.
- **G10: Nothing paid.** Before step 7, no real `claude` or `codex` model request ran, `agent_audit.jsonl` is unchanged,
  and no bridge or Spectre call was made. W7's local `--help` inspection is allowed; it must not invoke a model.
- **G11: Learning before handover.** A real SACLearner on synthetic MOCK results receives W eligible initial
  transitions, completes exactly U initial updates, then supplies its first policy action with the corresponding
  policy version. Verify finite updates and actual weight changes, source counts, normal online updates afterward,
  no automatic second random warm-up, no fake reset transitions, no early handover when replies/data are delayed,
  and no seed overshoot with parallel lanes. Cover insufficient data/budget, provider fallback, all control actions,
  scratch/fine_tune and resume in each phase. Weights and phase counters restore together. These tests establish
  correct integration, not improved circuit performance.
- **G12: Fair controls.** Benchmark controls use the same collection/handover code and effective W/U as the LLM arm.
  Recorded plans and outputs expose seeds, source labels, resets, duplicate rates, updates and all cost counters.
  B7 runs expose LLM-only episode differences and rescue latency/unused suggestions. An offline control run cannot
  invoke a real LLM. Plain SAC still satisfies G1.
- **G13: LLM only.** On MOCK, exactly one baseline precedes only LLM-proposed search designs, with no random/SAC
  candidate or learner update. Verify feedback between batches, ceilings, refusal/timeout/invalid-output stopping,
  responsive controls and faithful resume without model weights. No fallback silently changes the method.
- **G14: Rescue.** On MOCK with controlled progress and delayed replies, verify S-evaluation triggers, no requests
  during random warm-up, resets/infrastructure failures excluded, and progress resetting the counter before/after
  feasibility. SAC must dispatch and learn while a reply is pending; accepted suggestions use normal replay and
  updates. Check fresh stall windows, one pending batch, R-round/call ceilings, failure continuation, cancellation,
  late/unused replies, total evaluation budget and resume with identical counters. No rescue means the SAC sequence
  matches the plain SAC control. Fake timing tests establish scheduling correctness, not a performance benefit.

## 10. Reporting back

- **Docs.**
  - A new page `docs/llm-sizing.md`: the four methods, warm-start learning/handover, LLM-only stopping/resume,
    asynchronous rescue, how to run each, recorded data, literature limits and the benchmark controls.
  - A `docs/decisions.md` entry: the user decisions of 2026-09-29/30 and both digests.
  - The next free entry in `docs/workbench-log/7.119-and-later.md`, plus its row in the index.
  - `artifacts/local/llm-sizing/acceptance-summary.json`: the gates, the digest, the counts, the benchmark commit, and
    the parity and calibration results.
- **To the user.**
  - The files changed, package and workbench apart.
  - The digest before and after.
  - Each gate with its evidence path.
  - What failed or was skipped, and why.
  - The section 8 questions still open.
- Nothing is committed until the user says so. Then package (A) and workbench (B) go in as separate commits, with
  explicit paths.
