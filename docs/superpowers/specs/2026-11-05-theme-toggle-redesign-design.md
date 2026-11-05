# Theme Toggle Redesign

## Goal

Replace the bordered three-segment pill (自动 / 白天 / 夜间) and the separate
mobile icon button with one quiet line-icon button that fits the editorial
navigation. Behaviour (three modes, `localStorage` key `theme`, `FlogTheme`
API) is unchanged, so saved preferences keep working.

## Design

- One button `.theme-toggle` (`data-theme-toggle`, `data-theme-mode`) cycles
  auto -> light -> dark -> auto. The `.theme-selector` group and its three
  `data-theme-mode-option` buttons are removed, as is the CSS that switched
  between the two forms at 768px.
- Three inline SVG icons (24px viewBox, shown at 20px, 1.5px stroke,
  `stroke: currentColor`): auto = circle with the right half filled, light =
  sun (circle plus eight rays), dark = crescent moon. CSS shows the one that
  matches the button's `data-theme-mode`; no DOM swapping in JS.
- Idle colour `var(--text-secondary)`, hover `var(--text-primary)` with a soft
  `var(--surface-muted)` rounded background; no border or pill. Focus ring
  stays `2px solid var(--link-color)`. No animation.
- Placement: public nav, directly after the search trigger. Below 1200px (the
  dropdown panel) the button also shows a visible label "主题：自动/白天/夜间"
  and has a 44px hit area; at 1200px and up, and in the admin top bar, it is
  icon only.
- Accessibility: `aria-label` and `title` both read "当前为自动模式；切换到白天模式"
  (and the equivalents), updated whenever the mode changes.
- `theme.js` keeps `FlogTheme.getMode/setMode`, system-theme following and
  storage failure tolerance; the option-button branch is removed and the label
  text is synced.

## Testing

- `tests/theme.test.js`: harness without option buttons; one test that clicking
  cycles auto -> light -> dark -> auto, persists each mode, and syncs
  `data-theme-mode`, `aria-label`, `title` and the label text; one test that a
  saved preference is reflected on the button after `DOMContentLoaded`.
- `tests/test_ui_shell.py`: public and admin pages render exactly one toggle
  with three icons and no `data-theme-selector` / `data-theme-mode-option`; the
  CSS test checks `.theme-selector` is gone, `.theme-toggle` and its icon rules
  exist, and the label is shown in the dropdown panel only.
- Full `pytest` and `node --test tests/*.test.js`; playwright screenshots in
  light and dark at 1440, 1000 (dropdown) and 390, plus the admin top bar.

## Delivery

Branch `feat/theme-toggle-redesign`, two commits: markup, script and their
tests; then the CSS rewrite, CSS test and verification.
