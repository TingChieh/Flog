(() => {
  // The page ships the browser's own <audio controls>; when this script runs
  // they are swapped for controls that match the site.
  const root = document.querySelector('[data-podcast-player]');
  if (!root) return;
  const audio = root.querySelector('[data-episode-audio]');
  const controls = root.querySelector('[data-player-controls]');
  if (!audio || !controls) return;

  const play = controls.querySelector('[data-player-play]');
  const seek = controls.querySelector('[data-player-seek]');
  const current = controls.querySelector('[data-player-current]');
  const total = controls.querySelector('[data-player-total]');
  const rateButton = controls.querySelector('[data-player-rate]');
  const skipButtons = controls.querySelectorAll('[data-player-skip]');
  const RATES = [1, 1.25, 1.5, 2, 0.75];
  let rateIndex = 0;

  function format(seconds) {
    const whole = Math.max(0, Math.floor(seconds || 0));
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const secs = String(whole % 60).padStart(2, '0');
    if (hours) return `${hours}:${String(minutes).padStart(2, '0')}:${secs}`;
    return `${minutes}:${secs}`;
  }

  // The length is known from the page before the audio has loaded anything.
  function length() {
    if (Number.isFinite(audio.duration) && audio.duration > 0) return audio.duration;
    return Number(root.dataset.duration) || 0;
  }

  function paint() {
    const whole = length();
    const now = audio.currentTime || 0;
    seek.max = String(Math.floor(whole));
    seek.value = String(Math.floor(now));
    seek.style.setProperty('--progress', whole ? `${Math.min(100, (now / whole) * 100)}%` : '0%');
    current.textContent = format(now);
    total.textContent = format(whole);
  }

  function showState() {
    const playing = !audio.paused && !audio.ended;
    play.dataset.state = playing ? 'playing' : 'paused';
    play.setAttribute('aria-label', playing ? '暂停' : '播放');
  }

  audio.controls = false;
  audio.hidden = true;
  controls.hidden = false;

  play.addEventListener('click', () => {
    if (audio.paused) {
      const started = audio.play();
      if (started && started.catch) started.catch(() => {});
    } else {
      audio.pause();
    }
  });

  seek.addEventListener('input', () => {
    audio.currentTime = Number(seek.value);
    paint();
  });

  skipButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const target = (audio.currentTime || 0) + Number(button.dataset.playerSkip);
      audio.currentTime = Math.min(Math.max(0, target), length() || target);
      paint();
    });
  });

  rateButton.addEventListener('click', () => {
    rateIndex = (rateIndex + 1) % RATES.length;
    audio.playbackRate = RATES[rateIndex];
    rateButton.textContent = `${RATES[rateIndex]}×`;
  });

  ['loadedmetadata', 'durationchange', 'timeupdate', 'seeked'].forEach((type) => {
    audio.addEventListener(type, paint);
  });
  ['play', 'pause', 'ended'].forEach((type) => {
    audio.addEventListener(type, () => { showState(); paint(); });
  });

  paint();
  showState();
})();
