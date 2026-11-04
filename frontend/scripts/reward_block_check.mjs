// Browser check of the reward as the page states it since record 7.183 (2026-10-05): one sentence for the set of values a
// new configuration starts with - since record 7.372 folded behind one line, "Reward: the tested one - <objective>" - the
// controls in a closed "Advanced" fold, a configuration with other values told how many and which (folded) and offered the
// tested set on a button; the soft actor-critic values with which the search stays random named in the RL
// model window, which Run configuration's notice opens at that warning (branch record SIF-86), and "Use the template's values" (the starting preset) taking them away; the Specs scale headed "Scale"
// behind "More columns" and suggested as the size of the limit (6 dB for dB). The warning's numbers plain, as the page writes
// numbers under 10,000 (branch record SIF-117).
// Hermetic: reads go to the scratch backend, every writing request but validation is refused, and a network-settings
// write is held here (none is expected: there is no GATOR baseline to press since record 7.191).
// Run (Windows node through WSL interop):
//   "/mnt/c/Program Files/nodejs/node.exe" "$(wslpath -w frontend/scripts/reward_block_check.mjs)" [screenshot-dir]
import path from 'node:path';
import { NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';
import { check, launchEdge, outDir, runChecks, sleep, starterConfig, workbenchUrl, RL_MODEL_WINDOW } from './lib/harness.mjs';

const APP = await workbenchUrl();
const out = outDir();
const browser = await launchEdge('reward-block');

await runChecks(browser, async () => {
  const page = await browser.open();
  const { send, evaluate, consoleErrors, paused } = page;
  const settings = await (await fetch(new URL('api/network-settings', APP))).json();
  const starter = await starterConfig(APP);
  const RIGHT = `document.querySelector('aside.right')`;
  const label = name => `[...document.querySelectorAll('aside.right label')].find(e => e.textContent.startsWith(${JSON.stringify(name)}))`;
  const control = (name, type = 'input') => `(${label(name)})?.querySelector(${JSON.stringify(type)})`;
  // one selector each, so that a page still loading answers null instead of throwing
  const SENTENCE = `document.querySelector('aside.right .reward-sentence')`, OTHER = `document.querySelector('aside.right .reward-other')`,
    FOLD = `document.querySelector('aside.right details.reward-advanced')`;
  const values = () => evaluate(`[${control('Violation shape', 'select')}?.value, ${control('Worst hard-spec share')}?.value, ${control('Objective bonus weight')}?.value,
    ${control('Objective shape', 'select')}?.value, ${control('Tightest-margin bonus weight')}?.value]`);
  const SIMPLE = ['compressed', '0.5', '1', 'compressed', '1'];

  await page.trackSaves();
  await page.hold(['*/api/network-settings/*'], null, { others: 'read' });       // a network-settings write waits here; other writes are refused
  await send('Page.navigate', { url: APP });

  // ---- a new configuration: the tested set, in one sentence ----------------------------------------------------------------
  check('a new configuration shows the reward as one sentence', await page.until(`${SENTENCE}?.textContent.startsWith('Reward: minus half the average miss, minus half the worst miss.')`, 150),
    await evaluate(`${RIGHT}?.textContent.slice(0, 300)`));
  check('...which says what a passing design earns, and that no objective row is marked',
    await evaluate(`${SENTENCE}.textContent.includes('up to +1 for the room it leaves on its tightest row') && ${SENTENCE}.textContent.endsWith('(none is marked in Specs).')`), await evaluate(`${SENTENCE}.textContent`));
  check('...folded behind one line that names it the tested one and says the objective (record 7.372)', await evaluate(`(() => { const d = ${SENTENCE}.closest('details.reward-summary');
    return !!d && !d.open && d.querySelector('summary').textContent === 'Reward: the tested one - no objective in Specs'; })()`),
    await evaluate(`${SENTENCE}.closest('details')?.querySelector('summary')?.textContent ?? 'no fold'`));
  check('its five values are the tested set: compressed, share 0.5, objective 1 (compressed), margin 1', JSON.stringify(await values()) === JSON.stringify(SIMPLE), JSON.stringify(await values()));
  check('the controls are in a closed "Advanced" fold and nothing is flagged', await evaluate(`${FOLD}.open === false && ${FOLD}.querySelector('summary').textContent.trim() === 'Advanced' && !${OTHER}
    && !${RIGHT}.querySelector('.module-body .warn, .module-body .error')?.closest('.reward-advanced')`));
  check('no warning line about a bonus without an objective row', !(await evaluate(`${RIGHT}.textContent.includes('No active objective')`)));
  // a new configuration takes its training values from the backend's setting for the encoder: nothing to review, also while they load
  check('a new configuration is not sent to RL model (record 7.265: the line beside it names the new model\'s template)', await page.until(`/^New model · .+ template · GT \\d+\\/\\d+\\/\\d+/.test(document.querySelector('.rl-networks-row .net-short')?.textContent ?? '')`)
    && !(await evaluate(`[...${RIGHT}.querySelectorAll('.warn')].some(e => e.textContent.startsWith('Review the settings in RL model'))`)));
  await page.shot(path.join(out, 'reward-1-sentence.png'), `${SENTENCE}.closest('.module-body')`, { maxHeight: 900 });

  // ---- another value: named, with the way back on a button ---------------------------------------------------------------
  await page.setValue(control('Worst hard-spec share'), '0');
  check('a changed value replaces the sentence by what differs', await page.until(`${OTHER}?.textContent.includes('worst hard-spec share 0 instead of 0.5') && !${SENTENCE}`),
    await evaluate(`${OTHER}?.textContent`));
  check('the fold says how many values are not as tested', await evaluate(`${FOLD}.querySelector('summary').textContent.includes('1 not as tested')`));
  check('...and so does one line, which values folded under it (record 7.372)', await evaluate(`${OTHER}.querySelector('.reward-other-count')?.textContent === 'Reward: 1 setting not as tested.'
    && !!${OTHER}.querySelector('details') && !${OTHER}.querySelector('details').open`), await evaluate(`${OTHER}?.textContent.slice(0, 160)`));
  await page.shot(path.join(out, 'reward-2-other.png'), `${OTHER}.closest('.module-body')`, { maxHeight: 900 });
  await evaluate(`${RIGHT}.querySelector('button.reward-simple').click()`, true);
  check('"Use the tested reward" brings the sentence and the value back', await page.until(`!!${SENTENCE} && ${control('Worst hard-spec share')}?.value === '0.5'`));
  await page.saved();
  const saved = (await page.stored())?.run?.reward ?? {};
  check('the saved configuration holds the five tested values', saved.violation_shape === 'compressed' && saved.worst_spec_share === 0.5 && saved.objective_weight === 1
    && saved.objective_shape === 'compressed' && saved.margin_weight === 1, JSON.stringify(saved));

  // ---- a configuration saved before: nothing is changed by itself; an objective row is named ------------------------------------
  const old = { schema_version: 'gator-workbench-config-v1', ...starter,
    run: { ...(starter.run ?? {}), mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, reward: { violation_shape: 'capped' },
      advanced: { ...settings.legacy_baseline.advanced }, network: { encoder_type: 'graph_transformer', ...settings.legacy_baseline.network } },
    targets: starter.targets.map((t, i) => i === 0 ? { ...t, constraint: '>=', direction_after_feasible: 'maximize' } : t) };
  await page.seed({ config: old, when: 'once' });
  await evaluate(`sessionStorage.removeItem('fixture-seeded')`);
  await send('Page.reload');
  check('an older configuration is told all five differences', await page.until(`['violation shape capped instead of compressed', 'worst hard-spec share 0 instead of 0.5',
    'objective bonus weight 0 instead of 1', 'objective shape clipped instead of compressed', 'tightest-margin bonus weight 0 instead of 1'].every(t => ${OTHER}?.textContent.includes(t))`, 150),
    await evaluate(`${OTHER}?.textContent`));
  await page.saved();
  check('...and is not changed by itself', JSON.stringify((await page.stored())?.run?.reward) === JSON.stringify({ violation_shape: 'capped' }), JSON.stringify((await page.stored())?.run?.reward));
  await evaluate(`${RIGHT}.querySelector('button.reward-simple').click()`, true);
  const objective = `maximize ${old.targets[0].metric_id}`;
  check('with the tested reward, the sentence names the row marked as the objective', await page.until(`${SENTENCE}?.textContent.includes(${JSON.stringify('(' + objective + ').')})`),
    await evaluate(`${SENTENCE}?.textContent`));
  check('the fold keeps the objective line', await evaluate(`${FOLD}.querySelector('.reward-objective').textContent === ${JSON.stringify('Objective: ' + objective)}`));

  // ---- the soft actor-critic values of before: named where they are set, gone with the template's values -----------------------
  // branch record SIF-46: the notice says why, and its "RL model..." is the way to the window
  const REVIEW = `${RIGHT}.querySelector('p.network-review')`;
  check('Run configuration points at RL model, and says why', await page.until(`${REVIEW}?.classList.contains('warn') && ${REVIEW}.textContent
    === 'Review the settings in RL model... - with 1 update per evaluation and a starting temperature of 0.2, the network learned late or not at all in tests.'`),
    await evaluate(`${REVIEW}?.textContent ?? 'no notice'`));
  const networkPage = await openNetworks(page, browser, 'p.network-review button.text-link');
  const SLOW = `${NETWORK_PANEL}.querySelector('.sac-values')`;
  // branch record SIF-57: the tested values with the labels of the fields under Advanced, which carry other names
  check('the window names 1 update per evaluation and the starting temperature 0.2, and the tested values with their fields\' labels',
    await page.until(`${SLOW}?.textContent.startsWith('With 1 update per evaluation and a starting temperature of 0.2, soft actor-critic learned late or not at all')
      && ${SLOW}.textContent.endsWith('The tested values are 8 updates per evaluation (Updates per transition), starting temperature 0.01 (Initial alpha) and discount 0 (Discount gamma), under Advanced.')`),
    await evaluate(`${SLOW}?.textContent`));
  // Branch record SIF-117: its numbers as the page writes numbers under 10,000, plain (it read "1,500 evaluations" and
  // "evaluation 1,000" beside the facts' counts)
  check('... its numbers plain: "a uniform random search for 1500 evaluations", "about evaluation 1000" (SIF-117)',
    await page.until(`${SLOW}?.textContent.includes('stayed a uniform random search for 1500 evaluations,') && ${SLOW}.textContent.includes('learning to about evaluation 1000.')
      && !/\\d,\\d{3}/.test(${SLOW}.textContent)`), await evaluate(`${SLOW}?.textContent`));
  // Branch record SIF-86: the notice's link opened the window at its top, the warning further down, under the templates.
  const SLOW_AT = `(() => { const r = (${SLOW})?.getBoundingClientRect(), w = window.__checkRLWindow;
    return { window: Math.round(w.scrollY), top: r ? Math.round(r.top) : null, bottom: r ? Math.round(r.bottom) : null, height: w.innerHeight }; })()`;
  check('... and the notice\'s "RL model..." opened the window at that warning: scrolled to it, in view (SIF-86)',
    await page.until(`(() => { const at = ${SLOW_AT}; return at.window > 0 && at.top !== null && at.top >= 0 && at.bottom <= at.height; })()`, 40), JSON.stringify(await evaluate(SLOW_AT)));
  check('no GATOR baseline button and no word of it (record 7.191)', !(await evaluate(`${NETWORK_PANEL}.textContent.includes('GATOR baseline')
    || [...${NETWORK_PANEL}.querySelectorAll('button')].some(b => ['GATOR baseline', 'Publication preset'].includes(b.textContent.trim()))`)));
  await networkPage.shot(path.join(out, 'reward-3-sac-values.png'), NETWORK_PANEL, { maxHeight: 1100, beyond: true });
  const held = settings.settings.graph_transformer.advanced;                  // the starting preset on a scratch backend
  check('the default encoder\'s saved setting learns: 8 updates per evaluation, temperature 0.01 (the old schema values 1 and 0.2)',
    held.updates_per_transition === 8 && held.initial_alpha === 0.01 && settings.legacy_baseline.advanced.updates_per_transition === 1, JSON.stringify(held));
  await evaluate(`[...${NETWORK_PANEL}.querySelectorAll('.network-differences button')].find(b => b.textContent === "Use the template's values").click()`);
  check('with "Use the template\'s values" the warning is gone, here and in Run configuration', await page.until(`!${SLOW} && ![...${RIGHT}.querySelectorAll('.warn')].some(e => e.textContent.startsWith('Review the settings in RL model'))`),
    await evaluate(`${SLOW}?.textContent ?? ''`) + ' | ' + await evaluate(`${REVIEW}?.textContent ?? 'no notice'`));
  await page.saved();
  const advanced = (await page.stored())?.run?.advanced ?? {};
  check('the configuration now runs the saved setting\'s 8 updates per evaluation and temperature 0.01, and nothing was written', advanced.updates_per_transition === 8
    && advanced.initial_alpha === 0.01 && advanced.gamma === held.gamma && paused.length === 0, JSON.stringify(advanced));
  await networkPage.evaluate('setTimeout(() => window.close(), 0)');
  await browser.window(RL_MODEL_WINDOW, { present: false });

  // ---- Specs: the scale behind "More columns", headed "Scale", suggested as the size of the limit --------------------------
  const EDITORS = `document.querySelector('.editors')`;
  const CELL = (row, name) => `(() => { const at = [...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).indexOf(${JSON.stringify(name)});
    return ${EDITORS}.querySelectorAll('table.editor tbody tr')[${row}].children[at].querySelector('input, select'); })()`;
  const type = (row, name, v) => page.setValue(CELL(row, name), v, { event: 'input' });
  const scaleOf = async row => { await page.saved(); return (await page.stored()).targets[row].normalization_scale; };
  await evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith('Specs')).click()`);
  await page.until(`${EDITORS}.querySelectorAll('table.editor tbody tr').length === ${old.targets.length}`);
  const heads = () => evaluate(`[...${EDITORS}.querySelectorAll('table.editor thead th')].map(h => h.dataset.field).filter(Boolean)`);
  check('Specs shows neither hard nor the scale until "More columns"', !(await heads()).includes('hard') && !(await heads()).includes('normalization_scale'), JSON.stringify(await heads()));
  await evaluate(`[...${EDITORS}.querySelectorAll('.toolbar button')].find(b => /^More columns/.test(b.textContent.trim())).click()`);
  check('after it both are there, the scale headed "Scale"', await page.until(`${EDITORS}.querySelector('th[data-field="normalization_scale"]')?.textContent.trim() === 'Scale'
    && !!${EDITORS}.querySelector('th[data-field="hard"]')`), JSON.stringify(await heads()));
  // Specs have no Unit column since record 7.208: a Spec takes its Probe's unit, so the unit is set on the Probe (a list).
  check('Specs show no Unit column (record 7.208)', !(await heads()).includes('unit'), JSON.stringify(await heads()));
  const openTab = name => evaluate(`[...${EDITORS}.querySelectorAll('.tabs button')].find(b => b.textContent.trim().startsWith('${name}')).click()`);
  const probeUnit = async unit => { await openTab('Probes'); await page.until(`!!(${CELL(0, 'unit')})`);
    await page.setValue(CELL(0, 'unit'), unit, { event: 'change' }); await sleep(200); await openTab('Specs'); await page.until(`!!(${CELL(0, 'lower')})`); };
  await openTab('Probes'); await page.until(`!!(${CELL(0, 'unit')})`);
  check('the Probes\' Unit is a list like the page\'s others, in English letters', await evaluate(`(() => { const s = ${CELL(0, 'unit')};
    const o = [...s.options].map(x => x.value); return s.tagName === 'SELECT' && ['V', 'A', 'Hz', 'dB', 'deg', 'ohm'].every(u => o.includes(u)) && !o.some(u => /[µμΩ°]/.test(u)); })()`));
  await openTab('Specs'); await page.until(`!!(${CELL(0, 'lower')})`);
  // row 0: a dB row that still holds the suggestion of before (3): the next limit edit takes it to today's (6)
  await probeUnit('dB');
  await page.saved();                                       // the page stores 0.8 s after the last change
  check('a Spec on a Probe set to dB takes dB', (await page.stored()).targets[0].unit === 'dB', (await page.stored()).targets[0].unit);
  await type(0, 'normalization_scale', '3'); await type(0, 'lower', '40');
  check('a dB row still holding the old suggestion of 3 follows the next limit edit to 6', (await scaleOf(0)) === 6, String(await scaleOf(0)));
  await probeUnit('deg'); await type(0, 'lower', '60');
  check('a phase row is sized by its limit (60), no longer by 10 degrees', (await scaleOf(0)) === 60, String(await scaleOf(0)));
  await page.setValue(CELL(0, 'constraint'), 'interval|none'); await type(0, 'lower', '45'); await type(0, 'upper', '55');
  check('an interval is sized by its larger bound (55), no longer by half its width', (await scaleOf(0)) === 55, String(await scaleOf(0)));
  await type(0, 'normalization_scale', '7'); await type(0, 'upper', '58');
  check('a scale the user typed stays after a limit edit', (await scaleOf(0)) === 7, String(await scaleOf(0)));

  console.log(`INFO  other writing requests the page sent on its own, all refused here: ${[...new Set(page.refused)].join(', ') || 'none'}`);
  check('no console errors', consoleErrors.length === 0, consoleErrors.join(' | ').slice(0, 300));
});
