// Probes follow the testbench a cell was read through (plan-refactoring C9, out of Left.tsx's CircuitPanelBody).
import { MutableRefObject, useRef, useState } from 'react';
import { api, Json } from '../api';
import { useNewest } from '../newest';
import { sameJson, tablesOf } from './taskRows';

/** `ref`: the configuration's circuit; `latest`: the configuration as it is now. `followCount`: a task chosen meanwhile drops
 *  a probe read on its way (useTaskChoice). */
export function useTestbenchProbes({ ref, latest, setConfig }: { ref: Json; latest: MutableRefObject<Json>;
  setConfig: (f: (c: Json) => Json, record?: boolean) => void }) {
  // Probes follow the testbench (user request 2026-09-21): a cell read THROUGH a testbench brings, in Probes, the results
  // of the circuit type that testbench fits, each naming the testbench net or supply branch it is read from
  // (profiles.testbench_probes - from the export that was read, not from what the box shows now). Only after a choice of
  // library / cell / testbench or a press of Read, never on page load; and only over rows that are nobody's work - empty,
  // brought by an earlier testbench, or still exactly the rows the last registered task brought. That task's untouched
  // targets leave Specs with them (they point at its probes). Rows someone edited stay, and the line offers the exchange.
  // A choice exchanges within its own Undo step; a press is a step of its own. (The circuit type a saved task measures
  // with is read from its Probes when it is saved.)
  const [probeNote, setProbeNote] = useState<Json>(null);  // { state: brought | kept | none, found, clearedTask? }
  const brought = useRef<string[]>([]);                     // Probes this panel brought from a testbench (JSON), this page session
  const followCount = useNewest();
  const followTestbench = async (loaded: Json, press: boolean) => {
    const mine = followCount.next();
    const found = loaded?.loaded && loaded.native_draft && !loaded.profile_task ? loaded.testbench_probes : null;
    if (!found) { setProbeNote(null); return; }
    if (!found.rows.length) { setProbeNote({ state: 'none', found }); return; }
    if (sameJson(latest.current.measurements, found.rows)) { setProbeNote(null); return; }
    const taskId = latest.current.circuit.task_id;
    const starter = taskId ? await api.starter(taskId).catch(() => null) : null;
    if (!mine()) return;
    const now = latest.current;
    const untouched = !(now.measurements ?? []).length || brought.current.includes(JSON.stringify(now.measurements))
      || (!!starter && sameJson(tablesOf(now).measurements, tablesOf(starter).measurements));
    if (!untouched) { setProbeNote({ state: 'kept', found }); return; }
    const staleTargets = !!starter && (now.targets ?? []).length > 0 && sameJson(tablesOf(now).targets, tablesOf(starter).targets);
    brought.current.push(JSON.stringify(found.rows));
    setConfig(c => ({ ...c, measurements: found.rows, ...(staleTargets ? { targets: [] } : {}) }), press);
    setProbeNote({ state: 'brought', found, clearedTask: staleTargets ? taskId : null });
  };
  const takeTestbenchProbes = () => {
    const found = probeNote.found;
    brought.current.push(JSON.stringify(found.rows));
    setConfig(c => ({ ...c, measurements: found.rows }));
    setProbeNote({ state: 'brought', found });
  };
  const noteHere = probeNote && probeNote.found.library === ref.library && probeNote.found.cell === ref.cell ? probeNote : null;
  return { followTestbench, takeTestbenchProbes, followCount, noteHere };
}
