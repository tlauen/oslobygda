/* Opne felt med valideringsfeil, også når seksjonen er lukka. */
(() => {
  document.addEventListener('invalid', event => {
    for (let parent = event.target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') {
        parent.removeAttribute('name');
        parent.open = true;
      }
    }
  }, true);
})();
