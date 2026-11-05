# Theme Toggle Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** One quiet line-icon theme button replaces the segmented pill and the mobile icon button.

**Architecture:** `_theme_controls.html` renders one button with three inline SVGs; CSS picks the icon from `data-theme-mode`; `theme.js` keeps the cycle logic and syncs `aria-label`, `title` and a label span.

**Spec:** `docs/superpowers/specs/2026-11-05-theme-toggle-redesign-design.md`. Baseline: 551 pytest, 40 node passing. Branch `feat/theme-toggle-redesign`.

## Task 1: Markup, script, tests

**Files:** `app/templates/_theme_controls.html`, `app/static/theme.js`, `tests/theme.test.js`, `tests/test_ui_shell.py`

- [ ] **Step 1:** Rewrite `tests/theme.test.js` harness: drop `options` and the `querySelectorAll` assertion; give the toggle a `querySelector('[data-theme-label]')` returning a label object with `textContent`; replace the two option/mobile tests with (a) cycling auto -> light -> dark -> auto asserting `stored`, `root.dataset.themeMode`, `toggle.dataset.themeMode`, `aria-label`, `title`, label text (`主题：自动/白天/夜间`); (b) saved preference `dark` reflected on the toggle after `ready()`.
- [ ] **Step 2:** Update `tests/test_ui_shell.py` markup tests (public shell and admin shell): exactly one `data-theme-toggle`, `theme-toggle__icon--auto|light|dark` present, `data-theme-selector` and `data-theme-mode-option` absent, `aria-label="当前为自动模式；切换到白天模式"` and the same `title` present.
- [ ] **Step 3:** Run `node --test tests/theme.test.js` and the shell tests; expect FAIL.
- [ ] **Step 4:** Write `_theme_controls.html`:

```html
<button class="theme-toggle" type="button" data-theme-toggle
        data-theme-mode="auto"
        aria-label="当前为自动模式；切换到白天模式"
        title="当前为自动模式；切换到白天模式">
  <svg class="theme-toggle__icon theme-toggle__icon--auto" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>
  <svg class="theme-toggle__icon theme-toggle__icon--light" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  <svg class="theme-toggle__icon theme-toggle__icon--dark" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>
  <span class="theme-toggle__label" data-theme-label>主题：自动</span>
</button>
```

- [ ] **Step 5:** In `theme.js` remove `optionButtons` and the `[data-theme-mode-option]` handling; rename `mobileToggle` to `toggle`; in `syncControls` also set `title` to the same string as `aria-label` and the `[data-theme-label]` text to `主题：${labels[currentMode]}`.
- [ ] **Step 6:** Run `node --test tests/*.test.js` and `.venv/bin/python -m pytest -q`; expect all pass.
- [ ] **Step 7:** Commit `feat(ui): single line-icon theme toggle markup and script`.

## Task 2: CSS and verification

**Files:** `app/static/style.css`, `tests/test_ui_shell.py`

- [ ] **Step 1:** Rewrite `test_theme_controls_switch_between_desktop_and_mobile_forms` as `test_theme_toggle_is_a_single_quiet_icon_button`: no `.theme-selector` rule anywhere; `.theme-toggle` top-level rule has `display: inline-flex;` and `background: transparent;` and no `border: 1px`; rules exist for `.theme-toggle__icon`, the three `[data-theme-mode=...] .theme-toggle__icon--*` display rules, `.theme-toggle:hover`, `.theme-toggle:focus-visible`; `.theme-toggle__label` is hidden by default and shown under `.public-site .site-nav__menu`; keep the `:not(.theme-toggle)` mobile assertions. Run; expect FAIL.
- [ ] **Step 2:** Replace the `.theme-selector*` and old `.theme-toggle*` blocks (near line 1162-1209) with:

```css
.theme-toggle {
    min-width: 34px;
    height: 34px;
    padding: 0 6px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: var(--text-secondary);
    background: transparent;
    border: 0;
    border-radius: var(--radius);
    font: inherit;
    font-size: 14px;
    cursor: pointer;
}

.theme-toggle:hover {
    color: var(--text-primary);
    background: var(--surface-muted);
}

.theme-toggle:focus-visible {
    outline: 2px solid var(--link-color);
    outline-offset: 1px;
}

.theme-toggle__icon {
    width: 20px;
    height: 20px;
    display: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.theme-toggle[data-theme-mode="auto"] .theme-toggle__icon--auto,
.theme-toggle[data-theme-mode="light"] .theme-toggle__icon--light,
.theme-toggle[data-theme-mode="dark"] .theme-toggle__icon--dark {
    display: block;
}

.theme-toggle__label {
    display: none;
}
```

Remove the `.theme-selector { display: none; }` and `.theme-toggle { ... display: inline-flex; }` pair in the `@media (max-width: 768px)` block; replace `.public-site .site-nav__menu .theme-selector { align-self: flex-start; }` with `.public-site .site-nav__menu .theme-toggle { align-self: flex-start; }` plus `.public-site .site-nav__menu .theme-toggle__label { display: inline; }`; change `.public-site .theme-toggle { width: 44px; min-width: 44px; height: 44px; }` to `min-width: 44px; height: 44px;`; in the `@media (width >= 1200px)` block replace the `.theme-selector` alignment rule with `.public-site .site-nav__menu .theme-toggle { align-self: center; }` and `.public-site .site-nav__menu .theme-toggle__label { display: none; }`; in the `.public-site .search-trigger, .public-site .theme-selector { font-family }` rule drop `.theme-selector` and add `.public-site .theme-toggle` instead. The admin top bar renders the button without the label because `.theme-toggle__label` only shows under `.public-site .site-nav__menu`.
- [ ] **Step 3:** `grep -n "theme-selector" app/static/style.css app/templates tests` must show nothing; run the full suites; expect pass.
- [ ] **Step 4:** Visual check with the playwright skill (scratch DB, `flask run -p 5055`): light and dark at 1440, 1000 (dropdown open) and 390, plus `/admin/`; click through all three modes and confirm icon, `aria-label`, label text and that the saved choice survives a reload.
- [ ] **Step 5:** Commit `feat(ui): quiet line-icon theme toggle styles`.
