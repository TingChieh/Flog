(() => {
  const dialog = document.querySelector('[data-search-dialog]');
  const trigger = document.querySelector('[data-search-open]');
  if (!dialog || !trigger || !dialog.showModal) return;
  const input = dialog.querySelector('[data-search-input]');
  const status = dialog.querySelector('[data-search-status]');
  const list = dialog.querySelector('[data-search-results]');
  const form = dialog.querySelector('[data-search-form]');
  let previousFocus, scrollStyles, timer, controller, requestId = 0, selected = -1;

  function resetResults(message) {
    list.replaceChildren();
    selected = -1;
    status.textContent = message;
  }
  function appendSegments(element, segments) {
    segments.forEach(segment => {
      if (segment.highlight) {
        const mark = document.createElement('mark');
        mark.textContent = segment.text;
        element.append(mark);
      } else {
        element.append(document.createTextNode(segment.text));
      }
    });
  }
  function open() {
    if (dialog.open) return;
    previousFocus = document.activeElement;
    const root = document.documentElement;
    const scrollbarWidth = window.innerWidth - root.clientWidth;
    scrollStyles = {overflow: root.style.overflow, paddingRight: root.style.paddingRight};
    const padding = parseFloat(window.getComputedStyle(root).paddingRight) || 0;
    root.style.overflow = 'hidden';
    if (scrollbarWidth > 0) root.style.paddingRight = `${padding + scrollbarWidth}px`;
    dialog.showModal();
    input.focus();
  }
  function close() { if (dialog.open) dialog.close(); }
  trigger.addEventListener('click', event => { event.preventDefault(); open(); });
  dialog.querySelector('[data-search-close]').addEventListener('click', close);
  dialog.addEventListener('close', () => {
    document.documentElement.style.overflow = scrollStyles.overflow;
    document.documentElement.style.paddingRight = scrollStyles.paddingRight;
    clearTimeout(timer);
    requestId++;
    if (controller) controller.abort();
    input.value = '';
    resetResults(dialog.dataset.empty);
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
  });
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
  document.addEventListener('keydown', event => {
    const target = event.target;
    const typing = target instanceof Element && (target.isContentEditable || target.closest('input, textarea, select, [contenteditable="true"]'));
    if (((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') || (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey)) {
      event.preventDefault(); open();
    }
  });
  function select(index) {
    const links = [...list.querySelectorAll('a')];
    if (!links.length) return;
    selected = (index + links.length) % links.length;
    links.forEach((link, i) => link.classList.toggle('is-selected', i === selected));
    links[selected].focus();
    links[selected].scrollIntoView({block: 'nearest'});
  }
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      select(selected === -1 ? (direction === 1 ? 0 : -1) : selected + direction);
    } else if (event.key === 'Tab') {
      const elements = [...dialog.querySelectorAll('button, input, a[href]')].filter(el => !el.disabled);
      if (event.shiftKey && document.activeElement === elements[0]) { event.preventDefault(); elements[elements.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === elements[elements.length - 1]) { event.preventDefault(); elements[0].focus(); }
    }
  });
  form.addEventListener('submit', event => {
    const links = list.querySelectorAll('a');
    if (selected >= 0 && links[selected]) { event.preventDefault(); links[selected].click(); }
  });
  input.addEventListener('input', () => {
    clearTimeout(timer);
    if (controller) controller.abort();
    const id = ++requestId;
    const query = input.value.trim();
    if (!query) { resetResults(dialog.dataset.empty); return; }
    resetResults(dialog.dataset.loading);
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const response = await fetch(dialog.dataset.api + '?q=' + encodeURIComponent(query), {signal: controller.signal});
        if (!response.ok) throw new Error('Search request failed');
        const data = await response.json();
        if (id !== requestId) return;
        resetResults(data.results.length ? '' : dialog.dataset.noResults);
        data.results.forEach(result => {
          const item = document.createElement('li');
          const link = document.createElement('a');
          link.href = result.url;
          const title = document.createElement('strong'); appendSegments(title, result.title_segments);
          const excerpt = document.createElement('span'); appendSegments(excerpt, result.snippet_segments);
          const date = document.createElement('time'); date.textContent = result.date; date.dateTime = result.date;
          link.append(title, excerpt, date); item.append(link); list.append(item);
        });
      } catch (error) {
        if (error.name !== 'AbortError' && id === requestId) resetResults(dialog.dataset.error);
      }
    }, 250);
  });
})();
