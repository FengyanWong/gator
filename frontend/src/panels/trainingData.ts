/** The Training tab's numbers in the browser (record 7.193): what the backend sends (training_series.py), kept per run,
 *  and turned into chart series. No React, and no imports but its own parts in training/ (plan-refactoring C12), named with
 *  their .ts suffix (tsconfig allowImportingTsExtensions), so that frontend/scripts/training_data_check.mjs can run these
 *  files under Node as they are (Node strips the types) and check the arithmetic on fixtures. The parts: store.ts (what the
 *  backend sends, kept per run), series.ts (series maths), prep.ts (the shared chart preparation), catalog.ts (chart types
 *  and the charts a run offers), build.ts (one run's chart), compare.ts (several runs on one chart), keys.ts (key numbers).
 *
 *  What is kept: every recorded row, in commit order - evaluations (x = their number in recorded order, 1-based) and
 *  learner updates (x = the learner's cumulative update count, or - "Learner by evaluation", record 7.213 - the number of
 *  evaluations collected when the update ran, the evaluation charts' x). A missing or invalid value is NaN here and a gap (null)
 *  in a chart, never a zero. The journal's tail (bundles no flush has published yet) is the provisional end of the
 *  tables: cursor pages extend it; a new flush replaces it, so no bundle is counted twice.
 *
 *  Memory is bounded: past EVALUATION_CAP / UPDATE_CAP rows the oldest half of a table is thinned - in each bin of rows
 *  only the rows holding a column's smallest or largest value (and the bin's first and last row) stay, so every row kept
 *  is a recorded one. With more independent extremes than available row slots, the bound takes precedence. The page
 *  says when it thins history; the run's tables keep every row.
 *
 *  What the charts derive from the rows (record 7.221, performance plan A: each run's categories, pass flags, learner
 *  restarts, the rows in the order of a chart's x, running means) is worked out once per run and brought up to date as
 *  rows arrive, then shared by all its charts and its key numbers; a chart takes only the rows in view. The values drawn
 *  are the same numbers as before: see "shared chart preparation" in training/prep.ts. */

export { categoryOf, CATEGORY_LABEL, DESIGN_STATUSES, EVALUATION_CAP, UPDATE_CAP, setCaps, Changes, Table, UPDATE_NUMBERS, TrainingStore } from './training/store.ts';
export type { Coded, Columns, SpecDef, Chunk, Segment, Answer, Category, Context } from './training/store.ts';
export { updateBranches, smooth, smoothOver, decimate, visibleRows } from './training/series.ts';
export { passFlags, rowCategories, catalog } from './training/catalog.ts';
export type { Axis, ChartSpec, Series, Marker, Built } from './training/catalog.ts';
export { setSpacing, preparedSize } from './training/prep.ts';
export { build, viewRange } from './training/build.ts';
export type { View, LearnerX } from './training/build.ts';
export { COMPARE_MAX, buildCompare } from './training/compare.ts';
export type { CompareRun } from './training/compare.ts';
export { RECENT, ENDS, keyNumbers } from './training/keys.ts';
export type { KeyNumbers } from './training/keys.ts';
