(() => {
  const dialog = document.querySelector('.pobb-visar');
  const links = [...document.querySelectorAll('[data-pobb-bilete]')];
  if (!dialog || !dialog.showModal || !links.length) return;
  const image = dialog.querySelector('.pobb-visar__bilete');
  const caption = dialog.querySelector('.pobb-visar__tekst');
  const counter = dialog.querySelector('.pobb-visar__teljar');
  let current = 0;
  let opener;
  let previousOverflow;

  function show(index) {
    current = (index + links.length) % links.length;
    const link = links[current];
    image.src = link.href;
    image.alt = link.querySelector('img').alt;
    caption.textContent = [...link.closest('figure').querySelector('figcaption').childNodes]
      .map(node => node.textContent.trim()).filter(Boolean).join(' · ');
    counter.textContent = `${current + 1} av ${links.length}`;
  }

  links.forEach((link, index) => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    opener = link;
    show(index);
    previousOverflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = 'hidden';
  }));
  dialog.querySelector('[data-lukk]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-forrige]').addEventListener('click', () => show(current - 1));
  dialog.querySelector('[data-neste]').addEventListener('click', () => show(current + 1));
  dialog.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      show(current + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {
    document.body.style.overflow = previousOverflow;
    image.removeAttribute('src');
    opener?.focus({ preventScroll: true });
  });
})();
