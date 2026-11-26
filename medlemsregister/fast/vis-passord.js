/* Same kontroll ved alle passordfelt; passord er skjulte ved sideopning. */
(() => {
  const eye = '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>';
  const eyeOff = '<path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6.5 0 10 7 10 7a19 19 0 0 1-3 3.9M6.2 6.2A20 20 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.8-1.8M9.9 9.9a3 3 0 0 0 4.2 4.2"/>';
  document.querySelectorAll('input[type="password"]').forEach((input, index) => {
    if (!input.id) input.id = 'passordfelt-' + index;
    const wrapper = document.createElement('div');
    wrapper.className = 'innlogging-passord';
    input.before(wrapper);
    wrapper.append(input);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'passord-auge';
    button.setAttribute('aria-controls', input.id);
    const show = visible => {
      input.type = visible ? 'text' : 'password';
      const label = visible ? 'Skjul passord' : 'Vis passord';
      button.setAttribute('aria-label', label);
      button.title = label;
      button.setAttribute('aria-pressed', String(visible));
      button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (visible ? eye : eyeOff) + '</svg>';
    };
    show(false);
    wrapper.append(button);
    button.addEventListener('click', () => show(input.type === 'password'));
    input.form?.addEventListener('submit', () => show(false));
    input.form?.addEventListener('reset', () => show(false));
    window.addEventListener('pageshow', () => show(false));
  });
})();
