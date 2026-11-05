const body = document.querySelector('.article-body');
const bar = document.querySelector('.reading-progress__bar');

if (body && bar) {
  let scheduled = false;
  const update = () => {
    const rect = body.getBoundingClientRect();
    const start = rect.top + window.scrollY;
    const distance = Math.max(0, rect.height - window.innerHeight);
    const progress = distance ? (window.scrollY - start) / distance : (window.scrollY >= start ? 1 : 0);
    bar.style.transform = `scaleX(${Math.max(0, Math.min(1, progress))})`;
    scheduled = false;
  };
  const schedule = () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(update); }
  };
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule, { passive: true });
  if ('ResizeObserver' in window) new ResizeObserver(schedule).observe(body);
  update();

  const images = Array.from(body.querySelectorAll('img'));
  images.forEach((img, index) => {
    img.dataset.lightboxReady = '';
    img.setAttribute('role', 'button');
    img.setAttribute('tabindex', '0');
    img.setAttribute('aria-haspopup', 'dialog');
    const open = async (event) => {
      event.preventDefault();
      const scrollX = window.scrollX, scrollY = window.scrollY;
      const focus = document.activeElement;
      const sizes = await Promise.all(images.map(image => new Promise(resolve => {
        const source = image.currentSrc || image.src;
        const finish = (loaded) => resolve({ src: source,
          width: loaded.naturalWidth || 1, height: loaded.naturalHeight || 1,
          caption: image.closest('figure')?.querySelector('figcaption')?.textContent.trim() || image.alt || '' });
        if (image.complete && image.naturalWidth) finish(image);
        else {
          const loader = new Image();
          loader.onload = loader.onerror = () => finish(loader);
          loader.src = source;
        }
      })));
      const { default: PhotoSwipe } = await import('./vendor/photoswipe/photoswipe.esm.js');
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const gallery = new PhotoSwipe({ dataSource: sizes, index, showHideAnimationType: reduced ? 'none' : 'zoom',
        showAnimationDuration: reduced ? 0 : 333, hideAnimationDuration: reduced ? 0 : 333,
        bgOpacity: 0.9, returnFocus: false });
      gallery.on('uiRegister', () => gallery.ui.registerElement({
        name: 'custom-caption', order: 9, isButton: false, appendTo: 'root',
        onInit: (element, pswp) => {
          pswp.on('change', () => { element.textContent = pswp.currSlide?.data.caption || ''; });
        }
      }));
      gallery.on('destroy', () => { window.scrollTo({ left: scrollX, top: scrollY, behavior: 'instant' }); if (focus instanceof HTMLElement) focus.focus({ preventScroll: true }); });
      gallery.init();
    };
    img.addEventListener('click', open);
    img.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') open(event); });
  });
}

// Keep the current section in step with the sticky navigation and document scroll.
const tocLinks = Array.from(document.querySelectorAll('.article-toc a'));
if (body && tocLinks.length) {
  const sections = Array.from(body.querySelectorAll('h2[id], h3[id]'));
  const nav = document.querySelector('.site-nav');
  const updateOffset = () => {
    const offset = (nav?.getBoundingClientRect().height || 0) + 24;
    document.documentElement.style.setProperty('--article-nav-offset', `${offset}px`);
    return offset;
  };
  let queued = false;
  const updateCurrent = () => {
    const offset = updateOffset();
    let current = sections[0];
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= offset + 1) current = section;
      else break;
    }
    tocLinks.forEach(link => {
      let id;
      try { id = decodeURIComponent(link.getAttribute('href').slice(1)); } catch { return; }
      if (current && id === current.id) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    queued = false;
  };
  const scheduleCurrent = () => {
    if (!queued) { queued = true; requestAnimationFrame(updateCurrent); }
  };
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(scheduleCurrent, { threshold: [0, 1] });
    sections.forEach(section => observer.observe(section));
  }
  window.addEventListener('scroll', scheduleCurrent, { passive: true });
  window.addEventListener('resize', scheduleCurrent, { passive: true });
  if ('ResizeObserver' in window && nav) new ResizeObserver(scheduleCurrent).observe(nav);
  updateCurrent();
}
