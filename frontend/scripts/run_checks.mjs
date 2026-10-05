// Runs the browser checks (*_check.mjs) in parallel lanes against scratch servers - never the user's backend on 8765 -
// with one log and one screenshot folder per check, then prints a summary (review of 2026-09-30: the serial batch took
// 8.7 min, mostly waiting). Start it from WSL with run_checks.sh, which starts and stops the two scratch backends:
//   frontend/scripts/run_checks.sh [--lanes 4] [--only a,b] [--skip a,b] [--retry-failed] [--out <Windows dir>]
// By hand (Windows node), with backends already running:
//   node run_checks.mjs --hermetic-api http://127.0.0.1:<A> --writer-api http://127.0.0.1:<B> --scratch-out <B's allowed
//   output root, as the backend sees it> [--build <a built dist>] [--reward-fixture] [--lanes N] ...
// The hermetic checks share backend A and one preview of this tree's build. The two that start real MOCK runs (export,
// run_control_live) take backend B, one after the other: a page takes over any live run of its backend when it opens,
// so two of them side by side would adopt each other's run. request_lifecycle needs Vite's source preview; reward_v21
// and llm_sizing need it on a fixed port and a fixture of their own (PORTED below). The reward_v2 real/frontend checks
// read recorded evidence and are skipped. model_structure fails while the newest saved model under repo/outputs predates
// the current network code (types not verified): that is the data, not the runner.
import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scripts = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scripts, '..');
const configFile = path.join(root, 'vite.config.ts');

const args = process.argv.slice(2);
const option = (name, fallback = null) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; };
const flag = name => args.includes(name);
const names = list => (list ? list.split(',').map(n => n.trim().replace(/\.mjs$/, '')).map(n => n.endsWith('_check') ? n : `${n}_check`) : null);
const lanes = Math.max(1, Number(option('--lanes', 4)));
const hermeticApi = option('--hermetic-api'), writerApi = option('--writer-api'), scratchOut = option('--scratch-out');
const out = option('--out', path.join(tmpdir(), `gator-checks-${new Date().toISOString().replace(/[:.]/g, '-')}`));
if (!hermeticApi) { console.log('ERROR --hermetic-api <scratch backend URL> is required (run_checks.sh starts one)'); process.exit(2); }
for (const api of [hermeticApi, writerApi].filter(Boolean))
  if (new URL(api).port === '8765') { console.log(`ERROR ${api} is the user's live backend: give a scratch backend`); process.exit(2); }

// The last measured serial durations (s): the longest start first, and a check's time limit is 3x its duration.
const EXPECTED = { virtuoso_source_check: 76, connection_panel_check: 47, run_control_check: 46, testbench_probes_check: 43,
  agent_tab_check: 34, output_panel_check: 25, run_control_live_check: 23, typing_check: 19, model_chooser_check: 19,
  project_help_check: 17, run_list_check: 16, ngspice_window_check: 16, agent_setup_check: 16, working_copy_check: 15,
  save_now_check: 11, corner_check_check: 11, task_save_check: 10, graph_view_check: 8, blocking_issues_check: 8,
  calibration_check: 40 };
const WRITERS = ['export_check', 'run_control_live_check', 'agent_tab_check', 'calibration_check'];
const SOURCE = ['request_lifecycle_check', 'edit_state_check'];
// Checks that insist on Vite's source preview on a port of their own and read a fixture their author made; run_checks.sh
// passes the flag - and allows the fixture's folder on backend A - only when that fixture exists.
const PORTED = { reward_v21_check: { port: 5191, flag: '--reward-fixture', needs: 'its fixture run under /tmp/gator-reward-v21-browser' },
  llm_sizing_check: { port: 5193, flag: '--llm-fixture', needs: 'artifacts/local/llm-sizing/browser-fixture' } };
const SKIPPED = { reward_v2_frontend_check: 'needs recorded real-qualification evidence folders',
  reward_v2_real_check: 'needs recorded real-qualification evidence folders' };
for (const [name, p] of Object.entries(PORTED)) if (!flag(p.flag)) SKIPPED[name] = `needs ${p.needs} (run_checks.sh)`;

const only = names(option('--only')), skip = names(option('--skip')) ?? [];
const all = readdirSync(scripts).filter(f => f.endsWith('_check.mjs')).map(f => f.replace(/\.mjs$/, ''));
const chosen = all.filter(n => (!only || only.includes(n)) && !skip.includes(n) && !(n in SKIPPED && !only?.includes(n)));
if (!writerApi || !scratchOut) for (const n of WRITERS) if (chosen.includes(n)) chosen.splice(chosen.indexOf(n), 1);

const freePort = () => new Promise((resolve, reject) => {
  const server = net.createServer();
  server.once('error', reject);
  server.listen(0, '127.0.0.1', () => { const { port } = server.address(); server.close(() => resolve(port)); });
});
const portFree = port => new Promise(resolve => {
  const server = net.createServer();
  server.once('error', () => resolve(false));
  server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)));
});
const answers = async (url, seconds = 60) => {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    try { if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return true; } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 250));
  }
  return false;
};
const killTree = pid => { try { execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' }); } catch { /* gone */ } };

const servers = [];
async function serve() {
  const vite = await import('vite');
  const quiet = { configFile, root, logLevel: 'warn', clearScreen: false };
  let dist = option('--build');
  if (!dist) {
    dist = path.join(out, 'dist');
    await vite.build({ ...quiet, build: { outDir: dist, emptyOutDir: true } });
  }
  const preview = async api => {
    const port = await freePort();
    const server = await vite.preview({ ...quiet, build: { outDir: dist },
      preview: { host: '127.0.0.1', port, strictPort: true, proxy: { '/api': api } } });
    servers.push(server);
    return `http://127.0.0.1:${port}/`;
  };
  const source = async (api, port) => {
    const server = await vite.createServer({ ...quiet, server: { host: '127.0.0.1', port, strictPort: true, hmr: false,
      proxy: { '/api': api } } });
    await server.listen();
    servers.push(server);
    return `http://127.0.0.1:${port}/`;
  };
  const urls = { hermetic: await preview(hermeticApi) };
  if (writerApi && chosen.some(n => WRITERS.includes(n))) urls.writer = await preview(writerApi);
  if (chosen.some(n => SOURCE.includes(n))) urls.source = await source(hermeticApi, await freePort());
  for (const [name, { port }] of Object.entries(PORTED).filter(([n]) => chosen.includes(n))) {
    if (await portFree(port)) urls[name] = await source(hermeticApi, port);
    else { chosen.splice(chosen.indexOf(name), 1); SKIPPED[name] = `port ${port} is taken`; }
  }
  for (const url of Object.values(urls))
    if (!await answers(url)) throw new Error(`the preview at ${url} did not answer`);
  return urls;
}

function runOne(name, url, env = {}) {
  return new Promise(resolve => {
    const dir = path.join(out, name);
    mkdirSync(dir, { recursive: true });
    const limit = Math.max(120, 3 * (EXPECTED[name] ?? 40));
    const started = Date.now();
    const child = spawn(process.execPath, [path.join(scripts, `${name}.mjs`), dir], { windowsHide: true,
      env: { ...process.env, GATOR_WORKBENCH_URL: url, GATOR_CHECK_LIMIT_S: String(limit), ...env } });
    let text = '', killed = false;
    child.stdout.on('data', d => { text += d; });
    child.stderr.on('data', d => { text += d; });
    const timer = setTimeout(() => { killed = true; killTree(child.pid); }, (limit + 30) * 1000);
    child.on('close', code => {
      clearTimeout(timer);
      writeFileSync(path.join(out, `${name}.log`), text);
      let passed = (text.match(/^PASS\b/gm) ?? []).length, failed = (text.match(/^FAIL\b/gm) ?? []).length;
      const errors = (text.match(/^ERROR\b/gm) ?? []).length;
      const report = path.join(dir, 'browser-report.json');               // reward_v21 reports in its own file
      if (!passed && existsSync(report)) {
        try { const checks = JSON.parse(readFileSync(report, 'utf8')).checks ?? []; passed = checks.filter(c => c.passed).length; failed += checks.length - passed; }
        catch { /* unreadable: the exit code decides */ }
      }
      const status = killed ? 'TIMEOUT' : code === 0 && !failed && !errors ? 'passed' : 'FAILED';
      resolve({ name, status, passed, failed, errors, seconds: (Date.now() - started) / 1000, url,
        problems: text.split(/\r?\n/).filter(l => /^(FAIL|ERROR)\b/.test(l)).slice(0, 6) });
    });
  });
}

async function main() {
  mkdirSync(out, { recursive: true });
  const t0 = Date.now();
  // WSL's curl can answer before Windows localhost forwarding is ready. The browser and Vite run on Windows.
  await Promise.all([hermeticApi, writerApi].filter(Boolean).map(async api => {
    if (!await answers(new URL('/api/meta', api))) throw new Error(`Windows cannot reach the scratch backend at ${api}`);
  }));
  const urls = await serve();
  const urlOf = name => WRITERS.includes(name) ? urls.writer : SOURCE.includes(name) ? urls.source : urls[name] ?? urls.hermetic;
  const envOf = name => WRITERS.includes(name) ? { GATOR_SCRATCH_OUT: scratchOut } : {};
  const pool = chosen.filter(n => !WRITERS.includes(n)).sort((a, b) => (EXPECTED[b] ?? 10) - (EXPECTED[a] ?? 10));
  const serial = chosen.filter(n => WRITERS.includes(n));
  console.log(`${chosen.length} checks, ${lanes} lanes (+1 for ${serial.length} scripts that write scratch settings or start MOCK runs); logs in ${out}`);
  for (const [name, why] of Object.entries(SKIPPED)) if (all.includes(name) && !chosen.includes(name)) console.log(`skip  ${name}: ${why}`);
  const results = [];
  const report = r => { results.push(r); console.log(`[${String(results.length).padStart(2)}/${chosen.length}] ${r.status.padEnd(7)} `
    + `${r.name.padEnd(28)} ${String(r.passed).padStart(3)} passed ${r.failed ? `${r.failed} FAILED ` : ''}${r.seconds.toFixed(1).padStart(6)} s`); };
  const lane = async queue => { while (queue.length) { const name = queue.shift(); report(await runOne(name, urlOf(name), envOf(name))); } };
  await Promise.all([...Array.from({ length: Math.min(lanes, pool.length) }, () => lane(pool)), lane(serial)]);
  if (flag('--retry-failed'))
    for (const r of results.filter(x => x.status !== 'passed')) {
      const again = await runOne(r.name, r.url, envOf(r.name));
      console.log(`retry ${again.status.padEnd(7)} ${r.name}${again.status === 'passed' ? '  (flaky: failed once, passed alone)' : ''}`);
      if (again.status === 'passed') Object.assign(r, { status: 'flaky' });
    }
  const bad = results.filter(r => r.status !== 'passed' && r.status !== 'flaky');
  const total = results.reduce((s, r) => s + r.passed, 0);
  console.log(`\n${results.length} scripts, ${total} checks passed, ${bad.length} script(s) not passed, `
    + `${results.filter(r => r.status === 'flaky').length} flaky, ${((Date.now() - t0) / 1000).toFixed(0)} s wall (logs: ${out})`);
  for (const r of bad) console.log(`  ${r.status} ${r.name}: ${path.join(out, `${r.name}.log`)}\n${r.problems.map(p => `    ${p.slice(0, 200)}`).join('\n')}`);
  return bad.length ? 1 : 0;
}

let code = 1;
try { code = await main(); }
catch (error) { console.log(`ERROR ${error?.stack ?? error}`); }
finally { await Promise.allSettled(servers.map(s => s.close?.() ?? s.httpServer?.close())); }
process.exit(code);
