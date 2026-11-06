(() => {
  const form = document.querySelector('[data-comment-form]');
  if (!form) return;

  const parent = form.querySelector('[data-reply-parent]');
  const note = form.querySelector('[data-reply-note]');
  const name = form.querySelector('[data-reply-name]');
  const body = form.querySelector('[data-comment-body]');

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-reply-link]');
    if (link) {
      event.preventDefault();
      parent.value = link.dataset.replyId;
      name.textContent = link.dataset.replyName;
      note.hidden = false;
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      body.focus();
      return;
    }
    if (event.target.closest('[data-reply-cancel]')) {
      event.preventDefault();
      parent.value = '';
      note.hidden = true;
    }
  });
})();
