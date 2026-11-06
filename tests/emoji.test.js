const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'emoji.js'),
  'utf8',
);

function load() {
  const module = { exports: {} };
  vm.runInNewContext(source, { module, window: {}, document: undefined });
  return module.exports;
}

const { emojiKey, splitText: rawSplitText } = load();
// Arrays built inside the vm context have another prototype than ours.
const splitText = (...args) => JSON.parse(JSON.stringify(rawSplitText(...args)));
const keys = new Set(['1f600', '2764', '31-20e3', '1f44b']);

test('keys drop the variation selector and join code points', () => {
  assert.equal(emojiKey('😀'), '1f600');
  assert.equal(emojiKey('❤️'), '2764');
  assert.equal(emojiKey('1️⃣'), '31-20e3');
});

test('plain text comes back as one piece', () => {
  assert.deepEqual(splitText('hello 你好', keys), [{ text: 'hello 你好' }]);
});

test('bundled emoji are split out with their character and key', () => {
  assert.deepEqual(splitText('a😀b', keys), [
    { text: 'a' },
    { emoji: '😀', key: '1f600' },
    { text: 'b' },
  ]);
});

test('emoji written with a variation selector keep it in the character', () => {
  assert.deepEqual(splitText('❤️', keys), [{ emoji: '❤️', key: '2764' }]);
});

test('emoji that are not bundled stay as text', () => {
  assert.deepEqual(splitText('🦄 and 🇨🇳 and 👨‍👩‍👧', keys), [
    { text: '🦄 and 🇨🇳 and 👨‍👩‍👧' },
  ]);
});

test('digits and symbols are not mistaken for emoji', () => {
  assert.deepEqual(splitText('1 # * 2024', keys), [{ text: '1 # * 2024' }]);
});

test('keycaps are matched whole', () => {
  assert.deepEqual(splitText('1️⃣', keys), [
    { emoji: '1️⃣', key: '31-20e3' },
  ]);
});

test('neighbouring emoji become separate pieces', () => {
  assert.deepEqual(splitText('😀😀👋', keys).map((p) => p.key), ['1f600', '1f600', '1f44b']);
});
