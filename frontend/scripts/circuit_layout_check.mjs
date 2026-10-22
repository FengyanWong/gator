// Deterministic circuit-layout checks. Transpile the actual source in memory with installed TypeScript; no browser,
// backend, production build, simulation, or timing measurement. All graphs are synthetic and remain in memory.
// Default oracle restores the few original source chunks below, with exact-match guards. To verify against the
// archived independent original, add --before <path-to-circuitLayout.before.ts> (ordinary Windows path with Windows Node).
// WSL: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/circuit_layout_check.mjs)"
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url), ts = require('typescript');
const path = fileURLToPath(new URL('../src/panels/circuitLayout.ts', import.meta.url));
const source = readFileSync(path, 'utf8');
function replaceOne(text, from, to) {
  assert.equal(text.split(from).length - 1, 1, `One exact source chunk: ${from.slice(0, 100)}`);
  return text.replace(from, to);
}
function withoutPreparedNeighbors(text) {
  text = replaceOne(text, `  // Row membership and link weights stay fixed through the sweeps; only their neighbours' x positions change.
  const across = Object.fromEntries(order.map(id => {
    const others = (links[id] ?? []).filter(l => rowOf[l.to] !== rowOf[id]);
    return [id, { others, total: others.reduce((s, l) => s + l.weight, 0) }] as const;
  }));
`, '');
  return replaceOne(text, '        const { others, total } = across[id];',
    `        const others = (links[id] ?? []).filter(l => rowOf[l.to] !== r);
        const total = others.reduce((s, l) => s + l.weight, 0);`);
}
function withoutKeptPositionKeys(text) {
  text = replaceOne(text, `  // Every node is placed now. Moves replace coordinates, so keep the keys and read each node's current position.
  const placedIds = Object.keys(positions);
`, '');
  text = replaceOne(text,
    '      if (!placedIds.some(other => { const o = positions[other]; return other !== id && Math.abs(o.x - at.x) < 100 && Math.abs(o.y - at.y) < 50; })) { positions[id] = at; return true; }',
    '      if (!Object.entries(positions).some(([other, o]) => other !== id && Math.abs(o.x - at.x) < 100 && Math.abs(o.y - at.y) < 50)) { positions[id] = at; return true; }');
  return replaceOne(text, '      for (const id of placedIds) {', '      for (const id of Object.keys(positions)) {');
}
const restored = withoutPreparedNeighbors(withoutKeptPositionKeys(source));
// run_checks.mjs passes every check one argument, the folder for its evidence. This check writes none, so a lone existing
// folder is set aside: the batch reported the check failed while it passed alone. Any other argument is still refused.
const given = process.argv.slice(2);
const args = given.length === 1 && statSync(given[0], { throwIfNoEntry: false })?.isDirectory() ? [] : given;
assert.ok(!args.length || args.length === 2 && args[0] === '--before', 'Usage: circuit_layout_check.mjs [--before original.ts | <evidence folder>]');
const beforeSource = args.length ? readFileSync(args[1], 'utf8') : restored;
assert.equal(restored, beforeSource, 'Restored source matches the separately archived original when supplied');
const variants = { before: beforeSource, neighborsOnly: withoutKeptPositionKeys(source),
  positionsOnly: withoutPreparedNeighbors(source), both: source };

const blankCounts = () => ({ neighborFilters: 0, neighborLinks: 0, weightTotals: 0, weightTerms: 0,
  keyEnumerations: 0, keysAllocated: 0, entryEnumerations: 0, entryPairsAllocated: 0 });
function load(code, instrument = false) {
  const counts = blankCounts();
  if (instrument) {
    const filters = [...code.matchAll(/\(links\[id\] \?\? \[\]\)\.filter\(l => rowOf\[l\.to\] !== (r|rowOf\[id\])\)/g)];
    assert.equal(filters.length, 1);
    const right = filters[0][1];
    code = replaceOne(code, filters[0][0],
      `(__counts.neighborFilters++, (links[id] ?? []).filter(l => (__counts.neighborLinks++, rowOf[l.to] !== ${right})))`);
    code = replaceOne(code, 'others.reduce((s, l) => s + l.weight, 0)',
      '(__counts.weightTotals++, others.reduce((s, l) => (__counts.weightTerms++, s + l.weight), 0))');
    code = code.replaceAll('Object.keys(positions)', '__positionKeys(positions)')
      .replaceAll('Object.entries(positions)', '__positionEntries(positions)');
  }
  const compiled = ts.transpileModule(code, { fileName: path, reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } });
  assert.equal(compiled.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error).length ?? 0, 0);
  assert.ok(!compiled.outputText.includes('require('), 'Layout helpers need no runtime imports');
  const out = {};
  new Function('exports', '__counts', '__positionKeys', '__positionEntries', compiled.outputText)(out, counts,
    positions => { const keys = Object.keys(positions); counts.keyEnumerations++; counts.keysAllocated += keys.length; return keys; },
    positions => { const entries = Object.entries(positions); counts.entryEnumerations++; counts.entryPairsAllocated += entries.length; return entries; });
  return { layout: out.hintedLayout, counts };
}
const loaded = Object.fromEntries(Object.entries(variants).map(([name, code]) => [name, load(code).layout]));

function graph() { return { origin: 'synthetic', provenance: 'mock', devices: [], nets: [], connections: [] }; }
function net(view, id, roles = ['normal']) {
  if (!view.nets.some(n => n.id === id)) view.nets.push({ id, roles });
  return id;
}
function device(view, id, kind, terminals, family) {
  view.devices.push({ id, kind, ...(family ? { family } : {}) });
  terminals.forEach(([terminal, name, role = terminal]) => {
    net(view, name);
    view.connections.push({ id: `${id}.${terminal}`, device: id, net: name, terminal, role });
  });
}
function rails(view) { net(view, 'vdd', ['normal', 'supply']); net(view, '0', ['ground']); }
function inverterChain(size, { ring = false, capacitors = true, pdk = false } = {}) {
  const view = graph(); rails(view);
  for (let i = 0; i < size; i++) {
    const input = i ? `out_${i - 1}` : ring ? `out_${size - 1}` : 'in', output = `out_${i}`;
    device(view, `stage_${i}/P`, pdk ? 'fixture:pmodel' : 'pmos',
      [['D', output, 'drain'], ['G', input, 'gate'], ['S', 'vdd', 'source'], ['B', 'vdd', 'bulk']], pdk ? 'pmos' : undefined);
    device(view, `stage_${i}/N`, pdk ? 'fixture:nmodel' : 'nmos',
      [['D', output, 'drain'], ['G', input, 'gate'], ['S', '0', 'source'], ['B', '0', 'bulk']], pdk ? 'nmos' : undefined);
    if (capacitors) device(view, `load_${i}`, 'capacitor', [['p', output], ['n', '0']]);
  }
  if (!ring) device(view, 'input_source', 'vsource', [['p', 'in'], ['n', '0']]);
  device(view, 'supply_source', 'vsource', [['p', 'vdd'], ['n', '0']]);
  return view;
}
function passiveLadder(size, extra = true) {
  const view = graph(); rails(view);
  for (let i = 0; i < size; i++) {
    device(view, `R${i}`, 'resistor', [['p', i ? `tap_${i - 1}` : 'vdd'], ['n', i === size - 1 ? '0' : `tap_${i}`]]);
    if (extra && i < size - 1 && i % 2 === 0) device(view, `C${i}`, 'capacitor', [['p', `tap_${i}`], ['n', '0']]);
  }
  if (extra) {
    device(view, 'cross', 'resistor', [['p', 'vdd'], ['n', 'tap_0']]);
    device(view, 'bias_source', 'isource', [['p', 'tap_0'], ['n', '0']]);
  }
  return view;
}
const empty = graph(), onlyRails = graph(); rails(onlyRails);
const withoutGround = passiveLadder(3); withoutGround.nets.find(n => n.id === '0').roles = ['normal'];
const withoutSupply = passiveLadder(3); withoutSupply.nets.find(n => n.id === 'vdd').roles = ['normal'];
const disconnected = inverterChain(2);
device(disconnected, 'island/R', 'resistor', [['p', 'island/a'], ['n', 'island/b']]);
net(disconnected, 'isolated_net');
const bipolar = passiveLadder(4);
device(bipolar, 'Q', 'fixture:bipolar', [['C', 'tap_0', 'collector'], ['B', 'bias', 'base'], ['E', '0', 'emitter']], 'bjt');
device(bipolar, 'bias_drive', 'vsource', [['p', 'bias'], ['n', '0']]);
const repeatedPorts = inverterChain(2);
device(repeatedPorts, 'diode_connected', 'nmos', [['D', 'out_0', 'drain'], ['G', 'out_0', 'gate'], ['S', '0', 'source'], ['B', '0', 'bulk']]);
const manyRails = inverterChain(3);
net(manyRails, 'vdd2', ['supply']); net(manyRails, 'gnd2', ['ground']);
device(manyRails, 'extra_rail_source', 'vsource', [['p', 'vdd2'], ['n', 'gnd2']]);
device(manyRails, 'bridge', 'resistor', [['p', 'vdd2'], ['n', 'out_1']]);
const fixed = [empty, onlyRails, withoutGround, withoutSupply, passiveLadder(1), passiveLadder(8), inverterChain(1),
  inverterChain(3), inverterChain(5, { ring: true }), inverterChain(3, { pdk: true }), disconnected, bipolar, repeatedPorts, manyRails];

let checks = 0, fixtures = 0, differentialComparisons = 0;
function check(name, run) { run(); checks++; console.log(`PASS ${name}`); }
function compare(view) {
  const input = JSON.stringify(view), expected = loaded.before(view);
  for (const name of ['neighborsOnly', 'positionsOnly', 'both']) {
    const actual = loaded[name](view);
    assert.deepEqual(actual, expected, `Exact coordinates: ${name}`);
    if (expected) {
      assert.deepEqual(Object.keys(actual), Object.keys(expected), `Coordinate property order: ${name}`);
      for (const point of Object.values(actual)) assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y));
    }
    assert.equal(JSON.stringify(actual), JSON.stringify(expected), `Ordered coordinate serialization: ${name}`);
    assert.equal(JSON.stringify(view), input, 'Input graph was not modified');
    differentialComparisons++;
  }
  fixtures++;
  return expected;
}
check('rails, sources, capacitors, families, disconnected nodes and repeated terminal connections preserve complete layouts', () => {
  fixed.forEach(compare);
  for (const view of [empty, withoutGround, withoutSupply]) assert.equal(loaded.both(view), null);
  assert.deepEqual(Object.keys(loaded.both(onlyRails)), ['n:vdd', 'n:0']);
});
check('160 deterministic generated/reordered circuits match the original coordinates and property order', () => {
  let seed = 0x7356;
  const next = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed; };
  const shuffle = list => { for (let i = list.length - 1; i > 0; i--) { const j = next() % (i + 1); [list[i], list[j]] = [list[j], list[i]]; } };
  for (let i = 0; i < 160; i++) {
    const size = 2 + next() % 9;
    const view = i % 3 === 0 ? passiveLadder(size, !!(i % 2)) : inverterChain(size, { ring: i % 3 === 1, capacitors: !!(i % 2), pdk: !!(i % 5) });
    shuffle(view.devices); shuffle(view.nets); shuffle(view.connections);
    compare(view);
  }
});
check('successive calls use current graph contents and return independent position objects', () => {
  const view = inverterChain(3), first = loaded.both(view);
  const again = compare(view);
  assert.deepEqual(first, again);
  for (const key of Object.keys(first)) assert.notStrictEqual(first[key], again[key]);
  device(view, 'added_load', 'capacitor', [['p', 'out_1'], ['n', 'vdd']]);
  const changed = compare(view);
  assert.ok('d:added_load' in changed);
  assert.ok(!('d:added_load' in first));
});
let operationCounts;
check('instrumented real source isolates neighbor preparation and position-enumeration reductions', () => {
  const view = inverterChain(12, { ring: true }), expected = loaded.before(view);
  operationCounts = {};
  for (const [name, code] of Object.entries(variants)) {
    const measured = load(code, true);
    assert.deepEqual(measured.layout(view), expected, `Instrumentation preserves ${name} layout`);
    operationCounts[name] = measured.counts;
  }
  const { before, neighborsOnly, positionsOnly, both } = operationCounts;
  for (const key of ['neighborFilters', 'neighborLinks', 'weightTotals', 'weightTerms']) {
    assert.ok(both[key] > 0);
    assert.equal(before[key], 8 * both[key], `Eight sweeps: ${key}`);
    assert.equal(neighborsOnly[key], both[key]);
    assert.equal(positionsOnly[key], before[key]);
  }
  for (const key of ['keyEnumerations', 'keysAllocated', 'entryEnumerations', 'entryPairsAllocated']) {
    assert.equal(neighborsOnly[key], before[key]);
    assert.equal(positionsOnly[key], both[key]);
    assert.ok(both[key] < before[key], `Less coordinate enumeration: ${key}`);
  }
  assert.equal(both.keyEnumerations, 1);
});
const sha256 = text => createHash('sha256').update(text).digest('hex');
console.log(JSON.stringify({ checks, fixtures, differentialComparisons,
  originalSource: args.length ? 'independent --before file; matched reconstructed chunks' : 'original chunks reconstructed with exact-match guards',
  sourceHashes: Object.fromEntries(Object.entries(variants).map(([name, code]) => [name, sha256(code)])),
  node: process.version, typescript: ts.version, synthetic: { origin: 'synthetic', provenance: 'mock',
    measuredFixture: '12-stage inverter ring with load capacitors and a supply source', operationCounts },
  timingMeasured: false, browserUsed: false, backendContacted: false }, null, 2));
