const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'markdown-editor.js'),
  'utf8',
);
const normalize = (value) => JSON.parse(JSON.stringify(value));
const CDN = '/static/vendor/vditor/4.0.1';

function createClassList() {
  const names = new Set();
  return {
    add(...items) { items.forEach((item) => names.add(item)); },
    remove(...items) { items.forEach((item) => names.delete(item)); },
    toggle(item, force) {
      if (force === undefined) {
        if (names.has(item)) { names.delete(item); return false; }
        names.add(item); return true;
      }
      if (force) names.add(item);
      else names.delete(item);
      return Boolean(force);
    },
    contains(item) { return names.has(item); },
    toArray() { return [...names]; },
  };
}

function createFakeElement(tagName) {
  const styleProps = {};
  return {
    tagName,
    attributes: {},
    children: [],
    dataset: {},
    listeners: {},
    removed: false,
    hidden: false,
    disabled: false,
    focused: false,
    classList: createClassList(),
    style: {
      setProperty(name, value) { styleProps[name] = String(value); },
      getPropertyValue(name) { return styleProps[name] || ''; },
      props: styleProps,
    },
    append(...elements) {
      elements.forEach((element) => { element.parentNode = this; });
      this.children.push(...elements);
    },
    before(element) {
      this.preceding = element;
      element.parentNode = this.parentNode;
    },
    after(element) { this.following = element; },
    remove() {
      this.removed = true;
      if (this.parentNode?.children) {
        const index = this.parentNode.children.indexOf(this);
        if (index > -1) this.parentNode.children.splice(index, 1);
      }
    },
    focus() { this.focused = true; },
    addEventListener(eventName, listener) {
      if (!this.listeners[eventName]) this.listeners[eventName] = [];
      this.listeners[eventName].push(listener);
    },
    dispatch(eventName, event = {}) {
      (this.listeners[eventName] || []).forEach((listener) => listener(event));
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] ?? null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

function createHarness({
  hasEditor = true,
  canUpload = true,
  hasVditor = true,
  deferUploads = false,
  progressHelper = false,
  libraryUrl = null,
  withPicker = true,
  emojiPicker = false,
  theme = 'light',
  initialValue = '# source',
  withSvDom = false,
  lineHeightPx = 24,
  wrapAtChars = 0,
  uploadResponses = [{ ok: true, payload: { uploaded: 1, url: '/files/abc.png' } }],
} = {}) {
  let instances = 0;
  let instance;
  let editorValue = initialValue;
  const readyCallbacks = [];
  const requests = [];
  const pendingUploads = [];
  const progressCalls = [];
  const createdElements = [];
  const submitListeners = [];
  const themeCalls = [];
  const insertCalls = [];
  const previewModeCalls = [];
  const renderPreviewCalls = [];
  const observers = [];
  const resizeObservers = [];
  let uploadResponseIndex = 0;
  const wysiwygButton = { removed: false, remove() { this.removed = true; } };
  const pickerCalls = [];
  const emojiCalls = [];
  const boldButton = createFakeElement('button');
  boldButton.dataset.type = 'bold';
  const fullscreenButton = createFakeElement('button');
  fullscreenButton.dataset.type = 'fullscreen';
  const toolbarPanel = createFakeElement('div');
  toolbarPanel.style.display = 'block';
  const toolbarElement = createFakeElement('div');
  toolbarElement.className = 'vditor-toolbar';
  toolbarElement.querySelectorAll = (selector) => {
    if (selector === '.vditor-toolbar__item > button') return [boldButton, fullscreenButton];
    if (selector === '.vditor-panel') return [toolbarPanel];
    return [];
  };
  const svElement = createFakeElement('textarea');
  svElement.className = 'vditor-sv vditor-reset';
  svElement.value = initialValue;
  svElement.selectionStart = 0;
  svElement.scrollTop = 0;
  svElement.clientWidth = withSvDom ? 480 : 0;
  svElement.clientHeight = 400;
  svElement.scrollHeight = 1200;
  const previewElement = createFakeElement('div');
  previewElement.className = 'vditor-preview';
  previewElement.scrollTop = 0;
  previewElement.clientHeight = 400;
  previewElement.scrollHeight = 1600;

  const form = {
    dataset: {
      ...(canUpload ? { imageUploadUrl: '/upload' } : {}),
      ...(libraryUrl ? { imageLibraryUrl: libraryUrl } : {}),
    },
    querySelector(selector) {
      if (selector === 'input[name="csrf_token"]' && canUpload) return { value: 'csrf-token' };
      return null;
    },
    addEventListener(eventName, listener) {
      assert.equal(eventName, 'submit');
      submitListeners.push(listener);
    },
  };
  const field = {
    dataset: { vditorCdn: CDN },
    value: initialValue,
    hidden: false,
    form,
    after(element) { this.following = element; },
  };
  const root = { dataset: { theme } };

  class FakeVditor {
    constructor(host, options) {
      instances += 1;
      instance = this;
      this.host = host;
      this.options = options;
      host.querySelector = (selector) => {
        if (selector === 'button[data-mode="wysiwyg"]') return wysiwygButton;
        if (withSvDom && selector === '.vditor-toolbar') return toolbarElement;
        if (withSvDom && selector === 'textarea.vditor-sv') return svElement;
        if (withSvDom && selector === '.vditor-preview') return previewElement;
        return null;
      };
    }

    getValue() { return editorValue; }
    insertValue(markdown) {
      insertCalls.push(markdown);
      editorValue = `${editorValue}${markdown}`;
      svElement.value = editorValue;
    }
    setTheme(...args) { themeCalls.push(args); }
    setPreviewMode(mode) { previewModeCalls.push(mode); }
    renderPreview(value) { renderPreviewCalls.push(value); }
  }

  class FakeFormData {
    constructor() { this.entries = []; }
    append(name, value) { this.entries.push([name, value]); }
  }

  const context = {
    FormData: FakeFormData,
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target, options) { this.target = target; this.options = options; }
    },
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; resizeObservers.push(this); }
      observe(target) { this.target = target; }
    },
    fetch(url, options) {
      requests.push({ url, ...options });
      const response = uploadResponses[Math.min(uploadResponseIndex, uploadResponses.length - 1)];
      uploadResponseIndex += 1;
      const resolveResponse = () => ({
        ok: response.ok,
        json: () => Promise.resolve(response.payload),
      });
      if (!deferUploads) return Promise.resolve().then(resolveResponse);
      return new Promise((resolve) => pendingUploads.push(() => resolve(resolveResponse())));
    },
    ...(progressHelper ? { XMLHttpRequest: function XMLHttpRequest() {} } : {}),
    window: {
      ...(withSvDom ? {
        getComputedStyle() {
          return {
            paddingTop: '16px',
            paddingBottom: '16px',
            paddingLeft: '14px',
            paddingRight: '18px',
            fontFamily: 'monospace',
            fontSize: '14px',
            fontWeight: '400',
            fontStyle: 'normal',
            letterSpacing: 'normal',
            lineHeight: `${lineHeightPx}px`,
            tabSize: '4',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            wordWrap: 'break-word',
            fontVariantLigatures: 'none',
          };
        },
        requestAnimationFrame(callback) { callback(); return 1; },
      } : {}),
      ...(libraryUrl && withPicker ? { FlogImagePicker: { open: (options) => pickerCalls.push(options) } } : {}),
      ...(emojiPicker ? { FlogEmojiPicker: { open: (options) => emojiCalls.push(options) } } : {}),
      ...(progressHelper ? {
        FlogUploadProgress: {
          createProgress(host) {
            return {
              show(text, fraction) { host.hidden = false; host.textContent = text; progressCalls.push(['show', text, fraction]); },
              message(text, state) { host.hidden = false; host.dataset.state = state; host.textContent = text; progressCalls.push(['message', text, state]); },
            };
          },
          post(url, body, { headers, onProgress, onSent }) {
            requests.push({ url, method: 'POST', headers, body });
            onProgress(0.5);
            onSent();
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ uploaded: 1, url: '/files/abc.png' }) });
          },
        },
      } : {}),
    },
    document: {
      documentElement: root,
      addEventListener(eventName, listener) {
        assert.equal(eventName, 'DOMContentLoaded');
        readyCallbacks.push(listener);
      },
      querySelector() { return null; },
      querySelectorAll(selector) {
                assert.equal(selector, 'textarea[data-markdown-editor]');
        return hasEditor ? [field] : [];
      },
      createElement(tagName) {
        const element = createFakeElement(tagName);
        if (withSvDom) {
          element.getBoundingClientRect = () => {
            if (element.className === 'markdown-editor__mirror-line' && element.parentNode) {
              let top = 0;
              for (const child of element.parentNode.children) {
                const text = child.textContent === '\u200b' ? '' : (child.textContent || '');
                const rows = wrapAtChars > 0 ? Math.max(1, Math.ceil(text.length / wrapAtChars)) : 1;
                const height = rows * lineHeightPx;
                if (child === element) return { top, height };
                top += height;
              }
            }
            return { top: 0, height: lineHeightPx };
          };
        }
        createdElements.push(element);
        return element;
      },
    },
  };
  if (hasVditor) context.Vditor = FakeVditor;

  return {
    execute() {
      vm.runInNewContext(source, context);
      readyCallbacks.shift()();
    },
    ready() { instance.options.after(); },
    field,
    form,
    root,
    svElement,
    previewElement,
    toolbarElement,
    boldButton,
    fullscreenButton,
    toolbarPanel,
    pickerCalls,
    emojiCalls,
    requests,
    progressCalls,
    insertCalls,
    themeCalls,
    previewModeCalls,
    renderPreviewCalls,
    wysiwygButton,
    options() { return instance?.options; },
    instance() { return instance; },
    instanceCount() { return instances; },
    observer() { return observers[0]; },
    resizeObserver() { return resizeObservers[0]; },
    typeInEditor(value) {
      editorValue = value;
      svElement.value = value;
      instance.options.input(value);
    },
    setEditorValue(value) {
      editorValue = value;
      svElement.value = value;
    },
    submit() { submitListeners.forEach((listener) => listener()); },
    status() {
      return createdElements.find((element) => element.attributes.role === 'status');
    },
    host() { return createdElements.find((element) => element.className === 'markdown-editor-host'); },
    views() { return createdElements.find((element) => element.className === 'markdown-editor__views'); },
    gutter() { return createdElements.find((element) => element.className === 'markdown-editor__gutter'); },
    gutterLines() { return createdElements.find((element) => element.className === 'markdown-editor__gutter-lines'); },
    resolveNextUpload() {
      const resolve = pendingUploads.shift();
      assert.ok(resolve, 'expected a pending upload');
      resolve();
    },
    async settle() {
      for (let i = 0; i < 12; i += 1) await Promise.resolve();
    },
  };
}

test('does nothing when Vditor is not loaded', () => {
  const harness = createHarness({ hasVditor: false });

  harness.execute();

  assert.equal(harness.instanceCount(), 0);
  assert.equal(harness.field.hidden, false);
});

test('creates one Vditor per textarea, hides the textarea and stays idempotent', () => {
  const harness = createHarness();

  harness.execute();
  assert.equal(harness.instanceCount(), 1);
  assert.equal(harness.field.hidden, true);
  assert.equal(harness.field.following, harness.host());
  assert.equal(harness.field.value, '# source');

  harness.execute();
  assert.equal(harness.instanceCount(), 1);
});

test('does not touch pages without a Markdown textarea', () => {
  const harness = createHarness({ hasEditor: false });

  harness.execute();

  assert.equal(harness.instanceCount(), 0);
});

test('configures split view, local assets and the server-compatible feature set', () => {
  const harness = createHarness();

  harness.execute();
  const options = normalize(harness.options());

  assert.equal(options.mode, 'sv');
  assert.equal(options.lang, 'zh_CN');
  assert.equal(options.cdn, CDN);
  assert.equal(options.icon, 'ant');
  assert.equal(options.value, '# source');
  assert.equal(options.minHeight, 320);
  assert.deepEqual(options.fullscreen, { index: 1050 });
  assert.deepEqual(options.cache, { enable: false });
  assert.deepEqual(options.counter, { enable: true, type: 'markdown' });
  assert.deepEqual(options.toolbar, [
    'headings', 'bold', 'italic', '|', 'quote', 'list', 'ordered-list', '|',
    'code', 'inline-code', 'link', 'table', 'line', 'upload', '|',
    'undo', 'redo', '|', 'fullscreen',
  ]);
  assert.equal(options.preview.mode, 'both');
  assert.equal(options.preview.delay, 150);
  assert.equal(options.preview.hljs.enable, false);
  assert.deepEqual(options.preview.actions, []);
  assert.deepEqual(options.preview.markdown, {
    inlineMath: false, mathBlockPreview: false, codeBlockPreview: false,
    callout: false, mark: false, sup: false, sub: false, gfmAutoLink: false,
    footnotes: true, sanitize: true,
  });
  assert.equal(options.preview.theme.path, `${CDN}/dist/css/content-theme`);
  for (const removed of ['strike', 'check', 'emoji', 'outline', 'export', 'preview', 'edit-mode']) {
    assert.equal(options.toolbar.includes(removed), false, removed);
  }
});

test('without an upload URL and CSRF token there is no upload button or handler', () => {
  const harness = createHarness({ canUpload: false });

  harness.execute();
  const options = harness.options();

  assert.equal(options.toolbar.includes('upload'), false);
  assert.equal(options.upload, undefined);
});

test('configures the image upload for gif, jpeg and png', () => {
  const harness = createHarness();

  harness.execute();
  const upload = harness.options().upload;

  assert.equal(upload.accept, 'image/gif,image/jpeg,image/png');
  assert.equal(upload.multiple, true);
  assert.equal(typeof upload.handler, 'function');
});

test('typing copies the Markdown into the textarea and notifies listeners', () => {
  const harness = createHarness();
  harness.execute();
  const seen = [];
  harness.field.markdownEditor.onChange((value) => seen.push(value));

  harness.typeInEditor('# changed');

  assert.equal(harness.field.value, '# changed');
  assert.deepEqual(seen, ['# changed']);
});

test('submitting copies the current Markdown into the textarea once more', () => {
  const harness = createHarness();
  harness.execute();
  harness.ready();
  harness.setEditorValue('# written without an input event');

  harness.submit();

  assert.equal(harness.field.value, '# written without an input event');
});

test('the adapter reports the original text until Vditor is ready and unchanged', () => {
  const harness = createHarness();
  harness.execute();
  const editor = harness.field.markdownEditor;

  assert.equal(editor.value(), '# source');

  // Vditor normalises the document (trailing newline); that is not an edit.
  harness.setEditorValue('# source\n');
  harness.ready();
  assert.equal(editor.value(), '# source');

  harness.typeInEditor('# source\nmore');
  assert.equal(editor.value(), '# source\nmore');
});

test('removes the pure WYSIWYG entry from the mode menu once loaded', () => {
  const harness = createHarness();
  harness.execute();
  assert.equal(harness.wysiwygButton.removed, false);

  harness.ready();

  assert.equal(harness.wysiwygButton.removed, true);
});

test('starts dark when the page is dark and follows later theme changes', () => {
  const harness = createHarness({ theme: 'dark' });
  harness.execute();
  assert.equal(harness.options().theme, 'dark');
  assert.equal(harness.options().preview.theme.current, 'dark');

  const observer = harness.observer();
  assert.equal(observer.target, harness.root);
  assert.deepEqual(normalize(observer.options), {
    attributes: true, attributeFilter: ['data-theme'],
  });

  observer.callback();
  assert.equal(harness.themeCalls.length, 0, 'ignored until the editor is ready');

  harness.ready();
  assert.deepEqual(normalize(harness.themeCalls.pop()), ['dark', 'dark']);

  harness.root.dataset.theme = 'light';
  observer.callback();
  assert.deepEqual(normalize(harness.themeCalls.pop()), ['classic', 'light']);
});

test('starts in the light theme by default', () => {
  const harness = createHarness({ theme: 'light' });
  harness.execute();

  assert.equal(harness.options().theme, 'classic');
  assert.equal(harness.options().preview.theme.current, 'light');
});

test('uploads a selected image and inserts it once when the upload finishes', async () => {
  const harness = createHarness({ deferUploads: true });
  const image = { name: 'cat.png', type: 'image/png' };
  harness.execute();
  harness.ready();

  const result = harness.options().upload.handler([image]);
  assert.equal(harness.status().textContent, '正在上传 1 张图片…');
  assert.equal(harness.status().attributes['aria-live'], 'polite');
  assert.equal(harness.status().dataset.state, 'uploading');
  harness.resolveNextUpload();
  assert.equal(await result, null);
  await harness.settle();

  assert.deepEqual(normalize(harness.requests.map((request) => ({
    url: request.url,
    method: request.method,
    headers: request.headers,
    entries: request.body.entries,
  }))), [{
    url: '/upload',
    method: 'POST',
    headers: { 'X-CSRFToken': 'csrf-token' },
    entries: [['post', image]],
  }]);
  assert.deepEqual(harness.insertCalls, ['![图片](/files/abc.png)']);
  assert.equal(harness.status().textContent, '图片已插入');
  assert.equal(harness.status().dataset.state, 'success');
  assert.equal(harness.field.value, '# source![图片](/files/abc.png)');
});

test('a second drop while photos are still uploading is ignored', async () => {
  const harness = createHarness({ deferUploads: true });
  harness.execute();
  harness.ready();

  const first = harness.options().upload.handler([{ name: 'a.png', type: 'image/png' }]);
  const second = await harness.options().upload.handler([{ name: 'b.png', type: 'image/png' }]);
  assert.equal(second, null);
  assert.equal(harness.requests.length, 1, 'no extra request is started');

  harness.resolveNextUpload();
  await first;
  await harness.settle();
  assert.equal(harness.status().textContent, '图片已插入');

  const again = harness.options().upload.handler([{ name: 'c.png', type: 'image/png' }]);
  harness.resolveNextUpload();
  await again;
  assert.equal(harness.requests.length, 2, 'uploads work again once the batch is done');
});

test('a failed batch releases the lock so the visitor can retry', async () => {
  const harness = createHarness({ uploadResponses: [{ ok: false }, { ok: true, payload: { uploaded: 1, url: '/files/abc.png' } }] });
  harness.execute();
  harness.ready();

  await harness.options().upload.handler([{ name: 'a.png', type: 'image/png' }]);
  assert.equal(harness.status().dataset.state, 'error');
  await harness.options().upload.handler([{ name: 'a.png', type: 'image/png' }]);
  assert.equal(harness.status().dataset.state, 'success');
});

test('with the shared helper the upload shows byte progress, then the server phase', async () => {
  const harness = createHarness({ progressHelper: true });
  harness.execute();
  harness.ready();

  await harness.options().upload.handler([
    { name: 'a.png', type: 'image/png' }, { name: 'b.png', type: 'image/png' }]);
  await harness.settle();

  assert.deepEqual(normalize(harness.progressCalls.slice(0, 4)), [
    ['message', '正在上传 2 张图片…', 'uploading'],
    ['show', '正在上传 2 张图片… 第 1/2 张', 0],
    ['show', '正在上传 2 张图片… 50% 第 1/2 张', 0.5],
    ['show', '服务器处理中… 第 1/2 张', null],
  ]);
  assert.deepEqual(normalize(harness.requests.map((request) => request.headers)), [
    { 'X-CSRFToken': 'csrf-token' }, { 'X-CSRFToken': 'csrf-token' }]);
  assert.deepEqual(normalize(harness.progressCalls.at(-1)), ['message', '图片已插入', 'success']);
  assert.equal(harness.status().textContent, '图片已插入');
});

test('uploads only images, in order, and inserts the batch once', async () => {
  const harness = createHarness();
  const first = { name: 'first.png', type: 'image/png' };
  const ignored = { name: 'notes.txt', type: 'text/plain' };
  const second = { name: 'second.gif', type: 'image/gif' };
  harness.execute();
  harness.ready();

  await harness.options().upload.handler([first, ignored, second]);

  assert.deepEqual(normalize(harness.requests.map((request) => request.body.entries)), [
    [['post', first]], [['post', second]],
  ]);
  assert.deepEqual(harness.insertCalls, [
    '![图片](/files/abc.png)\n\n![图片](/files/abc.png)',
  ]);
});

test('a batch without images sends nothing and shows nothing', async () => {
  const harness = createHarness();
  harness.execute();
  harness.ready();

  const result = await harness.options().upload.handler([{ name: 'a.txt', type: 'text/plain' }]);

  assert.equal(result, null);
  assert.equal(harness.requests.length, 0);
  assert.equal(harness.status().hidden, true);
});

test('a rejected upload reports a safe error and leaves the editor unchanged', async () => {
  const harness = createHarness({ uploadResponses: [{ ok: false }] });
  harness.execute();
  harness.ready();

  const result = await harness.options().upload.handler([{ name: 'bad.png', type: 'image/png' }]);

  assert.equal(result, null);
  assert.equal(harness.insertCalls.length, 0);
  assert.equal(harness.field.value, '# source');
  assert.match(harness.status().textContent, /^上传失败：/);
  assert.equal(harness.status().dataset.state, 'error');
});

test('a later failure in a batch leaves the entire document unchanged', async () => {
  const harness = createHarness({
    uploadResponses: [
      { ok: true, payload: { uploaded: 1, url: '/files/first.png' } },
      { ok: false },
    ],
  });
  harness.execute();
  harness.ready();

  await harness.options().upload.handler([
    { name: 'first.png', type: 'image/png' },
    { name: 'second.png', type: 'image/png' },
  ]);

  assert.equal(harness.insertCalls.length, 0);
  assert.equal(harness.field.value, '# source');
});

test('an invalid upload response is treated as a failure', async () => {
  const harness = createHarness({
    uploadResponses: [{ ok: true, payload: { uploaded: 0 } }],
  });
  harness.execute();
  harness.ready();

  await harness.options().upload.handler([{ name: 'x.png', type: 'image/png' }]);

  assert.equal(harness.insertCalls.length, 0);
  assert.match(harness.status().textContent, /^上传失败：/);
});

function createDraftHarness({
  postId = 7, failRequests = false, deferRequests = false, sequence = 0, generation = 0,
  publishedWithoutDraft = false, unpublishedDraft = false,
} = {}) {
  const readyCallbacks = [];
  const documentListeners = {};
  const windowListeners = {};
  const timers = new Map();
  const requests = [];
  const pendingResponses = [];
  const actionForms = [{ listeners: {}, addEventListener(eventName, listener) {
    this.listeners[eventName] = listener;
  } }];
  let nextTimerId = 1;
  let reloads = 0;
  let serverGeneration = generation;
  let editorValue = '# initial source';
  let vditorInstance;
  const field = {
    dataset: { markdownEditor: '', vditorCdn: '/static/vendor/vditor/4.0.1' },
    value: editorValue,
    after() {},
  };
  const title = createInput('Initial title');
  const category = createInput('3');
  const status = { textContent: unpublishedDraft ? '草稿已保存' : '' };
  const publicationStatus = { textContent: '' };
  const unpublishButton = { disabled: false };
  const publishUpdate = { hidden: true };
  const publicationControls = {
    children: [],
    dataset: {
      publicationState: postId === null ? 'new' : publishedWithoutDraft ? 'published' : 'draft',
    },
    append(...elements) {
      this.children.push(...elements);
    },
    querySelector(selector) {
      if (selector === '[data-draft-save-status]') return status;
      if (selector === '[data-publication-status]') return publicationStatus;
      if (selector === '[data-unpublish]') return unpublishButton;
      if (selector === '[data-publish-update]') return publishUpdate;
      return null;
    },
  };
  const editorRoot = {
    dataset: {
      articleDraftEditor: '',
      postId: postId === null ? '' : String(postId),
      draftUrl: postId === null ? '/admin/posts/draft' : `/admin/posts/${postId}/draft`,
      leaveUrl: postId === null
        ? '/admin/posts/draft/leave' : `/admin/posts/${postId}/leave`,
      csrfToken: 'csrf-token',
      draftKey: 'draft-key',
      editorSequence: String(sequence),
      draftGeneration: String(generation),
    },
    action: postId === null ? '/admin/posts/new' : `/admin/posts/${postId}/edit`,
    querySelector(selector) {
      if (selector === '[name="title"]') return title;
      if (selector === '[name="category"]') return category;
      if (selector === 'textarea[data-markdown-editor]') return field;
      return null;
    },
  };

  class FakeVditor {
    constructor(host, options) {
      vditorInstance = this;
      this.options = options;
    }

    getValue() { return editorValue; }
    setTheme() {}
  }

  const context = {
    Vditor: FakeVditor,
    MutationObserver: class { observe() {} },
    fetch(url, options) {
      requests.push({ ...options, url, body: JSON.parse(options.body) });
      const response = (savedPostId = postId, metadata = {}) => ({
        ok: !failRequests && Number(options.headers['X-Draft-Generation']) === serverGeneration,
        json: () => Promise.resolve({ post_id: savedPostId, applied: true,
          generation, sequence: Number(options.headers['X-Draft-Sequence']), ...metadata }),
      });
      if (!deferRequests) return Promise.resolve(response());
      return new Promise((resolve) => pendingResponses.push(
        (savedPostId, metadata) => resolve(response(savedPostId, metadata))));
    },
    clearTimeout(timerId) {
      timers.delete(timerId);
    },
    setTimeout(callback) {
      const timerId = nextTimerId;
      nextTimerId += 1;
      timers.set(timerId, callback);
      return timerId;
    },
    window: {
      location: { reload() { reloads += 1; } },
      addEventListener(eventName, listener) {
        windowListeners[eventName] = listener;
      },
    },
    document: {
      documentElement: { dataset: { theme: 'light' } },
      addEventListener(eventName, listener) {
        if (eventName === 'DOMContentLoaded') readyCallbacks.push(listener);
        else documentListeners[eventName] = listener;
      },
      querySelector(selector) {
        if (selector === '[data-article-draft-editor]') return editorRoot;
        if (selector === '[data-publication-controls]') return publicationControls;
        return null;
      },
      querySelectorAll(selector) {
        if (selector === '[data-draft-leave-action]') return actionForms;
                assert.equal(selector, 'textarea[data-markdown-editor]');
        return [field];
      },
      createElement(tagName) {
        return {
          tagName,
          children: [],
          dataset: {},
          listeners: {},
          attributes: {},
          after() {},
          querySelector() { return null; },
          setAttribute(name, value) { this.attributes[name] = String(value); },
          append(...elements) {
            this.children.push(...elements);
          },
          addEventListener(eventName, listener) {
            this.listeners[eventName] = listener;
          },
          requestSubmit() {
            this.submitCount = (this.submitCount || 0) + 1;
            this.listeners.submit?.();
          },
        };
      },
    },
  };

  return {
    execute() {
      vm.runInNewContext(source, context);
      readyCallbacks.shift()();
      vditorInstance.options.after();
    },
    async advance(milliseconds) {
      assert.equal(milliseconds, 1000);
      const callbacks = [...timers.values()];
      timers.clear();
      const pending = callbacks.map((callback) => callback());
      if (!deferRequests) await Promise.all(pending);
    },
    changeBody(value) {
      editorValue = value;
      vditorInstance.options.input(value);
    },
    changeTitle(value) {
      title.value = value;
      title.listeners.input();
    },
    changeCategory(value) {
      category.value = value;
      category.listeners.change();
    },
    async leavePage() {
      windowListeners.pagehide();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
    async resolveNext(savedPostId) {
      const resolve = pendingResponses.shift();
      assert.ok(resolve, 'expected a pending draft request');
      resolve(savedPostId);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
    async resolveAt(index, savedPostId, metadata) {
      const [resolve] = pendingResponses.splice(index, 1);
      resolve(savedPostId, metadata);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
    restorePageFromCache() {
      windowListeners.pageshow({ persisted: true });
    },
    submitAction() {
      actionForms[0].listeners.submit();
    },
    formAction() {
      return editorRoot.action;
    },
    reloadCount() {
      return reloads;
    },
    advanceServerGeneration() {
      serverGeneration += 1;
    },
    requests,
    status,
    publicationStatus,
    unpublishButton,
    publishUpdate,
    publicationForm() {
      return publicationControls.children.find((child) => child.tagName === 'form');
    },
    state() {
      return context.window.articleDraftEditor;
    },
  };
}

function createInput(value) {
  return {
    listeners: {},
    value,
    addEventListener(eventName, listener) {
      this.listeners[eventName] = listener;
    },
  };
}

test('debounces title, category, and Markdown changes into one current draft request', async () => {
  const harness = createDraftHarness();
  harness.execute();
  harness.changeTitle('Revised title');
  harness.changeCategory('9');
  harness.changeBody('final source');

  await harness.advance(1000);

  assert.equal(harness.requests.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(harness.requests[0])), {
    url: '/admin/posts/7/draft',
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': 'csrf-token',
      'X-Draft-Generation': '0',
      'X-Draft-Key': 'draft-key',
      'X-Draft-Sequence': '1',
    },
    body: { title: 'Revised title', category_id: 9, body: 'final source' },
  });
  assert.equal(harness.status.textContent, '草稿已保存');
  assert.equal(harness.state().dirty, false);
});

test('writes autosave state to the header publication status', async () => {
  const harness = createDraftHarness({ deferRequests: true });
  harness.execute();
  harness.changeBody('changed');
  assert.equal(harness.status.textContent, '保存中');

  await harness.advance(1000);
  await harness.resolveNext(7);

  assert.equal(harness.status.textContent, '草稿已保存');
});

test('marks a published article as pending update after its first autosave', async () => {
  const harness = createDraftHarness({
    deferRequests: true,
    publishedWithoutDraft: true,
  });
  harness.execute();
  harness.changeBody('changed');
  await harness.advance(1000);
  await harness.resolveNext(7);

  assert.equal(harness.status.textContent, '草稿已保存');
  assert.equal(harness.publicationStatus.textContent, '有未发布修改');
  assert.equal(harness.unpublishButton.disabled, true);
  assert.equal(harness.publishUpdate.hidden, false);
});

test('keeps a failed draft dirty and reports that it was not saved', async () => {
  const harness = createDraftHarness({ failRequests: true });
  harness.execute();
  harness.changeBody('unsaved source');

  await harness.advance(1000);

  assert.equal(harness.status.textContent, '保存失败');
  assert.equal(harness.state().dirty, true);
});

test('failed autosave replaces an unpublished draft save state', async () => {
  const harness = createDraftHarness({
    failRequests: true,
    unpublishedDraft: true,
  });
  harness.execute();
  assert.equal(harness.status.textContent, '草稿已保存');
  assert.equal(harness.publicationStatus.textContent, '');

  harness.changeBody('unsaved source');
  await harness.advance(1000);

  assert.equal(harness.status.textContent, '保存失败');
  assert.equal(harness.publicationStatus.textContent, '');
});

test('page leave saves changed content as one keepalive revision request', async () => {
  const harness = createDraftHarness({ postId: 7 });
  harness.execute();
  harness.changeBody('snapshot');

  await harness.leavePage();

  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].url, '/admin/posts/7/leave');
  assert.equal(harness.requests[0].method, 'POST');
  assert.equal(harness.requests[0].keepalive, true);
  assert.deepEqual(harness.requests[0].body, {
    title: 'Initial title', category_id: 3, body: 'snapshot',
  });
});

test('page leave does not snapshot an unchanged draft', async () => {
  const harness = createDraftHarness();
  harness.execute();

  await harness.leavePage();

  assert.equal(harness.requests.length, 0);
});

test('serializes a new draft creation and turns the form into its edit page', async () => {
  const harness = createDraftHarness({ postId: null, deferRequests: true });
  harness.execute();
  harness.changeBody('first version');
  await harness.advance(1000);
  harness.changeBody('second version');
  await harness.advance(1000);

  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].url, '/admin/posts/draft');

  await harness.resolveNext(8);

  assert.equal(harness.state().postId, 8);
  assert.equal(harness.formAction(), '/admin/posts/8/edit');
  assert.equal(harness.state().leaveUrl, '/admin/posts/8/leave');
  assert.equal(harness.requests.length, 2);
  assert.equal(harness.requests[1].url, '/admin/posts/8/draft');
  assert.equal(harness.requests[1].body.body, 'second version');
});

test('creates a CSRF-protected publish button after a new draft autosaves', async () => {
  const harness = createDraftHarness({ postId: null, deferRequests: true });
  harness.execute();
  harness.changeBody('first version');
  await harness.advance(1000);
  await harness.resolveNext(8);

  const form = harness.publicationForm();
  assert.equal(form.method, 'post');
  assert.equal(form.action, '/admin/posts/8/publish');
  assert.equal(form.dataset.draftLeaveAction, '');
  const csrf = form.children.find((child) => child.name === 'csrf_token');
  assert.equal(csrf.value, 'csrf-token');
  const button = form.children.find((child) => child.tagName === 'button');
  assert.equal(button.type, 'submit');
  assert.equal(button.dataset.publish, '');
  assert.equal(button.textContent, '发布');
  assert.equal(button.className, 'button button--cta');
  assert.equal(form.children.some((child) => child.tagName === 'label'), false);

  form.listeners.submit();
  assert.equal(harness.state().intentionalLeave, true);
});

test('a BFCache-restored editor can make a later leave snapshot', async () => {
  const harness = createDraftHarness();
  harness.execute();
  harness.changeBody('first snapshot');
  await harness.leavePage();
  harness.restorePageFromCache();
  harness.changeBody('second snapshot');
  await harness.leavePage();

  assert.equal(harness.requests.length, 2);
  assert.equal(harness.requests[1].url, '/admin/posts/7/leave');
  assert.equal(harness.requests[1].body.body, 'second snapshot');
});

test('an acknowledged leave is not repeated after an unchanged BFCache restore', async () => {
  const harness = createDraftHarness();
  harness.execute();
  harness.changeBody('saved on leave');
  await harness.leavePage();
  harness.restorePageFromCache();
  await harness.leavePage();

  assert.equal(harness.requests.length, 1);
});

test('page leave creates and snapshots a new draft with one keepalive request', async () => {
  const harness = createDraftHarness({ postId: null });
  harness.execute();
  harness.changeBody('first unsaved source');

  await harness.leavePage();

  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].url, '/admin/posts/draft/leave');
  assert.equal(harness.requests[0].keepalive, true);
  assert.equal(harness.requests[0].body.body, 'first unsaved source');
});

test('BFCache after an intentional action reloads before accepting old-generation edits', async () => {
  const harness = createDraftHarness({ generation: 4 });
  harness.execute();
  harness.changeBody('stale source');
  harness.submitAction();
  harness.advanceServerGeneration();
  await harness.leavePage();
  assert.equal(harness.requests.length, 0);

  harness.restorePageFromCache();
  assert.equal(harness.reloadCount(), 1);
  assert.equal(harness.state().intentionalLeave, true);
  harness.changeBody('cached edits still carry generation 4 after the action advanced it');
  await harness.advance(1000);
  await harness.leavePage();
  assert.equal(harness.requests.length, 0);

  const reloaded = createDraftHarness({ generation: 5 });
  reloaded.execute();
  reloaded.changeBody('new-generation edits');
  await reloaded.advance(1000);
  assert.equal(reloaded.requests[0].headers['X-Draft-Generation'], '5');
  assert.equal(reloaded.state().dirty, false);
});

test('continues the server sequence rendered for a reloaded editor', async () => {
  const harness = createDraftHarness({ sequence: 4, generation: 2 });
  harness.execute();
  harness.changeBody('after reload');
  await harness.advance(1000);

  assert.equal(harness.requests[0].headers['X-Draft-Sequence'], '5');
  assert.equal(harness.requests[0].headers['X-Draft-Generation'], '2');
  assert.equal(harness.state().dirty, false);
});

test('an older autosave reply cannot replace the acknowledged leave payload', async () => {
  const harness = createDraftHarness({ deferRequests: true });
  harness.execute();
  harness.changeBody('older');
  await harness.advance(1000);
  harness.changeBody('newer');
  await harness.leavePage();
  await harness.resolveAt(1, 7);
  await harness.resolveNext(7);
  assert.equal(harness.state().lastSavedPayload.body, 'newer');
  assert.equal(harness.state().dirty, false);
  assert.equal(harness.status.textContent, '草稿已保存');
});

test('a reply started before an intentional action cannot mark its buffer saved', async () => {
  const harness = createDraftHarness({ deferRequests: true });
  harness.execute();
  harness.changeBody('before action');
  await harness.advance(1000);
  harness.submitAction();
  harness.restorePageFromCache();
  await harness.resolveNext(7);
  assert.equal(harness.state().lastSavedPayload.body, '# initial source');
  assert.equal(harness.state().dirty, true);
});

for (const metadata of [{ applied: false }, { generation: 1 }, { sequence: 2 }]) {
  test(`an unacknowledged payload stays dirty: ${JSON.stringify(metadata)}`, async () => {
    const harness = createDraftHarness({ deferRequests: true });
    harness.execute();
    harness.changeBody('not acknowledged');
    await harness.advance(1000);
    await harness.resolveAt(0, 7, metadata);
    assert.equal(harness.state().lastSavedPayload.body, '# initial source');
    assert.equal(harness.state().dirty, true);
    assert.equal(harness.status.textContent, '保存失败');
  });
}


test('without a library URL there is no image library button', () => {
  const harness = createHarness();
  harness.execute();
  assert.equal(harness.options().toolbar.some((item) => item?.name === 'image-library'), false);
});

test('a library URL adds the image library button right after upload', () => {
  const harness = createHarness({ libraryUrl: '/admin/images/picker' });
  harness.execute();
  const toolbar = harness.options().toolbar;
  const index = toolbar.indexOf('upload');
  assert.equal(toolbar[index + 1].name, 'image-library');
  assert.equal(toolbar[index + 1].tip, '图片库');
  assert.equal(typeof toolbar[index + 1].click, 'function');
});

test('the library button works even when uploading is not configured', () => {
  const harness = createHarness({ canUpload: false, libraryUrl: '/admin/images/picker' });
  harness.execute();
  const names = harness.options().toolbar.map((item) => item?.name ?? item);
  assert.equal(names.includes('upload'), false);
  assert.equal(names.includes('image-library'), true);
});

test('choosing a library image inserts it once and syncs the textarea', () => {
  const harness = createHarness({ libraryUrl: '/admin/images/picker' });
  harness.execute();
  harness.ready();
  const button = harness.options().toolbar.find((item) => item?.name === 'image-library');

  button.click();
  assert.equal(harness.pickerCalls.length, 1);
  assert.equal(harness.pickerCalls[0].url, '/admin/images/picker');

  harness.pickerCalls[0].onSelect('![Sunset](/files/a.png)');
  assert.deepEqual(harness.insertCalls, ['![Sunset](/files/a.png)']);
  assert.equal(harness.field.value, '# source![Sunset](/files/a.png)');
});

test('the library button is left out when the picker script did not load', () => {
  const harness = createHarness({ libraryUrl: '/admin/images/picker', withPicker: false });
  harness.execute();
  assert.equal(harness.options().toolbar.some((item) => item?.name === 'image-library'), false);
});

test('no emoji button without the picker script', () => {
  const harness = createHarness();
  harness.execute();
  assert.equal(harness.options().toolbar.some((item) => item?.name === 'emoji-picker'), false);
});

test('the emoji button sits before upload and opens the picker at the button', () => {
  const harness = createHarness({ emojiPicker: true });
  harness.execute();
  const toolbar = harness.options().toolbar;
  const index = toolbar.findIndex((item) => item?.name === 'emoji-picker');
  assert.ok(index > -1);
  assert.equal(toolbar[index].tip, '表情');
  assert.equal(toolbar[index + 1], 'upload');

  const anchor = { tag: 'button' };
  toolbar[index].click({ currentTarget: anchor });
  assert.equal(harness.emojiCalls.length, 1);
  assert.equal(harness.emojiCalls[0].anchor, anchor);
});

test('picking an emoji inserts it into the editor and syncs the textarea', () => {
  const harness = createHarness({ emojiPicker: true });
  harness.execute();
  harness.ready();
  const button = harness.options().toolbar.find((item) => item?.name === 'emoji-picker');
  button.click({ currentTarget: {} });
  harness.emojiCalls[0].onPick('😀');

  assert.deepEqual(harness.insertCalls, ['😀']);
  assert.equal(harness.field.value, '# source😀');
});

test('mounts three keyboard-accessible view buttons and switches between split, source, and preview', () => {
  const harness = createHarness({ withSvDom: true });
  harness.execute();
  harness.ready();

  const views = harness.views();
  assert.ok(views);
  assert.equal(views.attributes.role, 'group');
  assert.equal(views.attributes['aria-label'], '编辑器视图');
  assert.deepEqual(
    views.children.map((btn) => [btn.dataset.viewMode, btn.textContent, btn.attributes['aria-pressed']]),
    [
      ['split', '分屏预览', 'true'],
      ['source', '源码', 'false'],
      ['preview', '仅预览', 'false'],
    ],
  );
  assert.equal(harness.host().dataset.editorView, 'split');
  assert.equal(harness.svElement.style.display, 'block');
  assert.equal(harness.previewElement.style.display, 'block');
  assert.equal(harness.gutter().hidden, false);

  // Switch to source code view
  views.children[1].dispatch('click');
  assert.equal(harness.field.markdownEditor.viewMode(), 'source');
  assert.equal(harness.host().dataset.editorView, 'source');
  assert.equal(views.children[1].attributes['aria-pressed'], 'true');
  assert.equal(harness.svElement.style.display, 'block');
  assert.equal(harness.previewElement.style.display, 'none');
  assert.equal(harness.gutter().hidden, false);
  assert.equal(harness.boldButton.disabled, false);

  // Switch to preview-only view: disables edit toolbar, keeps fullscreen, hides source & gutter, preserves scrollTop
  harness.svElement.scrollTop = 240;
  views.children[2].dispatch('click');
  assert.equal(harness.field.markdownEditor.viewMode(), 'preview');
  assert.equal(harness.host().dataset.editorView, 'preview');
  assert.equal(views.children[2].attributes['aria-pressed'], 'true');
  assert.equal(harness.svElement.style.display, 'none');
  assert.equal(harness.gutter().hidden, true);
  assert.equal(harness.previewElement.style.display, 'block');
  assert.equal(harness.boldButton.disabled, true);
  assert.equal(harness.boldButton.attributes['aria-disabled'], 'true');
  assert.equal(harness.fullscreenButton.disabled, false);
  assert.equal(harness.toolbarPanel.style.display, 'none');
  assert.ok(harness.renderPreviewCalls.length >= 2);

  // Return to split view: re-enables toolbar, restores scrollTop and live preview
  harness.svElement.scrollTop = 0;
  views.children[0].dispatch('click');
  assert.equal(harness.field.markdownEditor.viewMode(), 'split');
  assert.equal(harness.boldButton.disabled, false);
  assert.equal(harness.svElement.style.display, 'block');
  assert.equal(harness.previewElement.style.display, 'block');
  assert.equal(harness.gutter().hidden, false);
  assert.equal(harness.svElement.scrollTop, 240);

  // Unknown view mode is ignored safely
  harness.field.markdownEditor.setViewMode('unknown');
  assert.equal(harness.field.markdownEditor.viewMode(), 'split');

  // Arrow/Home/End keyboard navigation moves focus between the 3 view buttons
  views.dispatch('keydown', { key: 'ArrowRight', target: views.children[0], preventDefault() {} });
  assert.equal(views.children[1].focused, true);
  views.dispatch('keydown', { key: 'End', target: views.children[1], preventDefault() {} });
  assert.equal(views.children[2].focused, true);
  views.dispatch('keydown', { key: 'ArrowLeft', target: views.children[2], preventDefault() {} });
  assert.equal(views.children[1].focused, true);
  views.dispatch('keydown', { key: 'Home', target: views.children[1], preventDefault() {} });
  assert.equal(views.children[0].focused, true);
});

test('computes accurate line numbers including empty docs, CRLF, long docs, wrapped rows, and scroll sync', () => {
  const longWrappedLine = 'a'.repeat(55);
  const initial = `# title\r\n\r\n${longWrappedLine}\r\nfinal line\r\n`;
  const harness = createHarness({
    withSvDom: true,
    initialValue: initial,
    lineHeightPx: 24,
    wrapAtChars: 20,
  });
  harness.execute();
  harness.ready();

  const gutterLines = harness.gutterLines();
  assert.equal(harness.field.markdownEditor.lineCount(), 5);
  assert.deepEqual(
    gutterLines.children.map((el) => el.textContent),
    ['1', '2', '3', '4', '5'],
  );
  // Line 3 has 55 chars wrapping at 20 chars/row -> 3 visual rows = 72px; line 1 & 2 are 24px
  assert.equal(gutterLines.children[0].style.height, '24px');
  assert.equal(gutterLines.children[1].style.height, '24px');
  assert.equal(gutterLines.children[2].style.height, '72px');
  assert.equal(gutterLines.children[3].style.height, '24px');
  assert.equal(gutterLines.children[4].style.height, '24px');

  // Active line follows caret position
  harness.svElement.selectionStart = initial.indexOf('final line');
  harness.svElement.dispatch('keyup');
  assert.equal(gutterLines.children[3].classList.contains('is-active'), true);
  assert.equal(gutterLines.children[0].classList.contains('is-active'), false);

  // Scroll sync moves gutter 1:1 and preview proportionally in split view
  harness.svElement.scrollTop = 400; // 400 / (1200 - 400) = 0.5
  harness.svElement.dispatch('scroll');
  assert.equal(gutterLines.style.transform, 'translateY(-400px)');
  assert.equal(harness.previewElement.scrollTop, 600); // 0.5 * (1600 - 400)

  // Empty document keeps line 1
  harness.typeInEditor('');
  assert.equal(harness.field.markdownEditor.lineCount(), 1);
  assert.deepEqual(gutterLines.children.map((el) => el.textContent), ['1']);

  // Long 250-line document updates digit width to 3
  const longDoc = Array.from({ length: 250 }, (_, i) => `line ${i + 1}`).join('\n');
  harness.typeInEditor(longDoc);
  assert.equal(harness.field.markdownEditor.lineCount(), 250);
  assert.equal(harness.gutter().style.props['--line-digits'], '3');
  assert.equal(gutterLines.children.length, 250);
  assert.equal(gutterLines.children[249].textContent, '250');

  // ResizeObserver re-measures without throwing
  harness.svElement.clientWidth = 320;
  harness.resizeObserver().callback();
  assert.equal(gutterLines.children.length, 250);
});

test('switching editor views preserves unsaved drafts without triggering spurious saves', async () => {
  const harness = createDraftHarness();
  harness.execute();

  // Mode switching alone does not mark the draft dirty or issue a save
  harness.state().editor.setViewMode('source');
  harness.state().editor.setViewMode('preview');
  harness.state().editor.setViewMode('split');
  await harness.advance(1000);
  assert.equal(harness.requests.length, 0);
  assert.equal(harness.state().dirty, false);

  // Editing and switching views preserves the edited content for autosave
  harness.changeBody('## Draft heading\n\nUnsaved paragraph');
  harness.state().editor.setViewMode('preview');
  harness.state().editor.setViewMode('source');
  await harness.advance(1000);

  assert.equal(harness.requests.length, 1);
  assert.equal(harness.requests[0].body.body, '## Draft heading\n\nUnsaved paragraph');
  assert.equal(harness.status.textContent, '草稿已保存');
});
