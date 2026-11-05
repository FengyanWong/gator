// The right column's Run configuration panel (the workbench's first build; split by panel in plan-refactoring C4): it
// holds useRlModel and draws Run configuration, its reward and conditions, and the RL model window.
import { memo } from 'react';
import type { Json } from '../api';
import { Module } from './fields';
import { PopupPortal } from './popupParts';
import { RewardConditions } from './RewardConditions';
import { deferredPanel } from './deferredPanel';
import type { NextModel } from './rlModelText';
import { RunConfiguration } from './RunConfiguration';
import { useRlModel } from './useRlModel';

const RlModelWindow = deferredPanel(() => import('./RlModelWindow').then(m => m.RlModelWindow), 'RL model');

/** Run configuration and its RL model window (plan-refactoring C4): useRlModel holds the state and the work and stays mounted
 *  with this panel - the state lives on while the window is closed -; RunConfiguration, RewardConditions and RlModelWindow draw it. */
function RunPanelBody(props: { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; refreshRuns: () => Promise<Json[]>; circuit: Json; schema: Json;
  onNext?: (next: NextModel) => void; runHeld?: boolean; undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean }) {
  const m = useRlModel(props);
  const { undo, redo, canUndo, canRedo } = props;
  return (
    <>
    <Module id="run" title="Run configuration" summary={m.folded}>
      <RunConfiguration m={m} runHeld={!!props.runHeld} />
      <RewardConditions m={m} />
    </Module>
    <PopupPortal popup={m.networkWindow.popup} root={m.networkWindow.root}><RlModelWindow m={m} undo={undo} redo={redo} canUndo={canUndo} canRedo={canRedo} /></PopupPortal>
    </>
  );
}

/** Memoised (record 7.275): its props change with the configuration, the run list and the circuit - not with the status
 *  polled every 1.5 s while a run works, which drew this whole panel (and the RL model window it holds) at every update.
 *  `runHeld` (branch record SIF-72) is a flag that changes only when the header's run starts or comes to rest; the page's
 *  `undo` and `redo` are stable, and `canUndo` / `canRedo` change with the configuration (branch record SIF-97); so is the
 *  page's `refreshRuns`, which a saved model's rename calls (branch record SIF-102). */
export const RunPanel = memo(RunPanelBody);
