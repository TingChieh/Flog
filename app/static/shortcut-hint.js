(() => {
  // The search shortcut works with Ctrl or ⌘; show the one this keyboard has.
  const platform = (navigator.userAgentData && navigator.userAgentData.platform)
    || navigator.platform || '';
  if (!/mac/i.test(platform)) return;
  document.querySelectorAll('[data-shortcut-hint]').forEach((hint) => {
    hint.textContent = '⌘ K';
  });
})();
