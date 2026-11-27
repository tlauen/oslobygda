/* Administrative innstillingar høyrer til Økonomi, ikkje medlemslista. */
(() => {
  const form = document.getElementById('kontingent-innstillingar');
  if (!form) return;
  const api = document.querySelector('meta[name="api-prefix"]').content;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const status = document.getElementById('kontingent-status');
  const save = document.getElementById('lagre-kontingent');
  const threshold = document.getElementById('superkul-grense');
  const close = document.getElementById('btn-lukk-medlemsar');
  const message = (text, error = false) => { status.textContent = text; status.classList.toggle('feil', error); };
  async function request(path, options = {}) {
    const response = await fetch(api + path, {credentials:'same-origin', ...options,
      headers:{'Content-Type':'application/json', 'X-CSRF-Token':csrf, ...options.headers}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Kunne ikkje oppdatere innstillingane.');
    return data;
  }
  async function loadYear() {
    const data = await request('/api/medlemsoversikt');
    close.dataset.year = data.medlemsbetalingsar;
    close.textContent = `Lukk medlemsår ${data.medlemsbetalingsar} og start ${Number(data.medlemsbetalingsar) + 1} …`;
    close.disabled = false;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); save.disabled = true;
    try {
      await request('/api/innstillingar/kontingent', {method:'PUT', body:JSON.stringify({superkul_grense_nok:threshold.value})});
      message('Grensa er lagra og medlemstypane er oppdaterte.');
    } catch (error) { message(error.message, true); }
    finally { save.disabled = false; }
  });
  close.addEventListener('click', async () => {
    const year = Number(close.dataset.year);
    if (!Number.isInteger(year) || !confirm(`Dette arkiverer medlemsår ${year}, startar ${year + 1} og oppdaterer betalingsstatus. Har du kontrollert betalingane og teke backup?`)) return;
    if (prompt(`Skriv ${year} for å stadfeste.`) !== String(year)) return;
    close.disabled = true;
    try {
      const data = await request('/api/medlemsar/lukk', {method:'POST', body:JSON.stringify({bekreft_ar:year})});
      message(data.message || 'Medlemsåret er avslutta.');
      await loadYear();
    } catch (error) { message(error.message, true); close.disabled = false; }
  });
  (async () => {
    try {
      const data = await request('/api/innstillingar/kontingent');
      threshold.value = (data.superkul_grense_ore / 100).toFixed(2);
      threshold.disabled = false; save.disabled = false;
      await loadYear();
    } catch (error) { message(error.message, true); }
  })();
})();
