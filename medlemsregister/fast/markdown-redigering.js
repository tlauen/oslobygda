/* Små Markdown-snarvegar; textarea og serverførehandsvising verkar utan JavaScript. */
(() => {
  for (const field of document.querySelectorAll('textarea[data-markdown]')) {
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
    field.before(tools);
  }
})();
