/* Last opp utan å navigere bort frå den utfylte posten. */
(()=>{
 const form=document.getElementById('post-form');if(!form)return;
 const panel=document.getElementById('post-bilag-upload');
 const file=document.getElementById('post-bilag-fil');
 const status=document.getElementById('post-bilag-status');
 const select=form.elements.namedItem('receipt_id');
 const submit=document.getElementById('bokfor-post');
 const explanation=document.getElementById('post-forklaring');
 const errors=document.getElementById('post-feil');
 const check=document.getElementById('post-kontroller-status');
 let busy=false,unresolved=false;let initiallyDisabled=submit.disabled;
 form.noValidate=true;
 const vippsPanel=document.getElementById('vipps-samla');
 const kindField=form.elements.namedItem('kind');
 function vippsFields(){
  const active=kindField.value==='vipps_income_settled';vippsPanel.hidden=!active;
  const a=Number(form.elements.namedItem('amount').value.replace(',','.'));
  const fee=Number(form.elements.namedItem('fee').value.replace(',','.'));
  document.getElementById('vipps-netto').textContent=Number.isFinite(a-fee)?new Intl.NumberFormat('nn-NO',{style:'currency',currency:'NOK'}).format(a-fee):'Kontroller beløpa';
 }
 form.addEventListener('input',vippsFields);kindField.addEventListener('change',vippsFields);kindField.addEventListener('guided-kind',vippsFields);vippsFields();
 panel.hidden=false;
 async function refreshStatus(){
  try{
   const day=form.elements.namedItem('day').value;
   const year=/^\d{4}-/.test(day)?day.slice(0,4):form.dataset.year;
   const response=await fetch(form.dataset.statusUrl+'?year='+encodeURIComponent(year),{headers:{Accept:'application/json'},credentials:'same-origin'});
   if(!response.ok)throw new Error();const result=await response.json();
   initiallyDisabled=!result.ready;submit.disabled=initiallyDisabled||busy||unresolved;
   explanation.textContent=result.ready?'Klart for bokføring. Fyll ut dato, beløp og skildring, og vel bilag eller forklar dokumentasjonen.':result.reason;
  }catch(error){explanation.textContent='Status kunne ikkje kontrollerast. Behald skjemaet og prøv kontrollknappen igjen.';}
 }
 check.addEventListener('click',refreshStatus);window.addEventListener('focus',refreshStatus);
 form.elements.namedItem('day').addEventListener('change',refreshStatus);
 form.addEventListener('submit',event=>{
  if(busy||unresolved){event.preventDefault();status.textContent='Vent på opplastinga, eller fjern filvalet før du bokfører.';file.focus();return;}
  const missing=[];
  const kind=form.elements.namedItem('kind').value;
  for(const [name,label] of [['day','Dato'],['amount','Beløp'],['public_text','Offentleg skildring']]){
   if(!form.elements.namedItem(name).value.trim())missing.push(label);
  }
  if(['private_expense','invoice','private_refund','private_forgiveness','pay_invoice'].includes(kind)&&!form.elements.namedItem('party').value.trim())missing.push('Namn på utleggshavar eller leverandør');
  if(!select.value&&!form.elements.namedItem('evidence_note').value.trim())missing.push('Bilag eller forklaring på dokumentasjon utan bilag');
  if(kind==='refund_income'&&!form.elements.namedItem('original_id').value.trim())missing.push('Originalpostnummer');
  if(kind==='vipps_income_settled'){
   if(!form.elements.namedItem('settlement_day').value)missing.push('Oppgjersdato');
   if(!form.elements.namedItem('vipps_not_booked').checked)missing.push('Stadfesting av at Vipps-innkome og oppgjer ikkje er førte frå før');
   if(!['membership','donations'].includes(form.elements.namedItem('category').value))missing.push('Kategori: Medlemspengar eller Gåver');
  }
  errors.replaceChildren();errors.hidden=!missing.length;
  if(missing.length){event.preventDefault();const title=document.createElement('strong');title.textContent='Du må fylle ut:';errors.append(title);const list=document.createElement('ul');missing.forEach(text=>{const item=document.createElement('li');item.textContent=text;list.append(item);});errors.append(list);errors.focus();return;}
  if(!form.checkValidity()){event.preventDefault();form.reportValidity();}

 });
 file.addEventListener('change',async()=>{
  const selected=file.files[0];unresolved=!!selected;
  if(!selected){submit.disabled=initiallyDisabled;status.textContent='Ingen ny fil vald.';return;}
  submit.disabled=true;
  if(selected.size>10*1024*1024||selected.size===0){status.textContent='Bruk ei fil mellom 1 byte og 10 MiB. Vel ei anna fil, eller fjern filvalet.';return;}
  busy=true;file.disabled=true;status.textContent='Lastar opp bilaget. Skjemaet blir ståande.';
  const data=new FormData();data.append('csrf_token',form.elements.namedItem('csrf_token').value);data.append('file',selected);
  try{
   const response=await fetch(form.dataset.uploadUrl,{method:'POST',body:data,headers:{Accept:'application/json'},credentials:'same-origin'});
   if(!response.ok)throw new Error();
   const receipt=await response.json();
   if(!Number.isInteger(receipt.id)||typeof receipt.name!=='string')throw new Error();
   const option=new Option('B'+receipt.id+' – '+receipt.name,String(receipt.id),true,true);
   select.add(option);select.value=String(receipt.id);
   status.textContent='Bilag B'+receipt.id+' er lasta opp og valt. Kontroller resten og trykk «Bokfør post».';
   file.value='';unresolved=false;
  }catch(error){
   status.textContent='Opplastinga vart ikkje stadfesta. Skjemafelta er bevarte. Kontroller bilagsoversikta i ei ny fane før nytt forsøk, så du unngår dobbel opplasting. Bruk PDF, JPEG eller PNG.';
  }finally{busy=false;file.disabled=false;submit.disabled=initiallyDisabled||unresolved;}
 });
})();
