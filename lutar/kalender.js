/* Flytt tilskipingar når sluttida i Oslo er passert, også mellom publiseringar. */
(function () {
  'use strict';
  function osloTime(now) {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Oslo', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(now);
    const value = Object.fromEntries(parts.map(p => [p.type, p.value]));
    return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`;
  }
  function hasEnded(end, now) {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(end);
    if (!match) return false;
    const [,y,m,d,h,min] = match.map(Number);
    const wall = Date.UTC(y,m-1,d,h,min);
    const candidates = [1,2].map(offset => wall-offset*3600000)
      .filter(time => osloTime(new Date(time)) === end);
    // Ved den doble timen om hausten vert den siste førekomsten brukt.
    const instant = candidates.length ? Math.max(...candidates) : wall-3600000;
    return now.getTime() >= instant;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {osloTime, hasEnded};
  if (typeof document === 'undefined') return;
  const upcoming = document.querySelector('[data-calendar-live="future"]');
  const history = document.querySelector('[data-calendar-live="past"]');
  if (!upcoming || !history) return;
  const cards = [...upcoming.querySelectorAll('[data-event-end]'), ...history.querySelectorAll('[data-event-end]')];
  let previous = '';
  function update() {
    const now = new Date();
    const future = cards.filter(c => !hasEnded(c.dataset.eventEnd, now)).sort((a,b) => a.dataset.eventStart.localeCompare(b.dataset.eventStart));
    const past = cards.filter(c => hasEnded(c.dataset.eventEnd, now)).sort((a,b) => b.dataset.eventStart.localeCompare(a.dataset.eventStart));
    const signature = JSON.stringify([future.map(c => c.dataset.eventUid), past.map(c => c.dataset.eventUid)]);
    if (signature === previous) return;
    previous = signature;
    const futureGrid = document.createElement('div');
    futureGrid.className = 'kalenderliste';
    for (const card of future) { card.classList.remove('kalenderkort--tidlegare'); futureGrid.append(card); }
    upcoming.replaceChildren(futureGrid);
    if (!future.length) {
      const message = document.createElement('p');
      message.className = 'dempa'; message.textContent = 'Ingen komande tilskipingar er lagde inn enno.';
      upcoming.append(message);
    }
    const fragment = document.createDocumentFragment();
    const years = [...new Set(past.map(c => c.dataset.eventStart.slice(0,4)))];
    for (const year of years) {
      const events = past.filter(c => c.dataset.eventStart.startsWith(year));
      const heading = document.createElement('h3'); heading.className = 'kalender-aar'; heading.textContent = year + ' ';
      const counts = [['pobb-', 'pøbbar'], ['kved-', 'kvedarkrokar'], ['kviss-', 'kvissar']]
        .map(([prefix,label]) => [events.filter(c => c.dataset.eventUid.startsWith(prefix)).length,label])
        .filter(([count]) => count > 0).map(([count,label]) => `${count} ${label}`);
      const note = document.createElement('span'); note.className = 'dempa';
      note.textContent = '(' + (counts.length ? counts.join(', ') : `${events.length} tilskipingar`) + ')';
      heading.append(note);
      const grid = document.createElement('div'); grid.className = 'kalenderliste';
      for (const card of events) { card.classList.add('kalenderkort--tidlegare'); grid.append(card); }
      fragment.append(heading, grid);
    }
    history.replaceChildren(fragment);
  }
  update();
  setInterval(update, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
  window.addEventListener('pageshow', update);
})();
