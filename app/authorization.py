import sqlalchemy as sa
from flask import abort

from app import db
from app.models import Image, Post, PostLike, User


ROLE_USER = 'user'
ROLE_ADMIN = 'admin'
VALID_ROLES = frozenset({ROLE_USER, ROLE_ADMIN})


class RoleChangeError(ValueError):
    pass


def owned_post_or_404(post_id: int, actor: User) -> Post:
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)
    if not actor.is_admin and post.user_id != actor.id:
        abort(403)
    return post


def change_user_role(actor: User, target: User, new_role: str) -> None:
    if not actor.is_admin:
        raise RoleChangeError('Administrator access is required.')
    if new_role not in VALID_ROLES:
        raise RoleChangeError('Unknown role.')
    if target.role == ROLE_ADMIN and new_role == ROLE_USER:
        admins = db.session.scalars(
            sa.select(User).where(User.role == ROLE_ADMIN).with_for_update()
        ).all()
        if len(admins) <= 1:
            raise RoleChangeError('The final administrator cannot be demoted.')
    if actor.id == target.id and target.role == ROLE_ADMIN \
            and new_role != ROLE_ADMIN:
        raise RoleChangeError('You cannot remove your own administrator role.')
    target.role = new_role


def delete_user(actor: User, target: User, receiver: User | None) -> None:
    """Delete ``target``, handing their posts and images to ``receiver``.

    Raises RoleChangeError on guard failures. The caller commits. The last
    administrator cannot be deleted: only an administrator may delete, and
    nobody may delete themselves.
    """
    if not actor.is_admin:
        raise RoleChangeError('Administrator access is required.')
    if actor.id == target.id:
        raise RoleChangeError('You cannot delete yourself.')
    post_count = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.user_id == target.id))
    if post_count:
        if receiver is None or receiver.id == target.id:
            raise RoleChangeError('Choose another user to receive the posts.')
        db.session.execute(sa.update(Post).where(
            Post.user_id == target.id).values(user_id=receiver.id))
    db.session.execute(sa.update(Image).where(
        Image.user_id == target.id).values(
            user_id=receiver.id if receiver is not None
            and receiver.id != target.id else None))
    db.session.execute(
        sa.delete(PostLike).where(PostLike.user_id == target.id))
    # Core DELETE: the write-only User.posts relationship cannot be walked by
    # an ORM delete, and the posts were just handed over.
    db.session.execute(sa.delete(User).where(User.id == target.id))
    db.session.expire_all()
