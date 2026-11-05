from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import sqlalchemy as sa
import pytest
from werkzeug.exceptions import Forbidden

from app import db
from app.models import (Category, Post, PostDraft, PostRevision, User,
                        get_site_settings)
from app.post_drafts import (
    DraftValues,
    PostDraftError,
    discard_draft,
    publish_draft,
    restore_revision,
    save_draft,
    save_editor_draft,
    snapshot_draft,
    trim_all_post_revisions,
    unpublish_post,
)
from tests.conftest import login


def test_editor_cas_rejects_a_save_with_a_stale_session_snapshot(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_editor_draft(actor, post, DraftValues('Initial', 'initial', 1), 1)
        db.session.commit()
        assert post.draft.body == 'initial'
        with application.app_context():
            newer_actor = db.session.get(User, users['author'])
            newer_post = db.session.get(Post, users['post'])
            save_editor_draft(newer_actor, newer_post,
                              DraftValues('Newer', 'newer', 1), 3)
            db.session.commit()
        _, applied = save_editor_draft(
            actor, post, DraftValues('Stale', 'stale', 1), 2)
        db.session.commit()
        db.session.expire_all()
        assert applied is False
        assert post.draft.body == 'newer'


@pytest.fixture()
def concurrent_database(application, users, tmp_path):
    engine = sa.create_engine(f'sqlite:///{tmp_path / "concurrency.db"}')
    with application.app_context():
        original = db.engine
        db.session.remove()
        db.metadata.create_all(engine)
        with original.connect() as source, engine.begin() as target:
            for table in db.metadata.sorted_tables:
                rows = source.execute(sa.select(table)).mappings().all()
                if rows:
                    target.execute(table.insert(), [dict(row) for row in rows])
        db.engines[None] = engine
        try:
            yield engine
        finally:
            db.session.remove()
            db.engines[None] = original
            engine.dispose()


def test_keyed_leave_keeps_creation_uncommitted_until_snapshot(
        client, application, users, concurrent_database, monkeypatch):
    from app.admin import posts as post_routes

    snapshot = post_routes.snapshot_draft
    visible_during_snapshot = []

    def observe_then_snapshot(actor, post_id):
        with concurrent_database.connect() as observer:
            visible_during_snapshot.append(observer.scalar(sa.select(Post.id).where(
                Post.editor_session_key == 'atomic-create')))
        return snapshot(actor, post_id)

    monkeypatch.setattr(post_routes, 'snapshot_draft', observe_then_snapshot)
    login(client, 'author')
    response = client.post('/admin/posts/draft/leave', headers={
        'X-Draft-Key': 'atomic-create', 'X-Draft-Sequence': '1',
        'X-Draft-Generation': '0'}, json={
            'title': 'Atomic', 'body': 'atomic', 'category_id': 1})
    assert response.status_code == 201
    assert visible_during_snapshot == [None]
    with concurrent_database.connect() as observer:
        assert observer.scalar(sa.select(PostRevision.post_id)) == response.json['post_id']


def test_unpublish_preserves_a_draft_created_by_an_overlapping_save(
        application, users, concurrent_database):
    paused = Event()
    resume = Event()

    def pause_unpublish_write(connection, cursor, statement, parameters, context, many):
        if (current_thread().name.startswith('unpublish') and (
                statement.startswith('INSERT INTO post_draft ')
                or statement.startswith('UPDATE post SET draft_generation'))):
            paused.set()
            assert resume.wait(5), 'overlapping save did not complete'

    def unpublish_request():
        with application.test_client() as client:
            login(client, 'author')
            return client.post(f'/admin/posts/{users["post"]}/unpublish')

    sa.event.listen(concurrent_database, 'before_cursor_execute', pause_unpublish_write)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='unpublish') as pool:
            pending = pool.submit(unpublish_request)
            try:
                assert paused.wait(5), 'unpublish did not reach its first draft write'
                with application.app_context():
                    actor = db.session.get(User, users['author'])
                    post = db.session.get(Post, users['post'])
                    save_editor_draft(actor, post, DraftValues('Latest', 'latest', 1), 1)
                    db.session.commit()
            finally:
                resume.set()
            assert pending.result(timeout=5).status_code == 302
    finally:
        sa.event.remove(concurrent_database, 'before_cursor_execute', pause_unpublish_write)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.is_published is False
        assert post.draft.body == 'latest'
        assert post.draft_generation == 1


@pytest.mark.parametrize('publish_winner', [False, True])
def test_overlapping_initial_creates_reuse_the_unique_key_winner(
        application, users, concurrent_database, publish_winner):
    paused = Event()
    resume = Event()
    headers = {'X-Draft-Key': 'creation-race', 'X-Draft-Generation': '0'}

    def pause_older_insert(connection, cursor, statement, parameters, context, many):
        if (current_thread().name.startswith('older-create')
                and statement.startswith('INSERT INTO post (')):
            paused.set()
            assert resume.wait(5), 'winning create did not complete'

    def older_create():
        with application.test_client() as client:
            login(client, 'author')
            return client.post('/admin/posts/draft', headers={
                **headers, 'X-Draft-Sequence': '1'}, json={
                    'title': 'Stale', 'body': 'stale', 'category_id': 1})

    sa.event.listen(concurrent_database, 'before_cursor_execute', pause_older_insert)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='older-create') as pool:
            pending = pool.submit(older_create)
            try:
                assert paused.wait(5), 'older create did not reach its insert'
                with application.test_client() as client:
                    login(client, 'author')
                    winner = client.post('/admin/posts/draft/leave', headers={
                        **headers, 'X-Draft-Sequence': '2'}, json={
                            'title': 'Latest', 'body': 'latest', 'category_id': 1})
                    assert winner.status_code == 201
                    post_id = winner.json['post_id']
                    if publish_winner:
                        assert client.post(f'/admin/posts/{post_id}/publish').status_code == 302
            finally:
                resume.set()
            response = pending.result(timeout=5)
            assert response.status_code == (409 if publish_winner else 201)
            if not publish_winner:
                assert response.json['post_id'] == post_id
                assert response.json['applied'] is False
    finally:
        sa.event.remove(concurrent_database, 'before_cursor_execute', pause_older_insert)
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count(Post.id)).where(
            Post.editor_session_key == 'creation-race')) == 1
        post = db.session.get(Post, post_id)
        if publish_winner:
            assert post.draft is None
            assert post.body == 'latest'
        else:
            assert post.draft.body == 'latest'
        assert db.session.scalar(sa.select(sa.func.count(PostRevision.id)).where(
            PostRevision.post_id == post_id)) == 1


@pytest.mark.parametrize('winner', ['save', 'publish', 'discard', 'restore', 'unpublish'])
def test_overlapping_save_is_fenced_at_the_database_write(
        application, users, concurrent_database, winner):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_editor_draft(actor, post, DraftValues('Initial', 'initial', 1), 1)
        revision = snapshot_draft(actor, post.id)
        db.session.commit()
        revision_id = revision.id

    paused = Event()
    resume = Event()

    def pause_older_write(connection, cursor, statement, parameters, context, many):
        if (current_thread().name.startswith('older-save')
                and statement.startswith('UPDATE post SET')):
            paused.set()
            assert resume.wait(5), 'newer transaction did not complete'

    def older_save():
        with application.app_context():
            actor = db.session.get(User, users['author'])
            post = db.session.get(Post, users['post'])
            assert post.draft.body == 'initial'
            _, applied = save_editor_draft(
                actor, post, DraftValues('Stale', 'stale', 1), 2)
            db.session.commit()
            return applied

    sa.event.listen(concurrent_database, 'before_cursor_execute', pause_older_write)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='older-save') as pool:
            pending = pool.submit(older_save)
            try:
                assert paused.wait(5), 'older save did not reach its database write'
                with application.app_context():
                    actor = db.session.get(User, users['author'])
                    post = db.session.get(Post, users['post'])
                    if winner == 'save':
                        save_editor_draft(actor, post, DraftValues('Latest', 'latest', 1), 3)
                    elif winner == 'publish':
                        publish_draft(actor, post.id)
                    elif winner == 'discard':
                        discard_draft(actor, post.id)
                    elif winner == 'unpublish':
                        unpublish_post(actor, post.id)
                    else:
                        restore_revision(actor, post.id, revision_id)
                    db.session.commit()
            finally:
                resume.set()
            assert pending.result(timeout=5) is False
    finally:
        sa.event.remove(concurrent_database, 'before_cursor_execute', pause_older_write)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        if winner in ('publish', 'discard'):
            assert post.draft is None
        else:
            assert post.draft.body == ('latest' if winner == 'save' else 'initial')


@pytest.mark.parametrize('action', ['publish', 'discard-draft', 'restore'])
def test_reloaded_editor_can_save_in_the_new_generation(client, application, users, action):
    login(client, 'author')
    response = client.post('/admin/posts/draft', headers={'X-Draft-Sequence': '7'}, json={
        'title': 'Before', 'body': 'before', 'category_id': 1})
    post_id = response.json['post_id']
    with application.app_context():
        revision = snapshot_draft(db.session.get(User, users['author']), post_id)
        db.session.commit()
        revision_id = revision.id
    path = f'revisions/{revision_id}/restore' if action == 'restore' else action
    client.post(f'/admin/posts/{post_id}/{path}')
    html = client.get(f'/admin/posts/{post_id}/edit').get_data(as_text=True)
    assert 'data-draft-generation="1"' in html
    assert 'data-editor-sequence="0"' in html
    response = client.put(f'/admin/posts/{post_id}/draft', headers={
        'X-Draft-Generation': '1', 'X-Draft-Sequence': '1'}, json={
            'title': 'After', 'body': 'after', 'category_id': 1})
    assert response.status_code == 200
    assert response.json['applied'] is True
    assert response.json['generation'] == 1
    assert response.json['sequence'] == 1
    with application.app_context():
        assert db.session.get(Post, post_id).draft.body == 'after'


@pytest.mark.parametrize('action', ['publish', 'discard-draft', 'restore'])
@pytest.mark.parametrize('save_path', ['draft', 'leave', 'new-draft', 'new-leave'])
def test_draft_actions_fence_delayed_editor_requests(
        client, application, users, action, save_path):
    login(client, 'author')
    headers = {'X-Draft-Key': 'generation-test', 'X-Draft-Sequence': '1',
               'X-Draft-Generation': '0'}
    created = client.post('/admin/posts/draft', headers=headers, json={
        'title': 'Saved', 'body': 'saved', 'category_id': 1})
    post_id = created.json['post_id']
    with application.app_context():
        revision = snapshot_draft(db.session.get(User, users['author']), post_id)
        db.session.commit()
        revision_id = revision.id
    action_path = (f'revisions/{revision_id}/restore'
                   if action == 'restore' else action)
    assert client.post(f'/admin/posts/{post_id}/{action_path}').status_code == 302
    path = {'draft': f'/admin/posts/{post_id}/draft',
            'leave': f'/admin/posts/{post_id}/leave',
            'new-draft': '/admin/posts/draft',
            'new-leave': '/admin/posts/draft/leave'}[save_path]
    response = client.open(path, method='PUT' if save_path == 'draft' else 'POST',
                           headers={**headers, 'X-Draft-Sequence': '20'}, json={
                               'title': 'Stale', 'body': 'stale', 'category_id': 1})
    assert response.status_code == 409
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.draft_generation == 1
        assert post.draft.body == 'saved' if action == 'restore' else post.draft is None
        assert db.session.scalar(sa.select(sa.func.count(PostRevision.id))) == 1


def create_other_post(application, users):
    with application.app_context():
        other = db.session.get(User, users['other'])
        category = db.session.scalar(sa.select(Category))
        post = Post(title='Other author post', body='<p>Private</p>',
                    author=other, category=category)
        db.session.add(post)
        db.session.commit()
        return post.id


def test_member_post_list_contains_only_owned_posts(
        client, application, users):
    create_other_post(application, users)
    login(client, 'author')

    response = client.get('/admin/posts')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '>Test<' in html
    assert 'Other author post' not in html


def test_member_cannot_guess_another_post_editor(
        client, application, users):
    other_post_id = create_other_post(application, users)
    login(client, 'author')

    response = client.get(f'/admin/posts/{other_post_id}/edit')

    assert response.status_code == 403


def test_admin_can_manage_any_post(client, application, users):
    other_post_id = create_other_post(application, users)
    login(client, 'admin')

    response = client.get(f'/admin/posts/{other_post_id}/edit')

    assert response.status_code == 200
    assert b'Other author post' in response.data


def test_member_can_create_markdown_edit_and_delete_own_post(
        client, application, users):
    login(client, 'author')
    with application.app_context():
        category = db.session.scalar(sa.select(Category))
        category_id = category.id

    created = client.post('/admin/posts/new', data={
        'title': 'Markdown article',
        'category': str(category_id),
        'post': '# Stored as source',
    })

    assert created.status_code == 302
    with application.app_context():
        post = db.session.scalar(sa.select(Post).join(PostDraft).where(
            PostDraft.title == 'Markdown article'))
        assert post.user_id == users['author']
        assert post.is_published is False
        assert post.draft.category_id == category_id
        assert post.draft.language == 'en'
        assert post.draft.body == '# Stored as source'
        assert post.body_format == 'markdown'
        post_id = post.id

    edited = client.post(f'/admin/posts/{post_id}/edit', data={
        'title': 'Updated in admin',
        'category': str(category_id),
        'post': '<p>Updated body</p>',
    })
    assert edited.status_code == 302

    deleted = client.post(f'/admin/posts/{post_id}/delete')
    assert deleted.status_code == 302
    with application.app_context():
        assert db.session.get(Post, post_id) is None


def test_admin_draft_forms_save_empty_title_and_body(client, application, users):
    login(client, 'author')
    with application.app_context():
        category_id = db.session.scalar(sa.select(Category)).id

    created = client.post('/admin/posts/new', data={
        'title': '', 'category': str(category_id), 'post': '',
    })

    assert created.status_code == 302
    with application.app_context():
        post = db.session.scalar(sa.select(Post).join(PostDraft).where(
            Post.user_id == users['author'], Post.title == ''))
        assert post.draft.title == ''
        assert post.draft.body == ''
        post_id = post.id

    updated = client.post(f'/admin/posts/{post_id}/edit', data={
        'title': '', 'category': str(category_id), 'post': '',
    })

    assert updated.status_code == 302
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.draft.title == ''
        assert post.draft.body == ''


def test_admin_post_list_labels_empty_draft_title(client, application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_draft(actor, post, DraftValues('', 'draft body', 1))
        db.session.commit()

    login(client, 'author')
    response = client.get('/admin/posts')

    assert response.status_code == 200
    assert '<strong>Untitled draft</strong>' in response.get_data(as_text=True)


def test_admin_post_edit_preserves_legacy_format_and_sanitizes_html(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(sa.select(Category))
        post = Post(title='Legacy article', body='<p>Legacy</p>',
                    body_format='html', author=author, category=category)
        db.session.add(post)
        db.session.commit()
        post_id = post.id
        category_id = category.id

    login(client, 'author')
    response = client.post(f'/admin/posts/{post_id}/edit', data={
        'title': 'Legacy article',
        'category': str(category_id),
        'post': '<p>Updated</p><script>alert(1)</script>',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.body == '<p>Legacy</p>'
        assert post.draft.body == '<p>Updated</p>alert(1)'
        assert post.body_format == 'html'


def test_legacy_post_edit_preserves_legacy_format_and_sanitizes_html(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(sa.select(Category))
        post = Post(title='Legacy compatibility article', body='<p>Legacy</p>',
                    body_format='html', author=author, category=category)
        db.session.add(post)
        db.session.commit()
        post_id = post.id
        category_id = category.id

    login(client, 'author')
    response = client.post(f'/post/{post_id}/edit', data={
        'title': 'Legacy compatibility article',
        'category': str(category_id),
        'post': '<p>Updated</p><script>alert(1)</script>',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.body == '<p>Updated</p>alert(1)'
        assert post.body_format == 'html'


def test_admin_post_edit_normalizes_invalid_format_without_publication(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(sa.select(Category))
        post = Post(title='Unknown format article', body='# Legacy source',
                    body_format='unexpected', author=author, category=category)
        db.session.add(post)
        db.session.commit()
        post_id = post.id
        category_id = category.id

    login(client, 'author')
    response = client.post(f'/admin/posts/{post_id}/edit', data={
        'title': 'Unknown format article',
        'category': str(category_id),
        'post': '<p>Updated</p><script>alert(1)</script>',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.body == '# Legacy source'
        assert post.draft.body == '<p>Updated</p>alert(1)'
        assert post.body_format == 'html'


def test_legacy_post_edit_normalizes_invalid_format_and_publishes(
        client, application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        category = db.session.scalar(sa.select(Category))
        post = Post(title='Unknown format article', body='# Legacy source',
                    body_format='unexpected', author=author, category=category)
        db.session.add(post)
        db.session.commit()
        post_id = post.id
        category_id = category.id

    login(client, 'author')
    response = client.post(f'/post/{post_id}/edit', data={
        'title': 'Unknown format article',
        'category': str(category_id),
        'post': '<p>Updated</p><script>alert(1)</script>',
    })

    assert response.status_code == 302
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.body == '<p>Updated</p>alert(1)'
        assert post.draft is None
        assert post.body_format == 'html'


def test_member_cannot_delete_another_post(client, application, users):
    other_post_id = create_other_post(application, users)
    login(client, 'author')

    response = client.post(f'/admin/posts/{other_post_id}/delete')

    assert response.status_code == 403
    with application.app_context():
        assert db.session.get(Post, other_post_id) is not None


def test_author_autosaves_private_draft_then_publishes(client, users):
    login(client, 'author')

    saved = client.post('/admin/posts/draft', json={
        'title': 'Half written', 'body': 'draft text', 'category_id': 1,
    })

    assert saved.status_code == 201
    post_id = saved.get_json()['post_id']
    assert client.get(f'/post/{post_id}').status_code == 404
    assert client.post(f'/admin/posts/{post_id}/publish').status_code == 302
    assert client.get(f'/post/{post_id}').status_code == 200


def test_draft_endpoints_reject_invalid_json_and_unknown_categories(client, users):
    login(client, 'author')

    invalid_payload = client.post('/admin/posts/draft', json={
        'title': ['not text'], 'body': 'draft text', 'category_id': 1,
    })
    unknown_category = client.post('/admin/posts/draft', json={
        'title': '', 'body': '', 'category_id': 999,
    })

    assert invalid_payload.status_code == 400
    assert unknown_category.status_code == 400


def test_author_can_save_an_empty_draft_and_update_it(client, application, users):
    login(client, 'author')
    created = client.post('/admin/posts/draft', json={
        'title': '', 'body': '', 'category_id': 1,
    })

    assert created.status_code == 201
    post_id = created.get_json()['post_id']

    updated = client.put(f'/admin/posts/{post_id}/draft', json={
        'title': 'Continued draft', 'body': 'saved later', 'category_id': 1,
    })

    assert updated.status_code == 200
    assert updated.get_json()['post_id'] == post_id
    with application.app_context():
        post = db.session.get(Post, post_id)
        assert post.is_published is False
        assert post.draft.title == 'Continued draft'
        assert post.draft.body == 'saved later'


def test_author_can_create_and_snapshot_a_draft_while_leaving_new_editor(
        client, application, users):
    login(client, 'author')

    saved = client.post('/admin/posts/draft/leave', json={
        'title': 'Leaving new editor', 'body': 'snapshot source',
        'category_id': 1,
    })

    assert saved.status_code == 201
    post_id = saved.get_json()['post_id']
    assert saved.get_json()['revision_created'] is True
    with application.app_context():
        post = db.session.get(Post, post_id)
        revisions = db.session.scalars(sa.select(PostRevision).where(
            PostRevision.post_id == post_id)).all()
        assert post.user_id == users['author']
        assert post.draft.body == 'snapshot source'
        assert len(revisions) == 1
        assert revisions[0].body == 'snapshot source'


def test_new_editor_session_key_reuses_one_post_and_one_leave_snapshot(
        client, application, users):
    login(client, 'author')
    headers = {'X-Draft-Key': 'new-editor-key', 'X-Draft-Sequence': '1'}
    created = client.post('/admin/posts/draft', headers=headers, json={
        'title': 'First', 'body': 'first source', 'category_id': 1,
    })
    left = client.post('/admin/posts/draft/leave', headers={
        'X-Draft-Key': 'new-editor-key', 'X-Draft-Sequence': '2'}, json={
        'title': 'Final', 'body': 'final source', 'category_id': 1,
    })

    assert created.status_code == 201
    assert left.status_code == 201
    assert created.get_json()['post_id'] == left.get_json()['post_id']
    with application.app_context():
        post = db.session.scalar(sa.select(Post).where(
            Post.editor_session_key == 'new-editor-key'))
        assert post.draft.body == 'final source'
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostRevision).where(PostRevision.post_id == post.id)) == 1


def test_stale_editor_sequence_cannot_overwrite_a_leave_snapshot(
        client, application, users):
    login(client, 'author')
    latest = client.post(f'/admin/posts/{users["post"]}/leave', headers={
        'X-Draft-Sequence': '2'}, json={
        'title': 'Latest', 'body': 'latest source', 'category_id': 1,
    })
    stale = client.put(f'/admin/posts/{users["post"]}/draft', headers={
        'X-Draft-Sequence': '1'}, json={
        'title': 'Stale', 'body': 'stale source', 'category_id': 1,
    })
    repeated = client.post(f'/admin/posts/{users["post"]}/leave', headers={
        'X-Draft-Sequence': '2'}, json={
        'title': 'Latest', 'body': 'latest source', 'category_id': 1,
    })

    assert latest.get_json()['revision_created'] is True
    assert latest.get_json()['applied'] is True
    assert stale.status_code == 200
    assert stale.get_json()['applied'] is False
    assert repeated.get_json()['revision_created'] is False
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.draft.body == 'latest source'
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostRevision).where(PostRevision.post_id == post.id)) == 1


def test_leave_creates_revision_and_denies_other_author(
        client, application, users):
    login(client, 'other')

    denied = client.post(f'/admin/posts/{users["post"]}/leave', json={
        'title': 'stolen', 'body': 'stolen', 'category_id': 1,
    })

    assert denied.status_code == 403

    client.post('/logout')
    login(client, 'author')
    saved = client.post(f'/admin/posts/{users["post"]}/leave', json={
        'title': 'Saved before leaving', 'body': 'draft snapshot',
        'category_id': 1,
    })

    assert saved.status_code == 200
    assert saved.get_json()['revision_created'] is True
    with application.app_context():
        revision = db.session.scalar(sa.select(PostRevision).where(
            PostRevision.post_id == users['post']))
        assert revision.title == 'Saved before leaving'
        assert revision.body == 'draft snapshot'


def test_editor_renders_draft_actions_and_revision_restore(
        client, application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_draft(actor, post, DraftValues('Pending update', 'private', 1))
        revision = snapshot_draft(actor, post.id)
        db.session.commit()
        revision_id = revision.id

    login(client, 'author')
    editor = client.get(f'/admin/posts/{users["post"]}/edit')
    html = editor.get_data(as_text=True)

    assert editor.status_code == 200
    assert 'Pending update' in html
    assert '有未发布修改' in html
    assert '发布更新' in html
    assert 'Discard draft' not in html
    assert f'/revisions/{revision_id}/restore' in html

    restored = client.post(
        f'/admin/posts/{users["post"]}/revisions/{revision_id}/restore')

    assert restored.status_code == 302
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.draft.title == 'Pending update'
        assert post.draft.body == 'private'


def test_unpublish_creates_a_publishable_draft(client, application, users):
    login(client, 'author')

    unpublished = client.post(f'/admin/posts/{users["post"]}/unpublish')
    editor = client.get(f'/admin/posts/{users["post"]}/edit')

    assert unpublished.status_code == 302
    html = editor.get_data(as_text=True)
    assert 'data-publish' in html
    assert 'role="switch"' not in html
    assert f'action="/admin/posts/{users["post"]}/publish"' in html
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post.is_published is False
        assert post.draft.title == 'Test'
        assert post.draft.body == '<p>safe</p>'


def test_draft_does_not_change_public_content_until_publish(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        post.is_published = True

        save_draft(actor, post, DraftValues('New', 'private update', 1))

        assert post.title == 'Test'
        assert post.body == '<p>safe</p>'
        assert post.is_published is True
        assert post.draft.title == 'New'
        assert post.draft.body == 'private update'

        publish_draft(actor, post.id)

        assert post.title == 'New'
        assert post.body == 'private update'
        assert post.is_published is True
        assert post.draft is None


def test_restoring_revision_updates_only_private_draft(application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.is_published = True
        revision = PostRevision(
            post=post, title='Old', body='old', category_id=1, language='en')
        db.session.add(revision)
        db.session.commit()

        restore_revision(
            db.session.get(User, users['author']), post.id, revision.id)

        assert post.draft.title == 'Old'
        assert post.draft.body == 'old'
        assert post.draft.category_id == 1
        assert post.draft.language == 'en'
        assert post.title == 'Test'
        assert post.body == '<p>safe</p>'
        assert post.is_published is True


def test_save_draft_rejects_other_actor_for_unpersisted_post(
        application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        other = db.session.get(User, users['other'])
        post = Post(title='Pending', body='pending', author=author)

        assert post.user_id is None
        with pytest.raises(Forbidden):
            save_draft(other, post, DraftValues('Stolen', 'draft body', 1))

        assert post.draft is None


def test_publishing_rejects_blank_draft_fields_and_unknown_category(
        application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])

        save_draft(actor, post, DraftValues(' ', 'draft body', 1))
        with pytest.raises(PostDraftError, match='title'):
            publish_draft(actor, post.id)

        save_draft(actor, post, DraftValues('Title', ' ', 1))
        with pytest.raises(PostDraftError, match='body'):
            publish_draft(actor, post.id)

        save_draft(actor, post, DraftValues('Title', 'draft body', 999))
        with pytest.raises(PostDraftError, match='category'):
            publish_draft(actor, post.id)

        save_draft(actor, post, DraftValues('Title', 'draft body', None))
        with pytest.raises(PostDraftError, match='category'):
            publish_draft(actor, post.id)


def test_draft_html_is_sanitized_using_legacy_post_format(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        post.body_format = 'html'

        save_draft(actor, post, DraftValues(
            'Edited', '<p>Safe</p><script>alert(1)</script>', 1))

        assert post.draft.body == '<p>Safe</p>alert(1)'


def test_saved_draft_persists_when_the_caller_commits(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])

        save_draft(actor, post, DraftValues('Persisted', 'draft body', 1))
        db.session.commit()
        db.session.expunge_all()

        post = db.session.get(Post, users['post'])
        assert post.draft.title == 'Persisted'
        assert post.draft.body == 'draft body'


def test_unpublish_and_discard_change_only_their_respective_state(
        application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        save_draft(actor, post, DraftValues('Draft', 'private', 1))

        unpublish_post(actor, post.id)

        assert post.is_published is False
        assert post.draft is not None

        discard_draft(actor, post.id)

        assert post.is_published is False
        assert post.draft is None


def test_restore_rejects_a_revision_owned_by_another_post(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        other = db.session.get(User, users['other'])
        other_post = Post(title='Other', body='other', author=other)
        revision = PostRevision(post=other_post, title='Old', body='old')
        db.session.add_all([other_post, revision])
        db.session.commit()

        with pytest.raises(PostDraftError, match='revision'):
            restore_revision(actor, post.id, revision.id)


def test_snapshot_copies_draft_and_prunes_oldest_per_post(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        get_site_settings().post_revision_limit = 2

        for body in ('first', 'second', 'third'):
            save_draft(actor, post, DraftValues('Draft', body, 1))
            snapshot_draft(actor, post.id)
            db.session.flush()

        revisions = db.session.scalars(sa.select(PostRevision).where(
            PostRevision.post_id == post.id).order_by(PostRevision.id)).all()
        assert [revision.body for revision in revisions] == ['second', 'third']


def test_snapshot_without_a_draft_returns_none(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])

        assert snapshot_draft(actor, users['post']) is None


def test_global_trim_prunes_each_post_to_the_given_limit(application, users):
    with application.app_context():
        actor = db.session.get(User, users['author'])
        post = db.session.get(Post, users['post'])
        other = db.session.get(User, users['other'])
        other_post = Post(title='Other', body='other', author=other)
        db.session.add(other_post)
        db.session.flush()
        db.session.add_all([
            PostRevision(post=post, title='one', body='one'),
            PostRevision(post=post, title='two', body='two'),
            PostRevision(post=other_post, title='three', body='three'),
            PostRevision(post=other_post, title='four', body='four'),
        ])
        db.session.flush()

        trim_all_post_revisions(1)

        revisions = db.session.scalars(sa.select(PostRevision).order_by(
            PostRevision.post_id, PostRevision.id)).all()
        assert [revision.body for revision in revisions] == ['two', 'four']
