// A launch the backend refused, kept beside its action until what it depends on changes (record 7.261): under the
// header for Start, Calibration and Resume, under Continue... in Run status.
import { Json } from '../api';
import { CheckSteps } from './Consistency';
import { Icon } from './Icons';

const NAMES: Record<string, string> = { start: 'Start', calibration: 'Calibration', resume: 'Resume', continue: 'Continue' };

/** A launch the backend refused (record 7.261; plan "One launcher", 6): its reason stays beside the action - on a line
 *  under the header for Start, Calibration and Resume, under Continue... in Run status - until what it depends on changes
 *  (launch.ts `Refusal.key`) or it is closed; it used to be a passing line that any click took away. A refusal by the
 *  check before every run shows its steps, as that line did. Nothing falls back to another kind of run. */
export function LaunchRefusal({ refusal, onDismiss }: { refusal: Json; onDismiss: () => void }) {
  const detail = refusal.detail ?? {};
  return <div className="launch-refusal" role="alert">
    {detail.code === 'consistency' && detail.report?.steps ? <CheckSteps result={detail.report} refused />
      : <div className="launch-refusal-text"><b>{NAMES[refusal.action] ?? 'The launch'} was refused:</b> {refusal.text}
        {(detail.code || detail.report) && <details><summary>Technical details</summary>
          <pre>{[detail.code && `code: ${detail.code}`, detail.report && JSON.stringify(detail.report, null, 1)].filter(Boolean).join('\n')}</pre></details>}</div>}
    <button className="launch-refusal-close" onClick={onDismiss} title="Close: This reason goes; nothing else changes."><Icon name="close" label="Close" /></button>
  </div>;
}
