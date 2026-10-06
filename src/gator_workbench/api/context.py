"""Per-application services for path authorization, configuration and the start checklist."""
from __future__ import annotations
from pathlib import Path
from pydantic import ValidationError
from .. import bridge_connect, connection, readiness, runs, schema, tasks
from ..paths import OutputRoots, PathNotAllowed, refuse_nul
from ..security import redact
from .support import fail, load_runtime, validate_loaded
from dataclasses import dataclass


@dataclass
class ApiContext:
    roots: OutputRoots
    input_roots: list[Path]
    monitor: connection.ConnectionMonitor
    connector: bridge_connect.BridgeConnector

    def load_config(self, raw):
        """Authorize and load a configuration once, for validation or the start checklist."""
        config = self.parse_config(raw)
        runtime, blocked = load_runtime(config)
        return config, runtime, blocked

    def parse_config(self, raw) -> schema.WorkbenchConfig:
        try:
            config = schema.WorkbenchConfig.model_validate(raw)
        except ValidationError as exc:
            fail(422, 'The configuration does not match the schema', errors=schema.describe_errors(exc))
        self.authorize_circuit(config.circuit)
        return config

    def authorize_circuit(self, circuit):
        for name in ('netlist_path', 'parser_config_path'):
            value = getattr(circuit, name)
            if value:
                try:
                    refuse_nul(value)                # the OS refuses a NUL byte with ValueError: it was an HTTP 500
                except PathNotAllowed as exc:
                    fail(403, exc)
                resolved = Path(value).expanduser().resolve()
                if not any(resolved == r or r in resolved.parents for r in self.input_roots):
                    fail(403, f'{name} is outside the allowed input roots. Roots are added by the backend operator '
                              '(--allow-input-root), never from the browser.')

    def run_path(self, run_dir) -> Path:
        try:
            path = self.roots.resolve(run_dir)
        except PathNotAllowed as exc:
            fail(403, exc)
        if not (path / 'run_manifest.json').is_file():
            fail(404, 'Not a run directory')
        return path

    def run_readiness(self, config, runtime, blocked) -> dict:
        """The start checklist. Free: static validation, the output-root check and the monitor's CACHED connection
        status - no bridge contact, no simulator, no agent. A fresh connection test stays the user's button."""
        report = validate_loaded(config, runtime, roots=self.roots).as_dict()
        profile_id = config.run.connection_profile_id
        try:
            link = self.monitor.status(profile_id) if profile_id and runtime is not None and not runtime.mock else None
        except (KeyError, ValueError):
            link = None
        try:
            output = self.roots.check(config.output.output_root or runs.remembered_output_root(), create=False, verify_windows=False)
        except Exception:                                  # a checklist must never fail because one line cannot be filled in
            output = None
        # A real circuit profile fixes WHICH sizes may be written and their range and grid. The engine checks that only when
        # the worker starts (after the budget was authorized), so say it here: compile offline and compare with the profile.
        fixed = tasks.profile_parameter_rows(runtime)
        profile = None
        if fixed:
            matches = problem = None
            broken = any(i['level'] in ('error', 'blocker') and str(i['path']).startswith('parameters') for i in report['issues'])
            if config.parameters and not broken:
                try:
                    from analog_optimizer.envs.sizing import graph_contract
                    from ..compile import compile_task
                    matches = graph_contract(compile_task(config, runtime.base_graph).graph) == graph_contract(runtime.base_graph)
                except Exception as exc:                   # it does not compile: a start would be refused for that alone
                    problem = redact(f'{type(exc).__name__}: {exc}', 300)
            profile = dict(rows=fixed, matches=matches, error=problem)
        return readiness.build(config.model_dump(mode='json'), task=runtime, task_blocker=(blocked or {}).get('blocker'),
                                     validation=report, connection=link, output=output, profile=profile)
