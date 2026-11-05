import pytest
from lxml import html as lxml_html

from app import db
from app.models import Page, Post, PostComment
from tests.conftest import login


def admin_get(client, users, path):
    login(client, 'admin')
    return client.get(path)


def test_admin_navigation_has_no_module_data_group(client, users):
    response = admin_get(client, users, '/admin/')
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '模块数据' not in text
    assert '友情链接' not in text
    assert 'Todo 数据' not in text
    assert '评论与留言' not in text
    assert '>评论<' in text


def test_admin_module_routes_are_gone(client, users):
    login(client, 'admin')
    for path in ('/admin/todos', '/admin/movies', '/admin/links'):
        assert client.get(path).status_code == 404, path


def test_admin_comments_page_lists_only_article_comments(client, application, users):
    with application.app_context():
        db.session.add(PostComment(
            name='Reader', email='r@example.com', body='Nice article',
            post=db.session.get(Post, users['post'])))
        db.session.commit()
    response = admin_get(client, users, '/admin/comments')
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert response.status_code == 200
    assert 'Nice article' in page.text_content()
    assert '留言' not in [h.text_content() for h in page.xpath('//h2')]
    assert client.post('/admin/comments/guestbook/1/delete').status_code in (404, 405)


def test_admin_page_list_has_no_module_filter(client, users):
    login(client, 'admin')
    assert client.get('/admin/pages?filter=module').status_code == 400
    text = client.get('/admin/pages').get_data(as_text=True)
    assert '模块页' not in text


@pytest.mark.parametrize('path', ['/movie', '/todo', '/links', '/comment'])
def test_old_module_urls_are_not_found(client, path):
    assert client.get(path).status_code == 404


def test_old_module_urls_reject_post(client):
    assert client.post('/comment', data={'name': 'a'}).status_code in (404, 405)


def test_leftover_module_page_row_is_not_served(client, application):
    with application.app_context():
        db.session.add(Page(title='Todo', slug='todo', kind='module',
                            module_key='todo', is_published=True,
                            show_in_nav=True))
        db.session.commit()
    assert client.get('/todo').status_code == 404


def test_custom_page_can_reuse_a_former_module_slug(client, application):
    with application.app_context():
        db.session.add(Page(title='友链', slug='links', kind='content',
                            body='<p>My friends</p>', is_published=True,
                            show_in_nav=True))
        db.session.commit()
    response = client.get('/links')
    assert response.status_code == 200
    assert 'My friends' in response.get_data(as_text=True)


def test_removed_models_and_forms_are_gone():
    import app.admin.forms as admin_forms
    import app.forms as forms
    import app.models as models
    for name in ('Link', 'Movie', 'Todo', 'Comment'):
        assert not hasattr(models, name), name
    for name in ('CommentForm', 'TodoForm', 'TodoEditForm', 'LinkForm'):
        assert not hasattr(forms, name), name
    for name in ('TodoAdminForm', 'MovieAdminForm', 'LinkAdminForm'):
        assert not hasattr(admin_forms, name), name
    assert hasattr(models, 'PostComment')
    assert hasattr(forms, 'PostCommentForm')


def test_pages_can_only_be_content_pages(application):
    import app.pages as pages
    from app.pages import PageValidationError, save_page
    assert not hasattr(pages, 'MODULE_KEYS')
    assert not hasattr(pages, 'PAGE_MODULE')
    with application.app_context():
        with pytest.raises(PageValidationError):
            save_page(Page(), {'title': 'Todo', 'slug': 'todo-page',
                               'kind': 'module', 'module_key': 'todo'})
        with pytest.raises(PageValidationError):
            save_page(Page(), {'title': 'X', 'slug': 'x-page',
                               'kind': 'content', 'module_key': 'todo'})
        page = save_page(Page(), {'title': 'Notes', 'slug': 'notes',
                                  'body': 'hello'})
        assert (page.kind, page.module_key) == ('content', None)
