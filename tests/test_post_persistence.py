import sqlalchemy as sa

from app import db
from app.models import Post, PostDraft, PostRevision, SiteSettings, get_site_settings


def test_get_site_settings_initializes_defaults_when_row_is_missing(application):
    with application.app_context():
        db.session.execute(sa.delete(SiteSettings))
        db.session.commit()

        settings = get_site_settings()

        assert settings.id == 1
        assert settings.registration_open is True
        assert settings.post_revision_limit == 20


def test_deleting_reloaded_post_removes_draft_and_revisions(application, users):
    with application.app_context():
        post_id = users['post']
        db.session.add_all([
            PostDraft(post_id=post_id, title='Draft', body='draft'),
            PostRevision(post_id=post_id, title='Earlier', body='earlier'),
            PostRevision(post_id=post_id, title='Latest', body='latest'),
        ])
        db.session.commit()

        db.session.expunge_all()
        db.session.delete(db.session.get(Post, post_id))
        db.session.commit()

        assert db.session.get(PostDraft, post_id) is None
        assert db.session.scalar(sa.select(sa.func.count()).select_from(
            PostRevision).where(PostRevision.post_id == post_id)) == 0
