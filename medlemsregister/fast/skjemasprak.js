/* Nettlesaren sitt språk kan vere engelsk sjølv om sida er på nynorsk. */
(()=>{
 const isDate=field=>field instanceof HTMLInputElement&&field.type==='date';
 document.addEventListener('invalid',event=>{
  const field=event.target;if(!isDate(field))return;
  field.setCustomValidity('');
  if(field.validity.badInput||field.validity.typeMismatch)field.setCustomValidity('Skriv inn ein gyldig dato.');
  else if(field.validity.valueMissing)field.setCustomValidity('Vel ein dato.');
  else if(field.validity.rangeUnderflow)field.setCustomValidity('Vel ein dato på eller etter '+dateText(field.min)+'.');
  else if(field.validity.rangeOverflow)field.setCustomValidity('Vel ein dato på eller før '+dateText(field.max)+'.');
 },true);
 for(const type of ['input','change'])document.addEventListener(type,event=>{
  if(isDate(event.target))event.target.setCustomValidity('');
 });
 function dateText(value){const parts=value.split('-');return parts.length===3?Number(parts[2])+'.'+parts[1]+'.'+parts[0]:value;}
})();
