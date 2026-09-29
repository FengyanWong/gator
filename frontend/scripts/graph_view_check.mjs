// Browser check of the circuit graph view (the ONE on-screen picture, user decision 2026-09-21) and of the red Abort
// button. Same approach as model_structure_check.mjs: a throwaway headless Edge over the DevTools protocol against a
// RUNNING workbench (default http://127.0.0.1:8765/). The chooser's routes and /api/runs/model/graph-view are answered
// with canned data labelled FIXTURE, so the drawn graph is known. GET requests pass through; every other writing
// request is refused here, so this check can start, save or probe nothing on the backend it runs against.
// What it pins: nothing is asked and the drawing library is NOT loaded until the view is opened; one request for the
// RESOLVED save point; a NODE-LINK picture of the network's graph (one node per device and net, straight links - no
// schematic symbols, rails or routed wires) with the circuit only as HINTS (positions, shapes, colours, gate / bulk marks);
// every device, net and connection is drawn, a sized device carries "now -> proposed"; line
// thickness follows the attention of the chosen block / head / direction WITHOUT a new request; a receiver with a single
// connection is drawn dashed (its 1.0 says nothing); supply on top; nothing overlaps or leaves the canvas; the tables
// beside the picture (sizes now / proposed / tried; the connections of a clicked device, summing to 1); another
// evaluation = one request; an encoder without attention and a refusal are said in plain words; Abort is red.
// Last section, against the REAL route of the backend it runs on (skipped with a note when it has no saved model or is
// older than the route): the drawn graph equals POST /api/runs/model/graph-view for the first real model.
// Run (Windows node through WSL interop; needs node >= 22 for the built-in WebSocket; takes about 30 s):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/graph_view_check.mjs)" [screenshot-dir]
// Optional: GATOR_WORKBENCH_OUTPUT_ROOT (from WSL: WSLENV=GATOR_WORKBENCH_URL:GATOR_WORKBENCH_OUTPUT_ROOT). Exit code 1 on failure.
import path from 'node:path';
import { validConfiguration, check, launchEdge, NEVER_ASKED_OR_SAVED, outDir, reportRefused, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT || undefined;
const out = outDir();
const browser = await launchEdge('graph');

// ---- canned answers ------------------------------------------------------------------------------------------
const NET = { encoder_type: 'graph_transformer', hidden_dim: 16, heads: 2, layers: 2 };
const RUN = '/fixture/outputs/mock/fx__1/runs/FIXTURE_graph/scratch_seed1__r1';
const POINT = { checkpoint_id: 'ckpt-00000020-final', kind: 'final', created_utc: '2026-09-21T10:04:00+00:00', mode: 'scratch', evaluations: 20, learner_updates: 16, replay_size: 20,
  restoration_capability: 'full_state', missing_components: [], network: NET, is_latest: true, is_best_policy: false };
const MODEL = { run_dir: RUN, run_id: 'run-fx', task_id: 'FIXTURE_graph:0123456789abcdef', task_name: 'FIXTURE_graph', task_definition_hash: 'f'.repeat(64), mode: 'scratch', mock: true, seed: 1,
  created_utc: '2026-09-21T10:00:00+00:00', state: 'completed', experiment: 'fx__1', evaluations: 20, circuit_task: 'synthetic:gpdk045_ota5', circuit_class: 'opamp', latest: POINT.checkpoint_id,
  best_policy: { selected: null, status: 'not_selected', reason: 'FIXTURE', score: null }, checkpoints: [POINT], network: NET, saved_utc: POINT.created_utc, trained_evaluations: 20, learner_updates: 16, restoration_capability: 'full_state' };
const DESCRIBED = { description: { checkpoint_id: POINT.checkpoint_id, path: `${RUN}/checkpoints/${POINT.checkpoint_id}`, kind: 'final', source_run_id: 'run-fx', source_task_id: MODEL.task_id, mode: 'scratch',
  created_utc: POINT.created_utc, metadata_version: 'FIXTURE', counters: { evaluations_committed: 20, learner_updates: 16, replay_size: 20 }, restoration_capability: 'full_state', restorable_components: [],
  missing_components: [], contract: { model_config: NET, sac_config: {} }, file_problems: [] }, compatibility: { mode: 'fine_tune', compatible: true, checks: [], checkpoint_id: POINT.checkpoint_id,
  source_run_id: 'run-fx', restoration_capability: 'full_state', suggestion: null }, suggestion: null };
// device, terminal, net, [to_device block1, block2], [to_net block1, block2]; uniform shares follow from the counts below
const WIRES = [['M1', 'D', 'out', [0.4, 0.1], [0.5, 0.2]], ['M1', 'G', 'in', [0.1, 0.4], [0.6, 0.4]], ['M1', 'S', '0', [0.3, 0.3], [0.2, 0.1]], ['M1', 'B', '0', [0.2, 0.2], [0.3, 0.2]],
  ['M2', 'D', 'out', [0.25, 0.25], [0.3, 0.5]], ['M2', 'G', 'in', [0.25, 0.25], [0.4, 0.6]], ['M2', 'S', 'vdd', [0.25, 0.25], [0.5, 0.5]], ['M2', 'B', 'vdd', [0.25, 0.25], [0.5, 0.5]],
  ['CL', 'P', 'out', [0.7, 0.6], [0.2, 0.3]], ['CL', 'N', '0', [0.3, 0.4], [0.4, 0.5]], ['VB', 'P', 'vb', [0.8, 0.5], [1, 1]], ['VB', 'N', '0', [0.2, 0.5], [0.1, 0.2]]];
const intoDevice = {}, intoNet = {};
for (const [d, , n] of WIRES) { intoDevice[d] = (intoDevice[d] ?? 0) + 1; intoNet[n] = (intoNet[n] ?? 0) + 1; }
const view = (evaluation, { attention = true } = {}) => ({ checkpoint_id: POINT.checkpoint_id, run_dir: RUN, task_id: MODEL.task_id, network: attention ? NET : { ...NET, encoder_type: 'rgcn' }, circuit_id: 'FIXTURE', origin: 'synthetic',
  step: { evaluation, policy_version_then: 3, saved_at: 20, status: 'ok', first: 2, last: 20, count: 19 },
  metrics: [{ id: 'score', value: 0.61, unit: 'fixture', valid: true }],
  devices: [{ id: 'M1', kind: 'nmos', model: 'FIXTURE_n', groups: ['wn'], parameters: { w: 2e-6, l: 1e-7 } }, { id: 'M2', kind: 'pmos', model: 'FIXTURE_p', groups: [], parameters: { w: 4e-6 } },
    { id: 'CL', kind: 'capacitor', model: 'cap', groups: ['cl'], parameters: { c: 1e-12 } }, { id: 'VB', kind: 'vsource', model: 'vsource', groups: [], parameters: { dc: 0.6 } }],
  nets: [{ id: 'out', roles: ['output'] }, { id: 'in', roles: ['input'] }, { id: '0', roles: ['ground'] }, { id: 'vdd', roles: ['supply'] }, { id: 'vb', roles: ['normal'] }],
  connections: WIRES.map(([device, terminal, net, toDevice, toNet], ordinal) => ({ id: `${device}.${terminal}#${ordinal}->${net}`, device, net, terminal, role: { D: 'drain', G: 'gate', S: 'source', B: 'bulk', P: 'positive', N: 'negative' }[terminal], ordinal,
    attention: !attention ? [] : [0, 1].map(block => ({ layer: block + 1, to_device: toDevice[block], to_device_heads: [toDevice[block] + 0.05, toDevice[block] - 0.05], to_device_uniform: 1 / intoDevice[device],
      to_net: toNet[block], to_net_heads: [toNet[block], toNet[block]], to_net_uniform: 1 / intoNet[net] })) })),
  groups: [{ id: 'wn', parameter: 'w', unit: 'm', value: 2e-6 + (evaluation - 20) * 1e-7, lower: 1e-6, upper: 8e-6, scale: 'linear', mutable: true, members: [{ device: 'M1', parameter: 'w', ratio: 1 }],
    policy_action: 0.2, policy_value: 5.2e-6, recorded_action: -0.5, recorded_value: 2.75e-6 },
  { id: 'cl', parameter: 'c', unit: 'F', value: 1e-12, lower: 1e-13, upper: 5e-12, scale: 'linear', mutable: true, members: [{ device: 'CL', parameter: 'c', ratio: 1 }],
    policy_action: 0, policy_value: 2.55e-12, recorded_action: 0.1, recorded_value: 2.795e-12 }],
  attention: attention ? { available: true, layers: 2, heads: 2, reason: null } : { available: false, layers: 0, heads: 0, reason: 'FIXTURE: The rgcn encoder has no attention: the picture shows the circuit and the proposed sizes only.' },
  reading: 'FIXTURE reading: attention is normalized per RECEIVING node; a node with a single connection always shows 1.0.', actions_note: 'FIXTURE actions note.' });
const VALID = validConfiguration();

await runChecks(browser, async () => {
  const starter = await (await fetch(new URL('api/tasks/starter?task_key=synthetic:gpdk045_ota5', APP))).json();
  const CONFIG = { ...starter, run: { ...starter.run, mode: 'fine_tune', network: { ...NET, layers: 2 }, model_source: { run_dir: RUN, checkpoint_id: 'latest' } }, output: { experiment_name: 'fixture', ...(ROOT ? { output_root: ROOT } : {}) }, research: {} };
  const page = await browser.open({ consoleApi: false });
  const { send, evaluate, fulfil, consoleErrors } = page;
  const refused = []; const asked = []; let canned = true, mode = {}, failNext = null;
  const answer = ({ requestId, request }) => {
    const name = new URL(request.url).pathname, body = request.postData ? JSON.parse(request.postData) : null;
    if (name === '/api/config/validate') return fulfil(requestId, 200, VALID);
    if (name === '/api/runs/default-model') return fulfil(requestId, 200, { run_dir: null, checkpoint_id: 'latest', reason: 'FIXTURE' });
    if (!canned && ['/api/runs/models', '/api/runs/model', '/api/runs/model/graph-view'].includes(name)) return send('Fetch.continueRequest', { requestId });
    if (name === '/api/runs/models') return fulfil(requestId, 200, { models: [MODEL] });
    if (name === '/api/runs/model') return fulfil(requestId, 200, DESCRIBED);
    if (name === '/api/runs/model/graph-view') {
      asked.push(body);
      if (failNext) { const detail = failNext; failNext = null; return fulfil(requestId, 409, { detail }); }
      return fulfil(requestId, 200, view(body.evaluation ?? 20, mode));
    }
    return page.readOrRefuse({ requestId, request }, refused);
  };
  const until = (expression, tries = 60) => page.until(expression, tries);
  const RIGHT = `document.querySelector('.right')`, OPEN = `document.querySelector('.right button.graph-open')`, DIALOG = `document.querySelector('dialog.graph-dialog')`, CY = `document.querySelector('.graph-canvas')?.__cy`;
  const setSelect = (expression, value) => page.setValue(`${expression}`, value);
  const drawn = () => evaluate(`(() => { const cy = ${CY}; if (!cy) return null; const box = cy.container().getBoundingClientRect();
    return { nodes: cy.nodes().map(n => ({ id: n.id(), label: n.data('label'), sized: n.data('sized'), kind: n.data('kind'), shape: n.style('shape'), fill: n.style('background-color'),
        x: n.renderedPosition('x'), y: n.renderedPosition('y'), box: n.renderedBoundingBox({ includeLabels: false }) })),
      edges: cy.edges().map(e => ({ curve: e.style('curve-style'), mark: e.style('source-arrow-shape'), role: e.data('role'), ends: [e.source().id(), e.target().id()], id: e.id(), attention: e.data('attention'), trivial: e.data('trivial'), width: parseFloat(e.style('width')), dashed: e.style('line-style') === 'dashed', label: e.data('label'), visible: e.visible() })),
      width: box.width, height: box.height }; })()`);
  const waitAsked = async count => { for (let i = 0; i < 60 && asked.length < count; i++) await sleep(100); return asked.length; };
  const scripts = () => evaluate(`performance.getEntriesByType('resource').filter(r => r.name.endsWith('.js')).map(r => r.name.split('/').pop())`);
  const shot = async (name, expression) => page.shot(path.join(out, name),
    await evaluate(`(() => { const r = ${expression}.getBoundingClientRect(); return { x: Math.max(0, r.x), y: Math.max(0, r.y), width: Math.min(1680, r.width), height: Math.min(1050, r.height), scale: 1 }; })()`));
  const edgeOf = (graph, device, terminal) => graph.edges.find(e => e.id.startsWith(`c:${device}.${terminal}#`));

  await page.intercept(['*/api/*'], answer);
  await page.seed({ config: CONFIG, when: 'once' });
  await send('Page.navigate', { url: APP });
  if (!(await until(`!!${RIGHT}?.querySelector('select.model-point')`, 150))) throw new Error('the model chooser never showed the seeded model; the page reads: ' + JSON.stringify(await evaluate(`document.body.innerText.slice(0, 300)`)));
  if (!(await until(`!!(${OPEN})`, 60))) throw new Error('this page has no "Circuit graph view" button: the served frontend is older than it (npm run build, then reload)');

  // ---- the Abort button is red -------------------------------------------------------------------------------------------------
  const abort = await evaluate(`(() => { const b = document.querySelector('header button.run-abort'), s = getComputedStyle(b); return { background: s.backgroundColor, colour: s.color, border: s.borderTopColor, disabled: b.disabled }; })()`);
  check('the Abort button is solid red with white text (also while there is nothing to abort)', abort.background === 'rgb(179, 38, 30)' && abort.colour === 'rgb(255, 255, 255)' && abort.border === 'rgb(179, 38, 30)', JSON.stringify(abort));

  // ---- nothing before it is opened: no request, and the drawing library is not loaded with the page ----------------------------------
  await until(`!${OPEN}.disabled`, 60); await sleep(500);
  const before = await scripts();
  check('nothing is asked before the view is opened', asked.length === 0, `${asked.length} request(s)`);
  check('the button sits under the structure fold-out and says what it does', await evaluate(`${OPEN}.parentElement.previousElementSibling?.classList.contains('structure') && /Nothing is simulated and nothing is written/.test(${OPEN}.title)`));
  await evaluate(`${OPEN}.click()`);
  check('opening it shows a dialog and asks once, for the RESOLVED save point and the default evaluation', (await until(`${DIALOG}.open`, 30)) && (await waitAsked(1)) === 1
    && asked[0].run_dir === RUN && asked[0].checkpoint_id === POINT.checkpoint_id && asked[0].evaluation === null, JSON.stringify(asked[0]));
  check('the graph is drawn', await until(`!!(${CY}) && ${CY}.nodes().length > 0`, 80));
  const after = await scripts();
  check('the drawing library was loaded only now, as its own file', after.length > before.length, JSON.stringify(after.filter(s => !before.includes(s))));
  let graph = await drawn();
  check('every device and net is a node, every connection a line', graph.nodes.length === 9 && graph.edges.length === WIRES.length, `${graph.nodes.length} nodes, ${graph.edges.length} lines`);
  const node = id => graph.nodes.find(n => n.id === id);
  check('a sized device reads id, kind and "now -> proposed"', node('d:M1').label === 'M1\nnmos\nw 2 \u00b5m -> 5.2 \u00b5m' && node('d:M1').sized === 1 && node('d:CL').label === 'CL\ncapacitor\nc 1 pF -> 2.55 pF', JSON.stringify([node('d:M1').label, node('d:CL').label]));
  check('a device the policy does not size reads id and kind only', node('d:M2').label === 'M2\npmos' && node('d:M2').sized === 0);
  check('lines carry the terminal and the attention of block 1 / mean / "what a device takes"', WIRES.every(([d, t, , toDevice]) => { const e = edgeOf(graph, d, t); return e.label === t && Math.abs(e.attention - toDevice[0]) < 1e-9; }));
  check('more attention = a thicker line', edgeOf(graph, 'VB', 'P').width > edgeOf(graph, 'M1', 'D').width && edgeOf(graph, 'M1', 'D').width > edgeOf(graph, 'M1', 'G').width,
    JSON.stringify([edgeOf(graph, 'VB', 'P').width, edgeOf(graph, 'M1', 'D').width, edgeOf(graph, 'M1', 'G').width]));
  check('no line is dashed in this direction (every device has several connections)', graph.edges.every(e => !e.dashed && e.trivial === 0));
  const tops = graph.nodes.slice().sort((a, b) => a.y - b.y);
  check('"Top-down from the supply": the supply net is the topmost node', tops[0].id === 'n:vdd', tops.slice(0, 3).map(n => n.id).join());
  check('... and ground is the bottom one, as in a schematic', tops[tops.length - 1].id === 'n:0', tops.slice(-3).map(n => n.id).join());
  // ---- a NODE-LINK picture of the network's graph (user: "don't generate schematic ... graph neural network style ... with some hints
  //      from the circuit information"): the circuit only gives HINTS - positions, a node's shape and colour, a mark at a gate / bulk link ------
  check('it is the graph the network sees: exactly one node per device and per net, one link per connection - no helper nodes, rails or symbols',
    graph.nodes.length === 9 && graph.edges.length === WIRES.length && graph.edges.every(e => e.ends[0].startsWith('d:') && e.ends[1].startsWith('n:'))
    && !(await evaluate(`${CY}.nodes().some(n => String(n.style('background-image')).includes('svg'))`)));
  check('links are straight node-to-node links, not routed wires', graph.edges.every(e => e.curve === 'bezier'), [...new Set(graph.edges.map(e => e.curve))].join());
  check('hint - shape says the family: transistors rounded boxes, R / C / L barrels, sources cut corners, nets circles', node('d:M1').shape === 'round-rectangle' && node('d:M2').shape === 'round-rectangle'
    && node('d:CL').shape === 'barrel' && node('d:VB').shape === 'cut-rectangle' && node('n:out').shape === 'ellipse', JSON.stringify(graph.nodes.map(n => n.shape)));
  check('hint - colour says the kind (nmos and pmos differ; supply, ground, input, output nets differ)', node('d:M1').fill !== node('d:M2').fill
    && new Set(['n:vdd', 'n:0', 'n:in', 'n:out'].map(id => node(id).fill)).size === 4, JSON.stringify([node('d:M1').fill, node('d:M2').fill]));
  check('hint - a link that enters a device at its gate ends in a dot there, at its bulk in a bar, the others in nothing',
    graph.edges.every(e => e.mark === (e.role === 'gate' ? 'circle' : e.role === 'bulk' ? 'tee' : 'none')), JSON.stringify([...new Set(graph.edges.map(e => `${e.role}:${e.mark}`))]));
  check('hint - the PMOS that hangs on the supply stands above the NMOS that stands on ground', node('d:M2').y < node('d:M1').y, `${Math.round(node('d:M2').y)} < ${Math.round(node('d:M1').y)}`);
  check('hint - two devices that share two nets (an inverter) stand above each other, their output net between them', Math.abs(node('d:M2').x - node('d:M1').x) < 2
    && node('n:out').y > node('d:M2').y && node('n:out').y < node('d:M1').y, `${node('d:M2').x} / ${node('d:M1').x}`);
  check('hint - a net that only drives gates stands beside the devices it drives, not in the rows', Math.abs(node('n:in').x - node('d:M1').x) > 80 && node('n:in').y >= node('d:M2').y - 60 && node('n:in').y <= node('d:M1').y + 60, JSON.stringify([node('n:in').x, node('n:in').y]));
  const through = await evaluate(`(() => { const cy = ${CY}, hits = []; cy.edges(':visible').forEach(e => { const a = e.source().position(), b = e.target().position();
    cy.nodes().forEach(n => { if (n.id() === e.source().id() || n.id() === e.target().id()) return; const box = n.boundingBox({ includeLabels: false }), dx = b.x - a.x, dy = b.y - a.y;
      let enter = 0, leave = 1, miss = false;
      for (const [d, low, high] of [[dx, box.x1 - a.x, box.x2 - a.x], [dy, box.y1 - a.y, box.y2 - a.y]]) {
        if (d === 0) { if (low > 0 || high < 0) miss = true; continue; }
        enter = Math.max(enter, Math.min(low / d, high / d)); leave = Math.min(leave, Math.max(low / d, high / d)); }
      if (!miss && enter <= leave) hits.push(e.id() + ' through ' + n.id()); }); }); return hits; })()`);
  check('no link runs through the BOX of a node it does not belong to', through.length === 0, through.join(', '));
  const overlap = (a, b) => a.box.x1 < b.box.x2 && b.box.x1 < a.box.x2 && a.box.y1 < b.box.y2 && b.box.y1 < a.box.y2;
  check('no two nodes overlap', !graph.nodes.some((a, i) => graph.nodes.slice(i + 1).some(b => overlap(a, b))));
  check('everything lies inside the canvas', graph.nodes.every(n => n.box.x1 >= 0 && n.box.y1 >= 0 && n.box.x2 <= graph.width && n.box.y2 <= graph.height), `${graph.width} x ${graph.height}`);
  const box = await evaluate(`(() => { const r = ${DIALOG}.getBoundingClientRect(), c = document.querySelector('.graph-canvas').getBoundingClientRect(); return { width: r.width, height: r.height, canvas: c.width, canvasHeight: c.height }; })()`);
  check('the dialog is large and the drawing has room', box.width > 1500 && box.canvas > 1000 && box.canvasHeight > 600, JSON.stringify(box));
  const line = await evaluate(`[...${DIALOG}.querySelectorAll('.graph-tools input:not([type=checkbox]), .graph-tools select, .graph-tools button')].map(e => { const r = e.getBoundingClientRect(); return { what: e.textContent.trim().slice(0, 14) || e.className || e.tagName, top: Math.round(r.top * 10) / 10, bottom: Math.round(r.bottom * 10) / 10 }; })`);
  check('the toolbar stands on ONE line: the evaluation box, Show, the arrows, the three lists and the layout buttons share their top and bottom edges',
    line.length >= 10 && Math.max(...line.map(e => e.bottom)) - Math.min(...line.map(e => e.bottom)) < 1 && Math.max(...line.map(e => e.top)) - Math.min(...line.map(e => e.top)) < 1, JSON.stringify(line.map(e => [e.what, e.top, e.bottom])));
  const tick = await evaluate(`(() => { const c = ${DIALOG}.querySelector('.graph-bulk').getBoundingClientRect(), b = ${DIALOG}.querySelector('.graph-tools button').getBoundingClientRect(); return Math.abs((c.top + c.bottom) / 2 - (b.top + b.bottom) / 2); })()`);
  check('... and the "Bulk connections" tick box is centred on that line', tick < 1.5, String(tick));
  await shot('graph-1-attention.png', DIALOG);

  // ---- block / head / direction: the lines change, nothing is asked again -----------------------------------------------------------------
  await setSelect(`${DIALOG}.querySelector('select.graph-direction')`, 'to_net'); await sleep(300);
  graph = await drawn();
  check('"what a net takes from its devices": the lines follow, without a new request', asked.length === 1 && WIRES.every(([d, t, , , toNet]) => Math.abs(edgeOf(graph, d, t).attention - toNet[0]) < 1e-9));
  check('a net with a single connection: its 1.0 says nothing, the line is thin and dashed', edgeOf(graph, 'VB', 'P').trivial === 1 && edgeOf(graph, 'VB', 'P').dashed && edgeOf(graph, 'VB', 'P').width === 1
    && graph.edges.filter(e => e.dashed).length === 1, JSON.stringify(edgeOf(graph, 'VB', 'P')));
  await setSelect(`${DIALOG}.querySelector('select.graph-layer')`, '2'); await setSelect(`${DIALOG}.querySelector('select.graph-direction')`, 'to_device'); await setSelect(`${DIALOG}.querySelector('select.graph-head')`, '1'); await sleep(300);
  graph = await drawn();
  check('block 2, head 1: that head\'s values', asked.length === 1 && WIRES.every(([d, t, , toDevice]) => Math.abs(edgeOf(graph, d, t).attention - (toDevice[1] + 0.05)) < 1e-9));
  await setSelect(`${DIALOG}.querySelector('select.graph-head')`, 'mean'); await setSelect(`${DIALOG}.querySelector('select.graph-layer')`, '1'); await sleep(200);

  // ---- bulk ties can be hidden: the picture gets tidier, the numbers stay ----------------------------------------------------------------------
  const BULK = `${DIALOG}.querySelector('.graph-bulk input')`;
  check('bulk ties are hidden at first to keep the graph readable (the tables still list them)', !(await evaluate(`${BULK}.checked`)) && graph.edges.filter(e => !e.visible).map(e => e.id.slice(2, 6)).sort().join() === 'M1.B,M2.B');
  await evaluate(`${BULK}.click()`); await sleep(300);
  check('ticking "Bulk connections" draws them, without a new request', asked.length === 1 && (await drawn()).edges.every(e => e.visible));
  await evaluate(`${BULK}.click()`); await sleep(300);
  graph = await drawn();
  check('... and unticking hides exactly the bulk ties again', asked.length === 1 && graph.edges.filter(e => !e.visible).map(e => e.id.slice(2, 6)).sort().join() === 'M1.B,M2.B', graph.edges.filter(e => !e.visible).map(e => e.id).join());

  // ---- the tables beside the picture ------------------------------------------------------------------------------------------------------
  const groups = await evaluate(`[...${DIALOG}.querySelectorAll('table.graph-groups tbody tr')].map(r => [...r.cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim()))`);
  check('sizes: now, what the policy proposes, what the run tried', groups.length === 2 && groups[0].join('|') === 'wn M1|2 \u00b5m|5.2 \u00b5m z 0.20|2.75 \u00b5m z -0.50' && groups[1].join('|') === 'cl CL|1 pF|2.55 pF z 0.00|2.795 pF z 0.10', JSON.stringify(groups));
  check('how to read attention is said next to the picture', /FIXTURE reading: attention is normalized per RECEIVING node/.test(await evaluate(`${DIALOG}.querySelector('.graph-reading').innerText`)));
  await evaluate(`(${CY}.getElementById('d:M1').emit('tap'), true)`); await sleep(300);
  const around = await evaluate(`[...${DIALOG}.querySelectorAll('table.graph-around tbody tr')].map(r => [...r.cells].map(c => c.textContent.trim()))`);
  check('a clicked device lists what it takes from each connection, with the uniform share', around.map(r => r.join(' ')).join('|') === 'D out 0.400 0.250|G in 0.100 0.250|S 0 0.300 0.250|B 0 0.200 0.250', JSON.stringify(around));
  check('... and the column sums to 1', Math.abs(around.reduce((s, r) => s + Number(r[2]), 0) - 1) < 1e-9);
  await evaluate(`(${CY}.edges().filter(e => e.id().startsWith('c:CL.P#')).emit('tap'), true)`); await sleep(300);
  check('a clicked line shows both directions for every block', (await evaluate(`${DIALOG}.querySelectorAll('table.graph-around tbody tr').length`)) === 4
    && /CL takes from out/.test(await evaluate(`${DIALOG}.querySelector('.graph-picked').innerText`)) && /out takes from CL/.test(await evaluate(`${DIALOG}.querySelector('.graph-picked').innerText`)));
  // The page has ONE number formatter since the review of 2026-09-23 (api.ts `si`): no SI prefix without a physical
  // unit, and the MOCK pseudo-units ("fixture", "count") are not written out - as the corner check always did.
  check('a value without a physical unit gets no SI prefix, and "fixture" is not shown as a unit', (await evaluate(`${DIALOG}.querySelector('table.graph-metrics').innerText.replace(/\\s+/g, ' ').trim()`)) === 'score 0.61', await evaluate(`${DIALOG}.querySelector('table.graph-metrics').innerText`));
  check('on screen only is said', /never written into the run folder/.test(await evaluate(`${DIALOG}.innerText`)));

  // ---- another evaluation = one request --------------------------------------------------------------------------------------------------------
  await evaluate(`[...${DIALOG}.querySelectorAll('button')].find(b => b.textContent === '<').click()`);
  check('"<" asks once for the evaluation before', (await waitAsked(2)) === 2 && asked[1].evaluation === 19 && await until(`/Evaluation 19 of this run/.test(${DIALOG}.innerText)`, 50), JSON.stringify(asked[1]));
  graph = await drawn();
  check('... and the picture follows (other sizes on the device)', graph.nodes.find(n => n.id === 'd:M1').label === 'M1\nnmos\nw 1.9 \u00b5m -> 5.2 \u00b5m', graph.nodes.find(n => n.id === 'd:M1').label);
  await evaluate(`(() => { const i = ${DIALOG}.querySelector('.graph-step input'); i.focus(); i.select(); })()`); await send('Input.insertText', { text: '2' });
  await evaluate(`[...${DIALOG}.querySelectorAll('button')].find(b => b.textContent === 'Show').click()`);
  check('a typed evaluation + Show asks once for it; at the first one "<" is off', (await waitAsked(3)) === 3 && asked[2].evaluation === 2
    && await until(`/Evaluation 2 of this run/.test(${DIALOG}.innerText) && [...${DIALOG}.querySelectorAll('button')].find(b => b.textContent === '<').disabled`, 50), JSON.stringify(asked[2]));

  // ---- a refusal and an encoder without attention, in plain words ------------------------------------------------------------------------------------
  failNext = { message: 'FIXTURE: This run has no archived evaluation 3: it holds 2 to 20.' };
  await evaluate(`[...${DIALOG}.querySelectorAll('button')].find(b => b.textContent === '>').click()`); await waitAsked(4);
  check('a refusal is said as the backend worded it, and the picture stays', await until(`/The view could not be built: FIXTURE: This run has no archived evaluation 3/.test(${DIALOG}.innerText)`, 50) && (await drawn()).nodes.length === 9);
  await evaluate(`${DIALOG}.querySelector('button.dialog-close').click()`);
  check('the close control is a cross at the top right corner, as a browser window has it', await evaluate(`(() => { const b = ${DIALOG}.querySelector('button.dialog-close'), d = ${DIALOG}.getBoundingClientRect(), r = b.getBoundingClientRect(), s = getComputedStyle(b);
    return b.textContent === '\u00d7' && b.getAttribute('aria-label') === 'Close' && s.borderTopStyle === 'none' && d.right - r.right < 24 && r.top - d.top < 24 && ![...${DIALOG}.querySelectorAll('button')].some(x => x.textContent === 'Close'); })()`));
  check('the cross closes the dialog and lets go of the drawing', (await until(`!${DIALOG}.open`, 30)) && !(await evaluate(`!!document.querySelector('.graph-canvas')`)));
  mode = { attention: false };
  await evaluate(`${OPEN}.click()`); await waitAsked(5); await until(`!!(${CY}) && ${CY}.nodes().length > 0`, 80);
  check('an encoder without attention: said in plain words, no block / head boxes', await until(`/FIXTURE: The rgcn encoder has no attention/.test(${DIALOG}.innerText)`, 40) && !(await evaluate(`!!${DIALOG}.querySelector('select.graph-layer')`)));
  graph = await drawn();
  check('... the circuit and the proposed sizes are still drawn, all lines thin and solid', graph.nodes.length === 9 && graph.edges.every(e => e.width === 1 && !e.dashed) && graph.nodes.find(n => n.id === 'd:M1').label.includes('->'));
  await shot('graph-2-no-attention.png', DIALOG);
  await evaluate(`${DIALOG}.querySelector('button.dialog-close').click()`); await until(`!${DIALOG}.open`, 30);
  const quiet = asked.length; await sleep(1500);
  check('closed: nothing is asked, and nothing on a timer', asked.length === quiet);

  // ---- reachable WITHOUT a Mode that loads a model: scratch -> "Look at a saved model" -> the same view ------------------------------------------
  mode = {};
  await setSelect(`[...(${RIGHT}?.querySelectorAll('label') ?? [])].find(l => l.firstChild?.textContent?.trim() === 'Mode')?.querySelector('select')`, 'scratch');
  check('in scratch mode the view is reached through "Look at a saved model"', await until(`!!${RIGHT}.querySelector('button.look-open')`, 40) && !(await evaluate(`!!(${OPEN})`)));
  await evaluate(`${RIGHT}.querySelector('button.look-open').click()`);
  await until(`${RIGHT}.querySelectorAll('button.model-card').length === 1`, 50);
  await evaluate(`${RIGHT}.querySelector('button.model-card').click()`);
  await until(`!!(${OPEN}) && !${OPEN}.disabled`, 40);
  const looked = asked.length;
  await evaluate(`${OPEN}.click()`);
  check('... it asks once for that model\'s latest save and draws it', (await waitAsked(looked + 1)) === looked + 1 && asked[looked].run_dir === RUN && asked[looked].checkpoint_id === 'latest'
    && await until(`!!(${CY}) && ${CY}.nodes().length === 9`, 80), JSON.stringify(asked[looked]));
  await evaluate(`${DIALOG}.querySelector('button.dialog-close').click()`); await until(`!${DIALOG}.open`, 30);
  await setSelect(`[...(${RIGHT}?.querySelectorAll('label') ?? [])].find(l => l.firstChild?.textContent?.trim() === 'Mode')?.querySelector('select')`, 'fine_tune');
  await until(`!!(${OPEN})`, 40);

  // ---- the REAL route of this backend -----------------------------------------------------------------------------------------------------------------
  const realModels = await fetch(new URL('api/runs/models' + (ROOT ? `?output_root=${encodeURIComponent(ROOT)}` : ''), APP));
  const first = realModels.ok ? (await realModels.json()).models[0] : null;
  const real = first && await fetch(new URL('api/runs/model/graph-view', APP), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_dir: first.run_dir, checkpoint_id: first.latest }) });
  if (!first) console.log('SKIP  the real route: this backend has no saved model under its output folder (or is older than the chooser)');
  else if (real.status === 404 || real.status === 405) console.log('SKIP  the real /api/runs/model/graph-view route: this backend is older than it - restart it');
  else if (real.status === 409) console.log(`SKIP  the real route answered 409 for the first model: ${(await real.json()).detail?.message}`);
  else {
    const expected = await real.json();
    canned = false; mode = {};
    await evaluate(`[...${RIGHT}.querySelectorAll('button')].find(b => b.textContent.trim() === 'Refresh list').click()`);
    const CARD = `[...${RIGHT}.querySelectorAll('button.model-card')].find(b => b.title === ${JSON.stringify(first.run_dir)})`;
    check('against the real route: the first real model can be chosen', (await until(`!!(${CARD})`, 80)) && (await evaluate(`(${CARD}.click(), true)`)) && await until(`${CARD}.getAttribute('aria-checked') === 'true' && !${OPEN}.disabled`, 60), first.run_dir);
    await sleep(600); await evaluate(`${OPEN}.click()`);
    check(`... its circuit is drawn: ${expected.devices.length} devices + ${expected.nets.length} nets, ${expected.connections.length} connections`,
      await until(`!!(${CY}) && ${CY}.nodes().length === ${expected.devices.length + expected.nets.length} && ${CY}.edges().length === ${expected.connections.length}`, 100));
    graph = await drawn();
    const sized = expected.groups.filter(g => g.mutable && g.policy_value != null).flatMap(g => g.members.map(m => m.device));
    check('... every device the real policy sizes carries "now -> proposed"', sized.length > 0 && sized.every(d => graph.nodes.find(n => n.id === `d:${d}`).label.includes('->')), sized.join());
    const expectTrivial = expected.connections.filter(c => c.attention[0]?.to_device_uniform === 1).length;
    check(`... attention as the real route says (${expected.attention.available ? `${expected.attention.layers} block(s), ${expected.attention.heads} heads` : 'none'})`,
      !expected.attention.available || expected.connections.every(c => { const e = graph.edges.find(x => x.id === `c:${c.id}`); return Math.abs(e.attention - c.attention[0].to_device) < 1e-6; })
      && graph.edges.filter(e => e.dashed).length === expectTrivial);
    check('... nothing overlaps and everything is inside the canvas', !graph.nodes.some((a, i) => graph.nodes.slice(i + 1).some(b => overlap(a, b)))
      && graph.nodes.every(n => n.box.x1 >= 0 && n.box.y1 >= 0 && n.box.x2 <= graph.width && n.box.y2 <= graph.height));
    await shot('graph-3-real.png', DIALOG);
    await evaluate(`${DIALOG}.querySelector('button.dialog-close').click()`);
  }

  reportRefused(refused, NEVER_ASKED_OR_SAVED);
  check('no console exception', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
