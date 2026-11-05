# Vditor 4.0.1 (vendored)

Self-hosted subset of the npm package `vditor@4.0.1` (MIT, see `LICENSE`),
published 2026-10-18. Do not edit these files; to upgrade, replace the whole
directory with a new versioned one and update the templates.

Source tarball integrity (`npm view vditor@4.0.1 dist.integrity`, verified
against the downloaded tarball on 2026-11-05):

    sha512-CyajvPNE8fjCgEAzAaSxVEEWwQMJ5FTIVkNn3k+5IRaldqGwPRr8Dx2QLALHGCby8L/AJ6pQXjXiSPUGhHGmDw==

Files kept (Vditor resolves them under `cdn + '/dist/...'`):

- `dist/index.min.js`, `dist/index.css`
- `dist/js/lute/lute.min.js` (Markdown engine)
- `dist/js/i18n/zh_CN.js`, `dist/js/icons/ant.js`
- `dist/css/content-theme/light.css`, `dark.css`
- `dist/js/highlight.js/styles/github.min.css` (Vditor requests this stylesheet
  even with highlighting disabled; the highlight.js script itself is not shipped)

Left out on purpose: the highlight.js script, mermaid, katex, mathjax, echarts, graphviz,
abcjs, markmap, plantuml, wavedrom, smiles-drawer, flowchart and emoji images.
The editor is configured so it never requests them.
