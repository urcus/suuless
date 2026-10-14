import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch(),page=await browser.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
async function view(name){await page.locator(`[data-view=${name}]`).click();await page.locator('#view-'+name).waitFor({state:'visible'});}
try{
  const auth=await(await page.request.post(base+'/api/auth/register',{data:{username:`navigation-${Date.now()}`,password:'navigation-test-password'}})).json();
  await page.goto(base);assert.equal(await page.locator('.app-nav').isVisible(),false);
  await page.evaluate(token=>sessionStorage.setItem('stop-clop-token',token),auth.token);await page.reload();
  await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='0');
  assert.equal(await page.locator('.app-view:visible').count(),1);
  assert.equal(await page.locator('#plus-one').isVisible(),true);
  assert.equal(await page.locator('#checkin-day').isVisible(),true);
  assert.equal(await page.locator('#chart').isVisible(),false);
  // The navigation is usable with a keyboard and announces the current page.
  await page.locator('[data-view=settings]').focus();await page.keyboard.press('Enter');
  await page.locator('#settings-form').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-view=settings]').getAttribute('aria-current'),'page');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'view-title');
  await page.locator('#pack-price').fill('13.25');
  await view('journey');await page.locator('#journey details').first().locator('summary').click();
  await page.locator('#journey-motivation').fill('Keep this unsaved draft');
  await view('today');await view('settings');assert.equal(await page.locator('#pack-price').inputValue(),'13.25');
  await view('journey');assert.equal(await page.locator('#journey-motivation').inputValue(),'Keep this unsaved draft');
  await view('history');await page.goBack();await page.locator('#view-journey').waitFor({state:'visible'});
  await page.reload();await page.locator('#view-journey').waitFor({state:'visible'});
  for(const code of ['en','fr','ja']){
    await page.locator('#header-language').selectOption(code);await page.waitForFunction(code=>document.documentElement.lang===code&&!document.querySelector('#header-language').disabled,code);
    for(const width of [320,390,1280]){
      await page.setViewportSize({width,height:844});
      for(const name of ['today','journey','analysis','history','settings']){
        await view(name);assert.equal(await page.locator('.app-view:visible').count(),1);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${code}/${name}/${width} overflow`);
        assert.equal(await page.locator('.app-nav [aria-current=page]').count(),1);
      }
    }
  }
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});assert.equal(await page.locator('.app-nav').isVisible(),false);
  assert.deepEqual(errors,[]);console.log('Navigation web OK: focused views, keyboard, history/reload, unsaved drafts, EN/FR/JA and 320/390/1280px.');
}finally{await browser.close();}
