const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'theme.js'),
  'utf8',
);

function createToggle() {
  const listeners = {};
  const label = {textContent: ''};
  return {
    dataset: {},
    attributes: {},
    label,
    addEventListener(name, listener) { listeners[name] = listener; },
    setAttribute(name, value) { this.attributes[name] = value; },
    querySelector(selector) {
      assert.equal(selector, '[data-theme-label]');
      return label;
    },
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
  const toggle = createToggle();
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
      removeItem(key) {
        if (storageThrows) throw new Error('storage unavailable');
        stored.delete(key);
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
    context, media, root, stored, toggle,
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

test('the toggle flips between light and dark and remembers the choice', () => {
  const harness = createHarness({systemDark: false});
  harness.ready();

  const cases = [
    {theme: 'dark', text: '主题：夜间', label: '当前为夜间模式；切换到白天模式'},
    {theme: 'light', text: '主题：白天', label: '当前为白天模式；切换到夜间模式'},
    {theme: 'dark', text: '主题：夜间', label: '当前为夜间模式；切换到白天模式'},
  ];

  for (const {theme, text, label} of cases) {
    harness.toggle.click();

    assert.equal(harness.context.FlogTheme.getMode(), theme);
    assert.equal(harness.stored.get('theme'), theme);
    assert.equal(harness.root.dataset.theme, theme);
    assert.equal(harness.toggle.dataset.themeMode, theme);
    assert.equal(harness.toggle.attributes['aria-label'], label);
    assert.equal(harness.toggle.attributes.title, label);
    assert.equal(harness.toggle.label.textContent, text);
  }
});

test('without a saved choice the toggle shows the system theme and flips away from it', () => {
  const harness = createHarness({systemDark: true});
  harness.ready();

  assert.equal(harness.context.FlogTheme.getMode(), 'auto');
  assert.equal(harness.toggle.dataset.themeMode, 'dark');
  assert.equal(harness.toggle.label.textContent, '主题：夜间');
  assert.equal(harness.stored.has('theme'), false);

  harness.toggle.click();
  assert.equal(harness.stored.get('theme'), 'light');
  assert.equal(harness.root.dataset.theme, 'light');
  assert.equal(harness.toggle.dataset.themeMode, 'light');
});

test('a saved preference is reflected on the toggle once the page is ready', () => {
  const harness = createHarness({savedTheme: 'dark'});
  harness.ready();

  assert.equal(harness.toggle.dataset.themeMode, 'dark');
  assert.equal(harness.toggle.attributes['aria-label'], '当前为夜间模式；切换到白天模式');
  assert.equal(harness.toggle.attributes.title, '当前为夜间模式；切换到白天模式');
  assert.equal(harness.toggle.label.textContent, '主题：夜间');
});

test('system changes update the toggle only while no choice is saved', () => {
  const harness = createHarness({systemDark: false});
  harness.ready();
  assert.equal(harness.toggle.dataset.themeMode, 'light');

  harness.setSystemDark(true);
  assert.equal(harness.toggle.dataset.themeMode, 'dark');
  assert.equal(harness.toggle.label.textContent, '主题：夜间');

  harness.toggle.click();
  assert.equal(harness.stored.get('theme'), 'light');
  harness.setSystemDark(false);
  harness.setSystemDark(true);
  assert.equal(harness.toggle.dataset.themeMode, 'light');
});

test('setMode auto forgets the saved choice and unknown values count as auto', () => {
  const harness = createHarness({savedTheme: 'light', systemDark: true});
  harness.ready();
  assert.equal(harness.root.dataset.theme, 'light');

  harness.context.FlogTheme.setMode('auto');
  assert.equal(harness.stored.has('theme'), false);
  assert.equal(harness.root.dataset.themeMode, 'auto');
  assert.equal(harness.root.dataset.theme, 'dark');
  assert.equal(harness.toggle.dataset.themeMode, 'dark');

  harness.context.FlogTheme.setMode('sepia');
  assert.equal(harness.root.dataset.themeMode, 'auto');
  assert.equal(harness.stored.has('theme'), false);
});

test('setMode from script keeps the toggle in sync', () => {
  const harness = createHarness();
  harness.ready();
  harness.context.FlogTheme.setMode('dark');

  assert.equal(harness.toggle.dataset.themeMode, 'dark');
  assert.equal(harness.toggle.label.textContent, '主题：夜间');
});
