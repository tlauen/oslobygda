const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.join(__dirname, '..');
const script = name => fs.readFileSync(path.join(root, 'medlemsregister/fast', name), 'utf8');
const rendered = process.env.SKJEMASTEG_TESTDATA ? JSON.parse(fs.readFileSync(process.env.SKJEMASTEG_TESTDATA, 'utf8')) : {};
async function dom(html) {
  const instance = new JSDOM(html, {url: 'https://bygdelista.example.test/', runScripts: 'outside-only'});
  await new Promise(resolve => instance.window.document.addEventListener('DOMContentLoaded', resolve, {once: true}));
  instance.window.HTMLElement.prototype.scrollIntoView = function () {};
  return instance;
}
function start(instance) { instance.window.eval(script('skjemasteg.js')); }
function next(form) { form.querySelector('.skjemasteg-knappar > button:nth-child(2)').click(); }
function last(form) { return [...form.querySelectorAll(':scope > [data-steg-panel]')].at(-1); }
function shown(form) { return form.querySelector(':scope > [data-steg-panel]:not([hidden])'); }
function input(window, node, value) { node.value = value; node.dispatchEvent(new window.Event('input', {bubbles: true})); node.dispatchEvent(new window.Event('change', {bubbles: true})); }
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

for (const [url, html] of Object.entries(rendered)) {
  test(`Ekte skjema: bevar alle felt og innsendingar på ${url}`, async () => {
    const instance = await dom(html);
    const {window} = instance;
    if (url.includes('del=registrer')) {
      window.eval(script('post-sporsmal.js'));
      window.eval(script('bilag-post.js'));
    }
    const forms = [...window.document.querySelectorAll('form[data-steg]')];
    const dataEntries = form => [...new window.FormData(form)].sort(([a], [b]) => a.localeCompare(b));
    const before = forms.map(form => ({form, data: dataEntries(form), fields: [...form.elements]}));
    start(instance);
    for (const original of before) {
      assert.deepEqual(dataEntries(original.form), original.data, 'Oppdeling må ikkje endre POST-data');
      for (const field of original.fields) assert.equal(field.form, original.form, 'Originale feltnodar må bevarast');
      if (original.form.dataset.stegKlar) {
        assert.equal(original.form.querySelectorAll(':scope > [data-steg-panel]:not([hidden])').length, 1);
        assert.ok(original.form.querySelector('.skjemasteg-knappar'));
      }
    }
    window.close();
  });
}

test('Ingen bokføring eller innsending før kontrollsteget; rette felt og submitter blir bevarte', async () => {
  const instance = await dom(`<form data-steg="tekst" data-steg-kontroll><input type="hidden" name="csrf_token" value="secret-test"><label>Tittel<input name="title" required></label><label>Tekst<textarea name="body"></textarea></label><button name="action" value="save_publish">Publiser</button><button name="action" value="save">Lagre utkast</button></form>`);
  const {window} = instance; const form = window.document.querySelector('form');
  let submitted = 0, submitter;
  form.addEventListener('submit', event => { submitted++; submitter = event.submitter; event.preventDefault(); });
  start(instance);
  next(form); assert.equal(submitted, 0); assert.notEqual(shown(form), last(form));
  input(window, form.elements.title, '<script>no execution</script>');
  input(window, form.elements.body, 'Bevar denne teksten');
  // Enter has the same controlled transition as Next.
  form.requestSubmit(form.querySelector('button[value="save_publish"]'));
  assert.equal(submitted, 0); assert.equal(shown(form), last(form));
  assert.ok(form.querySelector('.skjemasteg-oppsummering').textContent.includes('<script>no execution</script>'));
  assert.equal(form.querySelector('.skjemasteg-oppsummering script'), null);
  form.querySelector('button[value="save_publish"]').click();
  assert.equal(submitted, 1); assert.equal(submitter.value, 'save_publish');
  form.querySelector('.skjemasteg-oppsummering button').click();
  assert.equal(form.elements.body.value, 'Bevar denne teksten');
  assert.equal(form.elements.csrf_token.value, 'secret-test');
  // An optional draft save can be used without traversing all the steps again.
  form.querySelector('.skjemasteg-knappar > button:last-child').click();
  assert.equal(submitted, 2); assert.equal(submitter.value, 'save');
  window.close();
});

test('Tilbake bevarer filval, og feil i eit tidlegare steg opnar feltet', async () => {
  const instance = await dom(`<form data-steg="galleri"><label>Fil<input type="file" name="media" required></label><label>Tekst<input name="tekst" required></label><button>Publiser</button></form>`);
  const {window} = instance; const form = window.document.querySelector('form');
  const file = form.elements.media;
  // Simulate a browser FileList; retain the real input node through all transitions.
  const selected = [new window.File(['data'], 'foto.jpg', {type: 'image/jpeg'})];
  Object.defineProperty(file, 'files', {value: selected});
  file.required = false; // jsdom cannot set the native file input's internal FileList.
  start(instance); next(form);
  input(window, form.elements.tekst, 'Bilettekst'); next(form);
  assert.equal(shown(form), last(form));
  form.elements.tekst.value = '';
  let submissions = 0;
  form.addEventListener('submit', event => { submissions++; event.preventDefault(); });
  form.querySelector('.skjemasteg-innsending button').click();
  assert.equal(submissions, 0); assert.equal(shown(form).contains(form.elements.tekst), true);
  form.querySelector('.skjemasteg-knappar > button').click();
  assert.equal(form.elements.media, file); assert.equal(file.files[0], selected[0]);
  window.close();
});

if (rendered['/okonomi?year=2026&del=registrer']) {
  test('Privat utlegg: vilkår, dokumentasjon og kontroll av verknaden før bokføring', async () => {
    const instance = await dom(rendered['/okonomi?year=2026&del=registrer']);
    const {window} = instance;
    window.eval(script('post-sporsmal.js')); window.eval(script('bilag-post.js')); start(instance);
    const form = window.document.getElementById('post-form');
    const f = name => form.elements.namedItem(name);
    next(form); assert.equal(shown(form).contains(f('purpose')), true);
    input(window, f('purpose'), 'expense');
    next(form); assert.equal(shown(form).contains(f('expense_paid')), true);
    input(window, f('expense_paid'), 'private'); next(form);
    assert.equal(shown(form).contains(f('amount')), true);
    input(window, f('day'), '2026-11-26'); input(window, f('amount'), '350');
    next(form); assert.equal(shown(form).contains(f('party')), true);
    input(window, f('party'), 'Torbjørn'); next(form);
    input(window, f('public_text'), 'Domene'); next(form);
    assert.notEqual(shown(form), last(form), 'Dokumentasjon er obligatorisk');
    input(window, f('evidence_note'), 'Kontrollert kvittering'); next(form);
    assert.equal(shown(form), last(form));
    assert.match(form.querySelector('.skjemasteg-verknad').textContent, /gjeld/);
    assert.equal(f('kind').value, 'private_expense');
    assert.equal(f('party').value, 'Torbjørn');
    assert.equal(f('payment_method').required, false, 'Skjulte inntektsfelt må ikkje blokkere utlegg');
    window.close();
  });
}

if (rendered['/sakliste/2027']) {
  test('Sakliste: legg til, flytt og fjern utan å miste dei andre sakene', async () => {
    const instance = await dom(rendered['/sakliste/2027']); const {window} = instance;
    for (const node of window.document.querySelectorAll('script:not([src])')) window.eval(node.textContent);
    start(instance);
    const rootNode = window.document.getElementById('saker');
    const original = rootNode.children.length;
    window.document.getElementById('ny-sak').click(); await tick();
    assert.equal(rootNode.children.length, original + 1);
    const added = rootNode.lastElementChild;
    input(window, added.querySelector('input'), 'Ny sak');
    added.querySelector('[data-move="up"]').click(); await tick();
    assert.equal(rootNode.children[original - 1], added);
    assert.equal(rootNode.querySelectorAll(':scope > fieldset:not([hidden])').length, 1);
    added.querySelector('[data-move="remove"]').click(); await tick();
    assert.equal(rootNode.children.length, original);
    const data = new window.FormData(rootNode.closest('form'));
    assert.equal(data.getAll('item_title').length, original, 'Alle saker skal sendast, også dei som ikkje blir viste');
    window.close();
  });
}

test('Lister har korte sider og bevarer val på tvers av sidene', async () => {
  const instance = await dom(`<form><div data-steg-liste="2">${[1,2,3,4,5].map(i => `<details ${i === 4 ? 'open' : ''}><summary>${i}</summary><input type="checkbox" name="selected" value="${i}"></details>`).join('')}</div><button>Kontroller</button></form>`);
  const {window} = instance; start(instance);
  const list = window.document.querySelector('[data-steg-liste]');
  const bar = list.nextElementSibling;
  assert.equal(bar.querySelector('span').textContent, 'Side 2 av 3');
  list.children[3].querySelector('input').checked = true;
  bar.querySelector('button').click();
  list.children[0].querySelector('input').checked = true;
  assert.deepEqual([...new window.FormData(list.closest('form')).getAll('selected')], ['1', '4']);
  assert.equal(list.querySelectorAll(':scope > :not([hidden])').length, 2);
  window.close();
});

test('Redigering kan hoppe mellom delar, og kontrollsteget fangar manglar', async () => {
  const instance = await dom(`<form data-steg="protokoll" data-steg-redigering data-steg-kontroll><label>Overskrift<input name="title" required></label><fieldset><legend>Sak 1</legend><label>Vedtak<textarea name="decision"></textarea></label></fieldset><button>Lagre protokollen</button></form>`);
  const {window} = instance; const form = window.document.querySelector('form');
  start(instance);
  const select = form.querySelector('.skjemasteg-topp select');
  input(window, select, '1');
  assert.equal(shown(form).contains(form.elements.decision), true);
  input(window, form.elements.decision, 'Vedtaket er bevart');
  input(window, select, '2');
  assert.equal(shown(form).contains(form.elements.title), true, 'Kontroll krev manglande obligatorisk felt');
  input(window, form.elements.title, 'Årsmøte'); input(window, select, '2');
  assert.equal(shown(form), last(form));
  assert.equal(form.querySelector('.skjemasteg-oppsummering').textContent.includes('Gå til del'), false);
  let saved = false;
  form.addEventListener('submit', event => { saved = true; event.preventDefault(); });
  input(window, select, '1');
  form.querySelector('.skjemasteg-knappar > button:last-child').click();
  assert.equal(saved, true, 'Protokollen kan lagrast undervegs utan å gå gjennom andre saker');
  window.close();
});

if (rendered['/okonomi?year=2026&del=kontroll']) {
  test('Årsavslutning viser eitt kontrollpunkt og bevarer utfylte saldoar', async () => {
    const instance = await dom(rendered['/okonomi?year=2026&del=kontroll']);
    const {window} = instance; start(instance);
    const list = window.document.querySelector('[data-steg-oppgaver]');
    const select = list.previousElementSibling.querySelector('select');
    input(window, select, '1');
    const field = list.children[1].querySelector('input[name="actual"]');
    input(window, field, '125');
    input(window, select, '2'); input(window, select, '1');
    assert.equal(field.value, '125');
    assert.equal(list.querySelectorAll(':scope > :not([hidden])').length, 1);
    window.close();
  });
}

test('Årsmeldinga viser ulagrede endringar og vernar dei ved andre handlingar', {skip: !rendered['/arsmote/1']}, async () => {
  const instance = await dom(rendered['/arsmote/1']);
  const w = instance.window;
  const d = w.document;
  for (const inline of d.querySelectorAll('script:not([src])')) w.eval(inline.textContent);
  const editor = d.getElementById('report-form');
  const title = editor.querySelector('[name="title"]');
  input(w, title, 'Endra tittel som ikkje er lagra');
  assert.match(d.getElementById('arsmelding-endringsstatus').textContent, /ikkje er lagra/);
  const leaving = new w.Event('beforeunload', {cancelable: true});
  w.dispatchEvent(leaving);
  assert.equal(leaving.defaultPrevented, true);
  w.confirm = () => false;
  const other = [...d.forms].find(form => form !== editor);
  const switching = new w.Event('submit', {bubbles: true, cancelable: true});
  other.dispatchEvent(switching);
  assert.equal(switching.defaultPrevented, true);
  assert.equal(title.value, 'Endra tittel som ikkje er lagra');
  const saving = new w.Event('submit', {bubbles: true, cancelable: true});
  editor.dispatchEvent(saving);
  assert.equal(saving.defaultPrevented, false);
  w.close();
});
