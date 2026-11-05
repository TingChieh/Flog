# KaTeX 0.19.0 (vendored subset)

- Source: npm package `katex@0.19.0`, published 2026-10-01, MIT licence (see `LICENSE`).
- npm `dist.integrity`: `sha512-v6Tznz3zJ7u3niRCoDTsumM2+HA2XXcCu+WAacCeHD2z3p9A9Ks987o5FzfTGBN0e8A0vjEgIDvLbICrXpdw/Q==`
- Files kept from `dist/`: `katex.min.js`, `katex.min.css`, and the `fonts/*.woff2` files.
  The stylesheet also lists `.woff` and `.ttf` fallbacks; they are not shipped
  because every supported browser loads WOFF2.
- Not shipped: `contrib/` (auto-render, copy-tex, mhchem), ESM builds, sources.
- Loaded on demand by `app/static/rich-content.js`, only on pages that contain
  a formula.
