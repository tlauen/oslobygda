/* Approved rates only; an unavailable service leaves the useful payment link. */
(() => {
  const amount = new Intl.NumberFormat('nn-NO', {
    style: 'currency', currency: 'NOK', maximumFractionDigits: 2,
  });
  for (const block of document.querySelectorAll('[data-kontingent-url]')) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    fetch(block.dataset.kontingentUrl, {
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
    })
      .then(response => {
        if (!response.ok) throw new Error('Rates unavailable');
        return response.json();
      })
      .then(rates => {
        if (rates.currency !== 'NOK' || !Number.isSafeInteger(rates.year)
            || rates.year < 2026 || rates.year > 2100 || typeof rates.open !== 'boolean') return;
        const text = block.querySelector('[data-kontingent-tekst]');
        if (!rates.open) {
          text.textContent = `Medlemsbetaling for ${rates.year} er ikkje open no.`;
          return;
        }
        if (!Number.isSafeInteger(rates.minimum_ore) || rates.minimum_ore < 100
            || !Number.isSafeInteger(rates.superkul_ore)
            || rates.superkul_ore < rates.minimum_ore) return;
        text.textContent = `Medlemskap i ${rates.year}: frå ${amount.format(rates.minimum_ore / 100)}. `
          + `Superkul ved beløp over ${amount.format(rates.superkul_ore / 100)}.`;
      })
      .catch(() => {})
      .finally(() => clearTimeout(timer));
  }
})();
