/** trainingData.ts, part 4 (plan-refactoring C12): what a chart is, and the charts a run offers. */
import { categoryOf } from './store.ts';
import type { Category, Context, TrainingStore } from './store.ts';
import { designCodes, EVALUATION, prep } from './prep.ts';

// ---------------------------------------------------------------------------------------------------------------- charts
export type Axis = 'evaluation' | 'update';
export interface ChartSpec {
  id: string; title: string; unit: string; axis: Axis;
  group: 'Results' | 'Specs' | 'Learner (SAC)' | 'Not recorded';
  available: boolean; reason: string | null;    // why this run cannot draw it
  source: string;                               // the recorded column(s), by the data dictionary's names
  about: string;                                // what it is, in one sentence
}
export interface Series { label: string; role: 'raw' | 'smooth' | 'line' | 'limit' | 'superseded'; category: Category | null; values: (number | null | undefined)[]; step?: boolean;
  run?: number;            // compared runs (record 7.200): the run's place in the comparison, which picks its colour
  dash?: boolean }         // the second of two columns of one run (gradient norms: the policy's)
export interface Marker { x: number; label: string; kind: 'resume' | 'restart' }
export interface Built { axis: Axis; x: number[]; rows: number[]; series: Series[]; markers: Marker[]; thinnedTo: number | null; extent: [number, number] | null;
  range: [number, number] | null; unit: string;
  missing?: { label: string; reason: string }[] }     // compared runs that cannot be drawn on this chart, and why

const EVALUATION_TEXT = 'No evaluation is recorded yet.';

/** The pass flag of each evaluation: 1 = every hard spec met (all_hard_constraints_satisfied), 0 = not, NaN = no verdict on the
 *  design (DESIGN_STATUSES). */
export function passFlags(store: TrainingStore): Float64Array {
  const t = store.evaluations, out = new Float64Array(t.n).fill(NaN);
  const design = designCodes(store);
  for (let i = 0; i < t.n; i++) if (design.has(t.cols.status[i]) && !Number.isNaN(t.cols.feasible[i])) out[i] = t.cols.feasible[i];
  return out;
}

export function rowCategories(store: TrainingStore): Category[] {
  const t = store.evaluations, phases = store.words.phase.list;
  return Array.from({ length: t.n }, (_, i) => categoryOf(phases[t.cols.phase[i]]));
}

const LEARNER: [string, string, string, string, string][] = [   // id, title, unit, source, about
  ['actor_loss', 'Actor loss', '', 'learner_updates.actor_loss', 'The policy\'s loss at each learner update.'],
  ['critic_loss', 'Critic loss', '', 'learner_updates.critic_loss', 'The twin critics\' loss at each learner update.'],
  ['alpha', 'Temperature α', '', 'learner_updates.alpha', 'The entropy coefficient: how much the learner is paid to keep exploring.'],
  ['entropy', 'Entropy estimate', 'nats', 'learner_updates.mean_log_prob', 'The policy\'s entropy estimate, −mean_log_prob (the data dictionary\'s definition): high = actions spread out, low = the policy has settled.'],
  ['alpha_loss', 'Temperature loss', '', 'learner_updates.alpha_loss', 'The loss that adjusts α towards the target entropy.'],
  ['target_mean', 'Mean TD target', '', 'learner_updates.target_mean', 'The mean temporal-difference target of the batch the critics learned from.'],
  ['grad_norm', 'Gradient norms before clipping', '', 'learner_updates.critic_grad_norm, actor_grad_norm', 'How hard each update pushed the critics and the policy (the clip is the "max grad norm" setting).'],
];
export const LEARNER_COLUMNS: Record<string, [string, string][]> = {      // chart id -> [table column, series label]
  actor_loss: [['actorLoss', 'Actor loss']], critic_loss: [['criticLoss', 'Critic loss']], alpha: [['alpha', 'α']],
  entropy: [['logp', 'Entropy estimate']], alpha_loss: [['alphaLoss', 'Temperature loss']], target_mean: [['target', 'Mean TD target']],
  grad_norm: [['gradCritic', 'Critics'], ['gradActor', 'Policy']],
};

/** Every chart the tab offers for this run, the ones it cannot draw with the reason. */
export function catalog(store: TrainingStore, context: Context = {}): ChartSpec[] {
  const e = store.evaluations, u = store.updates, p = prep(store).evaluations();
  const empty = e.n === 0 ? EVALUATION_TEXT : null;
  const charts: ChartSpec[] = [];
  const evaluated = p.counts[EVALUATION] > 0;
  charts.push({ id: 'reward', title: 'Step reward', unit: '', axis: 'evaluation', group: 'Results', source: 'evaluations.reward',
    about: 'The learning reward of each evaluation (one environment step); 0 is the best a design can score before the bonuses. The run records no episode return.',
    available: p.any('reward'), reason: empty ?? 'No evaluation has a reward yet: a reset or a failed evaluation has none.' });
  charts.push({ id: 'pass', title: 'Meets every hard spec', unit: 'share', axis: 'evaluation', group: 'Results',
    source: 'evaluations.all_hard_constraints_satisfied, status',
    about: 'Each design: 1 = every hard spec met, 0 = not; the smoothed line is the share of the last designs that did. A timeout, a lost link or an interrupted evaluation is no verdict on the design: a gap.',
    available: p.first('judged', e, [e.changes], row => !Number.isNaN(p.pass[row])) >= 0, reason: empty ?? 'No evaluation has a verdict on its design yet.' });
  charts.push({ id: 'eval_pass', title: 'Evaluation success rate', unit: 'share', axis: 'evaluation', group: evaluated ? 'Results' : 'Not recorded',
    source: 'evaluations.all_hard_constraints_satisfied (phase frozen_eval or validation)',
    about: 'Designs of a policy evaluated without training (a frozen run): the share of them so far that met every hard spec.',
    available: evaluated && p.first('evaluated and judged', e, [e.changes], row => p.cat[row] === EVALUATION && !Number.isNaN(p.pass[row])) >= 0,
    reason: evaluated ? 'No evaluated design has a verdict yet.' : 'This run evaluated no policy apart from training: only a frozen run does. For training designs see "Meets every hard spec".' });
  charts.push({ id: 'episode_return', title: 'Episode return', unit: '', axis: 'evaluation', group: 'Not recorded', source: '-',
    about: 'The sum of an episode\'s rewards.', available: false,
    reason: 'Not recorded: the run records the reward of each evaluation, not of whole episodes. See "Step reward".' });
  charts.push({ id: 'violation', title: 'Worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.normalized_constraint_violation',
    about: 'How far each design misses its worst hard spec, divided by that spec\'s scale; 0 = every hard spec met.',
    available: p.any('violation'), reason: empty ?? 'No valid design yet: a failed evaluation has no value.' });
  charts.push({ id: 'margin', title: 'Tightest margin', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.clearance_margin',
    about: 'The signed margin of the binding hard spec: above 0 = met with room to spare, below 0 = missed.',
    available: p.any('margin'), reason: empty ?? 'This run records no margin (an older run, or no valid design yet).' });
  charts.push({ id: 'best', title: 'Best design so far: worst spec miss', unit: 'normalized', axis: 'evaluation', group: 'Results', source: 'evaluations.best_so_far_violation',
    about: 'The worst-spec miss of the design the run keeps as its best at each evaluation; it reaches 0 at the first design that meets every hard spec.',
    available: p.any('bestViolation'), reason: empty ?? 'No valid design yet.' });
  const objective = store.objective, objectiveUnit = objective ? store.specDefs[objective.metric]?.unit ?? '' : '';
  charts.push({ id: 'objective', title: objective ? `Best feasible ${objective.metric} (${objective.direction === 'min' ? 'lower' : 'higher'} is better)` : 'Best feasible objective',
    unit: objectiveUnit, axis: 'evaluation', group: objective ? 'Results' : 'Not recorded', source: 'evaluations.best_so_far_metrics, best_so_far_feasible',
    about: 'The objective\'s value of the best design that meets every hard spec, as the run keeps it (feasible first, then the objective).',
    available: !!objective && p.first('feasible objective', e, [e.changes], row => !Number.isNaN(e.cols.bestObjective[row]) && e.cols.bestFeasible[row] === 1) >= 0,
    reason: !objective ? 'No objective: no Specs row of this run says "then lower/higher is better".' : empty ?? 'No design has met every hard spec yet.' });
  for (const name of store.specNames) {
    const def = store.specDefs[name];
    const limits = [def?.threshold_lower != null ? `≥ ${def.threshold_lower}` : '', def?.threshold_upper != null ? `≤ ${def.threshold_upper}` : ''].filter(Boolean).join(', ');
    charts.push({ id: `spec:${name}`, title: name, unit: def?.unit ?? '', axis: 'evaluation', group: 'Specs', source: `metrics (aggregate row of ${name})`,
      about: `The value of this spec's equation at each evaluation${limits ? `, against its limit (${limits}, ${def?.hard ? 'hard' : 'soft'})` : ''}.`,
      available: p.any(`spec:${name}`), reason: 'No evaluation has a value for this spec yet.' });
  }
  charts.push({ id: 'seconds', title: 'Simulation time per evaluation', unit: 's', axis: 'evaluation', group: 'Results', source: 'evaluations.execution_seconds',
    about: 'From the start of an evaluation to its result, every attempt included.', available: p.any('seconds'), reason: empty });
  const learner = store.learner;
  for (const [id, title, unit, source, about] of LEARNER) {
    const columns = LEARNER_COLUMNS[id];
    const has = learner.recorded && !context.calibration && columns.some(([c]) => p.anyUpdate(c));
    charts.push({ id, title, unit, axis: 'update', group: 'Learner (SAC)', source, about, available: has,
      reason: context.calibration ? 'A baseline run with calibration learns nothing: its random designs only suggest each Specs row\'s scale and a starting temperature.'
        : learner.reason ?? (u.n === 0 ? 'No learner update yet: they begin once the warm-up designs fill a training batch.' : 'This run recorded no value of it.') });
  }
  return charts;
}
