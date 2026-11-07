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
        // Always open the full-size file, not the srcset candidate on screen.
        const source = image.src;
        const caption = image.closest('figure')?.querySelector('figcaption')?.textContent.trim() || '';
        const liveVideo = image.closest('.live-photo')?.dataset.liveVideo || '';
        const finish = (loaded) => resolve({ src: source,
          width: loaded.naturalWidth || 1, height: loaded.naturalHeight || 1, caption, liveVideo });
        const width = Number(image.getAttribute('width')), height = Number(image.getAttribute('height'));
        if (width > 0 && height > 0) resolve({ src: source, width, height, caption, liveVideo });
        else if (image.complete && image.naturalWidth && !image.srcset) finish(image);
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
      // A Live Photo moves in the lightbox too: its clip plays once when the
      // slide arrives, then the LIVE button plays (or stops) it.
      let liveSlide = null;
      const syncLiveBadge = (slide) => {
        slide?.liveBadge?.setAttribute('aria-pressed',
          slide.liveClip.classList.contains('is-playing') ? 'true' : 'false');
      };
      const stopLive = () => {
        const clip = liveSlide?.liveClip;
        if (clip) { clip.pause(); clip.classList.remove('is-playing'); }
        syncLiveBadge(liveSlide);
      };
      const playLive = (slide) => {
        const clip = slide.liveClip;
        try { clip.currentTime = 0; } catch (error) { /* not loaded yet */ }
        const playing = clip.play();
        if (playing && playing.catch) playing.catch(() => {});
      };
      const sizeLiveClip = (slide) => {
        // The same size PhotoSwipe gives the still (Slide#updateContentSize).
        const scale = slide.currentResolution || slide.zoomLevels.initial;
        if (!slide.liveClip || !scale) return;
        const width = Math.round(slide.width * scale);
        slide.liveClip.style.width = `${width}px`;
        slide.liveClip.style.height = `${Math.round(slide.height * scale)}px`;
        // The badge sits in the still's top-right corner, as it does in the article.
        slide.liveBadge.style.left = `${width}px`;
      };
      gallery.on('slideActivate', ({ slide }) => {
        liveSlide = slide;
        if (!slide.data.liveVideo) return;
        if (!slide.liveClip) {
          const clip = document.createElement('video');
          clip.className = 'pswp__live-video';
          clip.muted = true;
          clip.playsInline = true;
          clip.preload = 'auto';
          clip.setAttribute('aria-hidden', 'true');
          clip.addEventListener('playing', () => { clip.classList.add('is-playing'); syncLiveBadge(slide); });
          clip.addEventListener('ended', stopLive);
          clip.src = slide.data.liveVideo;
          const badge = document.createElement('button');
          badge.type = 'button';
          badge.className = 'live-photo__badge pswp__live-toggle';
          badge.setAttribute('aria-label', '播放 Live Photo');
          badge.setAttribute('aria-pressed', 'false');
          badge.textContent = 'LIVE';
          // Keep the gallery from reading a press on the badge as a drag or a tap on the photo.
          badge.addEventListener('pointerdown', (event) => event.stopPropagation());
          badge.addEventListener('click', (event) => {
            event.stopPropagation();
            if (clip.classList.contains('is-playing')) stopLive();
            else playLive(slide);
          });
          slide.liveClip = clip;
          slide.liveBadge = badge;
          slide.container.append(clip, badge);
          sizeLiveClip(slide);
        }
        if (!reduced) playLive(slide);
      });
      gallery.on('slideDeactivate', ({ slide }) => { if (slide === liveSlide) stopLive(); });
      gallery.on('contentResize', ({ content }) => { if (content.slide) sizeLiveClip(content.slide); });
      gallery.on('close', stopLive);
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
