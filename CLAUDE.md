# GATOR / analog-optimizer — guidance for Claude Code

Concise project guidance. Detailed project rules live in `.agents/skills/analog-optimizer/SKILL.md`
and its `references/` (a Codex-convention skill: read it as documentation; it is not auto-loaded by
Claude Code). Decisions: `docs/decisions.md`. There is no `AGENTS.md`.

## Before changing anything

1. Read `docs/frontend_implementation_status.md` (workbench state, blockers, next steps),
   `git status` / `git diff`, and the relevant spec. Do not redo finished modules from memory.
2. Preserve uncommitted user work. Never commit, push or reset without being asked.

## Hard rules

- **Do not add or edit files under `src/analog_optimizer/` unless the task is about the optimizer
  itself.** `training/sac.py::source_digest()` hashes every `*.py` there; `SACLearner.load` and the
  M5/M6 audit scripts require an exact match, so any change invalidates existing checkpoints and
  audits. Workbench code belongs in `src/gator_workbench/` and composes the optimizer.
- Do not change the SAC algorithm, the reward, or the action semantics to make a feature easier.
- Mock/synthetic data is always labelled (`origin=synthetic`, `provenance=mock`) and kept under
  `<output_root>/mock/`. Never present it as a circuit result; never fall back to mock silently.
- No real Virtuoso/Spectre run, schematic write or paid agent call without explicit authorization.
  Never start/stop the bridge tunnel or daemon from code. Never overwrite an original schematic.
- The workbench outputs data only: no plots, images, PDFs or analysis reports, no plotting library.
- Never log, display or send to an agent: credentials, tokens, license-server raw output, PDK models.

## Commands

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q                    # full regression
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q    # workbench only
PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve
cd frontend && npm run build        # Windows node via WSL interop on this machine
```

Tests must never touch real settings: `GATOR_WORKBENCH_SETTINGS_DIR` redirects
`configs/local/workbench/` (the test suite sets it; it also reaches worker/probe subprocesses).
`/mnt/d` is a 9p mount: a `stat` right after an atomic rename can transiently fail; use
`gator_workbench.storage.atomic` for writes.
