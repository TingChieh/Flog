(() => {
  const LONG_PRESS_MS = 350;
  const CLICK_GUARD_MS = 600;

  // Hover (mouse) or long-press (touch) plays the clip over the still, the way
  // the Photos app does; letting go returns to the still.
  const attach = (box, { reducedMotion = false } = {}) => {
    let video = null;
    let wanted = false;
    let pressTimer = null;
    let guardUntil = 0;

    const ensureVideo = () => {
      if (video) return video;
      video = document.createElement('video');
      video.className = 'live-photo__video';
      video.muted = true;
      video.playsInline = true;
      video.preload = 'auto';
      video.setAttribute('aria-hidden', 'true');
      video.addEventListener('playing', () => {
        if (wanted) box.classList.add('is-playing');
        else video.pause();
      });
      video.addEventListener('ended', () => stop());
      video.src = box.dataset.liveVideo;
      box.append(video);
      return video;
    };

    const start = () => {
      if (reducedMotion) return;
      wanted = true;
      const clip = ensureVideo();
      try { clip.currentTime = 0; } catch (error) { /* not loaded yet */ }
      const playing = clip.play();
      if (playing && playing.catch) playing.catch(() => {});
    };

    const stop = () => {
      wanted = false;
      box.classList.remove('is-playing');
      if (video) video.pause();
    };

    box.addEventListener('pointerenter', (event) => {
      if (event.pointerType === 'mouse') start();
    });
    box.addEventListener('pointerleave', (event) => {
      if (event.pointerType === 'mouse') stop();
    });

    box.addEventListener('touchstart', () => {
      if (!reducedMotion) ensureVideo();
      clearTimeout(pressTimer);
      pressTimer = setTimeout(() => {
        guardUntil = Date.now() + CLICK_GUARD_MS;
        start();
      }, LONG_PRESS_MS);
    }, { passive: true });
    ['touchend', 'touchcancel', 'touchmove'].forEach((name) => {
      box.addEventListener(name, () => {
        clearTimeout(pressTimer);
        if (wanted) guardUntil = Date.now() + CLICK_GUARD_MS;
        stop();
      }, { passive: true });
    });

    // Releasing a long press must not also open the lightbox.
    box.addEventListener('click', (event) => {
      if (Date.now() < guardUntil) {
        event.stopImmediatePropagation();
        event.preventDefault();
      }
    }, true);
    // Keep the browser's image menu from interrupting the long press.
    box.addEventListener('contextmenu', (event) => event.preventDefault());
  };

  const init = () => {
    const reducedMotion = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelectorAll('.live-photo[data-live-video]').forEach(
      (box) => attach(box, { reducedMotion }));
  };

  window.FlogLivePhoto = { attach, init };
  if (typeof document !== 'undefined' && document.querySelectorAll) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
})();
