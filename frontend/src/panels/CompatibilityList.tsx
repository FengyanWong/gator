// A saved model's compatibility with the task on the page, as the backend checks it (branch record SIF-36): the problems
// first, each in its own words; a "saved {...} != current {...}" pair - a dump of two Python dictionaries, twelve lines of
// red for the spec inputs - shown as the keys whose values differ; the checks that pass folded under one line.
import type { Json } from '../api';
import { MODE_NAME } from './rlModelText';
import { DESIGN_NAME } from '../lineage';

/** The Mode a compatibility answer was checked for, in the words of the Mode buttons. */
export const compatibilityMode = (mode: string) => mode === 'resume' ? 'Resume' : MODE_NAME[mode] ?? mode;

/** Python's repr of plain data (quotes, None, True, False) read as JSON - for display only; undefined for anything else. */
function fromRepr(text: string): Json | undefined {
  try { return JSON.parse(text.replace(/'/g, '"').replace(/\bNone\b/g, 'null').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false')); }
  catch { return undefined; }
}
const shown = (key: string, v: Json) => v === undefined ? '(not there)' : v === null ? 'none'
  : typeof v === 'string' ? (key === 'encoder_type' ? DESIGN_NAME[v] ?? v : v) : JSON.stringify(v);   // a design by its name (SIF-1)
const cut = (text: string) => text.length > 70 ? `${text.slice(0, 67)}...` : text;

/** "saved {...} != current {...}": the top-level keys whose values differ; null when the detail is not such a pair. */
function differences(detail: string): { key: string; saved: string; current: string }[] | null {
  const pair = /^saved (\{[\s\S]*\}) != current (\{[\s\S]*\})$/.exec(detail.trim());
  if (!pair) return null;
  const saved = fromRepr(pair[1]), current = fromRepr(pair[2]);
  const plain = (v: Json) => !!v && typeof v === 'object' && !Array.isArray(v);
  if (!plain(saved) || !plain(current)) return null;
  const keys = [...new Set([...Object.keys(saved), ...Object.keys(current)])].filter(k => JSON.stringify(saved[k]) !== JSON.stringify(current[k]));
  return keys.length ? keys.map(key => ({ key, saved: shown(key, saved[key]), current: shown(key, current[key]) })) : null;
}

const CLASS: Record<string, string> = { ok: 'info', warning: 'warning' };

function CheckItem({ check }: { check: Json }) {
  const diff = check.status === 'ok' ? null : differences(String(check.detail ?? ''));
  return <li className={`issue ${CLASS[check.status] ?? 'error'}`}>{check.component}: {check.status}{diff
    ? <> - the saved model and this run differ in {diff.length === 1 ? 'one key' : `${diff.length} keys`}:
        <ul className="compat-diff">{diff.map(d => <li key={d.key} title={`saved: ${d.saved}\nthis run: ${d.current}`}><code>{d.key}</code> {cut(d.saved)} → {cut(d.current)}</li>)}</ul>
        <details className="compat-raw"><summary>Both values in full</summary><pre>{check.detail}</pre></details></>
    : ` - ${check.detail}`}</li>;
}

export function CompatibilityList({ checks }: { checks: Json[] }) {
  const problems = checks.filter(c => c.status !== 'ok'), passed = checks.filter(c => c.status === 'ok');
  return <>
    {problems.length > 0 && <ul className="compat-problems">{problems.map(c => <CheckItem key={c.component} check={c} />)}</ul>}
    {passed.length > 0 && <details className="compat-passed"><summary>{passed.length === 1 ? (problems.length ? 'The other check passes' : 'The one check passes')
      : problems.length ? `The other ${passed.length} checks pass` : `All ${passed.length} checks pass`}</summary>
      <ul>{passed.map(c => <CheckItem key={c.component} check={c} />)}</ul></details>}
  </>;
}
