'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('stop-clop-token') || '';
let locale = localStorage.getItem('stop-clop-language') || 'en';
if (!['en','fr','ja'].includes(locale)) locale = 'en';
const dictionaries = {};
let pendingEntry = null, registering = false, settings, catalog, historyOffset = 0, noticeTimer;
const t = (key,...values) => (dictionaries[locale]?.[key] || dictionaries.en?.[key] || key).replace(/\{(\d+)\}/g,(_,i)=>values[i] ?? '');
const number = value => new Intl.NumberFormat(locale).format(value);
const money = (value,currency) => new Intl.NumberFormat(locale,{style:'currency',currency,currencyDisplay:'code'}).format(value);
const costs = data => Object.entries(data.costs).map(([code,value])=>money(value,code)).join(' + ');
function notice(message,error=false) {
  $('message').textContent=message; $('message').className=error?'error':''; $('message').hidden=false;
  clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('message').hidden=true,error?10000:5000);
}
function authLabels() {
  $('auth-title').textContent=t(registering?'personal_space':'welcome');
  $('auth-submit').textContent=t(registering?'register':'login');
  $('auth-switch').textContent=t(registering?'existing_account':'register');
}
async function setLanguage(code) {
  if (!dictionaries[code]) {
    const response=await fetch(`/static/locales/${code}.json`);
    if(!response.ok) throw new Error(t('network_error'));
    dictionaries[code]=await response.json();
  }
  locale=code; localStorage.setItem('stop-clop-language',code); document.documentElement.lang=code;
  document.title=t('page_title');
  document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
  document.querySelectorAll('[data-i18n-aria]').forEach(el=>el.setAttribute('aria-label',t(el.dataset.i18nAria)));
  $('header-language').value=code; $('language').value=code; authLabels();
}
function disconnected() {
  pendingEntry=null; token=''; sessionStorage.removeItem('stop-clop-token'); settings=null;
  $('auth').hidden=false; $('dashboard').hidden=true; $('identity').hidden=true;
  $('token-value').value=''; $('new-token').hidden=true;
}
async function api(path,method='GET',data,extra={}) {
  let response;
  try {
    response=await fetch('/api'+path,{method,headers:{'Accept-Language':locale,
      ...(token?{Authorization:`Bearer ${token}`} : {}),
      ...(data!==undefined?{'Content-Type':'application/json'}:{}),...extra},
      ...(data!==undefined?{body:JSON.stringify(data)}:{})});
  } catch { throw new Error(t('network_error')); }
  if(!response.ok) {
    const payload=await response.json().catch(()=>({}));
    if(response.status===401&&!path.startsWith('/auth/'))disconnected();
    const error=new Error(payload.error||t('http_error',response.status)); error.status=response.status; throw error;
  }
  if(response.status===204)return null;
  return path.startsWith('/export')?response.blob():response.json();
}
function action(id,event,callback) {
  $(id).addEventListener(event,async e=>{
    e.preventDefault();
    const buttons=[...$(id).querySelectorAll('button'),...($(id).tagName==='BUTTON'?[$(id)]:[])];
    buttons.forEach(b=>b.disabled=true);
    try{await callback(e);}catch(err){notice(err.message,true);}finally{buttons.forEach(b=>b.disabled=false);}
  });
}
function dateHere(){return settings.local_today;}
function setRange(days) {
  const end=dateHere(),start=new Date(end+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-days+1);
  $('start-date').value=start.toISOString().slice(0,10);$('end-date').value=end;
}
function query(){return `start=${$('start-date').value}&end=${$('end-date').value}`;}
function localInputNow(){$('occurred-at').value=settings.local_datetime.slice(0,16);}
function cell(text,tag='td'){const el=document.createElement(tag);el.textContent=text;return el;}
function dayLabel(value){return new Date(value+'T12:00:00Z').toLocaleDateString(locale,{timeZone:'UTC'});}
function pricePrecision(){
  const currency=$('currency').value,meta=catalog?.currencies.find(c=>c.code===currency);
  $('pack-price').step=String(10**-(meta?.digits??2));
  $('currency-price-hint').textContent=t('currency_price_hint',currency);
}
const searchKey = value => value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase();
function detectedTimezone(){
  let id;
  try{id=Intl.DateTimeFormat().resolvedOptions().timeZone;}catch{return 'UTC';}
  const representative=catalog?.timezone_aliases[id]||id;
  return catalog?.timezones.includes(representative)?representative:'UTC';
}
function timezoneOptions(preferred){
  const selected=preferred||$('timezone').value||settings?.timezone||detectedTimezone();
  const search=searchKey($('timezone-search').value.trim());
  const options=[...catalog.timezone_options];
  // Keep a stored legacy ID selectable without adding aliases to everyone's list.
  if(settings?.timezone_info&&!options.some(zone=>zone.id===settings.timezone))options.push(settings.timezone_info);
  $('timezone').replaceChildren(...options.filter(zone=>zone.id===selected||searchKey(zone.search+' '+zone.label).includes(search))
    .map(zone=>new Option(zone.label,zone.id,false,zone.id===selected)));
}
async function loadCatalog(){
  const nextCatalog=await api('/config');
  const selected=$('currency').value||settings?.currency||'EUR';
  catalog=nextCatalog;$('auth-switch').hidden=!catalog.registration_enabled;
  $('currency').replaceChildren(...catalog.currencies.map(c=>new Option(`${c.code} — ${c.name}`,c.code,false,c.code===selected)));
  timezoneOptions();pricePrecision();
  $('initial-timezone').textContent=t('initial_timezone',detectedTimezone());
}
async function loadHistory(append=false){
  if(!append){historyOffset=0;$('history').replaceChildren();}
  const data=await api(`/cigarettes?${query()}&limit=20&offset=${historyOffset}`);
  $('history-total').textContent=data.total?t('history_total',number(data.total)):t('no_entries');
  for(const row of data.items){
    const li=document.createElement('li'),desc=document.createElement('div');
    desc.textContent=`${t('quantity_count',number(row.quantity))} · ${money(row.cost,row.currency)}`;
    const time=document.createElement('small');time.textContent=new Date(row.local_datetime.slice(0,19)+'Z').toLocaleString(locale,{timeZone:'UTC',dateStyle:'short',timeStyle:'short'})+` (UTC${row.local_datetime.slice(-6)}) · ${row.source}`;desc.append(time);
    const remove=document.createElement('button');remove.className='danger';remove.textContent=t('delete');
    remove.onclick=async()=>{
      if(!confirm(t('delete_confirm')))return;remove.disabled=true;
      try{await api(`/cigarettes/${row.id}`,'DELETE');await refresh();notice(t('entry_deleted'));}catch(err){notice(err.message,true);remove.disabled=false;}
    };
    li.append(desc,remove);$('history').append(li);
  }
  historyOffset+=data.items.length;$('more-history').hidden=historyOffset>=data.total;
}
async function refresh(){
  settings=await api('/settings');
  if($('preset').value!=='custom')setRange(Number($('preset').value));
  const data=await api(`/stats?${query()}`);
  $('today-count').textContent=number(data.today.quantity);$('today-cost').textContent=t('today_cost',costs(data.today));
  $('period-count').textContent=number(data.period.quantity);$('period-cost').textContent=costs(data.period);
  $('average').textContent=t('average',number(data.period.average_per_day),number(data.period.days));
  $('all-time').textContent=`${t('quantity_count',number(data.total.quantity))} · ${costs(data.total)}`;
  $('target-label').textContent=t('target_label',number(settings.daily_target));$('timezone-label').textContent=t('timezone_label',data.timezone);
  $('chart').replaceChildren();$('daily-table').replaceChildren();
  const max=Math.max(1,...data.daily.map(day=>day.quantity));
  for(const day of data.daily){
    const col=document.createElement('div');col.className='bar-column';col.title=`${dayLabel(day.date)} : ${t('quantity_count',number(day.quantity))}, ${costs(day)}`;
    const value=cell(number(day.quantity),'b'),bar=document.createElement('div');bar.className='bar';bar.style.height=`${day.quantity/max*135}px`;
    col.append(value,bar,cell(day.date.slice(8),'span'));$('chart').append(col);
    const tr=document.createElement('tr');tr.append(cell(dayLabel(day.date)),cell(number(day.quantity)),cell(costs(day)));$('daily-table').append(tr);
  }
  await loadHistory();
}
async function loadTokens(){
  const rows=await api('/tokens');$('tokens').replaceChildren();
  for(const row of rows){
    const li=document.createElement('li'),name=document.createElement('div');name.textContent=row.name+(row.current?t('current_session'):'');
    name.append(cell(t('expires',new Date(row.expires_at).toLocaleDateString(locale)),'small'));
    const button=document.createElement('button');button.className='danger';button.textContent=t('revoke');
    button.onclick=async()=>{
      if(!confirm(t('revoke_confirm')))return;button.disabled=true;
      try{await api(`/tokens/${row.id}`,'DELETE');if(row.current)disconnected();else await loadTokens();}catch(err){notice(err.message,true);button.disabled=false;}
    };li.append(name,button);$('tokens').append(li);
  }
}
async function connected(){
  const [me,prefs]=await Promise.all([api('/me'),api('/settings')]);settings=prefs;
  await setLanguage(settings.language);await loadCatalog();
  $('username').textContent=me.username;$('auth').hidden=true;$('dashboard').hidden=false;$('identity').hidden=false;
  $('pack-price').value=settings.pack_price;$('currency').value=settings.currency;pricePrecision();
  $('pack-size').value=settings.pack_size;$('daily-target').value=settings.daily_target;timezoneOptions(settings.timezone);
  setRange(Number($('preset').value)||30);localInputNow();await Promise.all([refresh(),loadTokens()]);
}
action('header-language','change',async()=>{
  const next=$('header-language').value;
  try{if(token)settings=await api('/settings','PUT',{language:next});await setLanguage(next);await loadCatalog();if(token)await Promise.all([refresh(),loadTokens()]);}
  finally{$('header-language').value=locale;}
});
action('auth-switch','click',()=>{
  registering=!registering;authLabels();$('password-help').hidden=!registering;$('initial-timezone').hidden=!registering;
  const p=$('auth-form').elements.password;p.minLength=registering?12:1;p.autocomplete=registering?'new-password':'current-password';
});
action('auth-form','submit',async()=>{
  const payload={...Object.fromEntries(new FormData($('auth-form'))),language:locale};
  if(registering)payload.timezone=detectedTimezone();
  const response=await api(`/auth/${registering?'register':'login'}`,'POST',payload);
  token=response.token;sessionStorage.setItem('stop-clop-token',token);$('auth-form').reset();await connected();
});
action('logout','click',async()=>{await api('/auth/logout','POST');disconnected();});
async function saveEntry(payload){
  const serialized=JSON.stringify(payload);
  if(pendingEntry&&pendingEntry.payload!==serialized)throw new Error(t('pending_entry'));
  if(!pendingEntry)pendingEntry={payload:serialized,key:Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('')};
  try{await api('/cigarettes','POST',payload,{'Idempotency-Key':pendingEntry.key});pendingEntry=null;}
  catch(error){if(error.status&&error.status<500)pendingEntry=null;throw error;}
}
action('plus-one','click',async()=>{await saveEntry({source:'web'});notice(t('entry_saved'));await refresh();});
action('entry-form','submit',async()=>{
  await saveEntry({quantity:Number($('quantity').value),occurred_at_local:$('occurred-at').value,source:'web'});
  localInputNow();notice(t('entry_saved'));await refresh();
});
action('preset','change',async()=>{if($('preset').value!=='custom'){setRange(Number($('preset').value));await refresh();}});
action('range-form','submit',async()=>{$('preset').value='custom';await refresh();});
action('refresh','click',async()=>{if($('preset').value!=='custom')setRange(Number($('preset').value));await refresh();});
action('more-history','click',()=>loadHistory(true));
action('timezone-search','input',()=>timezoneOptions());
document.querySelector('.settings').addEventListener('toggle',()=>{
  if(document.querySelector('.settings').open)loadCatalog().catch(err=>notice(err.message,true));
});
action('currency','change',()=>{pricePrecision();$('pack-price').value='';$('pack-price').focus();});
action('settings-form','submit',async()=>{
  const previousTimezone=settings.timezone;
  settings=await api('/settings','PUT',{pack_price:$('pack-price').value,currency:$('currency').value,language:$('language').value,
    pack_size:Number($('pack-size').value),daily_target:Number($('daily-target').value),timezone:$('timezone').value});
  await setLanguage(settings.language);await loadCatalog();
  if(settings.timezone!==previousTimezone)localInputNow();
  if($('preset').value!=='custom')setRange(Number($('preset').value));notice(t('settings_saved'));await Promise.all([refresh(),loadTokens()]);
});
action('token-form','submit',async()=>{const result=await api('/tokens','POST',{name:$('token-name').value});$('token-value').value=result.token;$('new-token').hidden=false;await loadTokens();});
action('export','click',async()=>{const blob=await api(`/export.csv?${query()}`),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='stop-clop.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
(async()=>{await setLanguage(locale);await loadCatalog();if(token)await connected();})().catch(err=>notice(err.message,true));
