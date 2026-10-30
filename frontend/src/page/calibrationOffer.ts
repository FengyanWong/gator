// "Calibration ready" (record 7.204, user: "build the prompt when the run finishes"): when the header's Calibration run that has
// ended with proposals the page does not hold yet, a line under the header says so, with Apply calibration and Not now - so
// the proposals cannot be missed in Run status. Still the user's press: nothing is applied by itself. The run whose line was
// answered is kept in this browser (CALIBRATION_ANSWERED_KEY), so a reload does not ask again. Out of App.tsx's Page
// (plan-refactoring C5).
import { useEffect, useRef, useState } from 'react';
import type { Json } from '../api';
import { CALIBRATION_ANSWERED_KEY } from '../contract';
import { keep, readKept } from '../kept';
import { calibrationPlan, savingText } from '../panels/calibrationPlan';
import { requestTaskSave } from '../panels/TaskSave';
import type { RunControl } from '../runState';

export function useCalibrationOffer({ control, config, setConfig, setMessage }: { control: RunControl; config: Json;
  setConfig: (next: Json | ((c: Json) => Json), record?: boolean) => void; setMessage: (message: Json | ((now: Json) => Json)) => void }) {
  // The header's run at rest, its calibration result, and what Apply would do with the rows the page holds now.
  const [calibrationAnswered, setCalibrationAnswered] = useState<string | null>(() => readKept(s => s.getItem(CALIBRATION_ANSWERED_KEY), () => null));
  const calibrated: Json = control.phase === 'idle' && control.dir && control.dir !== calibrationAnswered ? control.status?.calibration?.result ?? null : null;
  const calibrationOffer = calibrated ? calibrationPlan(calibrated, config) : null;
  const calibrationReady = !!calibrationOffer && !calibrationOffer.otherTask && (calibrated.status !== 'calibrated' || calibrationOffer.pending > 0);
  // The message of an answer that asks for an Undo - Apply only, a save that could not start - with the result it applied.
  // It goes once the page no longer holds that result's values, as Run status's words do (review of branch record SIF-138):
  // after the Undo it asks for, "The Scale stays applied ... press Undo" was untrue, and a second Undo would take back an
  // earlier edit. A newer message stays.
  const askedUndo = useRef<{ message: Json; result: Json } | null>(null);
  useEffect(() => {
    const asked = askedUndo.current;
    if (!asked || !calibrationPlan(asked.result, config).pending) return;
    askedUndo.current = null;
    setMessage((now: Json) => (now === asked.message ? null : now));
  }, [config]);
  // 'save' (record 7.217, a task saved from a Virtuoso cell): Apply, then Save task as a press on it - asked in the same
  // click, sent with the rows of the next render (TaskSave.tsx), so the page is not left differing from its saved task.
  const answerCalibration = (how: 'save' | 'apply' | 'no') => {
    const dir = control.dir;
    if (!dir || !calibrationOffer) return;
    if (how !== 'no') setConfig(calibrationOffer.apply);
    // How this task is updated once the page holds the Scale (branch record SIF-138), with the place of Apply and save: the
    // line goes with any answer. Said after Apply only (`saves`), not after Apply calibration, which writes no Scale that
    // a save of this task would need.
    const where = ' under Run status of that run';
    const asked = how === 'save' ? requestTaskSave(config.circuit.task_id) : null;
    const after = asked ? savingText(asked, where) : calibrationOffer.saves ? calibrationOffer.afterApplied(where) : '';
    setCalibrationAnswered(dir);
    keep(s => s.setItem(CALIBRATION_ANSWERED_KEY, dir));   // a private window: asked again after a reload
    if (calibrated.status !== 'calibrated') return;
    const message = { level: 'info', text: how !== 'no' ? `Calibration applied: ${calibrationOffer.what}, as one Undo step.${after}`
      // "its Apply buttons" (branch record SIF-48): for a task saved from a cell, Run status offers Apply and save / Apply only.
      : 'Nothing was changed. The proposals stay under Run status of that run, with its Apply buttons.' };
    setMessage(message);
    askedUndo.current = (asked ? !asked.taken : how === 'apply' && calibrationOffer.saves) ? { message, result: calibrated } : null;
  };
  return { calibrated, calibrationOffer, calibrationReady, answerCalibration };
}
