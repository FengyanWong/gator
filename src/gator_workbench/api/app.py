"""Local same-origin FastAPI backend. Compose feature routes after preloading the optimizer."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
import threading
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .. import __version__, bridge_connect, connection, consistency, launch_requests, runs
from ..names import LOOPBACK_HOSTS
from ..paths import OutputRoots, bridge_session_lock, repo_root
from ..preload import preload
from ..security import redact
from .context import ApiContext
from . import agent_routes, circuit_routes, run_routes, settings_routes, task_folder_routes, local_agent_routes
from .support import attachment, file_snapshot  # compatibility exports

WILDCARD_HOSTS = ('0.0.0.0', '::', '')
ACTIVE_RUN_REUSE_SECONDS = 3.0                   # how long one look for a run that works on a connection serves (7.279)


def trusted_hosts(host=None) -> list[str]:
    """The names a request's Host header may carry. A page on a hostile domain whose name is made to resolve to 127.0.0.1
    (DNS rebinding) would reach this API with the browser's trust, but its Host header still names that domain (review of
    2026-09-29). Allowed: loopback, the test client's `testserver`, and the --host the backend is served on. Starlette
    compares an IPv6 literal with its brackets ("[::1]:8765" -> "[::1]"). A wildcard --host is reached under names this
    process cannot know (the machine's network address or name): the operator has chosen exposure, and nothing is checked."""
    if host in WILDCARD_HOSTS:
        return ['*']
    # browsers send a name in lower case
    names = [*LOOPBACK_HOSTS, 'testserver'] + ([host, host.lower()] if host else [])
    return list(dict.fromkeys(f'[{name}]' if ':' in name else name for name in names))


def session_idle(profile_id) -> bool:
    """Whether it is certain that nothing works in the Virtuoso session that connection `profile_id` reaches: no
    process holds that session's lock, which every real run, corner check and task save holds for as long as it works
    there (records 7.167, 7.311). One look at /proc/locks: the lock is not taken, and no run folder is read. False
    whenever that cannot be said - a name that is not set up, a connection that is no Virtuoso connection with a bridge
    settings file (an ngspice run takes no such lock), a machine without /proc/locks - and the caller looks at the runs
    themselves."""
    try:
        settings = connection.load_profiles()['profiles'].get(profile_id)
        if (not isinstance(settings, dict) or connection.entry_kind(settings) not in connection.SESSION_KINDS
                or not settings.get('env_file')):
            return False
        return consistency.lock_pids(bridge_session_lock(settings['env_file'], settings.get('profile'))) == []
    except Exception:                          # a shortcut must never fail the check it shortens
        return False


def create_app(*, extra_output_roots=(), extra_input_roots=(), serve_frontend=True, monitor=None,
               auto_check_on_start=True, connection_stale_seconds=120.0, connector=None, host=None) -> FastAPI:
    # Endpoints run in a thread pool and import the optimizer lazily: two first imports at once corrupt
    # torch_geometric for the life of the process. Import it here, before any thread or request exists.
    """Compose the local API, connection services and optional frontend after preloading the optimizer."""
    preload()
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if service := getattr(app.state, 'local_agent', None):
                service.close()
    app = FastAPI(title='GATOR workbench', version=__version__, docs_url='/api/docs', openapi_url='/api/openapi.json',
                  lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts(host))
    roots = OutputRoots(extra_output_roots)
    input_roots = [repo_root().resolve()] + [Path(p).expanduser().resolve() for p in extra_input_roots]

    # The connection gate asks this at every check, and Save task checks about ten times in a row. One look serves for
    # ACTIVE_RUN_REUSE_SECONDS (record 7.279): the look - the run list and up to 20 status files on the D: drive - took
    # 1-2.4 s, so its answer was about that old when it came anyway.
    # The lock of the connection's Virtuoso session is asked first (record 7.478): while nothing holds it, no run works
    # on the connection, and that is the answer at once. The look had grown with the run list - 826 runs: 5-10 s, and
    # 12-26 s after a start of the backend - and every connection test, check and gate began with it, where the test
    # itself takes 0.7 s. The runs are looked at only while the lock is held, or where there is no such lock to ask.
    looked: dict = {}

    def active_run(profile_id):
        if session_idle(profile_id):
            looked.pop(profile_id, None)                 # whatever an earlier look found there has ended
            return None
        seen = looked.get(profile_id)
        if seen is not None and time.monotonic() - seen[0] < ACTIVE_RUN_REUSE_SECONDS:
            return seen[1]
        found = None
        for run in runs.list_runs(roots, include_mock=False)[:20]:
            status = runs.run_status(run['run_dir'])
            if status.get('worker_alive') and status.get('connection_profile_id') == profile_id:
                found = status
                break
        looked[profile_id] = (time.monotonic(), found)
        return found
    # After `connection_stale_seconds` a result is shown as `unknown` with its age, never as a current `ok`.
    monitor = monitor or connection.ConnectionMonitor(active_run_lookup=active_run,
                                                      stale_after_seconds=float(connection_stale_seconds))
    connector = connector or bridge_connect.BridgeConnector()
    app.state.roots, app.state.monitor, app.state.connector = roots, monitor, connector

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
        app.state.auto_check_thread = threading.Thread(target=auto_check, name='gator-connection-auto-check',
            daemon=True)
        app.state.auto_check_thread.start()

    # ------------------------------------------------------------------ helpers
    context = ApiContext(roots, input_roots, monitor, connector)
    for routes in (settings_routes, circuit_routes, run_routes, agent_routes, task_folder_routes, local_agent_routes):
        routes.register(app, context)
    # Once at backend start (record 7.271 addendum): a launch request left on its way by the previous backend is let go
    # of, unless it is a launching one whose worker is there. Must never prevent the backend from starting.
    try:
        app.state.launch_requests_reconciled = launch_requests.reconcile(run_routes.worker_started)
    except Exception:
        app.state.launch_requests_reconciled = None

    # Return a bounded, redacted error response for uncaught request failures.
    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(status_code=500, content=dict(detail=dict(message=redact(f'{type(exc).__name__}: {exc}',
            1000))))

    dist = repo_root() / 'frontend' / 'dist'
    if serve_frontend and dist.is_dir():
        app.mount('/', StaticFiles(directory=str(dist), html=True), name='frontend')
    return app
