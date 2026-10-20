// Circuit graph attention painting, against the installed Cytoscape in headless mode with styles enabled.
// Extract the actual private helpers with TypeScript's parser and transpile in memory: no production build,
// browser, backend, simulation, or files in a run. Synthetic fixtures exist only in memory.
// WSL: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/graph_paint_check.mjs)"
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const cytoscape = require('cytoscape');
const path = fileURLToPath(new URL('../src/panels/CircuitGraphView.tsx', import.meta.url));
const source = readFileSync(path, 'utf8');
const parsed = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function statement(name) {
  const found = parsed.statements.filter(node =>
    ts.isFunctionDeclaration(node) ? node.name?.text === name : ts.isVariableStatement(node)
      && node.declarationList.declarations.some(d => ts.isIdentifier(d.name) && d.name.text === name));
  assert.equal(found.length, 1, `One actual source declaration for ${name}`);
  return found[0].getText(parsed);
}
// Independent original paint body; both versions use the unchanged production attention/weight helpers.
const originalPaint = `function paintBefore(cy, view, layer, head, direction, scope, query) {
  const weights = nodeWeights(view, scope, layer, head, query);
  const peak = Math.max(...weights, 1e-12);
  const queryId = query || view.node_attention?.nodes?.[0];
  cy.nodes().data({ focus: 0, query: 0 });
  (view.node_attention?.nodes ?? []).forEach((id, i) => cy.getElementById(id).data({
    focus: scope !== 'local' ? 1 : 0, focusWeight: (weights[i] ?? 0) / peak, query: scope === 'global' && id === queryId ? 1 : 0,
  }));
  cy.batch(() => view.connections.forEach(c => {
    const a = attentionOf(c, scope === 'local' ? layer : 0, head, direction);
    cy.getElementById('c:' + c.id).data({ attention: a.value ?? 0, trivial: a.trivial ? 1 : 0 });
  }));
}`;
const compiled = ts.transpileModule([
  ...['attentionOf', 'nodeWeights', 'graphStyle', 'paint'].map(statement), originalPaint,
  'exports.paint = paint; exports.before = paintBefore; exports.graphStyle = graphStyle;',
].join('\n'), {
  fileName: 'graph-paint-helpers.ts', reportDiagnostics: true,
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
});
assert.equal(compiled.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error).length ?? 0, 0);
const moduleExports = {};
// graphStyle reads CSS palette values only; its documented fallback palette needs no DOM or browser.
new Function('exports', 'getComputedStyle', compiled.outputText)(moduleExports, () => ({ getPropertyValue: () => '' }));
const { paint, before, graphStyle } = moduleExports;
const styles = graphStyle({});

function fixture(count = 6) {
  const nodes = Array.from({ length: count }, (_, i) => `${i % 2 ? 'n' : 'd'}:fixture_${i}`);
  const connections = nodes.map((id, i) => ({
    id: `fixture_${i}`, source: id, target: nodes[(i + 1) % count], role: i === 0 ? 'bulk' : i % 2 ? 'gate' : 'drain',
    attention: [0, 1].map(layer => {
      const toDevice = [0.15 + (i + layer) % 4 / 10, 0.45 + (i + layer) % 4 / 10];
      const toNet = [0.1 + (i + layer) % 3 / 10, 0.5 + (i + layer) % 3 / 10];
      return { to_device: (toDevice[0] + toDevice[1]) / 2, to_device_heads: toDevice, to_device_uniform: i % 3 ? 0.25 : 1,
        to_net: (toNet[0] + toNet[1]) / 2, to_net_heads: toNet, to_net_uniform: i % 2 ? 1 : 0.5 };
    }),
  }));
  const groups = ['fixture_group_a', 'fixture_group_b'];
  const layer = queryCount => [0, 1].map(head => Array.from({ length: queryCount }, (_, q) => {
    const row = nodes.map((_, i) => 1 + (i + q + head) % 7);
    const total = row.reduce((sum, v) => sum + v, 0);
    return row.map(v => v / total);
  }));
  return { origin: 'synthetic', provenance: 'mock', connections,
    node_attention: { nodes, groups, global_layers: [layer(nodes.length), layer(nodes.length)],
      group_layers: [layer(groups.length), layer(groups.length)] } };
}

function createGraph(view) {
  const ids = view.node_attention?.nodes ?? [...new Set(view.connections.flatMap(c => [c.source, c.target]))];
  const nodes = [...ids, 'n:outside_attention'].map((id, i) => ({ data: { id, type: id.startsWith('d:') ? 'device' : 'net',
    family: 'transistor', colour: '#dbeafe', label: id, role: 'normal', sized: i === 0 ? 1 : 0,
    focus: 1, focusWeight: 0.7, query: 1 }, position: { x: 20 + i * 31, y: 15 + i % 4 * 29 } }));
  const edges = view.connections.map(c => ({ data: { id: `c:${c.id}`, source: c.source, target: c.target,
    role: c.role, label: c.role, attention: 0.8, trivial: 1 } }));
  const cy = cytoscape({ headless: true, styleEnabled: true, elements: [...nodes, ...edges],
    style: structuredClone(styles), layout: { name: 'preset' } });
  cy.getElementById(ids[0] ?? 'n:outside_attention').select();
  cy.edges('[role = "bulk"]').addClass('hidden');
  return cy;
}

const nodeProperties = ['background-color', 'border-color', 'border-width', 'width', 'height', 'display'];
const edgeProperties = ['line-color', 'line-style', 'width', 'display', 'source-arrow-shape'];
function snapshot(cy) {
  return cy.elements().map(ele => ({ id: ele.id(), data: structuredClone(ele.data()), position: { ...ele.position() },
    selected: ele.selected(), classes: ele.classes(),
    style: Object.fromEntries((ele.isNode() ? nodeProperties : edgeProperties).map(p => [p, ele.style(p)])) }));
}
function observe(cy) {
  const renderer = cy.renderer(), notify = renderer.notify;
  const trace = { styleNotifications: 0, styleEvents: 0, dataEvents: [] };
  renderer.notify = function(name, ...rest) {
    if (name === 'style') trace.styleNotifications++;
    return notify.call(this, name, ...rest);
  };
  cy.on('style', () => trace.styleEvents++);
  cy.on('data', event => trace.dataEvents.push({ id: event.target.id(), data: structuredClone(event.target.data()) }));
  return { trace, reset: () => { trace.styleNotifications = 0; trace.styleEvents = 0; trace.dataEvents = []; } };
}

let comparisons = 0, checks = 0;
function compareSequence(view, cases, outerBatch = false) {
  const old = createGraph(view), current = createGraph(view);
  const oldSeen = observe(old), nowSeen = observe(current);
  const records = [];
  try {
    for (const args of cases) {
      const originalPositions = current.nodes().map(n => ({ id: n.id(), position: { ...n.position() }, selected: n.selected(), classes: n.classes() }));
      oldSeen.reset(); nowSeen.reset();
      if (outerBatch) { old.startBatch(); current.startBatch(); }
      before(old, view, ...args);
      paint(current, view, ...args);
      if (outerBatch) {
        assert.equal(nowSeen.trace.styleNotifications, 0, 'Nested paint does not flush its caller\'s batch');
        old.endBatch(); current.endBatch();
      }
      const counts = { before: { styleNotifications: oldSeen.trace.styleNotifications, styleEvents: oldSeen.trace.styleEvents },
        after: { styleNotifications: nowSeen.trace.styleNotifications, styleEvents: nowSeen.trace.styleEvents } };
      assert.deepEqual(nowSeen.trace.dataEvents, oldSeen.trace.dataEvents, `Same data mutations/events: ${JSON.stringify(args)}`);
      assert.deepEqual(snapshot(current), snapshot(old), `Same data, computed styles and state: ${JSON.stringify(args)}`);
      assert.deepEqual(current.nodes().map(n => ({ id: n.id(), position: { ...n.position() }, selected: n.selected(), classes: n.classes() })), originalPositions);
      assert.equal(current.batching(), false);
      assert.ok(counts.after.styleNotifications <= counts.before.styleNotifications);
      records.push({ args, ...counts, dataEvents: nowSeen.trace.dataEvents.length });
      comparisons++;
    }
    return records;
  } finally { old.destroy(); current.destroy(); }
}
function check(name, run) {
  run(); checks++;
  console.log(`PASS ${name}`);
}

const view = fixture();
check('local attention: both directions, mean/specific/missing heads and layers', () => {
  const cases = [];
  for (const direction of ['to_device', 'to_net']) for (const layer of [1, 2, 3]) for (const head of ['mean', '1', '2', '3']) {
    cases.push([layer, head, direction, 'local', '']);
  }
  compareSequence(view, cases);
});
check('global and group attention: query selection/fallback, all heads and layer changes', () => {
  const cases = [];
  for (const scope of ['global', 'group']) for (const query of ['', 'missing', scope === 'global' ? view.node_attention.nodes[2] : view.node_attention.groups[1]]) {
    for (const layer of [1, 2, 3]) for (const head of ['mean', '1', '2', '3']) cases.push([layer, head, 'to_device', scope, query]);
  }
  compareSequence(view, cases);
});
check('switching scopes preserves reset behavior, node positions, selection and hidden bulk edges', () => {
  compareSequence(view, [[1, 'mean', 'to_device', 'global', view.node_attention.nodes[2]],
    [2, '2', 'to_net', 'group', view.node_attention.groups[1]], [1, '1', 'to_net', 'local', ''],
    [1, '2', 'to_device', 'global', ''], [2, 'mean', 'to_device', 'local', '']]);
});
check('missing edge attention, absent dense attention, empty layers and all-zero weights', () => {
  const absent = structuredClone(view);
  delete absent.node_attention;
  absent.connections.forEach(c => { delete c.attention; });
  compareSequence(absent, [[1, 'mean', 'to_device', 'local', ''], [1, '1', 'to_net', 'global', '']]);
  const empty = structuredClone(view);
  empty.node_attention.global_layers = [];
  empty.node_attention.group_layers = [];
  empty.connections.forEach(c => { c.attention = [{ to_net: 0.2, to_net_heads: [0.1, 0.3], to_net_uniform: 1 }]; });
  compareSequence(empty, [[1, 'mean', 'to_device', 'global', ''], [1, '1', 'to_device', 'group', ''],
    [1, 'mean', 'to_device', 'local', ''], [1, '2', 'to_net', 'local', '']]);
  const zero = structuredClone(view);
  zero.node_attention.global_layers = zero.node_attention.global_layers.map(heads => heads.map(rows => rows.map(row => row.map(() => 0))));
  compareSequence(zero, [[1, 'mean', 'to_device', 'global', ''], [2, '1', 'to_net', 'global', 'missing']]);
});
check('empty graph attention and nested caller batches preserve behavior', () => {
  compareSequence({ origin: 'synthetic', provenance: 'mock', connections: [] }, [[1, 'mean', 'to_device', 'local', '']]);
  compareSequence(view, [[1, 'mean', 'to_device', 'global', ''], [1, 'mean', 'to_net', 'local', '']], true);
});
let workCounts;
check('128-node synthetic view emits one renderer style notification per paint', () => {
  const large = fixture(128);
  const records = compareSequence(large, [[1, 'mean', 'to_device', 'global', ''], [2, '2', 'to_net', 'group', 'fixture_group_b'],
    [1, 'mean', 'to_device', 'local', '']]);
  for (const record of records) {
    assert.equal(record.before.styleNotifications, 130);
    assert.equal(record.after.styleNotifications, 1);
  }
  workCounts = { attentionNodes: 128, totalNodes: 129, edges: 128, paints: records };
});
console.log(JSON.stringify({ checks, comparisons, sourceSha256: createHash('sha256').update(source).digest('hex'),
  node: process.version, typescript: ts.version, cytoscape: cytoscape.version, synthetic: workCounts,
  timingMeasured: false, browserUsed: false, backendContacted: false }, null, 2));
