// Real saved MOCK models on an isolated backend: architecture restoration, structure and attention inspection.
// Requires GATOR_WORKBENCH_URL and GATOR_WORKBENCH_OUTPUT_ROOT pointing to scratch fixtures with both new encoders.
import { NETWORK_DOCUMENT, NETWORK_PANEL, openNetworks } from './lib/rl_networks.mjs';
import { check, launchEdge, mockStarter, NEVER_ASKED_OR_SAVED, reportRefused, runChecks, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl();
const ROOT = process.env.GATOR_WORKBENCH_OUTPUT_ROOT;
if (!process.env.GATOR_WORKBENCH_URL || new URL(APP).port === '8765' || !ROOT) throw new Error('Use a scratch backend and output root.');
const { models } = await (await fetch(new URL(`api/runs/models?output_root=${encodeURIComponent(ROOT)}`, APP))).json();
const starter = await mockStarter(APP);
const browser = await launchEdge('encoder-models');

await runChecks(browser, async () => {
  const page = await browser.open();
  const refused = [];
  await page.intercept(['*/api/*'], params => page.readOrRefuse(params, refused, { reads: true }));
  for (const encoder of ['graph_gps', 'group_cross_attention', 'circuit_gps']) {
    const model = models.find(m => m.network?.encoder_type === encoder);
    if (!model) throw new Error(`Missing saved MOCK ${encoder} fixture`);
    // A new CircuitGPS model is architecture version 2: the measurement tree normalized at every level (record 7.341).
    check(`${encoder}: model chooser metadata carries the structural option and version`, model.mock
      && model.network.structural_encoding === 'rwse' && model.network.architecture_version === (encoder === 'circuit_gps' ? 2 : 1));
    const config = { ...starter, output: { ...starter.output, output_root: ROOT }, run: { ...starter.run, mode: 'fine_tune',
      network: { encoder_type: 'graph_transformer', hidden_dim: 32, heads: 4, layers: 2, structural_encoding: 'none' },
      model_source: { run_dir: model.run_dir, checkpoint_id: 'latest' } } };
    await page.seed({ config });
    await page.send('Page.navigate', { url: APP });
    await openNetworks(page, browser);
    const stored = `JSON.parse(localStorage.getItem('gator-workbench-config-v1')).run.network`;
    check(`${encoder}: selecting the saved model restores its complete architecture`, await page.until(`(() => { const n = ${stored};
      return n.encoder_type === '${encoder}' && n.hidden_dim === 16 && n.heads === 2 && n.layers === 1 && n.structural_encoding === 'rwse'; })()`, 120));
    if (encoder === 'circuit_gps') check('saved CircuitGPS restores the structured spec contract', await page.until(`(${stored}).spec_input === 'structured'`));
    check(`${encoder}: loaded architecture is not editable as a new network`, await page.evaluate(`!${NETWORK_PANEL}.querySelector('select.structural-encoding')`));
    // Since record 7.265 the structure and the graph view are in the saved model's Details, in the RL model window's table.
    const ROW = `[...${NETWORK_PANEL}.querySelectorAll('tr.model-row')].find(r => r.title === ${JSON.stringify(model.run_dir)})`;
    check(`${encoder}: the saved model is a row of the saved models table`, await page.until(`!!(${ROW})`, 300));
    await page.evaluate(`(${ROW}).querySelector('button.notes-link').click()`);
    const structure = `${NETWORK_PANEL}.querySelector('details.structure')`;
    await page.until(`!!${structure}`, 100);
    await page.evaluate(`${structure}.querySelector('summary').click()`);
    check(`${encoder}: saved layers are displayed`, await page.until(`!!${structure}.querySelector('table.structure-sections')`, 100));
    const graph = `${NETWORK_DOCUMENT}.querySelector('dialog.graph-dialog')`;
    await page.evaluate(`${NETWORK_PANEL}.querySelector('button.graph-open').click()`);
    const scope = encoder === 'graph_gps' ? 'global' : 'group';
    check(`${encoder}: actual saved policy supplies its attention scope`, await page.until(`!!${graph}.querySelector('.graph-canvas')?.__cy && !!${graph}.querySelector('select.graph-scope option[value="${scope}"]')`, 120));
    await page.setValue(`${graph}.querySelector('select.graph-scope')`, scope);
    check(`${encoder}: node weights are shown for the actual circuit`, await page.until(`${graph}.querySelectorAll('table.graph-node-attention tbody tr').length > 0`, 60));
    await page.evaluate(`${graph}.querySelector('button.dialog-close').click()`);
  }
  reportRefused(refused, NEVER_ASKED_OR_SAVED);
  check('no console exceptions', !page.consoleErrors.length, page.consoleErrors.join('\n'));
});
