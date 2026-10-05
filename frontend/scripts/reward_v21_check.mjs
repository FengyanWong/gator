// Hermetic source-preview acceptance for reward v2.1. Explicit scratch URL required; no physical calls.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { openNetworks } from './lib/rl_networks.mjs';
import { launchEdge, workbenchUrl, PAGE_OPEN_TEST, validConfiguration, sleep } from './lib/harness.mjs';
const url = await workbenchUrl({ writes: true });
if (new URL(url).port !== '5191') throw new Error('Reward v2.1 check requires scratch port 5191');
const fixture = JSON.parse(readFileSync(new URL('./fixtures/reward_v21.json',import.meta.url),'utf8'));
const output = process.argv[2];
if (!output) throw new Error('An explicit evidence directory is required');
mkdirSync(output,{recursive:true});
const checks=[], requests=[], errors=[], refused=[];
const check = (name, pass, detail) => { checks.push({name,passed:!!pass,detail}); if(!pass) throw new Error(name); };
const label = name => `Array.from(${name === 'Alpha learning rate' ? "window.__checkRLWindow.document" : 'document'}.querySelectorAll('${name === 'Alpha learning rate' ? '.rl-networks-panel' : 'aside.right'} label')).find(e=>e.textContent.startsWith(${JSON.stringify(name)}))`;
const control = (name,type='select') => `(${label(name)})?.querySelector('${type}')`;
const cell = (index,field) => `(() => {const table=document.querySelector('table.editor');const i=Array.from(table.tHead.rows[0].cells).findIndex(c=>c.dataset.field===${JSON.stringify(field)});return table.tBodies[0].rows[${index}].cells[i]?.querySelector('input,select')})()`;
let browser,page,canCorners=true;
try {
 const sample = await (await fetch(new URL('/api/circuit/load',url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit:{source:'registered_task',task_id:'synthetic:gpdk045_ota5'}})})).json();
 const status = await (await fetch(new URL('/api/runs/status?run_dir='+encodeURIComponent(fixture.run_dir),url))).json();
 check('scratch API computes steering from fixture tables', Math.abs(status.steering.reward_spread-.0392)<1e-12 && Math.abs(status.steering.exploration_bonus-.3)<1e-12,status.steering);
 browser=await launchEdge('reward-v21',{width:1680,height:1050});page=await browser.open({errors});
 await page.send('Network.enable');page.on('Network.requestWillBeSent',p=>requests.push({url:p.request.url,method:p.request.method}));
 await page.intercept(['*/api/*'], params=>{
  const {requestId,request}=params,name=new URL(request.url).pathname;
  if(name==='/api/connection/check'||name==='/api/connection/status') return page.fulfil(requestId,200,PAGE_OPEN_TEST(null));
  if(name==='/api/config/validate') return page.fulfil(requestId,200,validConfiguration({mock:false}));
  if(name==='/api/circuit/load') return page.fulfil(requestId,200,{...sample,loaded:true,task_key:'real:gpdk045_ota7',mock:true,evaluation_backend:'SYNTHETIC UI FIXTURE: no simulation',training_capabilities:{corners:canCorners},notes:['SYNTHETIC UI FIXTURE']});
  if(name==='/api/runs/default-model') return page.fulfil(requestId,200,{run_dir:null,checkpoint_id:'latest'});
  if(name==='/api/runs/models') return page.fulfil(requestId,200,{models:[]});
  if(request.method==='GET') return page.pass(requestId);
  refused.push(request.method+' '+name);return page.refuse(requestId);
 });
 await page.seed({config:fixture.config,run:fixture.run_dir,when:'once'});
 await page.send('Page.navigate',{url});
 check('source page and backend corner capability load',await page.until(`${control('Training conditions')}?.querySelector('option[value=after_nominal]')?.disabled===false`,200));
 check('three training choices',await page.evaluate(`Array.from((${control('Training conditions')}).options).map(o=>o.text).join('|')==='Nominal only|Corners after nominal passes|Every planned corner'`));
 await page.setValue(control('Training conditions'),'after_nominal');
 check('gated cost and band shown',await page.until("document.querySelector('.reward-costs').textContent.includes('1 per design that fails nominal, 1 + 4 per design that passes')"));
 check('nominal gate band 0.5',await page.evaluate(`${control('Nominal gate band','input')}.value==='0.5'`));
 await page.setValue(control('Objective shape'),'compressed');
 await page.setValue(control('Nominal gate band','input'),'0.4');await sleep(950);
 check('new reward controls persist', (await page.stored()).run.reward.objective_shape==='compressed' && (await page.stored()).run.reward.nominal_gate_band===.4);
 await page.evaluate("Array.from(document.querySelectorAll('.editors .tabs button')).find(b=>b.textContent.startsWith('Specs')).click()",true);
 check('new columns initially hidden',await page.evaluate("!document.querySelector('th[data-field=missing_is_failure]') && !document.querySelector('th[data-field=margin_sides]')"));
 check('saved empty scale remains empty on load',await page.evaluate(`${cell(0,'normalization_scale')}.value===''`));
 check('zero-floor margin hint',await page.evaluate("document.querySelector('.zero-floor-hint').textContent==='The margin also measures the distance to 0. If 0 is only a physical floor, choose Margin sides: upper.'"));
 await page.evaluate("Array.from(document.querySelectorAll('.editors button')).find(b=>b.textContent.startsWith('More columns')).click()",true);
 check('new optional labels',await page.evaluate("document.querySelector('th[data-field=missing_is_failure]').textContent==='Missing value = failed' && document.querySelector('th[data-field=margin_sides]').textContent==='Margin sides'"));
 await page.evaluate(`${cell(0,'missing_is_failure')}.click()`,true);await page.setValue(cell(0,'margin_sides'),'upper');
 await page.setValue(cell(0,'lower'),'54');await sleep(950);
 let saved=await page.stored();check('flags persist and editing dB limit proposes 3',saved.targets[0].missing_is_failure===true && saved.targets[0].margin_sides==='upper' && saved.targets[0].normalization_scale===3);
 // A suggestion runs only on an explicit edit, while the scale is empty or still the untouched suggestion.
 for (const [unit,constraint,lower,upper,tolerance,expected] of [
  ['deg','>=',30,null,0,10],['V','target',null,null,.2,.2],['V','interval',2,6,0,2],['V','>=',8,null,0,8]]) {
  await page.setValue(cell(0,'unit'),'');await page.setValue(cell(0,'constraint'),constraint);
  await page.setValue(cell(0,'lower'),lower==null?'':String(lower));await page.setValue(cell(0,'upper'),upper==null?'':String(upper));
  await page.setValue(cell(0,'tolerance'),String(tolerance));await page.setValue(cell(0,'normalization_scale'),'');await page.setValue(cell(0,'unit'),unit);await sleep(850);
  check(`scale suggestion ${unit}/${constraint}`, (await page.stored()).targets[0].normalization_scale===expected);
 }
 await page.setValue(cell(0,'normalization_scale'),'7');await page.setValue(cell(0,'lower'),'9');await sleep(850);
 check('explicit scale is retained',(await page.stored()).targets[0].normalization_scale===7);
 await page.evaluate("document.querySelector('.editors button[title^=\"Add:\"]').click()",true);await sleep(850);
 check('new spec receives editable scale',(await page.stored()).targets.at(-1).normalization_scale!=null);
 // Record 7.112: a new row's suggestion must follow the limits typed AFTER it was added, not freeze the bare 1 (1 W).
 const last=(await page.stored()).targets.length-1, scaleOf=async()=>(await page.stored()).targets[last].normalization_scale;
 await page.setValue(cell(last,'unit'),'W');await sleep(850);
 check('new row switched to W without limits stays empty',(await scaleOf())===null);
 await page.setValue(cell(last,'constraint'),'<=');await page.setValue(cell(last,'upper'),'3.24e-6');await sleep(850);
 check('typed upper limit sizes the new row (3.24e-6 W, not 1 W)',(await scaleOf())===3.24e-6);
 await page.setValue(cell(last,'upper'),'5e-6');await sleep(850);
 check('untouched suggestion follows the next limit edit',(await scaleOf())===5e-6);
 await page.setValue(cell(last,'normalization_scale'),'1e-6');await page.setValue(cell(last,'upper'),'4e-6');await sleep(850);
 check('scale typed by the user stays after a limit edit',(await scaleOf())===1e-6);
 await openNetworks(page, browser);
 await page.evaluate("Array.from(window.__checkRLWindow.document.querySelectorAll('.rl-networks-panel details')).find(d=>d.querySelector('summary')?.textContent.startsWith('Advanced')).open=true",true);
 check('alpha rate starts empty',await page.evaluate(`${control('Alpha learning rate','input')}.value===''`));
 await page.setValue(control('Alpha learning rate','input'),'0.003');await sleep(850);check('alpha field accepts independent rate',(await page.stored()).run.advanced.alpha_learning_rate===.003);
 await page.setValue(control('Alpha learning rate','input'),'');await sleep(850);check('alpha field returns to inherited rate',(await page.stored()).run.advanced.alpha_learning_rate===null);
 for(const name of ['Run status','Data tables']) {
  await page.evaluate(`Array.from(document.querySelectorAll('footer .tabs button')).find(b=>b.textContent===${JSON.stringify(name)}).click()`,true);
  check(`${name} steering values and verdict`,await page.until("document.querySelector('footer .steering-check')?.textContent.includes('0.0392') && document.querySelector('footer .steering-check')?.textContent.includes('0.3') && document.querySelector('footer .steering-check')?.textContent.includes('The network is still choosing close to random:')",150));
 }
 await page.shot(path.join(output,'reward-v21.png'));
 await page.evaluate("document.querySelector('.reward-costs').scrollIntoView({block:'center'});document.querySelector('th[data-field=missing_is_failure]').scrollIntoView({block:'nearest',inline:'center'})",true);
 await page.shot(path.join(output,'reward-v21-controls.png'));
 canCorners=false;await page.send('Page.reload',{ignoreCache:true});
 // Since record 7.182 a circuit without corners offers no Training conditions choice at all (it was Nominal only, the others greyed)
 check('backend capability takes the corner choice away even for the OTA7 id',await page.until(`!${control('Training conditions')} && !document.querySelector('.reward-costs')`,150));
 // A genuinely new browser configuration uses B7; loading the saved fixture above retained its explicit fields.
 await page.evaluate("localStorage.removeItem('gator-workbench-config-v1')",true);await page.send('Page.reload',{ignoreCache:true});
 check('new configuration starts compressed/share 0.5',await page.until(`${control('Violation shape')}?.value==='compressed' && ${control('Worst hard-spec share','input')}?.value==='0.5'`,150));
 check('no 8765 request',requests.every(r=>new URL(r.url).port!=='8765'));
 check('no action route requested',requests.every(r=>! /\/api\/(runs\/(start|continue|command|corner-check\/start)|virtuoso\/|connection\/connect|agent\/chat)/.test(r.url)));
 check('no JS errors',errors.length===0,errors);
} catch(error) {
 if(page){await page.shot(path.join(output,'failure.png'));writeFileSync(path.join(output,'failure.txt'),await page.evaluate('document.body.innerText'));}
 throw error;
} finally {
 if(browser)await browser.close();
 writeFileSync(path.join(output,'browser-report.json'),JSON.stringify({passed:checks.length>=25&&checks.every(c=>c.passed),origin:'synthetic UI fixtures',source:'Vite current source, no build',checks,requests,refused,errors,physical_calls:0},null,2));
}
