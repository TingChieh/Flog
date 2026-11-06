const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'qr-share.js'),
  'utf8',
);

function createHarness({ withLibrary = true } = {}) {
  const toggleListeners = {};
  const documentListeners = {};
  const attributes = {};
  const drawn = [];
  const target = { textContent: '', classList: { added: [], add(name) { this.added.push(name); } } };
  const panel = { hidden: true };
  let focused = 0;
  const toggle = {
    addEventListener(name, listener) { toggleListeners[name] = listener; },
    setAttribute(name, value) { attributes[name] = value; },
    focus() { focused += 1; },
  };
  const share = {
    dataset: { url: 'https://example.com/post/1' },
    querySelector(selector) {
      return { '.qr-share__toggle': toggle, '.qr-share__panel': panel, '[data-qr-target]': target }[selector];
    },
    contains(node) { return node === toggle || node === panel; },
  };
  function QRCode(element, options) { drawn.push({ element, options }); }
  QRCode.CorrectLevel = { M: 0 };
  const context = {
    document: {
      querySelector(selector) {
        assert.equal(selector, '[data-qr-share]');
        return share;
      },
      addEventListener(name, listener) { documentListeners[name] = listener; },
    },
  };
  if (withLibrary) context.QRCode = QRCode;
  vm.runInNewContext(source, context);
  return {
    panel, target, drawn, attributes,
    focused: () => focused,
    click: () => toggleListeners.click(),
    outsideClick: (node = {}) => documentListeners.click({ target: node }),
    key: (key) => documentListeners.keydown({ key }),
  };
}

test('the panel stays closed and the code is not drawn until asked for', () => {
  const harness = createHarness();

  assert.equal(harness.panel.hidden, true);
  assert.equal(harness.drawn.length, 0);
});

test('opening draws the article address once, dark on white', () => {
  const harness = createHarness();

  harness.click();
  harness.click();
  harness.click();

  assert.equal(harness.panel.hidden, false);
  assert.equal(harness.attributes['aria-expanded'], 'true');
  assert.equal(harness.drawn.length, 1);
  assert.equal(harness.drawn[0].options.text, 'https://example.com/post/1');
  assert.equal(harness.drawn[0].options.colorDark, '#1d1d1f');
  assert.equal(harness.drawn[0].options.colorLight, '#ffffff');
});

test('clicking elsewhere closes it, clicking inside does not', () => {
  const harness = createHarness();
  harness.click();

  harness.outsideClick(harness.panel);
  assert.equal(harness.panel.hidden, false);

  harness.outsideClick({});
  assert.equal(harness.panel.hidden, true);
  assert.equal(harness.attributes['aria-expanded'], 'false');
});

test('Escape closes it and returns focus to the button', () => {
  const harness = createHarness();
  harness.click();

  harness.key('Enter');
  assert.equal(harness.panel.hidden, false);

  harness.key('Escape');
  assert.equal(harness.panel.hidden, true);
  assert.equal(harness.focused(), 1);
});

test('without the QR library the address is shown as text', () => {
  const harness = createHarness({ withLibrary: false });

  harness.click();

  assert.equal(harness.target.textContent, 'https://example.com/post/1');
  assert.deepEqual(harness.target.classList.added, ['qr-share__code--text']);
});
