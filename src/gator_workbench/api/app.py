"""Local same-origin FastAPI backend. Compose feature routes after preloading the optimizer."""
from __future__ import annotations
from pathlib import Path
import threading
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .. import __version__, bridge_connect, connection, runs
from ..agents import ProposalStore
from ..paths import OutputRoots, repo_root
from ..preload import preload
from ..security import redact
from .context import ApiContext
from . import agent_routes, circuit_routes, run_routes, settings_routes
from .support import attachment, file_snapshot, live_answer  # compatibility exports


def create_app(*, extra_output_roots=(), extra_input_roots=(), serve_frontend=True, monitor=None,
               auto_check_on_start=True, connection_stale_seconds=120.0, connector=None) -> FastAPI:
    # Endpoints run in a thread pool and import the optimizer lazily: two first imports at once corrupt
    # torch_geometric for the life of the process. Import it here, before any thread or request exists.
    preload()
    app = FastAPI(title='GATOR workbench', version=__version__, docs_url='/api/docs', openapi_url='/api/openapi.json')
    roots = OutputRoots(extra_output_roots)
    input_roots = [repo_root().resolve()] + [Path(p).expanduser().resolve() for p in extra_input_roots]
    proposals = ProposalStore()

    def active_run(profile_id):
        for run in runs.list_runs(roots, include_mock=False)[:20]:
            status = runs.run_status(run['run_dir'])
            if status.get('worker_alive') and status.get('connection_profile_id') == profile_id:
                return status
        return None
    # After `connection_stale_seconds` a result is shown as `unknown` with its age, never as a current `ok`.
    monitor = monitor or connection.ConnectionMonitor(active_run_lookup=active_run,
                                                      stale_after_seconds=float(connection_stale_seconds))
    connector = connector or bridge_connect.BridgeConnector()
    app.state.roots, app.state.monitor, app.state.proposals, app.state.connector = roots, monitor, proposals, connector

    def auto_check():
        """Once at backend start: the CHEAP layers of the active profile (package, profile, tunnel state).
        No SKILL round trip, no Virtuoso contact, nothing started or repaired. Off the request thread."""
        try:
            active = connection.load_profiles()['active']
            if active:
                monitor.check(active, scope='cheap', trigger='auto')
        except Exception:                      # a diagnostic must never prevent the backend from starting
            pass
    if auto_check_on_start:
        app.state.auto_check_thread = threading.Thread(target=auto_check, name='gator-connection-auto-check', daemon=True)
        app.state.auto_check_thread.start()

    # ------------------------------------------------------------------ helpers
    context = ApiContext(roots, input_roots, monitor, connector, proposals)
    for routes in (settings_routes, circuit_routes, run_routes, agent_routes):
        routes.register(app, context)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(status_code=500, content=dict(detail=dict(message=redact(f'{type(exc).__name__}: {exc}', 1000))))

    dist = repo_root() / 'frontend' / 'dist'
    if serve_frontend and dist.is_dir():
        app.mount('/', StaticFiles(directory=str(dist), html=True), name='frontend')
    return app
