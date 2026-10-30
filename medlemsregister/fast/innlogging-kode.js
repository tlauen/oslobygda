/* Behald eitt vanleg skjemafelt. Vis siffer i faste ruter utan tekstrulling. */
(() => {
  const input = document.querySelector('.innlogging-kode');
  if (!input) return;
  const wrapper = input.closest('.innlogging-koderuter');
  const cells = [...wrapper.querySelectorAll('.innlogging-kodebakgrunn span')];
  const render = () => {
    const start = input.selectionStart ?? 0;
    const end = input.selectionEnd ?? start;
    cells.forEach((cell, index) => {
      cell.textContent = input.value[index] || '';
      cell.classList.toggle('er-markert', index >= start && index < end);
      cell.classList.toggle('er-aktiv', start === end && index === Math.min(start, 5));
    });
  };
  ['input', 'change', 'focus', 'blur', 'select', 'keyup', 'click'].forEach(event => {
    input.addEventListener(event, render);
  });
  document.addEventListener('selectionchange', () => {
    if (document.activeElement === input) render();
  });
  // Gjer klikk på kvar rute til ein tilsvarande tekstposisjon.
  input.addEventListener('pointerup', event => {
    const bounds = wrapper.getBoundingClientRect();
    const index = Math.max(0, Math.min(6, Math.floor((event.clientX - bounds.left) / (bounds.width / 6))));
    if (input.selectionStart === input.selectionEnd) {
      const position = Math.min(index, input.value.length);
      input.setSelectionRange(position, position);
    }
    render();
  });
  input.form?.addEventListener('reset', () => setTimeout(render, 0));
  window.addEventListener('pageshow', render);
  render();
  wrapper.classList.add('er-klar');
})();
