/* Bevar konteksten etter vanleg skjemainnsending. Ingen feltverdiar blir lagra. */
(()=>{
 const key='bygdelista-skjema-retur';
 const forms=()=>Array.from(document.forms);
 const year=()=>new URL(location.href).searchParams.get('year');
 document.addEventListener('submit',event=>{
  const form=event.target;
  if(!(form instanceof HTMLFormElement)||form.target==='_blank')return;
  if(/logout|logg-ut/.test(form.action))return;
  // API-skjema som hindrar vanleg innsending styrer si eiga vising.
  queueMicrotask(()=>{
   if(event.defaultPrevented)return;
   const destination=new URL(form.action||location.href,location.href);
   if(destination.origin!==location.origin)return;
   const state={path:location.pathname,year:year(),time:Date.now(),y:scrollY,
    formId:form.id,index:forms().indexOf(form),
    opened:Array.from(document.querySelectorAll('details')).map((node,index)=>node.open?index:-1).filter(index=>index>=0)};
   try{sessionStorage.setItem(key,JSON.stringify(state));}catch{}
  });
 });
 document.addEventListener('DOMContentLoaded',()=>{
  let state;
  try{state=JSON.parse(sessionStorage.getItem(key)||'null');sessionStorage.removeItem(key);}catch{return;}
  if(!state||state.path!==location.pathname||Date.now()-state.time>120000||(state.year&&year()&&state.year!==year()))return;
  const details=Array.from(document.querySelectorAll('details'));
  for(const index of state.opened||[])if(details[index])details[index].open=true;
  const error=Array.from(document.querySelectorAll('[role="alert"]')).find(node=>node.textContent.trim()&&node.getClientRects().length);
  const form=(state.formId&&document.getElementById(state.formId))||forms()[state.index];
  const messages=Array.from(document.querySelectorAll('[role="status"]')).filter(node=>node.textContent.trim()&&node.getClientRects().length);
  const banner=document.createElement('div');banner.className='skjema-retur-melding';banner.setAttribute('role','status');
  const text=document.createElement('span');
  text.textContent=error?'Kontroller meldinga og felta før du prøver igjen.':messages.length?messages[0].textContent.trim():'Sida er oppdatert.';
  banner.append(text);
  const close=document.createElement('button');close.type='button';close.textContent='Lukk';close.addEventListener('click',()=>banner.remove());banner.append(close);document.body.append(banner);
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
   if(error){error.closest('details')?.setAttribute('open','');error.setAttribute('tabindex','-1');error.focus({preventScroll:true});error.scrollIntoView({block:'center'});}
   else if(!location.hash){
    scrollTo(0,state.y);
   }
  }));
 });
})();
