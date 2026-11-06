const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'comment-reply.js'),
  'utf8',
);

function createHarness({ hasForm = true } = {}) {
  const parent = { value: '' };
  const note = { hidden: true };
  const name = { textContent: '' };
  const body = { focused: false, focus() { this.focused = true; } };
  const form = {
    scrolled: false,
    scrollIntoView() { this.scrolled = true; },
    querySelector(selector) {
      return {
        '[data-reply-parent]': parent,
        '[data-reply-note]': note,
        '[data-reply-name]': name,
        '[data-comment-body]': body,
      }[selector] || null;
    },
  };
  let clickHandler;
  const document = {
    querySelector: (selector) => (hasForm && selector === '[data-comment-form]' ? form : null),
    addEventListener(type, handler) { if (type === 'click') clickHandler = handler; },
  };
  vm.runInNewContext(source, { document });
  const click = (selector, dataset = {}) => {
    let prevented = false;
    const element = { dataset };
    clickHandler({
      target: { closest: (wanted) => (wanted === selector ? element : null) },
      preventDefault() { prevented = true; },
    });
    return prevented;
  };
  return { parent, note, name, body, form, click, hasHandler: () => Boolean(clickHandler) };
}

test('clicking reply targets the comment and focuses the form', () => {
  const harness = createHarness();
  const prevented = harness.click('[data-reply-link]', { replyId: '7', replyName: 'Ann' });

  assert.equal(prevented, true);
  assert.equal(harness.parent.value, '7');
  assert.equal(harness.name.textContent, 'Ann');
  assert.equal(harness.note.hidden, false);
  assert.equal(harness.form.scrolled, true);
  assert.equal(harness.body.focused, true);
});

test('cancel clears the reply target', () => {
  const harness = createHarness();
  harness.click('[data-reply-link]', { replyId: '7', replyName: 'Ann' });
  const prevented = harness.click('[data-reply-cancel]');

  assert.equal(prevented, true);
  assert.equal(harness.parent.value, '');
  assert.equal(harness.note.hidden, true);
});

test('clicks elsewhere are left alone', () => {
  const harness = createHarness();
  assert.equal(harness.click('[data-unrelated]'), false);
  assert.equal(harness.parent.value, '');
});

test('pages without a comment form do nothing', () => {
  assert.equal(createHarness({ hasForm: false }).hasHandler(), false);
});
