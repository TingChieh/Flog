const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'site.js'),
  'utf8',
);

function createClassList() {
  const names = new Set();
  return {
    add: (name) => names.add(name),
    remove: (name) => names.delete(name),
    contains: (name) => names.has(name),
    toggle(name, force) {
      const next = force === undefined ? !names.has(name) : Boolean(force);
      if (next) names.add(name);
      else names.delete(name);
      return next;
    },
  };
}

function createHarness({ scrollY = 0, innerHeight = 800, reducedMotion = false } = {}) {
  const docListeners = {};
  const winListeners = {};
  const navAttrs = { 'aria-expanded': 'false' };
  const navToggle = {
    focused: false,
    attrs: navAttrs,
    listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
    setAttribute(name, value) { navAttrs[name] = value; },
    focus() { this.focused = true; },
  };
  const nav = { hidden: true, classList: createClassList() };
  const backToTop = {
    hidden: true,
    listeners: {},
    addEventListener(type, fn) { this.listeners[type] = fn; },
  };
  const scrolled = [];
  const context = {
    scrollY,
    innerHeight,
    matchMedia: () => ({ matches: reducedMotion }),
    addEventListener(type, fn) { winListeners[type] = fn; },
    scrollTo(opts) { scrolled.push({ top: opts.top, behavior: opts.behavior }); },
    document: {
      addEventListener(type, fn) { docListeners[type] = fn; },
      querySelector(selector) {
        return {
          '[data-nav-toggle]': navToggle,
          '[data-site-nav]': nav,
          '[data-back-to-top]': backToTop,
        }[selector] || null;
      },
    },
  };
  vm.runInNewContext(source, context);
  docListeners.DOMContentLoaded();
  return { context, navToggle, nav, backToTop, docListeners, winListeners, scrolled };
}

test('mobile navigation toggle opens menu and Escape closes it with focus restored', () => {
  const { navToggle, nav, docListeners } = createHarness();

  navToggle.listeners.click();
  assert.equal(nav.hidden, false);
  assert.equal(nav.classList.contains('site-nav__menu--open'), true);
  assert.equal(navToggle.attrs['aria-expanded'], 'true');

  docListeners.keydown({ key: 'Escape', defaultPrevented: false });
  assert.equal(nav.hidden, true);
  assert.equal(nav.classList.contains('site-nav__menu--open'), false);
  assert.equal(navToggle.attrs['aria-expanded'], 'false');
  assert.equal(navToggle.focused, true);
});

test('back-to-top button appears after one viewport of scrolling and respects reduced motion', () => {
  const { context, backToTop, winListeners, scrolled } = createHarness({
    scrollY: 0,
    innerHeight: 600,
    reducedMotion: true,
  });

  assert.equal(backToTop.hidden, true);
  context.scrollY = 900;
  winListeners.scroll();
  assert.equal(backToTop.hidden, false);

  backToTop.listeners.click();
  assert.deepEqual(scrolled, [{ top: 0, behavior: 'auto' }]);
});
