// A live run nobody here holds is taken over when the page opens, and the run list follows the output root while it is typed
// (plan-refactoring C5, out of App.tsx's Page).
import { useEffect, useRef } from 'react';
import type { Json } from '../api';
import { folderName } from '../format';
import { launchKept } from '../launch';
import { isLive, RESUMABLE, type RunControl } from '../runState';

/** A run the header took over: said by a small badge beside the run chip (record 7.372; a line of its own under the header
 *  until then), its sentence in the badge's tooltip. */
export type Takeover = { dir: string; label: string; text: string };

/** `outputRoot`: the page's output root - the list is read again 1 s after it last changed. `setLooked`: said once the list was
 *  read, so the header knows whether a run is live. */
export function useLiveRunAdoption({ control, outputRoot, refreshRuns, setRunDir, setTakeover, setLooked }: { control: RunControl;
  outputRoot: string | null | undefined; refreshRuns: (fresh?: boolean) => Promise<Json[]>; setRunDir: (dir: string | null) => void;
  setTakeover: (takeover: Takeover | null) => void; setLooked: (looked: boolean) => void }) {
  const adopted = useRef(false);
  const controlNow = useRef(control);              // the header as it is when the list arrives (a launch recovered after a reload may hold one by then)
  controlNow.current = control;
  useEffect(() => {
    // The list follows the output root while it is typed: read 1 s after the last keystroke, not once per key (each read
    // looks at every run under the root; record 7.275). The first read, when the page opens, goes at once.
    const timer = setTimeout(() => refreshRuns().then(list => {
      // Once, when the page opens: a run that is live although this page does not hold it (started from another browser or
      // the CLI, or the browser's memory was cleared) is taken over, so the header offers Pause and Abort, not a second Start.
      if (adopted.current) return;
      adopted.current = true;
      const header = controlNow.current;
      const running = list.some(r => r.run_dir === header.dir && isLive(r)) ? null : list.find(isLive);
      if (running) {
        // Said (record 7.261), with the paused run the header held: it stays paused, and Runs continues it.
        const resting = list.find(r => r.run_dir === header.dir && RESUMABLE.includes(r.state));
        header.take(running.run_dir); setRunDir(running.run_dir);
        // A launch of this tab sent before a reload may have made it: the launcher says so once it has asked.
        const mine = launchKept();
        const where = mine ? 'a live run' : 'a live run started elsewhere (another browser tab, the command line or a task\'s baseline)';
        setTakeover({ dir: running.run_dir, label: mine ? 'recovered' : 'started elsewhere',
          text: `The header took over ${folderName(running.run_dir)}, ${where}: its Pause and Abort act on it.`
            + (resting ? ` ${folderName(resting.run_dir)} stays paused; continue it from Runs.` : '') });
      }
      setLooked(true);
    }), adopted.current ? 1000 : 0);
    return () => clearTimeout(timer);
  }, [outputRoot]);
}
