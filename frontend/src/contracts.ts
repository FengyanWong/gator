// The records handed between task choice, run choice and saved-model loading. These are wire/draft types, not runtime
// validation: the backend still validates configurations. Unknown extension fields survive spread/copy operations.
export type ConfigRow = Record<string, unknown>;
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
  parameters: ConfigRow[];
  targets: ConfigRow[];
  measurements: ConfigRow[];
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
    reward_settings?: { violation_shape?: string; worst_spec_share?: number; objective_weight?: number; margin_weight?: number };
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
