(() => {
  const form = document.querySelector('[data-minutes-form]');
  if (!form) return;
  const standard = 'Godkjent utan merknader.';
  function approval(checkbox) {
    const text = checkbox.closest('[data-decision]').querySelector('textarea');
    if (checkbox.checked) {
      if (!text.readOnly) text.dataset.previous = text.value === standard ? '' : text.value;
      text.value = standard;
      text.readOnly = true;
    } else {
      if (text.readOnly) text.value = text.dataset.previous || '';
      text.readOnly = false;
    }
  }
  form.querySelectorAll('[data-approval]').forEach(approval);
  form.addEventListener('change', event => {
    if (event.target.matches('[data-approval]')) approval(event.target);
  });
  function numberSubcases(container, index) {
    Array.from(container.children).forEach((row, subindex) => {
      row.querySelector('legend').textContent = `Undersak ${index + 1}.${subindex + 1}`;
      row.querySelector('input:not([type="checkbox"])').name = `sub_title_${index}`;
      row.querySelector('textarea').name = `sub_decision_${index}`;
      const checkbox = row.querySelector('[data-approval]');
      checkbox.name = `sub_approved_${index}`;
      checkbox.value = String(subindex);
      row.querySelector('[data-remove-subcase]').setAttribute('aria-label', `Fjern undersak ${index + 1}.${subindex + 1}`);
    });
  }
  form.querySelectorAll('[data-case-index]').forEach(row => numberSubcases(row.querySelector('[data-subcases]'), Number(row.dataset.caseIndex)));
  form.addEventListener('click', event => {
    const button = event.target.closest('[data-add-subcase], [data-remove-subcase]');
    if (!button) return;
    const parent = button.closest('[data-case-index]');
    const container = parent.querySelector('[data-subcases]');
    if (button.hasAttribute('data-add-subcase')) {
      container.append(document.getElementById('protokoll-undersak-mal').content.cloneNode(true));
      numberSubcases(container, Number(parent.dataset.caseIndex));
      container.lastElementChild.querySelector('input').focus();
    } else {
      button.closest('[data-subcase]').remove();
      numberSubcases(container, Number(parent.dataset.caseIndex));
      parent.querySelector('[data-add-subcase]').focus();
    }
  });
})();
