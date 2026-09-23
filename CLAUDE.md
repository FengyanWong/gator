# GATOR / analog-optimizer — guidance for Claude Code

Concise project guidance. The research-side rules (milestones M1-M6, the optimizer package) live in
`.agents/skills/analog-optimizer/SKILL.md` and its `references/` (a Codex-convention skill: read it as
documentation; it is not auto-loaded by Claude Code). Decisions: `docs/decisions.md`. There is no `AGENTS.md`.

## Before changing anything

1. Read `docs/frontend_implementation_status.md` - the INDEX of the workbench's development record -
   then `docs/workbench.md` for the feature you touch and only the entries of that area in
   `docs/workbench-log/`; `git status` / `git diff`, and the relevant spec. Do not redo finished modules
   from memory. A new entry goes at the end of `docs/workbench-log/7.61-and-later.md`, plus its row in the index.
2. Preserve uncommitted user work. Never commit, push or reset without being asked. Several sessions
   share this working tree and its git index: stage explicit paths only, never `git add -A`.

## Hard rules

- **Do not add or edit files under `src/analog_optimizer/` unless the task is about the optimizer
  itself.** `training/sac.py::source_digest()` hashes every `*.py` there (even an unused import or
  whitespace counts); `SACLearner.load` and the M5/M6 audit scripts require an exact match, so any
  change invalidates existing checkpoints and audits. Workbench code belongs in `src/gator_workbench/`
  and composes the optimizer.
- **Evidence files are pinned by hash**: the M5/M6 audits re-hash `configs/*.json`, several
  `examples/*.py` and `tests/fixtures/synthetic/*.scs`, keyed by ABSOLUTE path. Do not edit, reformat
  (no `ruff --fix` over `examples/`), rename or move them; moving the repository breaks re-validation of
  the frozen M6 plan.
- **Saved models load only under the exact library versions they were saved with** (the checkpoint
  contract records torch and torch-geometric): install with `pip install -c constraints.txt ...`.
- Do not change the SAC algorithm, the reward, or the action semantics to make a feature easier.
- Mock/synthetic data is always labelled (`origin=synthetic`, `provenance=mock`) and kept under
  `<output_root>/mock/`. Never present it as a circuit result; never fall back to mock silently.
- No real Virtuoso/Spectre run, schematic write or paid agent call without explicit authorization.
  Code never starts or stops the bridge tunnel or daemon on its own: only the user's explicit
  "Connect SSH" click starts the SSH tunnel (entry 7.3). Never overwrite an original schematic.
- The workbench outputs data only: no plots, images, PDFs or analysis reports, no Python plotting
  library. One exception, a user decision (entry 7.33): the circuit graph view draws what the network
  sees, in the browser (cytoscape).
- Never log, display or send to an agent: credentials, tokens, license-server raw output, PDK models.

## Commands

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q                    # full regression (~5 min)
OMP_NUM_THREADS=1 /tmp/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist load   # the same in ~1 min
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q    # workbench only
PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve
cd frontend && npx tsc --noEmit     # ALWAYS before a build: vite does NOT type-check
cd frontend && npm run build        # Windows node via WSL interop on this machine
node frontend/scripts/<name>.mjs    # a browser check; without GATOR_WORKBENCH_URL it drives the LIVE 8765
```

`npm run build` overwrites the `dist/` the user's backend serves, so never build while another
session's edit leaves `tsc` failing, and never while a real run is being watched in the browser.
Most checks in `frontend/scripts/` default to the live backend on 8765: to point one at a scratch
backend, export `GATOR_WORKBENCH_URL` AND add it to `WSLENV` (`WSLENV=GATOR_WORKBENCH_URL` - without
that the Windows-side browser never receives it and the check silently uses 8765).

Tests must never touch real settings: `GATOR_WORKBENCH_SETTINGS_DIR` redirects
`configs/local/workbench/` (the test suite sets it; it also reaches worker/probe subprocesses).
A scratch script that prepares a run must set it too - `tests/workbench/helpers.py` does so when
imported, but a script using `gator_workbench` directly writes the user's live settings otherwise.
`/mnt/d` is a 9p mount: a `stat` right after an atomic rename can transiently fail; use
`gator_workbench.storage.atomic` for writes.
