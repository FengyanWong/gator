/** Icon-only buttons (user request 2026-09-24, in two steps: icons next to the words, then "remove the text"): the
 *  header's Save now / Start-Pause-Resume / Abort, "Save task" (now Save as) in the editors' tab line, the editors' Add /
 *  Delete selected / Undo / Redo, and the Tasks window's Delete task. Branch records SIF-112 to SIF-114 (the icon audit):
 *  the blocking issues' Hide and the calibration line's Close, Refresh list in the Runs, Tasks and RL model windows,
 *  Running now's and the Virtuoso window's Refresh, and the CIW lines' Copy. One action, one drawing (SIF-113, SIF-115):
 *  Delete task draws the bin of Delete folder and Delete selected, and the Corner check's Check, which starts simulations,
 *  the play mark of Start. Each icon is a 16 x 16 stroke drawing in the button's own colour (currentColor).
 *
 *  The label is still there, only not on screen: `<Icon name label />` puts it in a visually hidden span, so a screen
 *  reader names the button, and the button's textContent stays exactly its label ("Pause", "Save now", "Delete task",
 *  ...), which the page checks under scripts/ read and compare. A sighted user gets the label from the tooltip: every
 *  icon-only button's title starts with its label. */

export type IconName = 'save' | 'play' | 'pause' | 'wait' | 'stop' | 'force-stop' | 'task' | 'add' | 'delete' | 'undo' | 'redo' | 'export' | 'import' | 'task-file'
  | 'refresh' | 'download' | 'csv' | 'zip' | 'copy' | 'check' | 'close' | 'windows' | 'folder' | 'new-folder' | 'rename' | 'follow' | 'zoom-reset';

const DRAWINGS: Record<IconName, JSX.Element> = {
  // A floppy disk: the model is written to disk while the run goes on.
  save: <><path d="M3 2.5h8l2.5 2.5v8.5H3z" /><path d="M5 2.5v3.5h5V2.5" /><rect x="5" y="9" width="6" height="4.5" /></>,
  // Start, Resume, Continue... (and its form's Continue) and the Corner check's Check: a play triangle, simulations start.
  play: <path d="M4.5 2.5l8 5.5-8 5.5z" fill="currentColor" />,
  // Pause: two bars.
  pause: <><rect x="3.5" y="2.5" width="3.2" height="11" fill="currentColor" /><rect x="9.3" y="2.5" width="3.2" height="11" fill="currentColor" /></>,
  // Starting... / Pausing... / Resuming... / Aborting... / Finishing..., Reading..., Exporting..., Deleting... and a download
  // being made: an hourglass, the request is on its way.
  wait: <><path d="M4 2.5h8M4 13.5h8" /><path d="M5 2.5c0 3 6 4 6 5.5s-6 2.5-6 5.5M11 2.5c0 3-6 4-6 5.5s6 2.5 6 5.5" /></>,
  // Abort and the Corner check's Stop: a stop square.
  stop: <rect x="3" y="3" width="10" height="10" rx="1" fill="currentColor" />,
  // Force abort: the stop square struck through, it does not wait.
  'force-stop': <><rect x="3" y="3" width="10" height="10" rx="1" /><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" /></>,
  // Open windows (record 7.372, the banner's Windows list): two windows, one in front of the other.
  windows: <><rect x="2" y="5" width="9.5" height="8.5" rx="1" /><path d="M5 5V2.5h9V11h-2.5" /></>,
  // Save as (the task's tab line, and its rough-frequency question): a document with a check mark, the rows saved as a
  // new task.
  task: <><path d="M4 1.5h5.5L13 5v9.5H4z" /><path d="M9.5 1.5V5H13" /><path d="M6 10l2 2 3.5-3.5" /></>,
  // Add, Add chart (Training) and Add to Parameters (the Virtuoso window's sizes): a plus, one more row or chart.
  add: <path d="M8 3v10M3 8h10" strokeWidth="1.8" />,
  // Delete selected, Delete folder, Delete task: a waste bin, what is chosen goes.
  delete: <><path d="M3 4.5h10M6.5 4.5V3h3v1.5" /><path d="M4.5 4.5l.7 9h5.6l.7-9" /><path d="M6.8 7v4.5M9.2 7v4.5" /></>,
  // Undo / Redo: an arrow curling back, and its mirror.
  undo: <><path d="M5.5 4.5H2.5v-3" /><path d="M2.6 4.4a5.5 5.5 0 1 1-1 5" /></>,
  redo: <><path d="M10.5 4.5h3v-3" /><path d="M13.4 4.4a5.5 5.5 0 1 0 1 5" /></>,
  // Export JSON and Export status (JSON): an arrow up out of a tray, the rows or the status leave as a file.
  export: <><path d="M8 9.5V2" /><path d="M5 5l3-3 3 3" /><path d="M2.5 10v3.5h11V10" /></>,
  // Import JSON...: an arrow into a document, a file's rows come in.
  import: <><path d="M8 1.5h2.5L13 4v10.5H4V10" /><path d="M10.5 1.5V4H13" /><path d="M1.5 7h7M6.5 4.5L9 7l-2.5 2.5" /></>,
  // Task file: a document with lines, the task as one readable file.
  'task-file': <><path d="M4 1.5h5.5L13 5v9.5H4z" /><path d="M9.5 1.5V5H13" /><path d="M6 8.5h4.5M6 11h4.5" /></>,
  // Refresh / Refresh list: an arrow around, read again.
  refresh: <><path d="M13 8A5 5 0 1 1 11.6 4.5" /><path d="M13.5 1.5v3.2h-3.2" /></>,
  // Download ...: an arrow down onto a line, a file comes to this computer.
  download: <><path d="M8 2v8" /><path d="M5 7l3 3 3-3" /><path d="M2.5 13.5h11" /></>,
  // Export detailed CSV: a table.
  csv: <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M2 6.5h12M2 9.5h12M6 6.5v6.5M10 6.5v6.5" /></>,
  // Export research CSVs (one zip): an archive box.
  zip: <><rect x="2" y="2.5" width="12" height="11" rx="1" /><path d="M2 5.5h12" /><path d="M6.5 5.5v2h3v2h-3v2h3" /></>,
  // Copy run path, Copy for Excel, the CIW lines' Copy: two sheets, one over the other.
  copy: <><rect x="5.5" y="5.5" width="8" height="8" rx="1" /><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" /></>,
  // Copied (the Connection window's CIW lines, for 1.5 s): a check mark, the copy is done. Nothing that starts work draws
  // it: the Corner check's Check, which did, draws the play mark since branch record SIF-115.
  check: <path d="M3 8.5l3.2 3.2L13 4.5" strokeWidth="1.8" />,
  // Close / Hide / Remove (Training's ×) / Let go (a paused run in the header): this goes away, nothing else changes.
  close: <path d="M4 4l8 8M12 4l-8 8" strokeWidth="1.8" />,
  // Folders (record 7.170): a folder, in the circle where the connection window's steps have their number.
  folder: <path d="M1.5 3.5h4.5l1.5 2h7v8h-13z" />,
  // Create a folder: a folder with a plus inside.
  'new-folder': <><path d="M1.5 3.5h4.5l1.5 2h7v8h-13z" /><path d="M8 7.5v4M6 9.5h4" /></>,
  // Rename (a folder, in the Runs, Tasks and RL model windows): a pencil.
  rename: <><path d="M3 10.5l7.5-7.5 2.5 2.5L5.5 13 2 14z" /><path d="M9 4.5L11.5 7" /></>,
  // Follow latest (Training tab, record 7.193): an arrow running to an end line, the charts keep the newest results in view.
  follow: <><path d="M2 8h9" /><path d="M8 5l3 3-3 3" /><path d="M14 3v10" /></>,
  // Reset zoom (Training): four corners opening out, the whole run again.
  'zoom-reset': <><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" /><path d="M5.5 8h5" /></>,
};

/** `label`: the button's words, kept for screen readers and for the page checks but not drawn (`.sr-only`). */
export function Icon({ name, label }: { name: IconName; label?: string }) {
  return (<>
    <svg className="icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{DRAWINGS[name]}</svg>
    {label !== undefined && <span className="sr-only">{label}</span>}
  </>);
}
