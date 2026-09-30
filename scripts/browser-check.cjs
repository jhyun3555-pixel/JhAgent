const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');

(async () => {
  fs.mkdirSync('test-results', {recursive:true});
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const page = await browser.newPage({viewport:{width:1512,height:1100},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  page.on('console', message=>{if(message.type()==='error')errors.push(message.text())});
  await page.goto(process.env.APP_URL || 'http://127.0.0.1:8765', {waitUntil:'domcontentloaded'});
  await page.waitForSelector('#metrics .metric');
  await page.selectOption('#time-range','60');
  await page.waitForTimeout(800);
  await page.screenshot({path:'test-results/dashboard.png',fullPage:true});
  console.log(JSON.stringify({title:await page.title(),metrics:await page.locator('#metrics').innerText(),errors,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)},null,2));
  await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
