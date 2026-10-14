import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const temp=await mkdtemp(join(tmpdir(),'suuless-smtp-env-'));
const fixture=spawn('.venv/bin/python',['tests/admin_web_server.py'],{env:{...process.env,PYTHONPATH:process.cwd(),ADMIN_TEST_DATABASE:join(temp,'db'),ADMIN_TEST_MAIL:join(temp,'mail.json'),SMTP_ENABLED:'true',SMTP_HOST:'smtp.example.com',SMTP_PORT:'465',SMTP_SECURITY:'tls',SMTP_USERNAME:'mailer',SMTP_PASSWORD:'smtp-env-test-secret',SMTP_FROM:'suuless@example.com',SMTP_PUBLIC_URL:'https://suuless.example.com'},stdio:['ignore','pipe','pipe']});
let stderr='',browser;fixture.stderr.on('data',c=>stderr+=c);
try{
 const port=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Fixture timeout: '+stderr)),20000);fixture.stdout.once('data',c=>{clearTimeout(timer);resolve(Number(c.toString().trim()));});fixture.once('exit',code=>{clearTimeout(timer);reject(new Error('Fixture stopped '+code+' '+stderr));});});
 const base='http://127.0.0.1:'+port;browser=await chromium.launch();const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.locator('#auth-form [name=username]').fill('administrator');await page.locator('#auth-form [name=password]').fill('administrator-test-password');await page.locator('#auth-submit').click();await page.waitForURL(base+'/admin');await page.locator('[data-tab=smtp]').click();
 await page.locator('#smtp-environment-note').waitFor({state:'visible'});
 assert.equal(await page.locator('#smtp-form [name=host]').inputValue(),'smtp.example.com');
 assert.equal(await page.locator('#smtp-form [name=password]').inputValue(),'');
 assert.ok(await page.locator('#smtp-form').evaluate(form=>[...form.elements].every(field=>field.disabled)));
 assert.ok(await page.locator('#smtp-test-form button').isEnabled());
 assert.ok(!(await page.content()).includes('smtp-env-test-secret'));
 const token=await page.evaluate(()=>sessionStorage.getItem('stop-clop-token'));
 assert.equal((await page.request.put(base+'/api/admin/smtp',{headers:{Authorization:'Bearer '+token},data:{enabled:false}})).status(),409);
 await page.locator('#smtp-test-form [name=email]').fill('test@example.com');await page.locator('#smtp-test-form button').click();await page.waitForFunction(()=>document.getElementById('portal-message').textContent==='Email sent.');
 assert.equal(JSON.parse(await readFile(join(temp,'mail.json'),'utf8')).recipient,'test@example.com');
 await page.locator('#portal-language').selectOption('fr');await page.waitForFunction(()=>document.getElementById('smtp-environment-note').textContent.includes('variables d’environnement'));
 assert.deepEqual(errors,[]);console.log('SMTP environment web OK: effective settings, read-only fields, password redaction, API conflict and test delivery.');
}finally{if(browser)await browser.close();fixture.kill('SIGTERM');await new Promise(resolve=>fixture.exitCode!==null||fixture.signalCode!==null?resolve():fixture.once('exit',resolve));await rm(temp,{recursive:true,force:true});}
