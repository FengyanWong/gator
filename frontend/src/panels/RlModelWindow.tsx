// The RL model window (plan-refactoring C4, out of Right.tsx): the Mode at the top, then that Mode's part - the templates of a
// new model, or the saved models to fine-tune or evaluate. It only draws what useRlModel holds; RunPanel portals it into
// its pop-up window.
import { Fragment } from 'react';
import { copy, Json } from '../api';
import { folderName, plural, short, stamp, taskNameOf } from '../format';
import { RESTORABLE, RESTORABLE_MEANS, RESTORABLE_OLDER, SavedModels } from './ModelChooser';
import { DESIGN_NAME, designName, pointText } from '../lineage';
import { LOADS } from '../savePoint';
import { ComponentList } from './Pdk';
import { Check, LookFold, Num } from './fields';
import { ADVANCED_ROWS, MODE_NAME, MODES, NETWORK_SETTING_LABELS, ORIGIN, INPUT_CHOICES, INPUT_NAMES, REWARD_HELP, REWARD_NAME, TRANSFER_TITLE, inputsChoice,
  newModelChoice, newModelInputs, inputsText } from './rlModelText';
import { NoModeNote } from './RunConfiguration';
import { CompatibilityList, compatibilityMode } from './CompatibilityList';
import type { RlModel } from './useRlModel';
/** The training conditions as Reward and conditions names them (branch record SIF-12): the facts wrote the key ("off"). */
const CONDITIONS: Record<string, string> = { off: 'Nominal only', after_nominal: 'Corners after nominal passes', always: 'Every planned corner' };
/** A saved model's training conditions: the policy, then its plan - nothing more for Nominal only with nothing planned (branch
 *  record SIF-80: "Nominal only; 0 conditions planned" said the one fact twice, the second time as a zero). */
const conditionsText = (contract: Json) => {
  const policy = contract?.condition_policy ?? 'off', planned = contract?.planned_conditions;
  return `${CONDITIONS[policy] ?? policy}${planned == null ? '; plan not recorded' : planned.length ? `; ${plural(planned.length, 'condition')} planned`
    : policy === 'off' ? '' : '; no corners planned'}`;
};
/** A setting's value in the differences table: RWSE as the saved models table writes it (SIF-8), a switch as on/off (branch
 *  record SIF-57: "rwse", "true"). */
const settingValue = (v: Json) => v === 'rwse' ? 'RWSE' : typeof v === 'boolean' ? (v ? 'on' : 'off') : String(v);
/** A saved model's counter in its facts, grouped as the warning below writes "1,500", with its noun in the right number
 *  (branch record SIF-58: "Training 12000 evaluations, 96000 updates, replay 12000"); '?' where a model recorded none. */
const count = (n: Json, word: string) => `${typeof n === 'number' ? n.toLocaleString('en-US') : '?'} ${n === 1 ? word : `${word}s`}`;
/** What the model in use's Restorable allows (review of branch record SIF-80): a full save point is continued exactly only by
 *  the optimizer source that wrote it (record 7.221). The compatibility's digest check says whether it did - a warning when it
 *  did not, then the Runs window's words; no meaning while no compatibility is known (still checking, or not checked). */
const restorableMeans = (capability: string, checks?: Json[]) => {
  if (capability !== 'full_state') return RESTORABLE_MEANS[capability];
  const code = checks?.find(c => c.component === 'optimizer source code digest')?.status;
  return code === 'ok' ? RESTORABLE_MEANS.full_state : code ? RESTORABLE_OLDER : undefined;
};

/** New model's templates (record 7.265): one row per encoder - its sizes and training values as the backend keeps them (the
 *  starting preset, or values edited and saved there), and how many saved models were made from it. A double click or "Use
 *  template" fills the draft's network and training values from it, as one Undo step (`applyEntry`, what choosing an
 *  encoder did until then). */
function TemplatesTable({ settings, encoders, current, runs, onUse }: { settings: Json; encoders: string[]; current: string; runs: Json[]; onUse: (encoder: string) => void }) {
  const made = (encoder: string) => runs.filter(r => r.encoder === encoder && !r.parent && r.model_label && r.run_kind !== 'offline_pretraining').length;
  return (<table className="grid small template-table"><thead><tr>
    <th title="The encoder of the network.">Template</th><th title="Hidden width / attention heads / layers.">Sizes</th>
    <th title="Learner updates per evaluation, starting temperature (initial alpha), discount and learning rate.">Training</th>
    <th title="The starting preset, or values edited and saved in the backend for this encoder.">Values</th>
    <th title="Saved models under the output folder made from this template (new models, not fine-tuned ones).">Models made</th><th className="plain"></th></tr></thead>
    <tbody>{encoders.map(e => { const s = settings?.settings?.[e], n = s?.network ?? {}, a = s?.advanced ?? {}, active = e === current; return (
      <tr key={e} className={`template-row${active ? ' current' : ''}`} aria-current={active ? 'true' : undefined} data-encoder={e} onDoubleClick={() => onUse(e)}>
        {/* "(experimental)" only where the label does not say it already (branch record SIF-8: "Parameter-group attention -
            experimental (experimental)") */}
        <td><b>{s?.label ?? e}</b>{s?.experimental && !/experimental/i.test(s?.label ?? '') && <span className="hint"> (experimental)</span>}</td>
        <td className="numeric">{n.hidden_dim ?? '?'}/{s?.uses_heads === false ? '–' : n.heads ?? '?'}/{n.layers ?? '?'}{n.structural_encoding && n.structural_encoding !== 'none' ? ` · ${String(n.structural_encoding).toUpperCase()}` : ''}</td>
        <td className="numeric">{a.updates_per_transition ?? '?'} updates · alpha {a.initial_alpha ?? '?'} · gamma {a.gamma ?? '?'} · lr {a.learning_rate ?? '?'}</td>
        <td>{s ? ORIGIN[s.origin] ?? s.origin : 'not read yet'}</td>
        <td className="numeric">{made(e)}</td>
        <td>{active ? <b className="ok">in use</b> : <button className="template-use" onClick={() => onUse(e)}
          title={`Use template: the next run's network and training values become the ${s?.label ?? e} template's, as one Undo step.`}>Use template</button>}</td></tr>); })}
    </tbody></table>);
}

/** The training numbers, with the warning about values that leave the search random right above them. In scratch they sit
 * directly below "Nominal device operating points" (user, 2026-10-05: "move the advanced setting to beneath the nominal
 * device op checkbox", record 7.195); a Mode that loads a model shows no network block, so there they close the window -
 * they hold the fine_tune switches. */
function AdvancedFields({ m }: { m: RlModel }) {
  const { adv, setAdv, editAdv, entry, encoder, schema, sacSlow } = m;
  // Branch record SIF-57: the tested values with the labels of their fields below (the warning named "starting temperature"
  // and "updates per evaluation", which no field there carries), and "template", the window's one word for what keeps them
  // (it said "stored per encoder" and "the selected encoder", and no encoder is chosen any more).
  return <>
    {sacSlow.length > 0 && <p className="warn sac-values">With {sacSlow.join(' and ')}, soft actor-critic learned late or not at all in the tests of 2026-10-05:
      with 1 update per evaluation the designs stayed a uniform random search for 1,500 evaluations, and a starting temperature of 0.2 delayed
      learning to about evaluation 1,000. The tested values are 8 updates per evaluation (Updates per transition), starting temperature 0.01 (Initial
      alpha) and discount 0 (Discount gamma), under Advanced.</p>}
    <details className="rl-advanced"><summary>Advanced (kept with the template, like the network sizes)</summary>
      <p className="hint">Alpha learning rate and the tick box below belong to this configuration; the other settings belong to the {DESIGN_NAME[encoder] ?? encoder} template. The algorithm stays soft actor-critic; only its numbers change.</p>
      <Num label="Alpha learning rate" nullable value={adv.alpha_learning_rate} onChange={v => setAdv({ alpha_learning_rate: v })} title="Empty uses the actor learning rate. A separate rate is stored in this configuration." />
      <Check label="Send the next design before learning (faster)" value={adv.update_after_dispatch ?? schema.$defs.AdvancedRL.properties.update_after_dispatch.default ?? true}
        onChange={v => setAdv({ update_after_dispatch: v })}
        title={'Off: after each result the learner makes its updates, then the lane gets its next design. On: the lane gets its next design first '
          + 'and simulates while the learner learns. The number of updates stays the same; each design comes from a policy a few updates older. '
          + 'On by default since record 7.294: on 2 real tasks x 2 seeds learning was not worse and the runs were 18 % shorter (record 7.281 built it).'} />
      {ADVANCED_ROWS.map((fields, i) => {
        const inputs = fields.map(([name, label, title]) => <Num key={name} label={label} title={title}
          value={adv[name] ?? entry?.advanced?.[name] ?? schema.$defs.AdvancedRL.properties[name].default}
          onChange={v => editAdv({ [name]: v })} />);
        return i === 0 ? <Fragment key={i}>{inputs}</Fragment> : <div className="row" key={i}>{inputs}</div>;
      })}
    </details>
  </>;
}

/** The RL model label's box, under "Name of the new model" in New model and as "Name of the model it saves" under Fine-tune's settings. */
function ModelLabelInput({ m }: { m: RlModel }) {
  const { run, set, config } = m;
  return <input className="model-label" value={run.model_label ?? ''} placeholder={config.project.task_name} maxLength={80}
    onChange={e => set({ model_label: e.target.value.trim() ? e.target.value : null })} />;
}

export function RlModelWindow({ m }: { m: RlModel }) {
  const { config, runs, run, set, setAdv, setNet, source, adv, net, networkWindow, error, modelLoading, model, netSettings, netMessage, presetRateUpdated,
    netFields, advFields, encoder, entry, offeredEncoders, usesHeads, usesStructure, applyEntry, chooseList, flush, queueSave, editNet, chooseEncoder,
    settingDifferences, differs, originLabel, budget, starved, loads, noMode, label, savedModel, savedNet, archDiffers, suggested, usingPoint, useSavePoint,
    chooseMode } = m;
  // A saved model chosen closes this window (user request 2026-10-09: "after selecting one target task, model or run, close
  // the pop up window"); a save point that cannot be read leaves it open, with the reason below.
  const chooseModel = (run_dir: string, checkpoint_id: string) => {
    const shown = networkWindow.popup;
    void useSavePoint(run_dir, checkpoint_id).then(ok => { if (ok && shown && !shown.closed) shown.close(); });
  };
  const means = model?.description && restorableMeans(model.description.restoration_capability, model.compatibility?.checks);
  return <section className="panel rl-networks-panel" aria-labelledby="rl-networks-title">
      {/* No close button of its own (user, 2026-10-03: "delete the cross button in RL network window"): the window's own close
          does it, and the settings are kept either way. Record 7.265: the RL model window - the Mode at the top, then that
          Mode's part: the templates of a new model, or the saved models to fine-tune or evaluate. */}
      <div className="rl-networks-heading"><h2 id="rl-networks-title">RL model</h2></div>
      <div className="rl-modes" role="radiogroup" aria-label="Mode">
        {MODES.map(([m, name, help]) => <button key={m} role="radio" aria-checked={run.mode === m} data-mode={m} className={`rl-mode${run.mode === m ? ' active' : ''}`}
          onClick={() => { if (run.mode !== m) chooseMode(m); }} title={`${name}: ${help}. One Undo step.`}>{name}</button>)}
      </div>
      {noMode ? <NoModeNote m={m} from={networkWindow.popup} />
        : <p className="hint rl-mode-help">{MODES.find(([m]) => m === run.mode)?.[2]?.replace(/^./, c => c.toUpperCase())}{loads ? '. The next run uses the network of the model chosen below.' : '.'}</p>}
      {run.mode === 'scratch' && <>
      <h3>Templates</h3>
      <p className="hint">A new model starts from one template: its network and its training values, kept per template in the backend. Editing a value
        below saves it into that template.</p>
      <TemplatesTable settings={netSettings} encoders={offeredEncoders} current={encoder} runs={runs} onUse={chooseEncoder} />
      {!offeredEncoders.includes(encoder) && <p className="error">{DESIGN_NAME[encoder] ?? encoder} is unavailable. Choose an available template. Existing models need their matching historical optimizer version.</p>}
      <h3>The {entry?.label ?? encoder} template, for this run</h3>
      <div className="row template-sizes"><Num label="hidden" value={net.hidden_dim ?? entry?.network?.hidden_dim ?? 32} onChange={v => editNet({ hidden_dim: v })} />
        <Num label="heads" value={net.heads ?? entry?.network?.heads ?? 4} onChange={v => editNet({ heads: v })} disabled={!usesHeads} note={usesHeads ? undefined : 'ignored by this encoder'}
          title={usesHeads ? 'Attention heads. hidden must be divisible by heads.' : 'RGCN does not use attention heads. The number is kept in the checkpoint.'} />
        <Num label="layers" value={net.layers ?? entry?.network?.layers ?? 2} onChange={v => editNet({ layers: v })} /></div>
      {usesStructure && <label>Structural encoding<select className="structural-encoding" value={net.structural_encoding ?? entry?.network?.structural_encoding ?? 'none'}
        onChange={e => editNet({ structural_encoding: e.target.value })}>
        <option value="none">None</option><option value="rwse">Random-walk returns (2, 4, 8, 16 steps)</option></select></label>}
      {entry?.experimental && <p className="hint encoder-experimental">Experimental encoder. Transfer performance and these starting settings have not been validated.</p>}
      {/* A new model's inputs come with its encoder's template (record 7.332; user: "Yes, no box"): one line of text. A box is
          drawn only while the configuration still holds another choice - that choice, and the encoder's own to move to. */}
      {inputsChoice(net) === newModelChoice(encoder)
        ? <p className="hint network-inputs-line" title={TRANSFER_TITLE}>Network inputs: {INPUT_NAMES[newModelChoice(encoder)]} ({inputsText(net).replace(/^.*? - /, '')})</p>
        : <label title={TRANSFER_TITLE}>Network inputs<select className="network-inputs" value={inputsChoice(net)}
          onChange={e => setNet(INPUT_CHOICES[e.target.value] ?? newModelInputs(encoder))}>
          <option value={newModelChoice(encoder)}>{INPUT_NAMES[newModelChoice(encoder)]} (a new model's inputs)</option>
          {inputsChoice(net) === 'custom' ? <option value="custom" disabled>{INPUT_NAMES.custom}</option>
            : <option value={inputsChoice(net)}>{INPUT_NAMES[inputsChoice(net)]} (this configuration's own)</option>}</select></label>}
      <Check label="Nominal device operating points" value={net.operating_points ?? false} onChange={v => setNet({ operating_points: v })}
        title="Measured nominal device values and validity masks. Corner operating points are recorded but never replace the nominal network input. Changing this changes the model input schema." />
      <AdvancedFields m={m} />
      <ComponentList value={net.vocabulary ?? 'standard'} onChoose={v => chooseList(v)} />
      {/* The GATOR baseline and both preset buttons were deleted (record 7.191, user: "Delete the gator baseline in RL networks
          and keep the publication preset, delete two buttons"); the one preset left became the starting preset (7.192). Typing a
          value back to its preset forgets the saved copy. */}
      {entry && <p className="hint in-use">In use: <b>{settingDifferences.length ? 'current run settings' : originLabel}</b></p>}
      {presetRateUpdated && adv.learning_rate === 0.001 && <p className="hint preset-rate-updated" role="status">
        Updated the restored starting preset’s learning rate from 0.0003 to 0.001. Undo in the main window restores the previous value.</p>}
      {/* The template by that word (branch record SIF-57): this box called it "the saved Graph Transformer defaults", with
          "Use saved defaults" / "Save as defaults", in a window whose table and buttons say "template". */}
      {differs && <div className="note network-differences">
        <p className="warn">This run's values differ from the {DESIGN_NAME[encoder] ?? encoder} template ({originLabel}).</p>
        <p className="hint">This run uses the values shown in the controls. A template's values are loaded when you use it; they do not replace an existing configuration on page reload.</p>
        <table className="grid small" aria-label="Network settings differences"><thead><tr><th>Setting</th><th>This run</th><th>Template</th></tr></thead><tbody>
          {settingDifferences.map(row => <tr key={row.field}><td title={row.field}>{NETWORK_SETTING_LABELS[row.field] ?? row.field}</td>
            <td className="numeric">{settingValue(row.current)}</td><td className="numeric">{row.saved == null ? 'Not set' : settingValue(row.saved)}</td></tr>)}
        </tbody></table>
        <div className="row pair"><button onClick={() => applyEntry(entry)} title={`Replace this run's network and Advanced values with the ${DESIGN_NAME[encoder] ?? encoder} template's values, as one Undo step.`}>Use the template's values</button>
          <button onClick={() => { queueSave(net, adv); flush(); }} title={`Keep this run's values and save them into the ${DESIGN_NAME[encoder] ?? encoder} template.`}>Save into the template</button></div>
      </div>}
      {entry?.problem && <p className="warn">{entry.problem}</p>}
      {entry && <details><summary>Where the {DESIGN_NAME[encoder] ?? encoder} values come from</summary>
        <p className="hint">{entry.summary}</p>
        {entry.architecture_reference && <p className="hint">Architecture reference: <a href={entry.architecture_reference.url} target="_blank" rel="noreferrer">{entry.architecture_reference.short}</a>. The starting values are project choices.</p>}
        <table className="grid small"><thead><tr><th>Setting</th><th>Preset</th><th>Basis</th><th>Source and note</th></tr></thead><tbody>
          {/* the settings by the differences table's names, the key in the tooltip, and numbers unpadded (branch record SIF-57:
              "updates_per_transition", "0.0100000"); String() keeps 0.0003 as the Templates table writes it */}
          {[...netFields, ...advFields].map(f => { const p = entry.provenance?.[f]; const ref = p?.source ? netSettings.references?.[p.source] : null; return (
            <tr key={f}><td title={f}>{NETWORK_SETTING_LABELS[f] ?? f.replace(/_/g, ' ')}</td><td className="numeric">{p?.value == null ? '' : String(p.value)}</td><td>{p?.basis}{p?.match === 'closest' ? ', closest network' : ''}</td>
              <td>{ref && <a href={ref.url} target="_blank" rel="noreferrer">{ref.short}</a>} {p?.note}</td></tr>); })}
        </tbody></table>
        <p className="hint">{netSettings.scale_note}</p></details>}
      <h3>Name of the new model</h3>
      <label title={`The name this run's RL model is saved under. Empty: the task's run label (${config.project.task_name}). A name a saved model carries already gets a number: ${label} (2), ${label} (3). A saved model can be renamed in its Details below.`}>RL model label
        <ModelLabelInput m={m} /></label>
      </>}
      {netMessage && (!netMessage.about || netMessage.about === JSON.stringify([run.mode, source.run_dir, source.checkpoint_id]))
        && <p className={`net-message ${netMessage.level === 'error' ? 'error' : netMessage.level === 'warn' ? 'warn' : 'hint'}`}>{netMessage.text}</p>}
      {starved && <p className="warn">Budget {budget} with warm-up {adv.warmup_transitions} and batch size {adv.batch_size}: {budget <= (adv.warmup_transitions ?? 0) ? 'every evaluation is a random warm-up action, so the policy never acts' : 'one batch is never filled, so the network never learns'}.
        Published settings assume thousands of simulations. Lower them under Advanced or raise the budget.</p>}
      {loads && (<>
        <h3>Saved models</h3>
        {/* No model is filled in by itself (record 7.265): the newest one under the RL model label is offered. Its save point
            by its evaluations, the id on hover (branch record SIF-67). */}
        {!source.run_dir && suggested?.run_dir && <p className="note model-suggested">Newest model named <b>{label}</b>: {folderName(String(suggested.run_dir))}
          {suggested.description?.checkpoint_id ? <span title={suggested.description.checkpoint_id}>{`, save point ${pointText(suggested.description.checkpoint_id)}`}</span> : ''}. <button className="model-suggested-use" disabled={usingPoint}
            onClick={() => chooseModel(suggested.run_dir, suggested.description?.checkpoint_id ?? 'latest')}>Use</button></p>}
        {!source.run_dir && <p className="warn model-none-chosen">No saved model is chosen yet: {MODE_NAME[run.mode]} needs one. Use a save point below; this window then closes.</p>}
        <SavedModels source={source} usable={LOADS.includes(run.mode) ? run.mode : null} runs={runs} outputRoot={config.output?.output_root}
          config={config} popup={networkWindow.popup} onUse={chooseModel} />
        {source.run_dir && <><h3>The model in use</h3>
        {modelLoading && <p className="hint" role="status">Checking model compatibility...</p>}
        {error && <p className="error">{error}</p>}
        {model?.description && <table className="grid small model-facts"><tbody>
          {savedNet && <tr className="model-network"><td>Network</td><td><b>{designName(savedNet)}</b>, hidden {savedModel.hidden_dim}, heads {savedModel.heads}{archDiffers || usesHeads ? '' : ' (ignored by this encoder)'}, layers {savedModel.layers}
            <span className="hint"> - this run uses it as it is: a saved model only loads into the network it was trained with.</span></td></tr>}
          {/* The list's name begins the cell, capitalised as every other fact (branch record SIF-80: "device families (11
              kinds)"); the backend's label stays as it is, which the graph view writes inside a sentence. */}
          {model.vocabulary && <tr className="model-components"><td>Components</td><td><b>{String(model.vocabulary.label).replace(/^./, c => c.toUpperCase())}</b>
            <span className="hint"> - the network of this run knows the same list{model.vocabulary.name !== 'standard' && !model.vocabulary.loaded
              ? '; that PDK is not loaded now, which is needed only for Parameters rows on its own parameters' : ''}.</span></td></tr>}
          {/* Branch record SIF-2: the task by its name (the id with its definition's hash in the tooltip), the time as the Runs and
              Tasks windows write it, in this computer's time; numbers without padding; the table's words for Restorable. */}
          <tr><td>Trained on</td><td title={model.description.source_task_id}>{taskNameOf(model.description.source_task_id)}</td></tr>
          <tr><td>Saved</td><td title={`${model.description.created_utc} (UTC)`}>{stamp(model.description.created_utc) ?? model.description.created_utc}</td></tr>
          {/* Branch record SIF-58: the facts below in words - "Schema" named the version of the save point's description,
              "1 planned" did not say what, "enabled" stood against "off", and the counters read "12000 evaluations, replay 12000". */}
          <tr><td>Metadata version</td><td title="The version of the format the save point's description is written in.">{model.description.metadata_version}</td></tr>
          {/* in words, the stored names in the tooltip (branch record SIF-41: it read "constraint_violation_v2; compressed") */}
          <tr><td>Reward</td><td title={`${model.description.contract?.reward_version ?? 'none recorded'}; ${model.description.contract?.reward_settings?.violation_shape ?? 'capped'}`}>
            {REWARD_NAME[model.description.contract?.reward_version ?? ''] ?? (model.description.contract?.reward_version ? String(model.description.contract.reward_version).replace(/_/g, ' ') : 'Legacy nominal')}; violation
            shape {model.description.contract?.reward_settings?.violation_shape ?? 'capped'}</td></tr>
          {/* The weights by the reward block's names, with its tooltips (branch record SIF-80: "Margin bonus weight" here was
              "Tightest-margin bonus weight" there, and no row said what it does). */}
          <tr title={REWARD_HELP.worst_spec_share}><td>Worst hard-spec share</td><td>{short(model.description.contract?.reward_settings?.worst_spec_share ?? 0)}</td></tr>
          <tr title={REWARD_HELP.objective_weight}><td>Objective bonus weight</td><td>{short(model.description.contract?.reward_settings?.objective_weight ?? 0)}</td></tr>
          <tr title={REWARD_HELP.margin_weight}><td>Tightest-margin bonus weight</td><td>{short(model.description.contract?.reward_settings?.margin_weight ?? 0)}</td></tr>
          <tr><td>Conditions</td><td>{conditionsText(model.description.contract)}</td></tr>
          {model.description.contract?.planned_conditions?.length! > 0 && <tr><td>Saved condition plan</td><td>{model.description.contract!.planned_conditions!.map(c => c.corner.id).join(', ')}</td></tr>}
          <tr><td>Operating points</td><td>{savedNet?.operating_points ? 'on' : 'off'}</td></tr>
          <tr className="model-inputs"><td>Network inputs</td><td>{inputsText(savedNet)}</td></tr>
          <tr><td>Training</td><td>{count(model.description.counters.evaluations_committed, 'evaluation')}, {count(model.description.counters.learner_updates, 'learner update')},
            {' '}{count(model.description.counters.replay_size, 'transition')} in replay</td></tr>
          <tr><td>Restorable</td><td><b>{RESTORABLE[model.description.restoration_capability] ?? model.description.restoration_capability}</b>{model.description.missing_components.length ? ` - missing: ${model.description.missing_components.join(', ')}` : ''}
            {means && <span className="hint">{model.description.missing_components.length ? '; ' : ' - '}{means}.</span>}</td></tr>
          <tr><td>Folder</td><td className="path" title="Click to copy" onClick={() => copy(model.description.path)}>{model.description.path}</td></tr>
        </tbody></table>}
        {model?.compatibility_unchecked && <div className="note compat-unchecked"><p><b>{model.compatibility_unchecked.title}</b></p>
          <p>{model.compatibility_unchecked.what}</p><p className="hint">{model.compatibility_unchecked.note}</p>
          <details><summary>Technical details</summary><pre className="small">{model.compatibility_unchecked.technical}</pre></details></div>}
        {/* The Modes in their buttons' words: "no fallback to scratch" and "Frozen actions" named them by their keys, and
            the choice said nothing of what it does (branch record SIF-53). The stored values stay the same. */}
        {model?.compatibility && !archDiffers && <details open={!model.compatibility.compatible}><summary className={model.compatibility.compatible ? '' : 'error'}>Compatibility for {compatibilityMode(model.compatibility.mode)}: {model.compatibility.compatible ? 'compatible' : 'NOT compatible - it cannot be loaded, and a run never falls back to New model'}</summary>
          <CompatibilityList checks={model.compatibility.checks} /></details>}</>}
        <h3>{run.mode === 'frozen' ? 'Evaluate only' : 'Fine-tune'}: its own settings</h3>
        {run.mode === 'frozen' && <label title="Deterministic: each step takes the policy's mean action, so the same state gives the same design. Sampled: each step draws an action from the policy, as in training.">Actions<select value={run.frozen_action ?? 'deterministic'} onChange={e => set({ frozen_action: e.target.value })}><option value="deterministic">Deterministic</option><option value="sampled">Sampled</option></select></label>}
        {run.mode === 'fine_tune' && <>
          {/* What each switch does, as the backend's modes.py does it (branch record SIF-58: no tooltip, so how Freeze
              encoder and Encoder-only transfer differ was said nowhere on the page). The actor and both critics each have
              an encoder. */}
          <Check label="Freeze encoder" value={adv.freeze_encoder} onChange={v => setAdv({ freeze_encoder: v })}
            title="The graph encoders of the actor and the critics keep their loaded weights; only the actor and critic heads learn." />
          <Check label="Encoder-only transfer" value={adv.encoder_only_transfer} onChange={v => setAdv({ encoder_only_transfer: v })}
            title="Only the encoders' weights are loaded; the actor and critic heads start from new random weights." />
          <Check label="Reset critic" value={adv.reset_critic} onChange={v => setAdv({ reset_critic: v })}
            title="The critics and their target copies start from new random weights; the actor keeps its loaded ones." />
          <Check label="Continual learning (inherit weights fine-tuned on a previous test task)" value={run.continual_learning} onChange={v => set({ continual_learning: v })} />
          <label title={`The name the model this run saves goes by. Empty: the task's run label (${config.project.task_name}); a name taken already gets a number.`}>Name of the model it saves
            <ModelLabelInput m={m} /></label></>}
        <AdvancedFields m={m} />
      </>)}
      {run.mode === 'scratch' && <LookFold summary={<summary>Saved models, to look at <span className="hint">- Fine-tune or Evaluate only above uses one</span></summary>}>
        {() => <SavedModels source={source} usable={null} runs={runs} outputRoot={config.output?.output_root} config={config} popup={networkWindow.popup} onUse={chooseModel} />}</LookFold>}
    </section>;
}
