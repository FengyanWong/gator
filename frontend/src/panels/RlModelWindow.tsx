// The RL model window (plan-refactoring C4, out of Right.tsx): the Mode at the top, then that Mode's part - the templates of a
// new model, or the saved models to fine-tune or evaluate. It only draws what useRlModel holds; RunPanel portals it into
// its pop-up window.
import { Fragment, useEffect } from 'react';
import type { Json } from '../api';
import { useCopied } from './copied';
import { folderName, plural, short, stamp, taskNameOf } from '../format';
import { RESTORABLE, RESTORABLE_MEANS, RESTORABLE_OLDER, SavedModels } from './ModelChooser';
import { DESIGN_NAME, designName, pointText } from '../lineage';
import { LOADS } from '../savePoint';
import { ComponentList } from './Pdk';
import { Check, LookFold, Num } from './fields';
import { ADVANCED_ROWS, MODE_NAME, MODES, NETWORK_SETTING_LABELS, ORIGIN, INPUT_CHOICES, INPUT_NAMES, REWARD_HELP, REWARD_NAME, REWARD_NAMES,
  TRANSFER_TITLE, inputsChoice, newModelChoice, newModelInputs, inputsText } from './rlModelText';
import { NoModeNote } from './RunConfiguration';
import { CompatibilityList, compatibilityMode } from './CompatibilityList';
import type { RlModel } from './useRlModel';
import type { ModelReply } from '../contracts';
import { Icon } from './Icons';
import { undoKey } from '../windows';
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
/** A saved model's counter in its facts, with its noun in the right number (branch record SIF-58: "Training 12000 evaluations,
 *  96000 updates, replay 12000"); '?' where a model recorded none. Written as every count of the page (branch record SIF-117:
 *  grouped from 1,000 up here, its 6,024 learner updates read 6024 in the Training tab and Run status). */
const count = (n: Json, word: string) => typeof n === 'number' ? plural(n, word) : `? ${word}s`;
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
 *  encoder did until then); so does Enter on the row itself, as on a run's row in the Runs window (branch record SIF-121) -
 *  on its Use template, Enter presses that button alone. `differs`: this run's values differ from the current template's
 *  (useRlModel), as the box under its settings, #network-differences, says. */
function TemplatesTable({ settings, encoders, current, differs, runs, onUse }: { settings: Json; encoders: string[]; current: string; differs: boolean;
  runs: Json[]; onUse: (encoder: string) => void }) {
  const made = (encoder: string) => runs.filter(r => r.encoder === encoder && !r.parent && r.model_label && r.run_kind !== 'offline_pretraining').length;
  return (<table className="grid small template-table"><thead><tr>
    <th title="The encoder of the network.">Template</th><th title="Hidden width / attention heads / layers.">Sizes</th>
    <th title="Learner updates per evaluation, starting temperature (initial alpha), discount and learning rate.">Training</th>
    <th title="The starting preset, or values edited and saved in the backend for this encoder.">Values</th>
    <th title="Saved models under the output folder made from this template (new models, not fine-tuned ones).">Models made</th>
    <th className="plain"></th></tr></thead>
    <tbody>{encoders.map(e => { const s = settings?.settings?.[e], n = s?.network ?? {}, a = s?.advanced ?? {}, active = e === current; return (
      <tr key={e} className={`template-row${active ? ' current' : ''}`} aria-current={active ? 'true' : undefined} data-encoder={e}
        onDoubleClick={() => onUse(e)} tabIndex={0} onKeyDown={k => { if (k.key === 'Enter' && k.target === k.currentTarget) onUse(e); }}>
        {/* "(experimental)" only where the label does not say it already (branch record SIF-8: "Parameter-group attention -
            experimental (experimental)") */}
        <td><b>{s?.label ?? e}</b>{s?.experimental && !/experimental/i.test(s?.label ?? '') && <span className="hint"> (experimental)</span>}</td>
        <td className="numeric">{n.hidden_dim ?? '?'}/{s?.uses_heads === false ? '–' : n.heads ?? '?'}/{n.layers ?? '?'}
          {n.structural_encoding && n.structural_encoding !== 'none' ? ` · ${String(n.structural_encoding).toUpperCase()}` : ''}</td>
        <td className="numeric">{a.updates_per_transition ?? '?'} updates · alpha {a.initial_alpha ?? '?'} · gamma {a.gamma ?? '?'} ·
          lr {a.learning_rate ?? '?'}</td>
        <td>{s ? ORIGIN[s.origin] ?? s.origin : 'not read yet'}</td>
        <td className="numeric">{made(e)}</td>
        {/* "in use" only while this run's values are the template's (branch record SIF-140): beside the template's values the
            row said "in use" while the box below said this run's differ - and the box's are the values that run. Its link
            brings that box into view in this window's own document (the table is drawn into the pop-up); its double click
            stays its own, as on the row it would put the template's values back. */}
        <td>{active ? differs ? <span className="warn template-differs"><b>chosen</b> - this run's values differ (<button className="item-link"
          onClick={ev => ev.currentTarget.ownerDocument.getElementById('network-differences')?.scrollIntoView({ block: 'center' })}
          onDoubleClick={ev => ev.stopPropagation()}
          title="Show how this run's values differ from this template: the comparison below, with Use the template's values and Save into the template.">
          see below</button>)</span>
          : <b className="ok">in use</b> : <button className="template-use" onClick={() => onUse(e)}
          title={`Use template (also a double click on its row, or Enter on it): the next run's network and training values become the ${
            s?.label ?? e} template's, as one Undo step.`}>Use template</button>}</td></tr>); })}
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
  // (it said "stored per encoder" and "the selected encoder", and no encoder is chosen any more). Its 1500 and 1000 plain, as
  // the page writes numbers under 10,000 (branch record SIF-117: "1,500", "1,000").
  return <>
    {sacSlow.length > 0 && <p className="warn sac-values" id="sac-values">With {sacSlow.join(' and ')}, soft actor-critic learned late or not at all
      in the tests of 2026-10-05: with 1 update per evaluation the designs stayed a uniform random search for 1500 evaluations, and a starting
      temperature of 0.2 delayed learning to about evaluation 1000. The tested values are 8 updates per evaluation (Updates per transition), starting
      temperature 0.01 (Initial alpha) and discount 0 (Discount gamma), under Advanced.</p>}
    <details className="rl-advanced"><summary>Advanced (kept with the template, like the network sizes)</summary>
      <p className="hint">Alpha learning rate and the tick box below belong to this configuration; the other settings belong
        to the {DESIGN_NAME[encoder] ?? encoder} template. The algorithm stays soft actor-critic; only its numbers change.</p>
      <Num label="Alpha learning rate" nullable value={adv.alpha_learning_rate} onChange={v => setAdv({ alpha_learning_rate: v })}
        title="Empty uses the actor learning rate. A separate rate is stored in this configuration." />
      <Check label="Send the next design before learning (faster)"
        value={adv.update_after_dispatch ?? schema.$defs.AdvancedRL.properties.update_after_dispatch.default ?? true}
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

/** The RL model window, as its parts: the heading with Undo and Redo, the Mode buttons and what the chosen Mode does, then New
 *  model's part (newModelPart) or the part of a Mode that loads a saved model (savedModelsPart), with the window's message and
 *  the budget's warning between them, and under New model the saved models to look at. `undo`, `redo`, `canUndo`, `canRedo`:
 *  the page's one Undo history (branch record SIF-97), as the editors' toolbar has it. Its two hooks, useCopied and
 *  useUndoKeys, run in this order at every draw (React keeps a hook's state by its place in that order); the parts are plain
 *  functions called inline, not components, so the tree React keeps is the one it kept before. */
export function RlModelWindow({ m, undo, redo, canUndo, canRedo }: { m: RlModel; undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean }) {
  const { config, runs, run, source, adv, networkWindow, model, netMessage, netFields, budget, starved, loads, noMode, useSavePoint, chooseMode } = m;
  // A saved model chosen closes this window (user request 2026-10-09: "after selecting one target task, model or run, close
  // the pop up window"); a save point that cannot be read leaves it open, with the reason below.
  const chooseModel = (run_dir: string, checkpoint_id: string) => {
    const shown = networkWindow.popup;
    void useSavePoint(run_dir, checkpoint_id).then(ok => { if (ok && shown && !shown.closed) shown.close(); });
  };
  const means = model?.description && restorableMeans(model.description.restoration_capability, model.compatibility?.checks);
  // A save point a Use could not read: its Details say it under its save points too (branch record SIF-85), not only here.
  const useError = netMessage?.level === 'error' && netMessage.point ? { point: netMessage.point, text: netMessage.text } : null;
  // The model in use's Folder is clicked in this window, so ITS clipboard takes it, and the cell says how it went (SIF-94).
  const copying = useCopied(networkWindow.popup);
  useUndoKeys(networkWindow, undo, redo);
  // The blocks Run configuration's notice can name carry ids (useRlModel's `networkAnchor`): its "RL model..." opens this
  // window at the one its reason is about (branch record SIF-86).
  return <section className="panel rl-networks-panel" aria-labelledby="rl-networks-title">
      {/* No close button of its own (user, 2026-10-03: "delete the cross button in RL network window"): the window's own close
          does it, and the settings are kept either way. Record 7.265: the RL model window - the Mode at the top, then that
          Mode's part: the templates of a new model, or the saved models to fine-tune or evaluate. */}
      {windowHeading(undo, redo, canUndo, canRedo)}
      {modeButtons(run, chooseMode)}
      {noMode ? <NoModeNote m={m} from={networkWindow.popup} />
        : <p className="hint rl-mode-help">{MODES.find(([mode]) => mode === run.mode)?.[2]?.replace(/^./, letter => letter.toUpperCase())}
          {loads ? '. The next run uses the network of the model chosen below.' : '.'}</p>}
      {run.mode === 'scratch' && newModelPart(m)}
      {netMessage && (!netMessage.about || netMessage.about === JSON.stringify([run.mode, source.run_dir, source.checkpoint_id]))
        && <p id="net-message" className={`net-message ${netMessage.level === 'error' ? 'error' : netMessage.level === 'warn' ? 'warn' : 'hint'}`}>
          {netMessage.text}</p>}
      {starved && <p className="warn" id="net-starved">Budget {budget} with warm-up {adv.warmup_transitions} and batch size {adv.batch_size}: {
        budget <= (adv.warmup_transitions ?? 0) ? 'every evaluation is a random warm-up action, so the policy never acts'
          : 'one batch is never filled, so the network never learns'}.
        Published settings assume thousands of simulations. Lower them under Advanced or raise the budget.</p>}
      {loads && savedModelsPart(m, { chooseModel, useError, means, copying })}
      {run.mode === 'scratch' && <LookFold
        summary={<summary>Saved models, to look at <span className="hint">- Fine-tune or Evaluate only above uses one</span></summary>}>
        {() => <SavedModels source={source} usable={null} runs={runs} outputRoot={config.output?.output_root} config={config} netFields={netFields}
          popup={networkWindow.popup} view={m.savedView} refreshRuns={m.refreshRuns} onUse={chooseModel} />}</LookFold>}
    </section>;
}

// ---- its hook, called on every drawing after useCopied, as RlModelWindow calls it ---------------------------------------------

/** Undo and Redo of the window's own (branch record SIF-97): every Mode button, Use template and Use this save point said "One
 *  Undo step", and the only Undo was in the main window's editors - Ctrl+Z here did nothing. The same history as the toolbar's,
 *  with its keys wherever the focus is but in a box that takes typing (windows.ts undoKey); the line under the main window's
 *  formula bar names what it took back. The keys are heard on the window's document, as the main window's are (review of
 *  branch record SIF-97): a handler on the window's section missed every press with the focus on the window's page itself -
 *  just opened, after a click on blank space, and after Use template or Use the template's values, whose button goes away as
 *  it is pressed - the very moment a wrong template is taken back. */
function useUndoKeys(networkWindow: RlModel['networkWindow'], undo: () => void, redo: () => void) {
  const popup = networkWindow.popup;
  useEffect(() => {
    if (!popup) return;
    const page = popup.document;
    const onKey = (e: KeyboardEvent) => { const step = undoKey(e); if (step) { e.preventDefault(); (step === 'undo' ? undo : redo)(); } };
    page.addEventListener('keydown', onKey);
    return () => page.removeEventListener('keydown', onKey);
  }, [popup, undo, redo]);
}

// ---- what it draws: plain functions called inline, not components, so the tree React keeps is the one it kept before ---------

/** The window's heading, with its own Undo and Redo (branch record SIF-97). */
function windowHeading(undo: () => void, redo: () => void, canUndo: boolean, canRedo: boolean) {
  return <div className="rl-networks-heading"><h2 id="rl-networks-title">RL model</h2>
    <span className="rl-networks-undo">
      <button disabled={!canUndo} onClick={undo}
        title={'Undo: The last change to the configuration, from any panel or window - a Mode, a template, a save point '
          + 'chosen here, rows, run and output settings. Ctrl+Z, but in a text box.'}><Icon name="undo" label="Undo" /></button>
      <button disabled={!canRedo} onClick={redo} title="Redo: The change Undo took back. Ctrl+Y or Ctrl+Shift+Z, but in a text box.">
        <Icon name="redo" label="Redo" /></button></span></div>;
}

/** The Mode buttons (record 7.265): New model, Fine-tune and Evaluate only, each one Undo step. */
function modeButtons(run: Json, chooseMode: (mode: string) => void) {
  return <div className="rl-modes" role="radiogroup" aria-label="Mode">
    {MODES.map(([mode, name, help]) => <button key={mode} role="radio" aria-checked={run.mode === mode} data-mode={mode}
      className={`rl-mode${run.mode === mode ? ' active' : ''}`} onClick={() => { if (run.mode !== mode) chooseMode(mode); }}
      title={`${name}: ${help}. One Undo step.`}>{name}</button>)}
  </div>;
}

/** New model's part (record 7.265): the templates; the chosen template's values for this run - its sizes, structural
 *  encoding, network inputs, operating points, Advanced and component list -, the values in use, how this run's differ
 *  from the template's and where the template's come from; and the name of the new model. */
function newModelPart(m: RlModel) {
  const { config, runs, setNet, adv, net, netSettings, presetRateUpdated, encoder, entry, offeredEncoders, usesHeads, usesStructure, chooseList,
    editNet, chooseEncoder, settingDifferences, differs, originLabel, label } = m;
  return <>
    <h3>Templates</h3>
    <p className="hint">A new model starts from one template: its network and its training values, kept per template in the backend. Editing a value
      below saves it into that template.</p>
    <TemplatesTable settings={netSettings} encoders={offeredEncoders} current={encoder} differs={differs} runs={runs} onUse={chooseEncoder} />
    {!offeredEncoders.includes(encoder) && <p className="error" id="net-unavailable">{DESIGN_NAME[encoder] ?? encoder} is unavailable. Choose an
      available template. Existing models need their matching historical optimizer version.</p>}
    <h3>The {entry?.label ?? encoder} template, for this run</h3>
    <div className="row template-sizes"><Num label="hidden" value={net.hidden_dim ?? entry?.network?.hidden_dim ?? 32}
      onChange={value => editNet({ hidden_dim: value })} />
      <Num label="heads" value={net.heads ?? entry?.network?.heads ?? 4} onChange={value => editNet({ heads: value })} disabled={!usesHeads}
        note={usesHeads ? undefined : 'ignored by this encoder'}
        title={usesHeads ? 'Attention heads. hidden must be divisible by heads.'
          : 'RGCN does not use attention heads. The number is kept in the checkpoint.'} />
      <Num label="layers" value={net.layers ?? entry?.network?.layers ?? 2} onChange={value => editNet({ layers: value })} /></div>
    {usesStructure && <label>Structural encoding<select className="structural-encoding"
      value={net.structural_encoding ?? entry?.network?.structural_encoding ?? 'none'} onChange={e => editNet({ structural_encoding: e.target.value })}>
      <option value="none">None</option><option value="rwse">Random-walk returns (2, 4, 8, 16 steps)</option></select></label>}
    {entry?.experimental && <p className="hint encoder-experimental">Experimental encoder. Transfer performance and these starting settings have not
      been validated.</p>}
    {networkInputs(m)}
    <Check label="Nominal device operating points" value={net.operating_points ?? false} onChange={value => setNet({ operating_points: value })}
      title="Measured nominal device values and validity masks. Corner operating points are recorded but never replace the nominal network input. Changing this changes the model input schema." />
    <AdvancedFields m={m} />
    <ComponentList value={net.vocabulary ?? 'standard'} onChoose={value => chooseList(value)} />
    {/* The GATOR baseline and both preset buttons were deleted (record 7.191, user: "Delete the gator baseline in RL networks
        and keep the publication preset, delete two buttons"); the one preset left became the starting preset (7.192). Typing a
        value back to its preset forgets the saved copy. */}
    {entry && <p className="hint in-use">In use: <b>{settingDifferences.length ? 'current run settings' : originLabel}</b></p>}
    {presetRateUpdated && adv.learning_rate === 0.001 && <p className="hint preset-rate-updated" role="status">
      Updated the restored starting preset’s learning rate from 0.0003 to 0.001. Undo restores the previous value.</p>}
    {differs && differencesBox(m)}
    {entry?.problem && <p className="warn" id="template-problem">{entry.problem}</p>}
    {entry && templateSources(m)}
    <h3>Name of the new model</h3>
    <label title={`The name this run's RL model is saved under. Empty: the task's run label (${
      config.project.task_name}). A name a saved model carries already gets a number: ${label} (2), ${
      label} (3). A saved model can be renamed in its Details below.`}>RL model label
      <ModelLabelInput m={m} /></label>
  </>;
}

/** A new model's network inputs come with its encoder's template (record 7.332; user: "Yes, no box"): one line of text. A box
 *  is drawn only while the configuration still holds another choice - that choice, and the encoder's own to move to. */
function networkInputs(m: RlModel) {
  const { setNet, net, encoder } = m;
  return inputsChoice(net) === newModelChoice(encoder)
    ? <p className="hint network-inputs-line"
      title={TRANSFER_TITLE}>Network inputs: {INPUT_NAMES[newModelChoice(encoder)]} ({inputsText(net).replace(/^.*? - /, '')})</p>
    : <label title={TRANSFER_TITLE}>Network inputs<select className="network-inputs" value={inputsChoice(net)}
      onChange={e => setNet(INPUT_CHOICES[e.target.value] ?? newModelInputs(encoder))}>
      <option value={newModelChoice(encoder)}>{INPUT_NAMES[newModelChoice(encoder)]} (a new model's inputs)</option>
      {inputsChoice(net) === 'custom' ? <option value="custom" disabled>{INPUT_NAMES.custom}</option>
        : <option value={inputsChoice(net)}>{INPUT_NAMES[inputsChoice(net)]} (this configuration's own)</option>}</select></label>;
}

/** How this run's values differ from its template's (#network-differences, which the Templates table's "see below" brings
 *  into view), with Use the template's values and Save into the template. The template by that word (branch record SIF-57):
 *  this box called it "the saved Graph Transformer defaults", with "Use saved defaults" / "Save as defaults", in a window
 *  whose table and buttons say "template". */
function differencesBox(m: RlModel) {
  const { adv, net, encoder, entry, applyEntry, flush, queueSave, settingDifferences, originLabel } = m;
  return <div className="note network-differences" id="network-differences">
    <p className="warn">This run's values differ from the {DESIGN_NAME[encoder] ?? encoder} template ({originLabel}).</p>
    <p className="hint">This run uses the values shown in the controls. A template's values are loaded when you use it; they do not replace an existing
      configuration on page reload.</p>
    <table className="grid small" aria-label="Network settings differences"><thead><tr><th>Setting</th><th>This run</th><th>Template</th></tr></thead><tbody>
      {settingDifferences.map(row => <tr key={row.field}><td title={row.field}>{NETWORK_SETTING_LABELS[row.field] ?? row.field}</td>
        <td className="numeric">{settingValue(row.current)}</td><td className="numeric">{row.saved == null ? 'Not set' : settingValue(row.saved)}</td></tr>)}
    </tbody></table>
    <div className="row pair"><button onClick={() => applyEntry(entry)}
      title={`Replace this run's network and Advanced values with the ${DESIGN_NAME[encoder] ?? encoder} template's values, as one Undo step.`}>
      Use the template's values</button>
      <button onClick={() => { queueSave(net, adv); flush(); }}
        title={`Keep this run's values and save them into the ${DESIGN_NAME[encoder] ?? encoder} template.`}>Save into the template</button></div>
  </div>;
}

/** Where the template's values come from: its summary and architecture reference, then each setting's preset, basis, source
 *  and note. */
function templateSources(m: RlModel) {
  const { netSettings, netFields, advFields, encoder, entry } = m;
  return <details><summary>Where the {DESIGN_NAME[encoder] ?? encoder} values come from</summary>
    <p className="hint">{entry.summary}</p>
    {entry.architecture_reference && <p className="hint">Architecture reference: <a href={entry.architecture_reference.url} target="_blank"
      rel="noreferrer">{entry.architecture_reference.short}</a>. The starting values are project choices.</p>}
    <table className="grid small"><thead><tr><th>Setting</th><th>Preset</th><th>Basis</th><th>Source and note</th></tr></thead><tbody>
      {/* the settings by the differences table's names, the key in the tooltip, and numbers unpadded (branch record SIF-57:
          "updates_per_transition", "0.0100000"); String() keeps 0.0003 as the Templates table writes it */}
      {[...netFields, ...advFields].map(field => {
        const provenance = entry.provenance?.[field];
        const ref = provenance?.source ? netSettings.references?.[provenance.source] : null;
        return (
          <tr key={field}><td title={field}>{NETWORK_SETTING_LABELS[field] ?? field.replace(/_/g, ' ')}</td>
            <td className="numeric">{provenance?.value == null ? '' : String(provenance.value)}</td>
            <td>{provenance?.basis}{provenance?.match === 'closest' ? ', closest network' : ''}</td>
            <td>{ref && <a href={ref.url} target="_blank" rel="noreferrer">{ref.short}</a>} {provenance?.note}</td></tr>);
      })}
    </tbody></table>
    <p className="hint">{netSettings.scale_note}</p></details>;
}

/** The window's own values its parts draw with, beside the RL model's (`m`): the choice of a saved model, which closes the
 *  window (`chooseModel`), the save point a Use could not read (`useError`), what the model in use's Restorable allows
 *  (`means`) and the copy of its Folder (`copying`). */
type WindowValues = { chooseModel: (run_dir: string, checkpoint_id: string) => void; useError: { point: string; text: string } | null;
  means: string | undefined; copying: ReturnType<typeof useCopied> };

/** The part of a Mode that loads a saved model (Fine-tune, Evaluate only): the newest model under the RL model label while
 *  none is chosen, the saved models, the model in use, and the Mode's own settings with Advanced. */
function savedModelsPart(m: RlModel, { chooseModel, useError, means, copying }: WindowValues) {
  const { config, runs, run, set, setAdv, source, adv, networkWindow, netFields, suggested, usingPoint } = m;
  return <>
    <h3>Saved models</h3>
    {!source.run_dir && suggested?.run_dir && suggestedModel(m, chooseModel)}
    {/* The row's double click, and its Enter since branch record SIF-121, named where the choice is asked for: the page said
        neither, so the row's Enter would use a model unannounced. SavedModels draws the line where it stood (branch record
        SIF-140): with no saved model listed, it says what to do instead of pointing at save points below. */}
    <SavedModels source={source} usable={LOADS.includes(run.mode) ? run.mode : null} runs={runs} outputRoot={config.output?.output_root}
      config={config} netFields={netFields} popup={networkWindow.popup} view={m.savedView} refreshRuns={m.refreshRuns} onUse={chooseModel}
      usingPoint={usingPoint} useError={useError}
      noneChosen={source.run_dir ? undefined : `No saved model is chosen yet: ${
        MODE_NAME[run.mode]} needs one. Use a save point below (a model's newest: a double click on its row, or Enter on it); this window then closes.`} />
    {source.run_dir && modelInUse(m, means, copying)}
    {/* The Mode by rlModelText's name (review of branch record SIF-141): the header's list of blocking issues names this
        heading, for Fine-tune's switches, by the same one. */}
    <h3>{MODE_NAME[run.mode === 'frozen' ? 'frozen' : 'fine_tune']}: its own settings</h3>
    {run.mode === 'frozen' && <label
      title="Deterministic: each step takes the policy's mean action, so the same state gives the same design. Sampled: each step draws an action from the policy, as in training.">
      Actions<select value={run.frozen_action ?? 'deterministic'} onChange={e => set({ frozen_action: e.target.value })}>
      <option value="deterministic">Deterministic</option><option value="sampled">Sampled</option></select></label>}
    {run.mode === 'fine_tune' && <>
      {/* What each switch does, as the backend's modes.py does it (branch record SIF-58: no tooltip, so how Freeze
          encoder and Encoder-only transfer differ was said nowhere on the page). The actor and both critics each have
          an encoder. */}
      <Check label="Freeze encoder" value={adv.freeze_encoder} onChange={value => setAdv({ freeze_encoder: value })}
        title="The graph encoders of the actor and the critics keep their loaded weights; only the actor and critic heads learn." />
      <Check label="Encoder-only transfer" value={adv.encoder_only_transfer} onChange={value => setAdv({ encoder_only_transfer: value })}
        title="Only the encoders' weights are loaded; the actor and critic heads start from new random weights." />
      <Check label="Reset critic" value={adv.reset_critic} onChange={value => setAdv({ reset_critic: value })}
        title="The critics and their target copies start from new random weights; the actor keeps its loaded ones." /></>}
    {/* In Evaluate only too (review of branch record SIF-103): its run reads it as Fine-tune's does - runs.py `_source_model`
        refuses a source itself fine-tuned on a test task unless it is on - and this Mode had no box, so one left on from a
        Fine-tune was unseen and could not be unticked here, nor ticked when the refusal asks for it. */}
    <Check label="Continual learning (inherit weights fine-tuned on a previous test task)" value={run.continual_learning}
      onChange={value => set({ continual_learning: value })}
      title={'Off: a saved model that was itself fine-tuned on a test task (Split "Test" under Research experiments, Transfer study) is refused, '
        + 'so each test task starts from the fixed source model. On: it is loaded, as continual learning.'} />
    {run.mode === 'fine_tune' && <label
      title={`The name the model this run saves goes by. Empty: the task's run label (${config.project.task_name}); a name taken already gets a number.`}>
      Name of the model it saves
      <ModelLabelInput m={m} /></label>}
    <AdvancedFields m={m} />
  </>;
}

/** The newest model saved under the RL model label, offered with its Use: no model is filled in by itself (record 7.265). Its
 *  save point by its evaluations, the id on hover (branch record SIF-67). */
function suggestedModel(m: RlModel, chooseModel: WindowValues['chooseModel']) {
  const { label, suggested, usingPoint } = m;
  return <p className="note model-suggested">Newest model named <b>{label}</b>: {folderName(String(suggested.run_dir))}
    {suggested.description?.checkpoint_id
      ? <span title={suggested.description.checkpoint_id}>{`, save point ${pointText(suggested.description.checkpoint_id)}`}</span>
      : ''}. <button className="model-suggested-use" disabled={!!usingPoint}
      onClick={() => chooseModel(suggested.run_dir, suggested.description?.checkpoint_id ?? 'latest')}>Use</button></p>;
}

/** The model in use: whether it is being checked or could not be, its facts, and its compatibility with this run - or why
 *  that could not be checked. */
function modelInUse(m: RlModel, means: WindowValues['means'], copying: WindowValues['copying']) {
  const { error, modelLoading, model, archDiffers } = m;
  return <><h3>The model in use</h3>
    {modelLoading && <p className="hint" role="status">Checking model compatibility...</p>}
    {error && <p className="error" id="net-check-error">{error}</p>}
    {model?.description && modelFacts(m, model, means, copying)}
    {model?.compatibility_unchecked && <div className="note compat-unchecked"><p><b>{model.compatibility_unchecked.title}</b></p>
      <p>{model.compatibility_unchecked.what}</p><p className="hint">{model.compatibility_unchecked.note}</p>
      <details><summary>Technical details</summary><pre className="small">{model.compatibility_unchecked.technical}</pre></details></div>}
    {/* The Modes in their buttons' words: "no fallback to scratch" and "Frozen actions" named them by their keys, and
        the choice said nothing of what it does (branch record SIF-53). The stored values stay the same. */}
    {model?.compatibility && !archDiffers && <details id="net-compat" open={!model.compatibility.compatible}>
      <summary className={model.compatibility.compatible ? '' : 'error'}>Compatibility for {compatibilityMode(model.compatibility.mode)}: {
        model.compatibility.compatible ? 'compatible' : 'NOT compatible - it cannot be loaded, and a run never falls back to New model'}</summary>
      <CompatibilityList checks={model.compatibility.checks} /></details>}</>;
}

/** The model in use's facts (`model`, once its description is known): its network and component list, the task it was
 *  trained on and when it was saved, its reward and conditions, its inputs and training, what it can be restored to, and its
 *  folder. */
function modelFacts(m: RlModel, model: ModelReply, means: WindowValues['means'], copying: WindowValues['copying']) {
  const { usesHeads, savedModel, savedNet, archDiffers } = m;
  return <table className="grid small model-facts"><tbody>
    {savedNet && <tr className="model-network"><td>Network</td>
      <td><b>{designName(savedNet)}</b>, hidden {savedModel.hidden_dim}, heads {savedModel.heads}
        {archDiffers || usesHeads ? '' : ' (ignored by this encoder)'}, layers {savedModel.layers}
        <span className="hint"> - this run uses it as it is: a saved model only loads into the network it was trained with.</span></td></tr>}
    {/* The list's name begins the cell, capitalised as every other fact (branch record SIF-80: "device families (11
        kinds)"); the backend's label stays as it is, which the graph view writes inside a sentence. */}
    {model.vocabulary && <tr className="model-components"><td>Components</td>
      <td><b>{String(model.vocabulary.label).replace(/^./, letter => letter.toUpperCase())}</b>
        <span className="hint"> - the network of this run knows the same list{model.vocabulary.name !== 'standard' && !model.vocabulary.loaded
          ? '; that PDK is not loaded now, which is needed only for Parameters rows on its own parameters' : ''}.</span></td></tr>}
    {/* Branch record SIF-2: the task by its name (the id with its definition's hash in the tooltip), the time as the Runs and
        Tasks windows write it, in this computer's time; numbers without padding; the table's words for Restorable. */}
    <tr><td>Trained on</td><td title={model.description.source_task_id}>{taskNameOf(model.description.source_task_id)}</td></tr>
    <tr><td>Saved</td><td title={`${model.description.created_utc} (UTC)`}>{stamp(model.description.created_utc) ?? model.description.created_utc}</td></tr>
    {/* Branch record SIF-58: the facts below in words - "Schema" named the version of the save point's description,
        "1 planned" did not say what, "enabled" stood against "off", and the counters read "12000 evaluations, replay 12000". */}
    <tr><td>Metadata version</td>
      <td title="The version of the format the save point's description is written in.">{model.description.metadata_version}</td></tr>
    {rewardFact(m, model)}
    {/* The weights by the reward block's names, with its tooltips (branch record SIF-80: "Margin bonus weight" here was
        "Tightest-margin bonus weight" there, and no row said what it does); the objective shape and the gate band too,
        the two of its six fields the facts left out (branch record SIF-103), the shape by the block's option names. */}
    <tr title={REWARD_HELP.worst_spec_share}><td>Worst hard-spec share</td>
      <td>{short(model.description.contract?.reward_settings?.worst_spec_share ?? 0)}</td></tr>
    <tr title={REWARD_HELP.objective_weight}><td>Objective bonus weight</td>
      <td>{short(model.description.contract?.reward_settings?.objective_weight ?? 0)}</td></tr>
    <tr title={REWARD_HELP.objective_shape}><td>Objective shape</td>
      <td>{String(model.description.contract?.reward_settings?.objective_shape ?? 'clipped').replace(/^./, letter => letter.toUpperCase())}</td></tr>
    <tr title={REWARD_HELP.margin_weight}><td>Tightest-margin bonus weight</td>
      <td>{short(model.description.contract?.reward_settings?.margin_weight ?? 0)}</td></tr>
    <tr title={REWARD_HELP.nominal_gate_band}><td>Nominal gate band</td>
      <td>{short(model.description.contract?.reward_settings?.nominal_gate_band ?? 0.5)}</td></tr>
    <tr><td>Conditions</td><td>{conditionsText(model.description.contract)}</td></tr>
    {model.description.contract?.planned_conditions?.length! > 0 && <tr><td>Saved condition plan</td>
      <td>{model.description.contract!.planned_conditions!.map(condition => condition.corner.id).join(', ')}</td></tr>}
    <tr><td>Operating points</td><td>{savedNet?.operating_points ? 'on' : 'off'}</td></tr>
    <tr className="model-inputs"><td>Network inputs</td><td>{inputsText(savedNet)}</td></tr>
    <tr><td>Training</td>
      <td>{count(model.description.counters.evaluations_committed, 'evaluation')}, {count(model.description.counters.learner_updates, 'learner update')},
      {' '}{count(model.description.counters.replay_size, 'transition')} in replay</td></tr>
    <tr><td>Restorable</td>
      <td><b>{RESTORABLE[model.description.restoration_capability] ?? model.description.restoration_capability}</b>
        {model.description.missing_components.length ? ` - missing: ${model.description.missing_components.join(', ')}` : ''}
        {means && <span className="hint">{model.description.missing_components.length ? '; ' : ' - '}{means}.</span>}</td></tr>
    <tr><td>Folder</td><td className="path" title="Click to copy" onClick={() => void copying.copyText(model.description.path)}>
      {model.description.path}{copying.word(model.description.path)}</td></tr>
  </tbody></table>;
}

/** The model in use's reward, in words, the stored names in the tooltip (branch record SIF-41: it read
 *  "constraint_violation_v2; compressed"), and in Fine-tune, while the next run's differs, "Use this model's reward". */
function rewardFact(m: RlModel, model: ModelReply) {
  const { run, reward, savedReward, rewardApart, useModelReward } = m;
  return <tr><td>Reward</td>
    <td title={`${model.description.contract?.reward_version ?? 'none recorded'}; ${model.description.contract?.reward_settings?.violation_shape ?? 'capped'}`}>
      {REWARD_NAME[model.description.contract?.reward_version ?? '']
        ?? (model.description.contract?.reward_version ? String(model.description.contract.reward_version).replace(/_/g, ' ')
          : 'Legacy nominal')}; violation
      shape {model.description.contract?.reward_settings?.violation_shape ?? 'capped'}
      {/* Branch record SIF-103: Fine-tune keeps the critics only with the model's reward, which had to be typed field by
          field into the main page's Reward and conditions. Shown only while the next run's differs; one Undo step. */}
      {run.mode === 'fine_tune' && savedReward && rewardApart.length > 0 && <> - <button className="text-link reward-from-model"
        onClick={useModelReward}
        title={`Use this model's reward: the next run's reward becomes this model's - ${rewardApart.map(field =>
          `${REWARD_NAMES[field]} ${short(savedReward[field])} instead of ${short(reward[field])}`).join('; ')} - as one Undo step. `
          + 'Fine-tune keeps the model\'s critics only when the reward and the training conditions both match; the conditions are not changed here (Reward and conditions on the main page).'}>
        Use this model's reward</button></>}</td></tr>;
}
