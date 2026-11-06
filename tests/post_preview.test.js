const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const read = (name) => fs.readFileSync(path.join(__dirname, '..', 'app', 'static', name), 'utf8');

function runPreview({ missing = false } = {}) {
  let clickHandler;
  let submitted = 0;
  let readyHandler;
  const button = { addEventListener(name, handler) { assert.equal(name, 'click'); clickHandler = handler; } };
  const preview = { elements: { title: { value: '' }, body: { value: '' } }, submit() { submitted += 1; } };
  const editor = { elements: { title: { value: '标题' }, post: { value: '# 正文' } } };
  const document = {
    addEventListener(name, handler) { assert.equal(name, 'DOMContentLoaded'); readyHandler = handler; },
    querySelector: (selector) => { assert.equal(selector, '[data-post-preview]'); return missing ? null : button; },
    getElementById: (id) => ({ 'post-preview-form': preview, 'article-editor-form': editor }[id]),
  };
  vm.runInNewContext(read('post-preview.js'), { document });
  readyHandler();
  return { preview, editor, click: () => clickHandler(), submitted: () => submitted };
}

test('clicking Preview copies the editor title and body into the hidden form and submits it', () => {
  const harness = runPreview();

  harness.click();

  assert.equal(harness.preview.elements.title.value, '标题');
  assert.equal(harness.preview.elements.body.value, '# 正文');
  assert.equal(harness.submitted(), 1);
});

test('each click sends what the editor holds at that moment', () => {
  const harness = runPreview();
  harness.click();

  harness.editor.elements.post.value = '改过的正文';
  harness.click();

  assert.equal(harness.preview.elements.body.value, '改过的正文');
  assert.equal(harness.submitted(), 2);
});

test('a page without the button does nothing', () => {
  assert.doesNotThrow(() => runPreview({ missing: true }));
});

function runBar({ closes }) {
  let clickHandler;
  const label = { textContent: '预览：……' };
  const window = { closed: false, close() { this.closed = closes; } };
  const closeButton = { addEventListener(name, handler) { clickHandler = handler; } };
  const document = {
    querySelector: (selector) => ({ '[data-preview-close]': closeButton, '.preview-bar span': label }[selector]),
  };
  vm.runInNewContext(read('post-preview-bar.js'), { document, window });
  clickHandler();
  return label;
}

test('Close preview closes the tab it was opened in', () => {
  assert.equal(runBar({ closes: true }).textContent, '预览：……');
});

test('when the browser refuses to close the tab it says so', () => {
  assert.equal(runBar({ closes: false }).textContent, '可以直接关闭此标签页。');
});
