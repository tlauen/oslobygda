/* Vis berre spørsmål og felt som høyrer til det brukaren faktisk gjer. */
(()=>{
 const form=document.getElementById('post-form');if(!form)return;
 const field=name=>form.elements.namedItem(name);
 const questions=document.getElementById('post-sporsmal');questions.hidden=false;field('guided').value='yes';
 const note=document.getElementById('post-val-forklaring');
 const label=name=>field(name)?.closest('label');
 const originalOptions=Array.from(field('category').options,option=>option.cloneNode(true));
 const display=(name,on)=>{const row=label(name);if(row)row.hidden=!on;};
 function sync(){
  const purpose=field('purpose').value,method=field('payment_method').value,paid=field('expense_paid').value;
  let state=field('vipps_state').value;
  const combinedOption=field('vipps_state').querySelector('option[value="settled_new"]');
  combinedOption.disabled=purpose==='other_income';
  if(combinedOption.disabled&&state==='settled_new'){field('vipps_state').value='';state='';}
  const incoming=['membership','donations','other_income'].includes(purpose),advanced=purpose==='other';
  questions.querySelector('[data-question="income"]').hidden=!incoming;
  questions.querySelector('[data-question="vipps"]').hidden=!(incoming&&method==='vipps');
  questions.querySelector('[data-question="expense"]').hidden=purpose!=='expense';
  let kind='income',account='bank',message='Vel kva du vil registrere, så viser me dei relevante felta.';
  if(incoming){
   account=method||'bank';
   if(method==='vipps'&&state==='settled_new')kind='vipps_income_settled';
   if(method==='vipps'&&state==='settled_booked')kind='vipps_settlement';
   message=kind==='vipps_income_settled'?'Du registrerer innkoma og overføringa til bank i eitt steg. Skriv beløpet før gebyr.':kind==='vipps_settlement'?'Du registrerer berre overføringa og gebyret. Innkoma blir ikkje telt på nytt.':method==='vipps'?'Du registrerer innkoma. Pengane blir ståande som Vipps til gode til dei er utbetalte.':'Du registrerer pengar laget har fått.';
  }else if(purpose==='expense'){
   kind=paid==='private'?'private_expense':paid==='unpaid'?'invoice':'expense';account=['bank','cash','vipps'].includes(paid)?paid:'bank';
   message=kind==='private_expense'?'Utgifta blir registrert, og laget får gjeld til personen som la ut.':kind==='invoice'?'Utgifta blir registrert som ei rekning laget skuldar leverandøren.':'Du registrerer ei utgift som laget har betalt.';
  }else if(purpose==='repayment'){kind='private_refund';message='Du registrerer ei tilbakebetaling som alt er gjord. Gjelda går ned; dette er inga ny utgift.';}
  else if(purpose==='forgive'){kind='private_forgiveness';message='Gjelda til personen blir redusert, og beløpet blir ført som ei gåve. Ingen pengar blir flytta. Bruk same namn som på utlegget. Legg ved ei datert stadfesting frå personen som ettergir gjelda, eller skriv stadfestinga i dokumentasjonsgrunnlaget.';}
  else if(purpose==='pay_invoice'){kind='pay_invoice';message='Du registrerer at ei tidlegare ført rekning er betalt. Kostnaden blir ikkje telt på nytt.';}
  if(!advanced){field('kind').value=kind;field('account').value=account;}
  else kind=field('kind').value;
  document.getElementById('post-avansert-hjelp').hidden=!advanced;
  display('kind',advanced);display('account',advanced);display('target',advanced&&kind==='transfer');
  const selected=field('category').value;
  const allowed=purpose==='membership'?['membership']:purpose==='donations'?['donations']:purpose==='other_income'?['grants','event_income','interest','other_income']:purpose==='expense'?['domain','events','beer','fees','other_expense']:originalOptions.map(x=>x.value);
  field('category').replaceChildren(...originalOptions.filter(x=>allowed.includes(x.value)).map(x=>x.cloneNode(true)));
  if(allowed.includes(selected))field('category').value=selected;
  display('category',purpose==='other_income'||purpose==='expense'||advanced);
  display('party',['private_expense','invoice','private_refund','private_forgiveness','pay_invoice'].includes(kind));
  const partyLabel=label('party');
  partyLabel.querySelector('.post-feltnamn').textContent=kind==='private_forgiveness'?'Kven ettergir gjelda?':'Intern utleggshavar/leverandør (bruk same namn ved refusjon)';
  partyLabel.querySelector('.feltforklaring').textContent=kind==='private_forgiveness'?'Skriv nøyaktig same namn som på det private utlegget.':'Til dømes Torbjørn. Bruk nøyaktig same namn når laget seinare betalar utlegget tilbake.';
  display('fee',kind==='vipps_income_settled'||kind==='vipps_settlement');
  display('original_id',advanced&&kind==='refund_income');display('event_uid',advanced);display('payment_id',advanced);
  // The combined panel supplies only the extra date and confirmation; hide its technical introduction.
  const combined=document.getElementById('vipps-samla');
  combined.querySelector('legend').textContent='Når kom pengane til banken?';
  const paragraphs=combined.querySelectorAll('p');if(paragraphs[0])paragraphs[0].hidden=true;
  note.textContent=message;
  field('kind').dispatchEvent(new Event('guided-kind'));
 }
 for(const name of ['purpose','payment_method','vipps_state','expense_paid'])field(name).addEventListener('change',sync);
 field('kind').addEventListener('change',()=>{if(field('purpose').value==='other')sync();});
 form.addEventListener('submit',event=>{
  let message='';const purpose=field('purpose').value;
  if(!purpose)message='Vel kva du ønskjer å registrere.';
  else if(['membership','donations','other_income'].includes(purpose)&&!field('payment_method').value)message='Vel korleis pengane vart betalte.';
  else if(['membership','donations','other_income'].includes(purpose)&&field('payment_method').value==='vipps'&&!field('vipps_state').value)message='Svar på om pengane er betalte vidare frå Vipps.';
  else if(purpose==='expense'&&!field('expense_paid').value)message='Vel kven som betalte.';
  if(message){event.preventDefault();event.stopImmediatePropagation();note.textContent=message;field('purpose').focus();}
 });
 sync();
})();
