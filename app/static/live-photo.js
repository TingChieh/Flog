(() => {
  // A Live Photo plays once by itself when the visitor scrolls it into place:
  // (nearly) the whole photo is on screen and stays there a moment, so peeking
  // at its edge or flicking past does not start it. After that the LIVE button
  // plays (or stops) it.
  const VISIBLE_RATIO = 0.9;
  const DWELL_MS = 400;

  const attach = (box, { autoplay = true, observe } = {}) => {
    const badge = box.querySelector('.live-photo__badge');
    let video = null;
    let wanted = false;

    const setPlaying = (playing) => {
      box.classList.toggle('is-playing', playing);
      if (badge) badge.setAttribute('aria-pressed', playing ? 'true' : 'false');
    };

    const ensureVideo = () => {
      if (video) return video;
      video = document.createElement('video');
      video.className = 'live-photo__video';
      video.muted = true;
      video.playsInline = true;
      video.preload = 'auto';
      video.setAttribute('aria-hidden', 'true');
      video.addEventListener('playing', () => {
        if (wanted) setPlaying(true);
        else video.pause();
      });
      video.addEventListener('ended', () => stop());
      video.src = box.dataset.liveVideo;
      box.append(video);
      return video;
    };

    const start = () => {
      wanted = true;
      const clip = ensureVideo();
      try { clip.currentTime = 0; } catch (error) { /* not loaded yet */ }
      const playing = clip.play();
      // Autoplay can be refused (e.g. low-power mode); the button still works.
      if (playing && playing.catch) playing.catch(() => { wanted = false; });
    };

    const stop = () => {
      wanted = false;
      setPlaying(false);
      if (video) video.pause();
    };

    if (badge) {
      badge.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (wanted) stop();
        else start();
      });
    }

    if (autoplay && observe) {
      observe(box, () => start(), VISIBLE_RATIO);
    }
  };

  // Calls ``callback`` once, after ``element`` has been on screen (at least
  // ``ratio`` of it) for ``DWELL_MS`` without leaving.
  const observeOnce = (element, callback, ratio) => {
    if (typeof IntersectionObserver !== 'function') return;
    let timer = null;
    const observer = new IntersectionObserver((entries) => {
      const entry = entries[entries.length - 1];
      clearTimeout(timer);
      if (!entry.isIntersecting) return;
      timer = setTimeout(() => {
        observer.disconnect();
        callback();
      }, DWELL_MS);
    }, { threshold: ratio });
    observer.observe(element);
  };

  const init = () => {
    const reducedMotion = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelectorAll('.live-photo[data-live-video]').forEach(
      (box) => attach(box, { autoplay: !reducedMotion, observe: observeOnce }));
  };

  window.FlogLivePhoto = { attach, init, observeOnce };
  if (typeof document !== 'undefined' && document.querySelectorAll) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
})();
