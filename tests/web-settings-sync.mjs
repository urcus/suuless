import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch({headless:true});
const desktop=await browser.newContext(),mobile=await browser.newContext({viewport:{width:390,height:844}});
const first=await desktop.newPage(),second=await mobile.newPage();
const errors=[];for(const page of [first,second])page.on('pageerror',error=>errors.push(error.message));
const account={username:`sync-${Date.now()}`,password:'settings-sync-password'};
async function signIn(page,register=false){
  await page.goto(base);if(register)await page.locator('#auth-switch').click();
  await page.locator('[name=username]').fill(account.username);await page.locator('[name=password]').fill(account.password);
  await page.locator('#auth-submit').click();await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='0');
  await page.locator('[data-view=settings]').click();
}
async function refresh(page){await page.locator('#refresh').click();await page.waitForFunction(()=>!document.querySelector('#refresh').disabled);}
async function save(page){await page.locator('#settings-form button').click();await page.waitForFunction(()=>!document.querySelector('#settings-form button').disabled);}
try{
  await signIn(first,true);await signIn(second);
  await first.locator('#currency').selectOption('JPY');await first.locator('#pack-price').fill('600');
  await first.locator('#pack-size').fill('25');await first.locator('#daily-target').fill('7');
  await first.locator('#language').selectOption('fr');await first.locator('#timezone').selectOption('Asia/Tokyo');await save(first);
  await refresh(second);
  assert.equal(await second.locator('#pack-price').inputValue(),'600');
  assert.equal(await second.locator('#currency').inputValue(),'JPY');
  assert.equal(await second.locator('#pack-size').inputValue(),'25');
  assert.equal(await second.locator('#daily-target').inputValue(),'7');
  assert.equal(await second.locator('#timezone').inputValue(),'Asia/Tokyo');
  assert.equal(await second.locator('html').getAttribute('lang'),'fr');
  // An unsaved edit must survive refresh; untouched fields still receive remote changes.
  await second.locator('#daily-target').fill('8');
  await first.locator('#pack-price').fill('700');await save(first);await refresh(second);
  assert.equal(await second.locator('#daily-target').inputValue(),'8');
  assert.equal(await second.locator('#pack-price').inputValue(),'700');
  // A stale form only sends edited fields, preserving a newer price from another device.
  await first.locator('#pack-price').fill('800');await save(first);await save(second);await refresh(first);
  assert.equal(await first.locator('#pack-price').inputValue(),'800');
  assert.equal(await first.locator('#daily-target').inputValue(),'8');
  await second.reload();await second.waitForFunction(()=>document.querySelector('#pack-price').value==='800');
  assert.equal(await second.locator('#currency').inputValue(),'JPY');
  assert.equal(await second.locator('#daily-target').inputValue(),'8');
  assert.equal(await second.locator('html').getAttribute('lang'),'fr');
  assert.deepEqual(errors,[]);
  console.log('Settings sync OK: two sessions, mobile refresh/reload, language, price, currency, timezone, unsaved edits and partial updates.');
}finally{await browser.close();}
