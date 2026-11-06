from lxml import html

from app import db
from app.models import Post, PostDraft, PostRevision
from tests.conftest import login


def preview(client, **fields):
    return client.post('/admin/posts/preview', data=fields)


def test_preview_renders_unsaved_markdown_like_the_article_page(client, application, users):
    login(client, 'author')

    response = preview(client, title='草稿标题', body='## 第一节\n\n正文\n\n## 第二节\n\n## 第三节')
    page = html.fromstring(response.data)

    assert response.status_code == 200
    assert page.xpath('//div[contains(@class,"article-body")]/h1/text()') == ['草稿标题']
    assert page.xpath('//div[contains(@class,"article-body")]/h2/text()') == ['第一节', '第二节', '第三节']
    assert page.xpath('//header[contains(@class,"article-header")]//*[contains(@class,"article-header__author")]/text()') == ['author']
    assert page.xpath('//nav[contains(@class,"article-toc")]')
    assert page.xpath('//div[contains(@class,"preview-bar")]')


def test_preview_has_no_reader_actions_and_is_not_indexable_or_cached(client, users):
    login(client, 'author')

    response = preview(client, title='T', body='body')
    page = html.fromstring(response.data)

    assert not page.xpath('//*[@id="post-actions"] | //form[@data-like-form] | //*[@data-qr-share]')
    assert not page.xpath('//section[@id="comments"]')
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'noindex' in response.headers['X-Robots-Tag']
    assert page.xpath('//meta[@name="robots"]/@content') == ['noindex, nofollow']


def test_preview_saves_nothing(client, application, users):
    login(client, 'author')

    preview(client, title='Never stored', body='text')

    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Post)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(PostDraft)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(PostRevision)) == 0


def test_preview_sanitizes_like_the_published_page(client, users):
    login(client, 'author')

    response = preview(client, title='<b>x</b>',
                       body='<script>alert(1)</script><img src=x onerror=alert(2)>[a](javascript:alert(3))')
    text = response.get_data(as_text=True)

    assert '<script>alert' not in text
    assert 'onerror' not in text
    assert 'javascript:' not in text
    assert '<b>x</b>' not in text


def test_empty_title_shows_a_placeholder(client, users):
    login(client, 'author')

    page = html.fromstring(preview(client, title='  ', body='x').data)

    assert page.xpath('//div[contains(@class,"article-body")]/h1/text()') == ['无标题']


def test_preview_of_an_existing_legacy_html_post_keeps_its_format(client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body_format = 'html'
        db.session.commit()
    login(client, 'author')

    page = html.fromstring(preview(
        client, post_id=users['post'], title='Old', body='<p>kept <em>html</em></p>').data)

    assert page.xpath('//div[contains(@class,"article-body")]//em/text()') == ['html']


def test_new_post_preview_treats_the_text_as_markdown(client, users):
    login(client, 'author')

    page = html.fromstring(preview(client, title='T', body='*lean*').data)

    assert page.xpath('//div[contains(@class,"article-body")]//em/text()') == ['lean']


def test_member_cannot_preview_against_another_authors_post(client, users):
    login(client, 'other')

    assert preview(client, post_id=users['post'], title='T', body='x').status_code == 403


def test_guest_is_sent_to_login(client, users):
    response = preview(client, title='T', body='x')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_editor_has_a_preview_button_and_form_for_new_and_existing_posts(client, users):
    login(client, 'author')

    for path, expected_id in (('/admin/posts/new', ''), (f'/admin/posts/{users["post"]}/edit', str(users['post']))):
        page = html.fromstring(client.get(path).data)
        form = page.xpath('//form[@id="post-preview-form"]')[0]
        assert form.get('target') == '_blank'
        assert form.get('action') == '/admin/posts/preview'
        assert form.xpath('.//input[@name="post_id"]/@value') == [expected_id]
        assert page.xpath('//button[@data-post-preview]')[0].text_content().strip() == '预览'
        assert 'static/post-preview.js' in client.get(path).get_data(as_text=True)
