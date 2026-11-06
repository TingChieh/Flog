const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'emoji-picker.js'),
  'utf8',
);

function load() {
  const module = { exports: {} };
  vm.runInNewContext(source, { module, window: {}, document: undefined });
  return module.exports;
}

const { searchGroups, pushRecent, insertAtCursor } = load();
// Arrays built inside the vm context have another prototype than ours.
const plain = (value) => JSON.parse(JSON.stringify(value));

const groups = [
  { id: 'a', label: '表情', items: [['😀', '嘻嘻笑', '脸 笑 开心 grinning face'], ['😢', '流泪', '脸 哭 crying face']] },
  { id: 'b', label: '符号', items: [['❤️', '红心', '心 爱 red heart']] },
];

test('search matches names and keywords', () => {
  assert.deepEqual(plain(searchGroups(groups, '哭')).map((i) => i[0]), ['😢']);
  assert.deepEqual(plain(searchGroups(groups, '红心')).map((i) => i[0]), ['❤️']);
  assert.deepEqual(plain(searchGroups(groups, 'HEART')).map((i) => i[0]), ['❤️']);
});

test('every word of the query has to match', () => {
  assert.deepEqual(plain(searchGroups(groups, '脸 哭')).map((i) => i[0]), ['😢']);
  assert.deepEqual(plain(searchGroups(groups, '脸 爱')), []);
});

test('blank search finds nothing to filter on', () => {
  assert.deepEqual(plain(searchGroups(groups, '   ')), []);
});

test('recent list puts the newest first without repeats and stays short', () => {
  assert.deepEqual(plain(pushRecent(['a', 'b'], 'c', 3)), ['c', 'a', 'b']);
  assert.deepEqual(plain(pushRecent(['a', 'b', 'c'], 'b', 3)), ['b', 'a', 'c']);
  assert.deepEqual(plain(pushRecent(['a', 'b', 'c'], 'd', 3)), ['d', 'a', 'b']);
});

function fakeField(value, start, end) {
  const events = [];
  return {
    value, selectionStart: start, selectionEnd: end, events,
    setRangeText(text, from, to, mode) {
      this.value = this.value.slice(0, from) + text + this.value.slice(to);
      if (mode === 'end') this.selectionStart = this.selectionEnd = from + text.length;
    },
    focus() { this.focused = true; },
    dispatchEvent(event) { events.push(event.type); },
  };
}

test('insert goes at the cursor, replaces a selection and announces the change', () => {
  const field = fakeField('hello world', 5, 5);
  insertAtCursor(field, '😀', (type) => ({ type }));
  assert.equal(field.value, 'hello😀 world');
  assert.equal(field.selectionStart, 5 + '😀'.length);
  assert.equal(field.focused, true);
  assert.deepEqual(field.events, ['input']);

  const replaced = fakeField('abcdef', 1, 4);
  insertAtCursor(replaced, 'X', (type) => ({ type }));
  assert.equal(replaced.value, 'aXef');
});
