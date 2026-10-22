// Vite source preview: StrictMode must replay updaters, unlike the production-only checks.
import { check, launchEdge, runChecks, sleep, workbenchUrl } from './lib/harness.mjs';

const base = await workbenchUrl();
const browser = await launchEdge('edit-state');
await runChecks(browser, async () => {
  const page = await browser.open();
  await page.intercept(['*/api/*'], p => page.refuse(p.requestId));
  const go = async kind => {
    await page.send('Page.navigate', { url: new URL(`/scripts/fixtures/edit_state.html?case=${kind}`, base).href });
    if (!await page.until('!!window.fixture?.state')) throw new Error('This check needs a Vite source preview.');
  };
  const expect = async (name, expression) => check(name, await page.until(expression), JSON.stringify(await page.evaluate('fixture.state')));
  const edit = async name => { await page.evaluate(`fixture.edit(${JSON.stringify(name)})`); await page.until(`fixture.state.name === ${JSON.stringify(name)}`); };
  await go('history');
  const original = await page.evaluate('fixture.state.name');
  for (const name of ['one', 'two', 'three']) await edit(name);
  for (const name of ['two', 'one', original]) {
    await page.evaluate('fixture.undo()');
    await expect(`StrictMode Undo restores ${name}`, `fixture.state.name === ${JSON.stringify(name)}`);
  }
  check('original history is exhausted exactly once', await page.evaluate('!fixture.state.canUndo && fixture.state.canRedo'));
  for (const name of ['one', 'two', 'three']) {
    await page.evaluate('fixture.redo()');
    await expect(`StrictMode Redo restores ${name}`, `fixture.state.name === ${JSON.stringify(name)}`);
  }
  check('redo history is exhausted exactly once', await page.evaluate('!fixture.state.canRedo'));
  // Branch record SIF-97: the history keeps its last move and the two configurations, for the editors' line to name.
  check('the last Redo is kept with the configurations it moved between (SIF-97)', await page.evaluate('fixture.state.step === "Redo two -> three"'), await page.evaluate('fixture.state.step'));
  await page.evaluate('fixture.redo()');
  check('...and a Redo with nothing to redo keeps it', await page.evaluate('fixture.state.step === "Redo two -> three" && fixture.state.name === "three"'), await page.evaluate('fixture.state.step'));
  await page.evaluate('fixture.undo()'); await page.until('fixture.state.name === "two"');
  check('...as is an Undo (SIF-97)', await page.evaluate('fixture.state.step === "Undo three -> two"'), await page.evaluate('fixture.state.step'));
  await edit('branch');
  check('an edit after Undo discards the abandoned future', await page.evaluate('!fixture.state.canRedo'));
  check('...and lets the last Undo go (SIF-97)', await page.evaluate('fixture.state.step === null'), await page.evaluate('fixture.state.step'));
  await page.evaluate('fixture.edit("batch1"); fixture.edit("batch2")'); await page.until('fixture.state.name === "batch2"');
  await page.evaluate('fixture.undo()'); await expect('batched edits retain the intermediate state', 'fixture.state.name === "batch1"');
  await page.evaluate('fixture.undo()'); await expect('batched edits retain the preceding state', 'fixture.state.name === "branch"');

  await go('history');
  await page.setValue('document.querySelector("#name")', 'typed one', { event: 'input' });
  await page.setValue('document.querySelector("#name")', 'typed two', { event: 'input' });
  await page.until('fixture.state.name === "typed two"');
  await page.evaluate('fixture.undo()');
  await expect('typing remains one Undo step under StrictMode', `fixture.state.name === ${JSON.stringify(original)} && !fixture.state.canUndo`);
  await page.evaluate('fixture.redo()'); await expect('Redo restores the whole typed value', 'fixture.state.name === "typed two"');

  await go('history');
  await page.evaluate('fixture.edit("loaded", false)');
  await expect('an unrecorded update does not create an Undo step', 'fixture.state.name === "loaded" && !fixture.state.canUndo');
  await edit('manual'); await page.evaluate('fixture.undo()');
  await expect('Undo returns to the unrecorded baseline', 'fixture.state.name === "loaded"');
  await go('history');
  await page.evaluate('for (let i = 1; i <= 110; i++) fixture.edit(String(i))');
  await page.until('fixture.state.name === "110"');
  await page.evaluate('for (let i = 0; i < 110; i++) fixture.undo()');
  await expect('history keeps exactly the latest 100 changes', 'fixture.state.name === "10" && !fixture.state.canUndo && fixture.state.canRedo');

  await go('task');
  const save = async () => {
    if (!await page.until('!!document.querySelector("#bar button.primary") && !document.querySelector("#bar button.primary").disabled')) throw new Error('Save task unavailable');
    const index = await page.evaluate('fixture.pending.length');
    await page.evaluate("window.dispatchEvent(new CustomEvent('gator-save-task-request', { detail: { task: fixture.state.task } }))");
    if (!await page.until(`fixture.pending.length === ${index + 1}`)) throw new Error('Save not sent');
    return index;
  };
  const finishSave = async (index, error = false) => {
    await page.evaluate(`fixture.finish(${index}, ${error})`);
    await page.until('!document.querySelector("#bar button.primary")?.disabled');
    await sleep(100);
  };
  let index = await save();
  await page.evaluate('fixture.edit("newer_edit")'); await page.until('fixture.state.parameter === "newer_edit"');
  await finishSave(index);
  check('a late save preserves edits made after its request', await page.evaluate('fixture.state.parameter === "newer_edit"'));
  check('the save explains that newer edits are not saved yet', await page.evaluate('document.querySelector("#notes").textContent.includes("Newer editor changes")'));
  index = await save(); await finishSave(index);
  check('an unchanged task still accepts normalized saved parameters', await page.evaluate('fixture.state.parameter === "normalized"'));

  index = await save();
  await page.evaluate('fixture.switchTask("bb")'); await page.until('fixture.state.loaded === "real:bb"');
  await finishSave(index);
  check('task B keeps its rows and circuit after task A saves', await page.evaluate('fixture.state.task === "real:bb" && fixture.state.parameter === "task_bb" && fixture.state.loaded === "real:bb"'));
  check('a stale save shows no success message on another task', await page.evaluate('!document.querySelector("#notes").textContent.includes("Saved")'));

  index = await save();
  await page.evaluate('fixture.switchTask("aa")'); await page.until('fixture.state.loaded === "real:aa"');
  await page.evaluate('fixture.switchTask("bb")'); await page.until('fixture.state.loaded === "real:bb"');
  await finishSave(index);
  check('switching away and back still invalidates the old save', await page.evaluate('fixture.state.parameter === "task_bb"'));
  index = await save();
  await page.evaluate('fixture.switchTask("aa")'); await page.until('fixture.state.loaded === "real:aa"');
  await finishSave(index, true);
  check('a stale save error is not shown on another task', await page.evaluate('!document.querySelector("#notes").textContent.includes("Fixture save failed")'));
  check('no browser exceptions', page.consoleErrors.length === 0, JSON.stringify(page.consoleErrors));
});
