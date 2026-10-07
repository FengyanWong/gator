# GATOR / analog-optimizer — guidance for Claude Code

Concise project guidance. The research-side rules (milestones M1-M6, the optimizer package) live in
`.agents/skills/analog-optimizer/SKILL.md` and its `references/` (a Codex-convention skill: read it as
documentation; it is not auto-loaded by Claude Code). Decisions: `docs/decisions.md` (the current state is at
its top). There is no `AGENTS.md`.

## Before changing anything

1. Read `docs/frontend_implementation_status.md`, the short INDEX of the workbench's development record. Then
   `grep -n '^##' docs/workbench.md` (its heading map) and read ONLY the section(s) of the feature you touch, with
   Read offset/limit: the whole file is ~145 kB, more than one Read returns. Then read only the log entries of that
   area (`grep -n '<feature words>' docs/workbench-log/*.md`). Also `git status` / `git diff`, and the spec of the
   area: for the workbench the untracked `gator_claude_code_fable51_frontend_data_outputs_en.md` at the repository
   root, otherwise the plan or brief of the area in `docs/`. Do not redo finished modules from memory. Where a function
   lives (button, code, route, entries, tests, checks): `docs/functionality-reference.md`; when you add, change or
   remove a function, change its row there as well. A new entry
   goes at the end of the open log file `docs/workbench-log/7.266-and-later.md`, plus its one-line row in the index;
   a new commit row goes at the end of the commit table in `docs/workbench-log/record-history.md`.
2. Preserve uncommitted user work. Never commit, push or reset without being asked. Several sessions
   share this working tree and its git index: stage explicit paths only, never `git add -A`. A bare `git commit`
   still commits everything other sessions have staged: use `git commit --only -- <paths>` or the private-index
   recipe (a temporary `GIT_INDEX_FILE`), and check `git diff --cached --stat` right before.

## Hard rules

- **Do not add or edit files under `src/analog_optimizer/` unless the task is about the optimizer
  itself.** `training/sac.py::source_digest()` hashes every `*.py` there (even an unused import or
  whitespace counts); `SACLearner.load` and the M5/M6 audit scripts require an exact match, so any
  change invalidates existing checkpoints and audits. Workbench code belongs in `src/gator_workbench/`
  and composes the optimizer.
- **Evidence files are pinned by hash**: the M5/M6 audits re-hash `configs/*.json`, several
  `examples/*.py` and `tests/fixtures/synthetic/*.scs`, keyed by ABSOLUTE path. Do not edit, reformat
  (no `ruff --fix` over `examples/`), rename or move them; moving the repository breaks re-validation of
  the frozen M6 plan. Exception, by the user's explicit choice (2026-09-30, record 7.128): the OTA7 and LDO
  example netlists and configurations (`configs/gpdk045_ota7*.json`, `configs/gpdk045_ldo*.json`,
  `examples/circuits/gpdk045_{ota7,ldo}.*`) were deleted with their tasks, so the M5/M6 audits and the frozen
  M6 plan re-validate from a checkout before that commit (git keeps the files).
- **Saved models load only under the exact library versions they were saved with** (the checkpoint
  contract records torch and torch-geometric): install with `pip install -c constraints.txt ...`.
- Do not change the SAC algorithm, the reward, or the action semantics to make a feature easier.
- Mock/synthetic data is always labelled (`origin=synthetic`, `provenance=mock`) and kept under
  `<output_root>/mock/`. Never present it as a circuit result; never fall back to mock silently.
- No real Virtuoso/Spectre run, schematic write or paid agent call without explicit authorization.
  Code never starts or stops the bridge tunnel or daemon on its own: only the user's explicit
  "Connect SSH" click starts the SSH tunnel (entry 7.3). Never overwrite an original schematic.
- The workbench outputs data only: no plots, images, PDFs or analysis reports, no Python plotting
  library. Exceptions by user decision, drawn in the browser only and never written to a run: the circuit
  graph view of what the network sees (entry 7.33, cytoscape) and the Training tab's charts of a run's
  recorded numbers (entry 7.193, uPlot).
- Never log, display or send to an agent: credentials, tokens, license-server raw output, PDK models.

## Commands

```bash
# Environment: ~/analog-optimizer-venv (home folder). /tmp is emptied at every WSL boot - on 2026-09-24 that deleted
# the previous /tmp/analog-optimizer-venv, which older docs still quote. Rebuild recipe: docs/workbench.md, "Start".
OMP_NUM_THREADS=1 ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist loadgroup   # full regression, ~1 min
~/analog-optimizer-venv/bin/python -m pytest -q                    # the same without -n: much longer
~/analog-optimizer-venv/bin/python -m pytest tests/workbench -q    # workbench only
PYTHONPATH=src ~/analog-optimizer-venv/bin/python -m gator_workbench.cli serve
cd frontend && npx tsc --noEmit     # type-check only (Windows npx through WSL interop)
cd frontend && npm run build        # = tsc --noEmit && vite build (a bare `npx vite build` does NOT type-check)
"/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/<name>.mjs)"   # a browser check (no `node` in WSL)
OMP_NUM_THREADS=1 PYTHONPATH=src ~/analog-optimizer-venv/bin/python tests/perf/learner_update_profile.py --wait-load 6   # learner step timing
```

Timing on this shared machine: follow `docs/performance-measurement.md` (quiet machine before EACH timed arm, resources
and load recorded). While another session simulates or measures, run the regression with `-n 4` and the browser checks
with `--lanes 2`, never the 12-worker suite beside a timed experiment.

The full regression takes about 1 min with `-n 12 --dist loadgroup` on a quiet machine (53 s on 2026-09-30) and
2-3 min while other sessions load it (86-196 s measured with `--dist load` on 2026-09-29), more than the Bash tool's
default 120 s timeout: run it in the background or pass a 600000 ms timeout. `--dist loadgroup` keeps each module
marked `xdist_group` on one worker, so its costly module fixture is built once: give a new module with such a fixture
that mark too, or loadgroup hands its tests out one by one.
`npm run build` stops at a type error, but it overwrites the `dist/` the user's backend serves with whatever
the working tree holds, other sessions' unfinished edits included when they type-check: look at
`git status -- frontend/src` first, and never build while a real run is being watched in the browser.
Most checks in `frontend/scripts/` default to the live backend on 8765: to point one at a scratch
backend, export `GATOR_WORKBENCH_URL` AND add it to `WSLENV` (`WSLENV=GATOR_WORKBENCH_URL` - without
that the Windows-side browser never receives it and the check silently uses 8765).

Tests must never touch real settings: `GATOR_WORKBENCH_SETTINGS_DIR` redirects
`configs/local/workbench/` (the test suite sets it; it also reaches worker/probe subprocesses).
A scratch script that prepares a run must set it too - `tests/workbench/helpers.py` does so when
imported, but a script using `gator_workbench` directly writes the user's live settings otherwise.
`/mnt/d` is a 9p mount: a `stat` right after an atomic rename can transiently fail; use
`gator_workbench.storage.atomic` for writes.
