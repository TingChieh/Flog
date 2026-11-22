document.addEventListener('DOMContentLoaded', () => {
  const TOOLBAR = [
    'headings', 'bold', 'italic', '|', 'quote', 'list', 'ordered-list', '|',
    'code', 'inline-code', 'link', 'table', 'line', 'emoji-picker', 'upload', 'image-library', '|',
    'undo', 'redo', '|', 'fullscreen',
  ];
  const VIEW_MODES = [
    { id: 'split', label: '分屏预览' },
    { id: 'source', label: '源码' },
    { id: 'preview', label: '仅预览' },
  ];
  const VIEW_MODE_IDS = new Set(VIEW_MODES.map((mode) => mode.id));
  const MIRROR_STYLE_PROPS = [
    'paddingLeft', 'paddingRight', 'fontFamily', 'fontSize', 'fontWeight', 'fontStyle',
    'letterSpacing', 'lineHeight', 'tabSize', 'whiteSpace', 'wordBreak',
    'overflowWrap', 'wordWrap', 'fontVariantLigatures',
  ];
  const IMAGE_TYPES = 'image/gif,image/jpeg,image/png';

  const isDark = () => document.documentElement.dataset.theme === 'dark';
  const splitLines = (text) => String(text ?? '').replace(/\r\n?/g, '\n').split('\n');

  const initializeEditors = () => {
    if (typeof Vditor === 'undefined') return;

    document.querySelectorAll('textarea[data-markdown-editor]').forEach((field) => {
      if (field.dataset.vditorInitialized) return;
      field.dataset.vditorInitialized = 'true';
      createEditor(field);
    });

    initializeArticleDraftEditor();
  };

  const createEditor = (field) => {
    const form = field.form;
    const uploadUrl = form?.dataset.imageUploadUrl;
    const csrfToken = form?.querySelector('input[name="csrf_token"]')?.value;
    const canUpload = Boolean(uploadUrl && csrfToken);
    const libraryUrl = form?.dataset.imageLibraryUrl;
    const cdn = field.dataset.vditorCdn;
    const initialValue = field.value;

    const host = document.createElement('div');
    host.className = 'markdown-editor-host';
    host.dataset.editorView = 'split';
    field.after(host);
    field.hidden = true;

    const status = document.createElement('div');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.hidden = true;
    status.className = 'markdown-upload-status';
    host.after(status);

    const listeners = [];
    let ready = false;
    let baseline = null;
    let vditor = null;
    let currentView = 'split';
    let lastLineCount = splitLines(initialValue).length;
    let lastMeasuredWidth = -1;
    let savedScrollTop = 0;
    let resizeRaf = null;
    let svElement = null;
    let previewElement = null;
    let gutterElement = null;
    let gutterLinesElement = null;
    let mirrorElement = null;
    let viewButtons = [];

    const currentValue = () => {
      if (!ready) return field.value;
      if (svElement) return svElement.value;
      const value = vditor.getValue();
      // Vditor may normalise the text (for example a trailing newline) on load.
      // That is not an edit, so report the original until the reader changes it.
      return value === baseline ? initialValue : value;
    };
    const sync = (value) => {
      field.value = value;
      listeners.forEach((listener) => listener(value));
    };

    const getSourceText = () => (svElement ? svElement.value : currentValue());

    const activeLineNumber = () => {
      if (!svElement) return 1;
      const pos = typeof svElement.selectionStart === 'number' ? svElement.selectionStart : 0;
      return splitLines(svElement.value.slice(0, pos)).length;
    };

    const syncGutterScroll = () => {
      if (!svElement || !gutterLinesElement?.style) return;
      gutterLinesElement.style.transform = `translateY(${-svElement.scrollTop}px)`;
    };

    const syncPreviewScroll = () => {
      if (currentView !== 'split' || !svElement || !previewElement) return;
      const sourceMax = svElement.scrollHeight - svElement.clientHeight;
      const previewMax = previewElement.scrollHeight - previewElement.clientHeight;
      if (sourceMax <= 0 || previewMax <= 0) {
        previewElement.scrollTop = 0;
        return;
      }
      const ratio = Math.min(1, Math.max(0, svElement.scrollTop / sourceMax));
      previewElement.scrollTop = ratio * previewMax;
    };

    const syncActiveLine = () => {
      if (!gutterLinesElement) return;
      const active = activeLineNumber();
      const nodes = gutterLinesElement.children || [];
      for (let i = 0; i < nodes.length; i += 1) {
        nodes[i].classList?.toggle('is-active', i + 1 === active);
      }
    };

    const updateLineNumbers = () => {
      const lines = splitLines(getSourceText());
      const lineCount = lines.length;
      lastLineCount = lineCount;
      if (!gutterElement || !gutterLinesElement) return;

      const digits = Math.max(2, String(lineCount).length);
      gutterElement.style?.setProperty?.('--line-digits', String(digits));

      let heights = null;
      const canMeasure = Boolean(
        svElement
        && mirrorElement
        && currentView !== 'preview'
        && svElement.clientWidth > 0
        && typeof window.getComputedStyle === 'function'
        && typeof mirrorElement.getBoundingClientRect === 'function',
      );

      if (canMeasure) {
        const computed = window.getComputedStyle(svElement);
        lastMeasuredWidth = svElement.clientWidth;
        mirrorElement.style.boxSizing = 'border-box';
        mirrorElement.style.width = `${svElement.clientWidth}px`;
        MIRROR_STYLE_PROPS.forEach((prop) => {
          mirrorElement.style[prop] = computed[prop];
        });
        if (gutterLinesElement.style) {
          gutterLinesElement.style.paddingTop = computed.paddingTop;
          gutterLinesElement.style.paddingBottom = computed.paddingBottom;
          gutterLinesElement.style.fontSize = computed.fontSize;
          gutterLinesElement.style.lineHeight = computed.lineHeight;
        }

        const mirrorChildren = mirrorElement.children;
        while (mirrorChildren.length < lineCount) {
          const lineEl = document.createElement('div');
          lineEl.className = 'markdown-editor__mirror-line';
          mirrorElement.append(lineEl);
        }
        while (mirrorChildren.length > lineCount) {
          mirrorChildren[mirrorChildren.length - 1].remove();
        }
        for (let i = 0; i < lineCount; i += 1) {
          const text = lines[i].length > 0 ? lines[i] : '\u200b';
          if (mirrorChildren[i].textContent !== text) {
            mirrorChildren[i].textContent = text;
          }
        }

        const rects = [];
        for (let i = 0; i < lineCount; i += 1) {
          rects.push(mirrorChildren[i].getBoundingClientRect());
        }
        heights = [];
        for (let i = 0; i < lineCount; i += 1) {
          const height = i + 1 < lineCount
            ? Math.max(0, rects[i + 1].top - rects[i].top)
            : rects[i].height;
          heights.push(height);
        }
      }

      const active = activeLineNumber();
      const gutterChildren = gutterLinesElement.children;
      while (gutterChildren.length < lineCount) {
        const num = gutterChildren.length + 1;
        const item = document.createElement('div');
        item.className = 'markdown-editor__line-number';
        item.dataset.line = String(num);
        item.textContent = String(num);
        gutterLinesElement.append(item);
      }
      while (gutterChildren.length > lineCount) {
        gutterChildren[gutterChildren.length - 1].remove();
      }
      for (let i = 0; i < lineCount; i += 1) {
        const item = gutterChildren[i];
        if (heights && item.style) {
          const px = `${heights[i]}px`;
          if (item.style.height !== px) item.style.height = px;
        } else if (item.style?.height) {
          item.style.height = '';
        }
        item.classList?.toggle('is-active', i + 1 === active);
      }

      syncGutterScroll();
    };

    const scheduleLineUpdate = () => {
      if (typeof window.requestAnimationFrame !== 'function') {
        updateLineNumbers();
        return;
      }
      if (resizeRaf !== null) return;
      resizeRaf = window.requestAnimationFrame(() => {
        resizeRaf = null;
        updateLineNumbers();
      });
    };

    const setEditToolbarDisabled = (disabled) => {
      const toolbar = host.querySelector?.('.vditor-toolbar');
      if (!toolbar?.querySelectorAll) return;
      toolbar.querySelectorAll('.vditor-toolbar__item > button').forEach((button) => {
        if (button.dataset?.type === 'fullscreen') return;
        button.disabled = disabled;
        button.classList?.toggle('vditor-menu--disabled', disabled);
        button.setAttribute('aria-disabled', String(disabled));
      });
      if (disabled) {
        toolbar.querySelectorAll('.vditor-panel').forEach((panel) => {
          if (panel.style) panel.style.display = 'none';
        });
      }
    };

    const updateViewButtons = (mode) => {
      viewButtons.forEach((button) => {
        const active = button.dataset.viewMode === mode;
        button.setAttribute('aria-pressed', String(active));
        button.classList?.toggle('is-active', active);
      });
    };

    const setViewMode = (mode, { focusEditor = false } = {}) => {
      if (!VIEW_MODE_IDS.has(mode)) return;
      const previous = currentView;
      if (previous !== 'preview' && mode === 'preview' && svElement) {
        savedScrollTop = svElement.scrollTop || 0;
      }
      currentView = mode;
      host.dataset.editorView = mode;
      updateViewButtons(mode);
      if (!ready) return;

      if (mode === 'split') {
        vditor.setPreviewMode?.('both');
        if (svElement?.style) svElement.style.display = 'block';
        if (previewElement?.style) previewElement.style.display = 'block';
        if (gutterElement) gutterElement.hidden = false;
        setEditToolbarDisabled(false);
        if (previous === 'preview' && svElement) svElement.scrollTop = savedScrollTop;
        vditor.renderPreview?.();
        updateLineNumbers();
        syncPreviewScroll();
        if (focusEditor) svElement?.focus?.();
      } else if (mode === 'source') {
        vditor.setPreviewMode?.('editor');
        if (svElement?.style) svElement.style.display = 'block';
        if (previewElement?.style) previewElement.style.display = 'none';
        if (gutterElement) gutterElement.hidden = false;
        setEditToolbarDisabled(false);
        if (previous === 'preview' && svElement) svElement.scrollTop = savedScrollTop;
        updateLineNumbers();
        if (focusEditor) svElement?.focus?.();
      } else {
        vditor.setPreviewMode?.('both');
        if (svElement?.style) svElement.style.display = 'none';
        if (gutterElement) gutterElement.hidden = true;
        if (previewElement?.style) previewElement.style.display = 'block';
        setEditToolbarDisabled(true);
        vditor.renderPreview?.();
      }
    };

    const mountViewSwitcher = () => {
      const views = document.createElement('div');
      views.className = 'markdown-editor__views';
      views.setAttribute('role', 'group');
      views.setAttribute('aria-label', '编辑器视图');

      viewButtons = VIEW_MODES.map((entry) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'markdown-editor__view-btn';
        button.dataset.viewMode = entry.id;
        button.textContent = entry.label;
        button.setAttribute('aria-pressed', String(entry.id === currentView));
        if (entry.id === currentView) button.classList?.add('is-active');
        button.addEventListener('click', () => setViewMode(entry.id));
        views.append(button);
        return button;
      });

      views.addEventListener('keydown', (event) => {
        const index = viewButtons.indexOf(event.target);
        if (index === -1) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % viewButtons.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + viewButtons.length) % viewButtons.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = viewButtons.length - 1;
        if (next !== -1) {
          event.preventDefault?.();
          viewButtons[next].focus?.();
        }
      });

      const toolbar = host.querySelector?.('.vditor-toolbar');
      if (toolbar?.append) toolbar.append(views);
      else host.append?.(views);
    };

    const mountLineNumbers = () => {
      svElement = host.querySelector?.('textarea.vditor-sv') || null;
      previewElement = host.querySelector?.('.vditor-preview') || null;
      if (!svElement) return;

      gutterElement = document.createElement('div');
      gutterElement.className = 'markdown-editor__gutter';
      gutterElement.setAttribute('aria-hidden', 'true');
      gutterElement.dataset.lineGutter = '';

      gutterLinesElement = document.createElement('div');
      gutterLinesElement.className = 'markdown-editor__gutter-lines';
      gutterLinesElement.dataset.lineGutterLines = '';
      gutterElement.append(gutterLinesElement);

      mirrorElement = document.createElement('div');
      mirrorElement.className = 'markdown-editor__mirror';
      mirrorElement.setAttribute('aria-hidden', 'true');

      if (typeof svElement.before === 'function') svElement.before(gutterElement);
      else host.append?.(gutterElement);
      host.append?.(mirrorElement);

      svElement.addEventListener('input', () => updateLineNumbers());
      svElement.addEventListener('keyup', syncActiveLine);
      svElement.addEventListener('click', syncActiveLine);
      svElement.addEventListener('select', syncActiveLine);
      svElement.addEventListener('focus', syncActiveLine);
      svElement.addEventListener('scroll', () => {
        if (svElement.clientWidth > 0 && svElement.clientWidth !== lastMeasuredWidth) {
          updateLineNumbers();
        } else {
          syncGutterScroll();
        }
        syncPreviewScroll();
      });

      gutterElement.addEventListener('wheel', (event) => {
        if (!svElement || svElement.scrollHeight <= svElement.clientHeight) return;
        svElement.scrollTop += event.deltaY || 0;
        syncGutterScroll();
        syncPreviewScroll();
      }, { passive: true });

      if (typeof ResizeObserver === 'function') {
        new ResizeObserver(() => scheduleLineUpdate()).observe(svElement);
      }
      if (document.fonts?.ready?.then) {
        document.fonts.ready.then(() => updateLineNumbers()).catch(() => {});
      }
    };

    // With the shared helper the status line also carries a progress bar.
    const progressUi = window.FlogUploadProgress
      ? window.FlogUploadProgress.createProgress(status) : null;
    const setStatus = (state, message) => {
      status.hidden = false;
      status.dataset.state = state;
      if (progressUi) progressUi.message(message, state);
      else status.textContent = message;
    };
    let uploading = false;
    const isImageFile = (file) => file?.type?.startsWith('image/');

    const uploadImages = async (files) => {
      const images = Array.from(files || []).filter(isImageFile);
      if (!images.length) return null;
      // A second drop while photos are still going up would only pile on.
      if (uploading) return null;
      uploading = true;

      const heading = `正在上传 ${images.length} 张图片…`;
      setStatus('uploading', heading);
      const trackProgress = Boolean(progressUi && typeof XMLHttpRequest === 'function');
      const send = (formData, index) => {
        const headers = { 'X-CSRFToken': csrfToken };
        if (!trackProgress) return fetch(uploadUrl, { method: 'POST', headers, body: formData });
        const step = images.length > 1 ? `第 ${index + 1}/${images.length} 张` : '';
        const show = (text, fraction) => progressUi.show([text, step].filter(Boolean).join(' '), fraction);
        show(heading, 0);
        return window.FlogUploadProgress.post(uploadUrl, formData, {
          headers,
          onProgress: (sent) => show(`${heading} ${Math.round(sent * 100)}%`, sent),
          onSent: () => show('服务器处理中…', null),
        });
      };
      try {
        const snippets = [];
        for (const [index, file] of images.entries()) {
          const formData = new FormData();
          formData.append('post', file);
          const response = await send(formData, index);
          if (!response.ok) throw new Error('upload failed');
          const payload = await response.json();
          if (payload?.uploaded !== 1 || typeof payload.url !== 'string') {
            throw new Error('invalid upload response');
          }
          snippets.push(`![图片](${payload.url})`);
        }
        vditor.insertValue(snippets.join('\n\n'));
        sync(currentValue());
        updateLineNumbers();
        if (currentView === 'preview') vditor.renderPreview?.();
        setStatus('success', '图片已插入');
      } catch (_error) {
        setStatus('error', '上传失败：无法上传图片');
      } finally {
        uploading = false;
      }
      return null;
    };

    const libraryButton = () => {
      if (!libraryUrl || !window.FlogImagePicker) return null;
      return {
        name: 'image-library',
        tip: '图片库',
        tipPosition: 's',
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 8"/></svg>',
        click: () => window.FlogImagePicker.open({
          url: libraryUrl,
          onSelect: (markdown) => {
            vditor.insertValue(markdown);
            sync(currentValue());
            updateLineNumbers();
            setStatus('success', '图片已插入');
          },
        }),
      };
    };

    const emojiButton = () => {
      if (!window.FlogEmojiPicker) return null;
      return {
        name: 'emoji-picker',
        tip: '表情',
        tipPosition: 's',
        // Vditor fills toolbar icons, so the face is cut out of a solid disc.
        icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-3.2 6.2a1.1 1.1 0 1 1 0 2.2 1.1 1.1 0 0 1 0-2.2Zm6.4 0a1.1 1.1 0 1 1 0 2.2 1.1 1.1 0 0 1 0-2.2ZM8 14.2c.9 1.5 2.3 2.4 4 2.4s3.1-.9 4-2.4l-1.2-.8c-.6 1.1-1.6 1.7-2.8 1.7s-2.2-.6-2.8-1.7L8 14.2Z"/></svg>',
        click: (event) => window.FlogEmojiPicker.open({
          anchor: event?.currentTarget || host,
          onPick: (chars) => {
            vditor.insertValue(chars);
            sync(currentValue());
            updateLineNumbers();
          },
        }),
      };
    };

    const applyTheme = () => {
      if (!ready) return;
      vditor.setTheme(isDark() ? 'dark' : 'classic', isDark() ? 'dark' : 'light');
    };

    vditor = new Vditor(host, {
      mode: 'sv',
      lang: 'zh_CN',
      cdn,
      icon: 'ant',
      value: initialValue,
      minHeight: 320,
      theme: isDark() ? 'dark' : 'classic',
      fullscreen: { index: 1050 },
      cache: { enable: false },
      counter: { enable: true, type: 'markdown' },
      toolbar: TOOLBAR.map((item) => {
        if (item === 'image-library') return libraryButton();
        if (item === 'emoji-picker') return emojiButton();
        return item;
      }).filter((item) => item && (canUpload || item !== 'upload')),
      preview: {
        mode: 'both',
        delay: 150,
        actions: [],
        hljs: { enable: false },
        theme: {
          current: isDark() ? 'dark' : 'light',
          path: `${cdn}/dist/css/content-theme`,
        },
        markdown: {
          inlineMath: false,
          mathBlockPreview: false,
          codeBlockPreview: false,
          callout: false,
          mark: false,
          sup: false,
          sub: false,
          gfmAutoLink: false,
          footnotes: true,
          sanitize: true,
        },
      },
      ...(canUpload ? {
        upload: { accept: IMAGE_TYPES, multiple: true, handler: uploadImages },
      } : {}),
      input: (value) => {
        sync(svElement ? svElement.value : value);
        updateLineNumbers();
      },
      after: () => {
        ready = true;
        baseline = vditor.getValue();
        // Let the stylesheet size the split/source/preview frame cleanly so panes scroll internally.
        if (host.style) host.style.height = '';
        // Pure WYSIWYG would rewrite the Markdown source formatting.
        host.querySelector('button[data-mode="wysiwyg"]')?.remove();
        mountViewSwitcher();
        mountLineNumbers();
        applyTheme();
        setViewMode(currentView);
      },
    });

    field.markdownEditor = {
      vditor,
      value: currentValue,
      onChange: (listener) => listeners.push(listener),
      viewMode: () => currentView,
      setViewMode,
      lineCount: () => lastLineCount,
      refreshLineNumbers: updateLineNumbers,
    };

    form?.addEventListener('submit', () => {
      if (ready) field.value = currentValue();
    });
    new MutationObserver(applyTheme).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
  };

  const initializeArticleDraftEditor = () => {
    const editorRoot = document.querySelector('[data-article-draft-editor]');
    if (!editorRoot || editorRoot.dataset.draftEditorInitialized) return;

    const field = editorRoot.querySelector('textarea[data-markdown-editor]');
    const title = editorRoot.querySelector('[name="title"]');
    const category = editorRoot.querySelector('[name="category"]');
    const publicationControls = document.querySelector('[data-publication-controls]');
    const status = publicationControls?.querySelector('[data-draft-save-status]');
    const publicationStatus = publicationControls?.querySelector(
      '[data-publication-status]');
    if (!field || !field.markdownEditor || !title || !category || !status) return;

    editorRoot.dataset.draftEditorInitialized = 'true';
    const state = {
      postId: editorRoot.dataset.postId ? Number(editorRoot.dataset.postId) : null,
      dirty: false,
      saveTimer: null,
      lastSavedPayload: null,
      draftUrl: editorRoot.dataset.draftUrl,
      leaveUrl: editorRoot.dataset.leaveUrl,
      csrfToken: editorRoot.dataset.csrfToken,
      draftKey: editorRoot.dataset.draftKey,
      editor: field.markdownEditor,
      form: editorRoot,
      status,
      publicationControls,
      publicationStatus,
      leaveSent: false,
      intentionalLeave: false,
      saveInFlight: false,
      saveQueued: false,
      nextSequence: Number(editorRoot.dataset.editorSequence || 0),
      generation: Number(editorRoot.dataset.draftGeneration || 0),
      responseEpoch: 0,
      acknowledgedSequence: 0,
    };
    state.lastSavedPayload = draftPayload(state, title, category);
    window.articleDraftEditor = state;

    const scheduleSave = () => {
      state.dirty = true;
      state.status.textContent = '保存中';
      clearTimeout(state.saveTimer);
      state.saveTimer = setTimeout(() => saveDraft(state, title, category), 1000);
    };

    title.addEventListener('input', scheduleSave);
    category.addEventListener('change', scheduleSave);
    state.editor.onChange(scheduleSave);
    document.querySelectorAll('[data-draft-leave-action]').forEach((form) => {
      form.addEventListener('submit', () => markIntentionalLeave(state));
    });
    window.addEventListener('pagehide', () => {
      if (state.intentionalLeave || state.leaveSent || !state.leaveUrl ||
          !payloadChanged(state, title, category)) return;
      state.leaveSent = true;
      clearTimeout(state.saveTimer);
      state.saveTimer = null;
      const payload = draftPayload(state, title, category);
      const sequence = ++state.nextSequence;
      const epoch = state.responseEpoch;
      fetch(state.leaveUrl, requestOptions(
        'POST', state, payload, true, sequence)).then(
        async (response) => {
          if (!response.ok) return;
          const saved = await response.json();
          if (updateSavedState(state, payload, saved, sequence, epoch)) {
            state.dirty = payloadChanged(state, title, category);
            updatePublicationState(state);
            state.status.textContent = state.dirty ? '保存中' : '草稿已保存';
          }
        }).catch(() => {});
    });

    window.addEventListener('pageshow', (event) => {
      if (event.persisted) {
        if (state.intentionalLeave) {
          window.location.reload();
          return;
        }
        state.leaveSent = false;
      }
    });
  };

  const draftPayload = (state, title, category) => ({
    title: title.value,
    category_id: Number(category.value),
    body: state.editor.value(),
  });

  const payloadChanged = (state, title, category) => JSON.stringify(
    draftPayload(state, title, category)) !== JSON.stringify(state.lastSavedPayload);

  const requestOptions = (method, state, payload, keepalive = false, sequence) => ({
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': state.csrfToken,
      'X-Draft-Generation': String(state.generation),
      ...(state.draftKey ? { 'X-Draft-Key': state.draftKey } : {}),
      ...(sequence ? { 'X-Draft-Sequence': String(sequence) } : {}),
    },
    body: JSON.stringify(payload),
    ...(keepalive ? { keepalive: true } : {}),
  });

  const saveDraft = async (state, title, category) => {
    if (state.intentionalLeave) return;
    if (state.saveInFlight) {
      state.saveQueued = true;
      return;
    }
    state.saveInFlight = true;
    state.saveTimer = null;
    const payload = draftPayload(state, title, category);
    const sequence = ++state.nextSequence;
    const epoch = state.responseEpoch;
    try {
      const response = await fetch(state.draftUrl, requestOptions(
        state.postId ? 'PUT' : 'POST', state, payload, false, sequence));
      if (!response.ok) throw new Error('draft save failed');
      const saved = await response.json();
      if (updateSavedState(state, payload, saved, sequence, epoch)) {
        state.dirty = payloadChanged(state, title, category);
        updatePublicationState(state);
        state.status.textContent = state.dirty ? '保存中' : '草稿已保存';
      }
    } catch (_error) {
      if (epoch === state.responseEpoch && sequence >= state.acknowledgedSequence) {
        state.dirty = true;
        state.status.textContent = '保存失败';
      }
    } finally {
      state.saveInFlight = false;
      if (state.saveQueued) {
        state.saveQueued = false;
        state.status.textContent = '保存中';
        saveDraft(state, title, category);
      }
    }
  };

  const updateSavedState = (state, payload, saved, sequence, epoch) => {
    if (epoch !== state.responseEpoch || sequence < state.acknowledgedSequence) {
      return false;
    }
    if (!saved.applied || saved.generation !== state.generation ||
        saved.sequence !== sequence) throw new Error('draft save was superseded');
    if (!state.postId && Number.isInteger(saved.post_id)) {
      state.postId = saved.post_id;
      state.form.dataset.postId = String(state.postId);
      state.draftUrl = state.draftUrl.replace(
        /\/draft$/, `/${state.postId}/draft`);
      state.leaveUrl = state.draftUrl.replace(/\/draft$/, '/leave');
      const editUrl = state.draftUrl.replace(/\/draft$/, '/edit');
      state.form.action = editUrl;
      if (window.history && typeof window.history.replaceState === 'function') {
        window.history.replaceState(null, '', editUrl);
      }
    }
    state.lastSavedPayload = payload;
    state.acknowledgedSequence = sequence;
    return true;
  };

  const updatePublicationState = (state) => {
    const controls = state.publicationControls;
    if (!controls) return;
    if (controls.dataset.publicationState === 'new') {
      appendPublishButton(state);
      return;
    }
    if (controls.dataset.publicationState !== 'published') return;
    controls.dataset.publicationState = 'published-draft';
    const unpublish = controls.querySelector('[data-unpublish]');
    if (unpublish) unpublish.disabled = true;
    const publishUpdate = controls.querySelector('[data-publish-update]');
    if (publishUpdate) publishUpdate.hidden = false;
    if (state.publicationStatus) {
      state.publicationStatus.textContent = '有未发布修改';
    }
  };

  const markIntentionalLeave = (state) => {
    state.intentionalLeave = true;
    state.responseEpoch += 1;
    state.saveQueued = false;
    clearTimeout(state.saveTimer);
    state.saveTimer = null;
  };

  const appendPublishButton = (state) => {
    const controls = state.publicationControls;
    if (!state.postId || controls.dataset.publicationState !== 'new') return;
    controls.dataset.publicationState = 'draft';

    const form = document.createElement('form');
    form.method = 'post';
    form.action = state.draftUrl.replace(/\/draft$/, '/publish');
    form.dataset.draftLeaveAction = '';
    const csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = 'csrf_token';
    csrf.value = state.csrfToken;
    const button = document.createElement('button');
    button.type = 'submit';
    button.className = 'button button--cta';
    button.dataset.publish = '';
    button.textContent = '发布';
    form.append(csrf, button);
    form.addEventListener('submit', () => markIntentionalLeave(state));
    controls.append(form);
  };

  initializeEditors();
});
