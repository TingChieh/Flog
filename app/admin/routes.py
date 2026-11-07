import sqlalchemy as sa
from flask import render_template
from flask_login import current_user, login_required

from app import db
from app.admin import bp
from app.models import Page, Post, PostComment, User


def _count(model, *conditions):
    return db.session.scalar(
        sa.select(sa.func.count()).select_from(model).where(*conditions))


@bp.route('/', methods=['GET'], strict_slashes=False)
@login_required
def dashboard():
    metrics = [{'label': '我的文章', 'endpoint': 'admin.posts', 'scope': 'mine',
                'value': str(_count(Post, Post.user_id == current_user.id))}]
    if current_user.is_admin:
        published = _count(Page, Page.is_published.is_(True))
        page_total = _count(Page)
        comment_total = _count(PostComment)
        comments_waiting = _count(PostComment, PostComment.status == 'pending')
        metrics += [
            {'label': '全部文章', 'endpoint': 'admin.posts', 'scope': 'all',
             'value': str(_count(Post))},
            {'label': '页面', 'endpoint': 'admin.pages',
             'value': str(published),
             'note': f'共 {page_total} 个' if page_total != published else None},
            {'label': '评论', 'endpoint': 'admin.comments',
             'value': str(comment_total),
             'note': f'{comments_waiting} 条待审' if comments_waiting else None,
             'alert': bool(comments_waiting)},
            {'label': '用户', 'endpoint': 'admin.users',
             'value': str(_count(User))},
        ]
    return render_template('admin/dashboard.html', metrics=metrics)
