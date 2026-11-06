const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'shortcut-hint.js'),
  'utf8',
);

function run(navigator) {
  const hint = { textContent: 'Ctrl K' };
  vm.runInNewContext(source, {
    navigator,
    document: {
      querySelectorAll(selector) {
        assert.equal(selector, '[data-shortcut-hint]');
        return [hint];
      },
    },
  });
  return hint.textContent;
}

test('a Mac shows the command key', () => {
  assert.equal(run({ platform: 'MacIntel' }), '⌘ K');
});

test('browsers that report the platform separately are read too', () => {
  assert.equal(run({ userAgentData: { platform: 'macOS' }, platform: '' }), '⌘ K');
});

test('Windows and Linux keep Ctrl', () => {
  assert.equal(run({ platform: 'Win32' }), 'Ctrl K');
  assert.equal(run({ userAgentData: { platform: 'Linux' }, platform: 'Linux x86_64' }), 'Ctrl K');
});

test('a phone, which has no shortcut keys anyway, keeps the default', () => {
  assert.equal(run({ platform: 'iPhone' }), 'Ctrl K');
});

test('missing platform information leaves the default', () => {
  assert.equal(run({}), 'Ctrl K');
});
