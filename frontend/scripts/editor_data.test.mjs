// Synthetic row edits only: no DOM, backend, saved task or simulator.
import assert from 'node:assert/strict';
import test from 'node:test';
import { fillCells, pasteCells, readPastedCell } from '../src/panels/editorSheet.ts';
import { prepareImport } from '../src/panels/editorImport.ts';
import { setUnitForms } from '../src/units.ts';
import { idList, indexUnsavedRows, unsavedSummary } from '../src/panels/editorChanges.ts';
import { limitLabel, limitUses } from '../src/panels/editorRules.ts';

setUnitForms({ spellings: { m: ['m', 1, 0], nm: ['m', 1e-9, 0], V: ['V', 1, 0] },
  prefixable: ['m', 'V'], symbols: {}, kinds: { w: 'm' } });
const lower = { name: 'lower', label: 'Lower', type: 'number', nullable: true };
const notes = { name: 'notes', label: 'Notes', type: 'string' };
const rules = { blocked: (row, column) => !!row.binding_group && column.name === 'lower', unitOf: row => row.unit ?? null };
const sheet = rows => ({ tab: 'parameters', keyField: 'variable_id', rows, visible: [lower, notes] });
const config = () => ({ schema_version: 'gator-workbench-config-v1', project: { name: 'synthetic', task_name: 'mock' },
  circuit: { source: 'registered_task', task_id: 'synthetic:fixture' }, parameters: [], measurements: [], targets: [],
  run: { mode: 'scratch', seed: 0, max_evaluations: 10 }, output: {}, research: {} });

test('fill converts units, preserves locked and incompatible cells, and leaves inputs untouched', () => {
  const data = sheet([{ variable_id: 'a', unit: 'nm', lower: 600 }, { variable_id: 'b', unit: 'm', lower: 0 },
    { variable_id: 'c', unit: 'm', lower: 0, binding_group: 'a' }, { variable_id: 'd', unit: 'V', lower: 1 }]);
  const before = structuredClone(data);
  const result = fillCells(data, rules, lower, 0, [1, 2, 3]);
  assert.deepEqual([...result.changes], [[1, { lower: 6e-7 }]]);
  assert.match(result.note.text, /1 cell that follows another field kept/);
  assert.match(result.note.text, /1 cell of another quantity kept/);
  assert.equal(result.note.warn, true);
  assert.deepEqual(data, before);
});

test('fill borrows no mutable object from its source', () => {
  const data = sheet([{ variable_id: 'a', extension: { values: [1] } }, { variable_id: 'b', extension: null }]);
  const result = fillCells(data, rules, { name: 'extension', type: 'object' }, 0, [1]);
  result.changes.get(1).extension.values.push(2);
  assert.deepEqual(data.rows[0].extension, { values: [1] });
});

test('paste follows displayed row order, skips headers and locked cells, and reports overflow', () => {
  const data = sheet([{ variable_id: 'a', unit: 'm' }, { variable_id: 'hidden', unit: 'm' },
    { variable_id: 'tied', unit: 'm', binding_group: 'a' }]);
  const before = structuredClone(data);
  const result = pasteCells(data, rules, 'Lower *\tNotes\n200 nm\ttied\n600 nm\tfirst\n1 nm\textra', [2, 0], { row: 0, column: 0 });
  assert.deepEqual([...result.changes], [[2, { notes: 'tied' }], [0, { lower: 6e-7, notes: 'first' }]]);
  assert.equal(result.note.text, 'Pasted 3 cells into 2 rows (one Undo step). The header line was skipped. '
    + '1 cell that follows another field kept. 1 line below the last row left out: Add rows first.');
  assert.equal(result.note.warn, true);
  assert.deepEqual(data, before);
});

test('a failed pasted quantity preserves that cell but still accepts its neighboring text', () => {
  const data = sheet([{ variable_id: 'a', unit: 'm', lower: 1 }]);
  const result = pasteCells(data, rules, '2 V\tkept note', [0], { row: 0, column: 0 });
  assert.deepEqual([...result.changes], [[0, { notes: 'kept note' }]]);
  assert.match(result.note.text, /Not read, left as they were: "2 V" in Lower/);
  assert.equal(result.note.warn, true);
});

test('empty nullable numbers clear, empty required numbers stay, and whitespace in text survives', () => {
  const read = (column, text) => readPastedCell('parameters', column, text, { unit: 'm' }, rules.unitOf);
  assert.deepEqual(read(lower, ''), { value: null });
  assert.deepEqual(read({ ...lower, nullable: false }, ''), {});
  assert.deepEqual(read(notes, '  note  '), { value: '  note  ' });
  assert.deepEqual(read({ name: 'optimized', type: 'boolean' }, 'yes'), { value: true });
  assert.deepEqual(read({ name: 'scale', type: 'string', options: ['linear', 'log'] }, 'LOG'), { value: 'log' });
  assert.deepEqual(readPastedCell('targets', { name: 'constraint', type: 'string' }, '≥', {}, rules.unitOf), { value: '>=' });
});

test('import refuses unrelated or incomplete configurations and rows without identifiers', () => {
  assert.throws(() => prepareImport({ schema_version: 'conditions' }, config(), 'parameters', 'variable_id'), /neither a workbench configuration/);
  assert.throws(() => prepareImport({ schema_version: 'gator-workbench-config-v1' }, config(), 'parameters', 'variable_id'), /not all there/);
  assert.throws(() => prepareImport([{}], config(), 'parameters', 'variable_id'), /every Parameters row needs its ID/);
  assert.throws(() => prepareImport(null, config(), 'parameters', 'variable_id'), /neither a workbench configuration/);
});

test('row-only import migrates old Specs, preserves other sections and never mutates its input', () => {
  const current = config(), incoming = [{ metric_id: 'gain', measurement_id: 'm_gain', constraint: '>=', lower: 1, unit: 'V/V', extension: { kept: true } }];
  const before = structuredClone({ current, incoming });
  const prepared = prepareImport(incoming, current, 'targets', 'metric_id');
  assert.equal(prepared.rows.section, 'targets');
  assert.equal(prepared.rows.value[0].equation, 'm_gain');
  assert.deepEqual(prepared.rows.value[0].extension, { kept: true });
  assert.deepEqual(prepared.next.project, current.project);
  assert.deepEqual({ current, incoming }, before);
});

test('whole-configuration import identifies changed non-table sections', () => {
  const current = config(), incoming = { ...config(), project: { name: 'replacement', task_name: 'mock' } };
  const prepared = prepareImport(incoming, current, 'parameters', 'variable_id');
  assert.equal(prepared.rows, null);
  assert.ok(prepared.others.includes('project'));
});

test('saved-row summaries keep the tooltip and dialog wording, order and different ID limits', () => {
  const rows = { added: ['a', 'b'], removed: ['r1', 'r2', 'r3', 'r4', 'r5'],
    changed: { z: { fields: { lower: 2 } }, y: { fields: { upper: 4 } } }, reordered: true };
  const before = structuredClone(rows);
  assert.equal(unsavedSummary(rows), '2 changed, 2 new, 5 saved rows deleted here (r1, r2, r3, ...), rows in another order');
  assert.equal(unsavedSummary(rows, true), '2 changed (z, y), 2 new (a, b), 5 saved rows deleted here (r1, r2, r3, r4, ...), rows in another order');
  assert.deepEqual(rows, before);
  assert.equal(idList(['a', 'b', 'c', 'd', 'e']), 'a, b, c, d, ...');
});

test('saved-row summaries handle absent reports, no changes, singular deletion and reorder-only changes', () => {
  for (const detail of [false, true]) {
    for (const rows of [null, undefined, {}, { added: [], removed: [], changed: {}, reordered: false }])
      assert.equal(unsavedSummary(rows, detail), null);
    assert.equal(unsavedSummary({ removed: ['one'] }, detail), '1 saved row deleted here (one)');
    assert.equal(unsavedSummary({ reordered: true }, detail), 'rows in another order');
  }
});

test('unsaved row indexes preserve marks and tied counts with missing, duplicate and non-string IDs', () => {
  const rows = [{ variable_id: 'leader' }, { variable_id: 'leader' }, { variable_id: 'new', binding_group: 'leader' },
    { variable_id: 'new', binding_group: 'leader' }, { variable_id: 'changed', binding_group: 'leader' },
    { variable_id: 'orphan', binding_group: 'missing' }, { variable_id: 7 }, { variable_id: '7' },
    { variable_id: 8, binding_group: '7' }, { variable_id: null, binding_group: 'leader' },
    { binding_group: 'leader' }, { variable_id: '', binding_group: '' }, { variable_id: 'self', binding_group: 'self' }];
  const report = { added: ['new', 'new', '7', '8', ''], removed: [],
    changed: { changed: { fields: { lower: 2 } }, orphan: { fields: { upper: 4 } }, self: { fields: { ratio: 2 } } } };
  const before = structuredClone({ rows, report });
  const ids = new Set(rows.map(row => row.variable_id));
  for (const parameters of [true, false]) {
    const leaderOf = row => parameters && row.binding_group && ids.has(row.binding_group) ? row.binding_group : null;
    for (const unsaved of [report, null, undefined, {}, { added: [], changed: {} }]) {
      const indexed = indexUnsavedRows(rows, 'variable_id', unsaved, leaderOf);
      const wasNew = row => !!unsaved?.added?.includes(String(row.variable_id ?? ''));
      const wasChanged = row => unsaved?.changed?.[String(row.variable_id ?? '')] ?? null;
      for (const row of rows) {
        assert.equal(indexed.isNew(row), wasNew(row));
        assert.equal(indexed.changeOf(row), wasChanged(row));
        const tied = rows.some(follower => !!leaderOf(follower) && leaderOf(follower) === row.variable_id);
        const count = tied ? rows.filter(follower => leaderOf(follower) === row.variable_id && (wasNew(follower) || wasChanged(follower))).length : 0;
        assert.equal(indexed.unsavedTies.get(row.variable_id) ?? 0, count);
      }
    }
  }
  const indexed = indexUnsavedRows(rows, 'variable_id', report, row => row.binding_group && ids.has(row.binding_group) ? row.binding_group : null);
  assert.equal(indexed.unsavedTies.get('leader'), 5); // Two duplicate new rows, one changed row and two empty IDs.
  assert.equal(indexed.unsavedTies.has('missing'), false);
  assert.equal(indexed.unsavedTies.get('7'), 1);
  assert.equal(indexed.unsavedTies.has(7), false); // Saved marks normalize IDs; ties keep the editor's exact keys.
  assert.deepEqual({ rows, report }, before);
});

test('unsaved follower lookup visits each row at most once regardless of the number of leaders', () => {
  const rows = Array.from({ length: 200 }, (_, i) => [
    { variable_id: `leader${i}` }, { variable_id: `follower${i}`, binding_group: `leader${i}` },
  ]).flat();
  const report = { added: rows.map(row => row.variable_id), changed: {}, removed: [] };
  let visits = 0;
  const indexed = indexUnsavedRows(rows, 'variable_id', report, row => { visits++; return row.binding_group ?? null; });
  for (let i = 0; i < 200; i++) assert.equal(indexed.unsavedTies.get(`leader${i}`), 1);
  assert.equal(visits, rows.length);
});

test('missing and legacy limit values remain visible without inventing a supported constraint', () => {
  assert.equal(limitLabel(undefined, 'none'), '(not set)');
  assert.equal(limitLabel('legacy', 'custom'), 'legacy, then custom');
  assert.equal(limitLabel(7, false), '7');
  assert.equal(limitUses(undefined, 'lower'), false);
  assert.equal(limitUses('interval', 'upper'), true);
});
