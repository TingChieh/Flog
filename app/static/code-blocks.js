(function () {
  document.querySelectorAll('.article-body pre, .page-body pre').forEach((pre) => {
    const code = pre.querySelector('code');
    if (!code || !navigator.clipboard || !navigator.clipboard.writeText) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-copy';
    button.textContent = 'Copy';
    button.setAttribute('aria-label', 'Copy code');
    let timer;
    button.addEventListener('click', async () => {
      clearTimeout(timer);
      try {
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = 'Copied!';
      } catch (error) {
        button.textContent = 'Copy failed';
      }
      timer = setTimeout(() => { button.textContent = 'Copy'; }, 2000);
    });
    pre.appendChild(button);
  });
})();
