/* Godta berre høgdemeldingar frå sjølve dokumentramma på same opphav. */
if(!window.bygdelistaDocumentFrames){
 window.bygdelistaDocumentFrames=true;
 window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.data?.type!=='bygdelista-document-height')return;
  const height=event.data.height;
  if(!Number.isFinite(height)||height<100||height>100000)return;
  document.querySelectorAll('[data-dokument-ramme]').forEach(frame=>{if(frame.contentWindow===event.source)frame.style.height=Math.ceil(height)+'px';});
 });
}
