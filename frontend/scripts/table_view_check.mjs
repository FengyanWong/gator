// Pure checks for Tasks / Runs / saved-model table arrangement and selection headers. Transpile the actual TSX module in memory with the
// installed TypeScript; do not build the frontend, open a browser, contact a backend, or write fixtures to a run.
// WSL: "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/table_view_check.mjs)"
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');
const path = fileURLToPath(new URL('../src/panels/TableView.tsx', import.meta.url));
const source = readFileSync(path, 'utf8');
function load(text) {
  const compiled = ts.transpileModule(text, {
    fileName: path,
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  });
  assert.equal(compiled.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error).length ?? 0, 0);
  const moduleExports = {};
  new Function('require', 'exports', compiled.outputText)(require, moduleExports);
  return moduleExports;
}
const { arrangeRows, TableHead } = load(source);
assert.equal(typeof arrangeRows, 'function');

// The original implementation, kept as an independent behavior oracle: same engine/locale, original comparator.
function before(rows, keep, text, value, words, down) {
  return rows.filter(r => keep(r) && words.every(w => text(r).includes(w))).sort((a, b) => {
    const x = value(a), y = value(b);
    if (x == null || x === '' || y == null || y === '') return (x == null || x === '' ? 1 : 0) - (y == null || y === '' ? 1 : 0);
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * (down ? -1 : 1);
  });
}
const wordsOf = filter => filter.toLowerCase().split(/\s+/).filter(Boolean);
const all = () => true;
const unread = () => { throw new Error('This callback must remain unread'); };
let checks = 0;
function check(name, run) {
  run();
  checks++;
  console.log(`PASS ${name}`);
}
function sameRows(actual, expected) {
  assert.equal(actual.length, expected.length);
  actual.forEach((row, i) => assert.strictEqual(row, expected[i], `Row reference at ${i}`));
}
function compare(rows, keep, text, value, words, down) {
  const original = [...rows];
  const expected = before(rows, keep, text, value, words, down);
  const actual = arrangeRows(rows, keep, text, value, words, down);
  sameRows(actual, expected);
  sameRows(rows, original);
  assert.notStrictEqual(actual, rows);
  return actual;
}

check('empty filters and fewer than two shown rows keep unused callbacks unread', () => {
  const row = Object.freeze({ id: 'only', text: 'alpha beta' });
  sameRows(arrangeRows([], unread, unread, unread, [], false), []);
  sameRows(arrangeRows([row], all, unread, unread, [], false), [row]);
  sameRows(arrangeRows([row], all, r => r.text, unread, ['beta'], true), [row]);
  sameRows(arrangeRows([row], all, r => r.text, unread, ['missing'], true), []);
  sameRows(arrangeRows([row, row], () => false, unread, unread, ['alpha'], true), []);
  sameRows(arrangeRows([row, { id: 'excluded' }], r => r === row, unread, unread, [], true), [row]);
});

check('numeric ordering, stable ties and every missing value stay last in both directions', () => {
  const rows = Object.freeze([
    { id: 'null', key: null }, { id: 'two-a', key: 2 }, { id: 'undefined', key: undefined },
    { id: 'one', key: 1 }, { id: 'empty', key: '' }, { id: 'two-b', key: 2 }, { id: 'zero', key: 0 },
  ].map(Object.freeze));
  const missing = ['null', 'undefined', 'empty'];
  for (const down of [false, true]) {
    const actual = compare(rows, all, unread, r => r.key, [], down);
    assert.deepEqual(actual.map(r => r.id), [...(down ? ['two-a', 'two-b', 'one', 'zero'] : ['zero', 'one', 'two-a', 'two-b']), ...missing]);
  }
});

check('folder exclusion, all-word filtering, whitespace and repeated words match the old arrangement', () => {
  const rows = Object.freeze([
    { id: 'hidden', folder: 'other', text: 'alpha beta', key: 0 },
    { id: 'both', folder: 'shown', text: 'prefix alpha beta suffix', key: 3 },
    { id: 'alpha', folder: 'shown', text: 'alpha', key: 1 },
    { id: 'reverse', folder: 'shown', text: 'beta alpha', key: 2 },
  ].map(Object.freeze));
  const keep = r => r.folder === 'shown';
  const text = r => { assert.equal(r.folder, 'shown'); return r.text; };
  const value = r => { assert.equal(r.folder, 'shown'); return r.key; };
  for (const filter of ['', ' \t\n ', ' AlPHA\t BETA alpha ', 'absent alpha']) for (const down of [false, true]) {
    compare(rows, keep, text, value, wordsOf(filter), down);
  }
});

check('mixed primitive keys, locale strings and duplicate references preserve exact comparator results', () => {
  const shared = Object.freeze({ id: 'shared', key: 2 });
  const rows = Object.freeze([
    ...[2, '10', 10, '2', 'é', 'e', 'E', '中', '', null, undefined, NaN, Infinity, -Infinity, -0].map((key, id) => Object.freeze({ id, key })),
    shared, shared,
  ]);
  for (const down of [false, true]) compare(rows, all, unread, r => r.key, [], down);
});

check('each arrangement reads changed values and filters again, with no persistent cache', () => {
  const a = { id: 'a', text: 'match', key: 1 }, b = { id: 'b', text: 'match', key: 2 };
  const rows = [a, b];
  sameRows(compare(rows, all, r => r.text, r => r.key, ['match'], false), [a, b]);
  a.key = 3;
  sameRows(compare(rows, all, r => r.text, r => r.key, ['match'], false), [b, a]);
  b.text = 'gone';
  sameRows(compare(rows, all, r => r.text, unread, ['match'], false), [a]);
});

check('1,000 deterministic generated tables preserve order and row identities', () => {
  let seed = 0x7356;
  const next = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed; };
  const keys = [null, undefined, '', -3, -0, 0, 1, 10, '2', '10', 'alpha', 'Beta', 'é', '中', NaN, Infinity];
  const texts = ['alpha beta', 'beta gamma', '', 'alpha gamma beta', 'gamma'];
  const filters = ['', 'alpha', 'beta gamma', ' Alpha\n beta ', 'gamma gamma', 'none'];
  for (let trial = 0; trial < 1000; trial++) {
    const rows = Object.freeze(Array.from({ length: next() % 80 }, (_, id) => Object.freeze({
      id, key: keys[next() % keys.length], text: texts[next() % texts.length], folder: next() % 3,
    })));
    const folder = trial % 4;
    compare(rows, r => folder === 3 || r.folder === folder, r => r.text, r => r.key, wordsOf(filters[trial % filters.length]), !!(trial % 2));
  }
});

let counts;
check('synthetic task/run columns derive search text and expensive sort values once per row', () => {
  const tasks = Array.from({ length: 128 }, (_, id) => ({ task_key: `synthetic:fixture_${id}`, id }));
  const runs = tasks.flatMap(task => Array.from({ length: 1 + (task.id * 17) % 40 }, (_, i) => ({
    task_key: task.task_key, created_utc: `2026-10-${String(1 + i % 28).padStart(2, '0')}T00:00:00Z`,
  })));
  function run(arrange) {
    const calls = { text: 0, value: 0, runRowsExamined: 0 };
    const output = arrange(tasks, all, task => {
      calls.text++;
      return `${task.task_key} common folder`;
    }, task => {
      calls.value++;
      // The original Tasks table's runsOf callback filtered all runs and sorted those belonging to this task.
      const mine = runs.filter(r => { calls.runRowsExamined++; return r.task_key === task.task_key; })
        .sort((a, b) => String(b.created_utc ?? '').localeCompare(String(a.created_utc ?? '')));
      return mine.length;
    }, ['synthetic', 'common', 'folder'], true);
    return { output, calls };
  }
  const old = run(before), current = run(arrangeRows);
  sameRows(current.output, old.output);
  assert.equal(current.calls.text, tasks.length);
  assert.equal(old.calls.text, 3 * tasks.length);
  assert.equal(current.calls.value, tasks.length);
  assert.ok(old.calls.value > 2 * current.calls.value);
  assert.equal(current.calls.runRowsExamined, tasks.length * runs.length);
  counts = { tasks: tasks.length, runs: runs.length, before: old.calls, after: current.calls };
});

// Reconstruct just the original linear membership expression. Both versions execute their actual JSX with the
// installed React runtime; no DOM shim or render lifecycle is needed to inspect their elements and call handlers.
const membership = '  const every = shown.every(r => view.selectedIds.has(id(r)));';
assert.equal(source.split(membership).length, 2, 'Match the exact new header expression once');
const beforeHeader = source.replace(membership, '  const every = shown.every(r => view.selected.includes(id(r)));');
const oldTableHead = load(beforeHeader).TableHead;
function headerResult(component, shown, selected, selectedIds = new Set(selected)) {
  let rowIdReads = 0;
  const changes = [];
  const tree = component({ shown, columns: [], disabled: false, what: 'runs',
    id: r => { rowIdReads++; return r.id; },
    view: { selected, selectedIds, sort: { key: 'name', down: false }, setSelected: value => changes.push(value), sortBy: unread },
  });
  const input = tree.props.children.props.children[0].props.children;
  // React 18 puts ref on the element; React 19 also exposes it as a prop. Read a data descriptor without its warning getter.
  const ref = Object.getOwnPropertyDescriptor(input.props, 'ref')?.value ?? Object.getOwnPropertyDescriptor(input, 'ref')?.value;
  const box = { indeterminate: 'unset' };
  ref(null);
  ref(box);
  return { state: { checked: input.props.checked, disabled: input.props.disabled, mixed: box.indeterminate, rowIdReads },
    changes, select: checked => input.props.onChange({ target: { checked } }) };
}

let headerCases = 0;
check('header checkbox and select-all behavior preserve empty, partial, all, offscreen, duplicate and sparse selections', () => {
  for (const [ids, selected, checked, mixed] of [
    [[], [], false, false], [[], ['offscreen'], false, false],
    [['a', 'b'], [], false, false], [['a', 'b'], ['a'], false, true],
    [['a', 'b'], ['a', 'b'], true, false], [['a', 'b'], ['offscreen'], false, true],
    [['a', 'a'], ['a', 'a', 'offscreen'], true, false],
    [[, 'a', , 'b'], [, 'a', 'b'], true, false],
  ]) {
    const shown = Object.freeze(ids.map(id => Object.freeze({ id })));
    Object.freeze(selected);
    const old = headerResult(oldTableHead, shown, selected), current = headerResult(TableHead, shown, selected);
    assert.deepEqual(current.state, old.state);
    assert.equal(current.state.checked, checked);
    assert.equal(current.state.mixed, mixed);
    current.select(true);
    current.select(false);
    assert.deepEqual(current.changes, [ids, []]);
    headerCases++;
  }
});

check('header follows the current selection membership, with the same short-circuit row reads', () => {
  const selected = [], shown = ['a', 'b'].map(id => ({ id }));
  for (const [ids, reads] of [[[], 1], [['a'], 2], [['a', 'b'], 2], [['offscreen'], 1]]) {
    selected.splice(0, selected.length, ...ids);
    const old = headerResult(oldTableHead, shown, selected), current = headerResult(TableHead, shown, selected);
    assert.deepEqual(current.state, old.state);
    assert.equal(current.state.rowIdReads, reads);
  }
});

let membershipCounts;
check('fully selected headers read each selected ID once instead of repeated linear searches', () => {
  membershipCounts = [128, 1024].map(size => {
    const shown = Array.from({ length: size }, (_, i) => ({ id: `synthetic:${i}` }));
    function run(old) {
      const calls = { selectedIdReads: 0, membershipChecks: 0, rowIdReads: 0 };
      const selected = new Proxy(Object.freeze(shown.map(r => r.id)), {
        get(target, key, receiver) {
          if (typeof key === 'string' && /^(0|[1-9]\d*)$/.test(key)) calls.selectedIdReads++;
          return Reflect.get(target, key, receiver);
        },
      });
      class CountedSet extends Set {
        has(value) { calls.membershipChecks++; return super.has(value); }
      }
      const component = old ? oldTableHead : TableHead;
      const { state } = headerResult(component, shown, selected, old ? null : new CountedSet(selected));
      assert.equal(state.checked, true);
      calls.rowIdReads = state.rowIdReads;
      return calls;
    }
    const old = run(true), current = run(false);
    assert.equal(old.selectedIdReads, size * (size + 1) / 2);
    assert.equal(current.selectedIdReads, size);
    assert.equal(current.membershipChecks, size);
    assert.equal(old.rowIdReads, size);
    assert.equal(current.rowIdReads, size);
    return { shown: size, selected: size, before: old, after: current };
  });
});

console.log(JSON.stringify({ checks, randomizedCases: 1000, headerCases,
  sourceSha256: createHash('sha256').update(source).digest('hex'), node: process.version, typescript: ts.version,
  synthetic: counts, headerMembership: membershipCounts, timingMeasured: false }, null, 2));
