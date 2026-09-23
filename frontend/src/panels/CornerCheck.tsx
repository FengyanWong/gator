import { useEffect, useRef, useState } from 'react';
import { api, Json, si } from '../api';
import { launchWithConsent } from './RunControl';

/** Corner check (status record 7.62; backend corner_check.py): the shown run's safest feasible designs, simulated again at
 *  the five fixed corners. The plan is read from the run's own files when the tab opens (free); the check starts only on
 *  the button, a real circuit only after the budget question. While a check works its progress is read every 1.5 s, as the
 *  run status is; nothing else runs on a timer. */

const VERDICT: Record<string, [string, string]> = { accepted: ['accepted', 'ok'], rejected: ['rejected', 'error'], inconclusive: ['inconclusive', 'warn'] };
const STATE_TEXT: Record<string, string> = { starting: 'Starting', running: 'Running', stopping: 'Stopping after the simulation in flight',
  completed: 'Completed', stopped: 'Stopped', failed: 'Failed', interrupted: 'Interrupted' };
const LIVE = ['starting', 'running', 'stopping'];

/** One cell of the grid: what that corner said about that design. */
function Cell({ record, running }: { record?: Json; running: boolean }) {
  if (!record) return <td className={running ? 'corner-pending' : 'hint'}>{running ? 'running...' : '-'}</td>;
  const values = Object.entries(record.metrics ?? {}).filter(([, v]) => v != null)
    .map(([k, v]) => `${k} = ${si(v, record.metric_units?.[k])}`).join('\n');
  if (record.state === 'passed') return <td className="corner-pass" title={values}>pass</td>;
  if (record.state === 'failed') {
    const worst = record.failing?.[0];
    return <td className="corner-fail" title={values || record.status}>FAIL{worst ? <span> {worst.metric_id} {si(worst.value, worst.unit)}</span>
      : <span> {record.status.replace(/_/g, ' ')}</span>}</td>;
  }
  const why = record.status === 'ok' ? 'measurement not valid' : record.status.replace(/_/g, ' ');
  return <td className="corner-unknown" title={record.error_summary || record.reason_code}>unknown <span>({why})</span></td>;
}

export function CornerCheckTab({ runDir }: { runDir: string | null }) {
  const [designs, setDesigns] = useState(3);
  const [plan, setPlan] = useState<Json>(null);
  const [checkId, setCheckId] = useState<string | null>(null);
  const [check, setCheck] = useState<Json>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<Json>(null);
  const planRequest = useRef(0);

  const readPlan = (count = designs) => {
    if (!runDir) return;
    const mine = ++planRequest.current;
    api.cornerPlan(runDir, count).then(p => {
      if (mine !== planRequest.current) return;
      setPlan(p);
      setCheckId(id => id && p.checks.some((c: Json) => c.check_id === id) ? id : p.checks[0]?.check_id ?? null);
    }, e => mine === planRequest.current && setNote({ level: 'error', text: e.message }));
  };
  const readCheck = (id = checkId) => {
    if (runDir && id) api.cornerStatus(runDir, id).then(setCheck, e => setNote({ level: 'error', text: e.message }));
  };
  useEffect(() => { setPlan(null); setCheck(null); setCheckId(null); setNote(null); readPlan(); }, [runDir]);
  useEffect(() => { setCheck(null); readCheck(); }, [checkId]);
  // Progress of a check that works: every 1.5 s until it has ended, then the plan once more (its list of checks).
  const live = !!check && (check.alive || LIVE.includes(check.status?.state)) && check.status?.state !== 'interrupted';
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => readCheck(), 1500);
    return () => { window.clearInterval(id); readPlan(); };
  }, [live, checkId]);

  if (!runDir) return <p className="hint">No run selected.</p>;
  const real = plan && plan.mock === false;
  const start = async () => {
    setNote(null); setBusy('start');
    try {
      const started = await launchWithConsent(flags => api.cornerStart({ run_dir: runDir, designs, simulations: plan.simulations,
        expected_designs: plan.designs.map((d: Json) => d.evaluation_id), ...flags }), { real: !!real,
        authorizeText: `This runs ${plan.simulations} REAL Spectre simulations of ${plan.task_key}: ${plan.designs.length} design(s) x ${plan.corners.length} corners.\n`
          + 'Each design\'s widths are written into the cell; the recorded widths are written back and read back at the end.\n'
          + `Authorize ${plan.simulations} simulations?` });
      if (started) { setCheckId(started.check_id); readCheck(started.check_id); readPlan(); }
      else setNote({ level: 'info', text: 'Not started: you answered no, so nothing was created.' });
    } catch (e: any) { setNote({ level: 'error', text: e.message }); } finally { setBusy(null); }
  };
  const stop = () => { setBusy('stop'); api.cornerStop(runDir, checkId!).then(() => readCheck(), e => setNote({ level: 'error', text: e.message })).finally(() => setBusy(null)); };

  const request = check?.request, results: Json[] = check?.results ?? [], summary = check?.summary, status = check?.status;
  const corners: Json[] = request?.corners ?? plan?.corners ?? [];
  const byCell = new Map(results.map(r => [`${r.design}|${r.corner}`, r]));
  const current = status?.current;
  const failedRepeat = (summary?.designs ?? []).filter((d: Json) => d.nominal_repeat?.matches === false);
  const variables = (d: Json) => Object.values(Object.fromEntries((d.widths ?? []).map((w: Json) => [w.variable_id, w])) as Record<string, Json>)
    .map(w => `${w.variable_id} ${si(w.value, w.unit)}`).join(' · ');
  return (<div className="corner-check">
    {plan?.notice && <p className="mock">{plan.notice}</p>}
    <div className="row">
      <label>Designs <select value={designs} disabled={!!busy || live} onChange={e => { const n = Number(e.target.value); setDesigns(n); readPlan(n); }}>
        {Array.from({ length: plan?.max_designs ?? 3 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select></label>
      <span className="hint">{plan?.supported ? `${plan.designs.length} design${plan.designs.length > 1 ? 's' : ''} x ${plan.corners.length} corners = ${plan.simulations} ${real
        ? 'REAL Spectre simulations (asks for your authorization first)' : 'MOCK simulations (free)'}` : plan ? 'Nothing to check in this run.' : 'Reading the run...'}</span>
      {live ? <button disabled={busy === 'stop' || status?.state === 'stopping'} onClick={stop}
          title="The simulation in flight finishes, then the check ends; for a real circuit the recorded widths are written back.">Stop</button>
        : <button className="primary" disabled={!plan?.supported || !!busy} onClick={start}>{busy === 'start' ? 'Starting...' : 'Check'}</button>}
      <button onClick={() => { readPlan(); readCheck(); }}>Refresh</button>
    </div>
    {note && <p className={note.level === 'error' ? 'error' : 'hint'}>{note.text}</p>}
    {plan && !plan.supported && plan.reason && <p className="note">{plan.reason}</p>}
    <details className="more"><summary>What the corner check does</summary>
      <p>After an optimization run it simulates the run's best designs again at five fixed conditions: the normal one (TT, 27 °C,
        1.0 V), slow transistors at 125 °C and 0.9 V, fast transistors at -40 °C and 1.1 V, and the two mixed process corners.</p>
      <p>A design is <b>accepted</b> only when it meets every hard spec at all five. One failed corner <b>rejects</b> it. A corner
        that could not be judged (no result, a measurement or connection error) makes it <b>inconclusive</b>; that is never
        blamed on the design. Nothing of the check goes back into the run, its replay or its model.</p>
      <p>Which designs: only those that met every hard spec at the normal condition, identical widths counted once, the safest
        first (the largest smallest margin: distance to the nearest limit divided by that spec's scale).</p>
      <p>Where it works: the op-amp circuits (real:gpdk045_ota5, real:gpdk045_ota7) and the MOCK task. A real check writes each
        design's widths into the cell and writes the recorded widths back at the end, as a run does; two connection or simulator
        failures in a row stop it so that no more budget is spent. Five corners are a sample, not a guarantee, and passing them
        says nothing about mismatch (that would be Monte Carlo).</p>
    </details>
    {check && <div className="corner-result">
      <h4>Check {check.check_id} <span className="hint">{request?.created_utc?.slice(0, 19).replace('T', ' ')} UTC{request?.mock ? ' - MOCK' : ''}</span></h4>
      <table className="grid small corner-grid"><thead><tr><th>Design</th>{corners.map(c => <th key={c.id}>{c.id}<span className="hint">{c.label}</span></th>)}<th>Verdict</th></tr></thead>
        <tbody>{(request?.designs ?? []).map((d: Json, i: number) => {
          const verdict = summary?.designs?.[i];
          const [text, css] = verdict ? VERDICT[verdict.disposition] ?? [verdict.disposition, ''] : [live ? 'checking...' : '-', 'hint'];
          return <tr key={d.evaluation_id}><td title={d.evaluation_id}>#{i + 1} <span className="hint">{d.evaluation_id.slice(0, 8)}</span></td>
            {corners.map(c => <Cell key={c.id} record={byCell.get(`${i}|${c.id}`)} running={live && current?.design === i && current?.corner === c.id} />)}
            <td className={css}><b>{text}</b>{verdict?.pass_rate != null && <span className="hint"> {Math.round(verdict.pass_rate * 5)}/5</span>}
              {verdict?.grading_error && <span className="error"> {verdict.grading_error}</span>}</td></tr>;
        })}</tbody></table>
      <p className={status?.state === 'failed' || status?.state === 'interrupted' ? 'error' : 'hint'}>
        {STATE_TEXT[status?.state] ?? status?.state}: {status?.done ?? 0} of {request?.simulations} simulations
        {summary?.verdicts ? ` - ${summary.verdicts.accepted} accepted, ${summary.verdicts.rejected} rejected, ${summary.verdicts.inconclusive} inconclusive.` : '.'}
        {status?.error?.message ? ` ${status.error.message}` : ''}{status?.note ? ` ${status.note}` : ''}</p>
      {summary?.restoration && (summary.restoration.state === 'restored'
        ? <p className="ok">The cell's recorded widths were written back and read back unchanged.</p>
        : summary.restoration.state === 'recovery_required' && <p className="blocker">The cell may still hold a checked design's widths: {summary.restoration.error}.
          {summary.restoration.journal ? ` The adapter's journal: ${summary.restoration.journal}` : ''}</p>)}
      {failedRepeat.length > 0 && <p className="warn">The nominal simulation of {failedRepeat.map((d: Json) => `design #${d.rank}`).join(', ')} differs from the
        run's own result ({failedRepeat[0].nominal_repeat.differences.map((x: Json) => { const unit = results.find(r => r.metric_units?.[x.metric_id])?.metric_units[x.metric_id];
          return `${x.metric_id}: run ${si(x.run, unit)}, check ${si(x.check, unit)}`; }).join('; ')}).</p>}
      {summary?.designs?.some((d: Json) => d.worst_case_metrics) && <details className="more"><summary>Worst value of each spec, per design</summary>
        <table className="grid small"><thead><tr><th>Design</th><th>Spec</th><th>Worst value</th><th>At corner</th><th>Corners measured</th></tr></thead>
          <tbody>{summary.designs.flatMap((d: Json) => Object.entries(d.worst_case_metrics ?? {}).map(([name, w]: [string, Json]) => {
            const unit = results.find(r => r.evaluation_id === d.evaluation_id)?.metric_units?.[name];
            return <tr key={`${d.rank}|${name}`}><td>#{d.rank}</td><td>{name}</td><td>{si(w.value, unit)}</td><td>{w.corner_id ?? '-'}</td>
              <td>{w.valid_corner_count} of {corners.length}</td></tr>;
          }))}</tbody></table></details>}
    </div>}
    {plan?.supported && <>
      <h4>Designs for the next check <span className="hint">- feasible at the normal condition, safest first</span></h4>
      <table className="grid small corner-designs"><thead><tr><th>#</th><th>Evaluation</th><th title="Distance to the nearest limit divided by that spec's scale: 0 = on the limit.">Smallest margin</th>
        <th>Sizes</th></tr></thead>
        <tbody>{plan.designs.map((d: Json, i: number) => <tr key={d.evaluation_id}><td>{i + 1}</td>
          <td title={d.evaluation_id}>{d.evaluation_id.slice(0, 8)} <span className="hint">(evaluation #{d.completion_index})</span></td>
          <td>{d.min_margin == null ? '-' : String(+d.min_margin.toPrecision(3))} <span className="hint">({d.tightest_spec})</span></td><td>{variables(d)}</td></tr>)}</tbody></table>
      <p className="hint">This run has {plan.counts.feasible} feasible evaluation{plan.counts.feasible === 1 ? '' : 's'}, {plan.counts.distinct} different
        design{plan.counts.distinct === 1 ? '' : 's'}. Corners: {plan.corners.map((c: Json) => `${c.id} (${c.label})`).join(' · ')}.</p>
    </>}
    {(plan?.checks?.length ?? 0) > 1 && <details className="more"><summary>Earlier checks of this run ({plan.checks.length})</summary>
      <p className="hint">Double click a row to show that check.</p>
      <table className="grid small corner-checks"><thead><tr><th>Check</th><th>State</th><th>Simulations</th><th>Verdicts</th></tr></thead>
        <tbody>{plan.checks.map((c: Json) => <tr key={c.check_id} className={c.check_id === checkId ? 'current' : ''} onDoubleClick={() => setCheckId(c.check_id)}>
          <td>{c.check_id}{c.mock ? ' (MOCK)' : ''}</td><td>{c.state}</td><td>{c.done} / {c.total}</td>
          <td>{c.verdicts ? `${c.verdicts.accepted} accepted, ${c.verdicts.rejected} rejected, ${c.verdicts.inconclusive} inconclusive` : '-'}</td></tr>)}</tbody></table>
    </details>}
  </div>);
}
