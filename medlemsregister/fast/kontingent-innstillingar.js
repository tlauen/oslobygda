/* Satsane blir lagra samla i årsskjemaet. Her avsluttar vi berre medlemsåret. */
(() => {
  const close = document.getElementById('btn-lukk-medlemsar');
  if (!close) return;
  const api = document.querySelector('meta[name="api-prefix"]').content;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const status = document.getElementById('kontingent-status');

  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('feil', error);
  }

  async function request(path, options = {}) {
    const response = await fetch(api + path, {
      credentials: 'same-origin',
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Kunne ikkje oppdatere medlemsåret.');
    return data;
  }

  async function loadYear() {
    const data = await request('/api/medlemsoversikt');
    close.dataset.year = data.medlemsbetalingsar;
    close.textContent = `Lukk medlemsår ${data.medlemsbetalingsar} og start ${Number(data.medlemsbetalingsar) + 1} …`;
    close.disabled = false;
  }

  close.addEventListener('click', async () => {
    const year = Number(close.dataset.year);
    if (!Number.isInteger(year)) return;
    if (!confirm(`Dette arkiverer medlemsår ${year}, startar ${year + 1} og oppdaterer betalingsstatus. Har du kontrollert betalingane og teke backup?`)) return;
    if (prompt(`Skriv ${year} for å stadfeste.`) !== String(year)) return;
    close.disabled = true;
    try {
      const data = await request('/api/medlemsar/lukk', {
        method: 'POST',
        body: JSON.stringify({bekreft_ar: year}),
      });
      message(data.message || 'Medlemsåret er avslutta.');
      await loadYear();
    } catch (error) {
      message(error.message, true);
      close.disabled = false;
    }
  });

  loadYear().catch(error => message(error.message, true));
})();
