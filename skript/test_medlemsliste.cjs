const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.join(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'medlemsregister/fast/medlemsliste.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'medlemsregister/malar/index.html'), 'utf8').replace(/{%[\s\S]*?%}|{{[\s\S]*?}}/g, '');
const members = Array.from({length:31}, (_,i) => ({id:i+1, fornamn:`Medlem ${String(i+1).padStart(2,'0')}`, etternamn:'Test', email:`member${i+1}@example.test`, membership_type:i%2?'kul':'vanleg', payment_status:i%2?'betalt':'ikkje betalt', total_paid_ore:0}));
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
async function start(data=members, fail=false) {
  const dom = new JSDOM(html, {url:'https://example.test/', runScripts:'outside-only'});
  const {window:w} = dom;
  w.Request = Request; w.Headers = Headers;
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
  w.HTMLDialogElement.prototype.close = function() { this.open = false; };
  w.localStorage.setItem('bygdelista-kolonner',JSON.stringify({epost:false}));
  const calls=[];
  w.fetch = async (url, options={}) => {
    calls.push([url,options]);
    const summary=String(url).endsWith('/api/medlemsoversikt');
    return {ok:!fail, status:fail?500:200, json:async () => fail?{error:'Prøv igjen seinare'}:summary?{medlemsbetalingsar:2026,antall_medlemer_totalt:data.length,totalt_innbetalt_ore:0}:data};
  };
  w.eval(script); await tick(); await tick();
  return {w,dom,calls,d:w.document};
}
test('Søk, filter, sortering og sideinndeling verkar saman på heile medlemsutvalet', async () => {
  const {w,d} = await start();
  assert.equal(d.querySelectorAll('#medlem-liste tr').length,25);
  assert.equal(d.getElementById('medlem-sidetal').textContent,'Side 1 av 2');
  d.getElementById('medlem-neste').click();
  assert.equal(d.querySelectorAll('#medlem-liste tr').length,6);
  const query=d.getElementById('medlem-soketekst'); query.value='member31@'; query.dispatchEvent(new w.Event('input'));
  assert.equal(d.querySelectorAll('#medlem-liste tr').length,1);
  assert.equal(d.getElementById('medlem-forre').disabled,true);
  d.getElementById('medlem-status').value='Betalt'; d.getElementById('medlem-status').dispatchEvent(new w.Event('change'));
  assert.equal(d.getElementById('medlem-ingen').hidden,false);
  d.getElementById('medlem-nullstill').click();
  assert.equal(query.value,''); assert.equal(d.querySelectorAll('#medlem-liste tr').length,25);
  d.getElementById('medlem-sortering').value='desc'; d.getElementById('medlem-sortering').dispatchEvent(new w.Event('change'));
  assert.match(d.querySelector('#medlem-liste tr').textContent,/Medlem 31/);
  assert.equal(d.querySelector('#medlem-liste td[data-col="epost"]').classList.contains('kolonne-skjult'),true);
  w.close();
});
test('Detaljar er trygt formaterte, og statusen kan ikkje endrast ved eit klikk i lista', async () => {
  const {w,d,calls} = await start([{...members[0],fornamn:'<img src=x onerror=alert(1)>'}]);
  d.querySelector('.medlem-lenkje').click();
  assert.equal(d.getElementById('medlem-detalj').open,true);
  assert.equal(d.querySelector('#medlem-detalj img'),null);
  assert.match(d.getElementById('medlem-detalj-tittel').textContent,/<img/);
  assert.equal(d.querySelector('[data-action="toggle-payment"]'),null);
  assert.equal(calls.some(([,o]) => o.method==='PUT'),false);
  w.close();
});
test('API-feil blir viste som feil, ikkje som ei tom medlemsliste', async () => {
  const {w,d} = await start([],true);
  assert.match(d.getElementById('status').textContent,/Prøv igjen seinare/);
  assert.notEqual(d.getElementById('medlem-treff').textContent,'Ingen treff');
  w.close();
});

test('Kontingentinnstillingar blir lagra frå økonomisida med CSRF og feilhandtering', async () => {
  const source=fs.readFileSync(path.join(root,'medlemsregister/malar/kontingent.html'),'utf8').replace(/{%[\s\S]*?%}|{{[\s\S]*?}}/g,'');
  const dom=new JSDOM(source,{url:'https://example.test/kontingent',runScripts:'outside-only'});
  const {window:w}=dom;const d=w.document;d.querySelector('meta[name="csrf-token"]').content='test-csrf';
  const calls=[];
  w.fetch=async (url,options)=>{calls.push([url,options]);return {ok:true,json:async()=>String(url).endsWith('medlemsoversikt')?{medlemsbetalingsar:2026}:{superkul_grense_ore:500}};};
  w.eval(fs.readFileSync(path.join(root,'medlemsregister/fast/kontingent-innstillingar.js'),'utf8'));
  await tick();await tick();
  const field=d.getElementById('superkul-grense');assert.equal(field.value,'5.00');assert.equal(field.disabled,false);
  field.value='10';d.getElementById('kontingent-innstillingar').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
  const write=calls.find(([,o])=>o.method==='PUT');assert.ok(write);assert.equal(write[1].headers['X-CSRF-Token'],'test-csrf');
  assert.equal(JSON.parse(write[1].body).superkul_grense_nok,'10');assert.match(d.getElementById('kontingent-status').textContent,/lagra/);
  w.fetch=async()=>({ok:false,json:async()=>({error:'Satsen er låst'})});
  d.getElementById('kontingent-innstillingar').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
  assert.match(d.getElementById('kontingent-status').textContent,/Satsen er låst/);assert.equal(d.getElementById('lagre-kontingent').disabled,false);
  w.close();
});
