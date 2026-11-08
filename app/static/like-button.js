(function () {
  const form = document.querySelector('[data-like-form]');
  if (!form || !window.fetch) return;
  const buttons = Array.from(form.querySelectorAll('[data-reaction]'));
  const fallback = form.querySelector('[data-reaction-fallback]');
  let busy = false;

  // Motion in the style of a chat app: the picked emoji pops, a few of it float up, the
  // count rolls. Every bit of it is skipped for readers who asked for less motion.
  // Motion is decoration: if a browser refuses any of it, the reaction still has to count.
  const safely = (fn) => (...args) => {
    try { return fn(...args); } catch (error) { return undefined; }
  };
  const calm = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const POP = [
    { transform: 'scale(1) rotate(0deg)' },
    { transform: 'scale(1.7) rotate(-10deg)', offset: 0.35 },
    { transform: 'scale(.9) rotate(4deg)', offset: 0.65 },
    { transform: 'scale(1) rotate(0deg)' },
  ];

  const pop = safely((button) => {
    const emoji = button.querySelector('[data-reaction-emoji]');
    if (!emoji || !emoji.animate || calm()) return;
    emoji.animate(POP, { duration: 520, easing: 'cubic-bezier(.3, 1.3, .5, 1)' });
  });

  const layerAt = (button) => {
    const box = button.getBoundingClientRect();
    const layer = document.createElement('div');
    layer.className = 'reaction-burst';
    layer.setAttribute('aria-hidden', 'true');
    layer.style.left = `${box.left + box.width / 2}px`;
    layer.style.top = `${box.top + box.height / 2}px`;
    document.body.append(layer);
    return layer;
  };

  // One emoji travelling along `path` ([x, y, turn, scale] at the end), then gone.
  const fly = (layer, symbol, { to, size, duration, delay = 0, from = 0.3, easing }, done) => {
    const item = document.createElement('span');
    item.className = 'reaction-burst__item';
    item.textContent = symbol;
    layer.append(item);
    const [dx, dy, turn] = to;
    const run = item.animate && item.animate([
      { transform: `translate(-50%, -50%) scale(${from})`, opacity: 0 },
      { transform: `translate(calc(-50% + ${dx * 0.3}px), calc(-50% + ${dy * 0.35}px)) scale(${size})`, opacity: 1, offset: 0.2 },
      { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) rotate(${turn}deg) scale(${size * 0.85})`, opacity: 0 },
    ], { duration, easing, delay, fill: 'both' });
    if (run) run.onfinish = done; else done();
  };

  const burst = safely((button) => {
    if (calm() || !document.createElement || !document.body || !button.getBoundingClientRect) return;
    const layer = layerAt(button);
    const total = 5;
    let pending = total;
    const done = () => { pending -= 1; if (!pending) layer.remove(); };
    for (let i = 0; i < total; i += 1) {
      const side = (i - (total - 1) / 2) / ((total - 1) / 2);
      fly(layer, button.value, {
        to: [side * 46 + (Math.random() - 0.5) * 20, -(70 + Math.random() * 60), (Math.random() - 0.5) * 60],
        size: 0.75 + Math.random() * 0.5,
        duration: 800 + Math.random() * 300,
        delay: i * 30,
        easing: 'cubic-bezier(.2, .7, .3, 1)',
      }, done);
    }
  });

  // Taking a reaction back: the emoji shrinks away and a single one sinks out of the button.
  const sink = safely((button) => {
    const emoji = button.querySelector('[data-reaction-emoji]');
    if (emoji && emoji.animate && !calm()) {
      emoji.animate([
        { transform: 'scale(1) rotate(0deg)' },
        { transform: 'scale(.5) rotate(10deg)', offset: 0.4 },
        { transform: 'scale(1) rotate(0deg)' },
      ], { duration: 360, easing: 'cubic-bezier(.4, 0, .3, 1.2)' });
    }
    if (calm() || !document.createElement || !document.body || !button.getBoundingClientRect) return;
    const layer = layerAt(button);
    fly(layer, button.value, {
      to: [0, 28, 0], size: 0.9, from: 1, duration: 420, easing: 'cubic-bezier(.5, 0, .8, .6)',
    }, () => layer.remove());
  });

  // The first burst has to paint colour emoji it has never drawn; do that unseen, ahead of the click.
  let warmed = false;
  const warm = safely(() => {
    if (warmed || !document.createElement || !document.body) return;
    warmed = true;
    const layer = document.createElement('div');
    layer.className = 'reaction-burst';
    layer.setAttribute('aria-hidden', 'true');
    layer.style.left = '-100px';
    layer.style.top = '0px';
    buttons.forEach((button) => {
      const item = document.createElement('span');
      item.className = 'reaction-burst__item';
      item.textContent = button.value;
      layer.append(item);
    });
    document.body.append(layer);
    const clear = window.requestAnimationFrame || ((fn) => setTimeout(fn, 50));
    clear(() => clear(() => layer.remove()));
  });
  form.addEventListener('pointerenter', warm);
  form.addEventListener('focusin', warm);
  form.addEventListener('touchstart', warm);

  // The old number slides out as the new one slides in, inside a clipped box.
  const EASE = 'cubic-bezier(.3, .9, .4, 1)';
  const roll = safely((counter, before, up, wide) => {
    if (!counter.animate || calm()) return;
    const slide = (from, to) => [
      { transform: `translateY(${from}%)`, opacity: from ? 0 : 1 },
      { transform: `translateY(${to}%)`, opacity: to ? 0 : 1 },
    ];
    const timing = { duration: 280, easing: EASE, fill: 'both' };
    counter.animate(slide(up ? 100 : -100, 0), timing);
    const box = counter.parentNode;
    if (!before || !box || !document.createElement) return;
    const ghost = document.createElement('span');
    ghost.className = 'reaction__count reaction__count--ghost';
    ghost.setAttribute('aria-hidden', 'true');
    ghost.textContent = String(before);
    // The box has no width left once the number is gone; hold it open while the old one leaves.
    if (wide) box.style.minWidth = `${wide}px`;
    box.append(ghost);
    const out = ghost.animate ? ghost.animate(slide(0, up ? -100 : 100), timing) : null;
    const clear = () => { ghost.remove(); box.style.minWidth = ''; };
    if (out) out.onfinish = clear; else clear();
  });

  // The button grows or shrinks to its new width instead of snapping to it. Layout widths
  // (offsetWidth) are used because a bump or a press scales the box and would skew the numbers.
  const resize = safely((button, from) => {
    if (!from || !button.animate) return;
    const to = button.offsetWidth;
    if (!to || Math.abs(to - from) < 1) return;
    // Cut the sides while the box is narrower than what it holds; leave the top and bottom
    // open so a popping emoji is not clipped.
    if (button.style) button.style.clipPath = 'inset(-16px 0 -16px 0)';
    const run = button.animate([{ width: `${from}px` }, { width: `${to}px` }], { duration: 300, easing: EASE });
    const free = () => { if (button.style) button.style.clipPath = ''; };
    if (run) run.onfinish = free; else free();
  });

  // The whole button swells a little when picked, and settles when let go.
  const bump = safely((button, picked) => {
    if (!button.animate || calm()) return;
    button.animate(picked
      ? [{ transform: 'scale(1)' }, { transform: 'scale(1.12)', offset: 0.35 }, { transform: 'scale(1)' }]
      : [{ transform: 'scale(.92)' }, { transform: 'scale(1)' }],
    { duration: picked ? 460 : 260, easing: 'cubic-bezier(.3, 1.2, .5, 1)' });
  });

  const countOf = (button) => button.querySelector('[data-reaction-count]');
  const read = (button) => Number(countOf(button).textContent) || 0;
  const show = (button, active, total) => {
    const counter = countOf(button);
    const before = Number(counter.textContent) || 0;
    const moving = !calm() && total !== before;
    const width = moving ? button.offsetWidth || 0 : 0;
    const wide = moving ? counter.offsetWidth || 0 : 0;
    button.classList.toggle('reaction--active', active);
    button.setAttribute('aria-pressed', String(active));
    counter.textContent = total > 0 ? String(total) : '';
    if (moving && (total > 0 || before > 0)) {
      // Measure the new width before the leaving number is put back to slide out.
      resize(button, width);
      roll(counter, before, total > before, total > 0 ? 0 : wide);
    }
  };
  const snapshot = () => buttons.map((button) => ({
    button, active: button.getAttribute('aria-pressed') === 'true', total: read(button),
  }));
  const restore = (state) => state.forEach(({ button, active, total }) => show(button, active, total));

  // Picking an emoji takes it back when it is already yours, and moves your pick otherwise.
  const preview = (picked) => {
    const wasActive = picked.getAttribute('aria-pressed') === 'true';
    buttons.forEach((button) => {
      const active = button.getAttribute('aria-pressed') === 'true';
      if (button === picked) {
        show(button, !wasActive, Math.max(0, read(button) + (wasActive ? -1 : 1)));
        bump(button, !wasActive);
        if (wasActive) sink(button);
        else { pop(button); burst(button); }
      } else if (active) show(button, false, Math.max(0, read(button) - 1));
    });
  };

  const render = (result) => buttons.forEach((button) => {
    show(button, button.value === result.reaction, (result.counts || {})[button.value] || 0);
  });

  form.addEventListener('submit', async (event) => {
    const picked = event.submitter;
    if (!picked || !buttons.includes(picked)) return;
    event.preventDefault();
    if (busy) return;
    busy = true;
    const before = snapshot();
    preview(picked);
    try {
      const body = new FormData(form);
      body.set('emoji', picked.value);
      const response = await fetch(form.action, {
        method: 'POST',
        body,
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      const type = response.headers.get('Content-Type') || '';
      if (!response.ok || !type.includes('application/json')) throw new Error('not json');
      render(await response.json());
    } catch (error) {
      // Offline, expired session or a server error: undo, then let the page do it the old way.
      restore(before);
      if (fallback) {
        fallback.value = picked.value;
        fallback.disabled = false;
      }
      form.submit();
      return;
    }
    busy = false;
  });
})();
