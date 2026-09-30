# Brief for Astra: LLM-driven sizing methods in the optimizer, with a free SKY130 benchmark

> **Status (2026-09-30): NOT STARTED.** Its precondition, reward v2.1 finished and committed, was met on 2026-09-29
> (`8cf53ae`, `8db46b8`, audit fixes `7d365c3`). For this work it overrides the no-LLM rule ("no LLM search / no LLM inner
> loop") of the Codex skill `.agents/skills/analog-optimizer`.

Written 2026-09-29 for Astra (Codex, `gpt-6-astra`) by the Claude Code session "LLM+RL sizing plan", on the user's
requests "Give a plan over current repo to add LLM support over sizing", then "modify the plan: options from the Codex
or Claude list (so you can choose Fable 5.1 and Astra), add the recommended SKY130 benchmark, the code should go to
analog_optimizer", then "what file should I give to astra". The plan also exists as a private claude.ai page that you
cannot open; this file carries everything you need. Where the page and this brief differ, this brief wins.

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

**Goal.** Let an LLM propose circuit designs inside GATOR's sizing loop, alone or together with SAC and pattern search.
Then compare it fairly with the existing methods on a free SKY130 benchmark, with every run recorded the way GATOR
records runs today.

**User decisions of 2026-09-29.**
- **Code location.** The method logic goes in `src/analog_optimizer/`, as ONE digest step.
- **Models.** Each run chooses its model from either CLI's current list. The measured runs use Fable 5.1 (through
  Claude Code) and `gpt-6-astra` (through Codex) as two separate arms.
- **Benchmark.** The recommended SKY130 benchmark: AnalogGym-Opt now (MIT). AMS-SizingBench only after its authors
  grant a licence; its repository has none.
- **The Agent tab.** Sizing calls use the Agent tab's provider layer. Their live replies appear in the Agent tab as one
  thread per run. The user may type hints into that thread, which marks the run "steered". A run never continues the
  tab's own CLI session.

**Why this design.** It follows the strongest published evidence, all read on 2026-09-29.
- An LLM alone reaches good designs in few simulations, but stalls just short of the specs.
- The best-controlled analog results come from letting the LLM lead and handing over to a numeric optimiser when
  progress stalls:
  - [TopoSizing](https://arxiv.org/abs/2509.14169): Spectre, SMIC 55 nm, 10 runs; 18/32/18/22 simulations against
    TuRBO's 25/66/107/37.
  - [AnaFlow](https://arxiv.org/abs/2511.03697), ICCAD 2025: 9 and 64 simulations against 1,035 and 1,808 for its RL
    optimiser alone.
- The strongest cross-domain hybrid is [Centaur](https://arxiv.org/abs/2603.24647). CMA-ES leads, and the LLM supplies
  about 30 % of the trials while seeing CMA-ES's state.
- [Rodrigues 2026](https://arxiv.org/abs/2606.21641): a claimed "LLM warm start" gain came from the default design,
  so a warm start needs a matched non-LLM control.
- [StateTune](https://arxiv.org/abs/2608.23601): LLM memory must be backed by evidence.
- [SABLE](https://arxiv.org/abs/2607.03701) and [AaLLM](https://arxiv.org/abs/2608.13472): LLM agents need operating
  points, worst-corner values, a strict output contract and stall rules.

## 2. What exists (facts, line numbers at commit `73f1668`; they will have moved after reward v2.1)

- `src/gator_workbench/engine.py:513` `_dispatch` picks every candidate: a reset, a random warm-up action, SAC's action,
  or a frozen policy's action.
- `engine.py:706-715`: every step with a valid reward becomes a SAC transition (`Transition.from_step` →
  `replay.add`), whoever chose the action. So LLM-chosen steps are learnable by SAC with no change to SAC.
- `src/analog_optimizer/parameters/actions.py:35` `ActionMapper`: actions are absolute, one value in [-1, 1] per
  mutable parameter group, mapped linearly or logarithmically onto its bounds and snapped to its grid
  (`ParameterGroup.project`). `engine.decode_action` mirrors it.
- `src/analog_optimizer/evaluation/benchmark.py:119` `PatternSearch`: M6's coordinate search. It was the strongest M6
  method: 3/3 successes in every class.
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

**S3 `PatternSearchProposer`.**
- It wraps `evaluation.benchmark.PatternSearch`, leaving that class unchanged. Moving the class is allowed only if the
  old import keeps working.
- It re-centres on ANY better result it observes, including LLM candidates.
- Its starting radius is configurable (default 0.5, as in M6), so it can do fine closure from a given design.

**S4 `SacProposer`.** An adapter around `learner.act` (sampled, or deterministic when frozen). SAC itself does not
change.

**S5 `LlmProposer`.**
- It builds the context (S7), calls an injected `LlmClient` (S11), checks the answer (S8), maps values to actions (S9)
  and queues the accepted candidates.
- Invalid output gets at most ONE repair request. It is counted, and a second failure is recorded as `invalid_output`.
- A refusal, a timeout or a cancellation is recorded as such. The method then falls back as S6 says for that method,
  and never silently.

**S6 Methods (hybrid schedules).** All of these land in this one digest step, so that phase-3 comparisons need no
second one.

| method | behaviour |
|---|---|
| `sac` | Today's behaviour. The default. |
| `random`, `pattern_search` | The M6 baselines, now available to the workbench engine. |
| `llm` | Every candidate from the LLM, k per call. Stops when the simulation budget or the LLM ceiling is reached. |
| `llm_first` | The LLM proposes until the best normalized violation has not improved for S evaluations (default 8). Then pattern search starts from the LLM's best design, with a closure radius (default 0.125). If pattern search stalls for S evaluations, the LLM is asked once more, at most R times (default 2). |
| `llm_advisor` | Pattern search leads and never waits. LLM calls run asynchronously and their candidates jump the queue; the target LLM share of dispatched candidates is about 1/3. The LLM's context includes pattern search's centre, radius, best 5 and last 20. |
| `llm_warmstart` | The first W candidates (default 8, the same as `warmup_transitions`) come from the LLM; then SAC continues with those transitions in replay. |
| `seeded_warmstart` | The control for `llm_warmstart`: the first W are the starting design plus a seeded Latin hypercube, no LLM; then SAC. |
| `sac_llm_rescue` | SAC runs; when the best violation has not improved for S evaluations, the LLM is asked for k candidates. |

Not built: `llm_bounds`, where the LLM narrows the bounds. It would change task definitions, and it stays for later.

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
- In the hybrids, the numeric search's latest ± results as directional hints.
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
- `FakeClient` serves scripted replies for tests.
- `CallRecord` holds call_id, method, provider, model, effort, timestamps, latency, prompt and reply SHA-256, tokens
  (input, output, cache read, cache write, each null when unknown), notional cost (null when unknown, never 0),
  candidates returned / accepted / rejected with reasons, status, repair flag, notes kept / dropped, and hints included.

**S12 Package tests** under `tests/`: every item above, determinism, replay, and the "defaults change nothing" rule. No
network and no CLI.

## 5. Workbench requirements (commit B, no digest change)

**W1 Engine.**
- `_dispatch` takes the next candidate from the configured method (S1/S6) through a queue.
- Method `sac` must reproduce today's runs row for row (G1).
- LLM calls run in a background thread, with at most one call in flight per run. Lanes wait for the LLM only in
  method `llm`.
- Pause, Stop and Force cancel an in-flight LLM call by stopping its process. No simulation starts after that, and the
  call is recorded as `cancelled`.
- Replay admission is unchanged.
- Methods that do not learn from episodes (`llm`, `random`, `pattern_search`, `llm_first` while the LLM or pattern
  search leads) run one long episode: one baseline evaluation, no repeated resets. SAC-based methods keep
  `episode_length`.
- Record the method and the episode handling in the run manifest.

**W2 Tables.**
- `ACTION_SOURCES` gains `llm_proposal`, `coordinate_poll`, `random_search` and `seeded_warmup`.
- `evaluations` gains a nullable `llm_call_id` (null means "not chosen by an LLM").
- A new `llm_calls` table follows S11, declared in `storage/tables.py` style so the data dictionary follows.
- Old run folders still load in every tab.
- `agents/run_digest.py` counts rewards by the new sources.

**W3 Run folder.**
- `llm/calls/<call_id>/prompt.txt`, `response.json` and `record.json`.
- `llm/live.jsonl`: run-wide, append-only, every event tagged with its `call_id`, in the event shapes of
  `agents/live.py`, plus one `outcome` event per candidate once it is simulated.

**W4 Settings.** A `run.search` block:
- method; provider; model; effort; candidates per call (default 4); `max_llm_calls`; `max_llm_notional_usd`;
  `llm_call_timeout_seconds` (default 600); stagnation window; closure radius; advisor share; warm-start count;
  `hints_allowed` (default true).
- It is hashed as absent while at its defaults, added to `_hashed` like `run.reward`.
- Validation: an LLM method needs a provider other than `disabled`, and both LLM ceilings.

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
  - The method select: SAC (default), Random search, Pattern search, LLM only, LLM first then pattern search, Pattern
    search with LLM advice, LLM warm start then SAC, Seeded warm start then SAC (control), SAC with LLM rescue.
  - Provider, Model and Effort drop-downs from the catalog, with "Same as the Agent tab" as the default.
  - The two ceilings.
  - The rest under a closed "More settings".
- The header shows "LLM n / N" during an LLM run.
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
- Parameter rows: W and L on their grid; multipliers as `integer` rows; bias currents on a `log` scale.
- Probe rows: every value the benchmark measures.
- Spec rows: the benchmark's own pass rule, read from its evaluator code (`AmpEnv.py`, `LdoEnv.py`), not guessed from
  the YAML. Max/min objectives become the after-feasible direction.

If a circuit needs both of its decks in one evaluation, merge them into one control block if parity holds. Otherwise
extend the ngspice backend to run several decks per candidate (a W item, covered by tests).

**B3 Parity gate.**
- For 20 seeded random designs per imported circuit, GATOR's measured values must equal AnalogGym-Opt's own evaluator,
  run locally, to 1e-9 relative. The benchmark's pass/fail verdict must match too.
- A circuit that fails is left out and reported. Never loosen the comparison to make it pass.

**B4 Calibration** (free), with fixed seeds, per circuit that passed B3:
- random search, 5 runs × 60 simulations;
- pattern search, 3 runs × 60 simulations.

Choose 3 amplifiers where random search succeeds in at most 1 of 5 runs, and pattern search, or AnalogGym-Opt's own RL
(optional; CPU only), shows the specs are reachable. Add `ldo_basic` if it passed B3.

Write `artifacts/local/llm-sizing/calibration/summary.json` and a plan file
`artifacts/local/llm-sizing/plan-benchmark.json`: benchmark commit, licence, circuits, seeds, budgets, the chosen
circuits and why.

**B5 Where the data goes.** Imported tasks stay in `configs/local` and are not committed; committing them is decision L3.
Do not clone, copy or run anything from AMS-SizingBench (`yuxi120407/AutoSizer`). It has no licence file.

## 7. Order of work

1. **Preflight.**
   - Confirm that reward v2.1 is committed.
   - Run `git status`. Stop on another session's uncommitted edits in files you need.
   - Record `source_digest()`, and snapshot `src/analog_optimizer/` and the tree for G1.
   - Run the full suite once, and write down any failures that already exist.
2. **Package (commit A).** S1-S12, with gates G2 and G5, and G1's package half.
3. **Workbench (commit B).** W1-W12, with gates G1, G3, G4, G6 and G7.
4. **Benchmark.** B1-B5, with gate G9.
5. **Checks and docs.**
   - Full suite and `tsc`.
   - Browser checks for W8-W10 against a scratch backend (G8), then G10.
   - Docs as section 10 lists.
6. **Report**, then stop.
7. **Only with a ceiling the user approved in words** (section 8):
   - (a) **Measured calls.** At most 2 calls with Fable 5.1 through Claude Code, and at most 2 with `gpt-6-astra`
     through Codex, from the fixed working directory. The second call of each shows whether the prompt was cached.
     Record latency, tokens and notional cost. The first Codex call is also the provider's first real request.
   - (b) **The phase-2 first slice.** One chosen circuit, 3 repeats, methods `llm` and `llm_first`, each with Fable 5.1
     and with Astra: about 70 LLM calls and free simulations. Also random, pattern search and SAC (GT) with the same
     60-simulation budget and seeds 17, 29, 43.
   - Report per run, with no pooling and no ranking claim at n = 3. Then stop.

Not in this brief:
- The full phase-2 set (about 420 LLM calls).
- Phase-3 comparisons (`llm_advisor`, `llm_warmstart` against `seeded_warmstart`, `sac_llm_rescue`, mixed replay, and
  ablations without operating points, without notes, k = 1 against 4, and model strength).
- Any Spectre run (phase 4: OTA7 and LDO, on a budget the user sets).
- AMS-SizingBench.

## 8. Decisions for the user (ask before the step that needs them)

- **L1**, before step 7: the LLM ceilings for 7a (proposed: 4 calls) and 7b (proposed: 70 calls). Fable 5.1 is the
  model heaviest on the user's Max usage; they hit its limit on 2026-09-29.
- **L2**, before step 5: the development model and the measured effort. Defaults: Sonnet 5.5 or `gpt-6-luna` for
  development; effort `high` for both measured models, with higher efforts only as an ablation.
- **L3**, at step 4: may imported benchmark tasks be committed? Default: no.

Defaults already chosen; do not ask:
- Specs are calibrated harder (B4).
- Operating points go to the LLM; no PDK-derived tables.
- Resets are kept for SAC methods.
- Hints are allowed and mark the run steered.
- `llm_first` before `llm_advisor` in comparisons.
- `llm_bounds` is not built.

## 9. Acceptance gates

- **G1: SAC unchanged.** Two scratch settings folders run the same seeded MOCK config (method `sac`) on the pre-change
  snapshot and on the new tree. The raw tables must be equal row for row. Ignore only timestamps, durations, run IDs,
  paths and the recorded code digest.
- **G2: Replay.** A MOCK run with `FakeClient` for each LLM method, replayed with `ReplayClient`, gives identical
  proposals and rows.
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
  pass on scratch ports.
- **G9: Benchmark.** B3 parity and B4 calibration are recorded.
- **G10: Nothing paid.** Before step 7, no real `claude` or `codex` process ran, `agent_audit.jsonl` is unchanged, and
  no bridge or Spectre call was made.

## 10. Reporting back

- **Docs.**
  - A new page `docs/llm-sizing.md`: what each method does, how to run one, what is recorded, and the limits.
  - A `docs/decisions.md` entry: the user decisions of 2026-09-29 and both digests.
  - The next free entry in `docs/workbench-log/7.101-and-later.md`, plus its row in the index.
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
