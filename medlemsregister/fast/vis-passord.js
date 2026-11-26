/* Vis berre passordet når brukaren sjølv ber om det. */
(() => {
  const input = document.getElementById('password');
  const button = document.getElementById('vis-passord');
  if (!input || !button) return;

  const show = visible => {
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Skjul passord' : 'Vis passord';
    button.setAttribute('aria-pressed', String(visible));
  };
  button.hidden = false;
  button.addEventListener('click', () => show(input.type === 'password'));
  input.form?.addEventListener('submit', () => show(false));
  input.form?.addEventListener('reset', () => show(false));
  window.addEventListener('pageshow', () => show(false));
})();
