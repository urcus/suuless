import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:8080';
const browser=await chromium.launch({headless:true}),context=await browser.newContext(),page=await context.newPage();
const errors=[];page.on('pageerror',error=>errors.push(error.message));
try{
 const auth=await(await context.request.post(base+'/api/auth/register',{data:{username:`auto-${Date.now()}`,password:'auto-refresh-test-password'}})).json();
 const headers={Authorization:`Bearer ${auth.token}`};
 await page.goto(base);await page.evaluate(token=>sessionStorage.setItem('stop-clop-token',token),auth.token);await page.reload();
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='0'&&!refreshPending);
 assert.equal(await page.locator('#refresh').count(),0);
 // An external API entry must appear through the real timer, without a click/event.
 await context.request.post(base+'/api/cigarettes',{headers,data:{quantity:1,source:'api'}});
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='1',null,{timeout:20000});
 // Keep a manual timestamp and a local settings draft while applying remote settings.
 await page.locator('[data-view=history]').click();await page.locator('#occurred-at').fill('2025-01-02T12:34');
 await page.locator('[data-view=settings]').click();await page.locator('#daily-target').fill('17');
 await context.request.put(base+'/api/settings',{headers,data:{pack_size:25,timezone:'Asia/Tokyo'}});
 await page.waitForFunction(()=>!refreshPending&&!autoRefreshing);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForFunction(()=>document.querySelector('#pack-size').value==='25');
 assert.equal(await page.locator('#daily-target').inputValue(),'17');
 assert.equal(await page.locator('#occurred-at').inputValue(),'2025-01-02T12:34');
 // Preserve expanded history after a background update.
 for(let i=0;i<24;i++)await context.request.post(base+'/api/cigarettes',{headers,data:{source:'api'}});
 await page.waitForFunction(()=>!refreshPending&&!autoRefreshing);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='25'&&!refreshPending);
 await page.locator('[data-view=history]').click();await page.locator('#more-history').click();
 await page.waitForFunction(()=>document.querySelectorAll('#history li').length===25&&!refreshPending&&!activeActions);
 await context.request.post(base+'/api/cigarettes',{headers,data:{source:'api'}});
 await page.evaluate(()=>window.dispatchEvent(new Event('online')));
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='26'&&!refreshPending);
 assert.equal(await page.locator('#history li').count(),25);
 // Offline: retain data, then catch up on reconnection.
 await context.setOffline(true);
 await context.request.post(base+'/api/cigarettes',{headers,data:{source:'api'}});
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 assert.equal(await page.locator('#today-count').textContent(),'26');
 await context.setOffline(false);
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='27',null,{timeout:20000});
 // Hidden tabs do not poll; returning catches up immediately.
 await page.waitForFunction(()=>!refreshPending&&!autoRefreshing);
 let requests=0;const countRequests=request=>{if(request.url().includes('/api/settings'))requests++;};
 page.on('request',countRequests);
 await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
 await context.request.post(base+'/api/cigarettes',{headers,data:{source:'api'}});
 await page.waitForTimeout(10500);
 assert.equal(requests,0);
 await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'));});
 await page.waitForFunction(()=>document.querySelector('#today-count').textContent==='28');
 page.off('request',countRequests);
 // Revocation is detected without pressing a refresh button.
 await context.request.post(base+'/api/auth/logout',{headers});
 await page.waitForFunction(()=>!refreshPending&&!autoRefreshing);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.locator('#auth').waitFor({state:'visible'});
 assert.equal(await page.evaluate(()=>sessionStorage.getItem('stop-clop-token')),null);
 assert.deepEqual(errors,[]);
 console.log('Automatic web refresh OK: timer, external entries, drafts, pagination, reconnect and revoked session.');
}finally{await browser.close();}
