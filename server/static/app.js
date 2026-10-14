'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('stop-clop-token') || '';
let locale = localStorage.getItem('stop-clop-language') || 'en';
if (!['en','fr','ja'].includes(locale)) locale = 'en';
const dictionaries = {};
let availableHistoryDays;
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
async function setLanguage(code, updatePreference=true) {
  if (!dictionaries[code]) {
    const response=await fetch(`/static/locales/${code}.json`);
    if(!response.ok) throw new Error(t('network_error'));
    dictionaries[code]=await response.json();
  }
  locale=code; localStorage.setItem('stop-clop-language',code); document.documentElement.lang=code;
  document.title=t('page_title');
  document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
  document.querySelectorAll('[data-i18n-aria]').forEach(el=>el.setAttribute('aria-label',t(el.dataset.i18nAria)));
  if(availableHistoryDays!==undefined)updatePeriodAvailability(availableHistoryDays);
  $('header-language').value=code; if(updatePreference)$('language').value=code; authLabels();renderNavigation();
}
function disconnected() {
  resetCoaching();showView("today");history.replaceState(null,"",location.pathname+location.search);
  preferenceBaseline=null;pendingEntry=null; token=''; sessionStorage.removeItem('stop-clop-token'); settings=null;
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
  return path.split('?')[0].endsWith('.csv')?response.blob():response.json();
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
  $('auth-email-label').hidden=!(registering&&catalog.email_required);$('auth-email').required=registering&&catalog.email_required;
  $('currency').replaceChildren(...catalog.currencies.map(c=>new Option(`${c.code} — ${c.name}`,c.code,false,c.code===selected)));
  timezoneOptions();pricePrecision();
  $('initial-timezone').textContent=t('initial_timezone',detectedTimezone());
}
const preferenceFields={pack_price:'pack-price',currency:'currency',pack_size:'pack-size',daily_target:'daily-target',language:'language',timezone:'timezone'};
let preferenceBaseline=null;
function preferenceDraft(){return Object.fromEntries(Object.entries(preferenceFields).map(([key,id])=>[key,$(id).value]));}
async function syncPreferences(prefs,force=false){
  const draft=preferenceDraft(),dirty=new Set();
  if(preferenceBaseline&&!force)for(const key of Object.keys(preferenceFields))if(draft[key]!==preferenceBaseline[key])dirty.add(key);
  // Keep a price paired with its selected currency while the user is editing either.
  if(dirty.has('currency')||dirty.has('pack_price')){dirty.add('currency');dirty.add('pack_price');}
  const oldTimezone=settings?.timezone,changedLanguage=locale!==prefs.language;
  settings=prefs;
  if(changedLanguage)await setLanguage(prefs.language,false);
  if(!catalog||changedLanguage)await loadCatalog();
  const baseline={};
  for(const [key,id] of Object.entries(preferenceFields)){
    const value=dirty.has(key)?draft[key]:String(prefs[key]);
    if(key==='timezone')timezoneOptions(value);else $(id).value=value;
    baseline[key]=dirty.has(key)?preferenceBaseline[key]:String(prefs[key]);
  }
  preferenceBaseline=baseline;pricePrecision();
  if(force||oldTimezone!==prefs.timezone)localInputNow();
}
function preferenceChanges(){
  const draft=preferenceDraft(),changes={};
  for(const key of Object.keys(preferenceFields))if(draft[key]!==preferenceBaseline[key])changes[key]=draft[key];
  if('currency' in changes||'pack_price' in changes){changes.currency=draft.currency;changes.pack_price=draft.pack_price;}
  for(const key of ['pack_size','daily_target'])if(key in changes)changes[key]=Number(changes[key]);
  return changes;
}
async function loadHistory(append=false){
  if(!append){historyOffset=0;$('history').replaceChildren();}
  const data=await api(`/cigarettes?${query()}&limit=20&offset=${historyOffset}`);
  $('history-range').textContent=dayLabel($('start-date').value)+' — '+dayLabel($('end-date').value);
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
function updatePeriodAvailability(available){
  availableHistoryDays=available;
  for(const count of [30,90]){
    const option=$('preset').querySelector(`[value="${count}"]`);option.disabled=available<count;
    option.textContent=t(count===30?'last_30':'last_90')+(option.disabled?' — '+t('waiting_data'):'');
  }
  $('history-availability').textContent=available<90?t('waiting_data')+' · '+t('history_wait',number(available)):'';
  $('history-availability').hidden=available>=90;
}
async function refresh(){
  await syncPreferences(await api('/settings'));
  if($('preset').value!=='custom')setRange(Number($('preset').value));
  let data=await api(`/stats?${query()}`);
  const available=data.history_days;
  updatePeriodAvailability(available);
  if(['30','90'].includes($('preset').value)&&available<Number($('preset').value)){
    $('preset').value='7';setRange(7);data=await api(`/stats?${query()}`);
  }
  $('today-count').textContent=number(data.today.quantity);$('today-cost').textContent=t('today_cost',costs(data.today));
  $('selected-period').textContent=dayLabel($('start-date').value)+' — '+dayLabel($('end-date').value);
  $('period-count').textContent=number(data.period.quantity);$('period-cost').textContent=costs(data.period);
  $('average').textContent=t('average',number(data.period.average_per_day),number(data.period.days));
  $('all-time').textContent=`${t('quantity_count',number(data.total.quantity))} · ${costs(data.total)}`;
  $('target-label').textContent=t('target_label',number(settings.daily_target));$('timezone-label').textContent=t('timezone_label',data.timezone);
  analysisData=data;renderAnalysis();
  await loadHistory();
  await loadCoaching();
}
let analysisData;
const signed=value=>(value>0?'+':'')+number(value);
const percent=value=>value===null?'—':signed(value)+'%';
function renderAnalysis(){
  if(!analysisData)return;
  const a=analysisData.analysis,comparison=a.comparison;
  renderHabits(a);
  $('analysis-average-quantity').textContent=number(a.average_quantity_per_day);
  $('analysis-average-cost').textContent=costs({costs:a.average_cost_per_day});
  $('analysis-range').textContent=t('analysis_range',number(a.minimum_quantity),number(a.maximum_quantity),number(a.days_with_entries));
  $('analysis-today').hidden=!a.includes_today;
  $('analysis-previous').textContent=a.previous_period.days?t('previous_dates',dayLabel(a.previous_period.start),dayLabel(a.previous_period.end)):t('no_comparison');
  $('analysis-comparison').textContent=comparison.quantity_delta===null?'—':t('quantity_count',signed(comparison.quantity_delta))+' ('+percent(comparison.quantity_percent)+')';
  $('analysis-cost-comparison').textContent=Object.entries(comparison.cost_deltas).map(([code,value])=>(value>0?'+':'')+money(value,code)+' ('+percent(comparison.cost_percent[code])+')').join(' · ');
  const codes=Object.keys(a.average_cost_per_day),selected=$('chart-currency').value;
  $('chart-currency').replaceChildren(...codes.map(code=>new Option(code,code,false,code===selected)));
  const costMode=$('chart-measure').value==='cost',code=$('chart-currency').value;
  $('chart-currency-label').hidden=!costMode;
  $('chart').setAttribute('aria-label',t(costMode?'cost':'daily_consumption'));
  const average=costMode?a.average_cost_per_day[code]:a.average_quantity_per_day;
  const smooth=$('chart-smooth').checked,series=smooth?a.trend:a.daily;
  $('trend-note').hidden=!smooth;
  const values=series.map(day=>costMode?day.costs[code]:day.quantity),max=Math.max(1,average,...values);
  $('chart').replaceChildren();$('daily-table').replaceChildren();
  for(const [index,day] of a.daily.entries()){
    const value=values[index],col=document.createElement('div');col.className='bar-column';
    col.title=dayLabel(day.date)+' : '+(costMode?money(value,code):t('quantity_count',number(value)));
    const slot=document.createElement('div');slot.className='bar-slot';
    const bar=document.createElement('div');bar.className='bar';bar.style.height=`${value/max*135}px`;
    const mean=document.createElement('div');mean.className='mean-tick';mean.style.bottom=`${average/max*135}px`;
    slot.append(bar,mean);col.append(cell(number(value),'b'),slot,cell(day.date.slice(8),'span'));$('chart').append(col);
    const tr=document.createElement('tr');
    tr.append(cell(dayLabel(day.date)),cell(number(day.quantity)),cell(signed(day.quantity_delta)+' ('+percent(day.quantity_percent)+')'),cell(costs(day)),
      cell(Object.entries(day.cost_deltas).map(([currency,delta])=>(delta>0?'+':'')+money(delta,currency)+' ('+percent(day.cost_percent[currency])+')').join(' · ')));
    $('daily-table').append(tr);
  }
}
action('chart-measure','change',renderAnalysis);
action('chart-currency','change',renderAnalysis);
action('chart-smooth','change',renderAnalysis);
async function loadTokens(){
  const rows=await api('/tokens');for(const id of ['tokens','sessions','legacy-tokens'])$(id).replaceChildren();
  for(const row of rows){
    const session=row.kind==='session',legacy=row.kind==='legacy';
    const li=document.createElement('li'),name=document.createElement('div');
    name.textContent=(session?t(row.client==='android'?'session_android':'session_web'):row.name)+(row.current?t('current_session'):'');
    const format=value=>new Date(value).toLocaleString(locale,{dateStyle:'medium',timeStyle:'short',timeZone:settings?.timezone||'UTC'});
    if(row.created_at)name.append(cell(t('session_created',format(row.created_at)),'small'));
    name.append(cell(t('expires',format(row.expires_at)),'small'));
    const button=document.createElement('button');button.className='danger';button.textContent=t(session?'logout':'revoke');
    button.onclick=async()=>{
      if(!confirm(t('revoke_confirm')))return;button.disabled=true;
      try{await api(`/tokens/${row.id}`,'DELETE');if(row.current)disconnected();else await loadTokens();}catch(err){notice(err.message,true);button.disabled=false;}
    };li.append(name,button);$(session?'sessions':legacy?'legacy-tokens':'tokens').append(li);
  }
  const sessions=rows.filter(row=>row.kind==='session');
  $('session-count').textContent=number(sessions.length);
  $('keys-empty').hidden=rows.some(row=>row.kind==='api');
  $('sessions-empty').hidden=sessions.length>0;
  $('legacy-access').hidden=!rows.some(row=>row.kind==='legacy');
  $('revoke-other-sessions').disabled=!sessions.some(row=>!row.current);
}
$('revoke-other-sessions').addEventListener('click',async()=>{
  if(!confirm(t('revoke_other_confirm')))return;
  $('revoke-other-sessions').disabled=true;
  try{await api('/sessions/others','DELETE');await loadTokens();notice(t('other_sessions_revoked'));}
  catch(err){notice(err.message,true);$('revoke-other-sessions').disabled=false;}
});

async function connected(){
  showView(location.hash.slice(1));
  const me=await api('/me');
  if(me.role==='admin'){location.replace('/admin');return;}
  $('user-email-state').textContent=t(me.email_verified?'email_verified':'email_pending');$('user-email-form').elements.recovery_email.value=me.email||'';
  const prefs=await api('/settings');
  await syncPreferences(prefs,true);
  $('username').textContent=me.username;$('auth').hidden=true;$('dashboard').hidden=false;$('identity').hidden=false;
  setRange(Number($('preset').value)||30);localInputNow();await Promise.all([refresh(),loadTokens()]);
}
action('header-language','change',async()=>{
  const next=$('header-language').value;
  $('header-language').disabled=true;$('logout').disabled=true;
  try{if(token)settings=await api('/settings','PUT',{language:next});await setLanguage(next);if(preferenceBaseline)preferenceBaseline.language=next;await loadCatalog();if(token)await Promise.all([refresh(),loadTokens()]);}
  finally{$('header-language').value=locale;$('header-language').disabled=false;$('logout').disabled=false;}
});
action('auth-switch','click',()=>{
  registering=!registering;authLabels();$('auth-email-label').hidden=!(registering&&catalog.email_required);$('auth-email').required=registering&&catalog.email_required;$('password-help').hidden=!registering;$('initial-timezone').hidden=!registering;
  const p=$('auth-form').elements.password;p.minLength=registering?12:1;p.autocomplete=registering?'new-password':'current-password';
});
action('auth-form','submit',async()=>{
  const payload={...Object.fromEntries(new FormData($('auth-form'))),language:locale,client:'web'};
  if(registering)payload.timezone=detectedTimezone();
  const response=await api(`/auth/${registering?'register':'login'}`,'POST',payload);
  if(response.activation_required){notice(response.message);return;}
  token=response.token;sessionStorage.setItem('stop-clop-token',token);$('auth-form').reset();await connected();
});
action('delete-account-form','submit',async()=>{
  const username=$('username').textContent;
  try{await api('/me','DELETE',{password:$('delete-account-password').value,confirm:$('delete-account-confirm').checked});}
  finally{$('delete-account-password').value='';}
  for(const key of Object.keys(localStorage))if(key.startsWith('stop-clop-reminder-'+username+'-'))localStorage.removeItem(key);
  sessionStorage.removeItem('stop-clop-craving-'+username);
  disconnected();
  for(const id of ['delete-account-form','journey-form','settings-form','entry-form'])$(id).reset();
  notice(t('account_deleted'));
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
  await saveEntry({quantity:Number($('quantity').value),occurred_at_local:$('occurred-at').value,source:'web',trigger:$('entry-trigger').value});
  localInputNow();notice(t('entry_saved'));await refresh();
});
action('preset','change',async()=>{$('range-form').hidden=$('preset').value!=='custom';if($('preset').value!=='custom'){setRange(Number($('preset').value));await refresh();}});
action('range-form','submit',async()=>{$('preset').value='custom';await refresh();});
action('refresh','click',async()=>{if($('preset').value!=='custom')setRange(Number($('preset').value));await Promise.all([refresh(),loadTokens()]);});
action('more-history','click',()=>loadHistory(true));
action('timezone-search','input',()=>timezoneOptions());
document.querySelector('.settings').addEventListener('toggle',()=>{
  if(document.querySelector('.settings').open)loadCatalog().catch(err=>notice(err.message,true));
});
action('currency','change',()=>{pricePrecision();$('pack-price').value='';$('pack-price').focus();});
action('settings-form','submit',async()=>{
  const changes=preferenceChanges();
  await syncPreferences(await api('/settings','PUT',changes),true);
  notice(t('settings_saved'));await Promise.all([refresh(),loadTokens()]);
});
action('token-form','submit',async()=>{const result=await api('/tokens','POST',{name:$('token-name').value});$('token-value').value=result.token;$('new-token').hidden=false;await loadTokens();});
action('export','click',async()=>{const blob=await api(`/export.csv?${query()}`),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='suuless.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
initializeNavigation();
initializeCoaching();
(async()=>{await setLanguage(locale);await loadCatalog();if(token)await connected();})().catch(err=>notice(err.message,true));

function renderHabits(a){
  $('habits-note').textContent=t('habits_note',analysisData.timezone);
  $('habits-empty').hidden=a.hourly.some(hour=>hour.quantity>0);
  $('hourly-chart').replaceChildren();$('hourly-figures').replaceChildren();
  const max=Math.max(1,...a.hourly.map(hour=>hour.quantity));
  for(const hour of a.hourly){
    const label=t('hourly_value',String(hour.hour).padStart(2,'0'),number(hour.quantity),number(hour.share_percent));
    const col=document.createElement('div');col.className='bar-column'+(hour.quantity===max?' peak':'');col.title=label;col.setAttribute('role','listitem');col.setAttribute('aria-label',label);
    const slot=document.createElement('div');slot.className='bar-slot';
    const bar=document.createElement('div');bar.className='bar';bar.style.height=`${hour.quantity/max*135}px`;slot.append(bar);
    col.append(cell(number(hour.quantity),'b'),slot,cell(String(hour.hour).padStart(2,'0'),'span'));$('hourly-chart').append(col);
    $('hourly-figures').append(cell(label,'li'));
  }
  const weekdayMax=Math.max(1,...a.weekdays.map(day=>day.average||0));$('weekday-chart').replaceChildren();
  for(const day of a.weekdays){
    const label=new Intl.DateTimeFormat(locale,{weekday:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2024,0,1+day.weekday)));
    const row=document.createElement('div');row.className='habit-row';
    const text=day.average===null?label+' · '+t('no_sample'):t('weekday_value',label,number(day.average),number(day.days));
    row.append(cell(text,'span'));
    const meter=document.createElement('meter');meter.max=weekdayMax;meter.value=day.average||0;meter.setAttribute('aria-label',text);row.append(meter);$('weekday-chart').append(row);
  }
  const p=a.projection;
  $('projection-quantity').textContent=p.quantity===null?'—':t('quantity_count',number(p.quantity));
  $('projection-cost').textContent=costs(p);
  $('projection-note').textContent=p.sample_days?t('projection_note',number(p.sample_days)):t('projection_empty');
}

action('user-email-form','submit',async()=>{
  const form=$('user-email-form');
  try{const response=await api('/account/email','POST',{email:form.elements.recovery_email.value,password:form.elements.current_password.value});$('user-email-state').textContent=t('email_pending');notice(response.message);}
  finally{form.elements.current_password.value='';}
});
