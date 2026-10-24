// The RL model's words (plan-refactoring C4, out of Right.tsx): the Modes, the encoders' settings and the reward fields as
// the panel names them, and the lines it writes about the next run's model - pure functions of the configuration.
import type { Json } from '../api';
import { count, durationWhole, plural } from '../format';
import { designName, designShort } from '../lineage';

// Settings stored per encoder in the backend (src/gator_workbench/network_presets.py). The lists are
// only a fallback for the moment before the backend answers; the backend's own lists are used afterwards.
type NumberField = readonly [name: string, label: string, title?: string];
export const ADVANCED_ROWS: NumberField[][] = [
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

/** The transferable network inputs of record 7.298, set together by the RL model window's one "Network inputs" choice:
 *  the specs read as a set (any names, any number), sizes relative to the PDK and its device model numbers. */
/** The second build (record 7.317): the testbench's sources on their own scales, net tags by one rule, and the
 *  operating-point ratios of each simulated design. Each choice sets all six settings, so a change of choice leaves none behind. */
const FIRST_BUILD_ONLY = { bench_features: 'absolute', net_roles: 'task', operating_point_ratios: false };
export const TRANSFERABLE = { spec_input: 'set', size_features: 'pdk_relative', device_model_features: true, ...FIRST_BUILD_ONLY };
export const TRANSFERABLE_2 = { spec_input: 'set', size_features: 'pdk_relative', device_model_features: true,
  bench_features: 'relative', net_roles: 'rule', operating_point_ratios: true };
export const STANDARD_INPUTS = { spec_input: 'slots', size_features: 'absolute', device_model_features: false, ...FIRST_BUILD_ONLY };
export const INPUT_CHOICES: Record<string, Json> = { standard: STANDARD_INPUTS, transferable: TRANSFERABLE, transferable2: TRANSFERABLE_2,
  structured: { ...STANDARD_INPUTS, spec_input: 'structured' },
  structured_transferable: { ...TRANSFERABLE_2, spec_input: 'structured' } };
export const INPUT_NAMES: Record<string, string> = { standard: 'Standard', transferable: 'Transferable', transferable2: 'Transferable 2',
  structured: 'Structured', structured_transferable: 'Structured + Transferable 2', custom: 'Custom (set in the configuration file)' };
/** The inputs a NEW model is made with, by its encoder (record 7.332; user: "Yes, no box"): Transferable 2 - the build the
 *  transfer experiment's step 3b accepted - and for CircuitGPS the same with its structured specs. New model and a template
 *  bring them (useRlModel), and the RL model window then shows one line of text where the box was; another choice shows
 *  in a box only while a configuration still holds it. */
export const newModelChoice = (encoder: string): 'transferable2' | 'structured_transferable' =>
  encoder === 'circuit_gps' ? 'structured_transferable' : 'transferable2';
export const newModelInputs = (encoder: string): Json => INPUT_CHOICES[newModelChoice(encoder)];
/** Whether a template may replace these inputs by its encoder's own: they are the standard ones (never chosen) or the
 *  set another template brought. A choice a configuration holds on purpose - the first build, plain Structured on
 *  CircuitGPS, a custom set - stays. */
export const takesTemplateInputs = (net: Json, encoder: string) => {
  const held = inputsChoice(net);
  return held === 'standard' || held === 'transferable2' || held === 'structured_transferable' || (held === 'structured' && encoder !== 'circuit_gps');
};
export const TRANSFER_TITLE = 'Standard: the specs in the fixed places of the result registry, sizes in micrometres - every model saved before '
  + '2026-10-10. Transferable: every spec described by what it measures and read as a set (any names, any number), transistor sizes '
  + "relative to the PDK's minimum, and four technology numbers of each transistor's model; a model trained so loads on any task and "
  + 'any PDK with the same inputs. Transferable 2 adds: the bench\'s current sources in microamperes and its voltage sources as a share '
  + 'of the supply, net tags by one rule (ground, supply, input, output, bias), and four ratios of each transistor at the simulated '
  + 'operating point (gm/Id, gm/gds, overdrive, Vds/Vdsat) - the run then reads every design\'s operating point. '
  + 'Needs the task\'s PDK loaded. Structured inputs preserve measurement operations, constants, circuit bindings and reward scales '
  + 'for CircuitGPS. Structured + Transferable 2 combines both. Changing this changes the model input schema.';
/** Which of the named choices a network block is; "custom" when its settings were set apart in a configuration file. */
export function inputsChoice(net: Json): 'standard' | 'transferable' | 'transferable2' | 'structured' | 'structured_transferable' | 'custom' {
  const values = [net?.spec_input ?? 'slots', net?.size_features ?? 'absolute', !!net?.device_model_features];
  const second = [net?.bench_features ?? 'absolute', net?.net_roles ?? 'task', !!net?.operating_point_ratios];
  const none = second[0] === 'absolute' && second[1] === 'task' && !second[2];
  const all = second[0] === 'relative' && second[1] === 'rule' && second[2];
  if (values[0] === 'structured') {
    if (values[1] === 'absolute' && !values[2] && none) return 'structured';
    return values[1] === 'pdk_relative' && values[2] && all ? 'structured_transferable' : 'custom';
  }
  if (values[0] === 'slots' && values[1] === 'absolute' && !values[2]) return none ? 'standard' : 'custom';
  if (!(values[0] === 'set' && values[1] === 'pdk_relative' && values[2])) return 'custom';
  return none ? 'transferable' : all ? 'transferable2' : 'custom';
}
/** A saved model's network inputs in words (the RL model window's model facts): the choice by the name New model's line and
 *  box give it, then what it reads (branch record SIF-80: "transferable: specs read as a set, ..." began with a lower-case
 *  key and a colon, a second label inside the cell). A set no choice makes is "Custom". */
export function inputsText(net: Json): string {
  if (!net) return 'unknown';
  const parts = [net.spec_input === 'structured' ? 'measurement programs and circuit bindings' : net.spec_input === 'set' ? 'specs read as a set' : null, net.size_features === 'pdk_relative' ? 'sizes relative to the PDK' : null,
    net.device_model_features ? 'device model features' : null, net.bench_features === 'relative' ? 'bench sources on their own scales' : null,
    net.net_roles === 'rule' ? 'net tags by rule' : null, net.operating_point_ratios ? 'operating-point ratios' : null].filter(Boolean);
  const choice = inputsChoice(net);
  return parts.length ? `${choice === 'custom' ? 'Custom' : INPUT_NAMES[choice]} - ${parts.join(', ')}` : INPUT_NAMES.standard;
}

export const NETWORK_SETTING_LABELS: Record<string, string> = {
  hidden_dim: 'Hidden width', heads: 'Heads', layers: 'Layers', structural_encoding: 'Structural encoding',
  ...Object.fromEntries(ADVANCED_ROWS.flat().map(([name, label]) => [name, label])),
};

/** The five reward settings a new configuration fixes (store.ts SIMPLE_REWARD), as the reward block names them, and the
 *  nominal gate band, the sixth a saved model's reward holds (branch record SIF-103). */
export const REWARD_NAMES: Record<string, string> = { violation_shape: 'violation shape', worst_spec_share: 'worst hard-spec share',
  objective_weight: 'objective bonus weight', objective_shape: 'objective shape', margin_weight: 'tightest-margin bonus weight',
  nominal_gate_band: 'nominal gate band' };
/** What a run takes for a reward field its configuration leaves out: the backend's RewardConfig defaults. The six keys are
 *  the whole reward a saved model's contract holds (RewardSettings), and Fine-tune compares all six (branch record SIF-103). */
export const REWARD_DEFAULTS: Json = { violation_shape: 'capped', worst_spec_share: 0, objective_weight: 0, objective_shape: 'clipped', margin_weight: 0,
  nominal_gate_band: 0.5 };
/** What they do: the reward block's tooltips, and the same rows of a saved model's facts (branch record SIF-80: the facts had
 *  none; SIF-103: the objective shape and the gate band, which the facts did not show). */
export const REWARD_HELP: Record<string, string> = {
  worst_spec_share: '0 to 1. Mix the weighted mean violation with the worst hard-spec violation. At 1, soft violations do not contribute to the penalty.',
  objective_weight: '0 to 1. Applies only to a complete hard-feasible plan and the single objective selected in Specs. Without an objective row the bonus is 0.',
  margin_weight: 'Complete hard-feasible plans only. Equality constraints remain mandatory but do not contribute clearance.',
  objective_shape: 'Clipped stops the objective bonus at one scale; compressed keeps rewarding improvement below 1.',
  nominal_gate_band: 'Strictly between 0 and 1. Gate-passing designs always rank above gate-failing designs.' };
/** A reward version by name: a saved model's (SIF-41) and a run's executed reward in Run status (SIF-54). */
export const REWARD_NAME: Record<string, string> = { constraint_violation_v2: 'Constraint violation, version 2' };

/** The Mode, in the RL model window (record 7.265; plan "RL model window": "Mode selection should be merged in to load model.
 *  Scratch mode will ask you to create a new model from the default templates. fine-tune and evaluate load existing ones").
 *  `resume` is no choice: a run is continued from Runs or Run status (Continue..., record 7.261). */
export const MODES: [string, string, string][] = [
  ['scratch', 'New model', 'a new RL model, made from one of the templates below; it starts from random weights'],
  ['fine_tune', 'Fine-tune', 'a saved model keeps learning, in a new run'],
  ['frozen', 'Evaluate only', 'a saved model is used as it is, with no learning'],
];
export const MODE_NAME: Record<string, string> = { scratch: 'New model', fine_tune: 'Fine-tune', frozen: 'Evaluate only', resume: 'no Mode chosen' };
/** What a run was, in the RL model window's words (branch record SIF-11): New model, Fine-tune, Evaluate only - a baseline
 *  simulation, a calibration and an offline training by their own names (a baseline's mode is "scratch", which read as a new
 *  model) - and, for a run that trains or evaluates a model, its design ("GraphGPS"; a run does not say CircuitGPS's version). */
export const runMode = (r: Json) => r.run_kind === 'baseline_preflight' ? 'Baseline' : r.run_kind === 'calibration' ? 'Calibration'
  : r.run_kind === 'offline_pretraining' ? 'Offline training' : r.mode === 'resume' ? 'Resume' : MODE_NAME[r.mode] ?? r.mode ?? '';
export const runDesign = (r: Json) => (['baseline_preflight', 'calibration'].includes(r.run_kind) || !r.encoder ? ''
  : designName({ encoder_type: r.encoder, architecture_version: r.network?.architecture_version }));
// Where an encoder's settings come from. The backend still calls it `publication`; since record 7.192 it is the network size
// from publications with every training value of the runs that learned on GATOR circuits (user: "keep this as the starting
// preset").
export const ORIGIN: Record<string, string> = { publication: 'starting preset', custom: 'edited, saved in the backend' };

/** What Start would start, as far as Run configuration knows it (record 7.269): the Mode with its model and save point, and the
 *  network in short. The page adds the task and the budget for the header's "Next" line. */
export type NextModel = { model: string; network: string };

/** The network in use, in sizes as the run takes them (user, 2026-10-03: "show the current network selection next to the RL
 *  network button in short"): the configuration's, else the encoder's saved setting, else the defaults; a component list that
 *  is not the standard one by its PDK. In a Mode that loads a model the configuration's network is that model's. */
export function networkSizes(net: Json, entry: Json) {
  const hidden = net.hidden_dim ?? entry?.network?.hidden_dim ?? 32, heads = net.heads ?? entry?.network?.heads ?? 4, layers = net.layers ?? entry?.network?.layers ?? 2;
  const components = net.vocabulary && net.vocabulary !== 'standard' ? net.vocabulary.replace(/^pdk:/, '') : null;
  return { hidden, heads, layers, components };
}
export type NetworkSizes = ReturnType<typeof networkSizes>;
/** The network in short, beside the RL model button. */
export const networkShort = (encoder: string, { hidden, heads, layers, components }: NetworkSizes, usesHeads: boolean, net: Json) =>
  [`${designShort({ encoder_type: encoder, architecture_version: net.architecture_version })} ${hidden}/${usesHeads ? heads : '–'}/${layers}`, net.operating_points ? 'op. points' : null,
      inputsChoice(net) === 'transferable2' ? 'transferable 2' : inputsChoice(net) !== 'standard' ? 'transferable' : null, components === 'families' ? 'families' : components ? `${components} parts` : null].filter(Boolean).join(' · ');
/** Fine-tune's own switches, in the RL model window's order: the key, whether `run` (else `run.advanced`) keeps it, the
 *  window's label and the Next line's word (branch record SIF-103). Only that window said them, and it closes once a save
 *  point is chosen; kept across Modes and runs and copied by New run like this, a switch left on went unseen before Start. */
const FINE_TUNE_SWITCHES: [key: string, inRun: boolean, label: string, word: string][] = [
  ['freeze_encoder', false, 'Freeze encoder', 'encoder frozen'], ['encoder_only_transfer', false, 'Encoder-only transfer', 'encoders only'],
  ['reset_critic', false, 'Reset critic', 'critics reset'], ['continual_learning', true, 'Continual learning', 'continual']];
/** The switches that are on, in a Mode whose run takes them: Fine-tune all four, Evaluate only Continual learning - there too
 *  it decides whether a source itself fine-tuned on a test task loads or is refused (runs.py `_source_model`; review of
 *  branch record SIF-103: "the backend reads them in no other Mode" was wrong for it). In another Mode the other three
 *  refuse the start, a blocking issue that names them (validation.py `fine_tune_only_option`). */
const switchesOn = (run: Json, adv: Json) => FINE_TUNE_SWITCHES.filter(([key, inRun]) =>
  (run.mode === 'fine_tune' || (run.mode === 'frozen' && key === 'continual_learning')) && !!(inRun ? run : adv)?.[key]);
/** Them on the Next line: nothing while all are off, so it reads as before. */
const switchWords = (run: Json, adv: Json) => switchesOn(run, adv).map(([, , , word]) => ` · ${word}`).join('');
/** Them on a line of their own under the model line, by the window's labels; null while all are off (review of branch record
 *  SIF-103: said at the end of the model line, which is cut at two lines, they were hidden - a saved model's name and its
 *  save point fill those two lines at 1366 and at 1680 px). */
export const switchesText = (run: Json, adv: Json) => {
  const on = switchesOn(run, adv);
  return on.length ? `Switches on: ${on.map(([, , label]) => label).join(', ')}.` : null;
};
/** The next run's model in one line, beside the button (record 7.265; plan "RL model window": "New model · Graph Transformer
 *  template · GT 48/4/4", "Fine-tune ota7t (2) · save point 420 evaluations", "Evaluate ... · deterministic actions"). The
 *  switches that are on have a line of their own (`switchesText`). */
export const modelLineText = ({ run, noMode, source, entry, encoder, netShort, sourceName, pointAt }: { run: Json; noMode: boolean; source: Json;
  entry: Json; encoder: string; netShort: string; sourceName: string | null; pointAt: Json }) =>
  run.mode === 'scratch' ? `New model · ${entry?.label ?? encoder} template · ${netShort}`
    : noMode ? 'No Mode chosen: choose one in RL model... (this configuration still says resume)'
    : !source.run_dir ? `${MODE_NAME[run.mode] ?? run.mode} · no saved model chosen`
    : `${run.mode === 'frozen' ? 'Evaluate' : 'Fine-tune'} ${sourceName} · save point ${pointAt != null ? `${count(pointAt)} evaluations` : source.checkpoint_id}`
      + (run.mode === 'frozen' ? ` · ${run.frozen_action ?? 'deterministic'} actions` : '');   // the count as the model's facts write it (branch record SIF-117)
/** The same, as the header's "Next" line names it (record 7.269; plan "The draft": "Next: ota7t · Fine-tune from ota7t (2)
 *  @ 420 · GT 48/4/4 · 800 evaluations"), with the switches that are on (branch record SIF-103). That line too is cut at two
 *  lines, and seldom shows them; its tooltip and Start's, which begins with it, say them whole. */
export const nextModelText = ({ run, adv, noMode, source, sourceName, pointAt }: { run: Json; adv: Json; noMode: boolean; source: Json; sourceName: string | null; pointAt: Json }) =>
  run.mode === 'scratch' ? 'New model'                 // the network beside it names the template's encoder
    : noMode ? 'no Mode chosen'
    : !source.run_dir ? `${MODE_NAME[run.mode] ?? run.mode} - no saved model chosen`
    : `${run.mode === 'frozen' ? 'Evaluate' : 'Fine-tune from'} ${sourceName} @ ${pointAt != null ? count(pointAt) : source.checkpoint_id}${run.mode === 'frozen' ? ` (${run.frozen_action ?? 'deterministic'} actions)` : ''}${switchWords(run, adv)}`;
/** That line's tooltip: the network in words, or what a Mode that loads a model still needs. The design by name (branch
 *  record SIF-57: it began "The network in use: graph_transformer"). In Fine-tune also the name typed for the model it saves
 *  (branch record SIF-103). */
export const networkTitle = ({ loads, source, run, encoder, hidden, heads, layers, components, usesHeads, net }: { loads: boolean; source: Json; run: Json;
  encoder: string; usesHeads: boolean; net: Json } & NetworkSizes) => {
  if (loads && !source.run_dir) return `${MODE_NAME[run.mode] ?? run.mode} loads a saved model: choose one in RL model...; the run then uses its network.`;
  const saves = run.mode === 'fine_tune' ? (run.model_label ?? '').trim() : '';
  return `The network in use: ${designName({ encoder_type: encoder, architecture_version: net.architecture_version })}, hidden ${hidden}, ${usesHeads ? `heads ${heads}` : 'no attention heads'}, layers ${layers}; nominal operating points ${net.operating_points ? 'on' : 'off'}; `
    + `inputs ${inputsText(net)}; `
    + `components ${components ?? 'standard'}${loads ? `. It is the network of the saved model this run loads (${source.run_dir}, save point ${source.checkpoint_id}).` : '.'} RL model... changes it.`
    + (saves ? ` It saves the model as ${saves}, with a number if that name is taken.` : '');
};
/** The limits a run seldom changes that are set, for the line of the Limits fold: "42 launches, 1 retry, wall time 24 h 00
 *  min" (branch record SIF-58: "1 launches, 1 retries, 86400 s"). */
export const limitsText = (run: Json) =>
  [run.max_spectre_launches != null ? plural(run.max_spectre_launches, 'launch', 'launches') : null,
    (run.max_retries ?? 0) > 0 ? plural(run.max_retries, 'retry', 'retries') : null,
    run.max_wall_seconds != null ? `wall time ${durationWhole(run.max_wall_seconds) ?? `${run.max_wall_seconds} s`}` : null].filter(Boolean) as string[];
/** Run configuration folded into one line: the Mode, the model label, the budget and the network. */
export const foldedText = (run: Json, budget: number, encoder: string, net: Json) =>
  [MODE_NAME[run.mode] ?? run.mode, run.model_label?.trim() ? `model ${run.model_label.trim()}` : null, typeof budget === 'number' ? `${count(budget)} evaluations` : null,
    `${designName({ encoder_type: encoder, architecture_version: net.architecture_version })} ${net.hidden_dim ?? '?'}/${net.heads ?? '?'}/${net.layers ?? '?'}`,   // the design by name (SIF-12)
    net.vocabulary === 'families' ? 'device families' : net.vocabulary && net.vocabulary !== 'standard' ? `knows ${net.vocabulary.slice(4)}` : null].filter(Boolean).join(' - ');
