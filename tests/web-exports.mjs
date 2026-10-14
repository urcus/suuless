import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {readFile} from 'node:fs/promises';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
try{
 const auth=await(await page.request.post(base+'/api/auth/register',{data:{username:`exports-${Date.now()}`,password:'export-test-password'}})).json();
 const headers={Authorization:`Bearer ${auth.token}`};
 await page.request.post(base+'/api/cigarettes',{headers,data:{quantity:5,occurred_at:new Date().toISOString()}});
 await page.goto(base);await page.evaluate(token=>sessionStorage.setItem('stop-clop-token',token),auth.token);await page.reload();
 await page.locator('[data-view=analysis]').click();await page.locator('#preset').selectOption('custom');
 await page.locator('#start-date').fill('2025-01-01');await page.locator('#end-date').fill('2025-01-03');await page.locator('#range-form button').click();
 await page.waitForFunction(()=>document.querySelector('#daily-table').children.length===3);
 const prefs=await(await page.request.get(base+'/api/settings',{headers})).json();
 const end=prefs.local_today;
 const startFor=days=>{const date=new Date(end+'T12:00:00Z');date.setUTCDate(date.getUTCDate()-days+1);return date.toISOString().slice(0,10);};
 await page.locator('#analysis-export').click();
 await page.locator('#export-dialog').waitFor({state:'visible'});
 assert.equal(await page.locator('#export-dialog').isVisible(),true);
 assert.equal(await page.locator('#download-csv').isVisible(),false);
 await page.locator('#export-7').click();
 for(const [button,extension] of [['download-csv','csv'],['download-report','html']]){
  const waiting=page.waitForEvent('download');await page.locator('#'+button).click();const download=await waiting;
  assert.match(download.suggestedFilename(),new RegExp(`${startFor(7)}-${end}\\.${extension}$`));
  const content=await readFile(await download.path(),'utf8');
  assert.ok(content.includes(extension==='csv'?'quantity,cost,currency':'Consumption report'));
  if(extension==='html'){
   assert.ok(content.includes('<td>5</td>'));assert.ok(content.includes('No entries'));assert.ok(!content.includes(auth.token));
   await download.saveAs('test-results/consumption-report.html');
   const report=await browser.newPage();await report.goto('file://'+resolve('test-results/consumption-report.html'));
   assert.match(await report.locator('h1').textContent(),/Consumption report/);
   const pdf=await report.pdf({format:'A4'});assert.ok(pdf.length>1000);
   await report.screenshot({path:'test-results/consumption-report.png',fullPage:true});await report.close();
  }
 }
 await page.evaluate(()=>{Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>true});Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{window.sharedName=data.files[0].name;}});});
 await page.locator('#share-report').click();assert.match(await page.evaluate(()=>window.sharedName),/report.*\.html$/);
 await page.evaluate(()=>Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>false}));
 await page.locator('#share-csv').click();assert.match(await page.locator('#export-status').textContent(),/Download the file/);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#close-export').click();assert.equal(await page.locator('#export-dialog').isVisible(),false);
 for(const days of [30,90]){
  await page.locator('[data-view=history]').click();await page.locator('#export').click();
  await page.locator(`#export-${days}`).click();
  const waiting=page.waitForEvent('download');await page.locator('#download-csv').click();
  assert.equal((await waiting).suggestedFilename(),`suuless-consumption-${startFor(days)}-${end}.csv`);
  await page.locator('#close-export').click();
 }
 assert.equal(await page.locator('#start-date').inputValue(),'2025-01-01');
 assert.equal(await page.locator('#end-date').inputValue(),'2025-01-03');
 assert.deepEqual(errors,[]);console.log('Exports OK: selected dates, CSV/HTML downloads, mobile dialog, native share and fallback.');
}finally{await browser.close();}
