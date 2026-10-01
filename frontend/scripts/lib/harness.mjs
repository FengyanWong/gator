// Shared harness of the workbench browser checks (frontend/scripts/*_check.mjs; there is no frontend test runner in this
// project). A throwaway headless Edge is driven over the Chrome DevTools protocol from WINDOWS node (>= 22: built-in fetch
// and WebSocket; node built-ins only, nothing to install). Run a check from WSL with BOTH variables, or Windows node never
// sees the URL and the check drives the user's live page:
//   WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:<port>/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/<name>_check.mjs)" [screenshot-dir]
//
// What a check takes from here:
//   workbenchUrl({ writes })      the page it drives; printed as the first line. A check that can WRITE through the real API
//                                 refuses the user's live backend: no GATOR_WORKBENCH_URL, port 8765, or a URL whose backend
//                                 keeps its settings in this repository's configs/local/workbench (a preview proxying to the
//                                 live backend; 8765 itself is never asked). A hermetic check (every writing request
//                                 refused) may run on 8765.
//   launchEdge(tag)               Edge on a debugging port of its own (--remote-debugging-port=0, the port read back from
//                                 <profile>/DevToolsActivePort: no two checks ever share a port); no extensions, no sync
//   browser.open()                the about:blank tab Edge started with, as a DevTools session: send / evaluate / until /
//                                 on / consoleErrors (a closing session rejects what is still waiting)
//   browser.window(title) + browser.attach(target)   a pop-up found by its title, with a session of its own
//   page.intercept / hold / nextPaused / fulfil / fulfilText / pass / refuse / readOrRefuse   Fetch interception: canned
//                                 JSON, reads pass, every other writing request refused with 418 (`others: 'read'` makes
//                                 a check that answers only some routes hermetic)
//   page.seed / trackSaves / saved / stored     the page's configuration in localStorage and its 800 ms save timer
//   page.shot(file, element | clip)             a PNG of one element (or of the page), brought to the front first
//   keepAgentSettings(url)        the agent settings before a check changes them, and restore() for `finally`
//   check / fail / finish, outDir PASS / FAIL lines, the summary, exit code 1 on any failure; the screenshot folder
//   runChecks(browser, body)      a check's body, then its end: an exception is counted (fail), Edge closed, finish()
//   reportRefused(refused, never) the INFO line of the writing requests refused, and the check that none is a NEVER_* one
//   answerDialogs / starterConfig the page's confirm dialogs answered as planned; the MOCK task as "Load task" merges it
//   browser.close()               Edge ends, and every temporary folder of the check is removed (also after a failure, and
//                                 by the watchdog when a check hangs: GATOR_CHECK_LIMIT_S, default 600 s)
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

export const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
export const LIVE_PORT = '8765';                                  // the user's own backend
export const CONFIG_KEY = 'gator-workbench-config-v1';            // the page's saved configuration (store.ts)
// A page that opens on the tests' MOCK stand-in, as a fresh page did until the MOCK task was deleted from the workbench
// (2026-09-30, record 7.128: a fresh page has no task now). The check's backend must register the stand-in (run_checks.sh).
export const MOCK_PAGE_CONFIG = {
  schema_version: 'gator-workbench-config-v1', project: { name: 'gator-project', task_name: 'task', notes: '' },
  circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' },
  parameters: [], targets: [], measurements: [],
  run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, reward: { violation_shape: 'compressed', worst_spec_share: 0.5 } },
  output: { experiment_name: 'experiment' }, research: {},
};
export const RUN_KEY = 'gator-workbench-current-run-v1';          // the run this browser remembers
export const NO_WRITES = 'FIXTURE: this check lets no writing request through';
/** The page tests the connection in use ONCE when it opens (status record 7.80, user request 2026-09-24): a hermetic check
 *  answers that one POST /api/connection/check here, as "not tested" - nothing is probed, and it is not a request the page
 *  made beyond what the user asked for, so it is not counted among the refused ones. */
export const PAGE_OPEN_TEST = profile_id => ({ profile_id, scope: 'interactive', trigger: 'user', checked_utc: null, age_seconds: null, stale: true,
  overall: 'unknown', run_active: false, layers: [], ciw: null,
  summary: { level: 'unknown', headline: 'FIXTURE: the test of the connection when the page opened was answered by this check; nothing was probed.', broken_layer: null, next_step: null } });
/** A fresh passing validation reply; each scenario can override its facts without sharing mutable state. */
export const validConfiguration = (overrides = {}) => ({ blocks_run: false, counts: {}, facts: { circuit_checked: false },
  issues: [], config_hash: 'fixture', task_definition_hash: 'fixture', circuit_blocker: null, mock: null, ...overrides });
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const text = value => JSON.stringify(value);                      // a JS literal for code sent into the page

// ---- PASS / FAIL -------------------------------------------------------------------------------------------------------
let passed = 0, failed = 0, stopped = 0;
export function check(name, ok, info = '') {
  if (ok) passed++; else failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? '  -> ' + info : ''}`);
}
/** The check itself stopped (an exception): counted as a failure. */
export function fail(error) { stopped++; console.log('ERROR ' + (error?.stack ?? error)); }
export const failures = () => failed + stopped;
/** The summary line and the exit code: 0 only when every check passed and nothing stopped the script. */
export function finish() {
  console.log(failed ? `${failed} of ${passed + failed} check(s) FAILED` : stopped ? `the check stopped early (${passed} check(s) passed before)` : `all ${passed} checks passed`);
  process.exit(failures() ? 1 : 0);
}
/** A check's body, then the end every check has: an exception stops it (counted by `fail`), Edge is closed whatever
 *  happened, and `finish` prints the summary and sets the exit code. */
export async function runChecks(browser, body) {
  try {
    await body();
  } catch (error) {
    fail(error);
  } finally {
    await browser.close();
  }
  finish();
}
/** The writing requests the page sent on its own (the check refused them all) as an INFO line; with `never` =
 *  [check name, pattern], the check that none of them is a request the page may never send by itself. */
export function reportRefused(refused, never = null) {
  console.log(`INFO  writing requests the page sent on its own, all refused here: ${refused.length ? [...new Set(refused)].join(', ') : 'none'}`);
  if (never) check(never[0], !refused.some(r => never[1].test(r)), refused.join(', '));
}
export const NEVER_ASKED = ['the page asked to start, continue, command, connect or call an agent on its own: never',
  /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/)/];
export const NEVER_ASKED_OR_SAVED = ['the page asked to start, continue, command, connect, save settings or call an agent on its own: never',
  /\/api\/(runs\/(start|continue|command)|connection\/(check|connect|profile)|agent\/|circuit\/modify|virtuoso\/|network-settings)/];
/** The page's confirm/alert dialogs on `session` answered from `answers` in order (true = OK; none left = Cancel), each
 *  recorded in `dialogs` with whether this check planned it. */
export function answerDialogs(session, answers, dialogs) {
  return session.on('Page.javascriptDialogOpening', p => {
    const accept = answers.length ? answers.shift() : null;
    dialogs.push({ message: p.message, planned: accept !== null });
    return session.send('Page.handleJavaScriptDialog', { accept: !!accept });
  });
}
/** The MOCK task's starter configuration, as "Load task" merges it (the page needs `output` and `research`). */
export const starterConfig = async base => ({ ...(await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', base))).json()),
  output: { experiment_name: 'fixture' }, research: {} });

// ---- the URL, and the guard for checks that write -----------------------------------------------------------------------
const liveHow = 'Start a scratch backend with its own settings folder, e.g.\n'
  + '  GATOR_WORKBENCH_SETTINGS_DIR=<empty dir> PYTHONPATH=src ~/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8768\n'
  + 'and run the check with BOTH variables (WSLENV carries the URL into the Windows process):\n'
  + '  WSLENV=GATOR_WORKBENCH_URL GATOR_WORKBENCH_URL=http://127.0.0.1:8768/ "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/<check>.mjs)"';
/** The settings the live backend keeps in this repository: paths.local_settings_dir() without GATOR_WORKBENCH_SETTINGS_DIR. */
const LIVE_SETTINGS = new URL('../../../configs/local/workbench/settings.json', import.meta.url);
const sorted = value => JSON.stringify(value, (_, v) => v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : 1))) : v);
/** Whether the backend behind `base` keeps its settings in the live folder of this repository: it answers /api/meta with
 *  exactly the settings stored there. That is the live backend itself behind a proxy (a vite preview forwards /api to
 *  8765 unless its config says otherwise), or a second server started without its own GATOR_WORKBENCH_SETTINGS_DIR. The
 *  live backend is never asked: its settings file is read from disk. 'unknown' when the backend cannot be read (a port
 *  that has just started listening can take a few seconds to reach a Windows process: it is asked for ~10 s). */
async function usesLiveSettings(base) {
  let live;
  try { live = JSON.parse(readFileSync(LIVE_SETTINGS, 'utf8')); } catch { return false; }     // no live settings in this checkout
  if (!live || typeof live !== 'object' || !Object.keys(live).length) return false;
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      const meta = await (await fetch(new URL('api/meta', base), { signal: AbortSignal.timeout(5000) })).json();
      return sorted(meta.remembered ?? null) === sorted(live);
    } catch { await sleep(500); }
  }
  return 'unknown';
}
/** The workbench page a check drives: GATOR_WORKBENCH_URL, else the user's live backend on 8765 - which only a hermetic
 *  check may use. `writes`: the check can write through the real API (saves settings, starts runs, lets requests of the
 *  page through); it then refuses the live backend, also behind a proxy. The URL is printed as the first line. */
export async function workbenchUrl({ writes = false } = {}) {
  const given = process.env.GATOR_WORKBENCH_URL;
  const url = new URL(given || `http://127.0.0.1:${LIVE_PORT}/`).href;
  if (writes) {
    const refuse = why => { console.log(`ERROR this check writes through the workbench API, so it does not run against your live backend: ${why}\n${liveHow}`); process.exit(2); };
    if (!given) refuse('GATOR_WORKBENCH_URL is not set (from WSL it also needs WSLENV=GATOR_WORKBENCH_URL).');
    if (new URL(url).port === LIVE_PORT) refuse(`${url} is port ${LIVE_PORT}.`);
    const live = await usesLiveSettings(url);
    if (live === 'unknown') refuse(`${url}api/meta could not be read, so it cannot be told apart from the live backend. Start the scratch backend first.`);
    if (live) refuse(`${url} reaches a backend that keeps its settings in this repository's configs/local/workbench - the live settings `
      + `(a preview that proxies /api to the live backend, or a server started without GATOR_WORKBENCH_SETTINGS_DIR).`);
  }
  console.log(`URL   ${url}  (${writes ? 'this check writes through its API: a scratch backend' : 'hermetic: writing requests are refused, safe on a live backend'})`);
  return url;
}
/** The screenshot folder: the first command-line argument that is not a --flag, else the OS temp folder. */
export function outDir(args = process.argv.slice(2)) {
  const dir = args.find(a => !a.startsWith('--')) ?? tmpdir();
  mkdirSync(dir, { recursive: true });
  return dir;
}

// ---- agent settings a check changes (on a scratch backend) ---------------------------------------------------------------
const AGENT_KEYS = ['provider', 'model', 'effort', 'timeout_seconds', 'permission_mode', 'allowed_tools', 'max_turns', 'stream'];
/** The agent settings as the backend has them now, or null when they cannot be read (then change nothing). `restore()`
 *  puts exactly these back - call it in `finally` - and checks that provider, model and effort are as they were. */
export async function keepAgentSettings(base) {
  const url = new URL('api/agent/settings', base);
  const read = async () => (await fetch(url)).json();
  let original = null;
  for (let attempt = 0; attempt < 6 && !original; attempt++) { original = await read().catch(() => null); if (!original) await sleep(500); }
  if (!original) return null;
  return {
    original,
    async restore() {
      const body = Object.fromEntries(AGENT_KEYS.map(k => [k, original[k]]));
      const ok = await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.ok, () => false);
      const now = ok ? await read().catch(() => null) : null;
      check('agent settings are back as they were', !!now && ['provider', 'model', 'effort'].every(k => now[k] === original[k]), now ? `${now.provider} / ${now.model} / ${now.effort}` : 'restore failed');
    },
  };
}

// ---- what a hermetic check lets through --------------------------------------------------------------------------------
/** POST requests that only read or compute on the backend (nothing is written, started, probed or asked of an agent). */
const READ_POSTS = new Set(['/api/config/validate', '/api/config/diff', '/api/agent/readiness', '/api/runs/model', '/api/runs/model/structure', '/api/runs/model/graph-view']);
const bodyOf = request => { try { return JSON.parse(request.postData ?? '{}') ?? {}; } catch { return {}; } };
export function readOnly(request) {
  if (request.method === 'GET') return true;
  if (request.method !== 'POST') return false;
  const pathname = new URL(request.url).pathname, body = bodyOf(request);
  if (READ_POSTS.has(pathname)) return true;
  if (pathname === '/api/output/check') return !body.create;                        // looks at the output folder; create: true writes a probe
  if (pathname === '/api/circuit/load') return body.circuit?.source === 'registered_task';   // local files; a Virtuoso source may reach the bridge
  return false;
}
const glob = pattern => new RegExp('^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');

// ---- one DevTools session (a page, or a pop-up window) -----------------------------------------------------------------
async function connect(target, { errors = [], prefix = '', consoleApi = true } = {}) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = () => reject(new Error(`no DevTools session for ${target.url}`)); });
  let nextId = 0, closed = false;
  const pending = new Map(), listeners = new Map();
  const cdpError = message => Object.assign(new Error(message), { cdp: true });
  const run = (fn, params) => {                                   // an event handler: a failure of the page going away is expected
    Promise.resolve().then(() => fn(params)).catch(e => { if (!e?.cdp) console.log(`NOTE  an event handler failed: ${e?.stack ?? e}`); });
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id) {
      const p = pending.get(m.id); pending.delete(m.id);
      if (p) m.error ? p.reject(cdpError(`${p.method}: ${text(m.error)}`)) : p.resolve(m.result);
    } else for (const fn of listeners.get(m.method) ?? []) run(fn, m.params);
  };
  // A click that closes its own window may never be acknowledged: a closing session rejects what is still waiting.
  ws.onclose = () => { closed = true; for (const p of pending.values()) p.reject(cdpError('the DevTools session closed (its window went away)')); pending.clear(); };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    if (closed) return reject(cdpError(`${method}: the DevTools session is closed`));
    const id = ++nextId; pending.set(id, { resolve, reject, method }); ws.send(JSON.stringify({ id, method, params }));
  });
  const session = {
    target, send, errors, consoleErrors: errors, paused: [], refused: [],
    close: () => ws.close(),
    get closed() { return closed; },
    /** Calls `fn(params)` for every event `method`; a failure inside is reported as a NOTE (a CDP error is not: the page went away). */
    on(method, fn) { listeners.set(method, [...(listeners.get(method) ?? []), fn]); return session; },
    /** The value of a JS expression in the page (promises awaited). `userGesture`: a click that may open a window or download. */
    async evaluate(expression, userGesture = false) {
      const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
      return r.result.value;
    },
    /** Update a React-controlled field through its native setter, including fields in a pop-up's realm. */
    setValue(expression, value, { event = 'change', focus = false, userGesture = false } = {}) {
      return session.evaluate(`(() => { const el = ${expression}; if (!el) return false;
        if (${focus}) el.focus();
        Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set.call(el, ${text(value)});
        el.dispatchEvent(new el.ownerDocument.defaultView.Event(${text(event)}, { bubbles: true }));
        return el.value; })()`, userGesture);
    },
    /** True as soon as `expression` is truthy, false after `tries` looks `every` ms apart. */
    async until(expression, tries = 80, every = 100) {
      for (let i = 0; i < tries; i++) { if (await session.evaluate(expression)) return true; await sleep(every); }
      return false;
    },
    viewport: (width, height) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }),

    // ---- Fetch interception (one per session: a second Fetch.enable replaces the first) ----------------------------------
    /** Pauses the requests matching `patterns` (CDP url patterns, * and ?) and hands each to `answer(params)`. With
     *  `others: 'read'` EVERY /api request pauses: the matching ones go to `answer`, the rest pass when they only read
     *  (readOnly) and are refused with 418 otherwise, listed in `session.refused`: the check is hermetic. */
    async intercept(patterns, answer, { others = null, connection = null } = {}) {
      const mine = patterns.map(p => glob(typeof p === 'string' ? p : p.urlPattern));
      session.on('Fetch.requestPaused', params => {
        // Tests of Virtuoso controls need a selected profile even on a scratch backend with empty settings.
        const name = new URL(params.request.url).pathname;
        if (connection && name === '/api/connection/profiles') return session.fulfil(params.requestId, 200, { active: connection,
          profiles: [{ profile_id: connection, family: 'virtuoso', kind: 'virtuoso_ssh', kind_label: 'FIXTURE Virtuoso' }] });
        if (connection && ['/api/connection/check', '/api/connection/status'].includes(name))
          return session.fulfil(params.requestId, 200, PAGE_OPEN_TEST(connection));
        return !others || mine.some(re => re.test(params.request.url)) ? answer(params)
          : session.readOrRefuse(params, session.refused, { reads: true });
      });
      const list = others ? ['*/api/*'] : [...patterns, ...(connection ? ['*/api/connection/*'] : [])];
      await send('Fetch.enable', { patterns: list.map(p => typeof p === 'string' ? { urlPattern: p, requestStage: 'Request' } : p) });
    },
    /** Pauses the matching requests and keeps them in `session.paused` until the check answers them (nextPaused, fulfil);
     *  `first(params)` may answer one at once (it then returns true). Options as for intercept. */
    hold(patterns, first = null, options = {}) {
      return session.intercept(patterns, params => {
        if (first?.(params)) return;
        const { requestId, request } = params;
        session.paused.push({ requestId, url: request.url, method: request.method, headers: request.headers, postData: request.postData });
      }, options);
    },
    /** The oldest held request whose URL ends with `suffix` (taken out of `paused`); throws after `ms`. */
    async nextPaused(suffix, ms = 5000) {
      for (let waited = 0; waited < ms; waited += 50) {
        const i = session.paused.findIndex(p => p.url.endsWith(suffix));
        if (i >= 0) return session.paused.splice(i, 1)[0];
        await sleep(50);
      }
      throw new Error(`no intercepted request for ${suffix}`);
    },
    fulfil: (requestId, status, obj) => session.fulfilText(requestId, status, 'application/json', JSON.stringify(obj)),
    fulfilText: (requestId, status, contentType, body) => send('Fetch.fulfillRequest', { requestId, responseCode: status,
      responseHeaders: [{ name: 'Content-Type', value: contentType }], body: Buffer.from(body).toString('base64') }),
    pass: requestId => send('Fetch.continueRequest', { requestId }),
    refuse: (requestId, message = NO_WRITES) => session.fulfil(requestId, 418, { detail: { message } }),
    /** The last word of a hermetic answer: a GET passes (with `reads`: any read-only request), anything else is refused
     *  with 418 and recorded in `refused` as "METHOD /path" - except the page's one test of the connection when it opens,
     *  answered as PAGE_OPEN_TEST (a check that fixtures /api/connection/* itself sees that request in its own answer). */
    readOrRefuse(params, refused = session.refused, { reads = false, message = NO_WRITES } = {}) {
      const { requestId, request } = params;
      if (request.method === 'GET' || (reads && readOnly(request))) return session.pass(requestId);
      if (request.method === 'POST' && /\/api\/connection\/check$/.test(new URL(request.url).pathname)) {
        let profile = null;
        try { profile = JSON.parse(request.postData ?? '{}').profile_id ?? null; } catch { /* answered as unknown */ }
        return session.fulfil(requestId, 200, PAGE_OPEN_TEST(profile));
      }
      refused.push(`${request.method} ${new URL(request.url).pathname}`);
      return session.refuse(requestId, message);
    },

    // ---- the page's saved configuration -----------------------------------------------------------------------------------
    /** Puts `config` (and the remembered run: a run folder, or null for none) into localStorage before the page's own code
     *  runs. when: 'always' (every load), 'missing' (only when nothing is saved yet) or 'once' (the first load of this tab).
     *  `also`: more code for every load of a workbench page. Returns the script's identifier. */
    async seed({ config, run, when = 'always', also = '' }) {
      const put = config === undefined ? '' : `localStorage.setItem(${text(CONFIG_KEY)}, ${text(JSON.stringify(config))});`;
      const remember = run === undefined ? '' : run === null ? `localStorage.removeItem(${text(RUN_KEY)});` : `localStorage.setItem(${text(RUN_KEY)}, ${text(run)});`;
      const source = when === 'once'
        ? `if (location.protocol.startsWith('http')) { if (!sessionStorage.getItem('fixture-seeded')) { sessionStorage.setItem('fixture-seeded', '1'); ${put} ${remember} } ${also} }`
        : when === 'missing' ? `if (!localStorage.getItem(${text(CONFIG_KEY)})) { ${put} } ${remember} ${also}` : `${put} ${remember} ${also}`;
      return (await send('Page.addScriptToEvaluateOnNewDocument', { source })).identifier;
    },
    /** The page writes its configuration 800 ms after the LAST change (store.ts), and headless Edge can run that timer late:
     *  a fixed sleep then reads one step behind. This tracks every pending 800 ms timer in window.__saves (register it
     *  before the page loads); `saved()` waits until none is left. An unwanted save still arms one and is seen. */
    trackSaves: () => send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => { const set = window.setTimeout, clear = window.clearTimeout; window.__saves = new Set();
      window.setTimeout = (fn, ms, ...rest) => { if (ms !== 800) return set(fn, ms, ...rest); const id = set(() => { window.__saves.delete(id); fn(...rest); }, ms); window.__saves.add(id); return id; };
      window.clearTimeout = id => { window.__saves.delete(id); return clear(id); }; })();` }),
    async saved() { await sleep(150); for (let i = 0; i < 100 && !(await session.evaluate('window.__saves.size === 0')); i++) await sleep(100); },
    /** The configuration as the page saved it in localStorage (null when there is none). */
    stored: () => session.evaluate(`JSON.parse(localStorage.getItem(${text(CONFIG_KEY)}) ?? 'null')`),

    /** A PNG: of the element a JS expression yields (with `pad` px around it, at most `maxHeight` high), of a given clip
     *  { x, y, width, height, scale }, or of the whole viewport. `beyond`: the clip may reach below the window. The tab is
     *  brought to the front first (a hidden tab never answers a capture), and a capture that hangs fails after 20 s. */
    async shot(file, what = null, { scale = 1, pad = 0, maxHeight = 1e6, beyond = false } = {}) {
      const clip = typeof what === 'string' ? await session.evaluate(`(() => { const r = (${what}).getBoundingClientRect();
        return { x: r.x - ${pad}, y: r.y - ${pad}, width: r.width + ${2 * pad}, height: Math.min(r.height + ${2 * pad}, ${maxHeight}), scale: ${scale} }; })()`) : what;
      await send('Page.bringToFront').catch(() => { /* a pop-up without the Page domain: capture anyway */ });
      const capture = send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip } : {}), ...(beyond ? { captureBeyondViewport: true } : {}) });
      let timer;
      const { data } = await Promise.race([capture, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`the screenshot ${path.basename(file)} did not come within 20 s`)), 20000); })])
        .finally(() => clearTimeout(timer));
      writeFileSync(file, Buffer.from(data, 'base64'));
    },
  };
  session.on('Runtime.exceptionThrown', p => errors.push(prefix + (p.exceptionDetails.exception?.description ?? p.exceptionDetails.text)));
  if (consoleApi) session.on('Runtime.consoleAPICalled', p => { if (p.type === 'error') errors.push(prefix + p.args.map(a => a.value ?? a.description).join(' ')); });
  return session;
}

// ---- Edge -----------------------------------------------------------------------------------------------------------------
/** A headless Edge with a new temporary profile (%TEMP%\gator-cdp-<tag>-*) on a debugging port of its own. */
export async function launchEdge(tag = 'check', { width = 1680, height = 1050, limitSeconds = Number(process.env.GATOR_CHECK_LIMIT_S) || 600 } = {}) {
  const profile = mkdtempSync(path.join(tmpdir(), `gator-cdp-${tag}-`));
  const temps = [], sessions = [];
  // --disable-extensions / --disable-sync: a fresh profile on this machine opens extension onboarding tabs (and a sync
  // dialog) some 60-90 s after start; the workbench tab is then hidden and Page.captureScreenshot never answers.
  const edge = spawn(EDGE, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run',
    '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--disable-sync', `--window-size=${width},${height}`, 'about:blank'], { stdio: 'ignore' });
  let exited = false, spawnError = null;
  const gone = new Promise(resolve => edge.on('exit', () => { exited = true; resolve(); }));
  edge.on('error', e => { spawnError = e; exited = true; });
  const browser = {
    profile, width, height, host: null, port: null, path: null, base: null,
    /** A folder of this check under the OS temp folder; removed by close(). */
    tempDir(name) { const dir = mkdtempSync(path.join(tmpdir(), `gator-cdp-${tag}-${name}-`)); temps.push(dir); return dir; },
    async pages() { return (await (await fetch(`${browser.base}/json/list`)).json()).filter(t => t.type === 'page'); },
    /** A session for another target (a pop-up window). Its page exceptions go into `errors`, each with `prefix`. */
    async attach(target, { errors = [], prefix = '', consoleApi = false } = {}) {
      const session = await connect(target, { errors, prefix, consoleApi });
      sessions.push(session);
      await session.send('Runtime.enable');
      return session;
    },
    /** The pop-up with this title (a fresh profile opens pages of its own: never "any other page"); `present: false` waits
     *  until it is gone and returns null. Throws after `ms`. */
    async window(title, { present = true, ms = 5000, except = null } = {}) {
      for (let waited = 0; waited < ms; waited += 100) {
        const found = (await browser.pages()).find(t => t.id !== except && t.title === title);
        if (!!found === present) return found ?? null;
        await sleep(100);
      }
      throw new Error(`the window "${title}" did not ${present ? 'appear' : 'close'}`);
    },
    /** The page Edge started with, as a session: Page and Runtime enabled, the viewport set (default 1680 x 1050).
     *  consoleApi: false = only exceptions count as console errors, not console.error() calls. `errors`: the array to
     *  collect them in (default a new one, session.consoleErrors). */
    async open({ width: w = width, height: h = height, consoleApi = true, errors = [] } = {}) {
      // The about:blank tab Edge was started with - never simply "the first page": that can be a tab Edge opened itself.
      let target;
      for (let i = 0; i < 75 && !target; i++) {
        try { target = (await browser.pages()).find(t => t.url === 'about:blank'); } catch { /* not up yet */ }
        if (!target) await sleep(200);
      }
      if (!target) throw new Error('Edge opened no about:blank page to drive');
      const page = await connect(target, { consoleApi, errors });
      sessions.push(page);
      await page.send('Page.enable'); await page.send('Runtime.enable');
      await page.viewport(w, h);
      return page;
    },
    /** Edge ends (asked first, then killed) and the profile and every tempDir are removed. Safe to call twice. */
    async close() {
      clearTimeout(watchdog);
      for (const s of sessions) try { s.close(); } catch { /* already closed */ }
      if (!exited && browser.base) {
        try {
          const ws = new WebSocket(`ws://${browser.host}:${browser.port}${browser.path}`);
          await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; setTimeout(reject, 2000); });
          ws.send(JSON.stringify({ id: 1, method: 'Browser.close' }));
        } catch { /* the kill below */ }
        await Promise.race([gone, sleep(3000)]);
      }
      if (!exited) { edge.kill(); await Promise.race([gone, sleep(3000)]); }
      for (const dir of [...temps.splice(0), profile]) {
        try { rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }); } catch (e) { console.log(`NOTE  temporary folder left behind: ${dir} (${e.code})`); }
      }
    },
  };
  // A check that hangs (a request nobody answers, a window that never closes) must not leave Edge and its profile behind.
  const watchdog = setTimeout(async () => {
    console.log(`ERROR the check did not finish within ${limitSeconds} s (GATOR_CHECK_LIMIT_S): Edge is closed and the check stops`);
    await browser.close(); process.exit(1);
  }, limitSeconds * 1000);
  watchdog.unref();
  process.once('SIGINT', async () => { await browser.close(); process.exit(130); });
  // Edge writes "<port>\n<browser path>" into the profile once it listens: the port was chosen by the system, not by us.
  let port = null, wsPath = null;
  for (let i = 0; i < 150 && !port && !exited; i++) {
    try {
      const [first, second] = readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n');
      if (/^\d+$/.test(first) && second?.startsWith('/devtools/')) [port, wsPath] = [Number(first), second.trim()];
    } catch { /* not written yet */ }
    if (!port) await sleep(100);
  }
  // It may listen on 127.0.0.1 or on ::1 only: the host that answers /json/version is used for every request and WebSocket.
  for (let i = 0; i < 20 && port && !browser.base && !exited; i++) {
    for (const host of ['127.0.0.1', '[::1]']) {
      const ok = await fetch(`http://${host}:${port}/json/version`, { signal: AbortSignal.timeout(1000) }).then(r => r.ok, () => false);
      if (ok) { Object.assign(browser, { host, port, path: wsPath, base: `http://${host}:${port}` }); break; }
    }
    if (!browser.base) await sleep(200);
  }
  if (!browser.base) {
    await browser.close();
    throw new Error(spawnError ? `Edge could not be started: ${spawnError.message}` : port ? `Edge answers on neither 127.0.0.1 nor [::1] at port ${port}` : 'Edge did not open a debugging port');
  }
  return browser;
}
