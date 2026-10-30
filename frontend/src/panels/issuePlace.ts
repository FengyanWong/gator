// An issue's place in the editors' and windows' words (branch record SIF-141): the header's list of blocking issues and the
// refusals of a configuration the backend cannot read (api.ts `schemaProblem`) name each place by it. Out of editorRules.ts
// since the review of SIF-141: a place in the RL model window names a Mode by rlModelText.ts's MODE_NAME, and
// scripts/editor_renames_check.mjs lets editorRules.ts load ../units alone. No React.
import type { Json } from '../api';
import { columnOf, fieldLabel, type Section, SECTION_TITLES } from './editorRules';
import { ADVANCED_ROWS, MODE_NAME } from './rlModelText';

/** The Advanced fold's boxes (RlModelWindow.tsx `AdvancedFields`): the alpha learning rate, the tick box, ADVANCED_ROWS. */
const ADVANCED_BOXES = ['alpha_learning_rate', 'update_after_dispatch', ...ADVANCED_ROWS.flat().map(([name]) => name)];
/** Output settings' boxes (OutputPanel.tsx; change both together): "Checkpoint every" sets either interval. */
const OUTPUT_BOXES = ['output_root', 'experiment_name', 'experiment_id', 'save_learner_updates', 'save_checkpoints', 'save_replay_snapshots',
  'save_transition_archive', 'export_summary_csv', 'checkpoint_every_evaluations', 'checkpoint_every_seconds', 'waveform_retention', 'waveform_storage_limit_bytes'];
/** Where a run, output or research setting is set, by the words of the panel or window that holds it: the first pattern the
 *  path matches. The Run configuration ones are RunConfiguration.tsx's labels, the RL model window's its headings and
 *  labels (RlModelWindow.tsx, Pdk.tsx `ComponentList`): change both together. Fine-tune's switches are kept with the
 *  Advanced values but ticked under its own settings, and a bare run.advanced is the check of them, fine_tune_only_option
 *  (validation.py `_check_run`). The connection is chosen in the Connection window. A setting no box sets matches none and
 *  stays as written (review of SIF-141: a last "Run configuration" for any run setting named it for run.rehearsal - a
 *  blocker, rehearsal_with_transfer_inputs, that New run like this can bring in - and for the connection; "RL model window
 *  · Advanced" every other run.advanced field, run.advanced.spec_registry too; "Output settings" min_free_bytes and four
 *  more). */
const PLACES: [RegExp, string][] = [
  [/^run\.network\.vocabulary\b/, 'RL model window · Components'],
  [/^run\.network\.(spec_input|size_features|device_model_features|bench_features|net_roles|operating_point_ratios)\b/, 'RL model window · Network inputs'],
  [/^run\.network\b/, 'RL model window · Network'],
  [/^run\.advanced(\.(freeze_encoder|encoder_only_transfer|reset_critic)\b|$)/, `RL model window · ${MODE_NAME.fine_tune}: its own settings`],
  [new RegExp(`^run\\.advanced\\.(${ADVANCED_BOXES.join('|')})\\b`), 'RL model window · Advanced'],
  [/^run\.mode\b/, 'RL model window · Mode'], [/^run\.model_source\b/, 'RL model window · Saved models'],
  [/^run\.(model_label|frozen_action|continual_learning)\b/, 'RL model window'],
  [/^run\.reward\b/, 'Run configuration · Reward and conditions'], [/^run\.conditions\b/, 'Run configuration · Training conditions'],
  [/^run\.concurrency\b/, 'Run configuration · Concurrent Spectre jobs'], [/^run\.max_evaluations\b/, 'Run configuration · Evaluation budget'],
  [/^run\.seed\b/, 'Run configuration · Random seed'], [/^run\.stop_at_first_feasible\b/, 'Run configuration · Stop at the first feasible design'],
  [/^run\.max_spectre_launches\b/, 'Run configuration · Limits · Max Spectre launches'],
  [/^run\.max_retries\b/, 'Run configuration · Limits · Max retries per evaluation'],
  [/^run\.max_wall_seconds\b/, 'Run configuration · Limits · Wall-time limit (s)'],
  [/^run\.max_consecutive_infrastructure_failures\b/, 'Run configuration · Limits · Pause after N consecutive infrastructure failures'],
  [/^run\.max_consecutive_failures\b/, 'Run configuration · Limits · Stop after N consecutive failed evaluations'],
  [/^run\.connection_profile_id\b/, 'Connection window'], [new RegExp(`^output\\.(${OUTPUT_BOXES.join('|')})\\b`), 'Output settings'],
  [/^research\b/, 'Research experiments'], [/^circuit\b/, 'Tasks window'],
];
/** An issue's place in the editors' and windows' words (branch record SIF-141), from its path in the configuration as the
 *  validation report and a refusal give it: the header's list and the refusals showed "parameters[0].lower row
 *  input_pair_width", "run.network" and "(whole configuration)" as they came, while the tabs, the formula bar and the
 *  confirmations had said the same places in words since SIF-5 and SIF-51. A row by its table, its ID in `config` (`keys`:
 *  schema.section_keys) - "row N" where none names it, both where another row of the table holds the same ID, as a
 *  duplicate does - and its field by the header of the column it is chosen in: "Parameters · input_pair_width · Lower". A
 *  table alone is "the Specs table", no path "the whole configuration", a setting the place that sets it ("RL model window ·
 *  Network"); a path none of these knows stays as written. pydantic's parameters.3.variable_id, as an older backend sends
 *  it, reads as parameters[3].variable_id. */
export function placeOf(path: string, config: Json | null, keys: Record<string, string>): string {
  const at = path.replace(/\.(\d+)(?=\.|$)/g, '[$1]');
  if (!at) return 'the whole configuration';
  const row = /^(parameters|measurements|targets)(?:\[(\d+)\](?:\.(\w+))?)?(?!\w)/.exec(at);
  if (!row) return PLACES.find(([pattern]) => pattern.test(at))?.[1] ?? path;
  const [, section, index, field] = row, title = SECTION_TITLES[section as Section];
  if (index == null) return `the ${title} table`;
  const n = Number(index), keyField = keys[section], rows: Json[] = config?.[section] ?? [];
  const key = keyField ? rows[n]?.[keyField] : null;
  const name = key == null || key === '' ? `row ${n + 1}`
    : rows.some((r, i) => i !== n && r?.[keyField] === key) ? `${key} (row ${n + 1})` : String(key);
  return [title, name, ...(field ? [fieldLabel(section, columnOf(section, field))] : [])].join(' · ');
}
