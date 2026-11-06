document.addEventListener('DOMContentLoaded', () => {
  const button = document.querySelector('[data-post-preview]');
  const preview = document.getElementById('post-preview-form');
  const editor = document.getElementById('article-editor-form');
  if (!button || !preview || !editor) return;

  // The editor keeps its textarea in step with every change, so this is
  // exactly what the next autosave would store, saved or not.
  button.addEventListener('click', () => {
    preview.elements.title.value = editor.elements.title.value;
    preview.elements.body.value = editor.elements.post.value;
    preview.submit();
  });
});
