# Responsive Automatic Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a default automatic theme that follows the operating system, with a three-segment desktop control and a cycling mobile button.

**Architecture:** A new head-loaded `theme.js` module owns theme-mode validation, storage, first-paint application, operating-system synchronization, and both responsive controls. The root keeps the preference in `data-theme-mode` and the resolved appearance in the existing `data-theme` and `data-bs-theme` attributes, so existing color CSS remains unchanged. `site.js` no longer owns theme behavior.

**Tech Stack:** Flask/Jinja templates, browser JavaScript, CSS media queries, Node.js built-in test runner, pytest.

## Global Constraints

- Theme preference values are exactly `auto`, `light`, and `dark`.
- Missing, inaccessible, or unrecognized stored values resolve to `auto`.
- Automatic mode responds immediately to `prefers-color-scheme: dark` changes; fixed modes ignore them.
- Desktop is 769px and above; mobile is 768px and below.
- Desktop copy is exactly `自动`, `白天`, and `夜间`.
- Mobile cycling order is exactly `auto -> light -> dark -> auto`.
- Existing light/dark design tokens and selectors remain unchanged.
- Do not add dependencies or server-side/account-level preferences.

## File Map

- Create `app/static/theme.js`: theme state, persistence, system synchronization, first-paint application, and responsive-control bindings.
- Create `tests/theme.test.js`: behavior tests running `theme.js` in a controlled browser-like VM.
- Modify `app/templates/base.html`: load `theme.js` before CSS and render both accessible control variants.
- Modify `app/static/site.js`: remove the obsolete two-state theme toggle.
- Modify `app/static/style.css`: segmented-control styling, mobile icon states, and breakpoint visibility.
- Modify `tests/test_ui_shell.py`: rendered-shell and responsive-style contract tests.

---

### Task 1: Three-State Theme Runtime

**Files:**
- Create: `tests/theme.test.js`
- Create: `app/static/theme.js`
- Modify: `app/templates/base.html:6-13`
- Modify: `app/static/site.js:2-9,33-38`

**Interfaces:**
- Consumes: root `document.documentElement.dataset`, `localStorage.theme`, and `matchMedia('(prefers-color-scheme: dark)')`.
- Consumes later markup hooks: `[data-theme-mode-option]` buttons and `[data-theme-toggle]` button.
- Produces: root `data-theme-mode="auto|light|dark"`, `data-theme="light|dark"`, and `data-bs-theme="light|dark"`.
- Produces: `window.FlogTheme.getMode(): string` and `window.FlogTheme.setMode(mode: string): void` for inspection and controlled updates.

- [ ] **Step 1: Write the failing runtime tests**

Create `tests/theme.test.js` with a VM harness that loads the real script:

```javascript
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'theme.js'),
  'utf8',
);

function createButton(mode) {
  const listeners = {};
  return {
    dataset: mode ? {themeModeOption: mode} : {},
    attributes: {},
    addEventListener(name, listener) { listeners[name] = listener; },
    setAttribute(name, value) { this.attributes[name] = value; },
    click() { listeners.click(); },
  };
}

function createHarness({
  savedTheme,
  storageThrows = false,
  systemDark = false,
} = {}) {
  const readyCallbacks = [];
  const mediaListeners = [];
  const stored = new Map();
  if (savedTheme !== undefined) stored.set('theme', savedTheme);
  const options = ['auto', 'light', 'dark'].map(createButton);
  const toggle = createButton();
  const root = {dataset: {}};
  const media = {
    matches: systemDark,
    addEventListener(name, listener) {
      assert.equal(name, 'change');
      mediaListeners.push(listener);
    },
  };
  const context = {
    document: {
      documentElement: root,
      addEventListener(name, listener) {
        assert.equal(name, 'DOMContentLoaded');
        readyCallbacks.push(listener);
      },
      querySelectorAll(selector) {
        assert.equal(selector, '[data-theme-mode-option]');
        return options;
      },
      querySelector(selector) {
        assert.equal(selector, '[data-theme-toggle]');
        return toggle;
      },
    },
    localStorage: {
      getItem(key) {
        if (storageThrows) throw new Error('storage unavailable');
        return stored.get(key) ?? null;
      },
      setItem(key, value) {
        if (storageThrows) throw new Error('storage unavailable');
        stored.set(key, value);
      },
    },
    matchMedia(query) {
      assert.equal(query, '(prefers-color-scheme: dark)');
      return media;
    },
  };
  context.window = context;

  vm.runInNewContext(source, context);
  return {
    context, media, options, root, stored, toggle,
    ready() { readyCallbacks.shift()(); },
    setSystemDark(matches) {
      media.matches = matches;
      mediaListeners.forEach((listener) => listener({matches}));
    },
  };
}

test('defaults missing and invalid preferences to automatic mode', () => {
  for (const savedTheme of [undefined, 'sepia']) {
    const harness = createHarness({savedTheme, systemDark: true});
    assert.equal(harness.root.dataset.themeMode, 'auto');
    assert.equal(harness.root.dataset.theme, 'dark');
    assert.equal(harness.root.dataset.bsTheme, 'dark');
  }
});

test('automatic mode follows system changes while fixed modes ignore them', () => {
  const harness = createHarness({systemDark: false});
  harness.setSystemDark(true);
  assert.equal(harness.root.dataset.theme, 'dark');

  harness.context.FlogTheme.setMode('light');
  harness.setSystemDark(false);
  harness.setSystemDark(true);
  assert.equal(harness.root.dataset.theme, 'light');
});

test('continues applying theme when browser storage is unavailable', () => {
  const harness = createHarness({storageThrows: true, systemDark: true});
  assert.equal(harness.context.FlogTheme.getMode(), 'auto');
  assert.equal(harness.root.dataset.theme, 'dark');

  harness.context.FlogTheme.setMode('light');
  assert.equal(harness.context.FlogTheme.getMode(), 'light');
  assert.equal(harness.root.dataset.theme, 'light');
});

test('desktop options persist and synchronize the selected mode', () => {
  const harness = createHarness();
  harness.ready();
  harness.options[2].click();

  assert.equal(harness.stored.get('theme'), 'dark');
  assert.equal(harness.root.dataset.themeMode, 'dark');
  assert.equal(harness.options[2].attributes['aria-pressed'], 'true');
  assert.equal(harness.options[0].attributes['aria-pressed'], 'false');
});

test('mobile button cycles auto, light, dark, then auto', () => {
  const harness = createHarness();
  harness.ready();

  harness.toggle.click();
  assert.equal(harness.context.FlogTheme.getMode(), 'light');
  harness.toggle.click();
  assert.equal(harness.context.FlogTheme.getMode(), 'dark');
  harness.toggle.click();
  assert.equal(harness.context.FlogTheme.getMode(), 'auto');
  assert.match(harness.toggle.attributes['aria-label'], /自动/);
});
```

- [ ] **Step 2: Run the runtime tests and verify RED**

Run: `node --test tests/theme.test.js`

Expected: FAIL because `app/static/theme.js` does not exist.

- [ ] **Step 3: Implement the minimal theme runtime**

Create `app/static/theme.js` as an IIFE. Use these exact state transitions and keep storage access guarded:

```javascript
(function () {
  const modes = ['auto', 'light', 'dark'];
  const root = document.documentElement;
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');

  const normalizeMode = (value) => modes.includes(value) ? value : 'auto';
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
  let optionButtons = [];
  let mobileToggle = null;

  const syncControls = () => {
    optionButtons.forEach((button) => {
      button.setAttribute(
        'aria-pressed',
        String(button.dataset.themeModeOption === currentMode),
      );
    });
    if (!mobileToggle) return;
    const labels = {auto: '自动', light: '白天', dark: '夜间'};
    const nextMode = modes[(modes.indexOf(currentMode) + 1) % modes.length];
    mobileToggle.dataset.themeMode = currentMode;
    mobileToggle.setAttribute(
      'aria-label',
      `当前为${labels[currentMode]}模式；切换到${labels[nextMode]}模式`,
    );
  };

  const setMode = (mode) => {
    currentMode = applyMode(mode);
    try { localStorage.setItem('theme', currentMode); }
    catch (error) { /* Theme still applies for this page. */ }
    syncControls();
  };

  systemTheme.addEventListener('change', () => {
    if (currentMode === 'auto') applyMode(currentMode);
  });

  document.addEventListener('DOMContentLoaded', () => {
    optionButtons = Array.from(
      document.querySelectorAll('[data-theme-mode-option]'),
    );
    mobileToggle = document.querySelector('[data-theme-toggle]');
    optionButtons.forEach((button) => {
      button.addEventListener('click', () => {
        setMode(button.dataset.themeModeOption);
      });
    });
    mobileToggle?.addEventListener('click', () => {
      const nextIndex = (modes.indexOf(currentMode) + 1) % modes.length;
      setMode(modes[nextIndex]);
    });
    syncControls();
  });

  window.FlogTheme = {getMode: () => currentMode, setMode};
})();
```

In `app/templates/base.html`, replace the inline theme initializer with a blocking head script before the stylesheet:

```html
<script src="{{ url_for('static', filename='theme.js') }}"></script>
```

In `app/static/site.js`, remove `root`, `themeToggle`, and the old two-state click handler. Leave navigation, drawer, scrolling, and back-to-top behavior untouched.

- [ ] **Step 4: Run the runtime tests and verify GREEN**

Run: `node --test tests/theme.test.js tests/markdown_editor.test.js`

Expected: all JavaScript tests PASS with no warnings.

- [ ] **Step 5: Commit the runtime**

```bash
git add app/static/theme.js app/static/site.js app/templates/base.html tests/theme.test.js
git commit -m "feat: add automatic theme runtime"
```

---

### Task 2: Responsive Theme Controls

**Files:**
- Modify: `tests/test_ui_shell.py:50-68,240-260`
- Modify: `app/templates/base.html:72-78`
- Modify: `app/static/style.css:1296-1304` and responsive sections near the existing 768px breakpoint

**Interfaces:**
- Consumes: `theme.js` hooks `[data-theme-mode-option]`, `[data-theme-toggle]`, and the mobile button's `data-theme-mode` state.
- Produces: `[data-theme-selector]` desktop group with three option buttons and one `[data-theme-toggle]` mobile button.
- Produces: `.theme-selector` visible at 769px and above; `.theme-toggle` visible at 768px and below.

- [ ] **Step 1: Write failing shell and stylesheet tests**

Extend `test_public_shell_has_accessible_navigation_footer_and_back_to_top`:

```python
assert 'static/theme.js' in html
assert 'data-theme-selector' in html
assert html.count('data-theme-mode-option=') == 3
assert 'data-theme-mode-option="auto"' in html
assert 'data-theme-mode-option="light"' in html
assert 'data-theme-mode-option="dark"' in html
assert 'aria-label="主题模式"' in html
assert '>自动</button>' in html
assert '>白天</button>' in html
assert '>夜间</button>' in html
```

Add a focused responsive CSS test:

```python
def test_theme_controls_switch_between_desktop_and_mobile_forms():
    css = Path('app/static/style.css').read_text()

    selector = _top_level_rule_bodies(css, '.theme-selector')[0]
    toggle = _top_level_rule_bodies(css, '.theme-toggle')[0]
    assert 'display: inline-flex;' in selector
    assert 'display: none;' in toggle

    mobile = css.rsplit('@media (max-width: 768px)', 1)[1]
    assert '.theme-selector {' in mobile
    assert 'display: none;' in mobile
    assert '.theme-toggle {' in mobile
    assert 'display: inline-flex;' in mobile
    assert 'width: 34px;' in mobile
    assert 'height: 34px;' in mobile
```

- [ ] **Step 2: Run the focused UI tests and verify RED**

Run: `pytest tests/test_ui_shell.py::test_public_shell_has_accessible_navigation_footer_and_back_to_top tests/test_ui_shell.py::test_theme_controls_switch_between_desktop_and_mobile_forms -v`

Expected: FAIL because the segmented markup and responsive styles are absent.

- [ ] **Step 3: Add accessible responsive markup**

Replace the existing theme button in `app/templates/base.html` with:

```html
<div class="theme-selector" role="group" aria-label="主题模式"
     data-theme-selector>
  <button type="button" data-theme-mode-option="auto"
          aria-pressed="false">自动</button>
  <button type="button" data-theme-mode-option="light"
          aria-pressed="false">白天</button>
  <button type="button" data-theme-mode-option="dark"
          aria-pressed="false">夜间</button>
</div>
<button class="icon-button theme-toggle" type="button" data-theme-toggle
        data-theme-mode="auto"
        aria-label="当前为自动模式；切换到白天模式"></button>
```

- [ ] **Step 4: Add stable segmented and mobile-control styles**

Replace the old appearance-driven theme icon rules with mode-driven rules and add the desktop segmented control:

```css
.theme-selector {
    height: 34px;
    padding: 2px;
    display: inline-flex;
    align-items: stretch;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-muted);
}

.theme-selector button {
    min-width: 46px;
    padding: 0 9px;
    color: var(--text-secondary);
    background: transparent;
    border: 0;
    border-radius: calc(var(--radius) - 1px);
    font-size: 13px;
    cursor: pointer;
}

.theme-selector button[aria-pressed="true"] {
    color: var(--text-primary);
    background: var(--surface);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.theme-toggle {
    width: 34px;
    min-width: 34px;
    height: 34px;
    display: none;
}

.theme-toggle::before {
    font-size: 18px;
    line-height: 1;
}

.theme-toggle[data-theme-mode="auto"]::before { content: "\25D0"; }
.theme-toggle[data-theme-mode="light"]::before { content: "\2600"; }
.theme-toggle[data-theme-mode="dark"]::before { content: "\263E"; }
```

In the existing final `@media (max-width: 768px)` block, add:

```css
.theme-selector { display: none; }
.theme-toggle { display: inline-flex; }
```

Add focus-visible styling consistent with the existing icon buttons. Do not key the mobile icon off `html[data-theme]`, because automatic mode's preference must remain visible even when its resolved appearance changes.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run: `pytest tests/test_ui_shell.py -v && node --test tests/theme.test.js tests/markdown_editor.test.js`

Expected: all UI shell and JavaScript tests PASS.

- [ ] **Step 6: Commit the responsive controls**

```bash
git add app/templates/base.html app/static/style.css tests/test_ui_shell.py
git commit -m "feat: add responsive theme controls"
```

---

### Task 3: Full Verification And Browser QA

**Files:**
- Verify only; modify Task 1 or Task 2 files only if a test or visual check exposes a defect.

**Interfaces:**
- Consumes: completed runtime, shared template controls, and responsive styles.
- Produces: verification evidence for automatic, light, and dark behavior on desktop and mobile.

- [ ] **Step 1: Run all automated tests**

Run:

```bash
pytest -q
node --test tests/theme.test.js tests/markdown_editor.test.js
```

Expected: all tests PASS with no failures or warnings attributable to this change.

- [ ] **Step 2: Start the local application**

Run the repository's documented development command from `README.md`, using an unused local port if the default is occupied. Record the final URL.

- [ ] **Step 3: Verify desktop behavior at 1440 by 900**

Use the in-app browser and verify:

- `自动 / 白天 / 夜间` is visible as one compact segmented control;
- only one option is selected and keyboard focus is visible;
- each option immediately changes the rendered theme and remains selected after reload;
- returning to `自动` resolves to the current emulated system scheme;
- navigation content does not overlap or wrap incoherently.

- [ ] **Step 4: Verify mobile behavior at 390 by 844**

Use the in-app browser and verify:

- the segmented control is hidden and exactly one 34px cycling button is visible;
- three clicks follow automatic, light, dark, automatic without layout movement;
- the accessible label and icon update after every click;
- opening the mobile navigation does not overlap the control or page content.

- [ ] **Step 5: Verify live automatic synchronization**

With automatic mode selected, emulate light then dark `prefers-color-scheme` and confirm the page changes immediately. Select fixed light and fixed dark in turn and confirm subsequent system changes do not override them.

- [ ] **Step 6: Inspect the final diff**

Run:

```bash
git diff --check
git status --short
git diff HEAD~2 -- app/static/theme.js app/static/site.js app/static/style.css app/templates/base.html tests/theme.test.js tests/test_ui_shell.py
```

Expected: no whitespace errors, no unrelated files, and only the scoped behavior described by the design.
