(() => {
  // Show notes often start a line with a time, like "[01:35] 聊吃的". Those
  // lines become buttons that jump the player there.
  const audio = document.querySelector('[data-episode-audio]');
  const notes = document.querySelector('[data-episode-notes]');
  if (!audio || !notes) return;

  const STAMP = /^\s*[[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?/;

  function seconds(stamp) {
    return stamp.split(':').reduce((total, part) => total * 60 + Number(part), 0);
  }

  notes.querySelectorAll('li, p').forEach((line) => {
    const match = STAMP.exec(line.textContent || '');
    if (!match) return;
    line.dataset.seek = String(seconds(match[1]));
    line.classList.add('is-seekable');
  });

  notes.addEventListener('click', (event) => {
    if (event.target.closest('a')) return;
    const line = event.target.closest('[data-seek]');
    if (!line) return;
    audio.currentTime = Number(line.dataset.seek);
    const started = audio.play();
    if (started && started.catch) started.catch(() => {});
  });
})();
