# SAC and LLM sizing

The Run panel has four search methods. The backend schema supplies their identifiers to the frontend;
the API validates the same restrictions that the page shows.

| Search method | What proposes designs | What learns |
|---|---|---|
| **SAC** | Existing random warm-up, then SAC | Existing SAC updates |
| **LLM warm start → SAC** | AI supplies starting designs, then SAC takes over | SAC trains on the starting experience before selecting its first policy action |
| **LLM only** | AI proposes every search design after one baseline measurement | No SAC learner |
| **SAC with LLM rescue** | SAC runs normally; AI contributes suggestions after progress stalls | SAC learns from eligible results from either source |

Search method is separate from model loading: scratch, fine tune, frozen policy, or resume. All AI methods
reject frozen policy. LLM only supports scratch and resume with one simulation lane. It has no graph encoder,
policy checkpoint or replay training. The other three methods retain the selected graph encoder and SAC algorithm.
Pattern search remains an existing benchmark baseline and is not an RL encoder or an additional workbench method.

## Starting a run

Load and validate the circuit's Parameters, Probes and Specs as usual. Choose a search method in the Run panel.
For an AI method, choose Claude Code or Codex, its model and effort, or inherit the Agent tab's choices. Run creation
resolves the inherited Agent settings into the effective configuration. Changing the Agent tab does not change an
existing run's recorded choices. A provider-default model still means the CLI/account default.
An inherited effort applies only when the selected model supports it; otherwise the provider default is shown and
recorded. The API rejects an explicitly requested unsupported effort, using the same model catalog as the dropdown.

Set an explicit maximum number of AI calls. Claude Code also needs a maximum notional dollar cost. Codex does not
provide dollar accounting here, so its cost stays unknown and the call ceiling applies. The confirmation names
these limits separately from the simulation budget. A model call, including a repair request, consumes an AI call;
only an evaluation that starts consumes an evaluation slot. Resets and unsuccessful evaluations count too.

The **More settings** fold contains batch size for proposals, timeout, warm-start counts, rescue counts and hints.
The defaults are provisional engineering settings, not measured optima:

| Setting | Default | Meaning |
|---|---|---|
| Designs per call, k | 4 | Upper limit on accepted designs from a reply |
| Starting transitions, W | max(8, training batch size, ordinary warm-up count) | Newly admitted transitions needed before initial training |
| Initial SAC updates, U | 8 | Updates completed before the first SAC policy action |
| Rescue stall window, S | 8 | Eligible search evaluations without progress before requesting help |
| Rescue round limit, R | 2 | Maximum intervention rounds |
| Call timeout | 600 seconds | Cancels a call that takes too long; it is not a handover timer |

W must fill a training batch and fit in replay. The page shows the resolved W/U and warns when the evaluation
budget cannot cover W plus required resets. A partial starting batch never pretends to have finished training.

## Handover and failure behavior

Warm start has three saved phases: collect W admitted transitions, complete U SAC updates, then SAC search.
Resets, queued proposals and infrastructure failures do not count toward W. Circuit failures retain the existing
replay eligibility rules. There is no training during collection and no second random warm-up after successful
handover. SAC's policy continues stochastic exploration; that is different from uniform random warm-up.

A failed warm start may fill its remaining W slots with recorded random proposals. It keeps its AI history and
is marked degraded. Once W is filled, it performs the same U initial updates. It does not silently increase a call
or cost ceiling. Unknown Claude cost stops further calls because another request cannot be bounded reliably.

LLM only makes one baseline measurement and then uses one long logical episode. The next AI batch sees feedback
from earlier simulations. Refusal, exhausted limits or invalid output after one repair stops the search; no numeric
fallback changes its method. Its progress save contains history, queue and budget without neural weights.

Rescue retains normal SAC warm-up, episode resets and online updates. Before feasibility, lower violation is
progress; after feasibility, the existing feasible reward determines progress. Resets and infrastructure failures
do not advance the stall counter. A single pending batch is allowed. SAC keeps proposing and learning while a
reply is pending. A finished or failed round requires a fresh stall window before another round. Late suggestions
are recorded as unused when the run ends. Provider latency is part of this experiment; the engine does not delay
SAC to make a rescue useful.

Pause, Stop and Force cancel an in-flight provider process and prevent another simulation from starting.
Pause retains accepted queued proposals. Resume restores phase counts together with the corresponding learner
state. Initial updates are saved before acknowledgement so an acknowledged update is not repeated. Evaluation
receipts and saved batches also preserve AI history and consumed queue entries newer than the learner checkpoint.
As in ordinary SAC recovery, online learner updates newer than a checkpoint are not recoverable; durable experience
can be readmitted, and that limitation is recorded. An unresolved physical launch still blocks resume.
If transition archives were disabled, a recovered warm start counts only transitions actually restored into replay.
It collects the missing starting experience within the remaining budgets before handing over to SAC, and records
that adjustment in the resume event. Failure context is redacted and bounded before entering AI history;
license-server output is withheld entirely.

## AI thread and evidence

The Agent tab has a separate sizing thread for the selected run. It shows provider replies, proposed values,
rejections and simulation outcomes. It reloads from run files. A hint applies to a future eligible call, does not
trigger rescue or alter requirements, and marks the run steered. The API rejects hints when no further call is
possible. Accepted and included hint counts are separate. A run never continues the Agent tab's own CLI session.

The model receives engineering data: circuit connectivity and sizes, legal variable domains, specs, bounded
evaluation history, operating-region information, condition results and cited notes. Circuit text is explicitly
untrusted DATA. Raw netlists, credentials, licence output and PDK model files or derived tables are excluded.
Rules remain intact if history must be shortened. An oversized fixed context is refused visibly.

Proposals must contain every mutable group, finite values and legal bounds. Legal grid snapping is recorded.
Duplicates are checked after snapping against evaluated, queued and in-flight designs, to a relative tolerance of
1e-9: on a continuous row without a grid the encode/legalize round trip drifts by a few ulp, and the exact-float
check the independent audit found let such repeats through (fixed in record 7.120, optimizer digest `100945fb…`).
Expected values are hypotheses,
never simulator measurements. Notes survive only with references to existing evaluations. One repair is allowed
and is charged. CLI requests use a fixed empty run directory, explicit tool restrictions and an isolated session.

Run files include:

- `effective_config.json`, manifest and status: selected method, resolved settings, phases, limits and fallback state.
- `data/llm_calls/`: calls, request/reply hashes, token/cost fields, latency, acceptance/rejection counts and status.
- `llm/calls/<call_id>/`: exact bounded prompt, normalized reply and complete call record.
- `llm/live.jsonl`: visible replies and linked outcomes; `llm/batches/` and `llm/receipts/`: recovery evidence.
- Evaluations: source, phase and nullable `llm_call_id`. Learner updates distinguish initial and online training.
- Search status: calls, cost when known, stall/round counts, steering and time spent waiting for proposals.

Older run tables load with nulls for newly added optional columns. Older policy checkpoints may be used for fine
tuning or frozen evaluation with a source-digest warning; exact resume rejects a different optimizer digest.
LLM-only saves are labelled search progress and do not appear as policy models.

## Benchmark and limits

`examples/benchmark_llm_sizing.py` runs plain SAC, matched random initialization, matched seeded initialization,
warm start, LLM only and rescue through the actual workbench scheduler. The two initialization controls are internal
benchmark arms: they never instantiate a provider or fabricate AI call rows. All matched starts collect W transitions,
perform U initial updates and then use ordinary SAC. Plain SAC's original schedule is kept and disclosed.

The driver reports every run separately, including unfinished runs, source counts, resets, duplicate rates,
initial/online updates, first feasibility, violations, elapsed/training/waiting time, calls and nullable tokens/cost.
LLM only has a different one-baseline episode policy, which is recorded explicitly. Steered or degraded starts must
not be pooled with unsteered successful starts.

The free importer uses MIT-licensed AnalogGym-Opt, pinned at
`10093e3496ef2c7d06494d91d131b0cc5de6c25b`. The checkout stays outside GATOR, and imported tasks stay in `configs/local`.
The optional `benchmark` dependencies are PyYAML and tabulate. The pinned evaluator is loaded by verified file hashes;
its destructive environment constructor is never called. Its pass rule comes from evaluator code, not YAML captions.
Native failure penalties remain identified as benchmark outputs. They are not evidence of successful measurements.

`examples/check_analoggym.py` compares independently run original testbenches with the imported backend at a strict
1e-9 relative tolerance. A failing circuit stops at its first mismatch and remains excluded. Calibration must then
use five random and three pattern-search runs of 60 evaluations for each eligible circuit. Selection requires three
amplifiers with at most one random success and demonstrated reachability. The LDO is included only after parity.
Starting values outside the published bounds or grid are reported rather than silently changed.

The user's 2026-09-30 decision sets calibration and comparison to feasibility-only, retaining the upstream pass
rule and unchanged reward. Every benchmark output remains a Probe, including inactive objective metrics.
The report includes all Probes for each run's best feasible design, descriptively. With no after-feasible objective,
all passing rewards tie at zero and the workbench retains the earliest passing design.
Bias currents are fixed at the upstream starting values in every arm, including all LLM arms. They are absent from
the mutable parameter groups and cannot be overridden by candidate assignments. The importer and comparison driver
enforce this common domain; `plan-benchmark.json` records the deviation and each circuit's fixed values.
The benchmark's native `mf` and `mult` multiplicity bindings also need numeric input columns. The workbench adds
only the count columns declared by an ngspice configuration, each with reference 1, and uses the same declaration
for validation, learner construction and archived state metadata. Explicit count bindings may tie these names to
`m`; unrelated parameter kinds remain incompatible. Default schemas and the optimizer package stay unchanged.

`examples/calibrate_analoggym.py` runs the free calibration and independently re-simulates **every** GATOR-passing
candidate in the two original upstream testbenches. Every reported metric must agree to 1e-9 relative tolerance
(no absolute tolerance floor), and verdicts must agree. Any disagreement stops all calibration workers after their
in-flight candidate checks. Verification launches are counted separately from the 60 search candidates; they never
enter the search. The earlier 205 parity designs contained no successes, so those checks alone do not validate passes.

A read-only in-memory check confirms a workbench-built `FeatureSchema` can append `current` with reference `1e-6 A`,
and PyG preserves its column and `dc` writeback name. SAC accepts it as a static device feature when the action groups
use supported kinds. Tunable-current SAC still rejects `current/A` at the hard-coded unit validation in
`models/inputs.py`; extending only the schema is insufficient for current actions. No current-support implementation or
optimizer package change was made for this follow-up.

Ten amplifiers passed all 20 parity designs; seven circuits were excluded for published starting-value/grid problems
or a timeout. All ten passed the MOS operating-point and bounded-context audit. The four methods and both controls
completed a free generic level-1 ngspice fixture with its bias current fixed, using FakeClient responses only.
This is an integration check, not an AnalogGym performance comparison. The initial current-group failures are kept.
The driver records simulator launches, retries and reached analysis commands. Counts persist in job rows before
raw-output retention; timeouts or delegated, uninstrumented commands keep totals unknown and retain observed lower
bounds. The imported best-design export writes both the main and transient decks and verifies physical parameters
by re-parsing. A representative ACBC candidate passed strict metric/verdict parity for both the instrumented backend
and exported decks; its single ngspice process performed five analyses, not five candidate evaluations.
The final scalar-output test also verifies that OP readout leaves the deck's original numeric precision unchanged.
Calibration completed 80 runs / 4,800 candidates: zero passes, so no circuit qualified for comparison and no positive-design
recheck was triggered. G9 remains unqualified for passing designs. Every best-feasible report is null; all Probes
remain available in the candidate data. Calibration, interrupted costs and exclusions are recorded in the acceptance report.

The offline Codex-schema tests intercept the actual files passed by both provider paths before any CLI launch.
Sizing schemas, with and without predicted metrics, meet the strict object rules. The unchanged Agent-tab proposal
schema has an explicit expected-failure test: every object must forbid additional properties and require all its
declared properties. To become strict it would need all root fields required; `patch` items to require `value` and
`basis`; checklist items to require `basis`; suggestions to require `url` and `quote`; encoder ideas to require
`url`; and setup to require every field. Open dictionaries (`patch.value`, setup analyses and their nested settings,
initial conditions and variables) need closed typed shapes or arrays of closed name/value records, with appropriate
nullable values for absent fields. These changes also require compatible parsing/UI handling and are **not built**.

Publications discussed in the [brief](brief-llm-sizing-for-astra.md) motivate initial learning and selective rescue;
they do not establish the best combination for these circuits or justify these default counts. Synthetic integration
tests establish scheduling behavior. No improvement in circuit performance is claimed.

## Acceptance record

The machine-readable report is
[`artifacts/local/llm-sizing/acceptance-summary.json`](../artifacts/local/llm-sizing/acceptance-summary.json).
It records all gates, full-suite/browser evidence, before/after digests and the benchmark qualification status.

**G10 failed during development:** a test's executable discovery accidentally launched one real Codex request.
The server rejected it with HTTP 400 for an invalid configuration-proposal JSON schema. No model reply was produced;
tokens and cost were not reported, so zero cost is not proven. The executable-discovery fallback was restricted to
the sizing client, and offline tests now block real Claude/Codex model executables. The
[incident record](../artifacts/local/llm-sizing/provider-launch-incident.json) is retained. No paid experiment has
been authorized; this incident must not be represented as a passing no-calls gate.

The live frontend bundle and port 8765 were not changed by this work. Feature code and imported tasks remain
uncommitted. Measured provider checks and each benchmark pilot still need the separate call and notional-cost
ceilings specified in section 8 of the brief, together with confirmation of model IDs and effort.
