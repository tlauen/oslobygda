const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const source = readFileSync(new URL('../lutar/kontingent.js', `file://${__filename}`), 'utf8');

async function render(payload, { fail = false, ok = true } = {}) {
  const text = { textContent: 'Gjeldande pris og medlemsår finn du i betalingsskjemaet.' };
  const block = { dataset: { kontingentUrl: 'https://example.test/api/kontingent' }, querySelector: () => text };
  const calls = [];
  vm.runInNewContext(source, {
    document: { querySelectorAll: () => [block] },
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (fail) throw new Error('offline');
      return { ok, json: async () => payload };
    },
    AbortController, setTimeout, clearTimeout,
  });
  await new Promise(resolve => setImmediate(resolve));
  return { text: text.textContent, calls };
}

test('viser variable satsar og sender ikkje nettlesarøkta', async () => {
  const result = await render({ year: 2028, currency: 'NOK', open: true, minimum_ore: 7500, superkul_ore: 12550 });
  assert.match(result.text, /2028/);
  assert.match(result.text, /75/);
  assert.match(result.text, /125,50/);
  assert.equal(result.calls[0].options.credentials, 'omit');
  assert.equal(result.calls[0].options.cache, 'no-store');
});

test('stengt år viser ingen gammal pris', async () => {
  const result = await render({ year: 2027, currency: 'NOK', open: false });
  assert.match(result.text, /2027 er ikkje open/);
  assert.doesNotMatch(result.text, /kroner|\b5\b/);
});

test('feil og ugyldige svar bevarer rettleiinga til betalingsskjemaet', async () => {
  for (const [payload, options] of [
    [null, { fail: true }], [null, { ok: false }],
    [{ year: '<script>', currency: 'NOK', open: true }, {}],
    [{ year: 2028, currency: 'NOK', open: true, minimum_ore: 500, superkul_ore: 100 }, {}],
  ]) {
    assert.match((await render(payload, options)).text, /betalingsskjemaet/);
  }
});
