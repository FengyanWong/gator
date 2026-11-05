// Hermetic Agent interaction checks. All Agent operations are synthetic, all other writes refused.
// Use an isolated backend/build with GATOR_WORKBENCH_URL; never launches an LLM or simulator.
import path from 'node:path';
import { check, launchEdge, MOCK_PAGE_CONFIG, outDir, runChecks, sleep, validConfiguration, workbenchUrl } from './lib/harness.mjs';

const APP = await workbenchUrl(), out = outDir(), browser = await launchEdge('local-agent');
await runChecks(browser, async () => {
  const page = await browser.open(), { evaluate, until } = page;
  let installed = false, deployed = false, active = null, serial = 0, installFails = true, compatible = false;
  let chatMode = 'valid', heldReview = null, holdReview = false;
  const jobs = new Map(), operations = [], refused = [];
  const model = () => ({ id: 'fixture', name: 'NVIDIA fixture model', provider: 'NVIDIA', description: 'origin=synthetic, provenance=mock',
    source: 'https://huggingface.co/nvidia', size: 100, installed, deployed, storage: installed ? 'external' : null,
    error: null, runtime: 'Synthetic runtime fixture', vram_gib: 22, ram_gib: 28 });
  const start = (kind, result = null) => {
    const id = `fixture-${++serial}`;
    jobs.set(id, { id, kind, model_id: 'fixture', state: 'running', phase: 'Synthetic operation', bytes: 25, total: 100,
      output: '', offset: 0, error: null, result, polls: 0 }); active = id; return id;
  };
  await page.intercept(['*/api/*'], async params => {
    const { requestId, request } = params, url = new URL(request.url), name = url.pathname;
    const reply = (data, status = 200) => page.fulfil(requestId, status, data);
    if (name === '/api/config/validate') return reply(validConfiguration());
    if (name === '/api/local-agent') return reply({ models: [model()], active_job: active, deployed: deployed ? 'fixture' : null, default_model: null, mode: 'Loads per reply' });
    if (name.endsWith('/compatibility') && name.startsWith('/api/local-agent')) return reply({ compatible,
      errors: compatible ? [] : ['Not enough free VRAM (synthetic)'], local_asset_available: true, runtime_ready: true, disk_needed: 100,
      note: 'Actual deployment still required.', host: { disk_free: 100e9, ram_free: 10e9, ram_total: 32e9, gpus: [{ name: 'Synthetic GPU', free: 23e9, total: 24e9 }] } });
    if (name === '/api/local-agent/models/fixture') {
      const { action } = JSON.parse(request.postData); operations.push(action);
      if (action === 'install' || action === 'deploy') return reply({ job_id: start(action) });
      if (action === 'undeploy') {
        deployed = false;
        if (active) { jobs.get(active).state = 'cancelled'; active = null; }
        return reply({ deployed: false });
      }
      if (action === 'delete') { installed = false; return reply({ installed: false, external_file_preserved: true }); }
    }
    if (name === '/api/local-agent/chat') {
      const body = JSON.parse(request.postData), next = structuredClone(body.config); next.run.seed = 123;
      const preview = { config: next, changes: [{ path: 'run.seed', label: 'Run · seed', before: body.config.run.seed, after: 123, unit: null }], warnings: [] };
      const result = chatMode === 'invalid' ? { message: 'synthetic invalid suggestion', proposal: null, proposal_error: 'unknown field: command', omitted_messages: 0 }
        : { message: 'synthetic suggestion', proposal: { run: { seed: 123 } }, proposal_error: null, preview, omitted_messages: 2 };
      const id = start('chat', result); jobs.get(id).held = chatMode === 'held';
      return reply({ job_id: id });
    }
    if (name.startsWith('/api/local-agent/jobs/')) {
      const id = name.split('/')[4], job = jobs.get(id);
      if (name.endsWith('/review')) {
        if (holdReview) { heldReview = { requestId, job }; return; }
        return reply(job.result.preview);
      }
      if (name.endsWith('/cancel')) { job.state = 'cancelled'; active = null; return reply({ state: 'cancelled' }); }
      if (job.state === 'running' && ++job.polls > 2 && !job.held) {
        job.state = 'completed'; active = null;
        if (job.kind === 'install') {
          if (installFails) { job.state = 'failed'; job.error = 'Synthetic download checksum failure'; installFails = false; }
          else installed = true;
        }
        if (job.kind === 'deploy') deployed = true;
      }
      const raw = job.kind === 'chat' ? 'Synthetic live model output' : '';
      return reply({ ...job, output: raw.slice(Number(url.searchParams.get('offset') ?? 0)), offset: raw.length });
    }
    return page.readOrRefuse(params, refused, { reads: true });
  });
  await page.trackSaves();
  await page.seed({ config: MOCK_PAGE_CONFIG, run: null, when: 'once' });
  await page.send('Page.navigate', { url: APP });
  const panel = `document.querySelector('.agent-panel')`;
  const button = label => `[...${panel}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})`;
  const clickText = label => evaluate(`${button(label)}.click()`);
  const icon = prefix => `${panel}.querySelector('button[title^="${prefix}"]')`;
  const clickIcon = prefix => evaluate(`${icon(prefix)}.click()`);
  const has = text => `${panel}?.innerText.includes(${JSON.stringify(text)})`;
  if (!await until(`!![...document.querySelectorAll('footer .tabs button')].find(b => b.textContent === 'Agent')`, 120)) throw new Error('Agent tab missing');
  await evaluate(`[...document.querySelectorAll('footer .tabs button')].find(b => b.textContent === 'Agent').click()`);
  await until(has('Not installed'), 80);
  check('latest has no preinstalled model or chat composer', await evaluate(`${has('Not installed')} && !document.querySelector('#agent-message')`));
  check('icon controls have accessible names and titles', await evaluate(`[...${panel}.querySelectorAll('.agent-controls button')].every(b => b.title && b.textContent.trim())`));
  await clickIcon('Install'); await until(has('Not enough free VRAM'), 40);
  check('incompatible resources prevent installation request', operations.length === 0);
  compatible = true;
  await clickIcon('Install'); await until(has('checksum failure'), 80);
  check('failed download is visible and remains uninstalled', !installed && await evaluate(has('checksum failure')));
  await clickIcon('Install'); await until(has('Model installed.'), 80);
  check('installation progress leads to installed state', installed);
  await clickIcon('Deploy'); await until(`!!document.querySelector('#agent-message')`, 80);
  check('deployment enables interaction', deployed && await evaluate(has('Ready · loads per reply')));
  const send = async text => {
    await evaluate(`document.querySelector('#agent-message').focus()`);
    await page.send('Input.insertText', { text });
    await clickText('Send');
  };
  await send('Suggest a seed.'); await until(has('Proposed editor changes'), 80);
  check('suggestion is previewed without automatically editing', (await page.savedConfig()).run.seed === 0);
  check('context continuation is disclosed', await evaluate(has('2 older messages')));
  await clickText('Apply changes'); await sleep(1000);
  check('Apply uses the normal configuration editor', (await page.savedConfig()).run.seed === 123);
  await evaluate(`document.querySelector('button[title^="Undo:"]').click()`);
  check('one Undo restores the previous configuration', (await page.savedConfig()).run.seed === 0);
  await evaluate(`document.querySelector('button[title^="Redo:"]').click()`);
  check('Redo restores the proposed change', (await page.savedConfig()).run.seed === 123);
  await evaluate(`document.querySelector('button[title^="Undo:"]').click()`);
  chatMode = 'invalid'; await send('Propose something invalid.'); await until(has('unknown field: command'), 80);
  check('invalid model suggestions expose rejection', await evaluate(has('Suggestion rejected:')) && (await page.savedConfig()).run.seed === 0);
  chatMode = 'valid'; await send('Another suggestion.'); await until(`document.querySelectorAll('.agent-proposal').length === 2`, 80);
  await evaluate(`document.querySelector('button[title^="Redo:"]').click()`);
  check('editor changes invalidate old suggestions', await evaluate(`${has('Stale suggestion')} && [...document.querySelectorAll('.agent-proposal button')].every(b => b.disabled)`));
  await evaluate(`document.querySelector('button[title^="Undo:"]').click()`);
  check('undoing an edit does not revive stale suggestions', await evaluate(`[...document.querySelectorAll('.agent-proposal button')].every(b => b.disabled)`));
  // While server revalidation is pending, a separate editor action must win.
  await send('Race check.'); await until(`document.querySelectorAll('.agent-proposal').length === 3`, 80);
  holdReview = true;
  await evaluate(`[...document.querySelectorAll('.agent-proposal button')].at(-1).click()`);
  for (let i=0; i<40 && !heldReview; i++) await sleep(50);
  if (!heldReview) throw new Error('Apply did not reach review');
  await evaluate(`document.querySelector('button[title^="Redo:"]').click()`);
  await page.fulfil(heldReview.requestId, 200, heldReview.job.result.preview); holdReview = false;
  await until(has('editor changed during validation'), 40);
  check('edit during validation prevents application', await evaluate(has('No changes applied.')));
  chatMode = 'held'; await send('Long uncapped answer.'); await until(has('Synthetic operation'), 40);
  await until(`!!document.querySelector('.agent-live')`, 40);
  check('collapsed live output does not populate a hidden text node', await evaluate(`!document.querySelector('.agent-live pre')`));
  await evaluate(`document.querySelector('.agent-live summary').click()`);
  check('expanding live output shows the accumulated stream', await until(`document.querySelector('.agent-live pre')?.textContent === 'Synthetic live model output'`, 40));
  await evaluate(`document.querySelector('.agent-live summary').click()`);
  check('collapsing live output releases its rendered text', await until(`!document.querySelector('.agent-live pre')`, 40));
  await clickIcon('Cancel Agent operation'); await until(has('Operation cancelled.'), 80);
  check('cancellation stops the active job', active === null);
  const beforeNew = JSON.stringify(await page.savedConfig());
  await clickText('New conversation');
  check('new conversation clears prior messages and proposals without editing the configuration',
    await evaluate(`document.querySelectorAll('.agent-message, .agent-proposal, .agent-live').length === 0`)
      && JSON.stringify(await page.savedConfig()) === beforeNew);
  await clickIcon('Undeploy'); await until(has('Install and deploy a model'), 40);
  check('undeploy removes the composer', !deployed && await evaluate(`!document.querySelector('#agent-message')`));
  await clickIcon('Delete registration'); await until(has('external benchmark file was preserved'), 40);
  check('delete preserves external weights and returns to setup', !installed);
  await evaluate(`document.querySelector('.bottom-body').scrollTop = 0`);
  await page.shot(path.join(out, 'local-agent.png'));
  check('no simulator or unrelated writing API was invoked', !refused.some(p => /runs\/(start|continue)|bridge|agent\/open/.test(p)), refused.join(', '));
  check('no browser console errors', page.consoleErrors.length === 0, JSON.stringify(page.consoleErrors));
});
