const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'lazy-images.js'),
  'utf8',
);

function createImage({ complete }) {
  const listeners = {};
  const classes = new Set();
  const attributes = new Map();
  return {
    complete,
    classes,
    attributes,
    classList: { add: (name) => classes.add(name) },
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
    addEventListener: (name, listener) => { listeners[name] = listener; },
    fire: (name) => listeners[name](),
  };
}

function run(images) {
  vm.runInNewContext(source, {
    document: {
      querySelectorAll(selector) {
        assert.equal(selector, '.article-body img, .page-body img');
        return images;
      },
    },
  });
}

test('a photo still on its way is held as a placeholder', () => {
  const image = createImage({ complete: false });

  run([image]);

  assert.equal(image.attributes.has('data-loading'), true);
  assert.equal(image.classes.has('is-loaded'), false);
});

test('when it arrives the placeholder goes and the fade-in starts', () => {
  const image = createImage({ complete: false });
  run([image]);

  image.fire('load');

  assert.equal(image.attributes.has('data-loading'), false);
  assert.equal(image.classes.has('is-loaded'), true);
});

test('a photo that fails to load drops the placeholder without fading in', () => {
  const image = createImage({ complete: false });
  run([image]);

  image.fire('error');

  assert.equal(image.attributes.has('data-loading'), false);
  assert.equal(image.classes.has('is-loaded'), false);
});

test('a photo already in the cache is left untouched', () => {
  const image = createImage({ complete: true });

  run([image]);

  assert.equal(image.attributes.size, 0);
  assert.equal(image.classes.size, 0);
});
