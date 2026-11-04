// The right column's Research experiments (plan-refactoring C4, out of Right.tsx).
import type { Json } from '../api';
import { Num } from './fields';
import { Typed } from './Typed';

/** A label's words in its list ("unseen_circuit_class" -> "Unseen circuit class"); the run still stores the label (branch record SIF-35). */
const words = (label: string) => label.charAt(0).toUpperCase() + label.slice(1).replace(/_/g, ' ');
/** A free-text label as its box shows it (none for "unspecified") and as it is stored (an empty box: "unspecified"). */
const unlabelled = (label?: string | null) => label && label !== 'unspecified' ? label : '';
const labelled = (typed: string) => typed.trim() ? typed : 'unspecified';

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
      {/* "unspecified", the backend's word for no label, is the placeholder, not text in the box (branch record SIF-60: it
          had to be deleted before typing, and the examples were never seen); an emptied box stores it, as the backend's
          default. The examples are labels the research tables already hold, not Mode names. */}
      <label title="Names the method in every research table (Data tables > Export research CSVs): run summary, success per budget, paired runs, transfer summary, cumulative cost.">Method label
        <input value={unlabelled(r.method_label)} onChange={e => set({ method_label: labelled(e.target.value) })} placeholder="unspecified - e.g. Scratch, Pretrained-Frozen, Pretrained-Fine-tuned, encoder-only transfer" /></label>
      <label title="Associates runs with the same target, initial dimensions, budget, test setup and target seed.">Comparison pair ID<input value={unlabelled(r.comparison_pair_id)} onChange={e => set({ comparison_pair_id: labelled(e.target.value) })} placeholder="unspecified" /></label>
      <label title="Evaluation budgets at which success is counted (success per budget). Empty: the run's own budget.">Budget checkpoints{listBox('budget_checkpoints', true)}</label>
      <details className="more transfer-study"><summary>Transfer study</summary>
        <p className="hint">Optional labels for training and testing on different circuits.</p>
        <label>Split<select value={r.split ?? 'unspecified'} onChange={e => set({ split: e.target.value })}>{['unspecified', 'train', 'validation', 'test'].map(s => <option key={s} value={s}>{words(s)}</option>)}</select></label>
        <label>Generalization level<select value={r.generalization_level ?? 'unspecified'} onChange={e => set({ generalization_level: e.target.value })}>
          {['unspecified', 'same_task', 'unseen_spec', 'unseen_topology', 'unseen_circuit_class'].map(s => <option key={s} value={s}>{words(s)}</option>)}</select></label>
        <label>Training sources{listBox('training_sources')}</label>
        <div className="row"><Num label="Task order K" nullable value={r.task_order} onChange={v => set({ task_order: v })} /><Num label="Pretrain seed (source)" nullable value={r.pretrain_seed} onChange={v => set({ pretrain_seed: v })} /></div>
        <label>Ablation labels{listBox('ablation_labels')}</label>
      </details>
    </details>
  );
}
