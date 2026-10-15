import { Json } from '../api';

/** The result of the check before every run of a saved task (backend consistency.py): one line per step - what was
 *  compared and whether it agrees. A failed step says what to do right beside it; the long reason is one closed line.
 *  Shown by "Check now" in the task's block and by a Start / Baseline simulation / Resume that was refused. */
export function CheckSteps({ result, refused = false }: { result: Json; refused?: boolean }) {
  const failed = (result.steps ?? []).filter((s: Json) => !s.ok);
  return (
    // A click inside (a "reason" line) must not close the banner this may sit in.
    <div className="check-steps" onClick={e => e.stopPropagation()}>
      <p className={result.ok ? 'ok' : 'error'}><b>{result.ok
        ? `The editors, the saved task ${result.task} (revision ${result.revision}) and its working copy in Virtuoso agree. Nothing was simulated.`
        : `${refused ? 'Not started: ' : ''}${result.task} - ${failed.length === 1 ? 'one step does' : `${failed.length} steps do`} not agree${refused
          ? '' : ', so a run would not start'}. Nothing was simulated.`}</b></p>
      {result.virtuoso_session?.said && <p className="hint">{result.virtuoso_session.said}</p>}
      <ul className="steps-list">{(result.steps ?? []).map((s: Json) => (
        <li key={s.step} className={s.ok ? (s.skipped ? 'hint' : 'ok') : 'error'}>
          <b>{s.ok ? (s.skipped ? 'left out' : 'passed') : 'FAILED'}:</b> {s.title}.{!s.ok && s.fix && <> <b>{s.fix}</b></>}
          {s.detail && <details className="more"><summary>{s.ok ? 'what was found' : 'the reason'}</summary><p>{s.detail}</p></details>}
        </li>))}</ul>
    </div>);
}
