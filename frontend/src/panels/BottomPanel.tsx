import { useCallback, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import type { Json } from '../api';
import type { TaskRunSummary } from '../contracts';
import { BOTTOM_KEY } from '../contract';
import { keep, readKept } from '../kept';
import type { Refusal, useLauncher } from '../launch';
import { AgentWindowTab } from './Agent';
import { CornerCheckTab } from './CornerCheck';
import { type RunChoice, RunListButton } from './RunList';
import { DataTab, FilesTab, LogsTab, StatusTab } from './RunTabs';
import { TrainingTab } from './TrainingTab';

// The bottom panel (plan-refactoring C5, out of App.tsx): its height and fold, kept in this browser, the splitter above it,
// its tab line and the tab it shows. The page holds the tab and the run shown; useBottomPanel holds the rest.

export type BottomTab = 'status' | 'logs' | 'data' | 'files' | 'training' | 'corners';
/** The bottom panel's height (record 7.158): dragged at its top edge, folded to its tab line with a double click there.
 *  Kept in this browser, like the folded modules; null = the default third of the window. */
type Bottom = { height: number | null; folded: boolean };
const storedBottom = (): Bottom => readKept(s => {
  const b = JSON.parse(s.getItem(BOTTOM_KEY) ?? 'null'); return { height: typeof b?.height === 'number' && b.height > 0 ? b.height : null, folded: b?.folded === true };
}, () => ({ height: null, folded: false }));

/** The bottom panel's height and fold, and the splitter's work. `runDir`: the run the panel shows - with none it stays folded
 *  until something asks to see it. `layoutRef`: the page's layout, whose height the splitter sets while it is dragged. */
export function useBottomPanel(runDir: string | null) {
  const [bottom, setBottom] = useState<Bottom>(storedBottom);
  // Folded while no run is shown (record 7.179, design advice 1): its tabs show a run, and with none it was a third of the page
  // saying "No run selected". A tab, the splitter, a started or a chosen run opens it; the kept height and fold stay.
  const [opened, setOpened] = useState(false);
  const folded = bottom.folded || (!runDir && !opened);
  const changeBottom = useCallback((change: (b: Bottom) => Bottom) => setBottom(b => {
    const next = change(b);
    if (next !== b) keep(s => s.setItem(BOTTOM_KEY, JSON.stringify(next)));   // a private window: not remembered
    return next;
  }), []);
  // A press that asks to see something in the bottom panel (one of its tabs, the header's run) opens it.
  const unfold = useCallback(() => { setOpened(true); changeBottom(b => (b.folded ? { ...b, folded: false } : b)); }, [changeBottom]);
  const toggleBottom = () => (folded ? unfold() : changeBottom(b => ({ ...b, folded: true })));
  // A cell entered while the table has little room (record 7.372, Editors.tsx onCramped): the panel folds to its tab line, and a
  // tab, the splitter or a run brings it back as before. Stable, for the memoised editors.
  const foldForRows = useCallback(() => changeBottom(b => (b.folded ? b : { ...b, folded: true })), [changeBottom]);

  // ---- the splitter above the bottom panel (record 7.158): nothing moves unless it is dragged, double-clicked or keyed --------
  const layoutRef = useRef<HTMLDivElement>(null);
  const fitBottom = (px: number) => {
    const tabs = layoutRef.current?.querySelector<HTMLElement>('footer > .tabs')?.offsetHeight ?? 34;
    return Math.round(Math.max(tabs + 60, Math.min(px, window.innerHeight - 280)));   // the editors keep room
  };
  const dragBottom = (e: ReactPointerEvent<HTMLDivElement>) => {
    const layout = layoutRef.current, foot = e.currentTarget.parentElement;
    if (e.button !== 0 || !layout || !foot) return;
    e.preventDefault();
    const handle = e.currentTarget, edge = foot.getBoundingClientRect().bottom;
    handle.setPointerCapture(e.pointerId);
    let height: number | null = null;          // drawn while dragged, remembered once let go
    const move = (m: PointerEvent) => { height = fitBottom(edge - m.clientY); layout.style.setProperty('--foot', `${height}px`); layout.classList.remove('bottom-folded'); };
    const end = () => {
      handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', end); handle.removeEventListener('pointercancel', end);
      const dragged = height;
      if (dragged !== null) { setOpened(true); changeBottom(() => ({ height: dragged, folded: false })); }
    };
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end);
  };
  const keyBottom = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleBottom(); return; }
    const step = e.key === 'ArrowUp' ? 24 : e.key === 'ArrowDown' ? -24 : 0;
    if (!step) return;
    e.preventDefault();
    const now = e.currentTarget.parentElement?.getBoundingClientRect().height ?? 0;
    setOpened(true); changeBottom(() => ({ height: fitBottom(now + step), folded: false }));
  };
  return { bottom, folded, unfold, toggleBottom, foldForRows, layoutRef, dragBottom, keyBottom };
}
export type BottomPanelState = ReturnType<typeof useBottomPanel>;
/** The Runs window's presses, as the page hands them to the Runs button (App.tsx: functions that stay the same). */
/** `load` and `newLike` answer whether they went through: the Runs window closes once a run is chosen (user request
 *  2026-10-09), and stays open when nothing changed, saying why (branch record SIF-84). `owner`: the Runs window, which asks
 *  the edits question. */
export type RunWindowActions = { choose: (dir: string | null) => void; load: (row: TaskRunSummary, owner?: Window | null) => Promise<RunChoice>;
  newLike: (row: TaskRunSummary, owner?: Window | null) => Promise<RunChoice>; continueFrom: (row: TaskRunSummary) => void };

/** The bottom panel: the splitter, the tab line (Agent..., the tabs, the run shown and Runs...) and the tab shown.
 *  `headerDir`: the header's run while it works or is paused, so the tab line can say when it shows another (branch record SIF-72). */
export function BottomPanel({ panel, tab, setTab, cornersUsable, config, setConfig, runs, runsError, runDir, status, statusError, runWindow, refreshRuns,
  shownCheck, continueBlocked, shownRefusal, continueShown, launcher, fineTuneFrom, askContinue, headerDir = null }: { panel: BottomPanelState; tab: BottomTab;
  setTab: (tab: BottomTab) => void; cornersUsable: boolean; config: Json; setConfig: (next: Json | ((c: Json) => Json)) => void; runs: Json[];
  runsError: string | null; runDir: string | null; status: Json; statusError: string | null; runWindow: RunWindowActions;
  refreshRuns: (fresh?: boolean) => Promise<Json[]>; shownCheck: Json | null; continueBlocked: string | null; shownRefusal: Refusal | null;
  continueShown: (total: number | null) => void; launcher: ReturnType<typeof useLauncher>; fineTuneFrom: (alternative: Json) => void;
  askContinue: { runDir: string; serial: number } | null; headerDir?: string | null }) {
  const { bottom, folded, unfold, toggleBottom, dragBottom, keyBottom } = panel;
  // A Continue... of the Runs window opens the budget form once (branch record SIF-90): Run status is drawn anew at each
  // return to its tab, and a request still standing opened the form again every time - after a Cancel, and for a run
  // that had been continued and was live by then. The panel stays mounted, so the last request answered is kept here.
  const askedContinue = useRef(0);
  return (
    <footer>
      <div className="splitter" role="separator" aria-orientation="horizontal" tabIndex={0} aria-label="Height of the bottom panel"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={folded ? 0 : bottom.height ? Math.min(100, Math.round(bottom.height / window.innerHeight * 100)) : 34}
        title="Drag to give the bottom panel more or less room. Double-click: fold it down to its tab line, or open it again. Kept in this browser."
        onPointerDown={dragBottom} onDoubleClick={toggleBottom} onKeyDown={keyBottom} />
      <div className="tabs">
        <AgentWindowTab config={config} />
        {(['status', 'logs', 'data', 'files', 'training', 'corners'] as BottomTab[]).filter(t => t !== 'corners' || cornersUsable).map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => { setTab(t); unfold(); }}>
          {{ status: 'Run status', logs: 'Logs', data: 'Data tables', files: 'Output files', training: 'Training', corners: 'Corner check' }[t]}</button>)}
        <span className="spacer" />
        <RunListButton runs={runs} runsError={runsError} runDir={runDir} shownState={status?.run_dir === runDir ? status?.state ?? null : null}
          onChoose={runWindow.choose} onRefresh={refreshRuns} onLoad={runWindow.load} onNewLike={runWindow.newLike} onContinue={runWindow.continueFrom} headerDir={headerDir} />
      </div>
      <div className="bottom-body">
        {tab === 'status' && <StatusTab status={status} runDir={runDir} error={statusError} check={shownCheck} continueBlocked={continueBlocked} refusal={shownRefusal}
          onContinue={continueShown} onDismissRefusal={() => launcher.setRefusal(null)} onFineTune={fineTuneFrom} config={config} setConfig={setConfig}
          ask={askContinue && askContinue.serial !== askedContinue.current ? askContinue : null} onAsked={serial => { askedContinue.current = serial; }} />}
        {tab === 'logs' && <LogsTab runDir={runDir} alive={!!status?.worker_alive} />}
        {tab === 'data' && <DataTab runDir={runDir} status={status} />}
        {/* whether the run's worker lives and its last save point: Output files reads a live run again at each save point
            (branch record SIF-99); null while the shown run's status is not read */}
        {tab === 'files' && <FilesTab runDir={runDir} alive={status?.run_dir === runDir ? !!status.worker_alive : null}
          savePoint={status?.run_dir === runDir ? status.last_checkpoint_utc ?? '' : null} />}
        {/* Stays mounted: its recorded numbers and chosen charts survive a look at another tab; hidden - another
            tab, or the panel folded to its tab line - it reads and draws nothing (record 7.193). */}
        <TrainingTab hidden={tab !== 'training' || folded} runDir={runDir} status={status} runs={runs} />
        {tab === 'corners' && cornersUsable && <CornerCheckTab runDir={runDir} />}
      </div>
    </footer>
  );
}
