import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({timezoneId:'Asia/Kathmandu',viewport:{width:1280,height:950}});
const page=await context.newPage(),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const username=`zones-${Date.now()}`,password='timezone-test-password';
async function waitText(selector,text){await page.waitForFunction(({selector,text})=>document.querySelector(selector)?.textContent.includes(text),{selector,text});}
try{
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#timezone option')!==null);
  await page.locator('#auth-switch').click();await waitText('#initial-timezone','Asia/Kathmandu');
  await page.locator('[name=username]').fill(username);await page.locator('[name=password]').fill(password);await page.locator('#auth-submit').click();
  await waitText('#timezone-label','Asia/Kathmandu');
  const token=await page.evaluate(()=>sessionStorage.getItem('stop-clop-token'));
  const headers={Authorization:`Bearer ${token}`};
  assert.equal((await(await context.request.get(base+'/api/settings',{headers})).json()).timezone,'Asia/Kathmandu');
  await page.locator('[data-view=settings]').click();
  const count=await page.locator('#timezone option').count();assert.ok(count>300&&count<400);
  assert.equal(await page.locator('#timezone option[value="US/Eastern"]').count(),0);
  assert.match(await page.locator('#timezone option:checked').textContent(),/UTC\+05:45/);
  for(const query of ['Japan','Japon','日本','Tokyo','Asia/Tokyo']){
    await page.locator('#timezone-search').fill(query);
    assert.equal(await page.locator('#timezone option[value="Asia/Tokyo"]').count(),1,query);
    assert.ok(await page.locator('#timezone option').count()<10);
  }
  await page.locator('#timezone-search').fill('Calcutta');
  assert.equal(await page.locator('#timezone option[value="Asia/Kolkata"]').count(),1);
  await page.locator('#timezone-search').fill('Tokyo');await page.locator('#timezone').selectOption('Asia/Tokyo');
  await page.locator('#settings-form button').click();await waitText('#timezone-label','Asia/Tokyo');
  // Date input is now in the profile's zone, not in the browser's Kathmandu zone.
  await page.locator('[data-view=history]').click();await page.locator('#occurred-at').fill('2025-01-02T00:30');await page.locator('#entry-form button').click();await waitText('#message','Consumption recorded');
  const history=await(await context.request.get(base+'/api/cigarettes?start=2025-01-01&end=2025-01-03',{headers})).json();
  assert.equal(history.items[0].occurred_at,'2025-01-01T15:30:00.000000+00:00');
  // Preserve a legacy identifier, including on an unrelated settings update.
  assert.equal((await context.request.put(base+'/api/settings',{headers,data:{timezone:'US/Eastern'}})).status(),200);
  await page.reload();await waitText('#timezone-label','US/Eastern');await page.locator('[data-view=settings]').click();
  assert.equal(await page.locator('#timezone').inputValue(),'US/Eastern');
  assert.match(await page.locator('#timezone option:checked').textContent(),/UTC-0[45]:00/);
  await page.locator('#pack-price').fill('13');await page.locator('#settings-form button').click();await waitText('#message','Settings saved');
  assert.equal((await(await context.request.get(base+'/api/settings',{headers})).json()).timezone,'US/Eastern');
  const secondContext=await browser.newContext({timezoneId:'Europe/Paris'}),second=await secondContext.newPage();
  await second.goto(base);await second.locator('[name=username]').fill(username);await second.locator('[name=password]').fill(password);await second.locator('#auth-submit').click();
  await second.waitForFunction(()=>document.querySelector('#timezone-label')?.textContent.includes('US/Eastern'));
  assert.equal(await second.locator('#timezone').inputValue(),'US/Eastern');
  await secondContext.close();assert.deepEqual(errors,[]);
  console.log('Timezone web OK: browser detection, city/country/alias search, fractional offset, profile-local entry, preserved legacy preference on reload and other browser.');
}finally{await browser.close();}
