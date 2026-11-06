from datetime import datetime, timezone
from hashlib import md5
from typing import Optional
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
    last_message_read_time: so.Mapped[Optional[datetime]]
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
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def avatar(self, size):
        if self.avatar_filename:
            return url_for('uploaded_files', filename=f'avatars/{self.avatar_filename}')
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://cravatar.cn/avatar/{digest}?d=identicon&s={size}'

        
        
    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'],algorithm='HS256')
        
    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
            return db.session.get(User, id)
        except jwt.PyJWTError:
            logging.getLogger(__name__).warning(
                'Password reset token validation failed')
            return None


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))

class Category(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, nullable=False)
    # Relationship with Post
    posts: so.Mapped[list["Post"]] = so.relationship('Post', back_populates='category', lazy='dynamic')    


class SiteSettings(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True, default=1)
    registration_open: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
    post_revision_limit: so.Mapped[int] = so.mapped_column(
        sa.Integer, nullable=False, default=20, server_default=sa.text('20'))


def get_site_settings():
    settings = db.session.get(SiteSettings, 1)
    if settings is None:
        settings = SiteSettings(
            id=1, registration_open=True, post_revision_limit=20)
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
        back_populates='post', cascade='all, delete-orphan',
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
        return '<Post {}>'.format(self.body)


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
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(Post.id, ondelete='CASCADE'), index=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64))
    email: so.Mapped[str] = so.mapped_column(sa.String(120))
    body: so.Mapped[str] = so.mapped_column(sa.Text)
    timestamp: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Post] = so.relationship(back_populates='comments')

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://cravatar.cn/avatar/{digest}?d=identicon&s={size}'


class PostLike(db.Model):
    __table_args__ = (
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    post_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(Post.id, ondelete='CASCADE'), index=True)
    user_id: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(User.id, ondelete='CASCADE'), index=True)
    timestamp: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Post] = so.relationship(back_populates='likes')
    user: so.Mapped[User] = so.relationship(back_populates='post_likes')
    
    

    
    
    
    


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
