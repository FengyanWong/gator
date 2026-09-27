import { useAsyncAction } from '../store';
import { useState } from 'react';
import { api, Json, problemText, virtuosoGateText } from '../api';

/** The Virtuoso side of a cell read into the workbench: the cell the task flow WORKS IN and the Maestro setup of that
 *  cell (outputs = Probes, specs = the starting Specs rows). Since 2026-09-23 (user request) the workbench makes no copy
 *  of its own: the user copies the cell in Virtuoso, and reading it asks whether it is such a copy - "OK" declares it the
 *  cell the flow works in (the backend's working-copy record then names the cell itself). A copy the workbench made
 *  before that date (`<library>_GATOR`) keeps its record and its wording. Every action is an explicit press. Two presses
 *  write the cell and read it back: approving the agent's setup and "Save task". This panel only reads: "Read setup" takes
 *  what the cell's Maestro test says into Probes and Specs (for changes someone made in Maestro). Nothing happens on load,
 *  nothing syncs by itself. */

const PREFIX: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, m: 1e-3, u: 1e-6, 'µ': 1e-6, n: 1e-9, p: 1e-12, f: 1e-15, a: 1e-18 };

/** How many base units one `unit` is, when `unit` is `base` with an SI prefix ('GHz' of 'Hz' -> 1e9); null otherwise. */
function prefixFactor(unit: string, base: string): number | null {
  if (unit === base) return 1;
  const prefix = unit.endsWith(base) ? unit.slice(0, unit.length - base.length) : null;
  return prefix !== null && prefix in PREFIX ? PREFIX[prefix] : null;
}

/** Probes and Specs with the cell's Maestro outputs and specs in place of the ones they stand for. A unit or an
 *  optimizer-only field someone chose on a row of the same name is kept - and a limit from the cell (Maestro keeps plain
 *  numbers in base units: Hz, V, s) is converted into that unit; when it cannot be, the spec keeps the base unit. Rows of
 *  other kinds are left alone. */
function withSetupRows(config: Json, rows: Json): Json {
  const probes: Json[] = config.measurements ?? [], specs: Json[] = config.targets ?? [];
  const before = new Map(probes.map(p => [p.measurement_id, p]));
  const measurements = [...probes.filter(p => p.result_source !== 'ade_output'),
    ...rows.measurements.map((row: Json) => {
      const old = before.get(row.measurement_id);
      return old?.result_source === 'ade_output' && old.unit ? { ...row, unit: old.unit, notes: old.notes || row.notes } : row;
    })];
  const adeIds = new Set([...probes.filter(p => p.result_source === 'ade_output').map(p => p.measurement_id),
    ...rows.measurements.map((r: Json) => r.measurement_id)]);
  const units = new Map(measurements.map((p: Json) => [p.measurement_id, p.unit]));
  const oldSpecs = new Map(specs.map(t => [t.metric_id, t]));
  const kept = specs.filter(t => !adeIds.has(String(t.equation ?? '').trim()));
  const OPTIMIZER_ONLY = ['hard', 'soft_weight', 'direction_after_feasible', 'normalization_scale', 'active', 'tolerance'];
  const fromCopy = rows.targets.map((row: Json) => {
    const wanted = units.get(row.equation) ?? row.unit, factor = prefixFactor(wanted, row.unit);
    const limits = factor === null ? {} : Object.fromEntries(['lower', 'upper', 'target'].filter(k => typeof row[k] === 'number').map(k => [k, row[k] / factor]));
    const old = oldSpecs.get(row.metric_id);
    const mine = old && factor !== null ? Object.fromEntries(OPTIMIZER_ONLY.filter(k => old[k] !== undefined && (k !== 'normalization_scale' || old.unit === wanted)).map(k => [k, old[k]])) : {};
    const scale = factor === null ? {} : { normalization_scale: row.normalization_scale / factor };
    return { ...row, ...(factor === null ? {} : { unit: wanted }), ...limits, ...scale, ...mine };
  });
  return { ...config, measurements, targets: [...kept, ...fromCopy] };
}

/** A fixed clock time of the declaration, in the viewer's local time. */
const declaredAt = (iso?: string | null) => { const d = iso ? new Date(iso) : null; return d && !Number.isNaN(d.getTime()) ? d.toLocaleString() : null; };

export function WorkingCopy({ profileId, library, cell, record, config, setConfig }: {
  profileId: string | null; library: string; cell: string; record: Json;
  config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void }) {
  const [message, setMessage] = useState<Json>(null);                   // { level, text }
  const [setup, setSetup] = useState<Json>(null);                       // the last setup read, with its rows and `changed`
  const { busy, run: act } = useAsyncAction(e => setMessage({ level: 'error', text: problemText(e, virtuosoGateText) }), () => setMessage(null));
  // Read and take in one press: the rows as they were when pressed are what the backend compared with, so the same
  // rows decide whether anything changes (a test without outputs gives nothing to take). Undo brings the rows back.
  // What the press says about the editors holds only while Probes and Specs are the rows it left (`after`).
  const rowsNow = (c: Json) => JSON.stringify([c.measurements ?? [], c.targets ?? []]);
  const read = () => act('read', async () => {
    const found = await api.setupRead(profileId!, library, cell, config);
    const next = found.test && found.rows?.measurements?.length ? withSetupRows(config, found.rows) : null;
    const changed = !!next && rowsNow(next) !== rowsNow(config);
    if (changed) setConfig(c => withSetupRows(c, found.rows), true);
    setSetup({ ...found, changed, after: rowsNow(changed ? next : config) });
  });

  // No record: the cell was read before the workbench asked the question (or the answer was no). Reading it again asks.
  if (!record) return (
    <div className="working-copy">
      <p className="warn">Not yet the cell the task flow works in: press <b>Read the cell again</b> - it asks whether this cell is a copy you made,
        and "OK" makes it that cell. The agent's setup and Save task write into it.</p>
    </div>);

  const declared = !!record.declared;
  const fresh = !!setup && setup.after === rowsNow(config);
  const diffs: string[] | undefined = fresh ? setup.editor_differences : undefined;
  const conditions = Object.keys(setup?.initial_conditions ?? {}).length;
  const summary = setup && setup.test ? [`${setup.outputs.length} output${setup.outputs.length === 1 ? '' : 's'}`, `${setup.specs.length} spec${setup.specs.length === 1 ? '' : 's'}`,
    `${Object.keys(setup.variables ?? {}).length} variable${Object.keys(setup.variables ?? {}).length === 1 ? '' : 's'}`,
    ...(conditions ? [`${conditions} start voltage${conditions === 1 ? '' : 's'}`] : []),
    `analyses: ${Object.keys(setup.analyses ?? {}).join(', ') || 'none'}`].join(', ') : null;
  return (
    <div className="working-copy">
      {!record.verified
        ? <p className="warn">The working copy <code>{record.copy.library}</code> the workbench made did not pass its checks: {(record.problems ?? []).join('; ')}.
          Make a copy of the cell in Virtuoso yourself and read that one here.</p>
        : declared
          ? <p className="hint declared">Working in <code>{record.copy.library}/{record.copy.testbench}</code> directly: you declared it a copy you made
            {declaredAt(record.created_utc) ? ` (${declaredAt(record.created_utc)})` : ''}. Its Maestro test and, in a run, its device sizes are written here.</p>
          : <p className="hint">Working copy: <code>{record.copy.library}/{record.copy.testbench}</code>, made by the workbench before 2026-09-23. Checked then:
            it netlists like your cell.</p>}
      {record.verified && <div className="row"><span className="hint">Changed its Maestro test yourself?</span>
        <button disabled={!profileId || !!busy} onClick={read}
          title="Reads the cell's Maestro test GATOR and takes its outputs and specs into Probes and Specs; your units and optimizer settings stay, Undo takes it back. Nothing is written into Virtuoso; no simulation.">
          {busy === 'read' ? 'Reading...' : 'Read setup'}</button></div>}
      <details className="more hint"><summary>How the editors and the cell's Maestro relate</summary>
        <p>Each Maestro output of the cell is a Probes row (source <i>ade_output</i>, the expression in <i>signal</i>); a Maestro spec is the
          Specs row on that one probe. Units, ranges, weights and the other optimizer settings exist only in the workbench. Two presses
          write the cell, and both read it back: approving the agent's setup and <b>Save task</b>. <b>Read setup</b> goes the other way:
          after you changed outputs or specs in Maestro yourself, it takes them into Probes and Specs. Analyses and variables changed in
          Maestro are not taken over (Save task writes the task's own again): change those in the <b>Task file</b>.</p></details>
      {setup && !setup.exists && <p className="hint">The cell has no Maestro setup yet. Ask the agent to set it up, or fill Probes and Specs and
        press <b>Save task</b>: it writes them into the cell.</p>}
      {setup && setup.exists && !setup.test && <p className="warn">The cell's Maestro view has no test <code>GATOR</code>{setup.tests?.length ? <> (it has: {setup.tests.join(', ')})</> : ''}.</p>}
      {summary && <p className="hint">Test <code>GATOR</code>: {summary}.</p>}
      {setup?.test && !Object.keys(setup.analyses ?? {}).length && <p className="warn">The test has no analysis yet: its outputs measure nothing until one is set.</p>}
      {setup?.test && !setup.rows?.measurements?.length && <p className="hint">It has no outputs, so nothing was taken into the editors.</p>}
      {fresh && setup.changed && <p className="ok">Probes and Specs now show the cell's outputs and specs; your units and optimizer settings stayed. Undo
        brings the previous rows back.</p>}
      {fresh && setup.test && setup.rows?.measurements?.length > 0 && !setup.changed && diffs && (diffs.length === 0 ? <p className="ok">The editors already say what the cell says.</p>
        : <p className="warn">It differs from the editors in {diffs.length} place{diffs.length === 1 ? '' : 's'} that Probes and Specs do not hold: <b>Save task</b> makes
          the cell say what the task says.</p>)}
      {diffs && diffs.length > 0 && <details className="more hint"><summary>What differed ({diffs.length})</summary>
        <ul className="steps-list">{diffs.map(d => <li key={d}>{d}</li>)}</ul></details>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>);
}
