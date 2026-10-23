const assert = require('node:assert/strict');
const {hasEnded, osloTime} = require('../lutar/kalender.js');
assert.equal(osloTime(new Date('2026-11-18T20:00:00Z')), '2026-11-18T21:00');
assert.equal(hasEnded('2026-11-18T23:45', new Date('2026-11-18T22:44:59Z')), false);
assert.equal(hasEnded('2026-11-18T23:45', new Date('2026-11-18T22:45:00Z')), true);
assert.equal(hasEnded('2026-08-27T00:30', new Date('2026-08-26T22:30:00Z')), true);
assert.equal(hasEnded('2026-10-25T02:30', new Date('2026-10-25T00:45:00Z')), false);
assert.equal(hasEnded('2026-10-25T02:30', new Date('2026-10-25T01:30:00Z')), true);
console.log('Klokkefiltrering: vinter, sommar, midnatt og klokkeomstilling OK.');
