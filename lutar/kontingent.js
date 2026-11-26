/* Vedtekne satsar frå betalingsløysinga. Ingen gammal pris ved feil eller stengt år. */
(() => {
  const amount = new Intl.NumberFormat('nn-NO', {
    style: 'currency', currency: 'NOK', minimumFractionDigits: 0, maximumFractionDigits: 0,
  });
  const requests = new Map();
  function fetchRates(url) {
    if (!requests.has(url)) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      const request = fetch(url, {
        credentials: 'omit', cache: 'no-store', signal: controller.signal,
      }).then(response => {
        if (!response.ok) throw new Error('Rates unavailable');
        return response.json();
      }).finally(() => clearTimeout(timer));
      requests.set(url, request);
    }
    return requests.get(url);
  }
  for (const block of document.querySelectorAll('[data-kontingent-url]')) {
    fetchRates(block.dataset.kontingentUrl).then(rates => {
      if (!rates || rates.currency !== 'NOK' || !Number.isSafeInteger(rates.year)
          || rates.year < 2026 || rates.year > 2100 || typeof rates.open !== 'boolean') return;
      const mode = block.dataset.kontingentVising;
      const text = block.querySelector('[data-kontingent-tekst]');
      if (!rates.open) {
        if (text) text.textContent = `Medlemsbetaling for ${rates.year} er ikkje open no.`;
        return;
      }
      if (!Number.isSafeInteger(rates.minimum_ore) || rates.minimum_ore < 100
          || !Number.isSafeInteger(rates.superkul_ore)
          || rates.superkul_ore < rates.minimum_ore) return;
      const minimum = amount.format(rates.minimum_ore / 100);
      if (mode === 'belop') {
        block.textContent = minimum;
      } else if (mode === 'kort') {
        block.textContent = `Medlemskap i ${rates.year}: frå ${minimum}.`;
      } else if (mode === 'merke') {
        const number = new Intl.NumberFormat('nn-NO', { maximumFractionDigits: 0 }).format(rates.minimum_ore / 100);
        block.querySelector('[data-kontingent-belop]').textContent = number;
        block.setAttribute('style', '--kontingent-storleik: ' + Math.min(112, 130 / (number.length * 0.7)) + 'px');
        block.setAttribute('aria-label', `Medlemskap i ${rates.year}: frå ${minimum}`);
        block.hidden = false;
      } else if (text) {
        text.textContent = `Medlemskap i ${rates.year}: frå ${minimum}. `
          + `Superkul ved beløp over ${amount.format(rates.superkul_ore / 100)}.`;
      }
    }).catch(() => {});
  }
})();
