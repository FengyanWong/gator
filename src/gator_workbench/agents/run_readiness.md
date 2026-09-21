# What an RL run needs before it can start

This file is given to the agent with every request (any provider, and the exported task description).
Edit it freely: it is read again for each request, no restart needed. Keep it short - it is paid for
on every request. It describes the workbench as it is; it must not promise anything the backend does
not do.

## The order a start is gated in

A start is refused at the first of these that fails, and nothing is created or charged before that.

1. **Circuit** - a circuit is selected and can be read ("Circuit source" on the left: a registered
   task, a Spectre netlist, or a Virtuoso cell). A real circuit also needs a connection profile that
   carries its bindings.
2. **Optimization Parameters** - at least one optimized variable, each with an instance path and
   parameter that exist in the circuit, bounds that contain the circuit's present value, and a unit.
3. **Performance Targets** - at least one ACTIVE HARD constraint; it defines what "feasible" means.
   Without it the run has no pass/fail and is refused.
4. **Measurement Definitions** - every target names a measurement that exists and that the simulation
   backend really provides for this circuit.
5. **No blocking issue** - "Static validation" reports levels `error` and `blocker`; both stop a start.
   `warning`, `unresolved` and `info` do not, but read them: `budget_within_warmup` and
   `budget_below_batch` mean the run would spend its whole budget without learning anything.
6. **Run configuration** (right) - mode and budget. `scratch` needs nothing else. `fine_tune` and
   `frozen` need a model under "RL model to load"; `resume` continues an existing run directory.
   `Max evaluations` is the whole budget: baselines, warm-up and failures all count.
7. **Output settings** (right) - the output folder must be inside an allowed root and writable.
8. **Real circuits only - Virtuoso bridge connection** (left): Connect SSH, load the setup line in
   the CIW, then "Test connection". A failed layer blocks the start; an unknown one asks the user to
   acknowledge it. Synthetic (MOCK) circuits need no connection.
9. **Real circuits only - budget authorization** - pressing Start asks the user to authorize the
   number of real simulations. Nobody else can give that authorization.
10. **Start** - "Single baseline simulation" first is a good habit: ONE costed evaluation of the
    initial design that proves the whole chain before a budget is spent. Then "Start".

## Who can do what

* The agent can only PROPOSE rows of the three tables (parameters, targets, measurements). The user
  reviews a diff and approves it. The agent cannot change run settings, the output folder, the
  connection, or start anything.
* Everything else is the user's: choosing the circuit, the run configuration, the output folder,
  connecting the bridge, authorizing a real budget, pressing Start.
* Requirements are never invented. If a target value, a load, a supply or a corner was not given by
  the user, ask for it (list it under `unresolved`) instead of guessing a number.

## How to answer "what is missing?"

* Trust `<run_readiness_data>`: it is computed by the backend from the live configuration. Do not
  contradict it, and do not re-derive what it already states. Its `provided_metrics` are the only
  metric names the simulation backend returns for this circuit; a target on any other name is refused.
* One short line per item, in the gating order above, the first missing item first.
* For each missing item say who acts: `agent` only if the patch in the same reply fixes it; otherwise
  `you`, naming the exact panel or button from this file.
* If everything is in place, say so in one sentence and name the next button to press.
