'use strict';
(async()=>{
  await portal.ready;
  // Keep the secret out of request URLs, history and referrers; only POST consumes it.
  const fragment=new URLSearchParams(location.hash.slice(1));const secret=fragment.get('token');
  const purpose=fragment.get('purpose')||'activate';const mode=new URLSearchParams(location.search).get('mode')||'forgot';
  if(secret)history.replaceState(null,'',location.pathname);
  const key=secret?({invite:'accept_invitation',reset:'reset_password',activate:'activate_account'}[purpose]||'activate_account'):(mode==='activate'?'resend_activation':'forgot_password');
  function labels(){document.getElementById('account-heading').textContent=portal.t(key);document.getElementById('complete-submit').textContent=portal.t(key);}
  labels();document.getElementById('portal-language').addEventListener('change',async e=>{await portal.language(e.target.value);labels();});
  document.getElementById('request-form').hidden=!!secret;document.getElementById('complete-form').hidden=!secret;
  document.getElementById('invite-fields').hidden=purpose!=='invite';document.getElementById('password-fields').hidden=purpose==='activate';
  const complete=document.getElementById('complete-form');complete.elements.username.required=purpose==='invite';complete.elements.password.required=purpose!=='activate';complete.elements.confirm.required=purpose!=='activate';
  portal.form('request-form',async data=>{const r=await portal.api('/auth/'+(mode==='activate'?'resend-activation':'forgot-password'),'POST',data);portal.message(r.message);});
  portal.form('complete-form',async data=>{if(purpose!=='activate'&&data.password!==data.confirm)throw new Error(portal.t('password_mismatch'));const r=await portal.api('/auth/complete','POST',{token:secret,username:data.username,password:data.password});document.getElementById('complete-form').hidden=true;portal.message(r.message);});
})().catch(e=>portal.message(e.message,true));
