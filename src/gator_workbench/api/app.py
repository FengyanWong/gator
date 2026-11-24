"""Local same-origin FastAPI backend. Compose feature routes after preloading the optimizer."""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
import threading
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders
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
READ_METHODS = ('GET', 'HEAD', 'OPTIONS')        # every other method may change something (cross_site_write, 7.484)
# The reads that change something, decided like a write (7.485): the first GET /api/local-agent starts the local Agent's
# one-time install (local_agent_routes.status -> Manager.bootstrap).
READS_THAT_CHANGE = ('/api/local-agent',)
OWN_PAGE = ('same-origin', 'none')               # Sec-Fetch-Site: the page this backend served; the user's own typing
# On every answer (NoFramingMiddleware, and the 500 of an unexpected error, which passes outside it; 7.485): no page of
# another site may show this one inside its own.
NO_FRAMING = (('X-Frame-Options', 'DENY'), ('Content-Security-Policy', "frame-ancestors 'none'"))
CROSS_SITE_REFUSAL = (
    'Refused, and nothing was changed: this request was sent by a web page that is not the page of this workbench (a '
    'page of another site, a page of another program on this machine, or a file opened in the browser). If you are '
    'working in the workbench itself, the page reaches the workbench backend through a proxy that changes its '
    'address: open the workbench at the address the backend printed when it started.')


def trusted_hosts(host=None) -> list[str]:
    """The names a request's Host header may carry. A page on a hostile domain whose name is made to resolve to 127.0.0.1
    (DNS rebinding) would reach this API with the browser's trust, but its Host header still names that domain (review of
    2026-09-29). Allowed: loopback, the test client's `testserver`, and the --host the backend is served on. Starlette
    compares an IPv6 literal with its brackets ("[::1]:8765" -> "[::1]"). A wildcard --host is reached under names this
    process cannot know (the machine's network address or name): the operator has chosen exposure, and no name is
    checked. cross_site_write() needs no names and is asked there as everywhere."""
    if host in WILDCARD_HOSTS:
        return ['*']
    # browsers send a name in lower case
    names = [*LOOPBACK_HOSTS, 'testserver'] + ([host, host.lower()] if host else [])
    return list(dict.fromkeys(f'[{name}]' if ':' in name else name for name in names))


def cross_site_write(method, fetch_site, origin, host, path='') -> bool:
    """Whether a request may change something AND was sent by a web page other than this backend's own: it is refused
    (record 7.484). The API has no login and obeys whoever reaches its port, and a page of any site the user has open
    can make the user's browser send a POST to 127.0.0.1 (cross-site request forgery). The browser keeps only the ANSWER
    from that page; a run is started by then. The rule is that of Go 1.25's http.CrossOriginProtection. It decides from
    the method and from three headers that the browser writes itself and no page can set, change or remove:
    - GET, HEAD and OPTIONS pass. (The OPTIONS with which a browser asks leave for a foreign page's PUT, PATCH, DELETE
      or JSON POST is answered 405 by the routes, which is a no.) Not so a GET or HEAD of a `path` in
      READS_THAT_CHANGE: the first GET /api/local-agent starts the local Agent's one-time install (record 7.485). Where
      the browser sends Sec-Fetch-Site, such a read passes only as 'same-origin', the page itself: 'none' marks any
      navigation the browser starts by itself, a link opened from mail or chat too, and it stays 'none' when a foreign
      site redirects that navigation here. An image's GET sends no Origin, so where the browser sends no Sec-Fetch-Site
      (plain http under a machine name, an old browser) a foreign page's <img> passes as a command line does: no header
      tells it from the page's own request there.
    - `fetch_site`, the Sec-Fetch-Site header, is the browser's own word on who asks: 'same-origin' is the page this
      backend served, 'none' the user (address bar, bookmark). Every other value is refused, 'same-site' too: that is a
      page of another port of this machine, so of another program.
    - Without it, `origin` (the Origin header) must name the address the request itself was sent to: `host`, the Host
      header. A browser leaves Sec-Fetch-Site out where the address is plain http under a machine name (a --host on the
      network), and one older than Chrome 76, Firefox 90 or Safari 16.4 does not know it; Origin they send with every
      request that is no GET or HEAD (Firefox before 70 not with a form's POST). 'null' (a sandboxed frame, a file
      opened in the browser) names no address. The two headers are compared with each other, not with a list of names,
      so the answer is right on a forwarded port (ssh -L 9000:127.0.0.1:8765) and under a wildcard --host, whose names
      this process cannot know.
    - Neither header: not a browser (curl, a script, the tests, an agent's command line), so no user's browser is
      misused, and whoever reaches the port directly is obeyed anyway.
    Sec-Fetch-Site is asked FIRST: behind the page's development proxy (vite rewrites Host to this backend, and Origin
    still names the proxy) only the browser's own word says that the page is the right one.
    Not decided here: a page whose NAME was made to resolve to this machine (DNS rebinding) is this backend's own page
    to the browser. That is trusted_hosts()'s case alone, and it is asked before this."""
    changes = method in ('GET', 'HEAD') and path.rstrip('/') in READS_THAT_CHANGE
    if method in READ_METHODS and not changes:
        return False
    if fetch_site:
        return fetch_site != 'same-origin' if changes else fetch_site not in OWN_PAGE
    if not origin:
        return False
    scheme, _, address = origin.lower().partition('://')
    return not (scheme in ('http', 'https') and bool(host) and address == host.lower())


class CrossSiteWriteMiddleware:
    """Answers a request that cross_site_write() names with 403, before a route or the request's body is read, in the
    shape of this API's other refusals ({detail: {message, code}}): the page shows the message as it is. Several Origin
    headers, which no browser sends, are joined and so name no address."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            headers = Headers(scope=scope)
            if cross_site_write(scope['method'], headers.get('sec-fetch-site'), ','.join(headers.getlist('origin')),
                                headers.get('host'), scope.get('path', '')):
                refusal = JSONResponse(status_code=403, content=dict(detail=dict(message=CROSS_SITE_REFUSAL,
                    code='cross_site_request')))
                await refusal(scope, receive, send)
                return
        await self.app(scope, receive, send)


class NoFramingMiddleware:
    """Puts NO_FRAMING on the answers (record 7.485): `X-Frame-Options: DENY` for older browsers, `frame-ancestors
    'none'` for the others. A page of another site could otherwise show this page inside its own, hidden or disguised,
    and lure the user's clicks into it; those clicks are the page's own requests, which cross_site_write() lets through.
    Nothing in the workbench frames itself: its windows are pop-ups. Added last, so it wraps the other checks and their
    refusals carry the headers too."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def framed_never(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                for name, value in NO_FRAMING:
                    headers.append(name, value)
            await send(message)
        await self.app(scope, receive, framed_never)


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
    # No documentation pages (record 7.485): FastAPI's /api/docs and /redoc load their scripts from a CDN into this
    # backend's address, where cross_site_write() trusts every script as the page's own. The schema stays.
    app = FastAPI(title='GATOR workbench', version=__version__, docs_url=None, redoc_url=None,
                  openapi_url='/api/openapi.json', lifespan=lifespan)
    # Starlette runs the middleware added last first. The Host check is added after the cross-site check: a foreign
    # Host is answered 400 as before, whatever the method, and cross_site_write() compares an Origin only with a Host
    # that was accepted. The framing headers are added last, so every answer carries them, refusals included.
    app.add_middleware(CrossSiteWriteMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts(host))
    app.add_middleware(NoFramingMiddleware)
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
        # Starlette runs this handler outside every added middleware, so NoFramingMiddleware never sees its answer.
        return JSONResponse(status_code=500, content=dict(detail=dict(message=redact(f'{type(exc).__name__}: {exc}',
            1000))), headers=dict(NO_FRAMING))

    dist = repo_root() / 'frontend' / 'dist'
    if serve_frontend and dist.is_dir():
        app.mount('/', StaticFiles(directory=str(dist), html=True), name='frontend')
    return app
