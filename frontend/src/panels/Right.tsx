import { useRequest } from '../store';
import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, bytes, copy, Json, num } from '../api';
import { ModelChooser } from './ModelChooser';
import { CircuitGraphView } from './CircuitGraphView';
import { ModelStructure } from './ModelStructure';
import { ComponentList } from './Pdk';
import { SearchSettings } from './SearchSettings';
import { Typed } from './Typed';
import { BLOCKED, usePopupWindow } from './popupWindow';

function Num({ label, value, onChange, title, nullable, disabled, note, after, placeholder, bounded }: { label: string; value: Json; onChange: (v: Json) => void; title?: string; nullable?: boolean; disabled?: boolean; note?: string; after?: ReactNode; placeholder?: string; bounded?: boolean }) {
  // `Typed` keeps what is being typed while the box has focus ("0." and "3e-" are steps towards 0.005 and 3e-4, not
  // values) and drops it as soon as the value changes from outside (reset button, undo, another encoder), focus or not.
  // `bounded`: a 0-to-1 reward coefficient - a number box that declares the backend's range, drawn without the browser's
  // up/down arrows (record 7.171, user: "remove the toggle for these 0 to 1 value boxes"; styles.css `input.bounded`).
  const box = <Typed className={bounded ? 'numeric bounded' : 'numeric'} value={value} disabled={disabled} placeholder={placeholder ?? (nullable ? 'none' : '')}
    {...(bounded ? { type: 'number', min: 0, max: 1, step: 'any', inputMode: 'decimal' as const,
      'aria-invalid': typeof value !== 'number' || value < 0 || value > 1 } : {})}
    format={v => v === null || v === undefined ? '' : String(v)}
    parse={t => t.trim() === '' ? { value: nullable ? null : 0 } : Number.isFinite(Number(t)) ? { value: Number(t) } : undefined}
    onChange={onChange} />;
  return (
    <label title={title} className={disabled ? 'disabled' : undefined}><span>{label}{note && <span className="hint"> - {note}</span>}</span>
      {after ? <span className="with-unit">{box}{after}</span> : box}</label>);
}

// A size that the configuration keeps in whole bytes, typed as a number plus a unit. The saved bytes change only when a
// number is typed; choosing another unit converts the shown number and leaves the size alone (1.5 GiB -> 1536 MiB).
// The shown number is always exact - the shortest decimal that gives the saved bytes back - never a rounded version.
const BYTE_UNITS: [string, number][] = [['bytes', 1], ['KiB', 1024], ['MiB', 1024 ** 2], ['GiB', 1024 ** 3], ['TiB', 1024 ** 4]];
const unitSize = (name: string) => BYTE_UNITS.find(([unit]) => unit === name)?.[1] ?? 1;
// The shortest decimal number that gives back exactly these bytes in that unit; undefined when `places` decimals cannot.
const inUnit = (n: number, size: number, places: number): number | undefined => {
  for (let p = 0; p <= places; p++) { const shown = Number((n / size).toFixed(p)); if (Math.round(shown * size) === n) return shown; }
  return undefined;
};
const bestUnit = (n: Json): string => typeof n !== 'number' ? 'GiB'
  : ([...BYTE_UNITS].reverse().find(([, size]) => n >= size && inUnit(n, size, 3) !== undefined) ?? BYTE_UNITS[0])[0];
// Exact in that unit, with as many decimals as it takes (1395864371 bytes in TiB = 0.00126953125); the full quotient
// only for a size that is not a whole number of bytes, which the schema would refuse anyway.
const showIn = (n: number, size: number): string => String(inUnit(n, size, 15) ?? n / size);

function ByteSize({ label, value, onChange, title, empty }: { label: string; value: Json; onChange: (v: Json) => void; title?: string; empty: string }) {
  const [unit, setUnit] = useState(() => bestUnit(value));
  const sent = useRef<Json>(value);
  const size = unitSize(unit);
  const toBytes = (t: string, s: number): Json => t.trim() === '' ? null : Math.round(Number(t) * s);
  // A value that did not come from this box (loaded configuration, undo) is shown in the unit that reads best.
  useEffect(() => { if (value !== sent.current) { sent.current = value; if (typeof value === 'number') setUnit(bestUnit(value)); } }, [value]);
  const send = (b: Json) => { sent.current = b; onChange(b); };
  return (
    <label title={`${title ? title + ' ' : ''}${typeof value === 'number' ? `Saved as ${value} bytes.` : `Empty = ${empty}.`}`}><span>{label}</span>
      <span className="with-unit">
        {/* The same box as everywhere else (`Typed`): what is being typed survives, in the unit chosen here. */}
        <Typed className="numeric" value={value} placeholder={empty} format={v => typeof v === 'number' ? showIn(v, size) : ''}
          parse={t => { const b = toBytes(t, size); return b === null || Number.isFinite(b) ? { value: b } : undefined; }} onChange={send} />
        {/* Another unit shows the same size in other words; nothing is saved by it. */}
        <select aria-label={`${label}: unit`} value={unit} onChange={e => setUnit(e.target.value)}>
          {BYTE_UNITS.map(([name]) => <option key={name}>{name}</option>)}</select></span></label>);
}

type Every = 'evaluations' | 'seconds';

// A whole module of the right column folded under its own heading (user request 2026-09-21). It starts OPEN; the
// viewer's choice is kept in this browser. It is a <details>, so the content stays mounted while folded: nothing inside
// stops working (the network still follows a chosen model, the output root is still looked at). Folded, the line says the
// module's main values, and whether something inside asks for attention - an error or a warning is never just hidden.
function Module({ id, title, summary, children }: { id: string; title: string; summary: string; children: ReactNode }) {
  const key = `gator-workbench-module-${id}`;
  const [open, setOpen] = useState(() => { try { return localStorage.getItem(key) !== 'closed'; } catch { return true; } });
  const [inside, setInside] = useState<'error' | 'warn' | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const toggle = (now: boolean) => { setOpen(now); try { localStorage.setItem(key, now ? 'open' : 'closed'); } catch { /* private window: not remembered */ } };
  // Watched in the page itself, not per render: parts inside keep their own state (the model list, the graph view) and
  // can show an error without this component rendering again.
  useEffect(() => {
    const node = body.current; if (!node) return;
    const look = () => setInside(node.querySelector('.error') ? 'error' : node.querySelector('.warn') ? 'warn' : null);
    look();
    const observer = new MutationObserver(look);
    observer.observe(node, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);
  return (
    <section className="panel">
      <details className="section module" open={open} onToggle={e => { if (e.target === e.currentTarget) toggle(e.currentTarget.open); }}>
        <summary title={open ? 'Fold this module into one line' : 'Unfold this module'}><h3>{title}</h3>
          {!open && inside && <span className={`module-attention ${inside}`}>{inside === 'error' ? 'error inside' : 'warning inside'}</span>}
          {!open && <span className="hint module-summary" title={summary}>{summary}</span>}</summary>
        <div className="module-body" ref={body}>{children}</div>
      </details>
    </section>);
}

// Settings stored per encoder in the backend (src/gator_workbench/network_presets.py). The lists are
// only a fallback for the moment before the backend answers; the backend's own lists are used afterwards.
const NETWORK_FIELDS = ['hidden_dim', 'heads', 'layers'];
const pick = (source: Json, fields: string[]): Json =>
  Object.fromEntries(fields.filter(f => source?.[f] !== undefined && source?.[f] !== null).map(f => [f, source[f]]));
const Check = ({ label, value, onChange, title, disabled }: { label: string; value: boolean; onChange: (v: boolean) => void; title?: string; disabled?: boolean }) => (
  <label className="check" title={title}><input type="checkbox" checked={!!value} disabled={disabled} onChange={e => onChange(e.target.checked)} />{label}</label>);

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
  hidden_dim: 'Hidden width', heads: 'Heads', layers: 'Layers',
  ...Object.fromEntries(ADVANCED_ROWS.flat().map(([name, label]) => [name, label])),
};

/** The encoders in short, for the line beside RL networks... (the window names them in full). */
const SHORT_ENCODER: Record<string, string> = { graph_transformer: 'GT', rgcn: 'RGCN', gatv2: 'GATv2' };

export function RunPanel({ config, setConfig, runs, circuit, schema }: { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; circuit: Json; schema: Json }) {
  const run = config.run;
  const llmOnly = run.search?.method === 'llm';
  const set = (fields: Json, record = true) => setConfig(c => ({ ...c, run: { ...c.run, ...fields } }), record);
  const setAdv = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, advanced: { ...(c.run.advanced ?? {}), ...fields } } }));
  const setNet = (fields: Json) => setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...fields } } }));
  const source = run.model_source ?? {};
  // Looking at a saved model (structure table, circuit graph view) must not need a Mode that loads it: in scratch the
  // selection is kept HERE, outside the configuration (a model_source in scratch would be a validation warning).
  const [looking, setLooking] = useState(false);
  const [look, setLook] = useState<{ run_dir: string | null; checkpoint_id: string }>({ run_dir: null, checkpoint_id: 'latest' });
  const adv = run.advanced ?? {};
  const net = run.network ?? {};
  // Keep the configuration, preset writes and compatibility checks here even when the window is closed.
  const networkWindow = usePopupWindow('gator-rl-networks', {
    title: 'GATOR - RL networks', features: 'popup,width=1100,height=900',
    rootId: 'rl-networks-root', rootClass: 'rl-networks-window', closeOnUnmount: true,
  });

  // Only a Mode that loads the model asks about it: a model_source left over from fine_tune is ignored in scratch, and
  // was compiled and checked after every edit there all the same (audit 2026-09-30).
  const modelChecked = run.mode !== 'scratch' && !!source.run_dir && !llmOnly;
  const { value: fresh, error, loading: modelLoading } = useRequest<Json>(signal => api.model(source.run_dir, source.checkpoint_id ?? 'latest', config, signal),
    [JSON.stringify([config.circuit, config.parameters, config.targets, config.measurements, run.mode, source,
      run.connection_profile_id, run.seed, run.network, run.advanced, run.reward, run.conditions, config.research?.split])],
    { enabled: modelChecked, delay: 250 });
  // While the SAME saved model is checked again after an edit (0.25 s and a compile), what is known about it - its facts,
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
  const toggleCorner = (id: string, checked: boolean) => set({ conditions: { ...run.conditions,
    // Re-adding a corner follows schema order, so toggling it back restores the original plan.
    corners: checked ? cornerIds.filter(c => c === id || corners.includes(c)) : corners.filter(c => c !== id) } });

  // Per-encoder settings live in the backend: choosing an encoder READS its settings, editing a value WRITES them back
  // for that encoder. The configuration always carries explicit values, so what is shown is what runs.
  const [netSettings, setNetSettings] = useState<Json>(null);
  const [netMessage, setNetMessage] = useState<{ level: string; text: string } | null>(null);
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
  const offeredEncoders: string[] = netSettings?.encoders ?? ['graph_transformer', 'rgcn', 'gatv2'];
  const usesHeads: boolean = entry ? !!entry.uses_heads : ['graph_transformer', 'gatv2'].includes(encoder);
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
  const reset = (to: string) => {
    const revision = ++netRevision.current;
    const expected = networkKey(run.mode, net, adv);
    pending.current = null; window.clearTimeout(timer.current);
    writing.current = writing.current.then(() => api.resetNetworkSettings(encoder, to)).then(e => {
      if (!currentReply(revision, encoder, expected)) return;
      remember(e); applyEntry(e);
      setNetMessage({ level: 'ok', text: to === 'publication' ? `${encoder}: publication preset restored in the backend.` : `${encoder}: GATOR baseline stored in the backend.` });
    }).catch(e => { if (currentReply(revision, encoder)) setNetMessage({ level: 'error', text: e.message }); });
  };
  useEffect(() => {
    const revision = ++netRevision.current;
    api.networkSettings().then(s => { if (netRevision.current === revision) setNetSettings(s); })
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
  const originLabel = entry && ({ publication: 'publication preset', gator_baseline: 'GATOR baseline', custom: 'edited, saved in the backend' } as Json)[entry.origin];
  const budget: number = run.max_evaluations;
  const starved = run.mode !== 'frozen' && typeof budget === 'number' && (budget <= (adv.warmup_transitions ?? 0) || budget < (adv.batch_size ?? 0) + 1);
  // resume / fine_tune / frozen LOAD a saved model, and its weights only fit the network they were trained with (the
  // backend refuses any other network in all three). So there is nothing to set up then: the block for a NEW network
  // is shown in scratch only, and otherwise the configuration takes the network of the chosen model - the act is the
  // choice of that model. Only the network follows; the training numbers under Advanced stay the user's.
  const loads = run.mode !== 'scratch';
  // The RL model's own label (record 7.159, user: "Give the RL model its own label, independent of the project name"):
  // typed here, else the task's run label. A run that saves a model files it under this name.
  const label: string = (run.model_label ?? '').trim() || config.project.task_name;
  const savedModel: Json = loads ? model?.description?.contract?.model_config : null;
  const savedNet: Json = savedModel?.encoder_type ? { encoder_type: savedModel.encoder_type, ...pick(savedModel, netFields),
    operating_points: !!model?.description?.contract?.feature_schema?.op_columns?.length } : null;
  const archDiffers = !!savedNet && Object.keys(savedNet).some(f => savedNet[f] !== (f === 'encoder_type' ? encoder : net[f]));
  const followed = useRef<string | null>(null);
  useEffect(() => {
    if (!loads) { followed.current = null; return; }
    if (!archDiffers) return;
    // The SAME model a second time = something else changed the network meanwhile (an applied agent suggestion, an
    // opened configuration). It is taken back as well, but said: a silent revert would read as a button that does nothing.
    const key = JSON.stringify([source.run_dir, model?.description?.checkpoint_id, savedNet]);
    if (followed.current === key) setNetMessage({ level: 'warn', text: `The network stays ${savedNet.encoder_type} ${savedModel.hidden_dim}/${savedModel.heads}/${savedModel.layers}: this run loads a saved model, and a saved model only loads into the network it was trained with. A new network needs Mode scratch.` });
    followed.current = key;
    setConfig(c => ({ ...c, run: { ...c.run, network: { ...(c.run.network ?? {}), ...savedNet } } }), false);
  }, [loads, archDiffers, JSON.stringify(savedNet)]);
  useEffect(() => setNetMessage(m => m?.level === 'warn' ? null : m), [source.run_dir, source.checkpoint_id, run.mode]);
  // The component list follows the chosen model as its network does: its weights only fit the list it was trained with.
  const savedList: string | undefined = loads ? model?.vocabulary?.name : undefined;
  useEffect(() => { if (savedList && savedList !== (net.vocabulary ?? 'standard')) chooseList(savedList, false); }, [savedList, net.vocabulary]);

  // Default the RL model to the newest model saved under the RL model label (record 7.159; before it, under the project
  // name, still asked for the runs remembered that way), and its `latest` checkpoint (not `best`) - in a Mode that
  // loads a model. In scratch it used to be written into the configuration on page load: a validation warning
  // (source_ignored_in_scratch), an undo step nobody made and a model compile on every edit. Filled by itself, it is no
  // Undo step either: one Undo takes back the Mode choice and the model it brought.
  // Its answer never overwrites a model chosen meanwhile, and never lands in scratch (the first reading of the default
  // hashes the checkpoint files, which takes seconds on D:).
  useEffect(() => {
    if (source.run_dir || !loads) return;
    let live = true;
    api.defaultModel(label, config.project.name).then(d => live && d.run_dir && setConfig(c => c.run.mode === 'scratch' || c.run.model_source?.run_dir ? c
      : { ...c, run: { ...c.run, model_source: { ...(c.run.model_source ?? {}), run_dir: d.run_dir, checkpoint_id: 'latest' } } }, false)).catch(() => undefined);
    return () => { live = false; };
  }, [label, loads]);


  // The network in use, in short, beside the RL networks button (user, 2026-10-03: "show the current network selection next to
  // the RL network button in short"). In a Mode that loads a model the configuration's network is that model's (above).
  const hidden = net.hidden_dim ?? entry?.network?.hidden_dim ?? 32, heads = net.heads ?? entry?.network?.heads ?? 4, layers = net.layers ?? entry?.network?.layers ?? 2;
  const components = net.vocabulary && net.vocabulary !== 'standard' ? net.vocabulary.replace(/^pdk:/, '') : null;
  const netShort = llmOnly ? 'not used (LLM only)' : loads && !source.run_dir ? 'no saved model chosen'
    : [`${SHORT_ENCODER[encoder] ?? encoder} ${hidden}/${usesHeads ? heads : '–'}/${layers}`, net.operating_points ? 'op. points' : null,
      components ? `${components} parts` : null, loads ? 'saved model' : null].filter(Boolean).join(' · ');
  const netTitle = llmOnly ? 'LLM only does not use an RL network.' : loads && !source.run_dir ? `Mode ${run.mode} loads a saved model: choose one in RL networks; the run then uses its network.`
    : `The network in use: ${encoder}, hidden ${hidden}, ${usesHeads ? `heads ${heads}` : 'no attention heads'}, layers ${layers}; nominal operating points ${net.operating_points ? 'on' : 'off'}; `
      + `components ${components ?? 'standard'}${loads ? `. It is the network of the saved model this run loads (${source.run_dir}).` : '.'} RL networks... changes it.`;
  const folded = [run.mode, run.model_label?.trim() ? `model ${run.model_label.trim()}` : null, typeof budget === 'number' ? `${budget} evaluations` : null,
    `${encoder} ${net.hidden_dim ?? '?'}/${net.heads ?? '?'}/${net.layers ?? '?'}`,
    net.vocabulary && net.vocabulary !== 'standard' ? `knows ${net.vocabulary.slice(4)}` : null].filter(Boolean).join(' - ');
  const networkError = error || netMessage?.level === 'error' || !offeredEncoders.includes(encoder)
    || (modelChecked && model?.compatibility?.compatible === false);
  const networkWarning = netMessage?.level === 'warn' || (!loads && (differs || entry?.problem))
    || (starved && run.search?.method !== 'llm_warmstart') || archDiffers;
  return (
    <>
    <Module id="run" title="Run configuration" summary={folded}>
      <label title="scratch: random init, new run. resume: same task, same run, full state. fine_tune: compatible weights, new task, new run with a parent. frozen: no updates at all.">Mode
        <select value={run.mode} onChange={e => set({ mode: e.target.value })}>
          {(llmOnly ? ['scratch', 'resume'] : run.search?.method && run.search.method !== 'sac' ? ['scratch', 'resume', 'fine_tune'] : ['scratch', 'resume', 'fine_tune', 'frozen']).map(m => <option key={m} value={m}>{m}</option>)}</select></label>
      <div className="rl-networks-row"><span className={`hint net-short${llmOnly || (loads && !source.run_dir) ? '' : ' net-code'}`} title={netTitle}>{netShort}</span>
        <button className="rl-networks-open" disabled={llmOnly}
          title={llmOnly ? 'LLM only does not use an RL network.' : 'Open RL network settings, saved models, and model views.'}
          onClick={() => networkWindow.open()}>RL networks...</button></div>
      {networkWindow.blocked && <p className="error" role="alert">{BLOCKED}</p>}
      {!llmOnly && (networkError || networkWarning) && <p className={networkError ? 'error' : 'warn'}>Review the settings in RL networks.</p>}
      {/* Only while the model is checked: in scratch the last check's suggestion stayed, never asked again (review of 2026-10-01) */}
      {modelChecked && model?.suggestion && model.suggestion.mode !== run.mode && <p className="warn">Suggested: <button className="text-link mode-suggestion"
        title={`Set Mode to ${model.suggestion.mode}`} onClick={() => set({ mode: model.suggestion.mode })}>{model.suggestion.mode}</button> - {model.suggestion.reason}
        {model.suggestion.requires_confirmation ? ' (needs your confirmation)' : ''}</p>}
      <SearchSettings run={run} schema={schema} set={set} />
      {/* Below Search method: Mode first, Search method second (record 7.150). */}
      <label title={`RL model label: the name this run's RL model is saved under. Mode resume, fine_tune and frozen start from the newest model saved under it. Empty: the task's run label (${config.project.task_name}).`}>RL model label
        <input className="model-label" value={run.model_label ?? ''} placeholder={config.project.task_name} disabled={llmOnly} maxLength={80}
          onChange={e => set({ model_label: e.target.value.trim() ? e.target.value : null })} /></label>
      <Num label="Concurrent Spectre jobs" disabled={llmOnly} value={run.concurrency} onChange={v => set({ concurrency: v })} title="Independent simulation jobs at once. NOT the thread count of one simulation." />
      {circuit?.max_concurrency && run.concurrency > circuit.max_concurrency && <p className="error">This task supports at most {circuit.max_concurrency} jobs.</p>}
      <Num label="Evaluation budget (max_evaluations)" value={run.max_evaluations} onChange={v => set({ max_evaluations: v })}
        title="NEW candidate evaluations that may START in the whole run, shared by all workers. Baselines, warm-up and failures count. Episode resets do not reset it." />
      <Num label="Max Spectre launches" nullable value={run.max_spectre_launches} onChange={v => set({ max_spectre_launches: v })} title="Optional hard cap incl. retries and failures." />
      <Num label="Max retries per evaluation" value={run.max_retries ?? 0} onChange={v => set({ max_retries: v })} title="A retry keeps the evaluation_id and costs a launch, not an evaluation." />
      <Num label="Wall-time limit (s)" nullable value={run.max_wall_seconds} onChange={v => set({ max_wall_seconds: v })} />
      <Num label="Random seed (target task)" value={run.seed} onChange={v => set({ seed: v })} title="Seed of THIS run. The source model's pretraining seed is recorded separately." />
      <Check label="Stop at the first feasible design" value={run.stop_at_first_feasible} onChange={v => set({ stop_at_first_feasible: v })} />
      <details><summary>Failure limits</summary>
        <Num label="Pause after N consecutive infrastructure failures" value={run.max_consecutive_infrastructure_failures ?? 3} onChange={v => set({ max_consecutive_infrastructure_failures: v })} />
        <Num label="Stop after N consecutive failed evaluations" value={run.max_consecutive_failures ?? 5} onChange={v => set({ max_consecutive_failures: v })}
          title={'When this many evaluations in a row fail (no valid result), the run stops safely: everything is saved and it ends as "failed", '
            + 'which Continue cannot pick up again. Reward v2.1 scores broken designs and learns from them, so a run exploring a region where many '
            + 'designs break may need a higher limit (1-1000).'} />
      </details>
      <h3>Reward and conditions</h3>
      {/* From Nominal only, every corner is planned; between the two corner policies the corners chosen stay chosen. */}
      <label>Training conditions<select value={run.conditions?.policy ?? 'off'} onChange={e => set({ conditions: {
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
      </tbody></table>
      {robust && !supportsCorners && <p className="error">Training corners require the registered real OTA7 task.</p>}
      {robust && (run.max_spectre_launches == null || run.max_spectre_launches < 1) && <p className="error">A positive launch cap is required for training corners.</p>}
      {robust && (run.max_retries ?? 0) !== 0 && <p className="error">Training corners require zero automatic retries.</p>}
      <label title="Capped: min(1, distance/scale). Compressed: (distance/scale)/(1 + distance/scale). Neither determines feasibility by reward sign.">Violation shape<select value={run.reward?.violation_shape ?? 'capped'} onChange={e => set({ reward: { ...run.reward, violation_shape: e.target.value } })}>
        <option value="capped">Capped</option><option value="compressed">Compressed</option></select></label>
      {gated && <Num label="Nominal gate band" value={run.reward?.nominal_gate_band ?? 0.5} onChange={v => set({ reward: { ...run.reward, nominal_gate_band: v } })} title="Strictly between 0 and 1. Gate-passing designs always rank above gate-failing designs." />}
      <label>Objective shape<select value={run.reward?.objective_shape ?? 'clipped'} onChange={e => set({ reward: { ...run.reward, objective_shape: e.target.value } })}><option value="clipped">Clipped</option><option value="compressed">Compressed</option></select></label>
      <Num label="Worst hard-spec share" bounded value={run.reward?.worst_spec_share ?? 0} onChange={v => set({ reward: { ...run.reward, worst_spec_share: v } })}
        title="0 to 1. Mix the weighted mean violation with the worst hard-spec violation. At 1, soft violations do not contribute to the penalty." />
      <Num label="Objective bonus weight" bounded value={run.reward?.objective_weight ?? 0} onChange={v => set({ reward: { ...run.reward, objective_weight: v } })}
        title="0 to 1. Applies only to a complete hard-feasible plan and the single objective selected in Specs." />
      <p className="hint reward-objective">Objective: {objective.length ? objective.map((t: Json) => `${t.direction_after_feasible} ${t.metric_id}`).join('; ') : 'none'}</p>
      {(run.reward?.objective_weight ?? 0) > 0 && !objective.length && <p className="warn">No active objective; the objective bonus is zero.</p>}
      <Num label="Tightest-margin bonus weight" bounded value={run.reward?.margin_weight ?? 0} onChange={v => set({ reward: { ...run.reward, margin_weight: v } })}
        title="Complete hard-feasible plans only. Equality constraints remain mandatory but do not contribute clearance." />
      {llmOnly && run.mode === 'resume' && <label>AI run to resume<select value={source.run_dir ?? ''}
        onChange={e => set({ model_source: { run_dir: e.target.value, checkpoint_id: 'latest' } })}>
        <option value="">Choose an AI-only run</option>{runs.filter((r: Json) => r.search?.method === 'llm').map((r: Json) =>
          <option key={r.run_dir} value={r.run_dir}>{r.task_name ?? r.run_dir}</option>)}</select></label>}
    </Module>
    {networkWindow.popup && networkWindow.root && createPortal(<section className="panel rl-networks-panel" aria-labelledby="rl-networks-title">
      {/* No close button of its own (user, 2026-10-03: "delete the cross button in RL network window"): the window's own close
          does it, and the settings are kept either way. */}
      <div className="rl-networks-heading"><h2 id="rl-networks-title">RL networks</h2></div>
      <p className="hint">Mode: <b>{run.mode}</b>. Changes apply to the current run configuration.</p>
      {llmOnly ? <p className="hint">LLM only does not use an RL network. Choose an SAC search method in Run configuration to edit these settings.</p> : <>
      {!loads && <>
      <h3>RL network</h3>
      <p className="hint">Independent of the agent language model. "No weights" means scratch, but an architecture is still required.
        Every encoder keeps its own settings in the backend: choosing one loads them, editing a value (here or under Advanced) saves it for that encoder.</p>
      <label>Encoder<select value={encoder} onChange={e => chooseEncoder(e.target.value)}>
        {offeredEncoders.map((m: string) => <option key={m} value={m}>{m}</option>)}
        {!offeredEncoders.includes(encoder) && <option value={encoder}>{encoder} (removed from the optimizer)</option>}</select></label>
      {!offeredEncoders.includes(encoder) && <p className="error">{encoder} is unavailable. Choose Graph Transformer, RGCN, or GATv2. Existing models need their matching historical optimizer version.</p>}
      <div className="row"><Num label="hidden" value={net.hidden_dim ?? entry?.network?.hidden_dim ?? 32} onChange={v => editNet({ hidden_dim: v })} />
        <Num label="heads" value={net.heads ?? entry?.network?.heads ?? 4} onChange={v => editNet({ heads: v })} disabled={!usesHeads} note={usesHeads ? undefined : 'ignored by this encoder'}
          title={usesHeads ? 'Attention heads. hidden must be divisible by heads.' : 'Only graph_transformer and gatv2 have attention heads. The number is still written into the checkpoint, so it is kept fixed here.'} />
        <Num label="layers" value={net.layers ?? entry?.network?.layers ?? 2} onChange={v => editNet({ layers: v })} /></div>
      <Check label="Nominal device operating points" value={net.operating_points ?? false} onChange={v => setNet({ operating_points: v })}
        title="Measured nominal device values and validity masks. Corner operating points are recorded but never replace the nominal network input. Changing this changes the model input schema." />
      <ComponentList value={net.vocabulary ?? 'standard'} onChoose={v => chooseList(v)} />
      {entry && <><p className="hint in-use">In use: <b>{settingDifferences.length ? 'current run settings' : originLabel}</b></p>
        <div className="row pair">
          <button disabled={entry.origin === 'publication' && !differs} onClick={() => reset('publication')} title="Forget the saved values of this encoder and return to the values taken from publications.">Publication preset</button>
          <button disabled={entry.origin === 'gator_baseline' && !differs} onClick={() => reset('gator_baseline')} title="The equal-size setting of all existing GATOR evidence and checkpoints. Suited to short runs.">GATOR baseline</button></div></>}
      {differs && <div className="note network-differences">
        <p className="warn">Current run values differ from the saved {encoder} defaults ({originLabel}).</p>
        <p className="hint">This run uses the values shown in the controls. Saved defaults are loaded when you choose an encoder; they do not replace an existing configuration on page reload.</p>
        <table className="grid small" aria-label="Network settings differences"><thead><tr><th>Setting</th><th>This run</th><th>Saved default</th></tr></thead><tbody>
          {settingDifferences.map(row => <tr key={row.field}><td title={row.field}>{NETWORK_SETTING_LABELS[row.field] ?? row.field}</td>
            <td className="numeric">{String(row.current)}</td><td className="numeric">{row.saved == null ? 'Not set' : String(row.saved)}</td></tr>)}
        </tbody></table>
        <div className="row pair"><button onClick={() => applyEntry(entry)} title="Replace this run's network and Advanced values with the saved defaults for this encoder.">Use saved defaults</button>
          <button onClick={() => { queueSave(net, adv); flush(); }} title="Keep this run's values and remember them as the defaults for this encoder.">Save as defaults</button></div>
      </div>}
      {entry?.problem && <p className="warn">{entry.problem}</p>}</>}
      {netMessage && <p className={`net-message ${netMessage.level === 'error' ? 'error' : netMessage.level === 'warn' ? 'warn' : 'hint'}`}>{netMessage.text}</p>}
      {starved && run.search?.method !== 'llm_warmstart' && <p className="warn">Budget {budget} with warm-up {adv.warmup_transitions} and batch size {adv.batch_size}: {budget <= (adv.warmup_transitions ?? 0) ? 'every evaluation is a random warm-up action, so the policy never acts' : 'one batch is never filled, so the network never learns'}.
        Published settings assume thousands of simulations. Lower them under Advanced{loads ? ' or raise the budget' : ', raise the budget, or use the GATOR baseline'}.</p>}
      {!loads && entry && <details><summary>Where the {encoder} values come from</summary>
        <p className="hint">{entry.summary}</p>
        <table className="grid small"><thead><tr><th>Setting</th><th>Preset</th><th>Basis</th><th>Source and note</th></tr></thead><tbody>
          {[...netFields, ...advFields].map(f => { const p = entry.provenance?.[f]; const ref = p?.source ? netSettings.references?.[p.source] : null; return (
            <tr key={f}><td>{f}</td><td className="numeric">{num(p?.value)}</td><td>{p?.basis}{p?.match === 'closest' ? ', closest network' : ''}</td>
              <td>{ref && <a href={ref.url} target="_blank" rel="noreferrer">{ref.short}</a>} {p?.note}</td></tr>); })}
        </tbody></table>
        <p className="hint">{netSettings.scale_note}</p></details>}
      <ModelChooser mode={run.mode} source={source} runs={runs} outputRoot={config.output?.output_root}
        onChoose={(run_dir, checkpoint_id) => set({ model_source: { ...source, run_dir, checkpoint_id } })} />
      {run.mode === 'scratch' && (!looking
        ? <div className="row"><button className="look-open" onClick={() => setLooking(true)} title="See the network structure and the circuit graph view of any saved model. Nothing about the run changes: Mode stays scratch.">Look at a saved model</button></div>
        : <>
          <ModelChooser lookOnly mode="look" source={look} runs={runs} outputRoot={config.output?.output_root}
            onChoose={(run_dir, checkpoint_id) => setLook({ run_dir, checkpoint_id })} />
          {look.run_dir && <ModelStructure runDir={look.run_dir} checkpointId={look.checkpoint_id} />}
          {look.run_dir && <CircuitGraphView runDir={look.run_dir} checkpointId={look.checkpoint_id} />}
          <div className="row"><button className="look-close" onClick={() => { setLooking(false); setLook({ run_dir: null, checkpoint_id: 'latest' }); }}>Done looking</button></div></>)}
      {loads && (<>
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
        {source.run_dir && <ModelStructure runDir={source.run_dir} checkpointId={model?.description?.checkpoint_id ?? null} label={model?.description?.source_task_id} />}
        {source.run_dir && <CircuitGraphView runDir={source.run_dir} checkpointId={model?.description?.checkpoint_id ?? null} label={model?.description?.source_task_id} />}
        {model?.compatibility_unchecked && <div className="note compat-unchecked"><p><b>{model.compatibility_unchecked.title}</b></p>
          <p>{model.compatibility_unchecked.what}</p><p className="hint">{model.compatibility_unchecked.note}</p>
          <details><summary>Technical details</summary><pre className="small">{model.compatibility_unchecked.technical}</pre></details></div>}
        {model?.compatibility && !archDiffers && <details open={!model.compatibility.compatible}><summary className={model.compatibility.compatible ? '' : 'error'}>Compatibility for {model.compatibility.mode}: {model.compatibility.compatible ? 'compatible' : 'NOT compatible - there is no fallback to scratch'}</summary>
          <ul>{model.compatibility.checks.map((c: Json) => <li key={c.component} className={`issue ${c.status === 'ok' ? 'info' : c.status === 'warning' ? 'warning' : 'error'}`}>{c.component}: {c.status} - {c.detail}</li>)}</ul></details>}
        {run.mode === 'frozen' && <label>Frozen actions<select value={run.frozen_action ?? 'deterministic'} onChange={e => set({ frozen_action: e.target.value })}><option>deterministic</option><option>sampled</option></select></label>}
        {run.mode === 'fine_tune' && <Check label="Continual learning (inherit weights fine-tuned on a previous test task)" value={run.continual_learning} onChange={v => set({ continual_learning: v })} />}
      </>)}
      <details><summary>Advanced (stored per encoder, like the network sizes)</summary>
        <p className="hint">Alpha learning rate belongs to this configuration; the other settings belong to the selected encoder. The algorithm stays soft actor-critic; only its numbers change.</p>
        <Num label="Alpha learning rate" nullable value={adv.alpha_learning_rate} onChange={v => setAdv({ alpha_learning_rate: v })} title="Empty uses the actor learning rate. A separate rate is stored in this configuration." />
        {ADVANCED_ROWS.map((fields, i) => {
          const inputs = fields.map(([name, label, title]) => <Num key={name} label={label} title={title}
            value={adv[name] ?? entry?.advanced?.[name] ?? schema.$defs.AdvancedRL.properties[name].default}
            onChange={v => editAdv({ [name]: v })} />);
          return i === 0 ? <Fragment key={i}>{inputs}</Fragment> : <div className="row" key={i}>{inputs}</div>;
        })}
        <Check label="Freeze encoder (fine_tune)" value={adv.freeze_encoder} onChange={v => setAdv({ freeze_encoder: v })} />
        <Check label="Encoder-only transfer (fine_tune)" value={adv.encoder_only_transfer} onChange={v => setAdv({ encoder_only_transfer: v })} />
        <Check label="Reset critic (fine_tune)" value={adv.reset_critic} onChange={v => setAdv({ reset_critic: v })} />
      </details>
      </>}
    </section>, networkWindow.root)}
    </>
  );
}

export function OutputPanel({ config, setConfig, meta, activeRun }: { config: Json; setConfig: (f: (c: Json) => Json) => void; meta: Json; activeRun: Json }) {
  const out = config.output;
  const llmOnly = config.run.search?.method === 'llm';
  const set = (fields: Json) => setConfig(c => ({ ...c, output: { ...c.output, ...fields } }));
  const root = out.output_root ?? meta?.output_root ?? '';
  const [browse, setBrowse] = useState<Json>(null);
  const locked = !!activeRun?.worker_alive;
  // The root is looked at 0.5 s after the last keystroke, and an answer for text typed before is dropped (useRequest): each
  // look walks the folder for its size, and whichever answer came last used to win, a half-typed path's too.
  const { value: looked, error: lookError, refresh: retryLook } = useRequest<Json>(signal => api.checkOutput(root, false, signal), [root], { enabled: !!root, delay: 500 });
  const [tested, setTested] = useState<{ root: string; value: Json } | null>(null);     // "Test writability", for the root it was pressed for
  useEffect(() => setTested(null), [root]);                                             // another root: its own look replaces it, as before
  const check: Json = tested && tested.root === root ? tested.value : looked;
  // Browse, a folder of its list and Test writability say what went wrong, as the other panels do (they used to say nothing).
  const [problem, setProblem] = useState<string | null>(null);
  // Only the newest press answers (two quick clicks in the folder list showed whichever came last), and a problem is
  // about the root it was pressed for: another root clears it.
  const pressed = useRef(0);
  const ask = <T,>(work: () => Promise<T>, done: (value: T) => void) => { const mine = ++pressed.current; setProblem(null);
    work().then(v => { if (mine === pressed.current) done(v); }, e => { if (mine === pressed.current) setProblem(e.message); }); };
  useEffect(() => { pressed.current++; setProblem(null); }, [root]);
  const paths = activeRun?.paths;
  const tail = String(root).split(/[\\/]/).filter(Boolean).slice(-2).join('/');
  // ONE checkpoint interval, counted in evaluations OR in seconds (user request 2026-09-22). The number goes into the field
  // of the chosen unit and the other field is emptied - also the default of 50 evaluations that an absent field means. The
  // backend refuses both at once (validation.py, checkpoint_interval_both). Another unit carries the number over:
  // evaluations and seconds do not convert into each other.
  const every: Json = out.checkpoint_every_evaluations === undefined ? 50 : out.checkpoint_every_evaluations;
  const seconds: Json = out.checkpoint_every_seconds ?? null;
  const [by, setBy] = useState<Every>(() => seconds !== null && every === null ? 'seconds' : 'evaluations');
  useEffect(() => { if (seconds !== null && every === null) setBy('seconds'); else if (every !== null && seconds === null) setBy('evaluations'); }, [every, seconds]);
  const interval: Json = by === 'seconds' ? seconds : every;
  const setEvery = (unit: Every, v: Json) => set({ checkpoint_every_evaluations: unit === 'evaluations' ? v : null, checkpoint_every_seconds: unit === 'seconds' ? v : null });
  const both = every !== null && seconds !== null;          // only from a file or an older copy of the configuration
  return (
    <Module id="output" title="Output settings" summary={[out.experiment_name, tail ? `.../${tail}` : 'no output root'].filter(Boolean).join(' - ')}>
      {/* "Copy path" is a sibling of the label, not inside it: a button inside would become what the label's text clicks. */}
      <div className="field-head"><label htmlFor="output-root" title="A backend directory inside an allowed root. Not a browser upload folder.">Output root</label>
        <button className="text-link" title="Copy the output root to the clipboard" onClick={() => copy(root)}>Copy path</button></div>
      <input id="output-root" value={root} disabled={locked} onChange={e => set({ output_root: e.target.value })} />
      <div className="row"><button disabled={locked} onClick={() => ask(() => api.browse(), setBrowse)}>Browse allowed roots...</button>
        <button onClick={() => { const at = root; if (at) ask(() => api.checkOutput(at, true), value => setTested({ root: at, value })); }}>Test writability</button></div>
      {problem && <p className="error">{problem}</p>}
      {!tested && lookError && <p className="error">{lookError} <button onClick={retryLook}>Retry read</button></p>}
      {locked && <p className="hint">The run directory is locked while a run is active. A resumed run writes back to its original directory.</p>}
      {browse && <ul className="tree">{browse.parent && <li onClick={() => ask(() => api.browse(browse.parent), setBrowse)}>..</li>}
        {browse.entries.map((e: Json) => <li key={e.path}><span onClick={() => ask(() => api.browse(e.path), setBrowse)}>{e.name}</span> <button onClick={() => { set({ output_root: e.path }); setBrowse(null); }}>select</button></li>)}</ul>}
      {check && <table className="grid small"><tbody>
        <tr><td>Resolved</td><td className="path">{check.resolved ?? '-'}</td></tr>
        <tr><td>Allowed / writable</td><td className={check.allowed && check.writable ? '' : 'error'}>{String(check.allowed)} / {String(check.writable)} {check.error ?? ''}</td></tr>
        <tr><td>Backend host</td><td>{check.host} ({check.environment}, {check.filesystem})</td></tr>
        <tr><td>Free space</td><td>{bytes(check.free_bytes)}; used here {bytes(check.bytes_used)}</td></tr>
        <tr><td>Windows path</td><td>{check.windows_path ?? <span className="hint">not shown: {check.windows_mapping}</span>}{check.windows_path && <span className="hint"> (verified by read-back)</span>}</td></tr>
        <tr><td>Mock data root</td><td className="path">{check.mock_data_root}</td></tr>
      </tbody></table>}
      <div className="row"><label>Experiment name<input value={out.experiment_name ?? ''} onChange={e => set({ experiment_name: e.target.value })} /></label>
        <label title="Set to append runs to an existing experiment; empty creates a new unique ID.">Experiment ID<input value={out.experiment_id ?? ''} placeholder="new" onChange={e => set({ experiment_id: e.target.value || null })} /></label></div>
      {paths && <details open><summary>Current run paths</summary><table className="grid small"><tbody>
        {Object.entries(paths).map(([k, v]) => <tr key={k}><td>{k}</td><td className="path" onClick={() => copy(String(v))}>{String(v)}</td></tr>)}
        <tr><td>bytes written</td><td>{bytes(activeRun?.bytes_written ?? activeRun?.persistence?.bytes_written)}</td></tr>
        <tr><td>last successful save</td><td>{activeRun?.persistence?.last_successful_save ?? '-'}</td></tr>
        <tr><td>remote Spectre work dir</td><td className="hint">local work/ for this task; final files are written directly here (sync: local)</td></tr>
      </tbody></table></details>}
      <h4>Always saved</h4><p className="hint">Configuration/provenance snapshots, per-evaluation records, actual parameters, metrics, simulator-job accounting, run summary, event/error logs (Parquet + JSON).</p>
      {!llmOnly && <Check label="Learner-update log" value={out.save_learner_updates ?? true} onChange={v => set({ save_learner_updates: v })} />}
      <Check label={llmOnly ? 'Search progress (needed to resume)' : 'Model checkpoints'} value={out.save_checkpoints ?? true} onChange={v => set({ save_checkpoints: v })} />
      {!llmOnly && <Check label="Replay snapshots (needed for a FULL resume)" value={out.save_replay_snapshots ?? true} onChange={v => set({ save_replay_snapshots: v })} />}
      {!llmOnly && out.save_replay_snapshots === false && <p className="warn">Without replay snapshots checkpoints are weights_only: a full training-state resume of this run will NOT be possible.</p>}
      <Check label="Complete transition archive (independent of replay snapshots)" value={out.save_transition_archive ?? true} onChange={v => set({ save_transition_archive: v })} />
      <Check label="Experiment summary CSVs" value={out.export_summary_csv ?? true} onChange={v => set({ export_summary_csv: v })} />
      <Num label="Checkpoint every" nullable value={interval} placeholder="only at pause, stop, end" onChange={v => setEvery(by, v)}
        title="The model and its training state are saved every N evaluations or every S seconds - one of the two. Empty = only when the run pauses, stops or ends."
        after={<select aria-label="Checkpoint every: unit" value={by} onChange={e => { const unit = e.target.value as Every; setBy(unit);
          const carried = (unit === 'seconds' ? seconds : every) ?? interval; if (carried !== null) setEvery(unit, carried); }}>
          <option>evaluations</option><option>seconds</option></select>} />
      {both && <p className="warn">This configuration has both: every {every} evaluations and every {seconds} seconds. Only one can be kept - type a number or choose the unit, and the other is emptied.</p>}
      <label title="Raw PSF only; nothing is rendered. Applies to raw outputs that actually exist.">Raw waveform retention
        <select value={out.waveform_retention ?? 'best_and_failures'} onChange={e => set({ waveform_retention: e.target.value })}><option>none</option><option>best_and_failures</option><option>all</option></select></label>
      {/* null is a real setting here (no limit); only a configuration without the field shows the backend's default. */}
      <ByteSize label="Waveform storage limit" empty="no limit" value={out.waveform_storage_limit_bytes === undefined ? 2147483648 : out.waveform_storage_limit_bytes}
        onChange={v => set({ waveform_storage_limit_bytes: v })}
        title="Oldest retained failures are removed first. The best design, models and primary data are never deleted automatically." />
    </Module>
  );
}

export function ResearchPanel({ config, setConfig }: { config: Json; setConfig: (f: (c: Json) => Json) => void }) {
  const r = config.research ?? {};
  const set = (fields: Json) => setConfig(c => ({ ...c, research: { ...(c.research ?? {}), ...fields } }));
  const list = (v: string) => v.split(',').map(s => s.trim()).filter(Boolean);
  // A list is typed as text with commas. The box keeps "a," while the list is ['a']: it used to swallow every comma.
  const listBox = (field: string, numbers = false) => <Typed value={r[field] ?? []} format={v => (v ?? []).join(', ')}
    parse={t => ({ value: numbers ? list(t).map(Number).filter(Number.isFinite) : list(t) })} onChange={v => set({ [field]: v })} />;
  return (
    // The heading in the modules' heading style, its note on hover (record 7.166, user: "Modify the font difference and make the
    // comment appear when mouse is over the module name"). It stays a closed fold of its own, not a Module.
    <details className="panel research-module"><summary><h3 title={'Optional for a single run; missing labels stay "unspecified".'}>Research experiments</h3></summary>
      {/* Record 7.163 (user, 2026-10-03, on "which should be kept"): Experiment group and Test tasks went - nothing read them;
          the labels only a transfer study uses are folded below; what every comparison table uses stays in view. */}
      <label title="Names the method in every research table (Data tables > Export research CSVs): run summary, success per budget, paired runs, transfer summary, cumulative cost.">Method label
        <input value={r.method_label ?? 'unspecified'} onChange={e => set({ method_label: e.target.value })} placeholder="Scratch | Pretrained-Frozen | Pretrained-Fine-tuned | encoder-only transfer" /></label>
      <label title="Associates runs with the same target, initial dimensions, budget, test setup and target seed.">Comparison pair ID<input value={r.comparison_pair_id ?? 'unspecified'} onChange={e => set({ comparison_pair_id: e.target.value })} /></label>
      <label title="Evaluation budgets at which success is counted (success per budget). Empty: the run's own budget.">Budget checkpoints{listBox('budget_checkpoints', true)}</label>
      <details className="more transfer-study"><summary>Transfer study</summary>
        <p className="hint">Labels for a study that trains on some circuits and tests on others; a single run needs none of them.</p>
        <label>Split<select value={r.split ?? 'unspecified'} onChange={e => set({ split: e.target.value })}>{['unspecified', 'train', 'validation', 'test'].map(s => <option key={s}>{s}</option>)}</select></label>
        <label>Generalization level<select value={r.generalization_level ?? 'unspecified'} onChange={e => set({ generalization_level: e.target.value })}>
          {['unspecified', 'same_task', 'unseen_spec', 'unseen_topology', 'unseen_circuit_class'].map(s => <option key={s}>{s}</option>)}</select></label>
        <label>Training sources{listBox('training_sources')}</label>
        <div className="row"><Num label="Task order K" nullable value={r.task_order} onChange={v => set({ task_order: v })} /><Num label="Pretrain seed (source)" nullable value={r.pretrain_seed} onChange={v => set({ pretrain_seed: v })} /></div>
        <label>Ablation labels{listBox('ablation_labels')}</label>
      </details>
    </details>
  );
}
