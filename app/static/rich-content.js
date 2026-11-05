// Formulas ($…$, $$…$$) and Mermaid diagrams in rendered articles. The libraries
// are large, so each one is loaded only when the page actually needs it.
(() => {
  const script = document.currentScript;
  const katexBase = script?.dataset.katexBase;
  const mermaidSrc = script?.dataset.mermaidSrc;
  const loading = new Map();
  let diagramCount = 0;

  const loadScript = (src) => {
    if (!loading.has(src)) {
      loading.set(src, new Promise((resolve, reject) => {
        const element = document.createElement('script');
        element.src = src;
        element.addEventListener('load', resolve);
        element.addEventListener('error', () => reject(new Error(`failed to load ${src}`)));
        document.head.append(element);
      }));
    }
    return loading.get(src);
  };

  const loadStylesheet = (href) => {
    const element = document.createElement('link');
    element.rel = 'stylesheet';
    element.href = href;
    document.head.append(element);
  };

  const renderMath = async () => {
    const formulas = document.querySelectorAll('.math');
    if (!formulas.length || !katexBase) return;
    loadStylesheet(`${katexBase}/katex.min.css`);
    await loadScript(`${katexBase}/katex.min.js`);
    formulas.forEach((element) => {
      if (element.dataset.rendered) return;
      try {
        window.katex.render(element.textContent, element, {
          displayMode: element.classList.contains('math-block'),
          throwOnError: false,
        });
        element.dataset.rendered = 'true';
      } catch (_error) { /* leave the TeX source readable */ }
    });
  };

  const mermaidTheme = () => (
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'neutral');

  const draw = async (container, source) => {
    diagramCount += 1;
    const { svg } = await window.mermaid.render(`flog-mermaid-${diagramCount}`, source);
    container.innerHTML = svg;
  };

  const initializeMermaid = () => window.mermaid.initialize({
    startOnLoad: false, securityLevel: 'strict', theme: mermaidTheme(),
  });

  const renderDiagrams = async () => {
    const blocks = Array.from(document.querySelectorAll('pre > code.language-mermaid'));
    if (!blocks.length || !mermaidSrc) return;
    await loadScript(mermaidSrc);
    initializeMermaid();
    for (const code of blocks) {
      const pre = code.parentElement;
      const source = code.textContent;
      const container = document.createElement('div');
      container.className = 'mermaid-diagram';
      container.dataset.source = source;
      pre.replaceWith(container);
      try {
        await draw(container, source);
      } catch (_error) {
        pre.dataset.mermaidError = 'true';
        container.replaceWith(pre);
      }
    }
    new MutationObserver(async () => {
      initializeMermaid();
      for (const container of document.querySelectorAll('.mermaid-diagram')) {
        try { await draw(container, container.dataset.source); } catch (_error) { /* keep the old drawing */ }
      }
    }).observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-theme'],
    });
  };

  const run = () => {
    renderMath().catch(() => {});
    renderDiagrams().catch(() => {});
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
