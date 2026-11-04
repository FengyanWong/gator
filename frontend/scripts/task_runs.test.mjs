// Synthetic run metadata only: no backend, saved task or simulator.
import assert from 'node:assert/strict';
import test from 'node:test';
import { summarizeTaskRuns } from '../src/panels/taskRuns.ts';

const original = (runs, key) => {
  const mine = runs.filter(run => run.task_key === key)
    .sort((a, b) => String(b.created_utc ?? '').localeCompare(String(a.created_utc ?? '')));
  return { count: mine.length, newest: mine[0] ?? null };
};

test('task summaries match the old stable sort for shuffled dates, ties and missing dates', () => {
  const dates = [null, undefined, '', '2026-10-01T01:00:00Z', '2026-09-01T01:00:00Z', '2026-10-01T01:00:00Z'];
  const runs = Object.freeze(Array.from({ length: 2500 }, (_, index) => Object.freeze({
    task_key: `synthetic:task${(index * 19) % 73}`, run_dir: `/synthetic/run${index}`,
    created_utc: dates[(index * 7 + Math.floor(index / 13)) % dates.length],
  })));
  const result = summarizeTaskRuns(runs);
  assert.equal(result.known, true);
  for (let index = 0; index < 74; index++) {
    const key = `synthetic:task${index}`, expected = original(runs, key);
    assert.deepEqual(result.of(key), expected);
    assert.equal(result.of(key).newest, expected.newest, 'the exact first tied row remains selected');
  }
});

test('empty and legacy lists preserve unknown task ownership', () => {
  for (const runs of [[], [{ run_dir: '/synthetic/legacy' }]]) {
    const result = summarizeTaskRuns(runs);
    assert.equal(result.known, false);
    assert.deepEqual(result.of('synthetic:missing'), { count: 0, newest: null });
  }
  // A present null key still means the server supports task ownership, as the previous `in` check did.
  const result = summarizeTaskRuns([{ task_key: null }, { run_dir: '/synthetic/legacy' }]);
  assert.equal(result.known, true);
  assert.deepEqual(result.of('synthetic:missing'), { count: 0, newest: null });
});

test('a new read updates counts and newest rows without changing an earlier summary', () => {
  const first = { task_key: 'synthetic:a', created_utc: '2026-09-01', run_dir: '/synthetic/first' };
  const later = { ...first, created_utc: '2026-10-01', run_dir: '/synthetic/later' };
  const old = summarizeTaskRuns([first]), next = summarizeTaskRuns([later, first]);
  assert.deepEqual(old.of(first.task_key), { count: 1, newest: first });
  assert.deepEqual(next.of(first.task_key), { count: 2, newest: later });
  assert.deepEqual(summarizeTaskRuns([]).of(first.task_key), { count: 0, newest: null });
});
