// Source preview only, synthetic responses. All action routes are intercepted.
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import path from 'node:path';
import {launchEdge, workbenchUrl, PAGE_OPEN_TEST, validConfiguration, sleep} from './lib/harness.mjs';
const url = await workbenchUrl({writes:true});
if(new URL(url).port !== '5193') throw Error('Requires scratch source preview on 5193');
const out=process.argv[2]; if(!out) throw Error('Evidence directory required'); mkdirSync(out,{recursive:true});
const fixture=JSON.parse(readFileSync(new URL('../../artifacts/local/llm-sizing/browser-fixture/fixture.json',import.meta.url),'utf8'));
const checks=[],requests=[],errors=[]; let browser,page;
const check=(name,passed,detail)=>{checks.push({name,passed:!!passed,detail});if(!passed)throw Error(name);};
const control=(label,type='select')=>`Array.from(document.querySelectorAll('aside.right label')).find(e=>e.textContent.startsWith(${JSON.stringify(label)}))?.querySelector('${type}')`;
let active=true,hinted=false,search={method:'llm_warmstart',phase:'llm_warmup',admitted:2,warm_count:8,trained:0,initial_updates:8,pending:true,calls:1,max_calls:4,hints_available:true,hint_count:0,rounds:0,max_rounds:2,stalled:0,stall_window:8};
const runDir=fixture.run_dir;
try{
 const sample=await(await fetch(new URL('/api/circuit/load',url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit:{source:'registered_task',task_id:'synthetic:gpdk045_ota5'}})})).json();
 const originalStatus=await(await fetch(new URL('/api/runs/status?run_dir='+encodeURIComponent(runDir),url))).json();
 const agent=await(await fetch(new URL('/api/agent/settings',url))).json();
 browser=await launchEdge('llm-sizing',{width:1680,height:1050});page=await browser.open({errors});
 await page.send('Network.enable');page.on('Network.requestWillBeSent',p=>requests.push({url:p.request.url,method:p.request.method}));
 await page.intercept(['*/api/*'],({requestId,request})=>{
  const name=new URL(request.url).pathname;
  if(name==='/api/connection/check'||name==='/api/connection/status')return page.fulfil(requestId,200,PAGE_OPEN_TEST(null));
  if(name==='/api/config/validate')return page.fulfil(requestId,200,validConfiguration({mock:true}));
  if(name==='/api/circuit/load')return page.fulfil(requestId,200,sample);
  if(name==='/api/agent/settings')return page.fulfil(requestId,200,{...agent,provider:'codex',model:'gpt-6-astra',effort:'ultra'});
  if(name==='/api/runs/default-model')return page.fulfil(requestId,200,{run_dir:null,checkpoint_id:'latest'});
  if(name==='/api/runs/models')return page.fulfil(requestId,200,{models:[]});
  if(name==='/api/runs/status')return page.fulfil(requestId,200,{...originalStatus,run_dir:runDir,worker_alive:active,state:active?'running':'paused',search});
  if(name==='/api/runs/llm-thread')return page.fulfil(requestId,200,{state:active?'running':'paused',search,events:[{type:'call_started',call_id:'fixture'},{type:'thinking',call_id:'fixture',text:'Synthetic thinking summary'},{type:'reply',call_id:'fixture',output:{analysis:'Synthetic sizing reply',notes:[],candidates:[{values:{w:1e-6},rationale:'Explore bias'}]},accepted:1,rejected:[]},{type:'outcome',call_id:'fixture',evaluation_id:'fixture-e1',valid:true,feasible:false,reward:-.2}]});
  if(name==='/api/runs/llm-hint'){hinted=true;return page.fulfil(requestId,200,{ok:true});}
  if(request.method==='GET')return page.pass(requestId);
  return page.refuse(requestId);
 });
 const config={...fixture.config,run:{...fixture.config.run,mode:'scratch',search:{method:'sac'},model_source:{}}};
 await page.seed({config,run:runDir,when:'once'});await page.send('Page.navigate',{url});
 check('search choices come from backend schema',await page.until(`${control('Search method')}?.options.length===4`,200));
 check('exactly four labels',await page.evaluate(`Array.from(${control('Search method')}.options).map(o=>o.text).join('|')==='SAC|LLM warm start → SAC|LLM only|SAC with LLM rescue'`));
 for(const method of ['llm_warmstart','llm','sac_llm_rescue','sac']){
  await page.setValue(control('Search method'),method);await sleep(900);
  check(`${method} persists without renaming`,(await page.stored()).run.search.method===method);
 }
 await page.setValue(control('Search method'),'llm');await sleep(900);
 check('AI only hides frozen and fine tune modes',await page.evaluate(`Array.from(${control('Mode')}.options).map(o=>o.value).join('|')==='scratch|resume'`));
 check('AI only locks one lane',(await page.stored()).run.concurrency===1);
 check('AI only hides neural model output options',await page.evaluate(`!Array.from(document.querySelectorAll('aside.right label')).some(l=>['Learner-update log','Replay snapshots','Model checkpoints'].some(t=>l.textContent.startsWith(t)))`));
 check('AI only retains search progress save',await page.evaluate(`Array.from(document.querySelectorAll('aside.right label')).some(l=>l.textContent.startsWith('Search progress'))`));
 await page.setValue(control('Search method'),'llm_warmstart');await sleep(900);
 check('warmstart cannot choose frozen',await page.evaluate(`!Array.from(${control('Mode')}.options).some(o=>o.value==='frozen')`));
 check('warmstart has W and U caption',await page.evaluate(`document.querySelector('.search-handover').textContent.includes('training updates → SAC')`));
 check('more settings initially closed',await page.evaluate(`!Array.from(document.querySelectorAll('.search-settings details')).find(d=>d.querySelector('summary').textContent==='More settings').open`));
 await page.setValue(control('AI model'),'gpt-6-luna');
 check('Luna only offers its supported effort levels',await page.until(`!Array.from(${control('AI effort')}.options).some(o=>o.value==='ultra')`));
 check('unsupported inherited Ultra falls back to provider default',await page.evaluate(`${control('AI effort')}.options[0].text==='Provider default'`));
 await page.setValue(control('AI model'),'gpt-6-astra');
 check('Astra can inherit the Agent Ultra setting',await page.until(`${control('AI effort')}.options[0].text==='Same as the Agent tab (ultra)'`));
 await page.evaluate("Array.from(document.querySelectorAll('footer button')).find(b=>b.textContent==='Agent').click()",true);
 check('sizing thread loads persisted call and outcome',await page.until("document.querySelector('.sizing-thread')?.textContent.includes('Synthetic sizing reply') && document.querySelector('.sizing-thread')?.textContent.includes('specifications not met')",150));
 check('warmup progress matches status',await page.until("document.querySelector('.sizing-thread')?.textContent.includes('2 / 8')"));
 await page.setValue("document.querySelector('.sizing-thread textarea')",'Explore lower bias current');
 await page.evaluate("document.querySelector('.sizing-thread button').click()",true);await sleep(400);check('hint goes to run hint route',hinted);
 search={...search,phase:'initial_learning',admitted:8,trained:3,pending:false,hints_available:false};
 check('initial learning progress and hint cutoff',await page.until("document.querySelector('.sizing-thread')?.textContent.includes('3 / 8 updates') && document.querySelector('.sizing-thread textarea').disabled",150));
 search={...search,method:'sac_llm_rescue',phase:'search',pending:true,rounds:1,stalled:8,hints_available:true};
 check('rescue stays SAC with pending AI',await page.until("document.querySelector('.sizing-thread')?.textContent.includes('SAC search — AI suggestions pending')",150));
 check('rescue counters in details',await page.evaluate("document.querySelector('.sizing-thread').textContent.includes('Rescue rounds 1 / 2; evaluations without progress 8 / 8')"));
 await page.shot(path.join(out,'llm-rescue.png'));
 active=false;search={...search,pending:false,hints_available:false};await sleep(3200);
 const before=requests.filter(r=>r.url.includes('/api/runs/llm-thread')).length;await sleep(2400);
 check('AI thread stops polling inactive run',before===requests.filter(r=>r.url.includes('/api/runs/llm-thread')).length);
 await page.send('Page.reload',{ignoreCache:true});
 check('saved AI thread survives reload',await page.until("document.querySelector('.sizing-thread')?.textContent.includes('Synthetic sizing reply')",150));
 for(const tab of ['Run status','Data tables','Output files','Logs']){
  const exists=await page.evaluate(`Array.from(document.querySelectorAll('footer .tabs button')).some(b=>b.textContent===${JSON.stringify(tab)})`);
  if(exists){await page.evaluate(`Array.from(document.querySelectorAll('footer .tabs button')).find(b=>b.textContent===${JSON.stringify(tab)}).click()`,true);await sleep(400);check(`${tab} renders without policy access errors`,errors.length===0);}
 }
 check('no real provider or simulator action',requests.every(r=>! /\/api\/(runs\/(start|continue)|agent\/(chat|propose)|virtuoso\/|connection\/connect)/.test(r.url)));
 check('no live port',requests.every(r=>new URL(r.url).port!=='8765'));check('no JS errors',errors.length===0,errors);
}catch(e){if(page){await page.shot(path.join(out,'failure.png'));writeFileSync(path.join(out,'failure.txt'),await page.evaluate('document.body.innerText'));}throw e;}
finally{if(browser)await browser.close();writeFileSync(path.join(out,'browser-report.json'),JSON.stringify({passed:checks.length>20&&checks.every(c=>c.passed),checks,requests,errors,origin:'synthetic',paid_calls:0,physical_calls:0},null,2));}
