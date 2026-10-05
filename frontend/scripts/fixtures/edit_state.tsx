// Real store and task components; every API answer is in memory. No simulator or task is written.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, type Json } from '../../src/api';
import { useConfig } from '../../src/store';
import { CircuitPanel } from '../../src/panels/Left';

const fixture: any = { pending: [], state: null };
(window as any).fixture = fixture;
const rows = (name: string) => [{ variable_id: name, instance_path: 'M1', parameter_name: 'w', unit: 'um', optimized: true, lower: 1, upper: 5, step: .1 }];
const generated = (task_key: string) => ({ loaded: true, task_key, mock: false, native_draft: false, generated_profile: true,
  baseline_recorded: true, complete: true, diagnostics: [], circuit: {}, hierarchy: {},
  summary: { device_count: 1, unknown_devices: [], devices: [] }, notes: [] });
api.tasks = async () => ({ tasks: ['real:aa', 'real:bb'].map(task_key => ({ task_key, kind: 'real', available: true, generated: true, revision: 1 })) });
api.loadCircuit = async ref => generated(ref.task_id);
api.taskSave = body => new Promise((resolve, reject) => { fixture.pending.push({ body, resolve, reject }); });
fixture.finish = (index: number, fail = false) => {
  const p = fixture.pending[index];
  if (fail) p.reject(new Error('Fixture save failed'));
  else p.resolve({ task_key: p.body.config.circuit.task_id, revision: 2, created: false, parameters: rows('normalized'), changed: [] });
};

function TaskFixture() {
  const [config, setConfig] = useState<Json>({ project: { name: 'audit', task_name: 'aa' },
    circuit: { source: 'registered_task', task_id: 'real:aa' }, parameters: rows('original'), measurements: [], targets: [], run: {}, output: {}, research: {} });
  const [circuit, setCircuit] = useState<Json>(generated('real:aa'));
  fixture.state = { task: config.circuit.task_id, parameter: config.parameters[0]?.variable_id, loaded: circuit?.task_key };
  fixture.edit = (name: string) => setConfig((c: Json) => ({ ...c, parameters: rows(name) }));
  fixture.switchTask = (name: string) => setConfig((c: Json) => ({ ...c, circuit: { ...c.circuit, task_id: `real:${name}` }, parameters: rows(`task_${name}`) }));
  return <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId="fixture" onAgent={() => {}}
    taskSlot={document.getElementById('bar')} taskNotes={document.getElementById('notes')} />;
}

function HistoryFixture() {
  const s = useConfig();
  fixture.state = { name: s.config.project.name, canUndo: s.canUndo, canRedo: s.canRedo };
  fixture.edit = (name: string, record = true) => s.setConfig((c: Json) => ({ ...c, project: { ...c.project, name } }), record);
  fixture.undo = s.undo; fixture.redo = s.redo;
  return <><input id="name" value={s.config.project.name} onChange={e => { const value = e.target.value; fixture.edit(value); }} />
    <button id="undo" onClick={s.undo}>Undo</button><button id="redo" onClick={s.redo}>Redo</button></>;
}

const task = new URL(location.href).searchParams.get('case') === 'task';
if (!task) localStorage.removeItem('gator-workbench-config-v1');
createRoot(document.getElementById('root')!).render(<React.StrictMode>{task ? <TaskFixture /> : <HistoryFixture />}</React.StrictMode>);
