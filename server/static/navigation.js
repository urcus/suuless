'use strict';
const appViews=['today','journey','analysis','history','settings'];
let activeView='today';
function renderNavigation(){
  for(const name of appViews){
    document.getElementById('view-'+name).hidden=name!==activeView;
    const link=document.querySelector(`[data-view="${name}"]`);
    if(name===activeView)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  }
  const title=document.getElementById('view-title');title.dataset.i18n='view_'+activeView;title.textContent=t(title.dataset.i18n);
  const description=document.getElementById('view-description');description.dataset.i18n=activeView+'_intro';description.textContent=t(description.dataset.i18n);
  document.getElementById('today-label').textContent=t('tagline');
}
function showView(name,focus=false){
  activeView=appViews.includes(name)?name:'today';renderNavigation();
  if(focus){document.getElementById('view-title').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
}
function initializeNavigation(){
  window.addEventListener('hashchange',()=>{
    const name=location.hash.slice(1);if(appViews.includes(name))showView(name,!document.getElementById('dashboard').hidden);
  });
  document.querySelectorAll('.app-nav a,.quick-links a,.history-toolbar a').forEach(link=>link.addEventListener('click',()=>{
    if(link.hash===location.hash)showView(link.hash.slice(1),true);
  }));
}
