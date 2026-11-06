(function () {
  const share = document.querySelector('[data-qr-share]');
  if (!share) return;
  const toggle = share.querySelector('.qr-share__toggle');
  const panel = share.querySelector('.qr-share__panel');
  const target = share.querySelector('[data-qr-target]');
  let drawn = false;

  const draw = () => {
    if (drawn) return;
    drawn = true;
    if (typeof QRCode === 'undefined') {
      // The library comes from a CDN; without it show the address instead.
      target.textContent = share.dataset.url;
      target.classList.add('qr-share__code--text');
      return;
    }
    new QRCode(target, {
      text: share.dataset.url,
      width: 148,
      height: 148,
      colorDark: '#1d1d1f',
      colorLight: '#ffffff',
      correctLevel: QRCode.CorrectLevel.M,
    });
  };

  const setOpen = (open, returnFocus = false) => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) draw();
    if (!open && returnFocus) toggle.focus();
  };

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  document.addEventListener('click', (event) => {
    if (!panel.hidden && !share.contains(event.target)) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) setOpen(false, true);
  });
})();
