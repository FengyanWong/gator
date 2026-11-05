// The RL model's state and work (plan-refactoring C4, out of Right.tsx's RunPanelBody): the Mode, the saved model in use and
// its check, the encoders' settings kept in the backend, and what Run configuration says about them. RunPanel keeps it
// mounted - the state lives on while the RL model window is closed - and hands it to RunConfiguration, RewardConditions and
// RlModelWindow, which only draw it. Its hooks are RunPanelBody's, in their order.
import { useEffect, useRef, useState } from 'react';
import { SIMPLE_REWARD, useRequest } from '../store';
import { api, Json } from '../api';
import { modelNameAt, useSavedModelsView } from './modelView';
import { DESIGN_NAME, designName, ENCODER_SHORT, pointEvaluations, pointText } from '../lineage';
import { LOADS, NETWORK_FIELDS, networkOf, pick, pointKey, readSavePoint, withSavePoint } from '../savePoint';
import { styled, usePopupWindow } from './popupWindow';
import { PRESET_RATE_KEY, RL_MODEL_WINDOW } from '../contract';
import { ADVANCED_ROWS, foldedText, limitsText, modelLineText, networkShort, networkSizes, networkTitle, NextModel, nextModelText, ORIGIN,
  newModelInputs, REWARD_DEFAULTS, switchesText, takesTemplateInputs } from './rlModelText';
import { sameScope, useNewest } from '../newest';
import { oncePerBrowser } from '../kept';
import type { ModelReply, NetworkConfig } from '../contracts';

/** The page's setter of the configuration (history.ts). */
type SetConfig = (f: (c: Json) => Json, record?: boolean) => void;

/** The RL model's state and work, as named steps: the saved model in use and its check, Reward and conditions, the encoders'
 *  templates and the writes into them, the network that follows a loaded model, the choice of a model, the model lines and
 *  Run configuration's notice. The steps run in this order at every draw, and so do their hooks: React keeps a hook's state
 *  by its place in that order. */
export function useRlModel({ config, setConfig, runs, refreshRuns, circuit, schema, onNext }: { config: Json;
  setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; refreshRuns: () => Promise<Json[]>; circuit: Json; schema: Json;
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
  // The saved models table's filter, sort, Design, folder, open Details and last list, kept while the window is closed
  // (branch record SIF-102): it closes after every choice (record 7.291).
  const savedView = useSavedModelsView();
  const { modelChecked, error, modelLoading, model } = useModelInUse(config, run, source);
  const { cornerIds, robust, gated, corners, supportsCorners, launchesPerStep, objective, reward, rewardOther, toggleCorner } =
    rewardAndConditions(config, run, circuit, schema, set);
  const templates = useTemplates(run, net, adv);
  const { netSettings, netMessage, presetRateUpdated, netFields, advFields, encoder, entry, offeredEncoders, usesHeads, usesStructure } = templates;
  const { applyEntry, chooseList, flush, queueSave, editNet, editAdv, chooseEncoder } = templateActions(templates, { run, net, adv, setConfig, setNet,
    setAdv });
  useReadTemplatesOnce(templates, flush, { run, net, adv, setConfig });
  useFillLeftOutValues(templates, net, adv, setConfig);
  const { settingDifferences, differs, originLabel } = templateDifferences(templates, net, adv);
  const { budget, sacSlow, starved } = trainingWarnings(run, adv, entry);
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
  const { savedModel, savedNet, archDiffers } = useNetworkFollowsModel(templates, { loads, model, net, source, run, setConfig, chooseList });
  const { suggested, usingPoint, nameOf, useSavePoint, chooseMode } = useModelChoice(templates, { label, config, loads, source, runs, run, setConfig });
  const { modelLine, switchesLine, netTitle } = useModelLines(templates, { net, source, nameOf, model, run, noMode, adv, loads, onNext });
  const { savedReward, rewardApart, useModelReward } = savedModelReward(loads, model, reward, run, set);
  const limitsSet = limitsText(run);
  const folded = foldedText(run, budget, encoder, net);
  const { networkError, networkWarning, networkReason, networkAnchor } = networkNotice(templates, { error, modelChecked, model, run, differs, starved,
    archDiffers, sacSlow });
  const openAt = useOpenAtBlock(networkWindow);
  return { config, setConfig, runs, refreshRuns, savedView, circuit, schema, run, set, setAdv, setNet, source, adv, net, networkWindow, modelChecked,
    error, modelLoading, model, cornerIds, robust, gated, corners, supportsCorners, launchesPerStep, objective, reward, rewardOther,
    toggleCorner, netSettings, netMessage, presetRateUpdated, netFields, advFields, encoder, entry, offeredEncoders, usesHeads, usesStructure, applyEntry,
    chooseList, flush, queueSave, editNet, editAdv, chooseEncoder, settingDifferences, differs, originLabel, budget, sacSlow, starved,
    loads, noMode, label, savedModel, savedNet, archDiffers, suggested, usingPoint, useSavePoint, chooseMode, modelLine, switchesLine, netTitle,
    limitsSet, folded, networkError, networkWarning, networkReason, networkAnchor, openAt, savedReward, rewardApart, useModelReward };
}
export type RlModel = ReturnType<typeof useRlModel>;

// ---- its steps, in the order useRlModel calls them: a step named use... holds hooks, the others are plain functions --------

/** The saved model in use, checked against this configuration in a Mode that loads it; while the same model is checked
 *  again after an edit, what is known about it stays and only the compatibility verdict waits. */
function useModelInUse(config: Json, run: Json, source: Json) {
  // Only a Mode that loads the model asks about it: a model_source left over from fine_tune is ignored in scratch, and
  // was compiled and checked after every edit there all the same (audit 2026-09-30).
  // A draft that still says resume (record 7.267) has no Mode chosen: it asks about no model either.
  const modelChecked = LOADS.includes(run.mode) && !!source.run_dir;
  const { value: fresh, error, loading: modelLoading } = useRequest(signal => api.model(source.run_dir, source.checkpoint_id ?? 'latest', config, signal),
    [JSON.stringify([config.circuit, config.parameters, config.targets, config.measurements, run.mode, source,
      run.connection_profile_id, run.seed, run.network, run.advanced, run.reward, run.conditions, config.research?.split])],
    // 0.5 s after the last edit, as validation (record 7.275: at 0.25 s a check - a compile - went at almost every pause in typing)
    { enabled: modelChecked, delay: 500 });
  // While the SAME saved model is checked again after an edit (0.5 s and a compile), what is known about it - its facts,
  // network, component list, structure and graph view - stays; only the compatibility verdict waits for the new answer
  // (an old "compatible" is never shown while checking, record 7.96). The whole block used to vanish and come back after
  // every edit, an open compatibility list closed, and an open network structure read the saved tensors again.
  const modelKey = `${source.run_dir}|${source.checkpoint_id ?? 'latest'}`;
  const lastModel = useRef<{ key: string; value: ModelReply } | null>(null);
  if (fresh?.description && lastModel.current?.value !== fresh) lastModel.current = { key: modelKey, value: fresh };
  const model: ModelReply | null = fresh ?? (!error && lastModel.current?.key === modelKey
    ? { ...lastModel.current.value, compatibility: null, compatibility_unchecked: null } : null);
  return { modelChecked, error, modelLoading, model };
}

/** What Reward and conditions draws: the corners the schema offers and those this run trains at, the launches a step makes,
 *  the Specs rows marked as the objective, and the reward this configuration runs, with where it differs from the tested one. */
function rewardAndConditions(config: Json, run: Json, circuit: Json, schema: Json, set: (fields: Json, record?: boolean) => void) {
  const cornerIds: string[] = schema.$defs.ConditionsConfig.properties.corners.items.enum;
  const robust = (run.conditions?.policy ?? 'off') !== 'off';
  const gated = run.conditions?.policy === 'after_nominal';
  const corners: string[] = run.conditions?.corners ?? [];
  const supportsCorners = circuit?.loaded && circuit?.task_key === config.circuit?.task_id && circuit?.training_capabilities?.corners === true;
  const launchesPerStep = robust ? 1 + corners.length : 1;
  const objective = (config.targets ?? []).filter((target: Json) => target.active !== false && target.direction_after_feasible
    && target.direction_after_feasible !== 'none');
  // The reward this configuration runs - with what the schema fills in for a field it leaves out - and where it differs from
  // the set a new configuration starts with, the one compared in training on 2026-10-05 (record 7.183).
  const reward: Json = { ...REWARD_DEFAULTS, ...(run.reward ?? {}) };
  const rewardOther = Object.keys(SIMPLE_REWARD).filter(field => reward[field] !== SIMPLE_REWARD[field]);
  const toggleCorner = (id: string, checked: boolean) => set({ conditions: { ...run.conditions,
    // Re-adding a corner follows schema order, so toggling it back restores the original plan.
    corners: checked ? cornerIds.filter(corner => corner === id || corners.includes(corner)) : corners.filter(corner => corner !== id) } });
  return { cornerIds, robust, gated, corners, supportsCorners, launchesPerStep, objective, reward, rewardOther, toggleCorner };
}

/** The Mode, a network and its training values as one string, to tell whether the configuration still holds the ones an
 *  answer was asked for. */
const networkKey = (mode: string, network: Json, advanced: Json) => JSON.stringify([mode, network, advanced]);
/** The component list is not a per-encoder setting: another encoder keeps the list that was chosen. */
const keepList = (network: Json) => ({ operating_points: network?.operating_points ?? false,
  ...pick(network, ['spec_input', 'size_features', 'device_model_features',           // the network inputs (record 7.298)
    'bench_features', 'net_roles', 'operating_point_ratios']),                         // and their second build (record 7.317)
  ...(network?.vocabulary && network.vocabulary !== 'standard' ? { vocabulary: network.vocabulary } : {}) });
/** A new model is built with the device families (record 7.298): a template used in New model brings them when the list is
 *  still the standard one. */
const newModelList = (config: Json) => config.run.mode === 'scratch' && (config.run.network?.vocabulary ?? 'standard') === 'standard'
  ? { vocabulary: 'families' } : {};
/** What a template brings of the network inputs (record 7.332; user: "Yes, no box"). For a new model: its encoder's whole
 *  input set, unless the configuration holds another choice on purpose. Otherwise, as before: only what the encoder cannot
 *  do without - CircuitGPS reads structured specs, and no other encoder does. */
const templateInputs = (name: string, network: Json, mode: string) => mode === 'scratch' && takesTemplateInputs(network, name) ? newModelInputs(name)
  : name === 'circuit_gps' ? { spec_input: 'structured' } : network?.spec_input === 'structured' ? { spec_input: 'set' } : {};

/** The encoders' templates as the backend keeps them (its network settings), the RL model window's message, and the refs
 *  that order the writes into a template; with the template of the encoder this configuration names, and what it takes. */
function useTemplates(run: Json, net: Json, adv: Json) {
  // Per-encoder settings live in the backend: choosing an encoder READS its settings, editing a value WRITES them back
  // for that encoder. The configuration always carries explicit values, so what is shown is what runs.
  const [netSettings, setNetSettings] = useState<Json>(null);
  // `about`: the Mode and saved model a message is about - it is shown only while they are still the ones chosen.
  // `reason`: an error's few words for Run configuration's notice (branch record SIF-46); the window shows `text`.
  // `point`: the save point a Use could not read (pointKey), whose Details repeat the error under its save points (branch
  // record SIF-85).
  const [netMessage, setNetMessage] = useState<{ level: string; text: string; about?: string; reason?: string; point?: string } | null>(null);
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
  const currentReply = (revision: number, name: string, expected?: string) => sameScope(
    { entity: name, revision }, { entity: currentNetwork.current.encoder, revision: netRevision.current })
    && currentNetwork.current.mode === run.mode
    && (expected === undefined || expected === networkKey(currentNetwork.current.mode, currentNetwork.current.net, currentNetwork.current.adv));
  const entry: Json = netSettings?.settings?.[encoder] ?? null;
  const offeredEncoders: string[] = netSettings?.encoders ?? Object.keys(ENCODER_SHORT);
  const usesHeads: boolean = entry ? !!entry.uses_heads : encoder !== 'rgcn';
  const usesStructure: boolean = entry ? !!entry.supports_structural_encoding : ['graph_gps', 'group_cross_attention', 'circuit_gps'].includes(encoder);
  const remember = (saved: Json) => setNetSettings((previous: Json) => previous && ({ ...previous,
    settings: { ...previous.settings, [saved.encoder_type]: saved } }));
  return { netSettings, setNetSettings, netMessage, setNetMessage, presetRateUpdated, setPresetRateUpdated, pending, netRevision, writing, timer,
    netFields, advFields, encoder, currentReply, entry, offeredEncoders, usesHeads, usesStructure, remember };
}
type Templates = ReturnType<typeof useTemplates>;

/** What the window does with the templates: takes one into the configuration, chooses the component list, writes an edited
 *  value into its encoder's template 0.7 s after the last edit (`flush` at once), and chooses an encoder. */
function templateActions(templates: Templates, { run, net, adv, setConfig, setNet, setAdv }: { run: Json; net: Json; adv: Json; setConfig: SetConfig;
  setNet: (fields: Json) => void; setAdv: (fields: Json) => void }) {
  const { setNetSettings, setNetMessage, netSettings, pending, netRevision, writing, timer, netFields, advFields, encoder, currentReply, entry,
    remember } = templates;
  const applyEntry = (template: Json, record = true) => setConfig(c => ({ ...c, run: { ...c.run,
    network: { ...keepList(c.run.network), ...newModelList(c), encoder_type: template.encoder_type, ...template.network,
      ...templateInputs(template.encoder_type, c.run.network, c.run.mode) }, advanced: { ...(c.run.advanced ?? {}), ...template.advanced } } }), record);
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
    // The template by the window's name for it (branch record SIF-57: "Saved in the backend as the graph_transformer
    // setting." came after every edit). It is kept per encoder, so no CircuitGPS version.
    writing.current = writing.current.then(() => api.saveNetworkSettings(job.encoder, job.body))
      .then(saved => { remember(saved); if (currentReply(revision, job.encoder)) setNetMessage({ level: 'ok',
        text: `Saved into the ${DESIGN_NAME[saved.encoder_type] ?? saved.encoder_type} template.` }); })
      .catch(e => { if (currentReply(revision, job.encoder)) setNetMessage({ level: 'error', text: `Not saved in the backend: ${e.message}`,
        reason: 'a template value was not saved in the backend' }); });
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
  const editAdv = (fields: Json) => { ++netRevision.current; setAdv(fields);
    queueSave(run.mode !== 'scratch' && entry ? entry.network : net, { ...adv, ...fields }); };
  const chooseEncoder = (name: string) => {
    const revision = ++netRevision.current;
    setNetMessage(null);
    const cached = netSettings?.settings?.[name];
    // Undo or Import can change these values without going through editNet/editAdv.
    const expected = networkKey(run.mode, cached ? { ...keepList(net), ...newModelList({ run: { mode: run.mode, network: net } }),
      encoder_type: name, ...cached.network, ...templateInputs(name, net, run.mode) } : { ...net, encoder_type: name, ...templateInputs(name, net, run.mode) },
      cached ? { ...adv, ...cached.advanced } : adv);
    if (cached) applyEntry(cached); else setNet({ encoder_type: name, ...templateInputs(name, net, run.mode) });
    // An unsaved edit still belongs to the previous encoder; then read the backend again (another tab may have changed it).
    flush().then(() => api.networkSettings()).then(answer => {
      if (!currentReply(revision, name, expected)) return;
      setNetSettings(answer);
      const fresh = answer.settings?.[name];
      if (fresh && JSON.stringify([fresh.network, fresh.advanced]) !== JSON.stringify([cached?.network, cached?.advanced])) applyEntry(fresh, false);
    }).catch(() => undefined);
  };
  return { applyEntry, chooseList, flush, queueSave, editNet, editAdv, chooseEncoder };
}

/** Reads the templates from the backend once, when Run configuration is first drawn - and, once per browser, takes a
 *  restored starting preset's old learning rate to its new one -; when it goes, an edit still waiting is written. */
function useReadTemplatesOnce(templates: Templates, flush: () => Promise<void>, { run, net, adv, setConfig }: { run: Json; net: Json; adv: Json;
  setConfig: SetConfig }) {
  const { setNetSettings, setNetMessage, setPresetRateUpdated, netRevision, encoder, currentReply } = templates;
  useEffect(() => {
    const revision = ++netRevision.current;
    const expected = networkKey(run.mode, net, adv);
    api.networkSettings().then(answer => {
      if (netRevision.current !== revision) return;
      setNetSettings(answer);
      // The starting preset changed from 3e-4 to 1e-3 (record 7.199), but its old explicit rate stayed in browser
      // storage. Upgrade only that otherwise-identical restored preset. Check once per browser, including when no
      // upgrade is needed: Undo, a later edit or an imported configuration must keep its chosen rate on reload.
      if (!oncePerBrowser(PRESET_RATE_KEY)) return; // Without durable storage, do not repeatedly override a rate the user may have restored.
      const saved = answer.settings?.[encoder];
      if (!currentReply(revision, encoder, expected) || run.mode !== 'scratch'
        || !['graph_transformer', 'rgcn', 'gatv2'].includes(encoder) || saved?.origin !== 'publication'
        || adv.learning_rate !== 0.0003 || saved.advanced.learning_rate !== 0.001
        || !answer.network_fields.every((field: string) => net[field] === saved.network[field])
        || !answer.advanced_fields.every((field: string) => field === 'learning_rate' || adv[field] === saved.advanced[field])) return;
      setConfig(c => networkKey(c.run.mode, c.run.network ?? {}, c.run.advanced ?? {}) !== expected ? c : ({ ...c,
        run: { ...c.run, advanced: { ...c.run.advanced, learning_rate: saved.advanced.learning_rate } } }));
      setPresetRateUpdated(true);
    })
      .catch(e => { if (netRevision.current === revision) setNetMessage({ level: 'error', text: `Backend network settings unavailable (${e.message}).`,
        reason: 'the templates could not be read from the backend' }); });
    return () => { ++netRevision.current; flush(); };
  }, []);
}

/** A configuration that leaves a value out would silently run the schema default. Fill it from the backend instead. */
function useFillLeftOutValues(templates: Templates, net: Json, adv: Json, setConfig: SetConfig) {
  const { entry, netFields, advFields, encoder } = templates;
  useEffect(() => {
    if (!entry) return;
    const missingNet = netFields.filter(field => net[field] === undefined || net[field] === null);
    const missingAdv = advFields.filter(field => adv[field] === undefined || adv[field] === null);
    if (net.encoder_type && !missingNet.length && !missingAdv.length) return;
    setConfig(c => ({ ...c, run: { ...c.run,
      network: { ...(c.run.network ?? {}), ...pick(entry.network, missingNet), encoder_type: encoder },
      advanced: { ...(c.run.advanced ?? {}), ...pick(entry.advanced, missingAdv) } } }), false);
  }, [entry, JSON.stringify(net), JSON.stringify(adv)]);
}

/** The values of this run that differ from its encoder's template, whether that is said (not while an edit is still to be
 *  written into the template), and where the template came from, in words. */
function templateDifferences(templates: Templates, net: Json, adv: Json) {
  const { entry, netFields, advFields, pending } = templates;
  const settingDifferences = entry ? [
    ...netFields.map(field => ({ field, current: net[field], saved: entry.network[field] })),
    ...advFields.map(field => ({ field, current: adv[field], saved: entry.advanced[field] })),
  ].filter(row => row.current != null && row.current !== row.saved) : [];
  const differs = settingDifferences.length > 0 && !pending.current;
  const originLabel = entry && ORIGIN[entry.origin];
  return { settingDifferences, differs, originLabel };
}

/** The budget, and what keeps the network from learning in it: soft actor-critic values measured to learn late, or a budget
 *  no larger than the warm-up or a batch. */
function trainingWarnings(run: Json, adv: Json, entry: Json) {
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
  return { budget, sacSlow, starved };
}

/** The network and the component list of the saved model a Mode loads, which the configuration follows - the model's weights
 *  only fit the network and the list it was trained with -, with the window's word on it. */
function useNetworkFollowsModel(templates: Templates, { loads, model, net, source, run, setConfig, chooseList }: { loads: boolean;
  model: ModelReply | null; net: Json; source: Json; run: Json; setConfig: SetConfig; chooseList: (value: string, record?: boolean) => void }) {
  const { netFields, encoder, setNetMessage } = templates;
  const savedModel: Json = loads ? model?.description?.contract?.model_config : null;
  const savedNet: NetworkConfig | null = loads ? networkOf(model?.description, netFields) : null;
  const archDiffers = !!savedNet && Object.keys(savedNet).some(field => savedNet[field] !== (field === 'encoder_type' ? encoder : net[field]));
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
    const named = `${designName(savedNet)} ${savedModel.hidden_dim}/${savedModel.heads}/${savedModel.layers}`;
    setNetMessage(seen ? { level: 'warn',
      text: `The network stays ${named}: this run loads a saved model, and a saved model only loads into the network it was trained with. A new network needs New model.` }
      : { level: 'ok', text: `The network is now the saved model's, ${named}: a saved model only loads into the network it was trained with.`,
        about: JSON.stringify([run.mode, source.run_dir, source.checkpoint_id]) });
    setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...savedNet } } }), false);
  }, [loads, archDiffers, JSON.stringify(savedNet)]);
  useEffect(() => setNetMessage(message => message?.level === 'warn' ? null : message), [source.run_dir, source.checkpoint_id, run.mode]);
  // The component list follows the chosen model as its network does: its weights only fit the list it was trained with.
  const savedList: string | undefined = loads ? model?.vocabulary?.name : undefined;
  useEffect(() => { if (savedList && savedList !== (net.vocabulary ?? 'standard')) chooseList(savedList, false); }, [savedList, net.vocabulary]);
  return { savedModel, savedNet, archDiffers };
}

/** The choice of a model: the newest model saved under the RL model label as a suggestion, "Use this save point" and the
 *  Mode; of the save points pressed, only the newest lands. */
function useModelChoice(templates: Templates, { label, config, loads, source, runs, run, setConfig }: { label: string; config: Json; loads: boolean;
  source: Json; runs: Json[]; run: Json; setConfig: SetConfig }) {
  const { netFields, setNetMessage } = templates;
  // The source is chosen, never filled in (record 7.265). Until then a Mode that loads a model filled it by itself with the
  // newest model saved under the RL model label (record 7.159), at `latest`. That model is now a suggestion with a press,
  // "Newest model named ...: Use", which pins its newest save point as any choice does.
  // Asked 0.5 s after the last keystroke of the label, as the checks are (record 7.279): each answer walks every run's
  // name under the output folder, and one went out at every key.
  const { value: suggested } = useRequest<Json>(() => api.defaultModel(label, config.project.name), [label, loads, source.run_dir],
    { enabled: loads && !source.run_dir, delay: 500 });
  // "Use this save point" (record 7.265): the draft's source becomes exactly that save point - a concrete id, never "latest" -
  // and the model's network and component list come with it, as ONE Undo step (they used to follow later, by themselves).
  // The save point being read (pointKey), null when none is: its own "Use this save point" says "Using..." (branch record
  // SIF-85; the press showed nothing until the window closed).
  const [usingPoint, setUsingPoint] = useState<string | null>(null);
  // Only the newest press lands (record 7.278, Astra's review of 2026-10-08; as Load run's generation number, 7.270): a save
  // point chosen before it and answered later changes nothing, and New model chosen meanwhile lets a pending one go.
  const pointSerial = useNewest();
  // A saved model's name, as the saved models table lists it: from its run's row (the folder's name when the run is not listed).
  const nameOf = (dir: string) => modelNameAt(runs, String(dir));
  // True once the save point is the draft's (the RL model window then closes, user request 2026-10-09), false when it
  // could not be read or a newer choice came first.
  const useSavePoint = (run_dir: string, checkpoint_id: string): Promise<boolean> => {
    const mine = pointSerial.next(), stale = () => !mine();
    setUsingPoint(pointKey(run_dir, checkpoint_id)); setNetMessage(null);
    return readSavePoint(run_dir, checkpoint_id, netFields).then(point => {   // savePoint.ts: Load run and New run like this take one the same way
      if (stale()) return false;
      setConfig(c => ({ ...c, run: withSavePoint(c.run, point) }));
      // The save point by its evaluations, as the model line names it (branch record SIF-67: "from its save point ckpt-00000006-a1").
      setNetMessage({ level: 'ok', text: `The next run ${run.mode === 'frozen' ? 'evaluates' : 'fine-tunes'} ${nameOf(run_dir)} from its save point ${
        pointText(point.checkpoint_id)}, with its network (one Undo step takes it back).`,
        about: JSON.stringify([run.mode, run_dir, point.checkpoint_id]) });
      return true;
    }).catch((e: Error) => { if (!stale()) setNetMessage({ level: 'error', text: `That save point could not be read: ${e.message}`,
      reason: 'the chosen save point could not be read', point: pointKey(run_dir, checkpoint_id) }); return false; })
      .finally(() => { if (!stale()) setUsingPoint(null); });
  };
  // A Mode is one Undo step. New model clears the saved model chosen: scratch never loads one (a source left there is a
  // validation warning), and coming back to Fine-tune asks for the choice again. A save point still on its way is let go too.
  const chooseMode = (mode: string) => {
    if (mode === 'scratch') { pointSerial.drop(); setUsingPoint(null); }
    setConfig(c => ({ ...c, run: { ...c.run, mode,
      ...(mode === 'scratch' && c.run.model_source?.run_dir ? { model_source: { ...c.run.model_source, run_dir: null, checkpoint_id: 'latest' } } : {}),
      ...(mode === 'scratch' ? { network: { ...(c.run.network ?? {}), ...newModelList({ ...c, run: { ...c.run, mode } }),
        ...templateInputs(c.run.network?.encoder_type ?? 'graph_transformer', c.run.network, mode) } } : {}) } }));
  };
  return { suggested, usingPoint, nameOf, useSavePoint, chooseMode };
}

/** The network in use, in short, beside the RL model button, and the next run's model in one line (rlModelText.ts), handed
 *  to the page for the header's Next line as they change. In a Mode that loads a model the configuration's network is that
 *  model's (useNetworkFollowsModel). */
function useModelLines(templates: Templates, { net, source, nameOf, model, run, noMode, adv, loads, onNext }: { net: Json; source: Json;
  nameOf: (dir: string) => string; model: ModelReply | null; run: Json; noMode: boolean; adv: Json; loads: boolean; onNext?: (next: NextModel) => void }) {
  const { entry, encoder, usesHeads } = templates;
  const sizes = networkSizes(net, entry);
  const netShort = networkShort(encoder, sizes, usesHeads, net);
  const sourceName = source.run_dir ? nameOf(source.run_dir) : null;
  const pointAt = model?.description?.counters?.evaluations_committed ?? pointEvaluations(source.checkpoint_id);
  const modelLine = modelLineText({ run, noMode, source, entry, encoder, netShort, sourceName, pointAt });
  const switchesLine = switchesText(run, adv);   // under the model line (review of branch record SIF-103)
  const nextModel = nextModelText({ run, adv, noMode, source, sourceName, pointAt });
  useEffect(() => onNext?.({ model: nextModel, network: netShort }), [nextModel, netShort]);
  const netTitle = networkTitle({ loads, source, run, encoder, ...sizes, usesHeads, net });
  return { modelLine, switchesLine, netTitle };
}

/** The model in use's reward, all six fields (a field its contract leaves out as the run takes it), and those the next run's
 *  differs in (branch record SIF-103). Fine-tune keeps the model's critics only with the same reward and conditions; matching
 *  it meant typing it field by field into Reward and conditions' Advanced, and the facts showed four of the six.
 *  "Use this model's reward" takes all six as one Undo step; the conditions stay the user's. */
function savedModelReward(loads: boolean, model: ModelReply | null, reward: Json, run: Json, set: (fields: Json, record?: boolean) => void) {
  const savedReward: Json = loads && model?.description?.contract?.reward_settings
    ? { ...REWARD_DEFAULTS, ...model.description.contract.reward_settings } : null;
  const rewardApart: string[] = savedReward ? Object.keys(REWARD_DEFAULTS).filter(field => savedReward[field] !== reward[field]) : [];
  const useModelReward = () => { if (savedReward) set({ reward: { ...run.reward, ...pick(savedReward, Object.keys(REWARD_DEFAULTS)) } }); };
  return { savedReward, rewardApart, useModelReward };
}

/** Whether Run configuration's notice is up - an error or a warning - and why, in a few words, with the id of the block in the
 *  window that says it in full. */
function networkNotice(templates: Templates, { error, modelChecked, model, run, differs, starved, archDiffers, sacSlow }: { error: string | null;
  modelChecked: boolean; model: ModelReply | null; run: Json; differs: boolean; starved: boolean; archDiffers: boolean; sacSlow: string[] }) {
  const { netMessage, offeredEncoders, encoder, entry } = templates;
  const networkError = error || netMessage?.level === 'error' || !offeredEncoders.includes(encoder)
    || (modelChecked && model?.compatibility?.compatible === false);
  const networkWarning = netMessage?.level === 'warn' || (run.mode === 'scratch' && (differs || entry?.problem))
    || starved || archDiffers || sacSlow.length > 0;
  // Why Run configuration's notice is up, in a few words (branch record SIF-46): it read "Review the settings in RL model."
  // for every one of the reasons above, and the window had to be searched for it. The first that applies, the errors first,
  // so the words match the notice's colour; the window says each in full. With each, the id of the block in the window that
  // says it (branch record SIF-86), where the notice's "RL model..." opens the window.
  const template = designName({ encoder_type: encoder });
  const [networkReason, networkAnchor]: [string | null, string | null] = !offeredEncoders.includes(encoder) ? [`${template} is unavailable`, 'net-unavailable']
    : modelChecked && model?.compatibility?.compatible === false ? ['the saved model is NOT compatible with this run', 'net-compat']
    : error ? ['the saved model could not be checked', 'net-check-error']
    : netMessage?.level === 'error' ? [netMessage.reason ?? netMessage.text, 'net-message']
    : archDiffers || netMessage?.level === 'warn' ? ["the network was taken back to the saved model's", 'net-message']
    : starved ? ['the budget is too small for the network to learn', 'net-starved']
    : sacSlow.length ? [`with ${sacSlow.join(' and ')}, the network learned late or not at all in tests`, 'sac-values']
    : run.mode === 'scratch' && entry?.problem ? [`the saved ${template} template values could not be used`, 'template-problem']
    : run.mode === 'scratch' && differs ? [`this run's values differ from the ${template} template`, 'network-differences']
    : [null, null];
  return { networkError, networkWarning, networkReason, networkAnchor };
}

/** The notice's "RL model..." opens the window AT the block its reason names (branch record SIF-86): it opened at the top, and
 *  the block was further down - often under the whole saved models table - to be searched for. Its folds are opened, and it
 *  is scrolled to the middle once the window has drawn and has its styles; one scroll per press. The model line's button
 *  opens at the top. */
function useOpenAtBlock(networkWindow: ReturnType<typeof usePopupWindow>) {
  const [openingAt, setOpeningAt] = useState<string | null>(null);
  const openAt = (anchor: string | null) => { if (networkWindow.open() && anchor) setOpeningAt(anchor); };
  useEffect(() => {
    const popup = networkWindow.popup, id = openingAt;
    if (!popup) { if (id) setOpeningAt(null); return; }
    if (!id) return;
    let current = true;
    const reveal = () => {
      const block = current && !popup.closed ? popup.document.getElementById(id) : null;
      if (!block) return;
      observer.disconnect();
      for (let fold = block.closest('details'); fold; fold = fold.parentElement?.closest('details') ?? null) fold.open = true;
      block.scrollIntoView({ block: 'center' });
      setOpeningAt(null);
    };
    // The optional window may still be downloading. Reveal the block after its content and styles arrive, once per press.
    const observer = new MutationObserver(reveal);
    void styled(popup).then(() => {
      if (!current || popup.closed) return;
      observer.observe(popup.document.body, { childList: true, subtree: true });
      reveal();
    });
    return () => { current = false; observer.disconnect(); };
  }, [openingAt, networkWindow.popup]);
  return openAt;
}
