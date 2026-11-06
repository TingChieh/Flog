const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'live-photo.js'), 'utf8');

function createHarness({ boxes = [], reducedMotion = false } = {}) {
  const timers = [];
  const videos = [];
  let now = 1000;

  const createBox = () => {
    const listeners = {};
    const classes = new Set();
    return {
      dataset: { liveVideo: '/files/a.mp4' },
      children: [],
      classList: {
        add: (name) => classes.add(name),
        remove: (name) => classes.delete(name),
        contains: (name) => classes.has(name),
      },
      append(node) { this.children.push(node); },
      addEventListener(name, fn, options) {
        (listeners[name] ||= []).push({ fn, capture: options === true });
      },
      fire(name, props = {}) {
        const event = {
          defaultPrevented: false, stopped: false, ...props,
          preventDefault() { this.defaultPrevented = true; },
          stopImmediatePropagation() { this.stopped = true; },
        };
        (listeners[name] || []).forEach(({ fn }) => fn(event));
        return event;
      },
    };
  };

  const createVideo = () => {
    const listeners = {};
    const video = {
      attributes: {}, className: '', plays: 0, pauses: 0, currentTime: 5,
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, fn) { listeners[name] = fn; },
      emit(name) { listeners[name](); },
      play() { this.plays += 1; return Promise.resolve(); },
      pause() { this.pauses += 1; },
    };
    videos.push(video);
    return video;
  };

  const context = {
    window: { matchMedia: () => ({ matches: reducedMotion }) },
    document: {
      readyState: 'complete',
      createElement: (tag) => (tag === 'video' ? createVideo() : {}),
      querySelectorAll: () => boxes,
      addEventListener() {},
    },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].cancelled = true; },
    Date: { now: () => now },
  };
  vm.runInNewContext(source, context);
  return {
    live: context.window.FlogLivePhoto, createBox, videos, timers,
    advance(ms) { now += ms; },
    runTimers() { timers.filter((t) => !t.cancelled && !t.done).forEach((t) => { t.done = true; t.fn(); }); },
  };
}

test('init fetches no clip before the visitor interacts', () => {
  const box = createHarness().createBox();
  const harness = createHarness({ boxes: [box] });
  assert.ok(harness.live);
  assert.equal(harness.videos.length, 0);
});

test('hovering with a mouse plays the clip and leaving stops it', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  box.fire('pointerenter', { pointerType: 'mouse' });
  const [video] = harness.videos;
  assert.equal(video.src, '/files/a.mp4');
  assert.equal(video.muted, true);
  assert.equal(video.playsInline, true);
  assert.equal(video.plays, 1);
  assert.equal(box.classList.contains('is-playing'), false, 'only shows once it is really playing');

  video.emit('playing');
  assert.equal(box.classList.contains('is-playing'), true);

  box.fire('pointerleave', { pointerType: 'mouse' });
  assert.equal(box.classList.contains('is-playing'), false);
  assert.equal(video.pauses, 1);
});

test('touch and pen pointers do not trigger hover playback', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  box.fire('pointerenter', { pointerType: 'touch' });
  box.fire('pointerenter', { pointerType: 'pen' });
  assert.equal(harness.videos.length, 0);
});

test('a long press plays after a delay and releasing stops it', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  box.fire('touchstart');
  assert.equal(harness.videos.length, 1, 'the clip starts loading right away');
  assert.equal(harness.videos[0].plays, 0);
  harness.runTimers();
  assert.equal(harness.videos[0].plays, 1);
  harness.videos[0].emit('playing');
  assert.equal(box.classList.contains('is-playing'), true);

  box.fire('touchend');
  assert.equal(box.classList.contains('is-playing'), false);
});

test('a quick tap or a scroll never starts the clip', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  box.fire('touchstart');
  box.fire('touchend');
  harness.runTimers();
  assert.equal(harness.videos[0].plays, 0);

  box.fire('touchstart');
  box.fire('touchmove');
  harness.runTimers();
  assert.equal(harness.videos[0].plays, 0);
});

test('releasing a long press does not open the lightbox, a later tap does', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  box.fire('touchstart');
  harness.runTimers();
  box.fire('touchend');
  const swallowed = box.fire('click');
  assert.equal(swallowed.stopped, true);
  assert.equal(swallowed.defaultPrevented, true);

  harness.advance(1000);
  assert.equal(box.fire('click').stopped, false);
});

test('a clip that finishes returns to the still', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);
  box.fire('pointerenter', { pointerType: 'mouse' });
  harness.videos[0].emit('playing');

  harness.videos[0].emit('ended');
  assert.equal(box.classList.contains('is-playing'), false);
});

test('a clip that starts after the pointer left is stopped, not shown', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);
  box.fire('pointerenter', { pointerType: 'mouse' });
  box.fire('pointerleave', { pointerType: 'mouse' });

  harness.videos[0].emit('playing');
  assert.equal(box.classList.contains('is-playing'), false);
  assert.ok(harness.videos[0].pauses >= 2);
});

test('the image context menu is suppressed so a long press can play', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box);

  assert.equal(box.fire('contextmenu').defaultPrevented, true);
});

test('reduced motion keeps the still and never plays', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { reducedMotion: true });

  box.fire('pointerenter', { pointerType: 'mouse' });
  box.fire('touchstart');
  harness.runTimers();
  assert.equal(harness.videos.length, 0);
});
