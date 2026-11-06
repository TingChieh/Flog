from lxml import html as lxml_html

from app import db
from app.models import Page, Post, PostComment
from tests.conftest import login


def seed(application, users):
    with application.app_context():
        page = Page(title='About', slug='about', kind='content',
                    is_published=True, comments_enabled=True)
        db.session.add(page)
        db.session.commit()
        rows = {
            'ok': PostComment(post_id=users['post'], name='Ann',
                              email='ann@example.com', body='approved one'),
            'wait': PostComment(post_id=users['post'], name='Bob',
                                email='bob@example.com', body='needs review',
                                status='pending'),
            'on_page': PostComment(page_id=page.id, name='Cy',
                                   email='cy@example.com', body='about page words'),
        }
        db.session.add_all(rows.values())
        db.session.commit()
        return {key: row.id for key, row in rows.items()} | {'page': page.id}


def listing(client, query=''):
    response = client.get(f'/admin/comments{query}')
    assert response.status_code == 200
    return lxml_html.fromstring(response.get_data(as_text=True))


def row_names(page):
    return [row.xpath('string(.//strong[@class="comment-author"])')
            for row in page.xpath('//article[@data-comment-row]')]


def test_default_view_lists_everything_with_tab_counts(client, application, users):
    seed(application, users)
    login(client, 'admin')
    page = listing(client)
    assert sorted(row_names(page)) == ['Ann', 'Bob', 'Cy']
    tabs = [a.text_content().strip() for a in page.xpath('//nav[@data-comment-tabs]//a')]
    assert tabs == ['待审核 (1)', '已通过 (2)', '全部 (3)']


def test_status_tabs_filter(client, application, users):
    seed(application, users)
    login(client, 'admin')
    assert row_names(listing(client, '?status=pending')) == ['Bob']
    assert sorted(row_names(listing(client, '?status=approved'))) == ['Ann', 'Cy']
    assert client.get('/admin/comments?status=nope').status_code == 400


def test_search_matches_name_email_and_body(client, application, users):
    seed(application, users)
    login(client, 'admin')
    assert row_names(listing(client, '?q=review')) == ['Bob']
    assert row_names(listing(client, '?q=cy@example')) == ['Cy']
    assert row_names(listing(client, '?q=Ann')) == ['Ann']


def test_filter_by_post_or_page(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    assert sorted(row_names(listing(client, f'?target=post:{users["post"]}'))) == ['Ann', 'Bob']
    assert row_names(listing(client, f'?target=page:{ids["page"]}')) == ['Cy']
    assert client.get('/admin/comments?target=garbage').status_code == 400


def test_rows_say_where_each_comment_lives(client, application, users):
    seed(application, users)
    login(client, 'admin')
    page = listing(client)
    targets = page.xpath('//article[@data-comment-row]//a[@data-comment-target]')
    assert sorted(a.text_content().strip() for a in targets) == ['About', 'Test', 'Test']
    assert any(a.get('href') == '/about' for a in targets)


def test_approve_one_comment(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    assert client.post(f'/admin/comments/{ids["wait"]}/approve').status_code == 302
    with application.app_context():
        assert db.session.get(PostComment, ids['wait']).status == 'approved'


def test_delete_one_comment_takes_its_replies_along(client, application, users):
    ids = seed(application, users)
    with application.app_context():
        reply = PostComment(post_id=users['post'], parent_id=ids['ok'],
                            name='Re', email='re@example.com', body='reply')
        db.session.add(reply)
        db.session.commit()
    login(client, 'admin')
    client.post(f'/admin/comments/posts/{ids["ok"]}/delete', data={'confirm': 'y'})
    with application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 2


def test_bulk_approve_and_delete(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    client.post('/admin/comments/bulk', data={
        'action': 'approve', 'ids': [str(ids['wait'])]})
    with application.app_context():
        assert db.session.get(PostComment, ids['wait']).status == 'approved'

    client.post('/admin/comments/bulk', data={
        'action': 'delete', 'ids': [str(ids['ok']), str(ids['on_page'])]})
    with application.app_context():
        left = db.session.scalars(db.select(PostComment.id)).all()
        assert left == [ids['wait']]


def test_bulk_rejects_unknown_actions_and_bad_ids(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    assert client.post('/admin/comments/bulk', data={
        'action': 'burn', 'ids': [str(ids['ok'])]}).status_code == 400
    assert client.post('/admin/comments/bulk', data={
        'action': 'delete', 'ids': ['abc']}).status_code == 400


def test_admin_reply_is_published_under_the_comment(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    client.post(f'/admin/comments/{ids["ok"]}/reply', data={'body': 'Thanks!'})
    with application.app_context():
        reply = db.session.scalar(db.select(PostComment).where(
            PostComment.parent_id == ids['ok']))
        assert reply.status == 'approved'
        assert reply.body == 'Thanks!'
        assert reply.user_id == users['admin']
        assert reply.name == 'admin'


def test_admin_cannot_reply_where_comments_are_closed(client, application, users):
    ids = seed(application, users)
    with application.app_context():
        db.session.get(Post, users['post']).comments_enabled = False
        db.session.commit()
    login(client, 'admin')
    response = client.post(f'/admin/comments/{ids["ok"]}/reply', data={'body': 'Hi'})
    assert response.status_code == 302
    with application.app_context():
        assert db.session.scalar(db.select(PostComment).where(
            PostComment.parent_id == ids['ok'])) is None


def test_admin_cannot_reply_to_a_pending_comment(client, application, users):
    ids = seed(application, users)
    login(client, 'admin')
    client.post(f'/admin/comments/{ids["wait"]}/reply', data={'body': 'Hi'})
    with application.app_context():
        assert db.session.scalar(db.select(PostComment).where(
            PostComment.parent_id == ids['wait'])) is None


def test_comment_actions_are_admin_only(client, application, users):
    ids = seed(application, users)
    login(client, 'author')
    for path in (f'/admin/comments/{ids["wait"]}/approve',
                 f'/admin/comments/{ids["wait"]}/reply',
                 '/admin/comments/bulk'):
        assert client.post(path, data={'body': 'x'}).status_code in (302, 403, 404)
    with application.app_context():
        assert db.session.get(PostComment, ids['wait']).status == 'pending'


def test_dashboard_shows_how_many_are_waiting(client, application, users):
    seed(application, users)
    login(client, 'admin')
    dashboard = client.get('/admin/').get_data(as_text=True)
    assert '3 / 待审 1' in dashboard
