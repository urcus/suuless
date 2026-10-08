import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1050},locale:'ja-JP'});
const page=await context.newPage(),errors=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
const username=`i18n-${Date.now()}`,password='long-international-password';
async function text(selector,value){await page.waitForFunction(({selector,value})=>document.querySelector(selector)?.textContent.includes(value),{selector,value});}
async function lang(value){await page.waitForFunction(value=>document.documentElement.lang===value,value);}
async function saved(word){await text('#message',word);await page.waitForFunction(()=>!document.querySelector('#settings-form button').disabled);}
async function translationCheck(code){
  const messages=await (await context.request.get(base+`/static/locales/${code}.json`)).json();
  const nodes=await page.locator('[data-i18n]').evaluateAll(nodes=>nodes.map(node=>[node.dataset.i18n,node.textContent]));
  for(const [key,value] of nodes)assert.equal(value,messages[key],`${code}: ${key}`);
}
try{
  await page.goto(base);await text('#auth-submit','Sign in');
  assert.equal(await page.locator('html').getAttribute('lang'),'en','First visit is English even on a Japanese device');
  await page.locator('#auth-switch').click();
  await page.locator('[name=username]').fill(username);await page.locator('[name=password]').fill(password);await page.locator('#auth-submit').click();
  await text('#today-count','0');await translationCheck('en');
  await page.locator('#plus-one').click();await text('#period-cost','0.60');
  await page.locator('.settings>summary').click();
  assert.ok(await page.locator('#timezone option').count()>300);
  assert.ok(await page.locator('#timezone option').count()<400);
  assert.ok(await page.locator('#currency option').count()>140);
  await page.locator('#timezone-search').fill('Kathmandu');
  assert.ok(await page.locator('#timezone option').count()<5);
  await page.locator('#timezone').selectOption('Asia/Kathmandu');
  await page.locator('#currency').selectOption('USD');
  assert.equal(await page.locator('#pack-price').inputValue(),'','Changing currency asks for a new price');
  await page.locator('#pack-price').fill('10.50');await page.locator('#language').selectOption('fr');
  await page.locator('#settings-form button').click();await saved('Réglages enregistrés');await lang('fr');await translationCheck('fr');
  await text('#timezone-label','Asia/Kathmandu');await page.locator('#plus-one').click();await text('#period-count','2');await text('#period-cost','USD');await text('#period-cost','EUR');
  await page.locator('#currency').selectOption('JPY');await page.locator('#pack-price').fill('600.5');
  assert.equal(await page.locator('#pack-price').evaluate(el=>el.checkValidity()),false,'Yen prices reject fractional digits');
  await page.locator('#pack-price').fill('600');await page.locator('#language').selectOption('ja');
  await page.locator('#timezone-search').fill('');await page.locator('#timezone').selectOption('Pacific/Chatham');
  await page.locator('#settings-form button').click();await saved('設定を保存しました');await lang('ja');await translationCheck('ja');
  await page.locator('#plus-one').click();await text('#period-count','3');await text('#period-cost','JPY');
  const token=await page.evaluate(()=>sessionStorage.getItem('stop-clop-token'));
  const stats=await (await context.request.get(base+'/api/stats',{headers:{Authorization:`Bearer ${token}`}})).json();
  assert.deepEqual(stats.total.costs,{EUR:0.6,USD:0.53,JPY:30});assert.equal(stats.total.cost,null);
  assert.ok((await page.locator('#period-cost').textContent()).includes('JPY'));
  await page.reload();await lang('ja');await text('#today-count','3');
  await page.locator('.settings>summary').click();
  assert.equal(await page.locator('#currency').inputValue(),'JPY');assert.equal(await page.locator('#pack-price').inputValue(),'600');assert.equal(await page.locator('#timezone').inputValue(),'Pacific/Chatham');
  await page.locator('#currency').selectOption('KWD');assert.equal(await page.locator('#pack-price').getAttribute('step'),'0.001');
  await page.locator('#pack-price').fill('1.234');await page.locator('#settings-form button').click();await saved('設定を保存しました');
  await mkdir('test-results',{recursive:true});
  await page.screenshot({path:'test-results/settings-japanese.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Settings fit a mobile screen');
  await page.screenshot({path:'test-results/settings-japanese-mobile.png',fullPage:true});
  // Hold the language refresh in flight: logout must not revoke its session.
  let releaseRefresh,refreshStarted;
  const refreshGate=new Promise(resolve=>{releaseRefresh=resolve;});
  const refreshSeen=new Promise(resolve=>{refreshStarted=resolve;});
  await page.route('**/api/stats?*',async route=>{refreshStarted();await refreshGate;await route.continue();});
  await page.locator('#header-language').selectOption('en');await lang('en');await refreshSeen;
  try{
    await translationCheck('en');
    assert.equal(await page.locator('#logout').isDisabled(),true,'Logout waits for the language refresh');
    assert.equal(await page.locator('#header-language').isDisabled(),true,'Language changes cannot overlap');
  }finally{releaseRefresh();}
  await page.waitForFunction(()=>!document.querySelector('#header-language').disabled);
  await page.unroute('**/api/stats?*');
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  // Profile language takes precedence over a fresh browser's default.
  const other=await browser.newContext({locale:'fr-FR'}),second=await other.newPage();
  await second.goto(base);await second.locator('[name=username]').fill(username);await second.locator('[name=password]').fill(password);await second.locator('#auth-submit').click();
  await second.locator('#dashboard').waitFor({state:'visible'});
  assert.equal(await second.locator('html').getAttribute('lang'),'en');
  await second.locator('#header-language').selectOption('ja');await second.waitForFunction(()=>document.documentElement.lang==='ja');
  await second.reload();await second.waitForFunction(()=>document.documentElement.lang==='ja');
  await other.close();assert.deepEqual(errors,[]);
  console.log('International web OK: default English, EN/FR/JA, currency precision, mixed totals, full timezone search, preferences across reload/login, mobile.');
}finally{await browser.close();}
