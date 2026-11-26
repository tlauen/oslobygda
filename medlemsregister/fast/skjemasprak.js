/* Nettlesaren sitt språk kan vere engelsk sjølv om sida er på nynorsk. */
(()=>{
 const isField=field=>field instanceof HTMLInputElement||field instanceof HTMLSelectElement||field instanceof HTMLTextAreaElement;
 document.addEventListener('invalid',event=>{
  const field=event.target;if(!isField(field))return;
  field.setCustomValidity('');
  const validity=field.validity;
  const isDate=field.type==='date';
  let message='';
  if(validity.badInput)message=isDate?'Skriv inn ein gyldig dato.':'Skriv inn eit gyldig tal.';
  else if(validity.valueMissing){
   if(field.type==='checkbox')message='Kryss av her for å gå vidare.';
   else if(field.type==='radio'||field instanceof HTMLSelectElement)message='Vel eit alternativ.';
   else message=isDate?'Vel ein dato.':'Fyll ut dette feltet.';
  }
  else if(validity.typeMismatch)message=field.type==='email'?'Skriv inn ei gyldig e-postadresse.':(field.type==='url'?'Skriv inn ei gyldig nettadresse.':'Kontroller verdien i dette feltet.');
  else if(validity.patternMismatch)message=field.name==='postnummer'?'Skriv inn eit postnummer med fire siffer.':(field.name==='code'?'Skriv inn koden med åtte siffer.':'Følg formatet som er oppgitt for feltet.');
  else if(validity.rangeUnderflow)message=isDate?'Vel ein dato på eller etter '+dateText(field.min)+'.':'Verdien må vere minst '+field.min+'.';
  else if(validity.rangeOverflow)message=isDate?'Vel ein dato på eller før '+dateText(field.max)+'.':'Verdien må vere høgst '+field.max+'.';
  else if(validity.stepMismatch)message=field.step==='1'?'Skriv inn eit heilt tal.':'Skriv inn ein verdi med rett intervall.';
  else if(validity.tooLong)message='Bruk høgst '+field.maxLength+' teikn.';
  else if(validity.tooShort)message='Bruk minst '+field.minLength+' teikn.';
  field.setCustomValidity(message);
 },true);
 for(const type of ['input','change'])document.addEventListener(type,event=>{
  if(isField(event.target))event.target.setCustomValidity('');
 });
 function dateText(value){const parts=value.split('-');return parts.length===3?Number(parts[2])+'.'+parts[1]+'.'+parts[0]:value;}
})();
