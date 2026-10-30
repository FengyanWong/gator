// Pure checks of the actual editor rules, transpiled in memory with installed TypeScript. No browser, backend, build,
// timing, or saved task writes. All configurations and unit forms below are synthetic/mock and remain in memory.
// The default oracle restores the original few chunks with exact-match guards, so a clean checkout needs no local files.
// Optional independent archive: --before <path-to-editorRules.before.ts>.
// WSL: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/editor_renames_check.mjs)"
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url), ts = require('typescript');
const sourcePath = fileURLToPath(new URL('../src/panels/editorRules.ts', import.meta.url));
const unitsPath = fileURLToPath(new URL('../src/units.ts', import.meta.url));
const source = readFileSync(sourcePath, 'utf8'), unitsSource = readFileSync(unitsPath, 'utf8');
function replaceOne(text, from, to) {
  assert.equal(text.split(from).length - 1, 1, `One exact source chunk: ${from.slice(0, 100)}`);
  return text.replace(from, () => to);
}
const afterHelper = "const equationRenamer = (from: string, to: string) => {\n  // An edit may touch many Specs. Compile once for this rename, only when a string equation needs it.\n  let pattern: RegExp | undefined;\n  return (equation: string) => equation.replace(pattern ??= new RegExp(`(?<![A-Za-z0-9_.])${from.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}(?![A-Za-z0-9_])`, 'g'), to);\n};";
const beforeHelper = "const renameInEquation = (equation: string, from: string, to: string) =>\n  equation.replace(new RegExp(`(?<![A-Za-z0-9_.])${from.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}(?![A-Za-z0-9_])`, 'g'), to);";
let restored = replaceOne(source, afterHelper, beforeHelper);
// The original oracle used an extensionless import; the rules now also load directly under Node's type stripping.
restored = replaceOne(restored, "from '../units.ts';", "from '../units';");
restored = replaceOne(restored,
  '  const renames: ((equation: string) => string)[] = [], moves: [string, string][] = [];',
  '  const renames: [string, string][] = [], moves: [string, string][] = [];');
restored = replaceOne(restored,
  'renames.push(equationRenamer(String(r.measurement_id), row.measurement_id));',
  'renames.push([String(r.measurement_id), row.measurement_id]);');
restored = replaceOne(restored, 'renames.reduce((e, rename) => rename(e), t.equation)',
  'renames.reduce((e, [from, to]) => renameInEquation(e, from, to), t.equation)');
// run_checks.mjs passes every check one argument, the folder for its evidence. This check writes none, so a lone existing
// folder is set aside: the batch reported the check failed while it passed alone. Any other argument is still refused.
const given = process.argv.slice(2);
const args = given.length === 1 && statSync(given[0], { throwIfNoEntry: false })?.isDirectory() ? [] : given;
assert.ok(!args.length || args.length === 2 && args[0] === '--before', 'Usage: editor_renames_check.mjs [--before original.ts | <evidence folder>]');
const beforeSource = args.length ? readFileSync(args[1], 'utf8') : restored;
assert.equal(restored, beforeSource, 'Restored oracle matches the independent original when supplied');

function compiled(code, path) {
  const result = ts.transpileModule(code, { fileName: path, reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } });
  assert.equal(result.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error).length ?? 0, 0);
  return result.outputText;
}
const forms = { origin: 'synthetic', provenance: 'mock', spellings: {
  V: ['V', 1, 0], mV: ['V', 0.001, 0], A: ['A', 1, 0], uA: ['A', 0.000001, 0], W: ['W', 1, 0],
  m: ['m', 1, 0], um: ['m', 0.000001, 0], count: ['count', 1, 0], dB: ['dB', 1, 0], deg: ['deg', 1, 0],
}, kinds: { w: 'm', l: 'm', nf: 'count' } };
function load(code, before, rejectPatterns = false) {
  const counts = { constructions: 0 }, patterns = [];
  const countedRegExp = new Proxy(RegExp, { construct(target, args) {
    counts.constructions++;
    if (rejectPatterns) throw new Error('Synthetic RegExp construction failure');
    const pattern = Reflect.construct(target, args);
    patterns.push(pattern);
    return pattern;
  } });
  const units = {};
  new Function('exports', compiled(unitsSource, unitsPath))(units);
  units.setUnitForms(forms);
  const out = {}, helper = before
    ? '(from: string, to: string) => (equation: string) => renameInEquation(equation, from, to)' : 'equationRenamer';
  const moduleSource = compiled(code + '\nexport const __renamer = ' + helper + ';\n', sourcePath);
  new Function('exports', 'require', 'RegExp', moduleSource)(out, name => {
    assert.ok(name === '../units' || name === '../units.ts', 'Only the local pure units module may load');
    return units;
  }, countedRegExp);
  return { ...out, counts, patterns };
}
const old = load(beforeSource, true), current = load(source, false);
const sections = ['parameters', 'measurements', 'targets'];
const config = (measurements = [], targets = [], parameters = []) =>
  ({ origin: 'synthetic', provenance: 'mock', parameters, measurements, targets, preserved: { text: 'unchanged' } });
const probe = (id, extra = {}) => ({ measurement_id: id, result_source: 'ade_output', source_name: id, unit: 'V', ...extra });
const spec = (equation, extra = {}) => ({ target_id: 'spec', equation, unit: 'V', constraint: '>=', lower: 2, ...extra });
function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value)) freeze(item);
  }
  return value;
}
function references(value, path = '$', found = new Map()) {
  if (!value || typeof value !== 'object' || found.has(value)) return found;
  found.set(value, path);
  for (const [key, item] of Object.entries(value)) references(item, `${path}.${key}`, found);
  return found;
}
function identityOf(value, inputs, path = '$', out = []) {
  if (!value || typeof value !== 'object') return out;
  if (inputs.has(value)) out.push([path, inputs.get(value)]);
  for (const [key, item] of Object.entries(value)) identityOf(item, inputs, `${path}.${key}`, out);
  return out;
}
let comparisons = 0, checks = 0;
function differential(label, tab, c, entries) {
  freeze(c);
  entries.forEach(([, fields]) => freeze(fields));
  const changes = new Map(entries), inputSnapshot = structuredClone(c), changesSnapshot = structuredClone(entries);
  const refs = references(c);
  entries.forEach(([index, fields]) => references(fields, `changes.${index}`, refs));
  const expected = old.withFollowers(tab, c, changes), actual = current.withFollowers(tab, c, changes);
  assert.deepEqual(actual, expected, `${label}: full result`);
  assert.equal(JSON.stringify(actual), JSON.stringify(expected), `${label}: property order`);
  assert.deepEqual(identityOf(actual, refs), identityOf(expected, refs), `${label}: input reference reuse`);
  assert.deepEqual(c, inputSnapshot, `${label}: configuration immutable`);
  assert.deepEqual([...changes], changesSnapshot, `${label}: changes immutable`);
  comparisons++;
  return actual;
}
function check(label, run) { run(); checks++; console.log(`PASS ${label}`); }

check('typed, pasted and filled renames preserve identifier boundaries and source row references', () => {
  const c = config([probe('m_gain'), probe('m_other'), probe('m_unedited')],
    [spec('m_gain + m_gain'), spec('xm_gain + m_gain2 + m_gain_ + .m_gain + m_gain.x + (m_gain)'),
      spec(''), spec(null), spec(7), spec({ expression: 'm_gain' })]);
  const actual = differential('boundaries', 'measurements', c, [[0, { source_name: 'new_gain' }], [1, { source_name: 'other_new' }]]);
  assert.equal(actual.targets[0].equation, 'm_new_gain + m_new_gain');
  assert.equal(actual.targets[1].equation, 'xm_gain + m_gain2 + m_gain_ + .m_gain + m_new_gain.x + (m_new_gain)');
  assert.equal(actual.measurements[2], c.measurements[2]);
  assert.equal(actual.targets[3], c.targets[3]);
  assert.notEqual(actual.targets[2], c.targets[2], 'Even an unchanged string equation keeps the old cloned-row behavior');
});
check('chains, duplicate IDs, swaps, escaped legacy IDs and rename/unit order remain sequential', () => {
  const chains = config([probe('m_a'), probe('m_b'), probe('m_a')], [spec('m_a + m_b'), spec('m_a')]);
  const actual = differential('chains', 'measurements', chains,
    [[0, { source_name: 'b' }], [1, { source_name: 'c' }], [2, { source_name: 'd' }]]);
  assert.equal(actual.targets[0].equation, 'm_c + m_c');
  differential('swap', 'measurements', config([probe('m_a'), probe('m_b')], [spec('m_a + m_b')]),
    [[0, { source_name: 'b' }], [1, { source_name: 'a' }]]);
  const legacy = ['old.[a]+(b)*?^$|\\id', 'old/name', '123', 'µgain', 'constructor', '__proto__'];
  differential('escaped IDs', 'measurements', config(legacy.map(id => probe(id)),
    legacy.map(id => spec(`${id} + (${id}) + x${id} + .${id}`))),
  legacy.map((_, i) => [i, { source_name: `new_${i}` }]));
  const moved = differential('moves and renames', 'measurements', config([probe('m_old')],
    [spec('m_old'), spec('m_new'), spec('m_old + m_new')]),
  [[0, { source_name: 'new', unit: 'A' }]]);
  assert.equal(moved.targets[0].unit, 'V', 'Unit moves still match the original ID after equations rename');
  const units = differential('units only', 'measurements', config([probe('m_old')], [spec(' m_old ')]),
    [[0, { unit: 'A' }]]);
  assert.equal(units.targets[0].unit, 'A');
});
check('all three sections keep existing quantity, objective, scale and invalid-name behavior', () => {
  differential('parameters', 'parameters', config([], [], [
    { parameter_id: 'p1', parameter_name: 'w', unit: 'um', lower: 1 },
    { parameter_id: 'p2', parameter_name: 'custom', unit: 'V' }]),
  [[0, { parameter_name: 'nf' }], [1, { parameter_name: 'unknown', notes: 'unchanged quantity' }]]);
  differential('target rules', 'targets', config([probe('m_a', { unit: 'A' })],
    [spec('before'), spec('m_a', { normalization_scale: 9 }), spec('m_a', { direction_after_feasible: 'maximize' }),
      spec('m_a', { unit: 'dB', normalization_scale: 3 })]),
  [[0, { equation: ' m_a ' }], [1, { upper: 4 }], [2, { constraint: '<=' }], [3, { lower: 5 }]]);
  const c = config([probe('m_a'), probe('m_b', { result_source: 'expression' }), probe('m_same'),
    probe(''), probe(null), probe(123)], [spec('m_a + m_b + m_same + 123')]);
  differential('rename acceptance', 'measurements', c, [
    [0, { source_name: 'bad-name' }], [1, { source_name: 'valid' }], [2, { source_name: 'same' }],
    [3, { source_name: 'empty' }], [4, { source_name: 'null_id' }], [5, { source_name: 'numeric_id' }],
  ]);
  for (const tab of sections) differential(`${tab}: no changes`, tab, config([probe('m_a')], [spec('m_a')]), []);
});
check('no rename or no string target performs no RegExp construction, including missing targets', () => {
  const cases = [config([probe('m_a')], []), config([probe('m_a')], [spec(null), spec(3), spec({ text: 'm_a' })]),
    { ...config([probe('m_a')]), targets: null }, { ...config([probe('m_a')]), targets: undefined }];
  const absent = config([probe('m_a')]); delete absent.targets; cases.push(absent);
  cases.forEach((c, i) => {
    const before = [old.counts.constructions, current.counts.constructions];
    differential(`no string ${i}`, 'measurements', c, [[0, { source_name: 'new' }]]);
    assert.deepEqual([old.counts.constructions, current.counts.constructions], before);
  });
  const before = [old.counts.constructions, current.counts.constructions];
  differential('no accepted rename', 'measurements', config([probe('m_a')], [spec('m_a')]), [[0, { source_name: 'bad-name' }]]);
  assert.deepEqual([old.counts.constructions, current.counts.constructions], before);
});
check('private renamers preserve replacement-string tokens and reset reused global RegExp lastIndex', () => {
  // Public output names only allow identifiers. Exercise the actual private helper too, preserving String.replace's
  // replacement-string contract rather than changing it into a callback or simultaneous substitution.
  for (const to of ['$&', '$$', '$1', "$`", "$'", 'new$&$$', 'plain']) {
    const expected = old.__renamer('m_a', to), actual = current.__renamer('m_a', to);
    const before = current.counts.constructions;
    for (const equation of ['m_a m_a', 'none', 'm_a', '.m_a (m_a)', '', 'm_a m_a m_a']) {
      assert.equal(actual(equation), expected(equation), `replacement ${to} in ${equation}`);
      assert.equal(current.patterns.at(-1).lastIndex, 0, 'Global replacement resets lastIndex');
      current.patterns.at(-1).lastIndex = 17; // The next replacement must reset even a nonzero initial lastIndex.
    }
    assert.equal(current.counts.constructions - before, 1);
  }
});
check('RegExp construction failures remain deferred until a string target is visited', () => {
  for (const module of [load(beforeSource, true, true), load(source, false, true)]) {
    const changes = new Map([[0, { source_name: 'new' }]]);
    for (const targets of [[], [spec(null), spec(7)], undefined]) {
      const c = freeze({ ...config([probe('m_a')]), targets });
      assert.doesNotThrow(() => module.withFollowers('measurements', c, changes));
    }
    assert.equal(module.counts.constructions, 0);
    assert.throws(() => module.withFollowers('measurements', freeze(config([probe('m_a')], [spec('m_a')])), changes),
      { name: 'Error', message: 'Synthetic RegExp construction failure' });
  }
});
check('deterministic generated edits preserve full contents, key order and input identities', () => {
  let seed = 0x184208;
  const next = n => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n; };
  for (let fixture = 0; fixture < 240; fixture++) {
    const count = 1 + next(12);
    const rows = Array.from({ length: count }, (_, i) => probe(i % 5 === 0 ? 'legacy.[x]' : `m_${i}`, {
      unit: ['V', 'mV', 'A', 'uA'][next(4)], result_source: next(5) ? 'ade_output' : 'expression' }));
    const targets = Array.from({ length: next(24) }, (_, i) => {
      const a = rows[next(count)].measurement_id, b = rows[next(count)].measurement_id;
      return spec([`${a} + ${b}`, ` ${a} `, `.${a} + x${a}`, '', null, i][next(6)],
        { target_id: `s_${i}`, unit: ['V', 'A', 'dB'][next(3)], normalization_scale: [null, 2, 3, 7][next(4)] });
    });
    const entries = rows.flatMap((_, i) => next(3) ? [[i, {
      source_name: [`renamed_${i}`, `_${next(count)}`, 'bad-name', `${next(count)}`][next(4)],
      ...(next(3) ? {} : { unit: ['V', 'mV', 'A'][next(3)] }),
    }]] : []);
    differential(`generated ${fixture}`, 'measurements', config(rows, targets), entries);
  }
});
const operationCounts = [];
check('bulk rename matrix compiles once per rename per call, without changing any formula', () => {
  for (const [renames, targets] of [[1, 16], [8, 32], [24, 96]]) {
    const c = config(Array.from({ length: renames }, (_, i) => probe(`m_${i}`)),
      Array.from({ length: targets }, (_, i) => spec(`m_${i % renames} + m_${(i + 1) % renames}`, { target_id: `s_${i}` })));
    const entries = c.measurements.map((_, i) => [i, { source_name: `new_${i}` }]);
    const before = [old.counts.constructions, current.counts.constructions];
    differential(`${renames} by ${targets}`, 'measurements', c, entries);
    const counts = [old.counts.constructions - before[0], current.counts.constructions - before[1]];
    assert.deepEqual(counts, [renames * targets, renames]);
    operationCounts.push({ origin: 'synthetic', provenance: 'mock', renames, stringTargets: targets,
      beforeRegExpConstructions: counts[0], afterRegExpConstructions: counts[1] });
    const nextBefore = current.counts.constructions;
    differential(`${renames} by ${targets}: repeat`, 'measurements', c, entries);
    assert.equal(current.counts.constructions - nextBefore, renames, 'New edit gets fresh request-local patterns');
  }
});
const hash = value => createHash('sha256').update(value).digest('hex');
console.log(JSON.stringify({ checks, differentialComparisons: comparisons, operationCounts,
  sourceSHA256: hash(source), beforeSourceSHA256: hash(beforeSource), unitsSHA256: hash(unitsSource),
  scriptSHA256: hash(readFileSync(fileURLToPath(import.meta.url))), node: process.version,
  typescript: ts.version, timingMeasured: false }, null, 2));
