// npm install --no-save playwright; node tests/browser.e2e.cjs
// Uses installed Google Chrome. Override PLAYWRIGHT_MODULE for a bundled runtime.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const port=Number(process.env.TEST_PORT||8766);
const base=`http://127.0.0.1:${port}`;
const db=path.join(root,'test-results',`e2e-${Date.now()}.db`);
const errors=[];
let server,browser,page;
async function start(){
  server=spawn(process.env.PYTHON||'python3',['run.py','--port',String(port),'--db',db],{cwd:root,env:{...process.env,AGENT_PROVIDER:'demo',AGENT_STEP_DELAY:'0.045'},stdio:['ignore','pipe','pipe']});
  let stderr='';server.stderr.on('data',d=>stderr+=d);
  for(let i=0;i<150;i++){try{if((await fetch(base+'/api/health')).ok)return}catch{}await new Promise(r=>setTimeout(r,100))}
  throw new Error('Test server did not start: '+stderr);
}
async function stop(){if(server&&server.exitCode===null){const exited=new Promise(r=>server.once('exit',r));server.kill('SIGINT');await exited}}
async function route(name){await page.locator(`.sidebar [data-nav="${name}"]`).click();await page.waitForSelector(`.sidebar [data-nav="${name}"].active`);await page.waitForSelector(({dashboard:'#metrics',lab:'#event-form',campaigns:'#campaign-form',jobs:'#jobs-table',agents:'.agent-card',reports:'#report-content',audit:'#audit-table'})[name])}
async function waitStatus(text){await page.locator('.drawer-head .status').filter({hasText:text}).waitFor({timeout:15000})}
async function close(){await page.locator('.drawer-head [data-action="close"]').click()}
async function scenario(id,status){await route('lab');await page.locator(`[data-scenario="${id}"]`).click();await page.locator('#event-form button[type="submit"]').click();await waitStatus(status)}
async function post(url,body,headers={}){const data=await (await fetch(base+'/api/bootstrap')).json();return fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':data.csrf_token,...headers},body:JSON.stringify(body)})}

(async()=>{
  fs.mkdirSync(path.join(root,'test-results'),{recursive:true});
  await start();
  browser=await chromium.launch({channel:'chrome',headless:true});
  page=await browser.newPage({viewport:{width:1512,height:1100}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.waitForSelector('#metrics .metric');
  assert.match(await page.locator('#metrics').innerText(),/64/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'test-results/dashboard-e2e.png',fullPage:true});
  await page.locator('.scatter .point').first().click();
  await page.waitForSelector('.step-timeline');
  await close();
  console.log('PASS dashboard, persisted data, clickable trace');

  await scenario('salary','고객 선택');
  assert.equal(await page.locator('[data-decision="accept"]').isDisabled(),true);
  await page.locator('#customer-consent').check();
  await page.locator('[data-decision="accept"]').click();
  await waitStatus('완료');
  await page.screenshot({path:'test-results/trace.png',fullPage:true});
  await close();
  await scenario('no_consent','정책 차단');await close();
  await scenario('frequency','정책 차단');await close();
  await scenario('nothing','제안 생략');await close();
  await scenario('fault','실패');
  await page.locator('[data-action="retry"]').click();
  await waitStatus('고객 선택');
  await page.locator('[data-decision="decline"]').click();
  await waitStatus('완료');await close();
  console.log('PASS customer consent, policy gates, Do Nothing, failure recovery');

  await route('campaigns');
  await page.locator('#brief').fill('잔액 3천만원 이상 고객에게 AI 포트폴리오를 안내해 주세요.');
  await page.locator('[data-action="parse-brief"]').click();
  assert.equal(await page.locator('#min-balance').inputValue(),'30000000');
  await page.locator('#max-audience').fill('10');
  await page.locator('#campaign-form button[type="submit"]').click();
  await waitStatus('승인 대기');
  await page.screenshot({path:'test-results/campaign-approval.png',fullPage:true});
  await page.locator('[data-decision="approve"]').click();
  await waitStatus('완료');
  assert.match(await page.locator('.drawer-body').innerText(),/발송 10/);
  await close();
  console.log('PASS natural-language helper, campaign audience, approval, delivery');

  await route('reports');
  await page.locator('[data-action="create-report"]').click();
  await page.waitForSelector('[data-report]');
  await page.screenshot({path:'test-results/report.png',fullPage:true});
  const csvURL=await page.locator('a[download]').first().getAttribute('href');
  const csv=await (await fetch(base+csvURL)).text();
  assert.match(csv,/가상 고객 및 시뮬레이션 성과/);
  const htmlURL=await page.locator('a[target="_blank"]').first().getAttribute('href');
  const printPage=await browser.newPage();await printPage.goto(base+htmlURL);
  assert.match(await printPage.locator('h1').innerText(),/마케팅 운영 리포트/);
  await printPage.pdf({path:'test-results/sample-report.pdf',format:'A4',printBackground:true});
  await printPage.close();
  await route('agents');assert.equal(await page.locator('.agent-card').count(),10);
  await page.locator('[data-agent="supervisor"]').click();
  await page.waitForSelector('.modal');await page.locator('.modal [data-action="close"]').click();
  await route('audit');await page.waitForSelector('#audit-table tbody tr');
  await route('jobs');await page.locator('#job-search').fill('C0004');
  assert.match(await page.locator('#jobs-table').innerText(),/C0004/);
  console.log('PASS reports, CSV, printable PDF, agent contracts, audit, search');

  const request={mode:'event',event_type:'quiet',customer_id:'C0006'};
  const first=await (await post('/api/jobs',request,{'Idempotency-Key':'browser-retry-test'})).json();
  const second=await (await post('/api/jobs',request,{'Idempotency-Key':'browser-retry-test'})).json();
  assert.equal(first.id,second.id);
  assert.equal((await fetch(base+'/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status,403);
  assert.equal((await post('/api/jobs',{...request,amount:-1})).status,400);
  await route('lab');await page.locator('[data-action="demo-start"]').click();
  await page.waitForSelector('.traffic-banner');
  await page.locator('[data-action="demo-stop"]').click();
  await page.waitForFunction(()=>!document.querySelector('.traffic-banner'));
  console.log('PASS idempotency, request protection, validation, live traffic stream');

  await page.setViewportSize({width:390,height:844});
  for(const name of ['dashboard','lab','campaigns','agents','reports','jobs']){
    await route(name);await page.waitForTimeout(150);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`mobile overflow: ${name}`);
  }
  await route('dashboard');
  await page.screenshot({path:'test-results/mobile.png',fullPage:true});
  const reportsBefore=await (await fetch(base+'/api/reports')).json();
  await stop();await start();
  const reportsAfter=await (await fetch(base+'/api/reports')).json();
  assert.equal(reportsBefore[0].id,reportsAfter[0].id);
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('PASS mobile responsive layouts, persistence after restart, zero browser errors');
  console.log('BROWSER E2E: ALL PASSED');
})().catch(async error=>{console.error(error);if(page)await page.screenshot({path:'test-results/failure.png',fullPage:true}).catch(()=>{});process.exitCode=1}).finally(async()=>{if(browser)await browser.close();await stop()});
