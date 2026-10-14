'use strict';
let coachingData,coachingFormPlan,coachingDirty=false,coachingSequence=0,coachingOffset=0;
const triggerValues=['','coffee','stress','meal','social','boredom','other'];
const strategyValues=['walk','water','breathe','distract'];
const supportResources={
  FR:['Tabac info service','https://www.tabac-info-service.fr/j-arrete-de-fumer/mes-outils-tabac-info-service'],
  GB:['NHS · Better Health','https://www.nhs.uk/better-health/quit-smoking/'],
  JP:['厚生労働省 · e-ヘルスネット','https://kennet.mhlw.go.jp/information/information/tobacco-summaries/t-06'],
  other:['WHO · Tobacco cessation','https://www.who.int/health-topics/tobacco']
};
function coachingOptions(id,values,label){
  const selected=$(id).value;$(id).replaceChildren(...values.map(value=>new Option(label(value),value,false,value===selected)));
}
function coachingDay(offset){const d=new Date(coachingData.local_today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+offset);return d.toISOString().slice(0,10);}
function resetCoaching(){coachingSequence++;coachingData=null;coachingFormPlan=null;coachingDirty=false;$('craving-dialog').close();}
async function loadCoaching(force=false){
  const session=token,sequence=++coachingSequence,data=await api('/coaching');
  if(session!==token||sequence!==coachingSequence)return;
  coachingData=data;coachingOffset=Date.parse(data.now)-Date.now();
  renderCoaching(force);checkCoachingReminders();
}
function addJourneyStep(step={date:coachingData.local_today,goal:0}){
  const row=document.createElement('div');row.className='journey-step';
  for(const [name,type,label] of [['date','date','day'],['goal','number','daily_target']]){
    const wrapper=document.createElement('label');const caption=cell(t(label),'span');caption.dataset.i18n=label;wrapper.append(caption);
    const input=document.createElement('input');input.type=type;input.value=step[name];input.dataset.field=name;input.required=true;
    input.min=name==='date'?'2000-01-01':'0';if(name==='goal')input.max='200';wrapper.append(input);row.append(wrapper);
  }
  const remove=document.createElement('button');remove.type='button';remove.className='quiet';remove.textContent=t('delete');remove.dataset.i18n='delete';remove.onclick=()=>{row.remove();coachingDirty=true;};row.append(remove);$('journey-steps').append(row);
}
function renderCoaching(force=false){
  const d=coachingData,p=d.plan;
  $('journey-mode-label').textContent=t(`mode_${p.mode}`);$('journey-reason').textContent=p.reason;
  $('journey-goal').textContent=d.current_goal===null?'':t('goal_today',number(d.current_goal),number(d.days.at(-1).quantity));
  if(d.current_goal!==null)$('target-label').textContent=$('journey-goal').textContent;
  $('journey-zero').textContent=t('smoke_free_total',number(d.confirmed_smoke_free_days));$('journey-passed').textContent=t('cravings_passed',number(d.cravings_passed));
  $('journey-clock').textContent='';if(d.quit_since){const hours=Math.max(0,Math.floor((Date.parse(d.now)-Date.parse(d.quit_since))/3600000));$('journey-clock').textContent=t('quit_clock',number(Math.floor(hours/24)),number(hours%24));}
  const selected=$('checkin-day').value||coachingDay(-1);$('checkin-day').replaceChildren(...[...d.days].reverse().map(day=>new Option(dayLabel(day.date),day.date,false,day.date===selected)));renderCheckin();
  if(force||!coachingDirty){
    coachingFormPlan=structuredClone(p);coachingDirty=false;
    for(const [id,key] of Object.entries({'journey-mode':'mode','journey-motivation':'reason','journey-quit':'quit_date','journey-goal-input':'daily_goal','daily-time':'daily_time','weekly-time':'weekly_time','quiet-start':'quiet_start','quiet-end':'quiet_end'}))$(id).value=p[key]??'';
    $('daily-enabled').checked=p.daily_enabled;$('weekly-enabled').checked=p.weekly_enabled;
    coachingOptions('weekly-day',['0','1','2','3','4','5','6'],day=>new Intl.DateTimeFormat(locale,{weekday:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2024,0,1+Number(day)))));$('weekly-day').value=String(p.weekly_day);
    coachingOptions('journey-strategy',strategyValues,value=>t(`strategy_${value}`));$('journey-strategy').value=p.strategy;
    coachingOptions('support-country',['other','FR','GB','JP'],value=>value==='other'?t('support_other'):new Intl.DisplayNames(locale,{type:'region'}).of(value));$('support-country').value=p.country;
    $('journey-steps').replaceChildren();for(const step of p.steps)addJourneyStep(step);
  }
  for(const id of ['entry-trigger','craving-trigger'])coachingOptions(id,triggerValues,value=>t(value?`trigger_${value}`:'trigger_none'));
  coachingOptions('craving-strategy',strategyValues,value=>t(`strategy_${value}`));
  $('baseline-form').hidden=!!p.baseline;
  if(p.baseline){const b=p.baseline;$('baseline-summary').textContent=t('baseline_summary',dayLabel(b.start),dayLabel(b.end),number(b.quantity/b.days),b.timezone);}
  else {$('baseline-summary').textContent='';if(!$('baseline-start').value)$('baseline-start').value=coachingDay(-7);if(!$('baseline-end').value)$('baseline-end').value=coachingDay(-1);$('baseline-start').max=coachingDay(-1);$('baseline-end').max=coachingDay(-1);}
  const progress=d.progress;
  $('progress-summary').textContent=progress?.confirmed_days?t(progress.quantity_difference<0?'progress_increase':'progress_value',number(Math.abs(progress.quantity_difference)),number(Math.abs(progress.reduction_percent)),number(progress.confirmed_days)):t('progress_missing');
  $('progress-costs').textContent=progress?costs({costs:progress.estimated_cost_difference}):'';
  $('weekly-dates').textContent=dayLabel(d.weekly.start)+' — '+dayLabel(d.weekly.end);
  $('weekly-summary').textContent=t('weekly_value',number(d.weekly.current.quantity),number(d.weekly.previous.quantity),number(d.weekly.current.confirmed_days));$('weekly-costs').textContent=costs(d.weekly.current);
  $('trigger-summary').replaceChildren(...d.triggers.filter(row=>row.cigarettes||row.cravings).map(row=>cell(t('trigger_summary',t(`trigger_${row.trigger}`),number(row.cigarettes),number(row.cravings),number(row.passed)),'li')));
  if(!$('trigger-summary').children.length)$('trigger-summary').append(cell(t('no_entries'),'li'));
  const resource=supportResources[p.country];$('support-link').textContent=resource[0];$('support-link').href=resource[1];
  renderCraving();
}
function renderCheckin(){
  const day=coachingData?.days.find(day=>day.date===$('checkin-day').value);if(!day)return;
  $('checkin-status').textContent=t(day.confirmed?'confirmed_day':'unconfirmed_day')+' · '+t('quantity_count',number(day.quantity));
  $('confirm-day').textContent=t('confirm_day',number(day.quantity));$('confirm-day').hidden=day.confirmed;$('unconfirm-day').hidden=!day.confirmed;
}
function renderCraving(){
  const craving=coachingData?.pending_craving;$('craving-form').hidden=!!craving;$('craving-active').hidden=!craving;
  if(craving)$('craving-activity').textContent=t(`strategy_${craving.strategy}`);
  updateCravingClock();
}
function updateCravingClock(){
  const craving=coachingData?.pending_craving;if(!craving)return;
  const seconds=Math.max(0,Math.ceil((Date.parse(craving.pause_until)-Date.now()-coachingOffset)/1000));
  $('craving-clock').textContent=seconds?t('pause_remaining',String(Math.floor(seconds/60)),String(seconds%60).padStart(2,'0')):t('pause_done');
}
function checkCoachingReminders(){
  if(!coachingData||document.visibilityState!=='visible')return;
  const p=coachingData.plan,day=coachingData.local_today,at=coachingData.local_datetime.slice(11,16);
  const a=p.quiet_start,b=p.quiet_end;if(a<b?at>=a&&at<b:a>b&&(at>=a||at<b))return;
  const weekday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7;
  for(const kind of ['daily','weekly']){
    if(!p[kind+'_enabled']||at<p[kind+'_time']||(kind==='weekly'&&weekday!==p.weekly_day))continue;
    const key='stop-clop-reminder-'+$('username').textContent+'-'+kind+'-'+day;
    if(localStorage.getItem(key))continue;localStorage.setItem(key,'1');notice(t(`${kind}_reminder_message`));
  }
}
function initializeCoaching(){
  $('journey-form').addEventListener('input',()=>coachingDirty=true);$('journey-form').addEventListener('change',()=>coachingDirty=true);
  action('add-step','click',()=>{if($('journey-steps').children.length<30){addJourneyStep();coachingDirty=true;}});
  action('reload-journey','click',()=>loadCoaching(true));
  action('journey-form','submit',async()=>{
    const values={mode:$('journey-mode').value,reason:$('journey-motivation').value,quit_date:$('journey-quit').value||null,daily_goal:Number($('journey-goal-input').value),strategy:$('journey-strategy').value,country:$('support-country').value,
      daily_enabled:$('daily-enabled').checked,daily_time:$('daily-time').value,weekly_enabled:$('weekly-enabled').checked,weekly_time:$('weekly-time').value,weekly_day:Number($('weekly-day').value),quiet_start:$('quiet-start').value,quiet_end:$('quiet-end').value,
      steps:[...$('journey-steps').children].map(row=>({date:row.querySelector('[data-field=date]').value,goal:Number(row.querySelector('[data-field=goal]').value)}))};
    const changes={version:coachingFormPlan.version};for(const [key,value] of Object.entries(values))if(JSON.stringify(value)!==JSON.stringify(coachingFormPlan[key]))changes[key]=value;
    await api('/coaching/plan','PUT',changes);coachingDirty=false;await refresh();notice(t('plan_saved'));
  });
  action('baseline-form','submit',async()=>{await api('/coaching/baseline','POST',{start:$('baseline-start').value,end:$('baseline-end').value});await loadCoaching();});
  action('checkin-day','change',renderCheckin);
  action('confirm-day','click',async()=>{const day=coachingData.days.find(day=>day.date===$('checkin-day').value);await api('/check-ins/'+day.date,'PUT',{quantity:day.quantity});await loadCoaching();});
  action('unconfirm-day','click',async()=>{await api('/check-ins/'+$('checkin-day').value,'DELETE');await loadCoaching();});
  action('open-craving','click',async()=>{await loadCoaching();$('craving-strategy').value=coachingData.plan.strategy;$('craving-dialog').showModal();});
  action('close-craving','click',()=>{$('craving-dialog').close();});
  action('craving-form','submit',async()=>{
    const key='stop-clop-craving-'+$('username').textContent;
    let pending=JSON.parse(sessionStorage.getItem(key)||'null');
    if(!pending){pending={key:Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join(''),payload:{trigger:$('craving-trigger').value,strategy:$('craving-strategy').value,minutes:Number($('craving-minutes').value)}};sessionStorage.setItem(key,JSON.stringify(pending));}
    await api('/cravings','POST',pending.payload,{'Idempotency-Key':pending.key});sessionStorage.removeItem(key);await loadCoaching();
  });
  for(const outcome of ['passed','smoked','cancelled'])action('craving-'+outcome,'click',async()=>{
    if(!coachingData.pending_craving)return;await api('/cravings/'+coachingData.pending_craving.id,'PUT',{outcome});$('craving-dialog').close();await refresh();
  });
  action('progress-export','click',async()=>{const blob=await api('/coaching/export.csv'),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='suuless-progress.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  setInterval(updateCravingClock,1000);
  setInterval(()=>{if(token&&!$('dashboard').hidden&&document.visibilityState==='visible')loadCoaching().catch(()=>{});},60000);
}
