const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'live-photo.js'), 'utf8');

function createHarness({ boxes = [], reducedMotion = false, playRejects = false } = {}) {
  const videos = [];

  const createListeners = () => {
    const listeners = {};
    return {
      listeners,
      addEventListener(name, fn) { (listeners[name] ||= []).push(fn); },
    };
  };

  const createBox = () => {
    const classes = new Set();
    const badge = {
      ...createListeners(), attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      click() {
        const event = {
          defaultPrevented: false, propagationStopped: false,
          preventDefault() { this.defaultPrevented = true; },
          stopPropagation() { this.propagationStopped = true; },
        };
        (this.listeners.click || []).forEach((fn) => fn(event));
        return event;
      },
    };
    return {
      ...createListeners(), badge, dataset: { liveVideo: '/files/a.mp4' }, children: [],
      classList: {
        toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
        contains: (name) => classes.has(name),
      },
      querySelector: (selector) => (selector === '.live-photo__badge' ? badge : null),
      append(node) { this.children.push(node); },
    };
  };

  const createVideo = () => {
    const video = {
      ...createListeners(), attributes: {}, plays: 0, pauses: 0, currentTime: 5,
      setAttribute(name, value) { this.attributes[name] = value; },
      emit(name) { (this.listeners[name] || []).forEach((fn) => fn()); },
      play() {
        this.plays += 1;
        return playRejects ? Promise.reject(new Error('NotAllowedError')) : Promise.resolve();
      },
      pause() { this.pauses += 1; },
    };
    videos.push(video);
    return video;
  };

  const observed = [];
  const observe = (element, callback, ratio) => observed.push({ element, callback, ratio });

  const context = {
    window: { matchMedia: () => ({ matches: reducedMotion }) },
    document: {
      readyState: 'complete',
      createElement: (tag) => (tag === 'video' ? createVideo() : {}),
      querySelectorAll: () => boxes,
      addEventListener() {},
    },
  };
  vm.runInNewContext(source, context);
  return {
    live: context.window.FlogLivePhoto, createBox, videos, observed, observe,
    settle: async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); },
  };
}

test('nothing is fetched until the photo scrolls into view', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });

  assert.equal(harness.videos.length, 0);
  assert.equal(harness.observed.length, 1);
  assert.equal(harness.observed[0].element, box);
  assert.ok(harness.observed[0].ratio >= 0.9, 'waits until (nearly) the whole photo is visible');
});

test('it plays by itself once when it comes into view', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });

  harness.observed[0].callback();
  const [video] = harness.videos;
  assert.equal(video.src, '/files/a.mp4');
  assert.equal(video.muted, true);
  assert.equal(video.playsInline, true);
  assert.equal(video.plays, 1);
  assert.equal(box.classList.contains('is-playing'), false, 'shows only once it is really playing');

  video.emit('playing');
  assert.equal(box.classList.contains('is-playing'), true);
  assert.equal(box.badge.attributes['aria-pressed'], 'true');

  video.emit('ended');
  assert.equal(box.classList.contains('is-playing'), false);
  assert.equal(box.badge.attributes['aria-pressed'], 'false');
  assert.equal(harness.observed.length, 1, 'no second automatic play is scheduled');
});

test('after that the LIVE button plays it again', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });
  harness.observed[0].callback();
  harness.videos[0].emit('playing');
  harness.videos[0].emit('ended');

  const event = box.badge.click();
  assert.equal(harness.videos.length, 1, 'reuses the same video');
  assert.equal(harness.videos[0].plays, 2);
  assert.equal(harness.videos[0].currentTime, 0, 'restarts from the beginning');
  assert.equal(event.defaultPrevented, true);
  assert.equal(event.propagationStopped, true);
  harness.videos[0].emit('playing');
  assert.equal(box.classList.contains('is-playing'), true);
});

test('clicking LIVE while it plays stops it', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });
  box.badge.click();
  harness.videos[0].emit('playing');

  box.badge.click();
  assert.equal(box.classList.contains('is-playing'), false);
  assert.equal(harness.videos[0].pauses, 1);
});

test('a clip that starts after it was stopped is paused, not shown', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });
  box.badge.click();
  box.badge.click();

  harness.videos[0].emit('playing');
  assert.equal(box.classList.contains('is-playing'), false);
  assert.ok(harness.videos[0].pauses >= 2);
});

test('hovering or touching the photo no longer plays it', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });

  assert.deepEqual(Object.keys(box.listeners), []);
  assert.equal(harness.videos.length, 0);
});

test('refused autoplay leaves the still and the button still works', async () => {
  const harness = createHarness({ playRejects: true });
  const box = harness.createBox();
  harness.live.attach(box, { observe: harness.observe });

  harness.observed[0].callback();
  await harness.settle();
  assert.equal(box.classList.contains('is-playing'), false);

  box.badge.click();
  assert.equal(harness.videos[0].plays, 2, 'a click is a fresh attempt');
});

test('without autoplay (reduced motion) only the button plays', () => {
  const harness = createHarness();
  const box = harness.createBox();
  harness.live.attach(box, { autoplay: false, observe: harness.observe });

  assert.equal(harness.observed.length, 0);
  box.badge.click();
  assert.equal(harness.videos[0].plays, 1);
});

test('init skips automatic playback when the visitor prefers reduced motion', () => {
  const box = createHarness().createBox();
  const harness = createHarness({ boxes: [box], reducedMotion: true });
  assert.ok(harness.live);
  assert.equal(harness.videos.length, 0);
  assert.equal(box.badge.listeners.click.length, 1, 'the button is still wired up');
});

function createObserverHarness() {
  const timers = [];
  const observers = [];
  class FakeObserver {
    constructor(callback, options) { this.callback = callback; this.options = options; this.disconnected = false; observers.push(this); }
    observe(element) { this.element = element; }
    disconnect() { this.disconnected = true; }
    report(isIntersecting) { this.callback([{ isIntersecting }]); }
  }
  const context = {
    window: {},
    document: { readyState: 'complete', querySelectorAll: () => [], addEventListener() {} },
    IntersectionObserver: FakeObserver,
    setTimeout: (fn, ms) => { timers.push({ fn, ms, cancelled: false }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].cancelled = true; },
  };
  vm.runInNewContext(source, context);
  return {
    observeOnce: context.window.FlogLivePhoto.observeOnce, observers, timers,
    fire() { timers.filter((t) => !t.cancelled && !t.done).forEach((t) => { t.done = true; t.fn(); }); },
  };
}

test('automatic play needs the photo (nearly) fully on screen and a moment of stillness', () => {
  const harness = createObserverHarness();
  const element = {};
  const calls = [];
  harness.observeOnce(element, () => calls.push('play'), 0.9);

  const [observer] = harness.observers;
  assert.equal(observer.element, element);
  assert.equal(observer.options.threshold, 0.9);

  observer.report(true);
  assert.deepEqual(calls, [], 'not at the instant it appears');
  assert.ok(harness.timers[0].ms >= 300);
  harness.fire();
  assert.deepEqual(calls, ['play']);
  assert.equal(observer.disconnected, true, 'only ever once');
});

test('flicking past the photo does not start it', () => {
  const harness = createObserverHarness();
  const calls = [];
  harness.observeOnce({}, () => calls.push('play'), 0.9);
  const [observer] = harness.observers;

  observer.report(true);
  observer.report(false);
  harness.fire();
  assert.deepEqual(calls, []);
  assert.equal(observer.disconnected, false, 'still waiting for it to come back');

  observer.report(true);
  harness.fire();
  assert.deepEqual(calls, ['play']);
});

test('a browser without IntersectionObserver just skips the automatic play', () => {
  const context = {
    window: {}, document: { readyState: 'complete', querySelectorAll: () => [], addEventListener() {} },
  };
  vm.runInNewContext(source, context);
  assert.doesNotThrow(() => context.window.FlogLivePhoto.observeOnce({}, () => {}, 0.9));
});
