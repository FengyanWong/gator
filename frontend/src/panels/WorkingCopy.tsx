import { useState } from 'react';
import { api, Json } from '../api';

/** The Virtuoso side of a cell read into the workbench: its WORKING COPY (the only cells the task flow writes into) and
 *  the Maestro setup of that copy (outputs = Probes, specs = the starting Specs rows). Every action is an explicit press:
 *  making the copy, reading the setup, taking it into the editors, writing the editors' rows back. Nothing happens on
 *  load, and nothing syncs by itself - the page says when the editors and the copy differ. */

const gateText = (gate: Json) => `Virtuoso cannot be reached (${[...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') || gate.status}). `
  + 'Bring the link up in the Connection window, then try again.';

const PREFIX: Record<string, number> = { T: 1e12, G: 1e9, M: 1e6, k: 1e3, m: 1e-3, u: 1e-6, 'µ': 1e-6, n: 1e-9, p: 1e-12, f: 1e-15, a: 1e-18 };

/** How many base units one `unit` is, when `unit` is `base` with an SI prefix ('GHz' of 'Hz' -> 1e9); null otherwise. */
export function prefixFactor(unit: string, base: string): number | null {
  if (unit === base) return 1;
  const prefix = unit.endsWith(base) ? unit.slice(0, unit.length - base.length) : null;
  return prefix !== null && prefix in PREFIX ? PREFIX[prefix] : null;
}

/** Probes and Specs with the copy's Maestro outputs and specs in place of the ones they stand for. A unit or an
 *  optimizer-only field someone chose on a row of the same name is kept - and a limit from the copy (Maestro keeps plain
 *  numbers in base units: Hz, V, s) is converted into that unit; when it cannot be, the spec keeps the base unit. Rows of
 *  other kinds are left alone. */
export function withSetupRows(config: Json, rows: Json): Json {
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

export function WorkingCopy({ profileId, library, cell, testbench, record, config, setConfig, onCopied }: {
  profileId: string | null; library: string; cell: string; testbench: string | null; record: Json;
  config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; onCopied: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<Json>(null);                   // { level, text }
  const [setup, setSetup] = useState<Json>(null);                       // the last setup read or written, with its rows
  const [written, setWritten] = useState<Json>(null);                   // the last write: { matches, differences }
  const [taken, setTaken] = useState(false);
  const act = async (what: string, action: () => Promise<void>) => {
    setBusy(what); setMessage(null);
    try { await action(); }
    catch (e: any) {
      const gate = e.detail?.gate;
      setMessage({ level: 'error', text: e.status === 404 || e.status === 405 ? 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).'
        : gate ? gateText(gate) : e.message });
    } finally { setBusy(null); }
  };
  const make = () => act('copy', async () => {
    const made = await api.workingCopy(profileId!, library, cell);
    setMessage(made.verified ? { level: 'ok', text: made.already ? 'This cell already had its working copy.' : `Copied into ${made.copy.library}. Your cells were not changed.` }
      : { level: 'error', text: 'The copy was made but did not pass its checks: ' + (made.problems ?? []).join('; ') });
    onCopied();
  });
  const read = () => act('read', async () => {
    const found = await api.setupRead(profileId!, library, cell, config);
    setSetup(found); setWritten(null); setTaken(false);
  });
  const adeProbes = (config.measurements ?? []).filter((m: Json) => m.result_source === 'ade_output');
  const write = () => {
    if (!adeProbes.length && !window.confirm('The editors hold no Maestro probes (Probes rows of source ade_output).\n\n'
      + `Writing now leaves the copy's test with no outputs and no specs. Write anyway?`)) return;
    act('write', async () => {
      const result = await api.setupWrite(profileId!, library, cell, config);
      setSetup({ ...result, editor_differences: result.differences }); setWritten(result); setTaken(false);
    });
  };
  const take = () => { setConfig(c => withSetupRows(c, setup.rows), true); setTaken(true); };

  if (!record) return (
    <div className="working-copy">
      <div className="row"><span className="hint">Edits and simulations of this cell happen in a copy, never in your cells.</span>
        <button className="primary" disabled={!profileId || !testbench || !!busy} onClick={make}
          title={testbench ? undefined : 'Read the cell through its testbench first: the copy is of the testbench and the cell under it.'}>
          {busy === 'copy' ? 'Copying...' : 'Make a working copy'}</button></div>
      <details className="more hint"><summary>What making the copy does</summary>
        <p>It adds the library <code>{library}_GATOR</code> next to yours (the library list <code>cds.lib</code> is backed up first), copies
          {testbench ? <> <code>{testbench}</code> and</> : ''} <code>{cell}</code> into it and points the copied testbench at the copied cell.
          It then checks that the copy netlists like the original and that your cells read back unchanged. No simulation.</p></details>
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>);

  const diffs: string[] | undefined = setup?.editor_differences;
  const summary = setup && setup.test ? [`${setup.outputs.length} output${setup.outputs.length === 1 ? '' : 's'}`, `${setup.specs.length} spec${setup.specs.length === 1 ? '' : 's'}`,
    `${Object.keys(setup.variables ?? {}).length} variable${Object.keys(setup.variables ?? {}).length === 1 ? '' : 's'}`,
    `analyses: ${Object.keys(setup.analyses ?? {}).join(', ') || 'none'}`].join(', ') : null;
  return (
    <div className="working-copy">
      {record.verified
        ? <p className="hint">Working copy: <code>{record.copy.library}/{record.copy.testbench}</code>. Checked: it netlists like your cell.</p>
        : <p className="warn">The working copy <code>{record.copy.library}</code> did not pass its checks: {(record.problems ?? []).join('; ')}</p>}
      {record.verified && <div className="row"><span className="hint">Its Maestro setup:</span>
        <button disabled={!profileId || !!busy} onClick={read} title="Reads the copy's Maestro test GATOR: analyses, outputs, specs, variables. Read-only, no simulation.">
          {busy === 'read' ? 'Reading...' : 'Read setup'}</button>
        <button disabled={!profileId || !!busy} onClick={write}
          title="Writes the Probes rows of source ade_output and the Specs on exactly one of them into the copy's Maestro test, then reads it back. Only the copy is written; no simulation.">
          {busy === 'write' ? 'Writing...' : 'Write to Virtuoso'}</button></div>}
      <details className="more hint"><summary>How the editors and the copy's Maestro relate</summary>
        <p>Each Maestro output of the copy is a Probes row (source <i>ade_output</i>, the expression in <i>signal</i>); a Maestro spec is the
          Specs row on that one probe. Units, ranges, weights and the other optimizer settings exist only in the workbench. Nothing is
          synchronized on its own: <b>Read setup</b> shows what the copy says and how the editors differ, <b>Use in editors</b> takes it over,
          and <b>Write to Virtuoso</b> makes the copy say what the editors say.</p></details>
      {setup && !setup.exists && <p className="hint">The copy has no Maestro view yet. <b>Write to Virtuoso</b> creates it.</p>}
      {setup && setup.exists && !setup.test && <p className="warn">The copy's Maestro view has no test <code>GATOR</code>{setup.tests?.length ? <> (it has: {setup.tests.join(', ')})</> : ''}.</p>}
      {summary && <p className="hint">Test <code>GATOR</code>: {summary}.</p>}
      {setup?.test && !Object.keys(setup.analyses ?? {}).length && <p className="warn">The test has no analysis yet: its outputs measure nothing until one is set.</p>}
      {written && (written.matches ? <p className="ok">Written and read back: the copy now says what the editors say.</p>
        : <p className="error">Written, but the copy reads back differently in {written.differences.length} place{written.differences.length === 1 ? '' : 's'}.</p>)}
      {setup?.test && diffs && !written && (diffs.length === 0 ? <p className="ok">The editors match the copy.</p>
        : <p className="warn">The editors differ from the copy in {diffs.length} place{diffs.length === 1 ? '' : 's'}.</p>)}
      {diffs && diffs.length > 0 && <details className="more hint"><summary>What differs</summary>
        <ul className="steps-list">{diffs.map(d => <li key={d}>{d}</li>)}</ul></details>}
      {setup?.test && setup.rows?.measurements?.length > 0 && !taken && <div className="row">
        <span className="hint">Fills Probes and Specs from the copy's outputs and specs; your units and optimizer settings stay. Undo takes it back.</span>
        <button onClick={take}>Use in editors</button></div>}
      {taken && <p className="hint">Probes and Specs now show the copy's Maestro outputs and specs. Undo brings the previous rows back.</p>}
      {message && <p className={message.level === 'ok' ? 'ok' : 'error'}>{message.text}</p>}
    </div>);
}
