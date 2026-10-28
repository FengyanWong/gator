// A task's baseline line under the editors' toolbar (record 7.248): the automatic baseline, followed in the header, and
// Retry baseline while no real one is recorded.
import { api, Json, problemText } from '../api';
import { useAsyncAction } from '../store';
import { useState } from 'react';
import { followTaskBaseline } from './TaskSave';

/** Automatic creation baselines are followed in the header. Retry is available only when a reference is missing. */
export function TaskBaseline({ circuit, config, refresh }: { circuit: Json; config: Json; refresh: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const { busy, run } = useAsyncAction(e => setError(problemText(e)), () => setError(null));
  if (!circuit.generated_profile && !circuit.circuit?.ngspice_task) return null;
  const baseline = circuit.baseline_setup;
  if (circuit.baseline_recorded || (!circuit.generated_profile && baseline?.state === 'completed' && !baseline.failed)) return null;
  const live = baseline?.worker_alive || baseline?.state === 'started';
  const retry = () => run('baseline', async () => {
    const made = await api.taskBaseline({ task_key: circuit.task_key, profile_id: config.run.connection_profile_id,
      output_root: config.output.output_root });
    followTaskBaseline(made);
    if (made.baseline?.state === 'blocked') setError(made.baseline.reason);
    refresh();
  });
  return <div className={live ? 'hint' : 'warn'}>
    <p>{live ? 'The task’s baseline is running: one simulation of its starting design. Follow it in Run status.'
      : `No real baseline yet. ${error || baseline?.reason || circuit.baseline_attempt?.reason || 'Task creation starts it automatically; an older task can run it here.'}`}</p>
    {!live && <button disabled={!!busy} onClick={retry} title="Runs one simulation of this task’s saved starting design, with fixed settings. No calibration or training.">{busy ? 'Starting baseline...' : 'Retry baseline'}</button>}
  </div>;
}
