// The configuration as a reload leaves it (plan-refactoring C3, out of store.ts): rows and fields retired over time are
// rewritten the way the backend reads them, so a row here equals the row it serves back.
import type { Json } from './api';

/** A Specs row saved before specs had equations named ONE probe in `measurement_id`: that probe is its equation (the
 *  simplest one). The key keeps its place, so the row still equals the same row served by the backend now (rows are
 *  compared as JSON text), and an `equation` given as well wins - the backend reads old rows the same way. */
export function migrateConfig(config: Json): Json {
  if (!config || typeof config !== 'object') return config;
  let out = config;
  if (Array.isArray(config.targets)) {
    const targets = config.targets.map((row: Json) => row && typeof row === 'object' && 'measurement_id' in row
      ? Object.fromEntries(Object.entries(row).filter(([key]) => !(key === 'measurement_id' && 'equation' in row))
          .map(([key, value]) => [key === 'measurement_id' ? 'equation' : key, value]))
      : row);
    out = { ...out, targets };
  }
  if (Array.isArray(config.parameters)) out = { ...out, parameters: config.parameters.map(migrateParameter) };
  out = withoutExpressionProbes(out);
  if (Array.isArray(out.targets)) out = { ...out, targets: out.targets.map(migrateTarget) };
  if (Array.isArray(out.measurements)) out = { ...out, measurements: out.measurements.map((row: Json) => without(row, RETIRED_MEASUREMENT_KEYS)) };
  // "Threads per job" retired on 2026-09-29: no simulator ever used it. The backend drops it too and hashes it at 1. The
  // Search method block went on 2026-10-06 (record 7.226: SAC is the only search method): the backend drops it too, and
  // refuses a start that still asks for an LLM method - kept here, it would be refused at every Start.
  if (config.run && typeof config.run === 'object' && ('threads_per_job' in config.run || 'search' in config.run))
    out = { ...out, run: without(config.run, ['threads_per_job', 'search']) };
  // "Experiment group" and "Test tasks" retired on 2026-10-03 (record 7.163): nothing read them. The backend drops them too.
  if (config.research && typeof config.research === 'object' && ('experiment_group' in config.research || 'test_tasks' in config.research))
    out = { ...out, research: without(config.research, ['experiment_group', 'test_tasks']) };
  return out;
}

/** Columns retired on 2026-09-26 (record 7.92), and the Probes' conditions and aggregation on 2026-09-29 (record 7.105).
 *  The backend drops them the same way when it reads a row, so a row here
 *  equals the row it serves back; what they meant is kept in the columns that remain (an expression relation as the
 *  ratio, a discrete candidate grid as lower/upper/step), and a value that cannot be kept goes into the notes. */
const RETIRED_PARAMETER_KEYS = ['name', 'target_kind', 'candidates', 'relation', 'expression'];
const RETIRED_MEASUREMENT_KEYS = ['function', 'window', 'at_frequency_hz', 'integration_band_hz', 'branch_direction', 'loop_definition', 'crossover', 'on_failure', 'validity',
  'conditions', 'aggregation', 'expression'];

/** Retired on 2026-10-03, as the backend does (schema.WorkbenchConfig._expression_probes, PerformanceTarget._retired_fields):
 *  a probe computed from other probes goes into the equations of the specs that use it, in parentheses; a spec's
 *  "target ± tolerance" becomes the interval it was, and a tolerance on another spec the limits it loosened (an empty scale
 *  gets the size it had). What never ran (a cycle of probes, a target without a positive tolerance) stays as it is, for
 *  the backend to refuse in plain words. */
const namePattern = (name: string) => new RegExp(`(?<![A-Za-z0-9_.])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g');
function withoutExpressionProbes(config: Json): Json {
  const probes: Json[] = Array.isArray(config.measurements) ? config.measurements : [];
  const computed = new Map<string, string>(probes.filter(m => m?.result_source === 'expression').map(m => [String(m.measurement_id), String(m.expression ?? '')]));
  if (!computed.size) return config;
  const written = (text: string, seen: string[] = []): string | null => {
    let out: string | null = text;
    for (const [name, expression] of computed) {
      if (out === null || !namePattern(name).test(out)) continue;
      if (seen.includes(name)) return null;
      const inner = written(expression, [...seen, name]);
      out = inner === null ? null : out.replace(namePattern(name), `(${inner})`);
    }
    return out;
  };
  const targets = (config.targets ?? []).map((t: Json) => typeof t?.equation === 'string' ? { t, equation: written(t.equation) } : { t, equation: t?.equation });
  if (targets.some((x: Json) => x.equation === null)) return config;                 // a cycle: the backend says so
  return { ...config, targets: targets.map((x: Json) => typeof x.t?.equation === 'string' ? { ...x.t, equation: x.equation } : x.t),
    measurements: probes.filter(m => m?.result_source !== 'expression') };
}
function migrateTarget(row: Json): Json {
  if (!row || typeof row !== 'object' || !('target' in row || 'tolerance' in row || row.constraint === 'target')) return row;
  const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const tolerance = row.tolerance ?? 0, size = Math.max(...[row.lower, row.upper, row.target].filter(number).map(Math.abs), 0) || 1;
  if (!number(tolerance) || tolerance < 0) return row;
  let out = without(row, ['target', 'tolerance']);
  if (row.constraint === 'target') {
    if (!number(row.target) || tolerance <= 0 || row.lower != null || row.upper != null) return row;
    out = { ...out, constraint: 'interval', lower: row.target - tolerance, upper: row.target + tolerance };
  } else if (tolerance) {
    out = { ...out, ...(number(row.lower) ? { lower: row.lower - tolerance } : {}), ...(number(row.upper) ? { upper: row.upper + tolerance } : {}) };
  } else return out;
  return out.normalization_scale == null ? { ...out, normalization_scale: size } : out;
}

function without(row: Json, keys: string[]): Json {
  if (!row || typeof row !== 'object' || !keys.some(key => key in row)) return row;
  return Object.fromEntries(Object.entries(row).filter(([key]) => !keys.includes(key)));
}

/** (lower, upper, step) when the values are a uniform grid, else null - the backend's rule (schema.uniform_grid). */
function uniformGrid(values: unknown): [number, number, number] | null {
  if (!Array.isArray(values) || values.some(v => typeof v !== 'number' || !Number.isFinite(v))) return null;
  const sorted = [...new Set(values as number[])].sort((a, b) => a - b);
  if (sorted.length < 2 || sorted.length !== values.length) return null;
  const step = sorted[1] - sorted[0];
  if (step <= 0 || sorted.some((v, i) => i > 0 && Math.abs(v - sorted[i - 1] - step) > 1e-9 * Math.abs(step) + 1e-18)) return null;
  return [sorted[0], sorted[sorted.length - 1], step];
}

/** The ratio r when the text is r*leader, leader*r or leader/r with a plain number r > 0, else null. */
function plainRatio(expression: unknown): number | null {
  if (typeof expression !== 'string') return null;
  const number = '([0-9]*\\.?[0-9]+(?:[eE][-+]?[0-9]+)?)';
  const forms: [RegExp, (n: number) => number][] = [
    [new RegExp(`^\\s*${number}\\s*\\*\\s*leader\\s*$`), n => n], [new RegExp(`^\\s*leader\\s*\\*\\s*${number}\\s*$`), n => n],
    [new RegExp(`^\\s*leader\\s*/\\s*${number}\\s*$`), n => 1 / n], [/^\s*leader\s*$/, () => 1]];
  for (const [form, ratio] of forms) {
    const match = form.exec(expression);
    if (match) { const r = ratio(Number(match[1] ?? 1)); return Number.isFinite(r) && r > 0 ? r : null; }
  }
  return null;
}

function migrateParameter(row: Json): Json {
  if (!row || typeof row !== 'object' || !(RETIRED_PARAMETER_KEYS.some(key => key in row) || row.value_type === 'discrete')) return row;
  const notes: string[] = [];
  let out: Json = { ...row };
  if (row.relation === 'expression') {
    const ratio = plainRatio(row.expression);
    if (ratio !== null) out.ratio = ratio;
    else notes.push(`Was relation expression ${JSON.stringify(row.expression ?? '')}: give the ratio (kept ${row.ratio ?? 1}).`);
  }
  if (row.value_type === 'discrete') {
    const grid = uniformGrid(row.candidates);
    if (grid) [out.lower, out.upper, out.step] = grid;
    else notes.push(`Was value_type discrete with candidates ${JSON.stringify(row.candidates ?? null)}: give lower, upper and step.`);
    out.value_type = 'continuous';
  }
  if (row.target_kind && row.target_kind !== 'instance_parameter') notes.push(`Was target_kind ${row.target_kind}: the optimizer writes instance parameters only.`);
  out = without(out, RETIRED_PARAMETER_KEYS);
  if (notes.length) out.notes = [row.notes, ...notes].filter(Boolean).join(' ');
  return out;
}
