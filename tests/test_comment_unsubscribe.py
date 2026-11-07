from lxml import html as lxml_html

from app import db
from app.comment_mail import (email_from_unsubscribe_token, stop_notifications,
                              unsubscribe_token, unsubscribe_url)
from app.models import PostComment


def add_comment(post_id, email, notify=True, **values):
    comment = PostComment(post_id=post_id, name='Reader', email=email,
                          body='hello', notify_replies=notify, **values)
    db.session.add(comment)
    db.session.commit()
    return comment.id


def notify_flags(*ids):
    return [db.session.get(PostComment, i).notify_replies for i in ids]


def test_token_round_trip_lowercases_the_address(application):
    token = unsubscribe_token(' Reader@Example.com ')
    assert email_from_unsubscribe_token(token) == 'reader@example.com'


def test_garbage_and_foreign_tokens_are_refused(application):
    assert email_from_unsubscribe_token('nope') is None
    assert email_from_unsubscribe_token('') is None


def test_unsubscribe_url_is_absolute(application):
    with application.test_request_context():
        url = unsubscribe_url('reader@example.com')
    assert url.startswith('http://localhost/comments/unsubscribe/')


def test_stop_notifications_matches_the_address_case_insensitively(
        application, users):
    mine = add_comment(users['post'], 'Reader@Example.com')
    mine_too = add_comment(users['post'], 'reader@example.com')
    other = add_comment(users['post'], 'someone@example.com')
    assert stop_notifications('READER@example.com') == 2
    db.session.commit()
    assert notify_flags(mine, mine_too, other) == [False, False, True]


def test_get_asks_for_confirmation_and_changes_nothing(
        client, application, users):
    comment_id = add_comment(users['post'], 'reader@example.com')
    token = unsubscribe_token('reader@example.com')
    response = client.get(f'/comments/unsubscribe/{token}')
    assert response.status_code == 200
    page = lxml_html.fromstring(response.get_data(as_text=True))
    assert 'reader@example.com' in page.text_content()
    assert page.xpath('//section[contains(@class, "form-shell")]//input[@type="submit"]')
    assert notify_flags(comment_id) == [True]


def test_post_switches_off_every_comment_of_that_address(
        client, application, users):
    first = add_comment(users['post'], 'reader@example.com')
    second = add_comment(users['post'], 'reader@example.com')
    other = add_comment(users['post'], 'someone@example.com')
    token = unsubscribe_token('reader@example.com')
    response = client.post(f'/comments/unsubscribe/{token}',
                           follow_redirects=True)
    assert '已退订' in response.get_data(as_text=True)
    db.session.expire_all()
    assert notify_flags(first, second, other) == [False, False, True]


def test_bad_token_is_a_404(client, application):
    assert client.get('/comments/unsubscribe/nope').status_code == 404
    assert client.post('/comments/unsubscribe/nope').status_code == 404
