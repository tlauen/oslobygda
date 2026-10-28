/* Vanlege biletl lenkjer fungerer òg utan JavaScript. */
(() => {
  const links = [...document.querySelectorAll('.galleri-lenkje')];
  const dialog = document.querySelector('.galleri-dialog');
  if (!links.length || !dialog || typeof dialog.showModal !== 'function') return;
  const image = dialog.querySelector('img');
  const caption = dialog.querySelector('.galleri-bildetekst');
  const counter = dialog.querySelector('.galleri-teljar');
  let selected = 0;
  function show(index) {
    selected = (index + links.length) % links.length;
    const source = links[selected].querySelector('img');
    image.src = links[selected].href;
    image.alt = source.alt;
    caption.textContent = links[selected].closest('figure').querySelector('figcaption')?.textContent || source.alt;
    counter.textContent = `${selected + 1} / ${links.length}`;
  }
  links.forEach((link, index) => link.addEventListener('click', event => {
    event.preventDefault(); show(index); dialog.showModal();
  }));
  dialog.querySelector('[data-gallery="close"]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-gallery="previous"]').addEventListener('click', () => show(selected - 1));
  dialog.querySelector('[data-gallery="next"]').addEventListener('click', () => show(selected + 1));
  dialog.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault(); show(selected + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
})();
