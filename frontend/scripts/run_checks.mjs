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
// needs it on a fixed port and a fixture of its own (PORTED below). The reward_v2 real/frontend checks
// read recorded evidence and are skipped. model_structure fails while the newest saved model under repo/outputs predates
// the current network code (types not verified): that is the data, not the runner.
import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scripts = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scripts, '..');
const configFile = path.join(root, 'vite.config.ts');
// Vite keeps its dependency cache in <root>/node_modules/.vite unless told otherwise: in a copy whose node_modules links the
// live tree's packages, that wrote into the live tree (record 7.290). A folder in the temp folder instead, one per checkout.
const cacheDir = path.join(tmpdir(), 'gator-checks-vite', createHash('sha256').update(root).digest('hex').slice(0, 12));

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

// Each check's duration (s) as the last run that finished it measured it, kept in DURATIONS beside every run's log folder: the
// longest start first, and a check's time limit is 3x its duration. FIRST_GUESS stands in for a check this machine never
// finished (the serial durations measured by hand before; plan-refactoring D5: derived from the runs instead of kept by hand).
const DURATIONS = path.join(tmpdir(), 'gator-checks-durations.json');
const FIRST_GUESS = { virtuoso_source_check: 76, connection_panel_check: 47, run_control_check: 46, testbench_probes_check: 43,
  external_agents_check: 12, output_panel_check: 25, run_control_live_check: 23, typing_check: 19, model_chooser_check: 19,
  project_help_check: 17, run_list_check: 16, ngspice_window_check: 16, working_copy_check: 15,
  save_now_check: 11, corner_check_check: 11, task_save_check: 10, graph_view_check: 8, blocking_issues_check: 8,
  calibration_check: 60, calibration_save_check: 14, dom_identity_check: 180 };
const measured = (() => { try { const kept = JSON.parse(readFileSync(DURATIONS, 'utf8')); return kept && typeof kept === 'object' ? kept : {}; } catch { return {}; } })();
const EXPECTED = { ...FIRST_GUESS, ...measured };
const WRITERS = ['export_check', 'run_control_live_check', 'calibration_check'];
const SOURCE = ['request_lifecycle_check', 'edit_state_check'];
// Checks that insist on Vite's source preview on a port of their own and read a fixture their author made; run_checks.sh
// passes the flag - and allows the fixture's folder on backend A - only when that fixture exists.
const PORTED = { reward_v21_check: { port: 5191, flag: '--reward-fixture', needs: 'its fixture run under /tmp/gator-reward-v21-browser' } };
const SKIPPED = { reward_v2_frontend_check: 'needs recorded real-qualification evidence folders',
  reward_v2_real_check: 'needs recorded real-qualification evidence folders' };
for (const [name, p] of Object.entries(PORTED)) if (!flag(p.flag)) SKIPPED[name] = `needs ${p.needs} (run_checks.sh)`;
// encoder_models_check reads two saved MOCK models from a folder backend A allows: --encoder-models <that folder, as the
// backend sees it>, which run_checks.sh makes (record 7.292).
const encoderModels = option('--encoder-models');
if (!encoderModels) SKIPPED.encoder_models_check = 'needs its two saved MOCK models (run_checks.sh makes them: --encoder-models)';

const only = names(option('--only')), skip = names(option('--skip')) ?? [];
// Check catalog: files are still discovered dynamically below; this list is documentation only.
// Hermetic checks refuse backend writes; snapshots/downloads stay in each check's evidence folder.
// external_agents_check: the Agent UI and routes stay absent; user-started desktop or CLI agents handle assistance.
// blocking_issues_check: Header's blocking-issues window; hermetic; record 7.12.
// calibration_check: Baseline calibration and Apply; writes scratch MOCK runs; records 7.197, 7.202.
// calibration_save_check: Calibration Apply and save; hermetic task-save fixtures; record 7.217.
// callouts_check: Panel and window callout styling; hermetic; record 7.218.
// circuit_layout_check: Circuit-graph layout; pure in-memory differential checks; record 7.375.
// circuit_source_check: Restoring the removed netlist source; hermetic; record 7.53.
// connection_panel_check: Connection window; hermetic, optional scratch ngspice writes; records 7.9, 7.77.
// consistency_check: Saved-task Check now and refused starts; hermetic; record 7.61.
// corner_check_check: Corner check tab and run state; hermetic; record 7.62.
// crash_panel_check: Crash panel and recovery actions; hermetic; record 7.188.
// dom_identity_check: Page/window DOM and request identity; hermetic, saves snapshots; record 7.290.
// edit_state_check: Editor/save state and Undo under StrictMode; in-memory source fixture; record 7.174.
// editor_columns_check: Parameters, Probes and Specs columns; hermetic; record 7.172.
// editor_renames_check: Editor rename propagation; pure in-memory differential checks; record 7.377.
// encoder_models_check: RL-model structure and attention; reads saved MOCK fixtures on scratch API; record 7.228.
// export_check: Run-tab exports and downloaded contents; writes scratch MOCK runs and exports; record 7.31.
// files_tab_check: Output files downloads and progress; hermetic download fixtures; record 7.91.
// find_fill_copy_check: Editor Find, Fill and Copy; hermetic, clipboard intercepted; record 7.184.
// formula_bar_check: Editor formula bar and cell editing; hermetic; record 7.175.
// graph_paint_check: Circuit-graph attention styling; in-memory headless Cytoscape; record 7.374.
// graph_view_check: Circuit graph window; fixtures plus optional saved-model reads; record 7.33.
// launch_recovery_check: Header recovery after a lost start/status reply; hermetic; record 7.268.
// looks_check: Page and window layout in the Roadster look; hermetic; records 7.158, 7.360.
// matched_devices_check: Parameters' Matched devices window; hermetic; record 7.103.
// mode_suggestion_check: Run mode suggestions and legacy resume; hermetic; records 7.90, 7.267.
// model_chooser_check: RL-model window and save-point selection; hermetic; record 7.265.
// model_structure_check: Model Details' structure tables; fixtures plus optional saved-model reads; record 7.26.
// module_fold_check: Run configuration and Output settings folding; hermetic; record 7.45.
// network_inputs_check: RL-model network-input choices; hermetic; records 7.298, 7.317.
// network_panel_check: RL-model templates and settings; hermetic save replies; record 7.265.
// ngspice_window_check: ngspice task window; hermetic import fixtures; record 7.74.
// output_panel_check: Output settings, paths and units; hermetic; record 7.41.
// pdk_check: PDK window and component list; hermetic; record 7.54.
// project_help_check: Circuit-column and Virtuoso-window explanations; hermetic; record 7.30.
// reliability_check: Browser persistence and stale UI replies; hermetic; record 7.130.
// request_lifecycle_check: Read cancellation and stale replies; in-memory source fixture; verified in record 7.99.
// reward_block_check: Run configuration's reward sentence and limits; hermetic; record 7.183.
// reward_v21_check: Reward v2.1 controls; hermetic preview with scratch fixture reads; record 7.112.
// reward_v2_frontend_check: Saved real reward data; scratch API and new evidence reports; records 7.95, 7.109.
// reward_v2_real_check: Saved real reward qualification; scratch API and evidence reports; record 7.95.
// room_check: Editor space, tab placement and narrow layouts; hermetic; record 7.179.
// run_control_check: Header Start, Pause, Resume and Abort; hermetic run fixtures; record 7.18.
// run_control_live_check: Header run controls end to end; writes scratch MOCK runs; record 7.18.
// run_list_check: Runs window, selection and details; hermetic; record 7.38.
// save_now_check: Header Save now without pausing; hermetic; record 7.23.
// sheet_check: Editor ties, selection and spreadsheet keys; hermetic; record 7.180.
// spec_equations_check: Specs equations and migration; read-only backend validation; record 7.52.
// table_view_check: Task/run/model table order and selection; pure in-memory checks; record 7.373.
// task_list_check: Tasks window and task selection; hermetic; record 7.227.
// task_rows_check: Task selection loads its editor rows; hermetic, optional read-only API mode; record 7.44.
// task_run_check: Bottom tabs follow the selected task; hermetic; record 7.212.
// task_save_check: Save as and Task file windows; hermetic save fixtures; records 7.57, 7.246.
// testbench_probes_check: Virtuoso testbench selection and Probe rows; hermetic; record 7.49.
// training_data_check: Training-tab series arithmetic; local fixtures without a backend; record 7.193.
// training_tab_check: Training-tab charts and recorded values; hermetic; record 7.193.
// typing_check: Typed editor values, units and imports; hermetic; record 7.64.
// unit_text_check: Shared quantity formatting; read-only schema API, no browser; record 7.208.
// unsaved_rows_check: Editor marks and diffs for unsaved rows; hermetic; record 7.222.
// virtuoso_source_check: Virtuoso cell window and import; hermetic, no Virtuoso contact; records 7.15, 7.362.
// working_copy_check: Virtuoso working-copy and Maestro setup; hermetic; record 7.55.
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
  const quiet = { configFile, root, cacheDir, logLevel: 'warn', clearScreen: false };
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
  const envOf = name => WRITERS.includes(name) ? { GATOR_SCRATCH_OUT: scratchOut }
    : name === 'encoder_models_check' ? { GATOR_WORKBENCH_OUTPUT_ROOT: encoderModels } : {};
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
  // What this run measured, for the next one's order and limits: every check that ended by itself (a timeout says only that it
  // took longer than its limit).
  try { writeFileSync(DURATIONS, JSON.stringify({ ...measured, ...Object.fromEntries(results.filter(r => r.status !== 'TIMEOUT')
    .map(r => [r.name, Math.ceil(r.seconds)])) }, null, 1)); } catch { /* not kept: the next run starts from what it finds */ }
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
