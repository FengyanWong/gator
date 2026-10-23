// The names the page and its browser checks share (plan-refactoring C2): the keys under which the page keeps things in the
// browser, the titles of its pop-up windows and the ids the checks find elements by. Import-free and plain: the checks' harness
// (frontend/scripts/lib/harness.mjs) imports this file as it is, under Node's type stripping, as unit_text_check.mjs imports
// units.ts - so a name changed here reaches every check, and a name taken away fails them when they load instead of silently.

// ---- kept in this browser: localStorage, unless said otherwise ----------------------------------------------------------------
/** The page's configuration, kept 0.8 s after each change (store.ts). */
export const CONFIG_KEY = 'gator-workbench-config-v1';
/** The run the header's buttons act on (runState.ts); App.tsx reads it too. */
export const HEADER_RUN_KEY = 'gator-workbench-current-run-v1';
/** The run the bottom tabs show, with the header's run of that moment (App.tsx, record 7.212). */
export const SHOWN_RUN_KEY = 'gator-workbench-shown-run-v1';
/** The launch on its way, kept in THIS TAB (sessionStorage) until it is answered (launch.ts, record 7.261). */
export const LAUNCH_KEY = 'gator-workbench-launch-v1';
/** The run whose "Calibration ready" line was answered (App.tsx, record 7.204). */
export const CALIBRATION_ANSWERED_KEY = 'gator-workbench-calibration-answered-v1';
/** The bottom panel's height and fold (App.tsx, record 7.158). */
export const BOTTOM_KEY = 'gator-workbench-bottom-v1';
/** The bottom panel's tab, kept in THIS TAB (sessionStorage): a reload comes back on it (BottomPanel.tsx useBottomTab,
 *  branch record SIF-105). */
export const BOTTOM_TAB_KEY = 'gator-workbench-bottom-tab-v1';
/** A right-column module folded or open: this prefix + the module's id (Right.tsx Module). */
export const MODULE_KEY_PREFIX = 'gator-workbench-module-';
/** A pop-up window's size and place as the viewer left it: this prefix + the window's name (popupWindow.ts, branch record
 *  SIF-110). */
export const WINDOW_PLACE_KEY_PREFIX = 'gator-workbench-window-';
/** The circuit picture's fold in the circuit column (CircuitPicture.tsx). */
export const CIRCUIT_PICTURE_KEY = 'gator-workbench-circuit-picture-v1';
/** The circuit column shown beside the task's rows (App.tsx, record 7.362): 'shown', or nothing - folded away, the default. */
export const CIRCUIT_SHOWN_KEY = 'gator-workbench-circuit-shown-v1';
/** The Training tab's runs compared with the shown one (TrainingTab.tsx, record 7.200). */
export const TRAINING_COMPARE_KEY = 'gator-workbench-training-compare-v1';
/** Lower caps of the Training tab's memory bound, set only by a browser check (TrainingTab.tsx, trainingData.ts setCaps). */
export const TRAINING_CAPS_KEY = 'gator-workbench-training-caps-v1';
/** The starting preset's learning rate was checked once in this browser (Right.tsx, record 7.199). */
export const PRESET_RATE_KEY = 'gator-workbench-preset-rate-2026-10-05';

// ---- the pop-up windows' titles (popupWindow.ts: the checks find each window by its title) --------------------------------
export const RUNS_WINDOW = 'GATOR - runs';
export const RL_MODEL_WINDOW = 'GATOR - RL model';
export const VIRTUOSO_WINDOW = 'GATOR - Virtuoso cell';
export const CONNECTION_WINDOW = 'GATOR - connection';
export const AGENT_WINDOW = 'GATOR - agent';
export const NGSPICE_WINDOW = 'GATOR - ngspice netlist';
export const PDK_WINDOW = 'GATOR - PDK';
export const RUNNING_WINDOW = 'GATOR - running now';
export const TASKS_WINDOW = 'GATOR - tasks';

// ---- element ids ------------------------------------------------------------------------------------------------------------
/** The element the page is drawn into (index.html, main.tsx). */
export const APP_ROOT_ID = 'root';
/** The Output settings' output root box (Right.tsx). */
export const OUTPUT_ROOT_ID = 'output-root';
/** The header's list of blocking issues (Issues.tsx). */
export const BLOCKING_ISSUES_ID = 'blocking-issues';

// ---- validation -------------------------------------------------------------------------------------------------------------
/** The issue levels that stop a start: the header's button counts these, and so does the Start and Calibration tooltip
 *  (launch.ts) - it counted errors alone, so with a blocker it named a number the button did not (branch record SIF-45). */
export const BLOCKING_LEVELS = ['error', 'blocker'];
