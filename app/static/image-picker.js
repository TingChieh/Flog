(() => {
  const escapeTitle = (title) => String(title).replace(/[\\[\]]/g, '\\$&');
  const markdownFor = (image) => `![${escapeTitle(image.title)}](${image.url})`;
  const SEARCH_DELAY = 250;

  let current = null;

  const open = ({ url, onSelect }) => {
    if (current) current.remove();

    const dialog = document.createElement('dialog');
    dialog.className = 'image-picker';
    dialog.setAttribute('aria-label', '图片库');

    const header = document.createElement('div');
    header.className = 'image-picker__header';
    const heading = document.createElement('h2');
    heading.textContent = '图片库';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'image-picker__close';
    close.setAttribute('aria-label', '关闭');
    close.textContent = '×';
    header.append(heading, close);

    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'image-picker__search';
    search.placeholder = '按名称、备注或文件名搜索';
    search.setAttribute('aria-label', '搜索图片');

    const status = document.createElement('p');
    status.className = 'image-picker__status';
    status.setAttribute('role', 'status');

    const list = document.createElement('div');
    list.className = 'image-picker__list';

    dialog.append(header, search, status, list);
    document.body.append(dialog);
    current = dialog;

    const finish = () => {
      if (current === dialog) current = null;
      dialog.remove();
    };
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', finish);
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });

    const render = (images) => {
      status.textContent = images.length ? '' : '没有图片';
      list.replaceChildren(...images.map((image) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'image-picker__item';
        const thumb = document.createElement('img');
        thumb.src = image.url;
        thumb.alt = image.title;
        thumb.loading = 'lazy';
        const title = document.createElement('span');
        title.textContent = image.title;
        item.append(thumb, title);
        item.addEventListener('click', () => {
          onSelect(markdownFor(image));
          dialog.close();
        });
        return item;
      }));
    };

    let requestId = 0;
    const load = async () => {
      const id = ++requestId;
      status.textContent = '加载中…';
      try {
        const response = await fetch(
          `${url}?q=${encodeURIComponent(search.value || '')}`,
          { credentials: 'same-origin' });
        if (!response.ok) throw new Error('request failed');
        const payload = await response.json();
        if (!Array.isArray(payload?.images)) throw new Error('bad response');
        if (id === requestId) render(payload.images);
      } catch (_error) {
        if (id !== requestId) return;
        list.replaceChildren();
        status.textContent = '加载失败';
      }
    };

    let timer = null;
    search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(load, SEARCH_DELAY);
    });

    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    load();
  };

  window.FlogImagePicker = { open, markdownFor };
})();
