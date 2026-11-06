(() => {
  // The image library's upload form: sends the files one set at a time so the
  // visitor sees real progress, can tell when the server is still working on a
  // file (a Live Photo clip takes a while), and cannot submit twice.
  const VIDEO = /\.(mov|mp4)$/i;
  const stemOf = (name) => name.replace(/\.[^.]*$/, '').toLowerCase();

  // A still and its same-named clip travel together as one Live Photo; every
  // other file goes alone. The server pairs them the same way.
  const groupFiles = (files) => {
    const groups = new Map();
    files.forEach((file) => {
      const key = stemOf(file.name);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(file);
    });
    const jobs = [];
    groups.forEach((list) => {
      const videos = list.filter((file) => VIDEO.test(file.name));
      const stills = list.filter((file) => !VIDEO.test(file.name));
      if (videos.length === 1 && stills.length === 1) jobs.push([stills[0], videos[0]]);
      else [...stills, ...videos].forEach((file) => jobs.push([file]));
    });
    return jobs;
  };

  const attach = (form, status) => {
    const { post, createProgress, guardLeaving } = window.FlogUploadProgress;
    const progress = createProgress(status);
    const input = form.querySelector('input[type="file"]');
    const button = form.querySelector('button[type="submit"]');
    const token = form.querySelector('input[name="csrf_token"]');
    const idleLabel = button.textContent;
    let busy = false;

    const setBusy = (on) => {
      busy = on;
      input.disabled = on;
      button.disabled = on;
      button.textContent = on ? '上传中…' : idleLabel;
      form.setAttribute('aria-busy', on ? 'true' : 'false');
    };

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (busy) return;
      const files = Array.from(input.files || []);
      if (!files.length) return;

      setBusy(true);
      const release = guardLeaving();
      const jobs = groupFiles(files);
      let saved = 0;
      const failed = [];

      for (let index = 0; index < jobs.length; index += 1) {
        const job = jobs[index];
        const position = jobs.length > 1 ? `${index + 1}/${jobs.length}` : '';
        const name = job[0].name;
        const label = (text) => [text, position, name].filter(Boolean).join(' ');
        const body = new FormData();
        if (token) body.append('csrf_token', token.value);
        job.forEach((file) => body.append('images', file, file.name));
        const overall = (part) => (index + part) / jobs.length;
        progress.show(label('正在上传'), overall(0));
        status.dataset.state = 'uploading';
        try {
          const response = await post(form.action, body, {
            headers: { Accept: 'application/json' },
            onProgress: (sent) => progress.show(
              `${label('正在上传')} · ${Math.round(sent * 100)}%`, overall(sent * 0.9)),
            onSent: () => progress.show(
              `${label('服务器处理中')}（视频转码可能需要几十秒，请不要关闭页面）`,
              jobs.length === 1 ? null : overall(0.95)),
          });
          if (!response.ok) {
            const rejected = new Error(`HTTP ${response.status}`);
            rejected.status = response.status;
            throw rejected;
          }
          const result = await response.json();
          saved += result.saved || 0;
          failed.push(...(result.failed || []));
        } catch (error) {
          // No status means the connection dropped before any answer came back.
          const reason = error.status ? `服务器返回 ${error.status}` : '连接中断或服务器处理超时';
          failed.push(`${name}：上传失败（${reason}），请稍后重试`);
        }
      }

      release();
      if (!failed.length) {
        progress.show(`已上传 ${saved} 张，正在刷新…`, 1);
        window.location.assign(`${window.location.pathname}?uploaded=${saved}`);
        return;
      }
      input.value = '';
      setBusy(false);
      const summary = `已上传 ${saved} 张，${failed.length} 项失败：${failed.join('；')}`;
      progress.message(summary, 'error');
      if (saved) {
        const link = document.createElement('a');
        link.href = `${window.location.pathname}?uploaded=${saved}`;
        link.textContent = '刷新列表';
        status.append(' ', link);
      }
    });
  };

  const init = () => {
    const form = document.querySelector('form[data-image-upload]');
    const status = document.querySelector('[data-upload-status]');
    if (form && status && window.FlogUploadProgress) attach(form, status);
  };

  window.FlogImageUpload = { groupFiles, attach };
  if (typeof document !== 'undefined' && document.querySelector) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})();
