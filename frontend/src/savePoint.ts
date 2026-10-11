import { api, Json } from './api';

/** One save point of a saved model, as "Use this save point" takes it (record 7.265; plan docs/plan-frontend-run-workflow.md,
 *  "RL model window"): the id the backend resolved - a "latest" asked for becomes the concrete id it names, so the choice is
 *  pinned -, the model's network and its component list. The RL model window, Load run and New run like this all take a
 *  saved model this way (record 7.267), so the draft never holds a model without its network. */
export type SavePoint = { run_dir: string; checkpoint_id: string; network: Json | null; vocabulary: string | null; evaluations: number | null };

/** The Modes that load a saved model. */
export const LOADS = ['fine_tune', 'frozen'];
/** The network settings a saved model fixes besides its encoder: the fallback until the backend's own list is read. */
export const NETWORK_FIELDS = ['hidden_dim', 'heads', 'layers', 'structural_encoding'];
export const pick = (source: Json, fields: string[]): Json =>
  Object.fromEntries(fields.filter(f => source?.[f] !== undefined && source?.[f] !== null).map(f => [f, source[f]]));

/** Reads a save point's description (`POST /api/runs/model`). Rejects when it cannot be read: no such save point, a run
 *  outside the allowed output roots. */
export async function readSavePoint(run_dir: string, checkpoint_id: string, fields: string[] = NETWORK_FIELDS): Promise<SavePoint> {
  const answer: Json = await api.model(run_dir, checkpoint_id);
  const network = networkOf(answer?.description, fields);
  return { run_dir, checkpoint_id: answer?.description?.checkpoint_id ?? checkpoint_id, network, vocabulary: answer?.vocabulary?.name ?? null,
    evaluations: answer?.description?.counters?.evaluations_committed ?? null };
}

/** The network a saved model fixes, from its description (`POST /api/runs/model`): its encoder, `fields`, its structural
 *  input, whether it takes operating points and its network inputs (record 7.298: a spec set, sizes relative to the PDK,
 *  device model features; record 7.317: bench sources, net tags by rule, operating-point ratios - read from the input
 *  schemas its contract records); null when the description names no encoder. */
export function networkOf(description: Json, fields: string[]): Json | null {
  const saved = description?.contract?.model_config;
  const version: string = description?.contract?.feature_schema?.version ?? '';
  return saved?.encoder_type ? { encoder_type: saved.encoder_type, ...pick(saved, fields),
    structural_encoding: saved.structural_encoding ?? (saved.encoder_type === 'graph_gps' ? 'rwse' : 'none'),
    // The raw operating-point input holds the measured numbers (ids first); a model of the second build with the
    // ratios alone holds only the region columns (record 7.317) and does not have the raw input.
    operating_points: !!description.contract?.feature_schema?.op_columns?.includes('ids'),
    spec_input: description.contract?.spec_schema?.layout === 'spec-set-v1' ? 'set' : 'slots',
    size_features: version.includes('+pdk-relative-sizes') ? 'pdk_relative' : 'absolute',
    device_model_features: version.includes('+device-model-features'),
    bench_features: version.includes('+bench-features') ? 'relative' : 'absolute',
    net_roles: version.includes('+net-roles-by-rule') ? 'rule' : 'task',
    operating_point_ratios: version.includes('+op-ratios') } : null;
}

/** The run settings with that save point as the source, its network and its component list: one change of the draft. */
export function withSavePoint(run: Json, point: SavePoint): Json {
  const { vocabulary: _old, ...rest } = run.network ?? {};
  return { ...run, model_source: { ...(run.model_source ?? {}), run_dir: point.run_dir, checkpoint_id: point.checkpoint_id },
    network: point.network ? { ...rest, ...point.network, ...(point.vocabulary && point.vocabulary !== 'standard' ? { vocabulary: point.vocabulary } : {}) } : run.network };
}
