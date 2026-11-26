/* Små Markdown-snarvegar; textarea og serverførehandsvising verkar utan JavaScript. */
(() => {
  document.addEventListener('invalid', event => {
    for (let parent = event.target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') {
        parent.removeAttribute('name');
        parent.open = true;
      }
    }
  }, true);
  for (const field of document.querySelectorAll('textarea[data-markdown]')) {
    const disclosure = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Formatering';
    disclosure.append(summary);
    const tools = document.createElement('div');
    tools.setAttribute('role', 'group');
    tools.setAttribute('aria-label', 'Markdown for ' + (field.labels[0]?.textContent || 'tekst'));
    for (const [label, before, after, example] of [
      ['Feit', '**', '**', 'tekst'], ['Kursiv', '*', '*', 'tekst'],
      ['Lenkje', '[', '](/)', 'lenkjetekst'], ['Overskrift', '\n\n## ', '\n', 'Overskrift'],
      ['Liste', '\n- ', '\n', 'Listepunkt'],
    ]) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'sekundaer'; button.textContent = label;
      button.addEventListener('click', () => {
        const start = field.selectionStart;
        const selected = field.value.slice(start, field.selectionEnd) || example;
        field.setRangeText(before + selected + after, start, field.selectionEnd, 'select');
        field.focus();
        field.dispatchEvent(new Event('input', { bubbles: true }));
      });
      tools.append(button);
    }
    disclosure.append(tools);
    field.before(disclosure);
  }
})();
