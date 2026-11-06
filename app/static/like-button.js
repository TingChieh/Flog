(function () {
  const form = document.querySelector('[data-like-form]');
  if (!form || !window.fetch) return;
  const button = form.querySelector('.like-button');
  const label = form.querySelector('[data-like-label]');
  const count = form.querySelector('.like-count');
  let busy = false;

  const render = (liked, total) => {
    button.classList.toggle('like-button--active', liked);
    button.setAttribute('aria-pressed', String(liked));
    label.textContent = liked ? form.dataset.labelLiked : form.dataset.labelLike;
    count.textContent = String(total);
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    button.disabled = true;
    const wasLiked = button.getAttribute('aria-pressed') === 'true';
    const was = Number(count.textContent) || 0;
    render(!wasLiked, Math.max(0, was + (wasLiked ? -1 : 1)));
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      const type = response.headers.get('Content-Type') || '';
      if (!response.ok || !type.includes('application/json')) throw new Error('not json');
      const result = await response.json();
      render(result.liked, result.count);
    } catch (error) {
      // Offline, expired session or a server error: undo, then let the page do it the old way.
      render(wasLiked, was);
      form.submit();
      return;
    }
    busy = false;
    button.disabled = false;
  });
})();
