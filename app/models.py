from datetime import datetime, timezone
from hashlib import md5
from typing import Optional
import hmac
import logging
import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login
from time import time
import jwt
from app import app

# Seconds a password reset link stays valid.
RESET_TOKEN_LIFETIME = 600


class User(UserMixin, db.Model):
    __table_args__ = (
        sa.CheckConstraint("role IN ('user', 'admin')", name='ck_user_role'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True,
                                                unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True,
                                             unique=True)
    role: so.Mapped[str] = so.mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'user'"),
        default='user')
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
    # File under <uploads>/avatars, or None to use the Cravatar default.
    avatar_filename: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64))
    last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))
    posts: so.WriteOnlyMapped['Post'] = so.relationship(
        back_populates='author')
    post_likes: so.WriteOnlyMapped['PostLike'] = so.relationship(
        back_populates='user', cascade='all, delete-orphan',
        passive_deletes=True)

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(
            self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def avatar(self, size):
        if self.avatar_filename:
            return url_for('uploaded_files', filename=f'avatars/{self.avatar_filename}')
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://cravatar.cn/avatar/{digest}?d=identicon&s={size}'

        
        
    def _password_fingerprint(self):
        """Changes whenever the password does, so a used token stops working."""
        return hmac.new(app.config['SECRET_KEY'].encode(),
                        (self.password_hash or '').encode(),
                        'sha256').hexdigest()[:32]

    def get_reset_password_token(self, expires_in=RESET_TOKEN_LIFETIME):
        return jwt.encode(
            {'reset_password': self.id, 'pw': self._password_fingerprint(),
             'exp': time() + expires_in},
            app.config['SECRET_KEY'],algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            claims = jwt.decode(token, app.config['SECRET_KEY'],
                                algorithms=['HS256'])
            user = db.session.get(User, claims['reset_password'])
            if user and hmac.compare_digest(
                    claims['pw'], user._password_fingerprint()):
                return user
        except (jwt.PyJWTError, KeyError, TypeError):
            pass
        logging.getLogger(__name__).warning(
            'Password reset token validation failed')
        return None


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))

class AuthAttempt(db.Model):
    """A failed sign-in or a reset request, kept for a day to slow down guessing.

    Only keyed hashes are stored: of the network address, and of the email
    address a reset was asked for.
    """
    __table_args__ = (
        sa.Index('ix_auth_attempt_lookup', 'action', 'key_hash', 'created_at'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    action: so.Mapped[str] = so.mapped_column(sa.String(16), nullable=False)
    key_hash: so.Mapped[str] = so.mapped_column(sa.String(64), nullable=False)
    created_at: so.Mapped[datetime] = so.mapped_column(
        nullable=False, index=True, default=lambda: datetime.now(timezone.utc))


class Category(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, nullable=False)
    # Relationship with Post
    posts: so.Mapped[list["Post"]] = so.relationship('Post', back_populates='category', lazy='dynamic')    


class SiteSettings(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, default=1)
    registration_open: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    post_revision_limit: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=20, server_default=sa.text('20'))
    # Wording shown across the public site; blank means "use the default".
    site_name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(60))
    home_tab_title: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))
    home_heading: so.Mapped[Optional[str]] = so.mapped_column(sa.String(60))
    nav_home_label: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    nav_archive_label: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    nav_categories_label: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))


def get_site_settings():
    settings = db.session.get(SiteSettings, 1)
    if settings is None:
        settings = SiteSettings(
            id=1, registration_open=False, post_revision_limit=20)
        db.session.add(settings)
    return settings


class Post(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    # Address of the post on the old blog (/archives/<legacy_id>/), if any.
    legacy_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.Integer, unique=True, index=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    body: so.Mapped[str] = so.mapped_column(sa.Text)
    view_count: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text('0'))
    is_published: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.true())
    comments_enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
    body_format: so.Mapped[str] = so.mapped_column(
        sa.String(20), nullable=False, default='html',
        server_default=sa.text("'html'"))
    # When the post went public; set again if it is unpublished and republished.
    timestamp: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc))
    # When a live post last had an update published; None until then.
    updated_at: so.Mapped[Optional[datetime]] = so.mapped_column()
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id),
                                               index=True)
    editor_session_key: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(64), unique=True, index=True)
    draft_generation: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text('0'))
    draft_sequence: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text('0'))

    author: so.Mapped[User] = so.relationship(back_populates='posts')
    language: so.Mapped[Optional[str]] = so.mapped_column(sa.String(5))
    category_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Category.id), nullable=True)
    category: so.Mapped[Category] = so.relationship('Category',back_populates='posts')
    comments: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='post', cascade='all, delete',
        order_by='PostComment.timestamp')
    likes: so.WriteOnlyMapped['PostLike'] = so.relationship(
        back_populates='post', cascade='all, delete-orphan',
        passive_deletes=True)
    draft: so.Mapped[Optional['PostDraft']] = so.relationship(
        back_populates='post', cascade='all, delete-orphan', uselist=False)
    revisions: so.Mapped[list['PostRevision']] = so.relationship(
        back_populates='post', cascade='all, delete-orphan',
        order_by='PostRevision.created_at.desc()')

    @property
    def local_timestamp(self):
        from app.timezones import to_display
        return to_display(self.timestamp)

    @property
    def local_updated_at(self):
        from app.timezones import later_update
        return later_update(self.timestamp, self.updated_at)

    def likes_count(self):
        return db.session.scalar(sa.select(sa.func.count()).select_from(
            self.likes.select().subquery()))

    def is_liked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return db.session.scalar(
            self.likes.select().where(PostLike.user_id == user.id)) is not None

    def __repr__(self):
        return '<Post {}>'.format(self.title)


class PostDraft(db.Model):
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey('post.id', ondelete='CASCADE'), primary_key=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    body: so.Mapped[str] = so.mapped_column(sa.Text, nullable=False)
    category_id: so.Mapped[int | None] = so.mapped_column(
        sa.ForeignKey('category.id'))
    language: so.Mapped[str | None] = so.mapped_column(sa.String(5))
    updated_at: so.Mapped[datetime] = so.mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
    last_editor_sequence: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text('0'))

    post: so.Mapped[Post] = so.relationship(back_populates='draft')


class PostRevision(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey('post.id', ondelete='CASCADE'), nullable=False, index=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    body: so.Mapped[str] = so.mapped_column(sa.Text, nullable=False)
    category_id: so.Mapped[int | None] = so.mapped_column(
        sa.ForeignKey('category.id'))
    language: so.Mapped[str | None] = so.mapped_column(sa.String(5))
    created_at: so.Mapped[datetime] = so.mapped_column(
        nullable=False, index=True, default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Post] = so.relationship(back_populates='revisions')


class PostComment(db.Model):
    __table_args__ = (
        sa.CheckConstraint(
            '(post_id IS NOT NULL) + (page_id IS NOT NULL) '
            '+ (episode_id IS NOT NULL) = 1',
            name='ck_post_comment_target'),
        sa.CheckConstraint(
            "status IN ('pending', 'approved')", name='ck_post_comment_status'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    # Exactly one of post_id, page_id and episode_id is set.
    post_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(Post.id, ondelete='CASCADE'), index=True)
    page_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('page.id', ondelete='CASCADE'), index=True)
    episode_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('episode.id', ondelete='CASCADE'), index=True)
    # A reply points at its top-level comment; replies never nest deeper.
    parent_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('post_comment.id', ondelete='CASCADE'), index=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64))
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True)
    body: so.Mapped[str] = so.mapped_column(sa.Text)
    status: so.Mapped[str] = so.mapped_column(
        sa.String(10), nullable=False, default='approved',
        server_default=sa.text("'approved'"))
    # Set only when the site owner wrote it while signed in.
    user_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(User.id, ondelete='SET NULL'), index=True)
    # Set when the commenter ticked "email me"; unsubscribing clears it.
    notify_replies: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    # The comment this one answers: its top-level comment, or the reply it
    # was written to. parent_id alone cannot say which reply was meant.
    answered_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('post_comment.id', ondelete='SET NULL'), index=True)
    # A keyed hash of the network address, for rate limits; never the address.
    ip_hash: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(64), index=True)
    timestamp: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Optional[Post]] = so.relationship(back_populates='comments')
    page: so.Mapped[Optional['Page']] = so.relationship(
        back_populates='comments')
    episode: so.Mapped[Optional['Episode']] = so.relationship(
        back_populates='comments')
    parent: so.Mapped[Optional['PostComment']] = so.relationship(
        back_populates='replies', remote_side='PostComment.id',
        foreign_keys='PostComment.parent_id')
    replies: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='parent', cascade='all, delete',
        order_by='PostComment.timestamp',
        foreign_keys='PostComment.parent_id')
    answered: so.Mapped[Optional['PostComment']] = so.relationship(
        remote_side='PostComment.id', foreign_keys='PostComment.answered_id')
    user: so.Mapped[Optional[User]] = so.relationship()

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://cravatar.cn/avatar/{digest}?d=identicon&s={size}'


class PostLike(db.Model):
    """A reaction from a browser (``visitor_id``) and, if they were signed in, a user."""
    __table_args__ = (
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),
        sa.UniqueConstraint('post_id', 'visitor_id', name='uq_post_like_visitor'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(Post.id, ondelete='CASCADE'), index=True)
    user_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(User.id, ondelete='CASCADE'), index=True)
    # Hashes only: of the browser's random cookie, and of the network address.
    visitor_id: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64))
    ip_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64), index=True)
    # The reaction the reader picked; one of app.likes.REACTIONS.
    emoji: so.Mapped[str] = so.mapped_column(
        sa.String(16), default='\u2764\ufe0f', server_default='\u2764\ufe0f')
    timestamp: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Post] = so.relationship(back_populates='likes')
    user: so.Mapped[Optional[User]] = so.relationship(back_populates='post_likes')


class Page(db.Model):
    __table_args__ = (
        sa.CheckConstraint(
            "kind IN ('content', 'module')", name='ck_page_kind'),
        sa.CheckConstraint(
            "(kind = 'content' AND module_key IS NULL) OR "
            "(kind = 'module' AND module_key IN "
            "('todo', 'movie', 'links', 'guestbook'))",
            name='ck_page_module_key'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    slug: so.Mapped[str] = so.mapped_column(
        sa.String(120), nullable=False, unique=True, index=True)
    summary: so.Mapped[Optional[str]] = so.mapped_column(sa.String(300))
    body: so.Mapped[Optional[str]] = so.mapped_column(sa.Text)
    body_format: so.Mapped[str] = so.mapped_column(
        sa.String(20), nullable=False, default='html',
        server_default=sa.text("'html'"))
    kind: so.Mapped[str] = so.mapped_column(
        sa.String(20), nullable=False, default='content',
        server_default=sa.text("'content'"))
    module_key: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(20), unique=True)
    is_published: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    show_in_nav: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    comments_enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    nav_order: so.Mapped[int] = so.mapped_column(
        nullable=False, default=0, server_default=sa.text('0'))
    created_at: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))
    updated_at: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    redirects: so.Mapped[list['PageRedirect']] = so.relationship(
        back_populates='page', cascade='all, delete-orphan',
        passive_deletes=True)
    comments: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='page', cascade='all, delete',
        order_by='PostComment.timestamp')


class PageRedirect(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    slug: so.Mapped[str] = so.mapped_column(
        sa.String(120), nullable=False, unique=True, index=True)
    page_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(Page.id, ondelete='CASCADE'), nullable=False, index=True)

    page: so.Mapped[Page] = so.relationship(back_populates='redirects')


class Image(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    filename: so.Mapped[str] = so.mapped_column(
        sa.String(80), unique=True, index=True)
    original_name: so.Mapped[str] = so.mapped_column(sa.String(255))
    title: so.Mapped[str] = so.mapped_column(sa.String(120))
    note: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))
    size: so.Mapped[int] = so.mapped_column(sa.Integer, default=0)
    # Pixel size of the stored file; None for images that predate the columns.
    width: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer)
    height: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer)
    # The Live Photo clip stored next to the file, or None for an ordinary image.
    video_filename: so.Mapped[Optional[str]] = so.mapped_column(sa.String(80))
    user_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(User.id, ondelete='SET NULL'), index=True)
    created_at: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))

    uploader: so.Mapped[Optional[User]] = so.relationship()


class PodcastShow(db.Model):
    """The podcast's own wording and artwork; blank fields use the defaults."""
    id: so.Mapped[int] = so.mapped_column(primary_key=True, default=1)
    # The podcast is off until an admin switches it on; while off its pages,
    # feed and menu link do not exist.
    enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    show_in_nav: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
    nav_order: so.Mapped[int] = so.mapped_column(
        nullable=False, default=100, server_default=sa.text('100'))
    title: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.Text)
    author: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))
    # Apple and 小宇宙 mail this address to prove who owns the feed.
    owner_email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))
    category: so.Mapped[Optional[str]] = so.mapped_column(sa.String(60))
    # Name of an uploaded image (served from /files/); square, 1400-3000 px.
    cover_filename: so.Mapped[Optional[str]] = so.mapped_column(sa.String(80))
    apple_url: so.Mapped[Optional[str]] = so.mapped_column(sa.String(300))
    xiaoyuzhou_url: so.Mapped[Optional[str]] = so.mapped_column(sa.String(300))


def get_podcast_show():
    show = db.session.get(PodcastShow, 1)
    if show is None:
        show = PodcastShow(id=1)
        db.session.add(show)
    return show


class Episode(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    # The public address is /podcast/<number>, so it is unique and never reused.
    number: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, unique=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(120), nullable=False)
    # Plain-text blurb for the feed and the list page.
    summary: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))
    # Show notes, written in Markdown.
    body: so.Mapped[Optional[str]] = so.mapped_column(sa.Text)
    # File under <uploads>/audio/; it is the feed's enclosure, so it is only
    # replaced on purpose.
    audio_filename: so.Mapped[str] = so.mapped_column(
        sa.String(80), nullable=False)
    audio_size: so.Mapped[int] = so.mapped_column(
        sa.BigInteger, nullable=False, default=0)
    audio_duration: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=0)
    audio_mime: so.Mapped[str] = so.mapped_column(
        sa.String(40), nullable=False, default='audio/mpeg')
    # Name of an uploaded image; blank uses the show's cover.
    cover_filename: so.Mapped[Optional[str]] = so.mapped_column(sa.String(80))
    is_published: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
    comments_enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
    # When it went (or goes) public.
    published_at: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc))
    # Path of the episode on the old WordPress site, kept for redirects.
    legacy_path: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(255), unique=True)
    # The id this episode had in the old feed. Apple and 小宇宙 tell episodes
    # apart by it, so a different one would list the episode twice.
    feed_guid: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    created_at: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))

    comments: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='episode', cascade='all, delete',
        order_by='PostComment.timestamp')
