"""Per-application services for path authorization, configuration and the start checklist."""
from __future__ import annotations
from pathlib import Path
from pydantic import ValidationError
from .. import bridge_connect, connection, readiness, runs, schema
from ..paths import OutputRoots, PathNotAllowed, inside, refuse_nul
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
                if not inside(resolved, self.input_roots):
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
        profile = readiness.profile_rows_check(config, runtime, report)
        return readiness.build(config.model_dump(mode='json'), task=runtime, task_blocker=(blocked or {}).get('blocker'),
                                     validation=report, connection=link, output=output, profile=profile)
