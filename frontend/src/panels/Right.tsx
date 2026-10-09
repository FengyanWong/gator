import { SIMPLE_REWARD, useRequest } from '../store';
import { Fragment, memo, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, copy, Json, num } from '../api';
import { folderName } from '../format';
import { modelNameAt, SavedModels } from './ModelChooser';
import { ENCODER_SHORT, pointEvaluations } from '../lineage';
import { openRunsAt } from '../openAt';
import { LOADS, NETWORK_FIELDS, networkOf, pick, readSavePoint, withSavePoint } from '../savePoint';
import { ComponentList } from './Pdk';
import { BLOCKED, usePopupWindow } from './popupWindow';
import { PRESET_RATE_KEY, RL_MODEL_WINDOW } from '../contract';
import { Check, LookFold, Module, Num } from './fields';

// Settings stored per encoder in the backend (src/gator_workbench/network_presets.py). The lists are
// only a fallback for the moment before the backend answers; the backend's own lists are used afterwards.
type NumberField = readonly [name: string, label: string, title?: string];
const ADVANCED_ROWS: NumberField[][] = [
  [
    ['learning_rate', 'Learning rate'],
    ['batch_size', 'Batch size', 'A learner update needs this many stored transitions.'],
    ['warmup_transitions', 'Warm-up transitions', 'Random actions until this many transitions are stored. They count against the budget.'],
    ['update_every', 'Update every N transitions'],
    ['updates_per_transition', 'Updates per transition (UTD)'],
    ['episode_length', 'Episode length'],
    ['replay_capacity', 'Replay capacity'],
  ],
  [
    ['gamma', 'Discount gamma'],
    ['tau', 'Target mixing tau'],
  ],
  [
    ['initial_alpha', 'Initial alpha', 'Starting entropy temperature of soft actor-critic. It is learned afterwards.'],
    ['target_entropy_per_action', 'Target entropy / action'],
    ['max_grad_norm', 'Max grad norm'],
  ],
];

const NETWORK_SETTING_LABELS: Record<string, string> = {
  hidden_dim: 'Hidden width', heads: 'Heads', layers: 'Layers', structural_encoding: 'Structural encoding',
  ...Object.fromEntries(ADVANCED_ROWS.flat().map(([name, label]) => [name, label])),
};

/** The five reward settings a new configuration fixes (store.ts SIMPLE_REWARD), as the reward block names them. */
const REWARD_NAMES: Record<string, string> = { violation_shape: 'violation shape', worst_spec_share: 'worst hard-spec share',
  objective_weight: 'objective bonus weight', objective_shape: 'objective shape', margin_weight: 'tightest-margin bonus weight' };

/** The Mode, in the RL model window (record 7.265; plan "RL model window": "Mode selection should be merged in to load model.
 *  Scratch mode will ask you to create a new model from the default templates. fine-tune and evaluate load existing ones").
 *  `resume` is no choice: a run is continued from Runs or Run status (Continue..., record 7.261). */
const MODES: [string, string, string][] = [
  ['scratch', 'New model', 'a new RL model, made from one of the templates below; it starts from random weights'],
  ['fine_tune', 'Fine-tune', 'a saved model keeps learning, in a new run'],
  ['frozen', 'Evaluate only', 'a saved model is used as it is, with no learning'],
];
export const MODE_NAME: Record<string, string> = { scratch: 'New model', fine_tune: 'Fine-tune', frozen: 'Evaluate only', resume: 'no Mode chosen' };
// Where an encoder's settings come from. The backend still calls it `publication`; since record 7.192 it is the network size
// from publications with every training value of the runs that learned on GATOR circuits (user: "keep this as the starting
// preset").
const ORIGIN: Record<string, string> = { publication: 'starting preset', custom: 'edited, saved in the backend' };

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
        <td><b>{s?.label ?? e}</b>{s?.experimental && <span className="hint"> (experimental)</span>}</td>
        <td className="numeric">{n.hidden_dim ?? '?'}/{s?.uses_heads === false ? '–' : n.heads ?? '?'}/{n.layers ?? '?'}{n.structural_encoding && n.structural_encoding !== 'none' ? ` · ${n.structural_encoding}` : ''}</td>
        <td className="numeric">{a.updates_per_transition ?? '?'} updates · alpha {a.initial_alpha ?? '?'} · gamma {a.gamma ?? '?'} · lr {a.learning_rate ?? '?'}</td>
        <td>{s ? ORIGIN[s.origin] ?? s.origin : 'not read yet'}</td>
        <td className="numeric">{made(e)}</td>
        <td>{active ? <b className="ok">in use</b> : <button className="template-use" onClick={() => onUse(e)}
          title={`Use template: the next run's network and training values become the ${s?.label ?? e} template's, as one Undo step.`}>Use template</button>}</td></tr>); })}
    </tbody></table>);
}


/** What Start would start, as far as Run configuration knows it (record 7.269): the Mode with its model and save point, and the
 *  network in short. The page adds the task and the budget for the header's "Next" line. */
export type NextModel = { model: string; network: string };

function RunPanelBody({ config, setConfig, runs, circuit, schema, onNext }: { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; circuit: Json; schema: Json;
  onNext?: (next: NextModel) => void }) {
  // A configuration without a Mode (a task's starter rows, an old file) is New model, as the backend reads it (schema default).
  const run = config.run.mode ? config.run : { ...config.run, mode: 'scratch' };
  const set = (fields: Json, record = true) => setConfig(c => ({ ...c, run: { ...c.run, ...fields } }), record);
  const setAdv = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, advanced: { ...(c.run.advanced ?? {}), ...fields } } }));
  const setNet = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...fields } } }));
  const source = run.model_source ?? {};
  const adv = run.advanced ?? {};
  const net = run.network ?? {};
  // Keep the configuration, preset writes and compatibility checks here even when the window is closed.
  const networkWindow = usePopupWindow('gator-rl-networks', {
    title: RL_MODEL_WINDOW, features: 'popup,width=1180,height=920',
    rootId: 'rl-networks-root', rootClass: 'rl-networks-window', closeOnUnmount: true,
  });

  // Only a Mode that loads the model asks about it: a model_source left over from fine_tune is ignored in scratch, and
  // was compiled and checked after every edit there all the same (audit 2026-09-30).
  // A draft that still says resume (record 7.267) has no Mode chosen: it asks about no model either.
  const modelChecked = LOADS.includes(run.mode) && !!source.run_dir;
  const { value: fresh, error, loading: modelLoading } = useRequest<Json>(signal => api.model(source.run_dir, source.checkpoint_id ?? 'latest', config, signal),
    [JSON.stringify([config.circuit, config.parameters, config.targets, config.measurements, run.mode, source,
      run.connection_profile_id, run.seed, run.network, run.advanced, run.reward, run.conditions, config.research?.split])],
    { enabled: modelChecked, delay: 500 });     // 0.5 s after the last edit, as validation (record 7.275: at 0.25 s a check - a compile - went at almost every pause in typing)
  // While the SAME saved model is checked again after an edit (0.5 s and a compile), what is known about it - its facts,
  // network, component list, structure and graph view - stays; only the compatibility verdict waits for the new answer
  // (an old "compatible" is never shown while checking, record 7.96). The whole block used to vanish and come back after
  // every edit, an open compatibility list closed, and an open network structure read the saved tensors again.
  const modelKey = `${source.run_dir}|${source.checkpoint_id ?? 'latest'}`;
  const lastModel = useRef<{ key: string; value: Json } | null>(null);
  if (fresh?.description && lastModel.current?.value !== fresh) lastModel.current = { key: modelKey, value: fresh };
  const model: Json = fresh ?? (!error && lastModel.current?.key === modelKey
    ? { ...lastModel.current.value, compatibility: null, compatibility_unchecked: null } : null);
  const cornerIds: string[] = schema.$defs.ConditionsConfig.properties.corners.items.enum;
  const robust = (run.conditions?.policy ?? 'off') !== 'off';
  const gated = run.conditions?.policy === 'after_nominal';
  const corners: string[] = run.conditions?.corners ?? [];
  const supportsCorners = circuit?.loaded && circuit?.task_key === config.circuit?.task_id && circuit?.training_capabilities?.corners === true;
  const launchesPerStep = robust ? 1 + corners.length : 1;
  const objective = (config.targets ?? []).filter((t: Json) => t.active !== false && t.direction_after_feasible && t.direction_after_feasible !== 'none');
  // The reward this configuration runs - with what the schema fills in for a field it leaves out - and where it differs from
  // the set a new configuration starts with, the one compared in training on 2026-10-05 (record 7.183).
  const reward: Json = { violation_shape: 'capped', worst_spec_share: 0, objective_weight: 0, objective_shape: 'clipped', margin_weight: 0, ...(run.reward ?? {}) };
  const rewardOther = Object.keys(SIMPLE_REWARD).filter(k => reward[k] !== SIMPLE_REWARD[k]);
  const toggleCorner = (id: string, checked: boolean) => set({ conditions: { ...run.conditions,
    // Re-adding a corner follows schema order, so toggling it back restores the original plan.
    corners: checked ? cornerIds.filter(c => c === id || corners.includes(c)) : corners.filter(c => c !== id) } });

  // Per-encoder settings live in the backend: choosing an encoder READS its settings, editing a value WRITES them back
  // for that encoder. The configuration always carries explicit values, so what is shown is what runs.
  const [netSettings, setNetSettings] = useState<Json>(null);
  // `about`: the Mode and saved model a message is about - it is shown only while they are still the ones chosen.
  const [netMessage, setNetMessage] = useState<{ level: string; text: string; about?: string } | null>(null);
  const [presetRateUpdated, setPresetRateUpdated] = useState(false);
  const pending = useRef<{ encoder: string; body: Json } | null>(null);
  const netRevision = useRef(0);
  const writing = useRef<Promise<void>>(Promise.resolve());
  const timer = useRef<number | undefined>(undefined);
  const netFields: string[] = netSettings?.network_fields ?? NETWORK_FIELDS;
  const advFields: string[] = netSettings?.advanced_fields ?? ADVANCED_ROWS.flat().map(([name]) => name);
  const encoder: string = net.encoder_type ?? netSettings?.default_encoder ?? 'graph_transformer';
  const currentNetwork = useRef({ encoder, mode: run.mode, net, adv });
  currentNetwork.current = { encoder, mode: run.mode, net, adv };
  const networkKey = (mode: string, network: Json, advanced: Json) => JSON.stringify([mode, network, advanced]);
  const currentReply = (revision: number, name: string, expected?: string) => netRevision.current === revision
    && currentNetwork.current.encoder === name && currentNetwork.current.mode === run.mode
    && (expected === undefined || expected === networkKey(currentNetwork.current.mode, currentNetwork.current.net, currentNetwork.current.adv));
  const entry: Json = netSettings?.settings?.[encoder] ?? null;
  const offeredEncoders: string[] = netSettings?.encoders ?? Object.keys(ENCODER_SHORT);
  const usesHeads: boolean = entry ? !!entry.uses_heads : encoder !== 'rgcn';
  const usesStructure: boolean = entry ? !!entry.supports_structural_encoding : ['graph_gps', 'group_cross_attention'].includes(encoder);
  const remember = (e: Json) => setNetSettings((s: Json) => s && ({ ...s, settings: { ...s.settings, [e.encoder_type]: e } }));
  // The component list is not a per-encoder setting: another encoder keeps the list that was chosen.
  const keepList = (network: Json) => ({ operating_points: network?.operating_points ?? false,
    ...(network?.vocabulary && network.vocabulary !== 'standard' ? { vocabulary: network.vocabulary } : {}) });
  const applyEntry = (e: Json, record = true) => setConfig(c => ({ ...c, run: { ...c.run,
    network: { ...keepList(c.run.network), encoder_type: e.encoder_type, ...e.network }, advanced: { ...(c.run.advanced ?? {}), ...e.advanced } } }), record);
  // The standard list is written as no field at all: that is what every configuration had before, and a server that was
  // not restarted yet still accepts it.
  const chooseList = (value: string, record = true) => setConfig(c => {
    const { vocabulary: _old, ...rest } = c.run.network ?? {};
    return { ...c, run: { ...c.run, network: value === 'standard' ? rest : { ...rest, vocabulary: value } } };
  }, record);
  const flush = (): Promise<void> => {
    window.clearTimeout(timer.current);
    const job = pending.current; pending.current = null;
    if (!job) return writing.current;
    const revision = netRevision.current;
    writing.current = writing.current.then(() => api.saveNetworkSettings(job.encoder, job.body))
      .then(e => { remember(e); if (currentReply(revision, job.encoder)) setNetMessage({ level: 'ok', text: `Saved in the backend as the ${e.encoder_type} setting.` }); })
      .catch(e => { if (currentReply(revision, job.encoder)) setNetMessage({ level: 'error', text: `Not saved in the backend: ${e.message}` }); });
    return writing.current;
  };
  const queueSave = (network: Json, advanced: Json) => {
    // The complete value set is sent, so hidden and heads are judged together (one at a time could never pass).
    pending.current = { encoder, body: { network: pick(network, netFields), advanced: pick(advanced, advFields) } };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 700);
  };
  const editNet = (fields: Json) => { ++netRevision.current; setNet(fields); queueSave({ ...net, ...fields }, adv); };
  // While a saved model is loaded, `net` is THAT model's network (see `loads` below): an Advanced edit then keeps the
  // sizes already stored for the encoder instead of storing the loaded model's sizes as the setting for new networks.
  const editAdv = (fields: Json) => { ++netRevision.current; setAdv(fields); queueSave(run.mode !== 'scratch' && entry ? entry.network : net, { ...adv, ...fields }); };
  const chooseEncoder = (name: string) => {
    const revision = ++netRevision.current;
    setNetMessage(null);
    const cached = netSettings?.settings?.[name];
    // Undo or Import can change these values without going through editNet/editAdv.
    const expected = networkKey(run.mode, cached ? { ...keepList(net), encoder_type: name, ...cached.network } : { ...net, encoder_type: name },
      cached ? { ...adv, ...cached.advanced } : adv);
    if (cached) applyEntry(cached); else setNet({ encoder_type: name });
    // An unsaved edit still belongs to the previous encoder; then read the backend again (another tab may have changed it).
    flush().then(() => api.networkSettings()).then(s => {
      if (!currentReply(revision, name, expected)) return;
      setNetSettings(s);
      const fresh = s.settings?.[name];
      if (fresh && JSON.stringify([fresh.network, fresh.advanced]) !== JSON.stringify([cached?.network, cached?.advanced])) applyEntry(fresh, false);
    }).catch(() => undefined);
  };
  useEffect(() => {
    const revision = ++netRevision.current;
    const expected = networkKey(run.mode, net, adv);
    api.networkSettings().then(s => {
      if (netRevision.current !== revision) return;
      setNetSettings(s);
      // The starting preset changed from 3e-4 to 1e-3 (record 7.199), but its old explicit rate stayed in browser
      // storage. Upgrade only that otherwise-identical restored preset. Check once per browser, including when no
      // upgrade is needed: Undo, a later edit or an imported configuration must keep its chosen rate on reload.
      try {
        const key = PRESET_RATE_KEY;
        if (localStorage.getItem(key)) return;
        localStorage.setItem(key, 'checked');
      } catch { return; } // Without durable storage, do not repeatedly override a rate the user may have restored.
      const saved = s.settings?.[encoder];
      if (!currentReply(revision, encoder, expected) || run.mode !== 'scratch'
        || !['graph_transformer', 'rgcn', 'gatv2'].includes(encoder) || saved?.origin !== 'publication'
        || adv.learning_rate !== 0.0003 || saved.advanced.learning_rate !== 0.001
        || !s.network_fields.every((f: string) => net[f] === saved.network[f])
        || !s.advanced_fields.every((f: string) => f === 'learning_rate' || adv[f] === saved.advanced[f])) return;
      setConfig(c => networkKey(c.run.mode, c.run.network ?? {}, c.run.advanced ?? {}) !== expected ? c : ({ ...c,
        run: { ...c.run, advanced: { ...c.run.advanced, learning_rate: saved.advanced.learning_rate } } }));
      setPresetRateUpdated(true);
    })
      .catch(e => { if (netRevision.current === revision) setNetMessage({ level: 'error', text: `Backend network settings unavailable (${e.message}).` }); });
    return () => { ++netRevision.current; flush(); };
  }, []);
  // A configuration that leaves a value out would silently run the schema default. Fill it from the backend instead.
  useEffect(() => {
    if (!entry) return;
    const missingNet = netFields.filter(f => net[f] === undefined || net[f] === null);
    const missingAdv = advFields.filter(f => adv[f] === undefined || adv[f] === null);
    if (net.encoder_type && !missingNet.length && !missingAdv.length) return;
    setConfig(c => ({ ...c, run: { ...c.run,
      network: { ...(c.run.network ?? {}), ...pick(entry.network, missingNet), encoder_type: encoder },
      advanced: { ...(c.run.advanced ?? {}), ...pick(entry.advanced, missingAdv) } } }), false);
  }, [entry, JSON.stringify(net), JSON.stringify(adv)]);
  const settingDifferences = entry ? [
    ...netFields.map(field => ({ field, current: net[field], saved: entry.network[field] })),
    ...advFields.map(field => ({ field, current: adv[field], saved: entry.advanced[field] })),
  ].filter(row => row.current != null && row.current !== row.saved) : [];
  const differs = settingDifferences.length > 0 && !pending.current;
  const originLabel = entry && ORIGIN[entry.origin];
  const budget: number = run.max_evaluations;
  // The soft actor-critic values measured on 2026-10-05 (record 7.183; validation.py says the same as a warning): with one
  // update per evaluation the designs stayed a uniform random search for 1,500 evaluations, and a starting temperature of
  // 0.2 delayed learning to about evaluation 1,000. Said where the values are set, for a Mode that trains.
  // Unknown until the encoder's settings have arrived (a new configuration holds no Advanced values of its own): no verdict then.
  const updatesPer: number | undefined = adv.updates_per_transition ?? entry?.advanced?.updates_per_transition;
  const startAlpha: number | undefined = adv.initial_alpha ?? entry?.advanced?.initial_alpha;
  const sacSlow = run.mode === 'frozen' || run.mode === 'resume' ? [] : [
    updatesPer !== undefined && updatesPer < 4 ? `${updatesPer} update${updatesPer === 1 ? '' : 's'} per evaluation` : null,
    startAlpha !== undefined && startAlpha > 0.05 ? `a starting temperature of ${startAlpha}` : null].filter(Boolean) as string[];
  const starved = run.mode !== 'frozen' && typeof budget === 'number' && (budget <= (adv.warmup_transitions ?? 0) || budget < (adv.batch_size ?? 0) + 1);
  // resume / fine_tune / frozen LOAD a saved model, and its weights only fit the network they were trained with (the
  // backend refuses any other network in all three). So there is nothing to set up then: the block for a NEW network
  // is shown in scratch only, and otherwise the configuration takes the network of the chosen model - the act is the
  // choice of that model. Only the network follows; the training numbers under Advanced stay the user's.
  const loads = LOADS.includes(run.mode);
  // No Mode chosen (record 7.267): a draft that still says resume - saved before record 7.265, or imported. The page starts
  // nothing with it (App.tsx) and names the run it continued, which Continue... in the Runs window goes on with.
  const noMode = run.mode === 'resume';
  // The RL model's own label (record 7.159, user: "Give the RL model its own label, independent of the project name"):
  // typed here, else the task's run label. A run that saves a model files it under this name.
  const label: string = (run.model_label ?? '').trim() || config.project.task_name;
  // Its box, under "Name of the new model" in New model and as "Name of the model it saves" under Fine-tune's settings.
  const labelInput = <input className="model-label" value={run.model_label ?? ''} placeholder={config.project.task_name} maxLength={80}
    onChange={e => set({ model_label: e.target.value.trim() ? e.target.value : null })} />;
  const savedModel: Json = loads ? model?.description?.contract?.model_config : null;
  const savedNet: Json = loads ? networkOf(model?.description, netFields) : null;
  const archDiffers = !!savedNet && Object.keys(savedNet).some(f => savedNet[f] !== (f === 'encoder_type' ? encoder : net[f]));
  const followed = useRef<string | null>(null);
  useEffect(() => {
    if (!loads || !savedNet) { if (!loads) followed.current = null; return; }
    const key = JSON.stringify([source.run_dir, model?.description?.checkpoint_id, savedNet]);
    const seen = followed.current === key;
    followed.current = key;
    if (!archDiffers) return;
    // "Use this save point" brings the network WITH the saved model (record 7.265), so a model seen with its network that now
    // differs got another network from elsewhere - an imported or opened configuration: it is taken back, and said as a
    // warning (a silent revert would read as a button that does nothing). A model that came without its network - an old
    // draft, the launcher's "Fine-tune from its newest save point", an imported configuration naming another model - gets
    // it here, said as a note.
    const named = `${savedNet.encoder_type} ${savedModel.hidden_dim}/${savedModel.heads}/${savedModel.layers}`;
    setNetMessage(seen ? { level: 'warn', text: `The network stays ${named}: this run loads a saved model, and a saved model only loads into the network it was trained with. A new network needs New model.` }
      : { level: 'ok', text: `The network is now the saved model's, ${named}: a saved model only loads into the network it was trained with.`,
        about: JSON.stringify([run.mode, source.run_dir, source.checkpoint_id]) });
    setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...savedNet } } }), false);
  }, [loads, archDiffers, JSON.stringify(savedNet)]);
  useEffect(() => setNetMessage(m => m?.level === 'warn' ? null : m), [source.run_dir, source.checkpoint_id, run.mode]);
  // The component list follows the chosen model as its network does: its weights only fit the list it was trained with.
  const savedList: string | undefined = loads ? model?.vocabulary?.name : undefined;
  useEffect(() => { if (savedList && savedList !== (net.vocabulary ?? 'standard')) chooseList(savedList, false); }, [savedList, net.vocabulary]);

  // The source is chosen, never filled in (record 7.265). Until then a Mode that loads a model filled it by itself with the
  // newest model saved under the RL model label (record 7.159), at `latest`. That model is now a suggestion with a press,
  // "Newest model named ...: Use", which pins its newest save point as any choice does.
  // Asked 0.5 s after the last keystroke of the label, as the checks are (record 7.279): each answer walks every run's
  // name under the output folder, and one went out at every key.
  const { value: suggested } = useRequest<Json>(() => api.defaultModel(label, config.project.name), [label, loads, source.run_dir],
    { enabled: loads && !source.run_dir, delay: 500 });
  // "Use this save point" (record 7.265): the draft's source becomes exactly that save point - a concrete id, never "latest" -
  // and the model's network and component list come with it, as ONE Undo step (they used to follow later, by themselves).
  const [usingPoint, setUsingPoint] = useState(false);
  // Only the newest press lands (record 7.278, Astra's review of 2026-10-08; as Load run's generation number, 7.270): a save
  // point chosen before it and answered later changes nothing, and New model chosen meanwhile lets a pending one go.
  const pointSerial = useRef(0);
  // A saved model's name, as the saved models table lists it: from its run's row (the folder's name when the run is not listed).
  const nameOf = (dir: string) => modelNameAt(runs, String(dir));
  const useSavePoint = (run_dir: string, checkpoint_id: string) => {
    const mine = ++pointSerial.current, stale = () => mine !== pointSerial.current;
    setUsingPoint(true); setNetMessage(null);
    readSavePoint(run_dir, checkpoint_id, netFields).then(point => {        // savePoint.ts: Load run and New run like this take one the same way
      if (stale()) return;
      setConfig(c => ({ ...c, run: withSavePoint(c.run, point) }));
      setNetMessage({ level: 'ok', text: `The next run ${run.mode === 'frozen' ? 'evaluates' : 'fine-tunes'} ${nameOf(run_dir)} from its save point ${point.checkpoint_id}, with its network (one Undo step takes it back).`,
        about: JSON.stringify([run.mode, run_dir, point.checkpoint_id]) });
    }).catch((e: any) => { if (!stale()) setNetMessage({ level: 'error', text: `That save point could not be read: ${e.message}` }); })
      .finally(() => { if (!stale()) setUsingPoint(false); });
  };
  // A Mode is one Undo step. New model clears the saved model chosen: scratch never loads one (a source left there is a
  // validation warning), and coming back to Fine-tune asks for the choice again. A save point still on its way is let go too.
  const chooseMode = (mode: string) => {
    if (mode === 'scratch') { pointSerial.current++; setUsingPoint(false); }
    setConfig(c => ({ ...c, run: { ...c.run, mode,
      ...(mode === 'scratch' && c.run.model_source?.run_dir ? { model_source: { ...c.run.model_source, run_dir: null, checkpoint_id: 'latest' } } : {}) } }));
  };


  // The network in use, in short, beside the RL model button (user, 2026-10-03: "show the current network selection next to
  // the RL network button in short"). In a Mode that loads a model the configuration's network is that model's (above).
  const hidden = net.hidden_dim ?? entry?.network?.hidden_dim ?? 32, heads = net.heads ?? entry?.network?.heads ?? 4, layers = net.layers ?? entry?.network?.layers ?? 2;
  const components = net.vocabulary && net.vocabulary !== 'standard' ? net.vocabulary.replace(/^pdk:/, '') : null;
  const netShort = [`${ENCODER_SHORT[encoder] ?? encoder} ${hidden}/${usesHeads ? heads : '–'}/${layers}`, net.operating_points ? 'op. points' : null,
      components ? `${components} parts` : null].filter(Boolean).join(' · ');
  // The next run's model in one line, beside the button (record 7.265; plan "RL model window": "New model · Graph Transformer
  // template · GT 48/4/4", "Fine-tune ota7t (2) · save point 420 evaluations", "Evaluate ... · deterministic actions").
  const sourceName = source.run_dir ? nameOf(source.run_dir) : null;
  const pointAt = model?.description?.counters?.evaluations_committed ?? pointEvaluations(source.checkpoint_id);
  const modelLine = run.mode === 'scratch' ? `New model · ${entry?.label ?? encoder} template · ${netShort}`
    : noMode ? 'No Mode chosen: choose one in RL model... (this configuration still says resume)'
    : !source.run_dir ? `${MODE_NAME[run.mode] ?? run.mode} · no saved model chosen`
    : `${run.mode === 'frozen' ? 'Evaluate' : 'Fine-tune'} ${sourceName} · save point ${pointAt != null ? `${pointAt} evaluations` : source.checkpoint_id}`
      + (run.mode === 'frozen' ? ` · ${run.frozen_action ?? 'deterministic'} actions` : '');
  // The same, as the header's "Next" line names it (record 7.269; plan "The draft": "Next: ota7t · Fine-tune from ota7t (2)
  // @ 420 · GT 48/4/4 · 800 evaluations").
  const nextModel = run.mode === 'scratch' ? 'New model'                 // the network beside it names the template's encoder
    : noMode ? 'no Mode chosen'
    : !source.run_dir ? `${MODE_NAME[run.mode] ?? run.mode} - no saved model chosen`
    : `${run.mode === 'frozen' ? 'Evaluate' : 'Fine-tune from'} ${sourceName} @ ${pointAt ?? source.checkpoint_id}${run.mode === 'frozen' ? ` (${run.frozen_action ?? 'deterministic'} actions)` : ''}`;
  useEffect(() => onNext?.({ model: nextModel, network: netShort }), [nextModel, netShort]);
  const netTitle = loads && !source.run_dir ? `${MODE_NAME[run.mode] ?? run.mode} loads a saved model: choose one in RL model...; the run then uses its network.`
    : `The network in use: ${encoder}, hidden ${hidden}, ${usesHeads ? `heads ${heads}` : 'no attention heads'}, layers ${layers}; nominal operating points ${net.operating_points ? 'on' : 'off'}; `
      + `components ${components ?? 'standard'}${loads ? `. It is the network of the saved model this run loads (${source.run_dir}, save point ${source.checkpoint_id}).` : '.'} RL model... changes it.`;
  const limitsSet = [run.max_spectre_launches != null ? `${run.max_spectre_launches} launches` : null, (run.max_retries ?? 0) > 0 ? `${run.max_retries} retries` : null,
    run.max_wall_seconds != null ? `${run.max_wall_seconds} s` : null].filter(Boolean) as string[];
  const folded = [MODE_NAME[run.mode] ?? run.mode, run.model_label?.trim() ? `model ${run.model_label.trim()}` : null, typeof budget === 'number' ? `${budget} evaluations` : null,
    `${encoder} ${net.hidden_dim ?? '?'}/${net.heads ?? '?'}/${net.layers ?? '?'}`,
    net.vocabulary && net.vocabulary !== 'standard' ? `knows ${net.vocabulary.slice(4)}` : null].filter(Boolean).join(' - ');
  const networkError = error || netMessage?.level === 'error' || !offeredEncoders.includes(encoder)
    || (modelChecked && model?.compatibility?.compatible === false);
  const networkWarning = netMessage?.level === 'warn' || (run.mode === 'scratch' && (differs || entry?.problem))
    || starved || archDiffers || sacSlow.length > 0;
  // The training numbers, with the warning about values that leave the search random right above them. In scratch they sit
  // directly below "Nominal device operating points" (user, 2026-10-05: "move the advanced setting to beneath the nominal
  // device op checkbox", record 7.195); a Mode that loads a model shows no network block, so there they close the window -
  // they hold the fine_tune switches.
  const advanced = <>
    {sacSlow.length > 0 && <p className="warn sac-values">With {sacSlow.join(' and ')}, soft actor-critic learned late or not at all in the tests of 2026-10-05:
      with 1 update per evaluation the designs stayed a uniform random search for 1,500 evaluations, and a starting temperature of 0.2 delayed
      learning to about evaluation 1,000. The tested values are 8 updates per evaluation, starting temperature 0.01 and discount 0 (under Advanced).</p>}
    <details className="rl-advanced"><summary>Advanced (stored per encoder, like the network sizes)</summary>
      <p className="hint">Alpha learning rate and the tick box below belong to this configuration; the other settings belong to the selected encoder. The algorithm stays soft actor-critic; only its numbers change.</p>
      <Num label="Alpha learning rate" nullable value={adv.alpha_learning_rate} onChange={v => setAdv({ alpha_learning_rate: v })} title="Empty uses the actor learning rate. A separate rate is stored in this configuration." />
      <Check label="Send the next design before learning (faster, experimental)" value={!!adv.update_after_dispatch} onChange={v => setAdv({ update_after_dispatch: v })}
        title={'Off: after each result the learner makes its updates, then the lane gets its next design. On: the lane gets its next design first '
          + 'and simulates while the learner learns - an estimated 11-27 % faster on the measured runs. The number of updates stays the same; each '
          + 'design comes from a policy a few updates older. Off until a check on real tasks shows that learning is not worse (record 7.281).'} />
      {ADVANCED_ROWS.map((fields, i) => {
        const inputs = fields.map(([name, label, title]) => <Num key={name} label={label} title={title}
          value={adv[name] ?? entry?.advanced?.[name] ?? schema.$defs.AdvancedRL.properties[name].default}
          onChange={v => editAdv({ [name]: v })} />);
        return i === 0 ? <Fragment key={i}>{inputs}</Fragment> : <div className="row" key={i}>{inputs}</div>;
      })}
    </details>
  </>;
  // Said in Run configuration and in the window, with the run that configuration continued: Continue... is where it goes on.
  const noModeNote = (from: Window | null) => noMode && <p className="warn no-mode">No Mode is chosen: this configuration still says resume, which is
    no longer a choice{source.run_dir ? <> - it continued the run <button className="text-link no-mode-run" onClick={() => openRunsAt({ run_dir: source.run_dir, from })}
      title="Open the Runs window at that run: Continue... goes on with it in its own folder, and Show results shows it.">{folderName(String(source.run_dir))}</button></> : ''}.
    Choose a Mode {from ? 'above' : 'in RL model...'} for the next run: Start waits until then.</p>;
  return (
    <>
    <Module id="run" title="Run configuration" summary={folded}>
      {/* The Mode and the RL model label moved into the RL model window (record 7.265); here the next run's model is one line. */}
      <div className="rl-networks-row"><span className={`hint net-short${loads && !source.run_dir ? '' : ' net-code'}`} title={netTitle}>{modelLine}</span>
        <button className="rl-networks-open" title="Open the RL model window: the Mode (New model, Fine-tune, Evaluate only), the templates of a new model, and the saved models."
          onClick={() => networkWindow.open()}>RL model...</button></div>
      {networkWindow.blocked && <p className="error" role="alert">{BLOCKED}</p>}
      {noModeNote(null)}
      {(networkError || networkWarning) && <p className={networkError ? 'error' : 'warn'}>Review the settings in RL model.</p>}
      {/* Only while the model is checked: in scratch the last check's suggestion stayed, never asked again (review of 2026-10-01).
          "resume" is no Mode any more (record 7.265): its suggestion is the run itself, a link into the Runs window (Continue...). */}
      {modelChecked && model?.suggestion && model.suggestion.mode !== run.mode && (model.suggestion.mode === 'resume'
        ? <p className="hint mode-suggestion-run">This model's own run can be continued exactly: <button className="text-link mode-suggestion"
            title="Open the Runs window at that run: its Continue... goes on in its own folder." onClick={() => openRunsAt({ run_dir: source.run_dir })}>open it in Runs</button>. {model.suggestion.reason}</p>
        : <p className="warn">Suggested: <button className="text-link mode-suggestion" title={`Set Mode to ${MODE_NAME[model.suggestion.mode] ?? model.suggestion.mode}`}
            onClick={() => set({ mode: model.suggestion.mode })}>{MODE_NAME[model.suggestion.mode] ?? model.suggestion.mode}</button> - {model.suggestion.reason}
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
      {robust && !supportsCorners && <p className="error">Training corners require the registered real OTA7 task.</p>}
      {robust && (run.max_spectre_launches == null || run.max_spectre_launches < 1) && <p className="error">A positive launch cap is required for training corners.</p>}
      {robust && (run.max_retries ?? 0) !== 0 && <p className="error">Training corners require zero automatic retries.</p>}
      {/* The reward in one sentence (record 7.183, user: "it is too complicated... is there room for simplification?"). The five
          settings compared in training on 2026-10-05 are fixed for a new configuration (store.ts SIMPLE_REWARD) and said here in
          words; the controls sit in one fold, for reproducing an older run or for an experiment. A configuration that holds other
          values is told which, and offered the tested set on a button - it is never changed by itself. */}
      {rewardOther.length === 0
        ? <p className="hint reward-sentence">Reward: minus half the average miss, minus half the worst miss. A design that meets every Specs row
            scores above 0: up to +1 for the room it leaves on its tightest row, and up to +1 more for improving the objective
            row{objective.length ? <> (<b>{objective.map((t: Json) => `${t.direction_after_feasible} ${t.metric_id}`).join('; ')}</b>).</> : ' (none is marked in Specs).'}</p>
        : <div className="note reward-other">
            <p className="hint">This configuration's reward is not the one a new configuration starts with (the set compared in training on 2026-10-05):
              {' '}{rewardOther.map(k => `${REWARD_NAMES[k]} ${reward[k]} instead of ${SIMPLE_REWARD[k]}`).join('; ')}.</p>
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
    </Module>
    {networkWindow.popup && networkWindow.root && createPortal(<section className="panel rl-networks-panel" aria-labelledby="rl-networks-title">
      {/* No close button of its own (user, 2026-10-03: "delete the cross button in RL network window"): the window's own close
          does it, and the settings are kept either way. Record 7.265: the RL model window - the Mode at the top, then that
          Mode's part: the templates of a new model, or the saved models to fine-tune or evaluate. */}
      <div className="rl-networks-heading"><h2 id="rl-networks-title">RL model</h2></div>
      <div className="rl-modes" role="radiogroup" aria-label="Mode">
        {MODES.map(([m, name, help]) => <button key={m} role="radio" aria-checked={run.mode === m} data-mode={m} className={`rl-mode${run.mode === m ? ' active' : ''}`}
          onClick={() => { if (run.mode !== m) chooseMode(m); }} title={`${name}: ${help}. One Undo step.`}>{name}</button>)}
      </div>
      {noMode ? noModeNote(networkWindow.popup)
        : <p className="hint rl-mode-help">{MODES.find(([m]) => m === run.mode)?.[2]?.replace(/^./, c => c.toUpperCase())}{loads ? '. The next run uses the network of the model chosen below.' : '.'}</p>}
      {run.mode === 'scratch' && <>
      <h3>Templates</h3>
      <p className="hint">A new model starts from one template: its network and its training values, kept per encoder in the backend. Editing a value
        below saves it for that encoder.</p>
      <TemplatesTable settings={netSettings} encoders={offeredEncoders} current={encoder} runs={runs} onUse={chooseEncoder} />
      {!offeredEncoders.includes(encoder) && <p className="error">{encoder} is unavailable. Choose an available template. Existing models need their matching historical optimizer version.</p>}
      <h3>The {entry?.label ?? encoder} template, for this run</h3>
      <div className="row"><Num label="hidden" value={net.hidden_dim ?? entry?.network?.hidden_dim ?? 32} onChange={v => editNet({ hidden_dim: v })} />
        <Num label="heads" value={net.heads ?? entry?.network?.heads ?? 4} onChange={v => editNet({ heads: v })} disabled={!usesHeads} note={usesHeads ? undefined : 'ignored by this encoder'}
          title={usesHeads ? 'Attention heads. hidden must be divisible by heads.' : 'RGCN does not use attention heads. The number is kept in the checkpoint.'} />
        <Num label="layers" value={net.layers ?? entry?.network?.layers ?? 2} onChange={v => editNet({ layers: v })} /></div>
      {usesStructure && <label>Structural encoding<select className="structural-encoding" value={net.structural_encoding ?? entry?.network?.structural_encoding ?? 'none'}
        onChange={e => editNet({ structural_encoding: e.target.value })}>
        <option value="none">None</option><option value="rwse">Random-walk returns (2, 4, 8, 16 steps)</option></select></label>}
      {entry?.experimental && <p className="hint encoder-experimental">Experimental encoder. Transfer performance and these starting settings have not been validated.</p>}
      <Check label="Nominal device operating points" value={net.operating_points ?? false} onChange={v => setNet({ operating_points: v })}
        title="Measured nominal device values and validity masks. Corner operating points are recorded but never replace the nominal network input. Changing this changes the model input schema." />
      {advanced}
      <ComponentList value={net.vocabulary ?? 'standard'} onChoose={v => chooseList(v)} />
      {/* The GATOR baseline and both preset buttons were deleted (record 7.191, user: "Delete the gator baseline in RL networks
          and keep the publication preset, delete two buttons"); the one preset left became the starting preset (7.192). Typing a
          value back to its preset forgets the saved copy. */}
      {entry && <p className="hint in-use">In use: <b>{settingDifferences.length ? 'current run settings' : originLabel}</b></p>}
      {presetRateUpdated && adv.learning_rate === 0.001 && <p className="hint preset-rate-updated" role="status">
        Updated the restored starting preset’s learning rate from 0.0003 to 0.001. Undo in the main window restores the previous value.</p>}
      {differs && <div className="note network-differences">
        <p className="warn">Current run values differ from the saved {encoder} defaults ({originLabel}).</p>
        <p className="hint">This run uses the values shown in the controls. Saved defaults are loaded when you use a template; they do not replace an existing configuration on page reload.</p>
        <table className="grid small" aria-label="Network settings differences"><thead><tr><th>Setting</th><th>This run</th><th>Saved default</th></tr></thead><tbody>
          {settingDifferences.map(row => <tr key={row.field}><td title={row.field}>{NETWORK_SETTING_LABELS[row.field] ?? row.field}</td>
            <td className="numeric">{String(row.current)}</td><td className="numeric">{row.saved == null ? 'Not set' : String(row.saved)}</td></tr>)}
        </tbody></table>
        <div className="row pair"><button onClick={() => applyEntry(entry)} title="Replace this run's network and Advanced values with the saved defaults for this encoder.">Use saved defaults</button>
          <button onClick={() => { queueSave(net, adv); flush(); }} title="Keep this run's values and remember them as the defaults for this encoder.">Save as defaults</button></div>
      </div>}
      {entry?.problem && <p className="warn">{entry.problem}</p>}
      {entry && <details><summary>Where the {encoder} values come from</summary>
        <p className="hint">{entry.summary}</p>
        {entry.architecture_reference && <p className="hint">Architecture reference: <a href={entry.architecture_reference.url} target="_blank" rel="noreferrer">{entry.architecture_reference.short}</a>. The starting values are project choices.</p>}
        <table className="grid small"><thead><tr><th>Setting</th><th>Preset</th><th>Basis</th><th>Source and note</th></tr></thead><tbody>
          {[...netFields, ...advFields].map(f => { const p = entry.provenance?.[f]; const ref = p?.source ? netSettings.references?.[p.source] : null; return (
            <tr key={f}><td>{f}</td><td className="numeric">{typeof p?.value === 'string' ? p.value : num(p?.value)}</td><td>{p?.basis}{p?.match === 'closest' ? ', closest network' : ''}</td>
              <td>{ref && <a href={ref.url} target="_blank" rel="noreferrer">{ref.short}</a>} {p?.note}</td></tr>); })}
        </tbody></table>
        <p className="hint">{netSettings.scale_note}</p></details>}
      <h3>Name of the new model</h3>
      <label title={`The name this run's RL model is saved under. Empty: the task's run label (${config.project.task_name}). A name a saved model carries already gets a number: ${label} (2), ${label} (3). A saved model can be renamed in its Details below.`}>RL model label
        {labelInput}</label>
      </>}
      {netMessage && (!netMessage.about || netMessage.about === JSON.stringify([run.mode, source.run_dir, source.checkpoint_id]))
        && <p className={`net-message ${netMessage.level === 'error' ? 'error' : netMessage.level === 'warn' ? 'warn' : 'hint'}`}>{netMessage.text}</p>}
      {starved && <p className="warn">Budget {budget} with warm-up {adv.warmup_transitions} and batch size {adv.batch_size}: {budget <= (adv.warmup_transitions ?? 0) ? 'every evaluation is a random warm-up action, so the policy never acts' : 'one batch is never filled, so the network never learns'}.
        Published settings assume thousands of simulations. Lower them under Advanced or raise the budget.</p>}
      {loads && (<>
        <h3>Saved models</h3>
        {/* No model is filled in by itself (record 7.265): the newest one under the RL model label is offered. */}
        {!source.run_dir && suggested?.run_dir && <p className="note model-suggested">Newest model named <b>{label}</b>: {folderName(String(suggested.run_dir))}
          {suggested.description?.checkpoint_id ? `, save point ${suggested.description.checkpoint_id}` : ''}. <button className="model-suggested-use" disabled={usingPoint}
            onClick={() => useSavePoint(suggested.run_dir, suggested.description?.checkpoint_id ?? 'latest')}>Use</button></p>}
        {!source.run_dir && <p className="warn model-none-chosen">No saved model is chosen yet: {MODE_NAME[run.mode]} needs one. Use a save point below.</p>}
        <SavedModels source={source} usable={LOADS.includes(run.mode) ? run.mode : null} runs={runs} outputRoot={config.output?.output_root}
          config={config} popup={networkWindow.popup} onUse={useSavePoint} />
        {source.run_dir && <><h3>The model in use</h3>
        {modelLoading && <p className="hint" role="status">Checking model compatibility...</p>}
        {error && <p className="error">{error}</p>}
        {model?.description && <table className="grid small model-facts"><tbody>
          {savedNet && <tr className="model-network"><td>Network</td><td><b>{savedNet.encoder_type}</b>, hidden {savedModel.hidden_dim}, heads {savedModel.heads}{archDiffers || usesHeads ? '' : ' (ignored by this encoder)'}, layers {savedModel.layers}
            <span className="hint"> - this run uses it as it is: a saved model only loads into the network it was trained with.</span></td></tr>}
          {model.vocabulary && <tr className="model-components"><td>Components</td><td><b>{model.vocabulary.label}</b>
            <span className="hint"> - the network of this run knows the same list{model.vocabulary.name !== 'standard' && !model.vocabulary.loaded
              ? '; that PDK is not loaded now, which is needed only for Parameters rows on its own parameters' : ''}.</span></td></tr>}
          <tr><td>Trained on</td><td>{model.description.source_task_id}</td></tr>
          <tr><td>Saved (UTC)</td><td>{model.description.created_utc}</td></tr>
          <tr><td>Schema</td><td>{model.description.metadata_version}</td></tr>
          <tr><td>Reward</td><td>{model.description.contract?.reward_version ?? 'Legacy nominal'}; {model.description.contract?.reward_settings?.violation_shape ?? 'capped'}</td></tr>
          <tr><td>Worst hard-spec share</td><td>{num(model.description.contract?.reward_settings?.worst_spec_share ?? 0)}</td></tr>
          <tr><td>Objective bonus weight</td><td>{num(model.description.contract?.reward_settings?.objective_weight ?? 0)}</td></tr>
          <tr><td>Margin bonus weight</td><td>{num(model.description.contract?.reward_settings?.margin_weight ?? 0)}</td></tr>
          <tr><td>Conditions</td><td>{model.description.contract?.condition_policy ?? 'off'}; {model.description.contract?.planned_conditions?.length ?? 'unknown'} planned</td></tr>
          {model.description.contract?.planned_conditions?.length > 0 && <tr><td>Saved condition plan</td><td>{model.description.contract.planned_conditions.map((c: Json) => c.corner.id).join(', ')}</td></tr>}
          <tr><td>Operating points</td><td>{savedNet?.operating_points ? 'enabled' : 'off'}</td></tr>
          <tr><td>Training</td><td>{model.description.counters.evaluations_committed} evaluations, {model.description.counters.learner_updates} updates, replay {model.description.counters.replay_size}</td></tr>
          <tr><td>Restorable</td><td><b>{model.description.restoration_capability}</b>{model.description.missing_components.length ? ` - missing: ${model.description.missing_components.join(', ')}` : ''}</td></tr>
          <tr><td>Folder</td><td className="path" title="Click to copy" onClick={() => copy(model.description.path)}>{model.description.path}</td></tr>
        </tbody></table>}
        {model?.compatibility_unchecked && <div className="note compat-unchecked"><p><b>{model.compatibility_unchecked.title}</b></p>
          <p>{model.compatibility_unchecked.what}</p><p className="hint">{model.compatibility_unchecked.note}</p>
          <details><summary>Technical details</summary><pre className="small">{model.compatibility_unchecked.technical}</pre></details></div>}
        {model?.compatibility && !archDiffers && <details open={!model.compatibility.compatible}><summary className={model.compatibility.compatible ? '' : 'error'}>Compatibility for {model.compatibility.mode}: {model.compatibility.compatible ? 'compatible' : 'NOT compatible - there is no fallback to scratch'}</summary>
          <ul>{model.compatibility.checks.map((c: Json) => <li key={c.component} className={`issue ${c.status === 'ok' ? 'info' : c.status === 'warning' ? 'warning' : 'error'}`}>{c.component}: {c.status} - {c.detail}</li>)}</ul></details>}</>}
        <h3>{run.mode === 'frozen' ? 'Evaluate only' : 'Fine-tune'}: its own settings</h3>
        {run.mode === 'frozen' && <label>Frozen actions<select value={run.frozen_action ?? 'deterministic'} onChange={e => set({ frozen_action: e.target.value })}><option>deterministic</option><option>sampled</option></select></label>}
        {run.mode === 'fine_tune' && <>
          <Check label="Freeze encoder" value={adv.freeze_encoder} onChange={v => setAdv({ freeze_encoder: v })} />
          <Check label="Encoder-only transfer" value={adv.encoder_only_transfer} onChange={v => setAdv({ encoder_only_transfer: v })} />
          <Check label="Reset critic" value={adv.reset_critic} onChange={v => setAdv({ reset_critic: v })} />
          <Check label="Continual learning (inherit weights fine-tuned on a previous test task)" value={run.continual_learning} onChange={v => set({ continual_learning: v })} />
          <label title={`The name the model this run saves goes by. Empty: the task's run label (${config.project.task_name}); a name taken already gets a number.`}>Name of the model it saves
            {labelInput}</label></>}
        {advanced}
      </>)}
      {run.mode === 'scratch' && <LookFold summary={<summary>Saved models, to look at <span className="hint">- Fine-tune or Evaluate only above uses one</span></summary>}>
        {() => <SavedModels source={source} usable={null} runs={runs} outputRoot={config.output?.output_root} config={config} popup={networkWindow.popup} onUse={useSavePoint} />}</LookFold>}
    </section>, networkWindow.root)}
    </>
  );
}

/** Memoised (record 7.275): its props change with the configuration, the run list and the circuit - not with the status
 *  polled every 1.5 s while a run works, which drew this whole panel (and the RL model window it holds) at every update. */
export const RunPanel = memo(RunPanelBody);
