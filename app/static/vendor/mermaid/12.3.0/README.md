# Mermaid 12.3.0 (vendored)

- Source: npm package `mermaid@12.3.0`, published 2026-11-03, MIT licence (see `LICENSE`).
- npm `dist.integrity`: `sha512-4113TdXeLAsMruJ79OpFL5O8+LTFXhQqZ260rF3tgUmiNAtRm4Uume04I+65PRN6yZ69J4f8rVYWW8zRk65UYw==`
- File kept from `dist/`: `mermaid.min.js`, the single-file UMD build (about
  5 MB, roughly 1.4 MB gzipped), which bundles DOMPurify 3.4.17.
- Loaded on demand by `app/static/rich-content.js`, only on pages that contain
  a `mermaid` code block, with `securityLevel: 'strict'`.
