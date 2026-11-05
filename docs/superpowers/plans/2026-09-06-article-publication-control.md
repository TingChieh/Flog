# Article Publication Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move article publication controls and save-state feedback into the editor header and remove the oversized bottom action area.

**Architecture:** Reuse the existing publish, unpublish, publish-update, and autosave behavior. The template renders a compact header action group from current Post and draft state; the existing browser autosave script updates its header status target.

**Tech Stack:** Flask, Jinja2, Flask-WTF CSRF forms, vanilla JavaScript, CSS, pytest, Node.js node:test.

## Global Constraints

- The 公开 switch represents current public-version visibility.
- A published article with a draft remains public and shows 有未发布修改; only 发布更新 replaces public content.
- An unpublished article can be published by switching 公开 on; a published article without a draft can be unpublished by switching it off.
- Header status is 保存中, 草稿已保存, 保存失败, 已公开, or 有未发布修改.
- Failed saves never claim success or alter publication state.
- Preserve CSRF-protected non-JavaScript forms and remove the old bottom submit/unpublish area.

---

### Task 1: Render and Synchronize Header Publication Controls

**Files:**
- Modify: app/templates/admin/posts/form.html
- Modify: app/static/markdown-editor.js
- Modify: app/static/style.css
- Modify: tests/test_ui_pages.py
- Modify: tests/markdown_editor.test.js

**Interfaces:**
- Consumes post.is_published, post.draft, and current endpoint names.
- Produces data-publication-controls, data-publication-status, and data-draft-save-status in the editor header.
- window.articleDraftEditor continues to set the same status target after save results.

- [ ] **Step 1: Write failing template and browser tests**

~~~python
def test_published_article_with_draft_shows_header_switch_and_update_notice(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = True
        post.draft = PostDraft(title='Changed', body='draft', category_id=1)
        db.session.commit()
    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)
    assert 'data-publication-controls' in html
    assert '有未发布修改' in html
    assert '发布更新' in html
    assert 'Unpublish' not in html
~~~

~~~javascript
test('writes autosave state to the header publication status', async () => {
  const harness = createDraftHarness();
  harness.execute();
  harness.changeBody('changed');
  assert.equal(harness.status.textContent, '保存中');
  await harness.resolveSave();
  assert.equal(harness.status.textContent, '草稿已保存');
});
~~~

- [ ] **Step 2: Verify red**

Run: pytest tests/test_ui_pages.py -k publication -v && node --test tests/markdown_editor.test.js

Expected: FAIL because the header has no publication group and save status is below the editor.

- [ ] **Step 3: Implement header controls and styling**

~~~html
<div class="publication-controls" data-publication-controls>
  <label class="publication-switch">
    <input type="checkbox" role="switch" checked>
    <span>公开</span>
  </label>
  <span class="publication-status" data-publication-status>有未发布修改</span>
  <button class="button button--cta" type="submit">发布更新</button>
</div>
~~~

Render only state-appropriate forms: publish for unpublished draft; unpublish for published post without draft; checked switch plus publish-update for published post with draft. Retain CSRF tokens. Move the draft-save target into this group and select it from markdown-editor.js. Make it a compact header row that wraps below the heading on narrow screens; no action button may stretch full width. Remove the normal bottom submit and detached Unpublish action area.

- [ ] **Step 4: Verify green**

Run: pytest tests/test_ui_pages.py -k publication -v && node --test tests/markdown_editor.test.js

Expected: PASS.

- [ ] **Step 5: Regression and commit**

Run: pytest tests/test_admin_posts.py tests/test_ui_pages.py -v && node --test tests/markdown_editor.test.js tests/theme.test.js

Expected: PASS.

~~~bash
git add app/templates/admin/posts/form.html app/static/markdown-editor.js app/static/style.css tests/test_ui_pages.py tests/markdown_editor.test.js
git commit -m "feat: move article publication controls to header"
~~~

