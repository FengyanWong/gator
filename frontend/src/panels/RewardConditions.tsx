// Run configuration's reward and training conditions (plan-refactoring C4, out of Right.tsx). It only draws what useRlModel holds.
import { SIMPLE_REWARD } from '../store';
import type { Json } from '../api';
import { Check, Num } from './fields';
import { REWARD_NAMES } from './rlModelText';
import type { RlModel } from './useRlModel';

export function RewardConditions({ m }: { m: RlModel }) {
  const { run, set, cornerIds, robust, gated, corners, supportsCorners, launchesPerStep, objective, reward, rewardOther, toggleCorner } = m;
  return (<>
      <h3>Reward and conditions</h3>
      {/* From Nominal only, every corner is planned; between the two corner policies the corners chosen stay chosen. Shown where
          corners can be used, or while a saved configuration asks for them (record 7.182): with nothing but Nominal only to choose,
          the choice and its launch table said nothing. */}
      {(supportsCorners || robust) && <><label>Training conditions<select value={run.conditions?.policy ?? 'off'} onChange={e => set({ conditions: {
        policy: e.target.value, corners: e.target.value === 'off' ? [] : !robust || !corners.length ? cornerIds : corners } })}>
        <option value="off">Nominal only</option><option value="after_nominal" disabled={!supportsCorners}>Corners after nominal passes</option><option value="always" disabled={!supportsCorners}>Every planned corner</option></select></label>
      {robust && <div className="training-corners">
        <Check label="nominal" value disabled onChange={() => undefined} title="Nominal is required in every training plan and is the only reset condition." />
        {cornerIds.map(id => <Check key={id} label={id} value={corners.includes(id)}
          disabled={corners.includes(id) && corners.length === 1}
          title={corners.includes(id) && corners.length === 1 ? 'At least one corner is required. Choose Nominal only to turn training corners off.' : id}
          onChange={checked => toggleCorner(id, checked)} />)}
      </div>}
      <table className="grid small reward-costs"><tbody>
        <tr><td>Launches / step</td><td>{gated ? `1 per design that fails nominal, 1 + ${corners.length} per design that passes` : launchesPerStep}</td></tr>
        <tr><td>Launches / reset</td><td>1</td></tr>
        <tr><td>Launch cap</td><td>{run.max_spectre_launches ?? (robust ? 'Required' : 'Not set')}</td></tr>
      </tbody></table></>}
      {/* Each refusal says what to change, by the control's own name (branch record SIF-48): the first named the OTA7 task,
          deleted in record 7.128 with the last corner deck (task_registry.py CORNER_TASKS), and the other two named fields
          that read otherwise in the closed Limits fold. */}
      {robust && !supportsCorners && <p className="error">No task can train at corners now: choose Nominal only under Training conditions.</p>}
      {robust && (run.max_spectre_launches == null || run.max_spectre_launches < 1) && <p className="error">A positive launch cap is required for training corners: set Max Spectre launches under Limits.</p>}
      {robust && (run.max_retries ?? 0) !== 0 && <p className="error">Training corners require zero automatic retries: set Max retries per evaluation under Limits to 0.</p>}
      {/* The reward in one sentence (record 7.183, user: "it is too complicated... is there room for simplification?"). The five
          settings compared in training on 2026-10-05 are fixed for a new configuration (store.ts SIMPLE_REWARD) and said here in
          words; the controls sit in one fold, for reproducing an older run or for an experiment. A configuration that holds other
          values is told which, and offered the tested set on a button - it is never changed by itself. */}
      {/* One line, the sentence one press away (record 7.372): the paragraph took the run column's room. */}
      {rewardOther.length === 0
        ? <details className="more reward-summary"><summary>Reward: the tested one - {objective.length
            ? <>objective <b>{objective.map((t: Json) => `${t.direction_after_feasible} ${t.metric_id}`).join('; ')}</b></> : 'no objective in Specs'}</summary>
          <p className="hint reward-sentence">Reward: minus half the average miss, minus half the worst miss. A design that meets every Specs row
            scores above 0: up to +1 for the room it leaves on its tightest row, and up to +1 more for improving the objective
            row{objective.length ? <> (<b>{objective.map((t: Json) => `${t.direction_after_feasible} ${t.metric_id}`).join('; ')}</b>).</> : ' (none is marked in Specs).'}</p></details>
        : <div className="note reward-other">
            <p className="hint reward-other-count">Reward: {rewardOther.length} setting{rewardOther.length === 1 ? '' : 's'} not as tested.</p>
            <details className="more"><summary>Which</summary>
              <p className="hint">This configuration's reward is not the one a new configuration starts with (the set compared in training on 2026-10-05):
                {' '}{rewardOther.map(k => `${REWARD_NAMES[k]} ${reward[k]} instead of ${SIMPLE_REWARD[k]}`).join('; ')}.</p></details>
            <div className="row"><button className="reward-simple" onClick={() => set({ reward: { ...run.reward, ...SIMPLE_REWARD } })}
              title="Compressed violations, worst hard-spec share 0.5, objective bonus weight 1 with the compressed shape, tightest-margin bonus weight 1. Nothing else changes.">Use the tested reward</button></div>
          </div>}
      <details className="limits reward-advanced"><summary>Advanced{rewardOther.length > 0 && <span className="hint"> - {rewardOther.length} not as tested</span>}</summary>
      <label title="Capped: min(1, distance/scale). Compressed: (distance/scale)/(1 + distance/scale). Neither determines feasibility by reward sign.">Violation shape<select value={run.reward?.violation_shape ?? 'capped'} onChange={e => set({ reward: { ...run.reward, violation_shape: e.target.value } })}>
        <option value="capped">Capped</option><option value="compressed">Compressed</option></select></label>
      {gated && <Num label="Nominal gate band" value={run.reward?.nominal_gate_band ?? 0.5} onChange={v => set({ reward: { ...run.reward, nominal_gate_band: v } })} title="Strictly between 0 and 1. Gate-passing designs always rank above gate-failing designs." />}
      <label>Objective shape<select value={run.reward?.objective_shape ?? 'clipped'} onChange={e => set({ reward: { ...run.reward, objective_shape: e.target.value } })}><option value="clipped">Clipped</option><option value="compressed">Compressed</option></select></label>
      <Num label="Worst hard-spec share" bounded value={run.reward?.worst_spec_share ?? 0} onChange={v => set({ reward: { ...run.reward, worst_spec_share: v } })}
        title="0 to 1. Mix the weighted mean violation with the worst hard-spec violation. At 1, soft violations do not contribute to the penalty." />
      <Num label="Objective bonus weight" bounded value={run.reward?.objective_weight ?? 0} onChange={v => set({ reward: { ...run.reward, objective_weight: v } })}
        title="0 to 1. Applies only to a complete hard-feasible plan and the single objective selected in Specs. Without an objective row the bonus is 0." />
      <p className="hint reward-objective">Objective: {objective.length ? objective.map((t: Json) => `${t.direction_after_feasible} ${t.metric_id}`).join('; ') : 'none'}</p>
      <Num label="Tightest-margin bonus weight" bounded value={run.reward?.margin_weight ?? 0} onChange={v => set({ reward: { ...run.reward, margin_weight: v } })}
        title="Complete hard-feasible plans only. Equality constraints remain mandatory but do not contribute clearance." />
      </details>
  </>);
}
