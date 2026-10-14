import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch(),page=await browser.newPage({viewport:{width:390,height:844}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 const credentials={username:'devices-'+Date.now(),password:'devices-test-password'};
 const auth=await(await page.request.post(base+'/api/auth/register',{data:credentials})).json();
 const other=await(await page.request.post(base+'/api/auth/login',{data:{...credentials,client:'android'}})).json();
 const headers={Authorization:'Bearer '+auth.token};
 const key=await(await page.request.post(base+'/api/tokens',{headers,data:{name:'Session'}})).json();
 await page.goto(base);await page.evaluate(token=>sessionStorage.setItem('stop-clop-token',token),auth.token);await page.reload();
 await page.waitForFunction(()=>document.querySelector('#session-count').textContent==='2');
 await page.locator('[data-view=settings]').click();
 assert.equal(await page.locator('#tokens li').count(),1);assert.match(await page.locator('#tokens').textContent(),/Session/);
 assert.equal(await page.locator('#sessions').isVisible(),false);
 await page.locator('.connected-devices').first().locator('summary').click();
 assert.equal(await page.locator('#sessions li').count(),2);assert.match(await page.locator('#sessions').textContent(),/Android app/);
 page.once('dialog',dialog=>dialog.dismiss());await page.locator('#revoke-other-sessions').click();assert.equal(await page.locator('#sessions li').count(),2);
 page.once('dialog',dialog=>dialog.accept());await page.locator('#revoke-other-sessions').click();
 await page.waitForFunction(()=>document.querySelector('#session-count').textContent==='1');
 assert.equal(await page.locator('#revoke-other-sessions').isDisabled(),true);
 assert.equal((await page.request.get(base+'/api/me',{headers:{Authorization:'Bearer '+other.token}})).status(),401);
 assert.equal((await page.request.get(base+'/api/me',{headers:{Authorization:'Bearer '+key.token}})).status(),200);
 assert.equal((await page.request.get(base+'/api/me',{headers})).status(),200);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'test-results/connected-devices-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);console.log('Sessions web OK: separate lists, collapsed devices, confirmation/cancellation, current session and API key preserved.');
}finally{await browser.close();}
