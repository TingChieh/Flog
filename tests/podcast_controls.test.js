const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'podcast-controls.js'),
  'utf8',
);

function element(extra = {}) {
  const listeners = {};
  const attributes = {};
  const styles = {};
  return {
    dataset: {},
    textContent: '',
    hidden: false,
    style: { setProperty: (name, value) => { styles[name] = value; }, styles },
    attributes,
    setAttribute: (name, value) => { attributes[name] = value; },
    addEventListener: (type, handler) => { (listeners[type] ||= []).push(handler); },
    emit: (type) => (listeners[type] || []).forEach((handler) => handler({})),
    ...extra,
  };
}

function build({ duration = 125, audioDuration = NaN } = {}) {
  const audio = element({
    controls: true,
    paused: true,
    ended: false,
    currentTime: 0,
    duration: audioDuration,
    playbackRate: 1,
    played: 0,
    paused_: 0,
    play() { this.played += 1; this.paused = false; this.emit('play'); return Promise.resolve(); },
    pause() { this.paused_ += 1; this.paused = true; this.emit('pause'); },
  });
  const play = element();
  const seek = element({ max: '', value: '' });
  const current = element();
  const total = element();
  const rate = element({ textContent: '1×' });
  const skipBack = element({ dataset: { playerSkip: '-15' } });
  const skipForward = element({ dataset: { playerSkip: '30' } });
  const controls = element({
    hidden: true,
    querySelector(selector) {
      return {
        '[data-player-play]': play,
        '[data-player-seek]': seek,
        '[data-player-current]': current,
        '[data-player-total]': total,
        '[data-player-rate]': rate,
      }[selector];
    },
    querySelectorAll: () => [skipBack, skipForward],
  });
  const root = element({
    dataset: { duration: String(duration) },
    querySelector: (selector) => (selector === '[data-episode-audio]' ? audio : controls),
  });
  vm.runInNewContext(source, {
    document: { querySelector: (selector) => (selector === '[data-podcast-player]' ? root : null) },
  });
  return { audio, controls, play, seek, current, total, rate, skipBack, skipForward };
}

test('the browser controls are swapped for the site ones', () => {
  const { audio, controls } = build();
  assert.equal(audio.controls, false);
  assert.equal(audio.hidden, true);
  assert.equal(controls.hidden, false);
});

test('the length from the page shows before any audio has loaded', () => {
  const { total, seek, current } = build({ duration: 7547 });
  assert.equal(total.textContent, '2:05:47');
  assert.equal(seek.max, '7547');
  assert.equal(current.textContent, '0:00');
});

test('the play button plays, pauses and says which it will do', () => {
  const { audio, play } = build();
  assert.equal(play.dataset.state, 'paused');
  assert.equal(play.attributes['aria-label'], '播放');
  play.emit('click');
  assert.equal(audio.played, 1);
  assert.equal(play.dataset.state, 'playing');
  assert.equal(play.attributes['aria-label'], '暂停');
  play.emit('click');
  assert.equal(audio.paused_, 1);
  assert.equal(play.dataset.state, 'paused');
});

test('progress follows the audio', () => {
  const { audio, current, seek } = build({ duration: 100 });
  audio.currentTime = 25;
  audio.emit('timeupdate');
  assert.equal(current.textContent, '0:25');
  assert.equal(seek.value, '25');
  assert.equal(seek.style.styles['--progress'], '25%');
});

test('the real length replaces the one from the page once it is known', () => {
  const { audio, total } = build({ duration: 100 });
  audio.duration = 3600;
  audio.emit('loadedmetadata');
  assert.equal(total.textContent, '1:00:00');
});

test('dragging the bar seeks', () => {
  const { audio, seek, current } = build({ duration: 600 });
  seek.value = '125';
  seek.emit('input');
  assert.equal(audio.currentTime, 125);
  assert.equal(current.textContent, '2:05');
});

test('skip buttons move within the episode and never past its ends', () => {
  const { audio, skipBack, skipForward } = build({ duration: 100 });
  audio.currentTime = 10;
  skipBack.emit('click');
  assert.equal(audio.currentTime, 0);
  audio.currentTime = 90;
  skipForward.emit('click');
  assert.equal(audio.currentTime, 100);
  audio.currentTime = 40;
  skipForward.emit('click');
  assert.equal(audio.currentTime, 70);
});

test('the speed button cycles and labels the speed', () => {
  const { audio, rate } = build();
  const seen = [];
  for (let i = 0; i < 5; i += 1) {
    rate.emit('click');
    seen.push([audio.playbackRate, rate.textContent]);
  }
  assert.deepEqual(seen, [[1.25, '1.25×'], [1.5, '1.5×'], [2, '2×'], [0.75, '0.75×'], [1, '1×']]);
});

test('the end of the episode shows the play button again', () => {
  const { audio, play } = build();
  play.emit('click');
  audio.paused = true;
  audio.ended = true;
  audio.emit('ended');
  assert.equal(play.dataset.state, 'paused');
});

test('a page without a player is left alone', () => {
  assert.doesNotThrow(() => vm.runInNewContext(source, {
    document: { querySelector: () => null },
  }));
});
