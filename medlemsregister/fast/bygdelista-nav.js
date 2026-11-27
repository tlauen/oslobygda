/* Open utan JS; kompakt mobilmeny når nettlesaren støttar matchMedia. */
(() => {
  const menu = document.querySelector('.bygdelista-navigasjon');
  if (!menu || !window.matchMedia) return;
  const wide = window.matchMedia('(min-width: 1000px)');
  function resize() { menu.open = wide.matches; }
  resize();
  wide.addEventListener('change', resize);
})();
