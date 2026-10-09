import { memo } from 'react';
import { createPortal } from 'react-dom';
import type { Json } from '../api';
import { Module } from './fields';
import { RewardConditions } from './RewardConditions';
import { RlModelWindow } from './RlModelWindow';
import type { NextModel } from './rlModelText';
import { RunConfiguration } from './RunConfiguration';
import { useRlModel } from './useRlModel';

/** Run configuration and its RL model window (plan-refactoring C4): useRlModel holds the state and the work and stays mounted
 *  with this panel - the state lives on while the window is closed -; RunConfiguration, RewardConditions and RlModelWindow draw it. */
function RunPanelBody(props: { config: Json; setConfig: (f: (c: Json) => Json, record?: boolean) => void; runs: Json[]; circuit: Json; schema: Json;
  onNext?: (next: NextModel) => void }) {
  const m = useRlModel(props);
  return (
    <>
    <Module id="run" title="Run configuration" summary={m.folded}>
      <RunConfiguration m={m} />
      <RewardConditions m={m} />
    </Module>
    {m.networkWindow.popup && m.networkWindow.root && createPortal(<RlModelWindow m={m} />, m.networkWindow.root)}
    </>
  );
}

/** Memoised (record 7.275): its props change with the configuration, the run list and the circuit - not with the status
 *  polled every 1.5 s while a run works, which drew this whole panel (and the RL model window it holds) at every update. */
export const RunPanel = memo(RunPanelBody);
