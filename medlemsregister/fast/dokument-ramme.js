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

/* Lasting kan vere ferdig før meldingslyttaren er registrert. */
document.querySelectorAll('[data-dokument-ramme]').forEach(frame => {
 const fit = () => {
  try {
   const paper = frame.contentDocument?.querySelector('.paper');
   if (!paper) return;
   const height = Math.ceil(paper.getBoundingClientRect().bottom + frame.contentWindow.scrollY + 24);
   if (Number.isFinite(height) && height >= 100 && height <= 100000) frame.style.height = height + 'px';
  } catch { /* Kryssopphav får berre bruke den kontrollerte meldingskanalen. */ }
 };
 frame.addEventListener('load', fit);
 fit();
});
