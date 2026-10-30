// The bottom tabs follow the registered task (record 7.212), and a Load run gives way to a task chosen elsewhere (record
// 7.270). Out of App.tsx's Page (plan-refactoring C5).
import { useEffect, useRef } from 'react';
import type { Json } from '../api';
import { useNewest } from '../newest';

// The bottom tabs follow the registered task (record 7.212, user: "after selecting specific task, it automatically load the
// most recent corresponding run of the registered task. If there is no recent run, then leave run selection and run status
// default blank unless you choose other runs"). When the page's task changes - chosen under Task, saved for the first time,
// a choice taken back with Undo - the run list is read again and the task's newest run is shown (a Baseline simulation is
// one of its runs), or no run. Not when the page opens: the run it showed is kept. A run chosen in the run window or
// started while the list is read stays, and so does the run shown when the read fails or the page leaves its tasks for a
// Virtuoso cell. The header's Start / Pause / Abort keep their own run. A server older than this page lists runs without
// their task: the run shown stays then, instead of every choice showing none.
export function useTaskRunFollow({ config, runDir, readRuns, setRunDir }: { config: Json; runDir: string | null;
  readRuns: (fresh?: boolean) => Promise<{ list: Json[]; error: string | null }>; setRunDir: (dir: string | null) => void }) {
  const taskKey: string | null = config.circuit?.source === 'registered_task' ? config.circuit.task_id ?? null : null;
  const followedTask = useRef(taskKey);
  // The generation of the Runs window's Load run / New run like this (record 7.270, Astra's review of 2026-10-07): each one
  // takes the next number and goes on only while it is still the newest - a task chosen elsewhere lets it go too.
  const loadSerial = useNewest();
  const shownNow = useRef(runDir);
  shownNow.current = runDir;
  useEffect(() => {
    if (taskKey === followedTask.current) return;
    followedTask.current = taskKey;
    loadSerial.drop();                                   // a task chosen elsewhere: a Load run still on its way is let go
    if (!taskKey) return;
    const before = shownNow.current;
    readRuns().then(({ list, error }) => {
      if (error || followedTask.current !== taskKey || shownNow.current !== before) return;
      if (list.length && !list.some(r => 'task_key' in r)) return;
      setRunDir(list.find(r => r.task_key === taskKey)?.run_dir ?? null);
    });
  }, [taskKey]);
  /** Load run and New run like this change the page's task themselves, with their run (record 7.270): the link gives way while
   *  their task loads, and is given back if it did not load - unless another task was chosen meanwhile. */
  const followTask = (key: string) => {
    const before = followedTask.current;
    followedTask.current = key;
    return (loaded: boolean) => { if (!loaded && followedTask.current === key) followedTask.current = before; };
  };
  return { taskKey, loadSerial, followTask };
}
