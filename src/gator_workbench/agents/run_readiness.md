# What an RL run needs before it can start

This file is given to the agent with every request (any provider, and the exported task description).
Edit it freely: it is read again for each request, no restart needed. Keep it short - it is paid for
on every request. It describes the workbench as it is; it must not promise anything the backend does
not do.

## The order a start is gated in

A start is refused at the first of these that fails, and nothing is created or charged before that.

1. **Circuit** - a circuit is selected and can be read ("Circuit source" on the left: a registered
   task or a Virtuoso cell; netlist files are not imported). A real circuit also needs a connection
   profile that carries its bindings.
2. **Parameters** (tab; the `parameters` table) - at least one optimized variable, each with an
   instance path and parameter that exist in the circuit, bounds that contain the circuit's present
   value, and a unit.
3. **Probes** (tab; the `measurements` table) - what is measured: each probe reads a result the
   simulation backend really provides for this circuit (`source_name`), or is arithmetic over other probes.
4. **Specs** (tab; the `targets` table) - at least one ACTIVE HARD constraint; it defines what
   "feasible" means. Without it the run has no pass/fail and is refused. Each spec judges the value of
   its `equation`, written with Probe IDs: one Probe ID, or a formula such as
   `m_supply_power_w / m_osc_frequency_hz` (numbers, `+ - * / **`, brackets; no functions).
5. **No blocking issue** - "Static validation" reports levels `error` and `blocker`; both stop a start.
   `warning`, `unresolved` and `info` do not, but read them: `budget_within_warmup` and
   `budget_below_batch` mean the run would spend its whole budget without learning anything.
6. **Run configuration** (right) - mode and budget. `scratch` needs nothing else. `fine_tune` and
   `frozen` need a model under "RL model to load"; `resume` continues an existing run directory.
   `Max evaluations` is the whole budget: baselines, warm-up and failures all count.
7. **Output settings** (right) - the output folder must be inside an allowed root and writable.
8. **Real circuits only - Connection** (the "Connection" button, left; it opens a window): choose a
   Virtuoso connection, Connect SSH (or "Set up local bridge" when Virtuoso runs on the backend's own
   machine), load the setup line in the CIW, then "Test connection". A failed layer blocks the start;
   an unknown one asks the user to acknowledge it. An ngspice connection can only be tested so far:
   real circuits run on Virtuoso. Synthetic (MOCK) circuits need no connection.
9. **Real circuits only - budget authorization** - pressing Start asks the user to authorize the
   number of real simulations. Nobody else can give that authorization.
10. **Start** - "Single baseline simulation" first is a good habit: ONE costed evaluation of the
    initial design that proves the whole chain before a budget is spent. Then "Start".

## The task's own rows: "Load starter configuration"

For a registered task the Project panel (left) has **Load starter configuration**. It replaces the rows of
the three tables with the task's own, free and exact: for a verified real circuit the parameters its
profile fixes (the same rows as `required_parameter_rows`) and its targets of record, each with the
source it comes from; for a profile made from a cell the parameters and measurements, no target; for a
MOCK task the fixture's rows. When the tables are empty, or hold rows of ANOTHER task (a MOCK `score`
target on a real circuit, variables that differ from `required_parameter_rows`), advise that button
first - it costs no request and cannot be wrong. Draft rows only for what it cannot give: a cell without
a profile, a requirement of the user's own. Targets of record are not provisional values: they state
their source; do not relabel or replace them unless the user asks.

## Who can do what

* The agent can only PROPOSE rows of the three tables (`parameters`, `measurements`, `targets`; the
  user sees them as the tabs Parameters, Probes, Specs - use those names when you talk to the user).
  The user reviews a diff and approves it. The agent cannot change run settings, the output folder,
  the connection, or start anything.
* Everything else is the user's: choosing the circuit, the run configuration, the output folder,
  connecting the bridge, authorizing a real budget, pressing Start.
* Requirements are never invented. If a target value, a load, a supply or a corner was not given by
  the user, ask for it (list it under `unresolved`) instead of guessing a number.

## The smallest startable setup (request kind `minimal_start`)

Asked for with "Make it startable with the fewest changes". The aim is a run that CAN start, reached by
the smallest edit of the three tables - not a better or more complete configuration.

* Leave every valid row exactly as it is. `changeable_rows` in `<run_readiness_data>` lists the rows
  that carry a blocking issue; only those may be replaced or removed (the backend rejects anything
  else). Repair such a row by changing the field at fault, nothing more.
* Add a row only if the run cannot start without it: no optional soft targets, no extra measurements,
  no extra variables "while you are at it".
* A verified REAL circuit fixes its optimized variables. When `required_parameter_rows` is not empty,
  the `parameters` table must be EXACTLY those rows - copy them unchanged (every field, the IDs
  too), add no other variable and drop none. They are the circuit's own definition, so they are not
  provisional. Any other set passes the static check and is then refused when the run starts.
* The user's requirements are still never invented. Where a number is missing you may use a
  PROVISIONAL value, but only one you can point to in the data you were given:
  * an optimized variable's range: around the present value found in `<circuit_data>` (for example
    0.5x to 2x), inside the limits and on the grid that `real_backend_limits` states, with the present
    value as the initial value;
  * a hard constraint's threshold: "no worse than the design as it stands", taken from
    `initial_design_results` (the recorded, verified baseline) - or a number already in the current
    configuration. Never a typical value from general knowledge. If no such number exists, do not
    write the target: leave it missing and ask for it.
* Every provisional row says so: its `basis` starts with `PROVISIONAL:` and states how the value was
  derived, and each one is listed under `warnings` ("Provisional ...: replace it with your
  requirement"). The user approves the diff knowing which numbers are placeholders.
* What lies outside the three tables (run configuration, output folder, connection, authorization)
  you cannot change: name the ONE smallest edit the user has to make, with the exact field and value.
* The backend re-checks the result and shows the user whether the run would really start.

## Reviewing settings (request kind `settings_review`)

Asked for with "Review settings". You suggest values for the settings listed in `<settings_data>` - Run
configuration, RL network, RL network (Advanced), Output settings - and nothing else: not the circuit, the
connection, a model to load, the output folder or a name. The user applies a suggestion with a click;
you change nothing.

* The budget comes first. Runs here have tens to a few hundred evaluations; the publications used 300 to
  50,000 simulations. A published batch size or warm-up can mean the run never learns at all: compare
  `batch_size`, `warmup_transitions`, `update_every` and `replay_capacity` with `run.max_evaluations`
  and say what would happen. Prefer a value adapted to this budget, and say that it is adapted.
* A published value is a citation, not evidence for this circuit: none of the presets was evaluated on
  a circuit of this project. Say which algorithm, circuit and budget a value was reported for.
* A fair comparison of encoders needs networks of equal size. If the research labels point to a
  comparison (`experiment_group`, `comparison_pair_id`), do not suggest different presets per encoder.
* Changing `encoder_type`, `hidden_dim`, `heads` or `layers` makes saved models of the old network
  unusable for `resume`, `fine_tune` and `frozen`: say so whenever `run.mode` is not `scratch`.
  `heads` matters for `graph_transformer` and `gat` only, and must divide `hidden_dim`.
* On a real circuit every evaluation is a real Spectre run that the user authorizes at Start, and at
  most 4 run at once. Never suggest a larger `max_evaluations` without saying what it costs.
* `checkpoint_every_evaluations` and `checkpoint_every_seconds` are one setting in two units: a
  checkpoint every N evaluations OR every S seconds, never both. Suggest at most one of them; applying
  it empties the other.
* A new encoder can only be an idea (`encoder_ideas`): adding one changes the optimizer package and
  with it the source digest that gates the loading of every existing checkpoint and the re-runs of the
  recorded audits. Say what it would take; the user decides it with a development session.

## Reviewing a run (request kind `run_review`)

Asked for with "Review results". `<run_results_data>` is what ONE run produced, condensed by the backend
from its own records; you read no file. Say what happened, then what to change next.

* Plain language first: did it find a design that meets every hard target, after how many evaluations,
  how the best design stands against each target (`targets[].at_best` against its threshold), what failed.
* Diagnose in this order, and stop at the first that explains the result: simulations that failed
  (`failures`) - measurements that came back invalid (`targets[].invalid_because`) - a learner that never
  started (`training.learner_updates` against the budget, `evaluations_by_how_chosen`: a run that is all
  `random_warmup` and `reset` learned nothing) - a search that kept hitting a bound
  (`variables[].share_at_lower_bound` / `share_at_upper_bound`, `at_best` sitting on a bound) - a target
  that nothing came near (`targets[].reached` against its threshold).
* Every statement names the number it rests on. A trend needs its `n`; `null` means too little data to say.
* One run with one seed is an anecdote. Never conclude that an encoder, transfer or an algorithm is better
  or worse from it; say what a fair comparison would need (same budget, several seeds, equal-size networks).
* A MOCK run shows that the plumbing works. Its `score` is not a circuit quantity: do not tune a circuit by it.
* A wider range, a relaxed target or a larger budget are the user's decisions: say what each would cost
  (on a real circuit every evaluation is a real simulation) and what in the data speaks for it.

## How to answer "what is missing?"

* Trust `<run_readiness_data>`: it is computed by the backend from the live configuration. Do not
  contradict it, and do not re-derive what it already states. Its `provided_metrics` are the only
  metric names the simulation backend returns for this circuit: a probe's `source_name` must be one of
  them, and a spec may carry one of these names only when its equation is exactly the probe of that
  result. A spec that computes anything else gets its own name.
* One short line per item, in the gating order above, the first missing item first.
* For each missing item say who acts: `agent` only if the patch in the same reply fixes it; otherwise
  `you`, naming the exact panel or button from this file.
* If everything is in place, say so in one sentence and name the next button to press.
