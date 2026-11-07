from lxml import html as lxml_html

from app import db
from app.models import Page, Post, PostComment
from tests.conftest import login


def page_for(client, path):
    return lxml_html.fromstring(client.get(path).get_data(as_text=True))


def add_comment(post_id=None, page_id=None, **values):
    values.setdefault('name', 'Old')
    values.setdefault('email', 'old@example.com')
    values.setdefault('body', 'earlier')
    comment = PostComment(post_id=post_id, page_id=page_id, **values)
    db.session.add(comment)
    db.session.commit()
    return comment.id


def post_comment(client, post_id, **data):
    data.setdefault('name', 'Reader')
    data.setdefault('email', 'reader@example.com')
    data.setdefault('body', 'Nice post')
    return client.post(f'/post/{post_id}', data=data, follow_redirects=True)


def comment_texts(page):
    return [c.text_content().strip()
            for c in page.xpath('//div[@class="post-comment__text"]')]


def make_page(**values):
    page = Page(title='About', slug='about', kind='content',
                is_published=True, body='hello', body_format='markdown',
                **values)
    db.session.add(page)
    db.session.commit()
    return page.id


def test_first_comment_waits_for_review_and_says_so(client, application, users):
    response = post_comment(client, users['post'])

    assert '审核通过后显示' in response.get_data(as_text=True)
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert comment_texts(page) == []
    with application.app_context():
        assert db.session.scalar(db.select(PostComment)).status == 'pending'


def test_trusted_email_is_published_at_once(client, application, users):
    with application.app_context():
        add_comment(post_id=users['post'], email='reader@example.com')
    response = post_comment(client, users['post'], body='Second **one**')

    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert 'Second one' in ' '.join(comment_texts(page))
    assert page.xpath('//div[@class="post-comment__text"]//strong')
    assert 'reader@example.com' not in response.get_data(as_text=True)


def test_site_owner_comment_is_published_with_a_badge(client, application, users):
    login(client, 'admin')
    response = post_comment(client, users['post'], name='admin',
                            email='admin@example.com', body='From the owner')
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert 'From the owner' in ' '.join(comment_texts(page))
    assert page.xpath('//span[@class="comment-badge"]')


def test_raw_html_in_a_comment_is_shown_as_text(client, application, users):
    with application.app_context():
        add_comment(post_id=users['post'], email='reader@example.com')
    response = post_comment(client, users['post'], body='<script>alert(1)</script>Hello')
    body = response.get_data(as_text=True)
    assert '<script>alert(1)' not in body
    assert '&lt;script&gt;alert(1)&lt;/script&gt;Hello' in body


def test_count_ignores_pending_comments(client, application, users):
    with application.app_context():
        add_comment(post_id=users['post'])
        add_comment(post_id=users['post'], status='pending')
    page = page_for(client, f'/post/{users["post"]}')
    assert page.xpath('string(//section[@id="comments"]//header/span)') == '1'


def test_reply_is_nested_and_a_reply_to_a_reply_joins_the_thread(
        client, application, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], email='reader@example.com',
                          name='Top', body='top comment')
    post_comment(client, users['post'], body='first reply', parent_id=str(top))
    with application.app_context():
        reply = db.session.scalar(
            db.select(PostComment).where(PostComment.parent_id == top))
        reply_id = reply.id
        reply_name = reply.name
    post_comment(client, users['post'], body='second reply', parent_id=str(reply_id))

    page = page_for(client, f'/post/{users["post"]}')
    replies = page.xpath(f'//article[@id="comment-{top}"]/following-sibling::div[@class="post-comment__replies"][1]//article')
    assert len(replies) == 2
    assert f'@{reply_name} second reply' in replies[1].text_content()


def test_reply_link_without_javascript_prefills_the_form(client, application, users):
    with application.app_context():
        top = add_comment(post_id=users['post'], name='Top')
    page = page_for(client, f'/post/{users["post"]}?reply={top}')
    assert page.xpath('//input[@name="parent_id"]/@value') == [str(top)]
    note = page.xpath('//*[@data-reply-note]')[0]
    assert note.get('hidden') is None
    assert 'Top' in note.text_content()

    plain = page_for(client, f'/post/{users["post"]}')
    assert plain.xpath('//*[@data-reply-note]')[0].get('hidden') is not None
    assert plain.xpath('//input[@name="parent_id"]/@value') == ['']


def test_reply_to_an_unknown_comment_shows_an_error(client, application, users):
    response = post_comment(client, users['post'], parent_id='9999')
    assert '要回复的评论不存在' in response.get_data(as_text=True)
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_closed_post_refuses_comments_and_keeps_old_ones_read_only(
        client, application, users):
    with application.app_context():
        add_comment(post_id=users['post'], body='still here')
        db.session.get(Post, users['post']).comments_enabled = False
        db.session.commit()

    response = client.post(f'/post/{users["post"]}', data={
        'name': 'R', 'email': 'r@example.com', 'body': 'late'})
    assert response.status_code == 403

    page = page_for(client, f'/post/{users["post"]}')
    assert comment_texts(page) == ['still here']
    assert '评论已关闭' in page.xpath('string(//section[@id="comments"])')
    assert not page.xpath('//form[contains(@class, "comment-form")]')
    assert not page.xpath('//a[@data-reply-link]')


def test_closed_post_without_comments_has_no_comment_section(
        client, application, users):
    with application.app_context():
        db.session.get(Post, users['post']).comments_enabled = False
        db.session.commit()
    assert not page_for(client, f'/post/{users["post"]}').xpath(
        '//section[@id="comments"]')


def test_honeypot_submission_is_dropped_quietly(client, application, users):
    response = post_comment(client, users['post'], website='http://spam.example')
    assert response.status_code == 200
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_form_carries_a_honeypot_and_a_token(client, users):
    page = page_for(client, f'/post/{users["post"]}')
    assert page.xpath('//input[@name="website"]')
    assert page.xpath('//input[@name="form_token"]/@value')[0]


def test_page_is_closed_until_comments_are_switched_on(client, application, users):
    with application.app_context():
        make_page()
    assert not page_for(client, '/about').xpath('//section[@id="comments"]')
    assert client.post('/about', data={
        'name': 'R', 'email': 'r@example.com', 'body': 'hi'}).status_code == 403


def test_comment_on_a_page_end_to_end(client, application, users):
    with application.app_context():
        page_id = make_page(comments_enabled=True)
        add_comment(page_id=page_id, email='reader@example.com', body='earlier')

    assert page_for(client, '/about').xpath('//form[contains(@class, "comment-form")]')
    response = client.post('/about', data={
        'name': 'Reader', 'email': 'reader@example.com', 'body': 'On a page'},
        follow_redirects=True)
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert comment_texts(page) == ['earlier', 'On a page']
    with application.app_context():
        assert db.session.scalars(db.select(PostComment).order_by(
            PostComment.id)).all()[-1].page_id == page_id


def test_posting_to_an_unknown_slug_is_not_found(client, application, users):
    assert client.post('/no-such-page', data={}).status_code == 404


def test_comment_form_has_an_emoji_button_and_loads_the_picker(client, users):
    page = page_for(client, f'/post/{users["post"]}')
    button = page.xpath('//form[contains(@class, "comment-form")]//button[@data-emoji-for]')
    assert [b.get('data-emoji-for') for b in button] == ['#body']
    assert page.xpath('//textarea[@id="body"]')
    html = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert 'emoji-data.js' in html and 'emoji-picker.js' in html


def test_closed_comments_do_not_load_the_picker(client, application, users):
    with application.app_context():
        add_comment(post_id=users['post'])
        db.session.get(Post, users['post']).comments_enabled = False
        db.session.commit()
    html = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert 'emoji-picker.js' not in html


def test_comment_form_has_an_unchecked_notify_box(client, users):
    page = page_for(client, f'/post/{users["post"]}')
    boxes = page.xpath('//form[@data-comment-form]//input[@type="checkbox"][@name="notify"]')
    assert len(boxes) == 1
    assert boxes[0].get('checked') is None


def test_notify_box_is_remembered(client, application, users):
    post_comment(client, users['post'], notify='y')
    with application.app_context():
        assert db.session.scalar(db.select(PostComment)).notify_replies is True


def test_comment_without_notify_box_stays_silent(client, application, users):
    post_comment(client, users['post'])
    with application.app_context():
        assert db.session.scalar(db.select(PostComment)).notify_replies is False
