from pathlib import Path

from lxml import html as lxml_html

from app import db
from app.models import Post, PostDraft
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = '//*[@data-publication-controls]'


def controls(client, post_id):
    document = lxml_html.fromstring(
        client.get(f'/admin/posts/{post_id}/edit').get_data(as_text=True))
    return document.xpath(CONTROLS)[0]


def prepare(application, users, published, draft):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body_format = 'markdown'
        post.is_published = published
        if draft:
            post.draft = PostDraft(title='Draft', body='draft', category_id=1)
        db.session.commit()


def test_unpublished_draft_has_a_primary_publish_button(client, application, users):
    prepare(application, users, published=False, draft=True)
    login(client, 'author')
    area = controls(client, users['post'])

    button = area.xpath('.//form[contains(@action, "/publish")]//button[@data-publish]')[0]
    assert button.text_content().strip() == '发布'
    assert 'button--cta' in button.get('class')
    assert button.get('type') == 'submit'
    assert not area.xpath('.//input[@role="switch"]')
    assert not area.xpath('.//*[@data-unpublish]')


def test_published_article_can_be_unpublished_with_a_confirmation(
        client, application, users):
    prepare(application, users, published=True, draft=False)
    login(client, 'author')
    area = controls(client, users['post'])

    form = area.xpath('.//form[contains(@action, "/unpublish")]')[0]
    button = form.xpath('.//button[@data-unpublish]')[0]
    assert button.text_content().strip() == '取消公开'
    assert button.get('disabled') is None
    assert 'confirm(' in button.get('onclick')
    update = form.xpath('.//button[@data-publish-update]')[0]
    assert update.get('hidden') is not None
    assert update.get('formaction').endswith('/publish')
    assert not area.xpath('.//*[@data-publish]')
    assert not area.xpath('.//input[@role="switch"]')


def test_published_article_with_pending_changes_offers_publish_update(
        client, application, users):
    prepare(application, users, published=True, draft=True)
    login(client, 'author')
    area = controls(client, users['post'])

    unpublish = area.xpath('.//button[@data-unpublish]')[0]
    assert unpublish.get('disabled') is not None
    update = area.xpath('.//form[contains(@action, "/publish")]//button[@data-publish-update]')[0]
    assert update.get('hidden') is None
    assert update.text_content().strip() == '发布更新'
    assert 'button--cta' in update.get('class')
    assert '有未发布修改' in area.text_content()


def test_the_publication_switch_is_gone_everywhere():
    assert not (ROOT / 'app/static/publication-controls.js').exists()
    assert not (ROOT / 'tests/publication_controls.test.js').exists()
    css = (ROOT / 'app/static/style.css').read_text()
    assert 'publication-switch' not in css
    editor = (ROOT / 'app/static/markdown-editor.js').read_text()
    assert 'publication-switch' not in editor and 'role = \'switch\'' not in editor


def test_editor_form_declares_the_upload_url_once(client, application, users):
    prepare(application, users, published=True, draft=False)
    login(client, 'author')
    html = client.get(f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)
    assert html.count('data-image-upload-url') == 1


def list_rows(client):
    document = lxml_html.fromstring(
        client.get('/admin/posts').get_data(as_text=True))
    return document.xpath('//article[contains(@class, "admin-list__row")]')


def test_article_list_offers_publish_for_a_draft_and_returns_to_the_list(
        client, application, users):
    prepare(application, users, published=False, draft=True)
    login(client, 'author')
    row = list_rows(client)[0]

    button = row.xpath('.//form[contains(@action, "/publish")]//button')[0]
    assert button.text_content().strip() == '公开'
    response = client.post(f'/admin/posts/{users["post"]}/publish',
                           data={'next': 'list'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/posts')
    with application.app_context():
        assert db.session.get(Post, users['post']).is_published is True


def test_article_list_offers_unpublish_for_a_live_article(
        client, application, users):
    prepare(application, users, published=True, draft=False)
    login(client, 'author')
    row = list_rows(client)[0]

    assert row.xpath('.//form[contains(@action, "/unpublish")]//button')[0] \
        .text_content().strip() == '取消公开'
    response = client.post(f'/admin/posts/{users["post"]}/unpublish',
                           data={'next': 'list'})
    assert response.headers['Location'].endswith('/admin/posts')
    with application.app_context():
        assert db.session.get(Post, users['post']).is_published is False


def test_publication_actions_still_return_to_the_editor_by_default(
        client, application, users):
    prepare(application, users, published=True, draft=False)
    login(client, 'author')
    response = client.post(f'/admin/posts/{users["post"]}/unpublish')
    assert response.headers['Location'].endswith(
        f'/admin/posts/{users["post"]}/edit')


def test_article_list_preview_shows_the_pending_draft(client, application, users):
    prepare(application, users, published=True, draft=True)
    login(client, 'author')
    row = list_rows(client)[0]
    link = row.xpath('.//a[contains(@href, "/preview")]')[0]
    assert link.get('target') == '_blank'

    response = client.get(link.get('href'))
    assert response.status_code == 200
    assert 'Draft' in response.get_data(as_text=True)
    assert response.headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_article_list_preview_is_limited_to_the_owner(client, users):
    login(client, 'other')
    assert client.get(f'/admin/posts/{users["post"]}/preview').status_code == 403
