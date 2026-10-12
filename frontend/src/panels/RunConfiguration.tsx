// Run configuration's own part (plan-refactoring C4, out of Right.tsx): the next run's model in one line with the RL model
// window's button, the budget, the seed and the limits. It only draws what useRlModel holds.
import { folderName } from '../format';
import { openRunsAt } from '../openAt';
import { Blocked } from './popupParts';
import { Check, Num } from './fields';
import { MODE_NAME } from './rlModelText';
import type { RlModel } from './useRlModel';

/** Said in Run configuration and in the window, with the run that configuration continued: Continue... is where it goes on. */
export function NoModeNote({ m, from }: { m: RlModel; from: Window | null }) {
  const { noMode, source } = m;
  return noMode && <p className="warn no-mode">No Mode is chosen: this configuration still says resume, which is
    no longer a choice{source.run_dir ? <> - it continued the run <button className="text-link no-mode-run" onClick={() => openRunsAt({ run_dir: source.run_dir, from })}
      title="Open the Runs window at that run: Continue... goes on with it in its own folder, and Show results shows it.">{folderName(String(source.run_dir))}</button></> : ''}.
    Choose a Mode {from ? 'above' : 'in RL model...'} for the next run: Start waits until then.</p>;
}

export function RunConfiguration({ m }: { m: RlModel }) {
  const { run, set, source, circuit, networkWindow, loads, netTitle, modelLine, networkError, networkWarning, modelChecked, model, limitsSet } = m;
  return (<>
      {/* The Mode and the RL model label moved into the RL model window (record 7.265); here the next run's model is one line. */}
      <div className="rl-networks-row"><span className={`hint net-short${loads && !source.run_dir ? '' : ' net-code'}`} title={netTitle}>{modelLine}</span>
        <button className="rl-networks-open" title="Open the RL model window: the Mode (New model, Fine-tune, Evaluate only), the templates of a new model, and the saved models."
          onClick={() => networkWindow.open()}>RL model...</button></div>
      {networkWindow.blocked && <Blocked role="alert" />}
      <NoModeNote m={m} from={null} />
      {(networkError || networkWarning) && <p className={networkError ? 'error' : 'warn'}>Review the settings in RL model.</p>}
      {/* Only while the model is checked: in scratch the last check's suggestion stayed, never asked again (review of 2026-10-01).
          "resume" is no Mode any more (record 7.265): its suggestion is the run itself, a link into the Runs window (Continue...). */}
      {modelChecked && model?.suggestion && model.suggestion.mode !== run.mode && (model.suggestion.mode === 'resume'
        ? <p className="hint mode-suggestion-run">This model's own run can be continued exactly: <button className="text-link mode-suggestion"
            title="Open the Runs window at that run: its Continue... goes on in its own folder." onClick={() => openRunsAt({ run_dir: source.run_dir })}>open it in Runs</button>. {model.suggestion.reason}</p>
        : <p className="warn">Suggested: <button className="text-link mode-suggestion" title={`Set Mode to ${MODE_NAME[model.suggestion.mode] ?? model.suggestion.mode}`}
            onClick={() => set({ mode: model.suggestion!.mode })}>{MODE_NAME[model.suggestion.mode] ?? model.suggestion.mode}</button> - {model.suggestion.reason}
            {model.suggestion.requires_confirmation ? ' (needs your confirmation)' : ''}</p>)}
      <Num label="Concurrent Spectre jobs" value={run.concurrency} onChange={v => set({ concurrency: v })} title="Independent simulation jobs at once. NOT the thread count of one simulation." />
      {circuit?.max_concurrency && run.concurrency > circuit.max_concurrency && <p className="error">This task supports at most {circuit.max_concurrency} jobs.</p>}
      <Num label="Evaluation budget" value={run.max_evaluations} onChange={v => set({ max_evaluations: v })}
        title="NEW candidate evaluations that may START in the whole run, shared by all workers. Baselines, warm-up and failures count. Episode resets do not reset it." />
      <Num label="Random seed" value={run.seed} onChange={v => set({ seed: v })} title="Seed of THIS run. The source model's pretraining seed is recorded separately." />
      <Check label="Stop at the first feasible design" value={run.stop_at_first_feasible} onChange={v => set({ stop_at_first_feasible: v })} />
      {/* The limits a run seldom changes, in one fold (record 7.179, design advice 2): the caps on launches, retries and wall
          time with the two consecutive-failure rules (7.150's "Failure limits"). Its line names the ones that are set. */}
      <details className="limits"><summary>Limits{limitsSet.length > 0 && <span className="hint"> - {limitsSet.join(', ')}</span>}</summary>
        <Num label="Max Spectre launches" nullable value={run.max_spectre_launches} onChange={v => set({ max_spectre_launches: v })} title="Optional hard cap incl. retries and failures." />
        <Num label="Max retries per evaluation" value={run.max_retries ?? 0} onChange={v => set({ max_retries: v })} title="A retry keeps the evaluation_id and costs a launch, not an evaluation." />
        <Num label="Wall-time limit (s)" nullable value={run.max_wall_seconds} onChange={v => set({ max_wall_seconds: v })} />
        <Num label="Pause after N consecutive infrastructure failures" value={run.max_consecutive_infrastructure_failures ?? 3} onChange={v => set({ max_consecutive_infrastructure_failures: v })} />
        <Num label="Stop after N consecutive failed evaluations" value={run.max_consecutive_failures ?? 5} onChange={v => set({ max_consecutive_failures: v })}
          title={'When this many evaluations in a row fail (no valid result), the run stops safely: everything is saved and it ends as "failed", '
            + 'which Continue cannot pick up again. Reward v2.1 scores broken designs and learns from them, so a run exploring a region where many '
            + 'designs break may need a higher limit (1-1000).'} />
      </details>
  </>);
}
