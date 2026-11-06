(() => {
  const RECENT_KEY = 'flog-emoji-recent';
  const RECENT_MAX = 24;

  const searchGroups = (groups, query) => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const found = [];
    groups.forEach((group) => group.items.forEach((item) => {
      const haystack = `${item[1]} ${item[2]}`.toLowerCase();
      if (words.every((word) => haystack.includes(word))) found.push(item);
    }));
    return found;
  };

  const pushRecent = (list, chars, max = RECENT_MAX) => (
    [chars, ...list.filter((item) => item !== chars)].slice(0, max));

  const insertAtCursor = (field, text, makeEvent = (type) => new Event(type, { bubbles: true })) => {
    const start = field.selectionStart ?? field.value.length;
    const end = field.selectionEnd ?? start;
    field.setRangeText(text, start, end, 'end');
    field.focus();
    field.dispatchEvent(makeEvent('input'));
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { searchGroups, pushRecent, insertAtCursor };
  }
  if (typeof document === 'undefined') return;

  const base = document.currentScript?.dataset.base || '/static/emoji/noto/';
  const keyOf = (chars) => Array.from(chars.replace(/️/g, ''))
    .map((c) => c.codePointAt(0).toString(16)).join('-');

  const readRecent = () => {
    try {
      const list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      return Array.isArray(list) ? list.filter((item) => typeof item === 'string') : [];
    } catch (_error) {
      return [];
    }
  };
  const writeRecent = (list) => {
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch (_error) { /* storage unavailable */ }
  };

  let panel = null;
  let opener = null;

  const close = () => {
    if (!panel) return;
    panel.remove();
    panel = null;
    document.removeEventListener('keydown', onKey, true);
    document.removeEventListener('pointerdown', onOutside, true);
    opener?.focus();
    opener = null;
  };
  const onKey = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  };
  const onOutside = (event) => {
    if (panel && !panel.contains(event.target) && !opener?.contains(event.target)) close();
  };

  const makeItem = (item, onPick) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'emoji-picker__item';
    button.title = item[1];
    const image = document.createElement('img');
    image.className = 'emoji';
    image.alt = item[0];
    image.loading = 'lazy';
    image.src = `${base}${keyOf(item[0])}.png`;
    button.append(image);
    button.addEventListener('click', () => onPick(item[0]));
    return button;
  };

  const fill = (host, sections, onPick) => {
    host.replaceChildren();
    sections.forEach(({ label, items, id }) => {
      if (!items.length) return;
      const heading = document.createElement('h3');
      heading.textContent = label;
      if (id) heading.id = `emoji-group-${id}`;
      const grid = document.createElement('div');
      grid.className = 'emoji-picker__grid';
      items.forEach((item) => grid.append(makeItem(item, onPick)));
      host.append(heading, grid);
    });
    if (!host.children.length) {
      const empty = document.createElement('p');
      empty.className = 'emoji-picker__empty';
      empty.textContent = '没有找到匹配的表情';
      host.append(empty);
    }
  };

  const open = ({ anchor, onPick }) => {
    const groups = window.FlogEmoji?.groups;
    if (!groups) return;
    close();
    opener = anchor;

    panel = document.createElement('div');
    panel.className = 'emoji-picker';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', '选择表情');

    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'form-control emoji-picker__search';
    search.placeholder = '搜索表情';
    search.setAttribute('aria-label', '搜索表情');

    const tabs = document.createElement('div');
    tabs.className = 'emoji-picker__tabs';
    const list = document.createElement('div');
    list.className = 'emoji-picker__list';

    const byChars = new Map(groups.flatMap((g) => g.items).map((item) => [item[0], item]));
    const pick = (chars) => {
      writeRecent(pushRecent(readRecent(), chars));
      close();
      onPick(chars);
    };
    const showAll = () => {
      const recent = readRecent().map((chars) => byChars.get(chars)).filter(Boolean);
      fill(list, [{ label: '最近使用', items: recent, id: 'recent' }, ...groups], pick);
    };

    [{ label: '最近', id: 'recent' }, ...groups].forEach((group) => {
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.textContent = group.label;
      tab.addEventListener('click', () => {
        search.value = '';
        showAll();
        list.querySelector(`#emoji-group-${group.id}`)?.scrollIntoView({ block: 'start' });
      });
      tabs.append(tab);
    });
    search.addEventListener('input', () => {
      const query = search.value.trim();
      if (!query) { showAll(); return; }
      fill(list, [{ label: '搜索结果', items: searchGroups(groups, query) }], pick);
    });

    showAll();
    panel.append(search, tabs, list);
    document.body.append(panel);

    const box = anchor.getBoundingClientRect();
    const width = Math.min(panel.offsetWidth || 340, window.innerWidth - 16);
    panel.style.top = `${window.scrollY + box.bottom + 6}px`;
    panel.style.left = `${Math.max(8, Math.min(window.scrollX + box.left, window.scrollX + window.innerWidth - width - 8))}px`;
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onOutside, true);
    search.focus();
  };

  window.FlogEmojiPicker = { open, close };

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-emoji-for]');
    if (!trigger) return;
    const field = document.querySelector(trigger.dataset.emojiFor);
    if (!field) return;
    event.preventDefault();
    open({ anchor: trigger, onPick: (chars) => insertAtCursor(field, chars) });
  });
})();
