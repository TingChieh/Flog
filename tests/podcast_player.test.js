const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'podcast-player.js'),
  'utf8',
);

function line(text) {
  const classes = new Set();
  return {
    textContent: text,
    dataset: {},
    classList: { add: (name) => classes.add(name), has: (name) => classes.has(name) },
    closest(selector) {
      return selector === '[data-seek]' && 'seek' in this.dataset ? this : null;
    },
  };
}

function run(lines) {
  const audio = { currentTime: 0, played: 0, play() { this.played += 1; return Promise.resolve(); } };
  let click;
  const notes = {
    querySelectorAll: () => lines,
    addEventListener: (type, handler) => { if (type === 'click') click = handler; },
  };
  vm.runInNewContext(source, {
    document: {
      querySelector: (selector) => (selector === '[data-episode-audio]' ? audio : notes),
    },
  });
  return { audio, click };
}

test('lines that start with a time jump the player there', () => {
  const lines = [line('[01:35] 阿丁吃不惯江苏菜'), line('[1:01:00]在上新疆家里蹲'), line('没有时间的一行')];
  const { audio, click } = run(lines);
  assert.equal(lines[0].dataset.seek, '95');
  assert.equal(lines[1].dataset.seek, '3660');
  assert.ok(!('seek' in lines[2].dataset));
  assert.ok(lines[0].classList.has('is-seekable'));
  click({ target: lines[0] });
  assert.equal(audio.currentTime, 95);
  assert.equal(audio.played, 1);
});

test('a time without brackets, or with a missing closing bracket, still counts', () => {
  const lines = [line('24:41 为什么学校不能骑电动车'), line('[1:01:00在上新疆')];
  run(lines);
  assert.equal(lines[0].dataset.seek, String(24 * 60 + 41));
  assert.equal(lines[1].dataset.seek, '3660');
});

test('clicking a link inside a line does not move the player', () => {
  const lines = [line('[00:10] see <a>this</a>')];
  const { audio, click } = run(lines);
  click({ target: { closest: (selector) => (selector === 'a' ? {} : null) } });
  assert.equal(audio.currentTime, 0);
  assert.equal(audio.played, 0);
});

test('clicking outside a timed line does nothing', () => {
  const { audio, click } = run([line('[00:10] x')]);
  click({ target: { closest: () => null } });
  assert.equal(audio.played, 0);
});

test('a page without the player or notes is left alone', () => {
  assert.doesNotThrow(() => vm.runInNewContext(source, {
    document: { querySelector: () => null },
  }));
});
