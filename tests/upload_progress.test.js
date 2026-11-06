const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const read = (name) => fs.readFileSync(path.join(__dirname, '..', 'app', 'static', name), 'utf8');

function element(tagName = 'div') {
  return {
    tagName: tagName.toUpperCase(), dataset: {}, attributes: {}, children: [], listeners: {},
    hidden: false, disabled: false, textContent: '', className: '', value: '',
    append(...nodes) { this.children.push(...nodes); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); },
    emit(name, event = {}) {
      const e = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...event };
      (this.listeners[name] || []).forEach((fn) => fn(e));
      return e;
    },
  };
}

function createContext(extra = {}) {
  const windowListeners = {};
  const timers = [];
  const context = {
    document: {
      readyState: 'complete', createElement: element,
      querySelectorAll: () => [], querySelector: () => null, addEventListener() {},
    },
    window: {
      location: { pathname: '/admin/images', assigned: null, assign(url) { this.assigned = url; } },
      addEventListener(name, fn) { windowListeners[name] = fn; },
      removeEventListener(name) { delete windowListeners[name]; },
    },
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    FormData: class {
      constructor() { this.entries = []; }
      append(name, value, filename) { this.entries.push([name, value, filename]); }
    },
    ...extra,
  };
  context.windowListeners = windowListeners;
  context.timers = timers;
  return context;
}

// --- upload-progress.js ----------------------------------------------------------

function loadProgress(extra) {
  const context = createContext(extra);
  vm.runInNewContext(read('upload-progress.js'), context);
  return { api: context.window.FlogUploadProgress, context };
}

test('createProgress shows a determinate bar, an indeterminate one, then a message', () => {
  const { api } = loadProgress();
  const host = element();
  host.hidden = true;
  const ui = api.createProgress(host);
  const [bar, text] = host.children;

  ui.show('正在上传 a.jpg · 40%', 0.4);
  assert.equal(host.hidden, false);
  assert.equal(bar.hidden, false);
  assert.equal(bar.value, 40);
  assert.equal(text.textContent, '正在上传 a.jpg · 40%');

  ui.show('服务器处理中', null);
  assert.equal('value' in bar.attributes, false, 'removing value makes the bar indeterminate');

  ui.message('上传失败', 'error');
  assert.equal(bar.hidden, true);
  assert.equal(host.dataset.state, 'error');
  assert.equal(text.textContent, '上传失败');
});

test('createProgress keeps the fraction between 0 and 100 percent', () => {
  const { api } = loadProgress();
  const host = element();
  const ui = api.createProgress(host);
  ui.show('x', 1.7);
  assert.equal(host.children[0].value, 100);
  ui.show('x', -2);
  assert.equal(host.children[0].value, 0);
});

test('post reports bytes sent, the moment sending ends, and the JSON reply', async () => {
  let xhr;
  class FakeXhr {
    constructor() { xhr = this; this.upload = {}; this.headers = {}; }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(name, value) { this.headers[name] = value; }
    send(body) { this.body = body; }
  }
  const { api } = loadProgress({ XMLHttpRequest: FakeXhr });
  const events = [];

  const pending = api.post('/up', 'BODY', {
    headers: { Accept: 'application/json' },
    onProgress: (fraction) => events.push(['progress', fraction]),
    onSent: () => events.push(['sent']),
  });
  assert.equal(xhr.method, 'POST');
  assert.equal(xhr.url, '/up');
  assert.equal(xhr.headers.Accept, 'application/json');
  assert.equal(xhr.body, 'BODY');

  xhr.upload.onprogress({ lengthComputable: true, loaded: 25, total: 100 });
  xhr.upload.onprogress({ lengthComputable: false, loaded: 1, total: 0 });
  xhr.upload.onload();
  xhr.status = 200;
  xhr.responseText = '{"saved":2}';
  xhr.onload();

  const response = await pending;
  assert.deepEqual(JSON.parse(JSON.stringify(events)), [['progress', 0.25], ['sent']]);
  assert.equal(response.ok, true);
  assert.deepEqual(JSON.parse(JSON.stringify(await response.json())), { saved: 2 });
});

test('post resolves a non-2xx reply as not ok and rejects on a network error', async () => {
  let xhr;
  class FakeXhr {
    constructor() { xhr = this; this.upload = {}; }
    open() {}
    setRequestHeader() {}
    send() {}
  }
  const { api } = loadProgress({ XMLHttpRequest: FakeXhr });

  const bad = api.post('/up', null);
  xhr.status = 400;
  xhr.onload();
  assert.equal((await bad).ok, false);

  const lost = api.post('/up', null);
  xhr.onerror();
  await assert.rejects(lost, /network/);
});

test('guardLeaving blocks navigation until it is released', () => {
  const { api, context } = loadProgress();
  const release = api.guardLeaving();
  const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  context.windowListeners.beforeunload(event);
  assert.equal(event.defaultPrevented, true);
  release();
  assert.equal(context.windowListeners.beforeunload, undefined);
});

test('lockForm disables the buttons after the first submit and ignores a second', () => {
  const { api, context } = loadProgress();
  const form = element('form');
  const button = element('button');
  button.textContent = '上传头像';
  form.querySelectorAll = () => [button];

  api.lockForm(form);
  const first = form.emit('submit');
  assert.equal(first.defaultPrevented, false, 'the first submit goes through');
  assert.equal(form.attributes['aria-busy'], 'true');
  assert.equal(button.disabled, false, 'disabled only after the browser has read the form');
  context.timers.forEach((fn) => fn());
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, '上传中…');

  assert.equal(form.emit('submit').defaultPrevented, true);
});

// --- image-upload.js -----------------------------------------------------------------

function loadImageUpload({ post, forms = false } = {}) {
  const context = createContext();
  context.window.FlogUploadProgress = {
    createProgress: (host) => {
      const calls = [];
      host.calls = calls;
      return {
        show: (text, fraction) => { host.hidden = false; calls.push(['show', text, fraction]); },
        message: (text, state) => { host.hidden = false; host.dataset.state = state; calls.push(['message', text, state]); },
      };
    },
    post,
    guardLeaving: () => { context.guarded = true; return () => { context.released = true; }; },
  };
  vm.runInNewContext(read('image-upload.js'), context);
  return { api: context.window.FlogImageUpload, context };
}

const file = (name) => ({ name });
// Arrays made inside the vm context are not this realm's, so copy them out.
const names = (jobs) => JSON.parse(JSON.stringify(jobs.map((job) => job.map((f) => f.name))));

test('a still and its same-named clip are sent together, anything else alone', () => {
  const { api } = loadImageUpload();
  const jobs = api.groupFiles([
    file('IMG_1.HEIC'), file('solo.png'), file('img_1.MOV'), file('lonely.mov'),
    file('a.jpg'), file('a.png'), file('a.mp4')]);

  assert.deepEqual(names(jobs), [
    ['IMG_1.HEIC', 'img_1.MOV'], ['solo.png'], ['lonely.mov'],
    ['a.jpg'], ['a.png'], ['a.mp4']]);
});

function createForm(files) {
  const form = element('form');
  form.action = '/admin/images/upload';
  const input = element('input');
  input.files = files;
  const button = element('button');
  button.textContent = '上传';
  const token = element('input');
  token.value = 'csrf-123';
  form.querySelector = (selector) => ({
    'input[type="file"]': input, 'button[type="submit"]': button,
    'input[name="csrf_token"]': token,
  })[selector] || null;
  return { form, input, button };
}

const settle = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };

test('uploading locks the form, shows progress per set, then reloads with the count', async () => {
  const sent = [];
  let release;
  const post = (url, body, hooks) => {
    sent.push({ url, body, headers: hooks.headers });
    hooks.onProgress(0.5);
    hooks.onSent();
    return new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ saved: 1, failed: [] }) }); });
  };
  const { api, context } = loadImageUpload({ post });
  const { form, input, button } = createForm([file('a.png'), file('b.png')]);
  const status = element();

  api.attach(form, status);
  const submit = form.emit('submit');
  assert.equal(submit.defaultPrevented, true, 'the browser does not also submit the form');
  await settle();

  assert.equal(button.disabled, true);
  assert.equal(button.textContent, '上传中…');
  assert.equal(input.disabled, true);
  assert.equal(form.attributes['aria-busy'], 'true');
  assert.equal(context.guarded, true);
  assert.equal(sent.length, 1, 'one set at a time');
  assert.equal(sent[0].headers.Accept, 'application/json');
  assert.deepEqual(JSON.parse(JSON.stringify(sent[0].body.entries)), [
    ['csrf_token', 'csrf-123', null], ['images', { name: 'a.png' }, 'a.png']]);
  const texts = status.calls.map((call) => call[1]);
  assert.ok(texts.includes('正在上传 1/2 a.png · 50%'));
  assert.ok(texts.some((text) => text.startsWith('服务器处理中 1/2 a.png')));

  const secondSubmit = form.emit('submit');
  assert.equal(secondSubmit.defaultPrevented, true);
  assert.equal(sent.length, 1, 'a second click starts nothing');

  release();
  await settle();
  assert.equal(sent.length, 2);
  release();
  await settle();
  assert.equal(context.released, true);
  assert.equal(context.window.location.assigned, '/admin/images?uploaded=2');
});

test('a single file shows an indeterminate bar while the server works', async () => {
  const post = (url, body, hooks) => { hooks.onSent(); return new Promise(() => {}); };
  const { api } = loadImageUpload({ post });
  const { form } = createForm([file('IMG_1.HEIC'), file('IMG_1.MOV')]);
  const status = element();
  api.attach(form, status);

  form.emit('submit');
  await settle();

  const last = status.calls.at(-1);
  assert.equal(last[2], null);
  assert.match(last[1], /^服务器处理中 IMG_1\.HEIC（视频转码可能需要几十秒/);
});

test('failures are listed, the form is released and uploaded counts are kept', async () => {
  const replies = [
    { ok: true, json: async () => ({ saved: 1, failed: [] }) },
    { ok: true, json: async () => ({ saved: 0, failed: ['bad.png：不是有效的图片'] }) },
  ];
  let call = 0;
  const post = () => Promise.resolve(replies[call++]);
  const { api, context } = loadImageUpload({ post });
  const { form, input, button } = createForm([file('ok.png'), file('bad.png')]);
  const status = element();
  api.attach(form, status);

  form.emit('submit');
  await settle();

  assert.equal(context.window.location.assigned, null, 'no reload while there is something to read');
  assert.equal(button.disabled, false);
  assert.equal(input.disabled, false);
  assert.equal(button.textContent, '上传');
  assert.equal(input.value, '');
  assert.equal(status.dataset.state, 'error');
  assert.deepEqual(JSON.parse(JSON.stringify(status.calls.at(-1))), [
    'message', '已上传 1 张，1 项失败：bad.png：不是有效的图片', 'error']);
  const link = status.children.at(-1);
  assert.equal(link.href, '/admin/images?uploaded=1');
});

test('a network error or a rejected request counts as a failure, not a hang', async () => {
  const post = (url, body) => (body.entries.some((e) => e[2] === 'a.png')
    ? Promise.reject(new Error('network'))
    : Promise.resolve({ ok: false, status: 400, json: async () => ({}) }));
  const { api } = loadImageUpload({ post });
  const { form, button } = createForm([file('a.png'), file('b.png')]);
  const status = element();
  api.attach(form, status);

  form.emit('submit');
  await settle();

  assert.equal(button.disabled, false);
  assert.match(status.calls.at(-1)[1], /^已上传 0 张，2 项失败：a\.png：上传失败.*b\.png：上传失败/);
});

test('submitting with nothing chosen does nothing', async () => {
  let posted = 0;
  const { api } = loadImageUpload({ post: () => { posted += 1; return Promise.resolve(); } });
  const { form, button } = createForm([]);
  api.attach(form, element());

  form.emit('submit');
  await settle();
  assert.equal(posted, 0);
  assert.equal(button.disabled, false);
});
