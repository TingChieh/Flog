document.querySelector('[data-preview-close]')?.addEventListener('click', () => {
  window.close();
  // A tab the browser did not open for us cannot close itself.
  if (!window.closed) {
    document.querySelector('.preview-bar span').textContent = '可以直接关闭此标签页。';
  }
});
