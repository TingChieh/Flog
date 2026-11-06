import hashlib

import pytest
from lxml import html as lxml_html

from app import db
from app.models import Category, Page, Post, PostDraft
from tests.conftest import login


@pytest.mark.parametrize('path', [
    '/about', '/categories', '/login',
])
def test_public_pages_render_in_the_shared_design(client, application, path):
    with application.app_context():
        if path == '/about':
            db.session.add(Page(
                title='About', slug='about', kind='content',
                body='<p>About</p>', is_published=True))
        db.session.commit()
    response = client.get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="site-nav"' in html
    assert 'class="site-footer"' in html
    expected_shell = 'form-shell' if path == '/login' else 'content-section'
    assert f'class="{expected_shell}' in html
    assert 'class="page-heading"' in html
    assert '<font' not in html
    assert 'style="display:inline' not in html


def test_search_results_use_editorial_rows(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '<p>Test result</p>'
        db.session.commit()

    response = client.get('/search?q=Test')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="editorial-list"' in html
    assert 'class="editorial-post"' in html
    assert '>Test<' in html
    assert '复制链接' not in html
    assert '生成二维码' not in html
    detail = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert '复制链接' not in detail
    assert '生成二维码' in detail


def test_empty_search_does_not_return_all_posts(client, users):
    response = client.get('/search?q=')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="editorial-post"' not in html
    assert '未找到结果。' in html


def test_search_treats_like_metacharacters_as_literals(
        client, application, users):
    with application.app_context():
        author_post = db.session.get(Post, users['post'])
        db.session.add(Post(
            title='Literal metacharacters', body='<p>100%_complete</p>',
            author=author_post.author, category=author_post.category,
            is_published=True))
        db.session.commit()

    for query in ('%', '_'):
        response = client.get('/search', query_string={'q': query})
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert html.count('class="editorial-post"') == 1
        assert 'Literal metacharacters' in html


def test_search_paginates_and_preserves_query(client, application, users):
    with application.app_context():
        author_post = db.session.get(Post, users['post'])
        db.session.add_all([
            Post(title=f'Match {number}', body='<p>pagination needle</p>',
                 author=author_post.author, category=author_post.category,
                 is_published=True)
            for number in range(application.config['POSTS_PER_PAGE'] + 1)
        ])
        db.session.commit()

    first_page = client.get('/search?q=pagination+needle')
    first_html = first_page.get_data(as_text=True)
    second_page = client.get('/search?q=pagination+needle&page=2')
    second_html = second_page.get_data(as_text=True)

    assert first_page.status_code == 200
    assert first_html.count('class="editorial-post"') == 10
    assert 'q=pagination+needle&amp;page=2' in first_html
    assert second_page.status_code == 200
    assert second_html.count('class="editorial-post"') == 1


def test_search_rejects_overlong_query(client, application):
    response = client.get('/search', query_string={
        'q': 'a' * (application.config['SEARCH_QUERY_MAX_LENGTH'] + 1),
    })

    assert response.status_code == 400


def test_markdown_post_excerpts_strip_rendered_markup(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '# Excerpt heading\n\n**Bold text** and [safe link](https://example.com)'
        post.body_format = 'markdown'
        db.session.commit()

    html = client.get('/').get_data(as_text=True)

    assert 'Excerpt heading' in html
    assert 'Bold text and safe link' in html
    assert '# Excerpt heading' not in html
    assert '**Bold text**' not in html
    assert '[safe link](https://example.com)' not in html


def test_invalid_login_uses_shared_field_error_presentation(client):
    response = client.post('/login', data={'username': '', 'password': ''})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert html.count('class="invalid-feedback"') >= 2
    assert 'form-control is-invalid' in html


def test_markdown_editor_assets_are_scoped_to_markdown_admin_forms(
        client, users):
    client.post('/login', data={'username': 'admin', 'password': 'password'})

    page_editor = client.get('/admin/pages/new').get_data(as_text=True)
    post_editor = client.get('/admin/posts/new').get_data(as_text=True)
    public = client.get('/').get_data(as_text=True)

    for editor in (page_editor, post_editor):
        assert 'data-markdown-editor' in editor
        assert 'data-image-upload-url="/upload"' in editor
        assert 'data-vditor-cdn="/static/vendor/vditor/4.0.1"' in editor
        assert '/static/vendor/vditor/4.0.1/dist/index.css' in editor
        assert '/static/vendor/vditor/4.0.1/dist/index.min.js' in editor
        assert '/static/markdown-editor.js' in editor
        for gone in ('easymde', 'dompurify', 'maxcdn', 'font-awesome',
                     'unpkg.com', 'cdn.jsdelivr.net/npm/vditor'):
            assert gone not in editor.lower(), gone
    assert '/static/vendor/vditor/' not in public
    post_page = lxml_html.fromstring(post_editor)
    assert [l.text_content() for l in post_page.xpath('//label[@for="post"]')] == ['正文']
    assert 'data-image-upload-url' not in public
    assert 'CKEDITOR' not in page_editor + post_editor + public


def test_post_editor_renders_autosave_data_and_keeps_server_forms(client, users):
    with client.application.app_context():
        post = db.session.get(Post, users['post'])
        post.body_format = 'markdown'
        db.session.commit()
    client.post('/login', data={'username': 'admin', 'password': 'password'})

    html = client.get(
        f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)

    assert f'data-post-id="{users["post"]}"' in html
    assert f'data-draft-url="/admin/posts/{users["post"]}/draft"' in html
    assert f'data-leave-url="/admin/posts/{users["post"]}/leave"' in html
    assert 'data-csrf-token=' in html
    assert 'data-draft-save-status' in html
    assert 'data-editor-sequence="0"' in html
    assert f'action="/admin/posts/{users["post"]}/edit"' in html
    assert 'method="post"' in html

    new_editor = client.get('/admin/posts/new').get_data(as_text=True)
    assert 'data-draft-url="/admin/posts/draft"' in new_editor
    assert 'data-leave-url="/admin/posts/draft/leave"' in new_editor


def test_published_article_with_draft_shows_header_switch_and_update_notice(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.draft = PostDraft(title='Changed', body='draft', category_id=1)
        db.session.commit()

    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(
        as_text=True)

    assert 'data-publication-controls' in html
    assert '<span class="publication-status" data-publication-status' in html
    assert '<span class="draft-save-status" data-draft-save-status' in html
    assert '有未发布修改' in html
    assert '发布更新' in html
    assert 'Unpublish' not in html


def test_legacy_post_editor_has_explicit_publication_buttons(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body_format = 'html'
        db.session.commit()

    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(
        as_text=True)

    assert 'publication-controls.js' not in html
    assert 'data-unpublish' in html
    assert 'role="switch"' not in html


def test_unpublished_draft_keeps_initial_save_state_mutable(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = False
        post.draft = PostDraft(title='Draft', body='draft', category_id=1)
        db.session.commit()

    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(
        as_text=True)
    publication_status = html.split('data-publication-status', 1)[1].split(
        '</span>', 1)[0]
    draft_save_status = html.split('data-draft-save-status', 1)[1].split(
        '</span>', 1)[0]

    assert '草稿已保存' not in publication_status
    assert '草稿已保存' in draft_save_status
    assert 'data-publish' in html
    assert 'role="switch"' not in html


def test_new_post_starts_without_a_publish_button(client, users):
    login(client, 'author')
    html = client.get('/admin/posts/new').get_data(as_text=True)

    assert 'data-publication-state="new"' in html
    assert 'data-publish' not in html
    assert 'data-unpublish' not in html


def test_published_article_without_draft_hides_update_action_with_css(
        client, users):
    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(
        as_text=True)
    css = client.get('/static/style.css').get_data(as_text=True)

    assert 'data-publish-update hidden' in html
    assert '.publication-controls [hidden] {\n    display: none;' in css


@pytest.mark.parametrize(('asset_path', 'expected_sha256'), [
    (
        '/static/vendor/vditor/4.0.1/dist/index.min.js',
        'aac93a3647a200b324dbb40734c173893205fe2ed7330336dd376582d33a04cd',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/index.css',
        'c6e693e24d3c0b472b435d48d9baff62bee62d13f5265723265256e73f310dba',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/js/lute/lute.min.js',
        '53b61b051a3dfd9ee5a5010c873233679e139d8e62c49da08b4c2f2c195587cb',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/js/i18n/zh_CN.js',
        '6a0c07e6c40f934715b0bebcea20bdbbf20c34ba70ab9ea8d22336a1c47ab09c',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/js/icons/ant.js',
        'a91e14e09dcd7b99f49b7b8dcc6301fed6774d62547fcf4e971757aa3a802c33',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/css/content-theme/light.css',
        '9848c5a4d637f1803859b18ece4aa9df17d03a706f3d6416ba729c357d4ee360',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/js/highlight.js/styles/github.min.css',
        '5f5db2458549f8b86de973acd7d5d7b26ff5413c07f26aa3f42b054b943c3448',
    ),
    (
        '/static/vendor/vditor/4.0.1/dist/css/content-theme/dark.css',
        '79529741d2e94b6dd3dd72bc660f91497127188c8d2aa5bffd28fdbb60b9c7c9',
    ),
])
def test_markdown_editor_vendor_assets_match_published_packages(
        client, asset_path, expected_sha256):
    response = client.get(asset_path)

    assert response.status_code == 200
    assert hashlib.sha256(response.data).hexdigest() == expected_sha256


def test_legacy_article_and_page_forms_preserve_html_source_without_editor(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '<p>Legacy article source</p>'
        post.body_format = 'html'
        page = Page(
            title='Legacy page', slug='legacy-page', kind='content',
            body='<p>Legacy page source</p>', body_format='html',
            is_published=True,
        )
        db.session.add(page)
        db.session.commit()
        page_id = page.id

    client.post('/login', data={'username': 'admin', 'password': 'password'})
    article = client.get(
        f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)
    page = client.get(
        f'/admin/pages/{page_id}/edit').get_data(as_text=True)

    for html in (article, page):
        assert '旧版 HTML 内容' in html
        assert 'data-image-upload-url' not in html
        assert 'data-markdown-editor' not in html
        assert '/static/vendor/vditor/' not in html
        assert 'data-vditor-cdn' not in html
        assert '/static/markdown-editor.js' not in html
    assert '&lt;p&gt;Legacy article source&lt;/p&gt;' in article
    assert '&lt;p&gt;Legacy page source&lt;/p&gt;' in page


def test_comment_textarea_does_not_opt_in_to_markdown_editor(
        client, application, users):
    article = client.get(f'/post/{users["post"]}').get_data(as_text=True)

    assert 'data-markdown-editor' not in article
    assert 'data-image-upload-url' not in article


def test_category_management_controls_exist_only_in_admin_workspace(
    client, application, users):
    with application.app_context():
        category_id = Category.query.first().id

    anonymous = client.get('/categories').get_data(as_text=True)
    assert 'action="/categories"' not in anonymous
    assert f'/category/{category_id}/edit' not in anonymous

    client.post('/login', data={'username': 'author', 'password': 'password'})
    member = client.get('/categories').get_data(as_text=True)
    assert 'action="/categories"' not in member
    assert f'/category/{category_id}/edit' not in member

    client.post('/logout')
    client.post('/login', data={'username': 'admin', 'password': 'password'})
    public_admin = client.get('/categories').get_data(as_text=True)
    assert 'action="/categories"' not in public_admin
    assert f'/category/{category_id}/edit' not in public_admin
    admin = client.get('/admin/categories').get_data(as_text=True)
    assert f'/admin/categories/{category_id}/edit' in admin


def test_authenticated_member_sees_no_public_about_controls(
        client, application, users):
    with application.app_context():
        db.session.add(Page(
            title='About', slug='about', kind='content', body='<p>About</p>',
            is_published=True, show_in_nav=True, nav_order=5))
        db.session.commit()

    client.post('/login', data={'username': 'author', 'password': 'password'})

    about = client.get('/about').get_data(as_text=True)

    assert 'href="/about/edit"' not in about


def test_search_count_includes_all_pages_and_only_published_posts(client, application, users):
    with application.app_context():
        author = db.session.get(Post, users['post']).author
        db.session.add_all([Post(title=f'Countneedle {i}', body='body', author=author,
                                 is_published=True) for i in range(12)])
        db.session.add(Post(title='Countneedle draft', body='body', author=author,
                            is_published=False))
        db.session.commit()
    html = client.get('/search?q=Countneedle&page=2', headers={'Accept-Language': 'en'}).get_data(as_text=True)
    assert '12 个结果' in html
