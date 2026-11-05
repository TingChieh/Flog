(function () {
  // Two visible themes. "auto" is only the default when nothing is saved: the
  // page follows the system until the reader picks light or dark.
  const chosen = ['light', 'dark'];
  const labels = {light: '白天', dark: '夜间'};
  const root = document.documentElement;
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');

  const normalizeMode = (value) => chosen.includes(value) ? value : 'auto';
  const readMode = () => {
    try { return normalizeMode(localStorage.getItem('theme')); }
    catch (error) { return 'auto'; }
  };
  const resolveTheme = (mode) => (
    mode === 'auto' ? (systemTheme.matches ? 'dark' : 'light') : mode
  );
  const applyMode = (mode) => {
    const normalized = normalizeMode(mode);
    const theme = resolveTheme(normalized);
    root.dataset.themeMode = normalized;
    root.dataset.theme = theme;
    root.dataset.bsTheme = theme;
    return normalized;
  };

  let currentMode = applyMode(readMode());
  let toggle = null;
  let toggleLabel = null;

  const syncControls = () => {
    if (!toggle) return;
    const theme = resolveTheme(currentMode);
    const next = theme === 'dark' ? 'light' : 'dark';
    const description =
      `当前为${labels[theme]}模式；切换到${labels[next]}模式`;
    toggle.dataset.themeMode = theme;
    toggle.setAttribute('aria-label', description);
    toggle.setAttribute('title', description);
    if (toggleLabel) toggleLabel.textContent = `主题：${labels[theme]}`;
  };

  const setMode = (mode) => {
    currentMode = applyMode(mode);
    try {
      if (currentMode === 'auto') localStorage.removeItem('theme');
      else localStorage.setItem('theme', currentMode);
    } catch (error) { /* Theme still applies for this page. */ }
    syncControls();
  };

  systemTheme.addEventListener('change', () => {
    if (currentMode !== 'auto') return;
    applyMode(currentMode);
    syncControls();
  });

  document.addEventListener('DOMContentLoaded', () => {
    toggle = document.querySelector('[data-theme-toggle]');
    toggleLabel = toggle?.querySelector('[data-theme-label]') ?? null;
    toggle?.addEventListener('click', () => {
      setMode(resolveTheme(currentMode) === 'dark' ? 'light' : 'dark');
    });
    syncControls();
  });

  window.FlogTheme = {getMode: () => currentMode, setMode};
})();
