// The records handed between task choice, run choice and saved-model loading. These are wire/draft types, not runtime
// validation: the backend still validates configurations. Unknown extension fields survive spread/copy operations.
export type ConfigRow = Record<string, unknown>;
export type EditorSection = 'parameters' | 'measurements' | 'targets';
/** Draft rows may omit defaults and may be invalid; the backend owns validation. */
export interface ParameterRow extends ConfigRow {
  variable_id: string;
  parameter_name: string;
  unit: string;
  instance_path?: string | null;
  initial_value?: number | null;
  optimized?: boolean;
  value_type?: 'continuous' | 'integer';
  lower?: number | null;
  upper?: number | null;
  step?: number | null;
  scale?: 'linear' | 'log';
  binding_group?: string | null;
  ratio?: number;
  notes?: string;
}
export interface ProbeRow extends ConfigRow {
  measurement_id: string;
  analysis: 'dc' | 'ac' | 'tran' | 'noise' | 'stb' | 'pss' | 'pnoise' | 'other';
  unit: string;
  result_source?: 'backend_profile' | 'ade_output' | 'size_estimate';
  source_name?: string | null;
  signal?: string | null;
  notes?: string;
}
export interface SpecRow extends ConfigRow {
  metric_id: string;
  equation: string;
  unit: string;
  constraint: '>=' | '<=' | 'interval';
  lower?: number | null;
  upper?: number | null;
  hard?: boolean;
  direction_after_feasible?: 'none' | 'minimize' | 'maximize';
  nominal_only?: boolean;
  missing_is_failure?: boolean;
  margin_sides?: 'both' | 'lower' | 'upper';
  soft_weight?: number;
  normalization_scale?: number | null;
  active?: boolean;
  basis?: string;
  notes?: string;
}
/** A generic table can inspect known fields without treating arbitrary extensions as any. */
export type EditorRow = Partial<ParameterRow & ProbeRow & SpecRow>;
export interface EditorColumn {
  name: string;
  type: string;
  label?: string;
  default?: unknown;
  guidance?: string;
  nullable?: boolean;
  required?: boolean;
  advanced?: boolean;
  hidden?: boolean;
  options?: string[] | null;
}
export interface EditorSchema {
  schema_version: string;
  editors: Record<EditorSection, EditorColumn[]>;
  section_keys: Record<EditorSection, string>;
  json_schema: Record<string, unknown>;
  units: string[];
  unit_forms: unknown;
  run_modes: string[];
  encoder_types: string[];
  tables: string[];
  data_dictionary: unknown;
}
export interface RowDiff {
  section: EditorSection;
  key: string;
  change: 'added' | 'removed' | 'modified';
  fields: { field: string; before: unknown; after: unknown }[];
}
export interface ValidationIssue {
  level: 'error' | 'blocker' | 'warning' | 'unresolved' | 'info';
  code: string;
  path: string;
  message: string;
}
export interface SavedRowChange {
  fields: ConfigRow;
  unit?: string | null;
}
export interface UnsavedSection {
  added: string[];
  removed: string[];
  changed: Record<string, SavedRowChange>;
  reordered?: boolean;
}
export interface UnsavedRows {
  sections?: Partial<Record<EditorSection, UnsavedSection>>;
}
export interface ValidationReply {
  blocks_run: boolean;
  counts: Partial<Record<ValidationIssue['level'], number>>;
  issues: ValidationIssue[];
  facts: Record<string, unknown> & { independent_action_variables?: number };
  unsaved_rows?: UnsavedRows | null;
}
export interface CircuitReference {
  [field: string]: unknown;
  source?: string;
  task_id?: string | null;
  circuit_class?: string | null;
  pdk_id?: string | null;
  library?: string | null;
  cell?: string | null;
}
export interface TaskRows {
  parameters: ParameterRow[];
  targets: SpecRow[];
  measurements: ProbeRow[];
}
export interface TaskStarter extends TaskRows {
  circuit: CircuitReference;
  project: { [field: string]: unknown; name?: string; task_name: string };
  revision?: number | null;
}
export interface TaskSummary {
  [field: string]: unknown;
  task_key: string;
  kind: string;
  generated?: boolean;
  saved_utc?: string | null;
}
export interface ModelSource {
  [field: string]: unknown;
  run_dir?: string | null;
  checkpoint_id?: string | null;
}
export interface NetworkConfig {
  [field: string]: unknown;
  encoder_type?: string;
  hidden_dim?: number;
  heads?: number;
  layers?: number;
  structural_encoding?: string;
  operating_points?: boolean;
  vocabulary?: string;
  spec_input?: string;
  size_features?: string;
  device_model_features?: boolean;
  bench_features?: string;
  net_roles?: string;
  operating_point_ratios?: boolean;
}
export interface RunSettings {
  mode: string;
  optimizer?: string;
  model_label?: string | null;
  max_evaluations: number;
  max_spectre_launches?: number | null;
  max_wall_seconds?: number | null;
  max_retries?: number;
  max_consecutive_failures?: number;
  max_consecutive_infrastructure_failures?: number;
  stop_at_first_feasible?: boolean;
  seed: number;
  frozen_action?: string;
  network?: NetworkConfig;
  model_source?: ModelSource;
  reward?: Record<string, unknown>;
  conditions?: Record<string, unknown>;
  advanced?: Record<string, unknown>;
  rehearsal?: Record<string, unknown>;
  continual_learning?: boolean;
}
export interface WorkbenchConfig extends TaskStarter {
  [field: string]: unknown;
  run: RunSettings;
}
export type ConfigSetter = (next: WorkbenchConfig | ((config: WorkbenchConfig) => WorkbenchConfig), record?: boolean) => void;
export interface RunSummary {
  [field: string]: unknown;
  run_dir: string;
  task_key: string | null;
  task_name?: string | null;
  created_utc?: string | null;
  mode?: string | null;
  parent?: (ModelSource & { run_dir: string }) | null;
}
/** Load run/New run like this are offered only for a run whose registered task is known. */
export type TaskRunSummary = RunSummary & { task_key: string };
export interface ModelDescription {
  checkpoint_id: string;
  contract?: {
    model_config?: NetworkConfig;
    feature_schema?: { version?: string; op_columns?: string[] };
    spec_schema?: { layout?: string };
    reward_version?: string;
    reward_settings?: { violation_shape?: string; worst_spec_share?: number; objective_weight?: number; margin_weight?: number;
      objective_shape?: string; nominal_gate_band?: number };
    condition_policy?: string;
    planned_conditions?: { corner: { id: string } }[];
  };
  counters: { evaluations_committed: number; learner_updates: number; replay_size: number };
  source_task_id: string;
  created_utc: string;
  metadata_version: string;
  restoration_capability: string;
  missing_components: string[];
  path: string;
}
export interface ModelReply {
  description: ModelDescription;
  vocabulary?: { name: string; label: string; loaded?: boolean };
  compatibility?: { compatible: boolean; mode: string; checks: { component: string; status: string; detail: string }[] } | null;
  compatibility_unchecked?: { title: string; what: string; note: string; technical: string } | null;
  suggestion?: { mode: string; reason: string; requires_confirmation: boolean };
}
