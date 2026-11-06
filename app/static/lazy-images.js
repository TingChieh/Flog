(() => {
  // Photos that have not arrived yet are held as a quiet block and fade in once
  // they have. Ones already in the cache are left alone.
  document.querySelectorAll('.article-body img, .page-body img').forEach((image) => {
    if (image.complete) return;
    image.setAttribute('data-loading', '');
    const settle = (arrived) => {
      image.removeAttribute('data-loading');
      if (arrived) image.classList.add('is-loaded');
    };
    image.addEventListener('load', () => settle(true), { once: true });
    image.addEventListener('error', () => settle(false), { once: true });
  });
})();
