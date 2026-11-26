/* Stegvis utfylling. Felt blir verande i same skjema og blir berre sende ved innsending. */
(() => {
  'use strict';
  const profiles = {
    post: [
      ['Kva har skjedd?', 'purpose payment_method vipps_state expense_paid kind'],
      ['Beløp og betaling', 'day amount settlement_day vipps_not_booked account target category fee party original_id'],
      ['Skildring og dokumentasjon', 'public_text internal_note receipt_id evidence_note event_uid payment_id'],
    ],
    medlem: [
      ['Namn og kontakt', 'fornamn mellomnamn etternamn email phone'],
      ['Adresse og alder', 'adresse postnummer poststad birth_date'],
      ['Medlemskap', 'membership_type payment_status approve-payment-status'],
    ],
    tilskiping: [
      ['Tilskipinga', 'tittel kind stad'],
      ['Dato og tid', 'dato start slutt sluttdato'],
      ['Omtale og bilete', 'merknad lenkje bilete'],
    ],
    kontingent: [
      ['År og satsar', 'year minimum threshold'],
      ['Opning og vedtak', 'opens_on approved_on approved'],
    ],
    galleri: [
      ['Vel bilete eller film', 'media poster'],
      ['Tekst og plassering', 'tekst fotograf position'],
    ],
    styret: [
      ['Namn og verv', 'name role'],
      ['Portrett og styreår', 'portrait current'],
    ],
    opning: [
      ['Pengar og krav ved starten av året', 'bank vipps cash prepaid receivable'],
      ['Gjeld og dokumentasjon', 'private payable party note'],
    ],
    budsjett: [
      ['Om budsjettet', 'title meeting_year'],
      ['Innkome', 'amount_membership amount_grants amount_donations amount_event_income amount_interest amount_other_income'],
      ['Utgifter', 'amount_domain amount_events amount_beer amount_fees amount_other_expense'],
      ['Omtale og føresetnader', 'note'],
    ],
  };
  const controls = node => [...(node.matches('input:not([type="hidden"]),select,textarea') ? [node] : []), ...node.querySelectorAll('input:not([type="hidden"]),select,textarea')];
  const fields = form => [...form.elements].filter(el => el.matches('input:not([type="hidden"]),select,textarea') && !el.hasAttribute('data-steg-ui'));
  const isSubmit = node => node.matches('button:not([type]),button[type="submit"],input[type="submit"]');
  const submits = node => isSubmit(node) || [...node.querySelectorAll('button,input')].some(isSubmit);
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const matches = (key, pattern) => pattern.endsWith('*') ? key.startsWith(pattern.slice(0, -1)) : key === pattern;
  // Hidden by conditional form logic is different from hidden by this step view.
  function relevant(field, form) {
    if (field.disabled || field.type === 'password') return false;
    for (let node = field; node && node !== form; node = node.parentElement) {
      if (node.hidden && !node.hasAttribute('data-steg-panel')) return false;
    }
    return true;
  }
  function label(field) {
    const source = field.labels?.[0];
    if (!source) return field.name || field.id || 'Felt';
    const copy = source.cloneNode(true);
    copy.querySelectorAll('input,select,textarea,small,.feltforklaring').forEach(node => node.remove());
    return copy.textContent.replace(/\s+/g, ' ').replace(/\s*\*$/, '').trim();
  }
  function value(field) {
    if (field.type === 'checkbox' || field.type === 'radio') return field.checked ? (field.type === 'checkbox' ? 'Ja' : field.value) : 'Ikkje valt';
    if (field.type === 'file') return [...field.files].map(file => file.name).join(', ') || 'Inga ny fil vald';
    if (field.tagName === 'SELECT') return [...field.selectedOptions].map(option => option.textContent.trim()).join(', ');
    return field.value.trim() || 'Ikkje fylt ut';
  }
  function enhance(form) {
    if (form.dataset.stegKlar) return;
    if (!profiles[form.dataset.steg] && fields(form).length <= 3 && !form.hasAttribute('data-steg-kontroll')) return;
    const units = [...form.children].filter(node => !node.matches('input[type="hidden"],script,template'));
    const actionUnits = units.filter(node => submits(node) && !controls(node).length);
    if (!actionUnits.length) return;
    const steps = [];
    const profile = profiles[form.dataset.steg];
    function step(title) {
      const panel = make('section', '', 'skjemasteg-panel');
      panel.dataset.stegPanel = '';
      const item = {title, panel};
      steps.push(item);
      return item;
    }
    if (profile) profile.forEach(([title]) => step(title));
    let current = null;
    for (const unit of units) {
      if (actionUnits.includes(unit)) continue;
      // Live errors/status must remain reachable on every step, including AJAX errors.
      if (unit.matches('[role="alert"],#skjema-feil,#betaling-feil,#post-feil,#post-forklaring,#post-kontroller-status')) continue;
      const inputs = controls(unit);
      if (!inputs.length && !current) continue;
      if (profile && inputs.length) {
        const index = profile.findIndex(([, patterns]) => inputs.some(field => patterns.split(' ').some(pattern => matches(field.name || field.id, pattern))));
        current = steps[index < 0 ? steps.length - 1 : index];
      } else if (!profile && inputs.length) {
        if (unit.matches('[data-steg-del],fieldset,details') || !current || controls(current.panel).length + inputs.length > 4) {
          const title = unit.dataset.stegDel || unit.querySelector(':scope > legend,:scope > summary,h2,h3')?.textContent.trim() || label(inputs[0]);
          current = step(title);
        }
      }
      if (current) current.panel.append(unit);
    }
    const activeSteps = steps.filter(item => controls(item.panel).length);
    if (!activeSteps.length) return;
    const review = step('Kontroller og fullfør');
    const summary = make('div', '', 'skjemasteg-oppsummering');
    review.panel.append(make('p', 'Kontroller opplysningane. Bruk «Endre» for å rette eit svar. Bruk knappen nedanfor når du vil fullføre.'), summary);
    const actions = make('div', '', 'skjemasteg-innsending');
    actionUnits.forEach(node => actions.append(node));
    const panels = [...activeSteps, review];
    form.dataset.stegKlar = 'yes';
    form.classList.add('skjemasteg');
    form.noValidate = true;
    const top = make('div', '', 'skjemasteg-topp');
    const progress = make('p'); progress.setAttribute('aria-live', 'polite');
    const heading = make('h2'); heading.tabIndex = -1;
    top.append(progress, heading);
    let sectionSelect;
    if (form.hasAttribute('data-steg-redigering')) {
      const labelNode = make('label', 'Gå til del');
      sectionSelect = make('select'); sectionSelect.dataset.stegUi = '';
      panels.forEach((item, i) => sectionSelect.append(new Option(item.title, String(i))));
      sectionSelect.addEventListener('change', () => {
        const target = Number(sectionSelect.value);
        if (target === panels.length - 1 && !validate(fields(form))) return;
        show(target);
      });
      labelNode.append(sectionSelect); top.append(labelNode);
    }
    form.prepend(top);
    panels.forEach(item => form.append(item.panel));
    const bar = make('div', '', 'skjemasteg-knappar');
    const back = make('button', 'Tilbake', 'sekundaer'); back.type = 'button';
    const next = make('button', 'Neste'); next.type = 'button';
    bar.append(back, next, actions);
    // Cancel must be available without completing the form.
    actions.querySelectorAll('button[type="button"]').forEach(button => bar.append(button));
    const draft = [...actions.querySelectorAll('button')].find(button => /lagre utkast|lagre protokollen/i.test(button.textContent));
    let bypass = false;
    let draftShortcut;
    if (draft) {
      draftShortcut = make('button', /protokollen/i.test(draft.textContent) ? 'Lagre protokollen' : 'Lagre utkast', 'sekundaer'); draftShortcut.type = 'button';
      draftShortcut.addEventListener('click', () => { bypass = true; form.requestSubmit(draft); bypass = false; });
      bar.append(draftShortcut);
    }
    form.append(bar);
    let index = 0;
    function show(target, focus = true) {
      index = Math.max(0, Math.min(target, panels.length - 1));
      form.dataset.stegIndeks = String(index);
      panels.forEach((item, i) => { item.panel.hidden = i !== index; });
      progress.textContent = `Steg ${index + 1} av ${panels.length}`;
      heading.textContent = panels[index].title;
      if (sectionSelect) sectionSelect.value = String(index);
      panels[index].panel.querySelectorAll(':scope > details').forEach(details => {
        details.removeAttribute('name'); details.open = true; details.classList.add('skjemasteg-open-del');
      });
      back.hidden = index === 0;
      actions.hidden = index !== panels.length - 1;
      next.hidden = index === panels.length - 1;
      next.textContent = index === panels.length - 2 ? 'Kontroller opplysningane' : 'Neste';
      if (draftShortcut) draftShortcut.hidden = index === panels.length - 1;
      if (index === panels.length - 1) updateSummary();
      if (focus) { heading.focus({preventScroll: true}); top.scrollIntoView?.({block: 'start'}); }
    }
    function locate(field) {
      const target = panels.findIndex(item => item.panel.contains(field));
      if (target >= 0) show(target);
      field.dispatchEvent(new CustomEvent('skjemasteg:visfelt', {bubbles: true}));
      for (let parent = field.parentElement; parent && parent !== form; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS') parent.open = true;
      }
    }
    function validate(items) {
      const invalid = items.find(field => relevant(field, form) && !field.checkValidity());
      if (!invalid) return true;
      locate(invalid); invalid.focus(); invalid.reportValidity();
      return false;
    }
    function advance() {
      if (validate(fields(form).filter(field => panels[index].panel.contains(field)))) show(index + 1);
    }
    function updateSummary() {
      summary.replaceChildren();
      for (const [i, item] of activeSteps.entries()) {
        const shown = fields(form).filter(field => item.panel.contains(field) && relevant(field, form));
        if (!shown.length) continue;
        const section = make('section'); section.append(make('h3', item.title));
        const list = make('dl');
        for (const field of shown) {
          const row = make('div');
          const text = value(field);
          row.append(make('dt', label(field)), make('dd', text.length > 300 ? text.slice(0, 300) + ' …' : text));
          list.append(row);
        }
        const edit = make('button', 'Endre', 'sekundaer'); edit.type = 'button';
        edit.setAttribute('aria-label', 'Endre: ' + item.title);
        edit.addEventListener('click', () => show(i));
        section.append(list, edit); summary.append(section);
      }
      const note = document.getElementById('post-val-forklaring');
      if (form.dataset.steg === 'post' && note) summary.prepend(make('p', note.textContent, 'skjemasteg-verknad'));
    }
    back.addEventListener('click', () => show(index - 1));
    next.addEventListener('click', advance);
    form.addEventListener('submit', event => {
      if (bypass) return;
      if (index !== panels.length - 1) {
        event.preventDefault(); event.stopImmediatePropagation(); advance();
      } else if (!validate(fields(form))) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    }, true);
    // Existing handlers may detect domain errors only on submission.
    form.addEventListener('invalid', event => locate(event.target), true);
    form.addEventListener('skjemasteg:visfelt', event => {
      const target = panels.findIndex(item => item.panel.contains(event.target));
      if (target >= 0) show(target);
    });
    form.addEventListener('skjemasteg:start', () => show(0, false));
    form.addEventListener('skjemasteg:tilsteg', event => { if (Number.isInteger(event.detail)) show(event.detail, false); });
    form.addEventListener('reset', () => setTimeout(() => show(0, false), 0));
    // Changing a previous answer must pass through review again; values stay in the DOM.
    form.addEventListener('change', () => { if (index === panels.length - 1) updateSummary(); });
    show(0, false);
  }
  function paginate(list) {
    const items = [...list.children];
    const size = Number(list.dataset.stegListe) || 10;
    if (items.length <= size) return;
    const anchor = location.hash ? document.getElementById(location.hash.slice(1)) : null;
    const requested = items.findIndex(item => item.matches('details[open]') || (anchor && item.contains(anchor)));
    let page = requested < 0 ? 0 : Math.floor(requested / size);
    const bar = make('nav', '', 'skjemasteg-sider'); bar.setAttribute('aria-label', 'Sider i lista');
    const previous = make('button', 'Førre side', 'sekundaer'); previous.type = 'button';
    const next = make('button', 'Neste side', 'sekundaer'); next.type = 'button';
    const status = make('span'); status.setAttribute('aria-live', 'polite');
    bar.append(previous, status, next); list.after(bar);
    function show() {
      items.forEach((item, i) => { item.hidden = i < page * size || i >= (page + 1) * size; });
      status.textContent = `Side ${page + 1} av ${Math.ceil(items.length / size)}`;
      previous.disabled = page === 0; next.disabled = (page + 1) * size >= items.length;
    }
    previous.addEventListener('click', () => { page--; show(); });
    next.addEventListener('click', () => { page++; show(); });
    show();
  }
  function cases(root) {
    const bar = make('div', '', 'skjemasteg-saker');
    const labelNode = make('label', 'Sak du redigerer');
    const select = make('select'); select.dataset.stegUi = ''; labelNode.append(select); bar.append(labelNode); root.before(bar);
    let current;
    const rows = () => [...root.children].filter(node => node.tagName === 'FIELDSET');
    function show(row) {
      current = row;
      rows().forEach(item => { item.dataset.stegPanel = ''; item.hidden = item !== row; });
      select.value = String(rows().indexOf(row));
    }
    function refresh() {
      const list = rows();
      select.replaceChildren(...list.map((row, i) => new Option(row.querySelector('input')?.value || `Sak ${i + 1}`, String(i))));
      const focused = list.find(row => row.contains(document.activeElement));
      show(focused || (list.includes(current) ? current : list[0]));
      bar.hidden = list.length < 2;
    }
    select.addEventListener('change', () => show(rows()[Number(select.value)]));
    root.addEventListener('skjemasteg:visfelt', event => { const row = rows().find(item => item.contains(event.target)); if (row) show(row); });
    root.addEventListener('input', event => { if (event.target.matches('input')) { const row = rows().find(item => item.contains(event.target)); const i = rows().indexOf(row); if (i >= 0) select.options[i].textContent = row.querySelector('input').value || `Sak ${i + 1}`; } });
    new MutationObserver(refresh).observe(root, {childList: true});
    refresh();
  }
  function tasks(root) {
    const rows = [...root.children];
    const bar = make('div', '', 'skjemasteg-oppgaver');
    const labelNode = make('label', 'Vel kontrollpunkt');
    const select = make('select'); select.dataset.stegUi = ''; labelNode.append(select); bar.append(labelNode);
    const back = make('button', 'Førre punkt', 'sekundaer'); back.type = 'button';
    const next = make('button', 'Neste punkt', 'sekundaer'); next.type = 'button';
    const bottom = make('div', '', 'skjemasteg-knappar'); bottom.append(back, next);
    root.before(bar); root.after(bottom);
    const anchored = location.hash ? rows.findIndex(row => row.id === location.hash.slice(1)) : -1;
    let index = Math.max(0, anchored);
    if (anchored < 0 && root.dataset.opningKlar === 'yes') {
      const pending = rows.findIndex(row => row.matches('.arsavslutning-missing,.arsavslutning-difference,.arsavslutning-stale'));
      index = pending >= 0 ? pending : rows.length - (root.dataset.arAvslutta === 'yes' ? 1 : 2);
    }
    rows.forEach((row, i) => select.append(new Option(`${i + 1}. ${row.querySelector('h3,summary')?.textContent.trim() || 'Kontroll'}`, String(i))));
    function show(i) {
      index = i; select.value = String(i);
      rows.forEach((row, j) => { row.hidden = j !== i; });
      back.disabled = i === 0; next.disabled = i === rows.length - 1;
    }
    select.addEventListener('change', () => show(Number(select.value)));
    back.addEventListener('click', () => show(index - 1)); next.addEventListener('click', () => show(index + 1));
    window.addEventListener('hashchange', () => { const i = rows.findIndex(row => row.id === location.hash.slice(1)); if (i >= 0) show(i); });
    // Keep the submitted control visible when the server returns an error or difference.
    const filled = rows.findIndex(row => row.querySelector('input[name="actual"]')?.value);
    if (filled >= 0) index = filled;
    show(index);
  }
  // Run after page-specific scripts have installed their conditional-field logic.
  function start() {
    document.querySelectorAll('form[data-steg]').forEach(enhance);
    document.querySelectorAll('[data-steg-saker]').forEach(cases);
    document.querySelectorAll('[data-steg-oppgaver]').forEach(tasks);
    document.querySelectorAll('[data-steg-liste]').forEach(paginate);
    function revealAnchor() {
      const target = document.getElementById(location.hash.slice(1));
      if (!target) return;
      for (let node = target.parentElement; node; node = node.parentElement) if (node.tagName === 'DETAILS') node.open = true;
    }
    window.addEventListener('hashchange', revealAnchor); revealAnchor();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
