document.addEventListener('DOMContentLoaded', () => {
  const button = document.querySelector('[data-post-preview]');
  const preview = document.getElementById('post-preview-form');
  const editor = document.getElementById('article-editor-form');
  if (!button || !preview || !editor) return;

  // The editor keeps its textarea in step with every change, so this is
  // exactly what the next autosave would store, saved or not.
  button.addEventListener('click', () => {
    preview.elements.title.value = editor.elements.title.value;
    preview.elements.body.value = editor.elements.post.markdownEditor?.value() ?? editor.elements.post.value;
    if (editor.dataset?.postId) preview.elements.post_id.value = editor.dataset.postId;
    preview.submit();
  });

  document.querySelector('[data-publication-controls]')?.addEventListener('submit', (event) => {
    if (!event.submitter?.matches('[data-publish], [data-publish-update]')) return;
    event.target.addEventListener('formdata', ({ formData }) => {
      const { title, post, category } = editor.elements;
      formData.set('title', title.value);
      formData.set('post', post.markdownEditor?.value() ?? post.value);
      formData.set('category', category.value);
    }, { once: true });
  });
});
