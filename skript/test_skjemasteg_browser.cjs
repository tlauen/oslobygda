const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const screenshots = process.env.SKJEMASTEG_SCREENSHOTS || path.join(require('node:os').tmpdir(), 'skjemasteg-bilete');
fs.mkdirSync(screenshots, {recursive:true});
const pages = JSON.parse(fs.readFileSync(process.env.SKJEMASTEG_TESTDATA, 'utf8'));
(async()=>{
 const browser = await chromium.launch({headless:true,timeout:20000});
 try {
 const context = await browser.newContext({viewport:{width:1365,height:900}});
 const page = await context.newPage();
 page.setDefaultTimeout(10000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!=='http://127.0.0.1:8765')return route.abort();
  const key=url.pathname+url.search;
  if(pages[key])return route.fulfill({contentType:'text/html',body:pages[key]});
  if(url.pathname.startsWith('/fast/')){
   const filename=path.join(root,'medlemsregister/fast',path.basename(url.pathname));
   if(fs.existsSync(filename))return route.fulfill({contentType:filename.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(filename)});
  }
  if(url.pathname.endsWith('/foringsstatus'))return route.fulfill({contentType:'application/json',body:JSON.stringify({ready:true,reason:''})});
  if(url.pathname==='/api/members')return route.fulfill({contentType:'application/json',body:'[]'});
  if(url.pathname==='/api/medlemsoversikt')return route.fulfill({contentType:'application/json',body:'{}'});
  return route.fulfill({status:404,body:''});
 });
 await page.goto('http://127.0.0.1:8765/okonomi?year=2026&del=registrer');
 await page.locator('#post-form[data-steg-klar]').waitFor();
 await page.locator('#post-form').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(screenshots,'post-desktop.png'),fullPage:true});
 await page.locator('[name=purpose]').selectOption('expense');
 await page.locator('[name=expense_paid]').selectOption('private');
 await page.locator('#post-form .skjemasteg-knappar > button').nth(1).click();
 await page.locator('[name=day]').fill('2026-11-26');
 await page.locator('[name=amount]').fill('350');
 await page.locator('[name=party]').fill('Torbjørn');
 await page.locator('#post-form .skjemasteg-knappar > button').nth(1).click();
 await page.locator('[name=public_text]').fill('Domene');
 await page.locator('[name=evidence_note]').fill('Kontrollert kvittering');
 await page.locator('#post-form .skjemasteg-knappar > button').nth(1).click();
 await page.locator('#bokfor-post').waitFor({state:'visible'});
 await page.screenshot({path:path.join(screenshots,'post-review-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.locator('#post-form .skjemasteg-topp').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(screenshots,'post-review-mobile.png')});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 assert.equal(overflow,false,'Mobil skal ikkje ha horisontal skrolling');
 for(const url of ['/budsjett/2027','/sakliste/2027','/sakliste/2027/protokoll','/arsmote/1','/nettsida/tekst','/nettsida/pobb/galleri']){
  await page.goto('http://127.0.0.1:8765'+url);
  await page.locator('form[data-steg-klar]').first().waitFor({state:'attached'});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,url+' mobiloverløp');
 }
 await page.goto('http://127.0.0.1:8765/budsjett/2027');
 await page.locator('#budget-form[data-steg-klar]').waitFor();
 await page.locator('#budget-form .skjemasteg-topp select').selectOption('1');
 await page.locator('#budget-form').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(screenshots,'budget-mobile.png')});
 await page.goto('http://127.0.0.1:8765/');
 await page.locator('#medlem-skjema[data-steg-klar]').waitFor({state:'attached'});
 await page.locator('#btn-ny').click();
 await page.locator('#fornamn').fill('Test'); await page.locator('#etternamn').fill('Medlem');
 await page.locator('#email').fill('medlem@example.test');
 await page.locator('#medlem-skjema .skjemasteg-knappar > button').nth(1).click();
 await page.locator('#medlem-skjema .skjemasteg-knappar > button').nth(1).click();
 await page.locator('#medlem-skjema .skjemasteg-knappar > button').nth(1).click();
 await page.locator('#btn-avbryt').click();
 await page.locator('#btn-ny').click();
 assert.equal(await page.locator('#medlem-skjema').getAttribute('data-steg-indeks'),'0','Ny redigering må starte på første steg');
 assert.deepEqual(errors,[],'Ingen JavaScript-feil');
 console.log('Nettlesarkontroll: privat utlegg, kontrollsteg, mobilbreidd og seks redigerarar OK');
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1)});
