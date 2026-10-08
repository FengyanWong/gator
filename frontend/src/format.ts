// Small text helpers that several windows carried a copy of each (record 7.276): a run folder's own name, and the page's
// times. One place, so the Runs, Tasks and RL model windows, the run brief and the messages cannot drift apart.

/** A run folder's own name, unique per run: the last part of its path. */
export const folderName = (dir: string) => dir.split(/[\\/]/).filter(Boolean).pop() ?? dir;
/** The same for a file name made from it (an export): "run" when the path has no name. */
export const runName = (runDir: string) => runDir.split(/[\\/]/).filter(Boolean).pop() ?? 'run';
/** Two digits: 7 -> "07". */
export const two = (n: number) => String(n).padStart(2, '0');
/** Local time, in a form that sorts and compares by eye: 2026-09-21 14:03:22. */
export const stamp = (utc?: string | null) => {
  const d = utc ? new Date(utc) : null;
  return d && !Number.isNaN(d.getTime()) ? `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}` : null;
};
/** The time now, as a window says when it last read: 14:03:22. */
export const clock = () => new Date().toLocaleTimeString([], { hour12: false });
