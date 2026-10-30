/* Bruk berre den offentlege dokumentteksten, utan nettsidemenyar. */
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-dokument-pdf]');if(!button)return;
 const source=button.closest('.offentleg-okonomi')||button.closest('main')||button.parentElement.parentElement;
 const popup=window.open('','_blank');if(!popup)return;
 const doc=popup.document;doc.open();doc.write('<!doctype html><html lang="nn"><head><meta charset="utf-8"><title></title></head><body></body></html>');doc.close();
 doc.title=document.title;
 const loading=[];
 document.querySelectorAll('link[rel="stylesheet"],style').forEach(style=>{
  const copy=style.cloneNode(true);
  if(copy.tagName==='LINK'){copy.href=style.href;loading.push(new Promise(resolve=>{copy.onload=resolve;copy.onerror=resolve;}));}
  doc.head.append(copy);
 });
 const content=source.cloneNode(true);
 content.querySelectorAll('.dokument-pdf,.arsmelding-tilbake,script,button').forEach(node=>node.remove());
 const hasMainTable=Array.from(content.querySelectorAll('table')).some(table=>!table.closest('details'));
 const copies=Array.from(content.querySelectorAll('details'));
 copies.forEach((copy,index)=>{if(hasMainTable||index>0)copy.remove();else{copy.open=true;copy.querySelector('summary')?.remove();}});
 doc.body.append(content);
 const style=doc.createElement('style');style.textContent='@page{size:A4;margin:16mm}body{background:white!important;margin:0;padding:0;color:#12110e}h2,h3{break-after:avoid}tr,article.arsmelding-aktivitet{break-inside:avoid}table{width:100%}*{print-color-adjust:exact;-webkit-print-color-adjust:exact}';doc.head.append(style);
 await Promise.all(loading);await doc.fonts.ready;
 await Promise.all(Array.from(doc.images,img=>img.complete?Promise.resolve():new Promise(resolve=>{img.onload=resolve;img.onerror=resolve;})));
 popup.focus();popup.print();
});
