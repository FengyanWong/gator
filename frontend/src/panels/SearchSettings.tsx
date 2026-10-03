import { useEffect, useState } from 'react';
import { agentSettingsShared, Json, onAgentSettings } from '../api';

export const SEARCH_METHODS: Record<string, [string, string]> = {
  sac: ['SAC', 'Random starting designs, then SAC learns and explores'],
  llm_warmstart: ['LLM warm start → SAC', 'LLM starting designs, initial SAC training, then SAC learns and explores'],
  llm: ['LLM only', 'AI proposes every search design'],
  sac_llm_rescue: ['SAC with LLM rescue', 'SAC runs; AI contributes suggestions when progress stalls'],
};

export function searchPhase(s: Json): string {
  if (!s) return '';
  if (s.phase === 'llm_warmup') return `Collecting starting designs · ${s.admitted} / ${s.warm_count}`;
  if (s.phase === 'initial_learning') return `Learning from starting designs · ${s.trained} / ${s.initial_updates} updates`;
  if (s.method === 'llm') return s.pending ? 'AI proposing designs' : 'Simulating AI designs';
  return s.pending ? 'SAC search — AI suggestions pending' : 'SAC search';
}

export function SearchSettings({ run, schema, set }: { run: Json; schema: Json; set: (fields: Json) => void }) {
  const search = run.search ?? {}, method = search.method ?? 'sac';
  const [agent, setAgent] = useState<Json>(null);
  const [error, setError] = useState('');
  // The Agent tab's settings as it saved them last (shared, api.ts): "Same as the Agent tab (...)" follows a save there.
  useEffect(() => { agentSettingsShared().then(setAgent).catch(e => setError(e.message)); return onAgentSettings(setAgent); }, []);
  const fields = schema.$defs.SearchSettings.properties;
  const value = (key: string) => search[key] ?? fields[key]?.default ?? '';
  const edit = (patch: Json) => set({ search: { ...search, ...patch } });
  const provider = search.provider ?? agent?.provider;
  const catalog = agent?.catalog?.[provider];
  const inheritedModel = provider === agent?.provider ? agent?.model : null;
  const model = search.model ?? inheritedModel;
  const efforts = catalog?.models?.find((m: Json) => m.id === model)?.efforts ?? catalog?.efforts ?? [];
  const inheritedEffort = provider === agent?.provider && efforts.includes(agent?.effort) ? agent.effort : null;
  const count = search.warm_start_count ?? Math.max(8, run.advanced?.batch_size ?? 8, run.advanced?.warmup_transitions ?? 8);
  const requiredEvaluations = count + Math.ceil(count / (run.advanced?.episode_length ?? 4));
  // An empty box is the default, shown greyed as its placeholder. It used to show the default as a typed value again the
  // moment the box was emptied (typing 8 then gave 48), and stored null for a number that may not be empty.
  const number = (key: string, label: string, nullable = false) => <label>{label}<input type="number" min={fields[key]?.minimum ?? 1}
    max={fields[key]?.maximum} step={key.includes('usd') ? '0.01' : '1'} value={search[key] ?? ''}
    placeholder={nullable ? 'Automatic' : fields[key]?.default != null ? String(fields[key].default) : 'Required'}
    onChange={e => edit({ [key]: e.target.value === '' ? (nullable ? null : undefined) : Number(e.target.value) })} /></label>;
  return <section className="search-settings">
    {/* One "Search method", the field's own label (user, 2026-10-03: "The search method subtitle is repeated"), as Mode has. */}
    <label>Search method<select aria-label="Search method" value={method} onChange={e => {
      const next = e.target.value;
      set({ search: { ...search, method: next }, ...(next === 'llm' ? { concurrency: 1, mode: 'scratch', model_source: {} }
        : next !== 'sac' && run.mode === 'frozen' ? { mode: 'scratch' } : {}) });
    }}>{fields.method.enum.map((m: string) => <option key={m} value={m}>{SEARCH_METHODS[m]?.[0] ?? m}</option>)}</select></label>
    <p className="hint search-caption">{SEARCH_METHODS[method]?.[1]}</p>
    <details><summary>What each method does</summary>{Object.entries(SEARCH_METHODS).map(([key, [label, caption]]) =>
      <p key={key}><b>{label}.</b> {caption}.</p>)}
      <p>SAC modes use the selected graph encoder. AI suggestions are simulated and checked against the same bounds and specifications.</p></details>
    {method !== 'sac' && <>
      {error && <p className="error">{error}</p>}
      <label>AI provider<select value={search.provider ?? ''} onChange={e => edit({ provider: e.target.value || null, model: null, effort: null })}>
        <option value="">Same as the Agent tab</option><option value="claude_code">Claude Code</option><option value="codex">Codex</option></select></label>
      {provider === 'disabled' && <p className="error">Choose a provider here or enable one in the Agent tab.</p>}
      <label>AI model<select value={search.model ?? ''} onChange={e => edit({ model: e.target.value || null, effort: null })}>
        <option value="">{inheritedModel ? `Same as the Agent tab (${inheritedModel})` : 'Provider default'}</option>
        {(catalog?.models ?? []).map((m: Json) => <option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
      <label>AI effort<select value={search.effort ?? ''} onChange={e => edit({ effort: e.target.value || null })}>
        <option value="">{inheritedEffort ? `Same as the Agent tab (${inheritedEffort})` : 'Provider default'}</option>
        {efforts.map((e: string) => <option key={e} value={e}>{e}</option>)}</select></label>
      {number('max_llm_calls', 'Maximum AI calls')}
      {provider === 'claude_code' && number('max_llm_notional_usd', 'Maximum notional cost (USD)')}
      {provider === 'codex' && <p className="hint">Codex reports tokens, but no dollar cost here. The call ceiling applies.</p>}
      {method === 'llm_warmstart' && <>
        <p className="search-handover">{count} starting transitions → {value('initial_sac_updates')} training updates → SAC</p>
        {count < (run.advanced?.batch_size ?? 8) && <p className="error">Starting designs must fill a training batch.</p>}
        {count > (run.advanced?.replay_capacity ?? 10000) && <p className="error">Replay capacity must hold all starting transitions.</p>}
        {run.max_evaluations < requiredEvaluations && <p className="warn">Starting designs plus required resets need at least {requiredEvaluations} evaluations. This budget may end before SAC training.</p>}
      </>}
      {method === 'llm' && <p className="hint">One baseline, one simulation lane, then AI designs. Save now keeps search progress; there is no policy model.</p>}
      <details><summary>More settings</summary>
        {number('candidates_per_call', 'Designs per AI call')}
        {number('llm_call_timeout_seconds', 'AI call timeout (seconds)')}
        {method === 'llm_warmstart' && <>{number('warm_start_count', 'Starting transitions', true)}{number('initial_sac_updates', 'Initial SAC updates')}</>}
        {method === 'sac_llm_rescue' && <>{number('rescue_stagnation_evaluations', 'Evaluations without progress before rescue')}
          {number('rescue_max_rounds', 'Maximum rescue rounds')}</>}
        <label><input type="checkbox" checked={search.hints_allowed ?? true} onChange={e => edit({ hints_allowed: e.target.checked })} />Allow hints in the run’s AI thread</label>
      </details>
    </>}
  </section>;
}
