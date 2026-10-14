import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch(),page=await browser.newPage({viewport:{width:390,height:844}});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
try{
 const auth=await(await page.request.post(base+'/api/auth/register',{data:{username:'delete-'+Date.now(),password:'delete-test-password'}})).json();
 const headers={Authorization:'Bearer '+auth.token};await page.request.post(base+'/api/cigarettes',{headers,data:{quantity:3}});
 await page.goto(base);await page.evaluate(token=>sessionStorage.setItem('stop-clop-token',token),auth.token);await page.reload();
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='3');
 await page.locator('[data-view=settings]').click();assert.equal(await page.locator('#delete-account-form').isVisible(),false);
 await page.locator('.account-deletion>summary').click();
 await page.locator('#delete-account-password').fill('wrong');await page.locator('#delete-account-confirm').check();
 await page.locator('#delete-account-form button').click();await page.waitForFunction(()=>document.querySelector('#message').classList.contains('error'));
 assert.equal(await page.locator('#dashboard').isVisible(),true);assert.equal(await page.locator('#delete-account-password').inputValue(),'');
 assert.equal((await page.request.get(base+'/api/me',{headers})).status(),200);
 await page.locator('#delete-account-password').fill('delete-test-password');await page.locator('#delete-account-form button').click();
 await page.locator('#auth').waitFor({state:'visible'});assert.equal(await page.evaluate(()=>sessionStorage.getItem('stop-clop-token')),null);
 assert.equal((await page.request.get(base+'/api/stats',{headers})).status(),401);
 assert.match(await page.locator('#message').textContent(),/account and its data have been deleted/);
 assert.deepEqual(errors,[]);console.log('Account deletion web OK: collapsed form, explicit confirmation, wrong password preserves account, successful deletion signs out.');
}finally{await browser.close();}
