(() => {
  const SCOPES = '.article-body, .page-body, .post-comment__text';
  const SKIPPED = 'pre, code, script, style, textarea, .katex, .mermaid';
  const EMOJI = /\p{Regional_Indicator}{2}|[#*0-9]️?⃣|\p{Extended_Pictographic}(?:️|\p{Emoji_Modifier})?(?:‍\p{Extended_Pictographic}(?:️|\p{Emoji_Modifier})?)*/gu;

  const emojiKey = (chars) => Array.from(chars.replace(/️/g, ''))
    .map((c) => c.codePointAt(0).toString(16))
    .join('-');

  // Cut text into plain pieces and the emoji that have an image.
  const splitText = (text, keys) => {
    const pieces = [];
    let last = 0;
    for (const match of text.matchAll(EMOJI)) {
      const key = emojiKey(match[0]);
      if (!keys.has(key)) continue;
      if (match.index > last) pieces.push({ text: text.slice(last, match.index) });
      pieces.push({ emoji: match[0], key });
      last = match.index + match[0].length;
    }
    if (last < text.length) pieces.push({ text: text.slice(last) });
    return pieces;
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { emojiKey, splitText };
  }
  if (typeof document === 'undefined') return;

  const base = document.currentScript?.dataset.base || '/static/emoji/noto/';
  const keys = new Set((window.FlogEmojiKeys || '').split(' ').filter(Boolean));
  if (!keys.size) return;

  const toImage = (piece) => {
    const image = document.createElement('img');
    image.className = 'emoji';
    image.alt = piece.emoji;
    image.draggable = false;
    image.src = `${base}${piece.key}.png`;
    image.addEventListener('error', () => image.replaceWith(piece.emoji), { once: true });
    return image;
  };

  const replaceIn = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      if (node.parentElement.closest(SKIPPED)) return;
      const pieces = splitText(node.nodeValue, keys);
      if (pieces.length === 1 && pieces[0].text !== undefined) return;
      node.replaceWith(...pieces.map((piece) => (
        piece.text !== undefined ? piece.text : toImage(piece))));
    });
  };

  const run = () => document.querySelectorAll(SCOPES).forEach(replaceIn);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
