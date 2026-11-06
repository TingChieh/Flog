(() => {
  // Shared pieces for slow uploads: a status line with a progress bar, a POST
  // that reports how many bytes have been sent, and a lock that stops a form
  // from being submitted twice.

  // fetch cannot report upload progress, so this uses XMLHttpRequest. The
  // result looks like a fetch response (ok, status, json()).
  const post = (url, body, { headers = {}, onProgress, onSent } = {}) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    Object.keys(headers).forEach((name) => xhr.setRequestHeader(name, headers[name]));
    if (xhr.upload) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
      };
      xhr.upload.onload = () => { if (onSent) onSent(); };
    }
    xhr.onload = () => resolve({
      ok: xhr.status >= 200 && xhr.status < 300,
      status: xhr.status,
      json: () => new Promise((done) => done(JSON.parse(xhr.responseText))),
    });
    const fail = () => reject(new Error('network'));
    xhr.onerror = fail;
    xhr.onabort = fail;
    xhr.ontimeout = fail;
    xhr.send(body);
  });

  // Fills ``host`` with a text line and a <progress>. ``fraction`` is 0..1, or
  // null while the server is working and there is nothing to measure.
  const createProgress = (host) => {
    const text = document.createElement('span');
    text.className = 'upload-progress__text';
    const bar = document.createElement('progress');
    bar.className = 'upload-progress__bar';
    bar.max = 100;
    bar.hidden = true;
    host.append(bar, text);

    const setText = (message) => { text.textContent = message; };
    return {
      setText,
      show(message, fraction) {
        host.hidden = false;
        setText(message);
        bar.hidden = false;
        if (fraction === null || fraction === undefined) {
          bar.removeAttribute('value');
        } else {
          bar.value = Math.round(Math.min(1, Math.max(0, fraction)) * 100);
        }
      },
      message(message, state) {
        host.hidden = false;
        host.dataset.state = state || '';
        bar.hidden = true;
        setText(message);
      },
      busy(state) { host.dataset.state = state || 'uploading'; },
      hide() { host.hidden = true; },
    };
  };

  // Keeps an accidental reload or navigation from cutting an upload short.
  const guardLeaving = () => {
    const handler = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  };

  // A plain form whose submit is slow (the server works on the file): after the
  // first submit the buttons stay disabled and say so.
  const lockForm = (form) => {
    let locked = false;
    form.addEventListener('submit', (event) => {
      if (locked) {
        event.preventDefault();
        return;
      }
      locked = true;
      form.setAttribute('aria-busy', 'true');
      // Disable after the browser has collected the form data and started sending.
      setTimeout(() => {
        form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((button) => {
          button.disabled = true;
          if (button.tagName === 'BUTTON') button.textContent = button.dataset.busyLabel || '上传中…';
        });
      }, 0);
    });
  };

  const init = () => {
    document.querySelectorAll('form[data-upload-lock]').forEach(lockForm);
  };

  window.FlogUploadProgress = { post, createProgress, guardLeaving, lockForm };
  if (typeof document !== 'undefined' && document.querySelectorAll) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})();
