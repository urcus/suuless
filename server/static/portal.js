'use strict';
const portal={
  locale:['en','fr','ja'].includes(localStorage.getItem('stop-clop-language'))?localStorage.getItem('stop-clop-language'):'en',
  dict:{}, token:sessionStorage.getItem('stop-clop-token')||'',
  t(key){return this.dict[key]||key;},
  async language(code){const r=await fetch('/static/locales/'+code+'.json');if(!r.ok)throw new Error('Language unavailable');this.dict=await r.json();this.locale=code;localStorage.setItem('stop-clop-language',code);document.documentElement.lang=code;document.title=this.t('app_name');document.getElementById('portal-language').value=code;document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=this.t(e.dataset.i18n));},
  message(text,error=false){const e=document.getElementById('portal-message');e.textContent=text;e.className=error?'error':'';},
  async api(path,method='GET',data){
    let response;try{response=await fetch('/api'+path,{method,headers:{'Accept-Language':this.locale,...(this.token?{Authorization:'Bearer '+this.token}:{}),...(data!==undefined?{'Content-Type':'application/json'}:{})},...(data!==undefined?{body:JSON.stringify(data)}:{})});}catch{throw new Error(this.t('network_error'));}
    if(response.status===204)return null;
    const result=await response.json();if(!response.ok){const error=new Error(result.error);error.status=response.status;throw error;}return result;
  },
  form(id,callback){const form=document.getElementById(id);form.addEventListener('submit',async e=>{e.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await callback(Object.fromEntries(new FormData(form)),form);}catch(err){this.message(err.message,true);}finally{button.disabled=false;}});}
};
portal.ready=portal.language(portal.locale);
