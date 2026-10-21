// "Calibration ready" (record 7.204, user: "build the prompt when the run finishes"): when the header's Calibration run that has
// ended with proposals the page does not hold yet, a line under the header says so, with Apply calibration and Not now - so
// the proposals cannot be missed in Run status. Still the user's press: nothing is applied by itself. The run whose line was
// answered is kept in this browser (CALIBRATION_ANSWERED_KEY), so a reload does not ask again. Out of App.tsx's Page
// (plan-refactoring C5).
import { useState } from 'react';
import type { Json } from '../api';
import { CALIBRATION_ANSWERED_KEY } from '../contract';
import { keep, readKept } from '../kept';
import { calibrationPlan, savingText } from '../panels/calibrationPlan';
import { requestTaskSave } from '../panels/TaskSave';
import type { RunControl } from '../runState';

export function useCalibrationOffer({ control, config, setConfig, setMessage }: { control: RunControl; config: Json;
  setConfig: (next: Json | ((c: Json) => Json), record?: boolean) => void; setMessage: (message: Json) => void }) {
  // The header's run at rest, its calibration result, and what Apply would do with the rows the page holds now.
  const [calibrationAnswered, setCalibrationAnswered] = useState<string | null>(() => readKept(s => s.getItem(CALIBRATION_ANSWERED_KEY), () => null));
  const calibrated: Json = control.phase === 'idle' && control.dir && control.dir !== calibrationAnswered ? control.status?.calibration?.result ?? null : null;
  const calibrationOffer = calibrated ? calibrationPlan(calibrated, config) : null;
  const calibrationReady = !!calibrationOffer && !calibrationOffer.otherTask && (calibrated.status !== 'calibrated' || calibrationOffer.pending > 0);
  // 'save' (record 7.217, a task saved from a Virtuoso cell): Apply, then Save task as a press on it - asked in the same
  // click, sent with the rows of the next render (TaskSave.tsx), so the page is not left differing from its saved task.
  const answerCalibration = (how: 'save' | 'apply' | 'no') => {
    const dir = control.dir;
    if (!dir || !calibrationOffer) return;
    if (how !== 'no') setConfig(calibrationOffer.apply);
    const after = how === 'save' ? savingText(requestTaskSave(config.circuit.task_id)) : calibrationOffer.afterwards;
    setCalibrationAnswered(dir);
    keep(s => s.setItem(CALIBRATION_ANSWERED_KEY, dir));   // a private window: asked again after a reload
    if (calibrated.status === 'calibrated') setMessage({ level: 'info', text: how !== 'no' ? `Calibration applied: ${calibrationOffer.what}, as one Undo step.${after}`
      // "its Apply buttons" (branch record SIF-48): for a task saved from a cell, Run status offers Apply and save / Apply only.
      : 'Nothing was changed. The proposals stay under Run status of that run, with its Apply buttons.' });
  };
  return { calibrated, calibrationOffer, calibrationReady, answerCalibration };
}
