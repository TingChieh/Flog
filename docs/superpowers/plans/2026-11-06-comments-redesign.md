# 评论系统改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 评论支持两层回复、首次审核与防刷、受限 Markdown、文章与页面各自的评论开关,并重做后台评论管理页。

**Architecture:** `PostComment` 加字段后可挂在文章或页面上(有且只有一个归属)。评论的渲染放在 `app/comment_markdown.py`,审核/限流/回复归并等规则放在 `app/comments.py`,路由只负责接表单与跳转。前台评论区抽成共用片段 `_comments.html`,文章页与内容页共用。表情功能另见 `2026-11-06-emoji.md`,不在本计划内。

**Tech Stack:** Flask、SQLAlchemy 2、Alembic(`batch_alter_table`,SQLite 与 MySQL 都要能跑)、WTForms、Python-Markdown 3.11 + bleach 6.4(都已在 `requirements.txt`)、pytest、`node --test`。

设计文档:`docs/superpowers/specs/2026-11-06-comments-redesign-design.md`。

## Global Constraints

- 站点界面固定中文。本计划里新增的界面文字直接写中文,不新增 `_()` 词条(现有 `_('Comments')` 保持不动)。
- 评论正文长度上限 1000(沿用 `Length(1, 1000)`)。
- 允许的评论标签:`a blockquote br code em li ol p pre strong ul`;链接协议仅 `http https mailto`;链接一律 `rel="nofollow ugc noopener" target="_blank"`;不允许图片、标题、原始 HTML(原始 HTML 当文字原样显示)。
- 状态只有 `pending` 和 `approved`。
- 回复只有两层:顶层评论 + 平铺的回复;回复回复时 `parent_id` 指向其顶层评论,正文开头自动补 `@昵称 `。
- 站长(`current_user.is_admin`)发的评论直接 `approved` 并记录 `user_id`;其他人 `user_id` 为空。
- 免审:同一邮箱此前有 `approved` 且 `user_id IS NULL` 的评论,并且新评论链接数 ≤ 2。其他情况 `pending`。站长自己的邮箱不给他人带来免审资格。
- 限流:每个 `ip_hash` 每分钟 3 条、每小时 20 条(`COMMENTS_PER_MINUTE_PER_IP`、`COMMENTS_PER_HOUR_PER_IP`);表单最短填写 3 秒(`COMMENTS_MIN_FILL_SECONDS`);蜜罐字段 `website`。蜜罐或太快的提交静默丢弃(不入库,页面表现得像「已提交待审」)。
- 关闭评论后:提交一律 403;已通过评论只读展示并标注「评论已关闭」;一条都没有时整个评论区隐藏。
- `PostComment` 的多归属关系**不要**用 `delete-orphan`(多个父关系会让 SQLAlchemy 判定孤儿而报错),一律 `cascade='all, delete'`。
- 提交代码时遵循现有风格:单引号、4 空格缩进、中文注释极少(参考 `app/likes.py` 的英文 docstring)。
- 每个任务结束时必须跑 `source .venv/bin/activate && python -m pytest tests -q`,全绿再提交。

## 前置说明

- 工作区开始时有两处未提交改动(顶部菜单去掉「分类」、设计文档)。提交前先问用户要不要和本计划的第一个提交合并。
- 相对设计文档有两处刻意的偏离,计划完成后在设计文档里同步:
  1. 文章的「允许评论」做成独立开关按钮(不进草稿流程,点击立即生效),页面的「允许评论」仍是编辑表单里的复选框。
  2. 点「回复」时表单不搬到评论下方,而是留在原位,显示「回复 @某人 ✕」并滚动聚焦;无 JS 时用 `?reply=ID#comment-form` 链接达到同样效果。

## File Structure

| 文件 | 职责 |
| --- | --- |
| `app/models.py`(改) | `PostComment` 新字段与关系;`Post`/`Page` 的 `comments_enabled` 与 `comments` |
| `migrations/versions/a1d9c3e5f7b2_comment_replies_moderation_pages.py`(新) | 数据库迁移 |
| `config.py`(改) | 三个防刷阈值 |
| `app/likes.py`(改) | 新增公开函数 `hash_address()` |
| `app/comment_markdown.py`(新) | `render_comment(text) -> Markup` |
| `app/comments.py`(新) | 提交规则、审核决策、线程查询、表单令牌 |
| `app/forms.py`(改) | `PostCommentForm` 新字段 |
| `app/routes.py`(改) | 文章/页面评论提交与渲染 |
| `app/templates/_comments.html`(新) | 共用评论区 |
| `app/templates/post/post.html`、`page/content.html`(改) | 引入评论区 |
| `app/static/comment-reply.js`(新)、`style.css`(改) | 回复交互与样式 |
| `app/admin/forms.py`、`pages.py`、`app/pages.py`、`templates/admin/pages/form.html`(改) | 页面评论开关 |
| `app/admin/posts.py`、`templates/admin/posts/{list,form}.html`(改) | 文章评论开关 |
| `app/admin/modules.py`、`templates/admin/comments/list.html`(改) | 后台评论管理 |
| `app/admin/routes.py`(改) | 仪表盘待审数 |

---

### Task 1: 数据模型与迁移

**Files:**
- Modify: `app/models.py`(`PostComment` 约 215-229 行、`Post.comments` 约 147 行、`Page` 约 254-285 行)
- Create: `migrations/versions/a1d9c3e5f7b2_comment_replies_moderation_pages.py`
- Modify: `config.py:74-76`
- Modify: `tests/conftest.py`(`application` fixture)
- Modify: `tests/test_migrations.py`
- Create: `tests/test_comment_model.py`

**Interfaces:**
- Produces: `PostComment` 新增 `page_id`、`parent_id`、`status`(`'pending'|'approved'`)、`user_id`、`ip_hash`,关系 `page`、`parent`、`replies`、`user`;`Post.comments_enabled`(默认 True)、`Page.comments_enabled`(默认 False)、`Page.comments`。配置 `COMMENTS_PER_MINUTE_PER_IP=3`、`COMMENTS_PER_HOUR_PER_IP=20`、`COMMENTS_MIN_FILL_SECONDS=3`。

- [ ] **Step 1: 写模型的失败测试**

创建 `tests/test_comment_model.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Page, Post, PostComment


def make_page(**values):
    page = Page(title='About', slug='about', kind='content',
                is_published=True, **values)
    db.session.add(page)
    db.session.commit()
    return page


def test_comment_can_belong_to_a_page(application, users):
    with application.app_context():
        page = make_page()
        comment = PostComment(
            page=page, name='R', email='r@example.com', body='Hi')
        db.session.add(comment)
        db.session.commit()

        assert comment.post_id is None
        assert comment.page_id == page.id
        assert comment.status == 'approved'
        assert page.comments == [comment]


def test_comment_needs_exactly_one_target(application, users):
    with application.app_context():
        page = make_page()
        db.session.add(PostComment(name='R', email='r@example.com', body='Hi'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        db.session.add(PostComment(
            post_id=users['post'], page_id=page.id,
            name='R', email='r@example.com', body='Hi'))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_status_rejects_unknown_values(application, users):
    with application.app_context():
        db.session.add(PostComment(
            post_id=users['post'], name='R', email='r@example.com',
            body='Hi', status='spam'))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_replies_are_deleted_with_their_parent(application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        top = PostComment(post=post, name='A', email='a@example.com', body='top')
        reply = PostComment(
            post=post, parent=top, name='B', email='b@example.com', body='re')
        db.session.add_all([top, reply])
        db.session.commit()
        assert top.replies == [reply]

        db.session.delete(top)
        db.session.commit()
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_deleting_a_page_removes_its_comments(application, users):
    with application.app_context():
        page = make_page()
        db.session.add(PostComment(
            page=page, name='R', email='r@example.com', body='Hi'))
        db.session.commit()

        db.session.delete(page)
        db.session.commit()
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_comments_are_open_on_posts_and_closed_on_pages_by_default(
        application, users):
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True
        assert make_page().comments_enabled is False
```

- [ ] **Step 2: 运行,确认失败**

Run: `source .venv/bin/activate && python -m pytest tests/test_comment_model.py -q`
Expected: FAIL(`PostComment` 没有 `page`、`comments_enabled` 等)

- [ ] **Step 3: 改模型**

`app/models.py` 中把 `Post.comments` 关系改为(去掉 `delete-orphan`):

```python
    comments: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='post', cascade='all, delete',
        order_by='PostComment.timestamp')
```

在 `Post` 的 `is_published` 字段后面加:

```python
    comments_enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true())
```

把 `PostComment` 整个类替换为:

```python
class PostComment(db.Model):
    __table_args__ = (
        sa.CheckConstraint(
            '(post_id IS NOT NULL) <> (page_id IS NOT NULL)',
            name='ck_post_comment_target'),
        sa.CheckConstraint(
            "status IN ('pending', 'approved')", name='ck_post_comment_status'),
    )

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    # Exactly one of post_id and page_id is set.
    post_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(Post.id, ondelete='CASCADE'), index=True)
    page_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('page.id', ondelete='CASCADE'), index=True)
    # A reply points at its top-level comment; replies never nest deeper.
    parent_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('post_comment.id', ondelete='CASCADE'), index=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(64))
    email: so.Mapped[str] = so.mapped_column(sa.String(120))
    body: so.Mapped[str] = so.mapped_column(sa.Text)
    status: so.Mapped[str] = so.mapped_column(
        sa.String(10), nullable=False, default='approved',
        server_default=sa.text("'approved'"))
    # Set only when the site owner wrote it while signed in.
    user_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(User.id, ondelete='SET NULL'), index=True)
    # A keyed hash of the network address, for rate limits; never the address.
    ip_hash: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(64), index=True)
    timestamp: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc))

    post: so.Mapped[Optional[Post]] = so.relationship(back_populates='comments')
    page: so.Mapped[Optional['Page']] = so.relationship(
        back_populates='comments')
    parent: so.Mapped[Optional['PostComment']] = so.relationship(
        back_populates='replies', remote_side='PostComment.id')
    replies: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='parent', cascade='all, delete',
        order_by='PostComment.timestamp')
    user: so.Mapped[Optional[User]] = so.relationship()

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://cravatar.cn/avatar/{digest}?d=identicon&s={size}'
```

在 `Page` 类的 `show_in_nav` 字段后面加:

```python
    comments_enabled: so.Mapped[bool] = so.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false())
```

在 `Page.redirects` 关系后面加:

```python
    comments: so.Mapped[list['PostComment']] = so.relationship(
        back_populates='page', cascade='all, delete',
        order_by='PostComment.timestamp')
```

`config.py` 在 `LIKES_PER_IP_PER_POST = 3` 后面加:

```python
    # Comments one network address (hashed) may leave, and the quickest a
    # reader could plausibly fill the form in.
    COMMENTS_PER_MINUTE_PER_IP = 3
    COMMENTS_PER_HOUR_PER_IP = 20
    COMMENTS_MIN_FILL_SECONDS = 3
```

`tests/conftest.py` 的 `application` fixture 里,`app.config.update(` 增加 `COMMENTS_MIN_FILL_SECONDS=0,`(其余测试不想被「填写太快」拦住;专门测它的用例自己设成 3)。

- [ ] **Step 4: 运行模型测试**

Run: `python -m pytest tests/test_comment_model.py -q`
Expected: PASS(6 passed)

- [ ] **Step 5: 写迁移的失败测试**

在 `tests/test_migrations.py` 末尾追加,并把 `test_site_text_revision_is_the_only_head` 里的 `'c4e8a1f2b7d9'` 改成 `'a1d9c3e5f7b2'`:

```python
COMMENT_REVISION_PATH = Path(__file__).parents[1] / 'migrations' / 'versions' / (
    'a1d9c3e5f7b2_comment_replies_moderation_pages.py')


def load_comment_revision():
    spec = importlib.util.spec_from_file_location(
        'comment_replies', COMMENT_REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_old_comment_schema(engine):
    metadata = sa.MetaData()
    sa.Table('user', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('page', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('post', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'post_comment', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('post_id', sa.Integer,
                  sa.ForeignKey('post.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False))
    metadata.create_all(engine)


def test_comment_migration_keeps_comments_approved_and_adds_targets():
    revision = load_comment_revision()
    engine = sa.create_engine('sqlite://')
    create_old_comment_schema(engine)

    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
        connection.execute(sa.text('INSERT INTO page (id) VALUES (1)'))
        connection.execute(sa.text(
            "INSERT INTO post_comment (id, post_id, name, email, body, timestamp)"
            " VALUES (1, 1, 'A', 'a@example.com', 'hi', '2026-01-01 00:00:00')"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

            inspector = sa.inspect(connection)
            columns = {c['name']: c for c in inspector.get_columns('post_comment')}
            assert {'page_id', 'parent_id', 'status', 'user_id', 'ip_hash'} <= set(columns)
            assert columns['post_id']['nullable'] is True
            assert 'comments_enabled' in {c['name'] for c in inspector.get_columns('post')}
            assert 'comments_enabled' in {c['name'] for c in inspector.get_columns('page')}

            assert connection.execute(sa.text(
                'SELECT status, post_id FROM post_comment')).one() == ('approved', 1)
            assert connection.execute(sa.text(
                'SELECT comments_enabled FROM post')).scalar_one() == 1
            assert connection.execute(sa.text(
                'SELECT comments_enabled FROM page')).scalar_one() == 0

            connection.execute(sa.text(
                "INSERT INTO post_comment (id, page_id, name, email, body, timestamp)"
                " VALUES (2, 1, 'B', 'b@example.com', 'on a page', '2026-01-02 00:00:00')"))
            with pytest.raises(sa.exc.IntegrityError):
                with connection.begin_nested():
                    connection.execute(sa.text(
                        "INSERT INTO post_comment (id, name, email, body, timestamp)"
                        " VALUES (3, 'C', 'c@example.com', 'nowhere', '2026-01-03 00:00:00')"))


def test_comment_migration_downgrade_drops_what_old_schema_cannot_hold():
    revision = load_comment_revision()
    engine = sa.create_engine('sqlite://')
    create_old_comment_schema(engine)

    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO post (id) VALUES (1)'))
        connection.execute(sa.text('INSERT INTO page (id) VALUES (1)'))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, post_id, name, email, body, status, timestamp)"
                " VALUES (1, 1, 'A', 'a@example.com', 'kept', 'approved', '2026-01-01 00:00:00'),"
                " (2, 1, 'B', 'b@example.com', 'pending', 'pending', '2026-01-02 00:00:00')"))
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, post_id, parent_id, name, email, body, status, timestamp)"
                " VALUES (3, 1, 1, 'C', 'c@example.com', 'a reply', 'approved', '2026-01-03 00:00:00')"))
            connection.execute(sa.text(
                "INSERT INTO post_comment (id, page_id, name, email, body, status, timestamp)"
                " VALUES (4, 1, 'D', 'd@example.com', 'on a page', 'approved', '2026-01-04 00:00:00')"))

            revision.downgrade()

            inspector = sa.inspect(connection)
            names = {c['name'] for c in inspector.get_columns('post_comment')}
            assert names == {'id', 'post_id', 'name', 'email', 'body', 'timestamp'}
            assert 'comments_enabled' not in {c['name'] for c in inspector.get_columns('post')}
            assert 'comments_enabled' not in {c['name'] for c in inspector.get_columns('page')}
            assert connection.execute(sa.text(
                'SELECT id FROM post_comment')).scalars().all() == [1]
```

- [ ] **Step 6: 运行,确认失败**

Run: `python -m pytest tests/test_migrations.py -q -k "comment_migration or only_head"`
Expected: FAIL(迁移文件不存在)

- [ ] **Step 7: 写迁移**

创建 `migrations/versions/a1d9c3e5f7b2_comment_replies_moderation_pages.py`:

```python
"""comment replies, moderation, page comments and per-item switches"""
from alembic import op
import sqlalchemy as sa


revision = 'a1d9c3e5f7b2'
down_revision = 'c4e8a1f2b7d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('post') as batch:
        batch.add_column(sa.Column(
            'comments_enabled', sa.Boolean(), nullable=False,
            server_default=sa.true()))
    with op.batch_alter_table('page') as batch:
        batch.add_column(sa.Column(
            'comments_enabled', sa.Boolean(), nullable=False,
            server_default=sa.false()))
    with op.batch_alter_table('post_comment') as batch:
        batch.alter_column('post_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('page_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column(
            'status', sa.String(length=10), nullable=False,
            server_default='approved'))
        batch.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('ip_hash', sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            'fk_post_comment_page_id_page', 'page', ['page_id'], ['id'],
            ondelete='CASCADE')
        batch.create_foreign_key(
            'fk_post_comment_parent_id_post_comment', 'post_comment',
            ['parent_id'], ['id'], ondelete='CASCADE')
        batch.create_foreign_key(
            'fk_post_comment_user_id_user', 'user', ['user_id'], ['id'],
            ondelete='SET NULL')
        batch.create_index('ix_post_comment_page_id', ['page_id'])
        batch.create_index('ix_post_comment_parent_id', ['parent_id'])
        batch.create_index('ix_post_comment_user_id', ['user_id'])
        batch.create_index('ix_post_comment_ip_hash', ['ip_hash'])
        batch.create_check_constraint(
            'ck_post_comment_target',
            '(post_id IS NOT NULL) <> (page_id IS NOT NULL)')
        batch.create_check_constraint(
            'ck_post_comment_status', "status IN ('pending', 'approved')")


def downgrade():
    # The old schema has no replies, pages or review queue: drop what it
    # cannot hold rather than show unreviewed comments as published.
    op.execute(
        "DELETE FROM post_comment WHERE page_id IS NOT NULL "
        "OR parent_id IS NOT NULL OR status = 'pending'")
    with op.batch_alter_table('post_comment') as batch:
        batch.drop_constraint('ck_post_comment_status', type_='check')
        batch.drop_constraint('ck_post_comment_target', type_='check')
        batch.drop_index('ix_post_comment_ip_hash')
        batch.drop_index('ix_post_comment_user_id')
        batch.drop_index('ix_post_comment_parent_id')
        batch.drop_index('ix_post_comment_page_id')
        batch.drop_constraint('fk_post_comment_user_id_user', type_='foreignkey')
        batch.drop_constraint(
            'fk_post_comment_parent_id_post_comment', type_='foreignkey')
        batch.drop_constraint('fk_post_comment_page_id_page', type_='foreignkey')
        batch.drop_column('ip_hash')
        batch.drop_column('user_id')
        batch.drop_column('status')
        batch.drop_column('parent_id')
        batch.drop_column('page_id')
        batch.alter_column('post_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('page') as batch:
        batch.drop_column('comments_enabled')
    with op.batch_alter_table('post') as batch:
        batch.drop_column('comments_enabled')
```

- [ ] **Step 8: 运行迁移测试与全部测试**

Run: `python -m pytest tests/test_migrations.py tests/test_comment_model.py -q`
Expected: PASS

Run: `python -m pytest tests -q`
Expected: 全部 PASS(原 817 + 新增)。`test_db_isolation_config` 之类若因新配置项失败,按失败信息核对后再改。

- [ ] **Step 9: 用迁移生成一致性检查模型与迁移没有漂移**

Run: `rm -f /tmp/drift.sqlite3 && DATABASE_URL=sqlite:////tmp/drift.sqlite3 flask db upgrade && DATABASE_URL=sqlite:////tmp/drift.sqlite3 flask db migrate -m drift --rev-id zzzz 2>&1 | tail -5; ls migrations/versions | grep zzzz`
Expected: 输出 `No changes in schema detected`,且 `migrations/versions` 里没有 `zzzz_*.py`。如果生成了该文件,把它里面的差异合并回 `a1d9c3e5f7b2` 之后删掉该文件。(临时库用后删除:`rm -f /tmp/drift.sqlite3`)

- [ ] **Step 10: 提交**

```bash
git add app/models.py config.py migrations/versions/a1d9c3e5f7b2_comment_replies_moderation_pages.py tests/conftest.py tests/test_migrations.py tests/test_comment_model.py
git commit -m "feat(comments): comments can reply, wait for review and belong to pages"
```

---

### Task 2: 评论 Markdown 渲染

**Files:**
- Create: `app/comment_markdown.py`
- Modify: `app/__init__.py:37`(注册模板过滤器)
- Create: `tests/test_comment_markdown.py`

**Interfaces:**
- Produces: `render_comment(text: str) -> markupsafe.Markup`;模板过滤器 `comment_markdown`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_comment_markdown.py`:

```python
from app.comment_markdown import render_comment


def test_allowed_formatting_is_rendered():
    html = str(render_comment('**b** *i* `c`\nsecond line'))
    assert '<strong>b</strong>' in html
    assert '<em>i</em>' in html
    assert '<code>c</code>' in html
    assert '<br>' in html


def test_quotes_lists_and_code_blocks():
    assert '<blockquote>' in str(render_comment('> quoted'))
    assert '<li>a</li>' in str(render_comment('- a\n- b'))
    assert '<pre><code>print(1)' in str(render_comment('```py\nprint(1)\n```'))


def test_raw_html_is_shown_as_text():
    html = str(render_comment('<script>alert(1)</script>Hello'))
    assert '<script' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;Hello' in html
    assert '<img' not in str(render_comment('<img src=x onerror=alert(1)>'))


def test_ampersands_and_comparisons_survive():
    html = str(render_comment('a & b <3 and 1 > 0'))
    assert 'a &amp; b &lt;3 and 1 &gt; 0' in html


def test_images_and_headings_are_not_allowed():
    assert '<img' not in str(render_comment('![x](http://example.com/x.png)'))
    html = str(render_comment('# Title'))
    assert '<h1' not in html and 'Title' in html


def test_links_are_marked_untrusted_and_open_elsewhere():
    html = str(render_comment('[x](https://example.com/a)'))
    assert 'href="https://example.com/a"' in html
    assert 'rel="nofollow ugc noopener"' in html
    assert 'target="_blank"' in html


def test_bare_urls_become_links_but_not_inside_code():
    assert 'href="https://example.com"' in str(render_comment('see https://example.com now'))
    assert '<a' not in str(render_comment('`https://example.com`'))


def test_dangerous_link_protocols_lose_their_href():
    html = str(render_comment('[x](javascript:alert(1))'))
    assert 'javascript:' not in html
    assert 'href=' not in html


def test_empty_text_renders_nothing():
    assert str(render_comment('')) == ''
    assert str(render_comment(None)) == ''
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m pytest tests/test_comment_markdown.py -q`
Expected: FAIL(`ModuleNotFoundError: app.comment_markdown`)

- [ ] **Step 3: 实现**

创建 `app/comment_markdown.py`:

```python
"""Comment text is Markdown, narrowed to what a comment needs.

Raw HTML is shown as text (it is escaped before Markdown sees it), bleach then
drops everything outside a short tag list, and every link is marked untrusted.
"""
import bleach
import markdown
from markupsafe import Markup

ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'li', 'ol', 'p', 'pre', 'strong',
    'ul',
}
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}
ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}
LINK_REL = 'nofollow ugc noopener'


def _mark_link(attrs, new=False):
    attrs[(None, 'rel')] = LINK_REL
    attrs[(None, 'target')] = '_blank'
    return attrs


def render_comment(text):
    source = (text or '').replace('&', '&amp;').replace('<', '&lt;')
    rendered = markdown.markdown(
        source, extensions=['fenced_code', 'nl2br'], output_format='html')
    cleaned = bleach.clean(
        rendered, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS, strip=True)
    linked = bleach.linkify(
        cleaned, callbacks=[_mark_link], skip_tags={'pre', 'code'},
        parse_email=False)
    return Markup(linked)
```

在 `app/__init__.py` 第 37 行 `app.jinja_env.filters['render_content'] = render_content` 后面,按同样方式加:

```python
from app.comment_markdown import render_comment  # noqa: E402
app.jinja_env.filters['comment_markdown'] = render_comment
```

(先看 `app/__init__.py` 里该行附近的 import 写法,保持一致:如果其他 import 都在文件靠后位置,就放在 `from app.content import render_content` 同一块。)

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_comment_markdown.py -q`
Expected: PASS(9 passed)

- [ ] **Step 5: 提交**

```bash
git add app/comment_markdown.py app/__init__.py tests/test_comment_markdown.py
git commit -m "feat(comments): render comment text as narrowed Markdown"
```

---

### Task 3: 提交规则服务

**Files:**
- Modify: `app/likes.py`(新增 `hash_address`,`toggle_like` 改用它)
- Create: `app/comments.py`
- Create: `tests/test_comment_service.py`

**Interfaces:**
- Consumes: `PostComment`、`Post`、`Page`(Task 1);配置三个阈值。
- Produces(Task 4、6 使用,签名固定):
  - 常量 `APPROVED = 'approved'`、`PENDING = 'pending'`、`DROPPED = 'dropped'`
  - `class CommentsClosed(Exception)`、`class CommentRejected(Exception)`(`str(exc)` 是可直接展示给读者的中文)
  - `@dataclass(frozen=True) class Submission: outcome: str; comment: PostComment | None = None`
  - `@dataclass(frozen=True) class Thread: comment: PostComment; replies: list[PostComment]`
  - `make_form_token() -> str`
  - `count_links(body: str) -> int`
  - `submit_comment(target, *, name, email, body, parent_id=None, honeypot='', form_token='', author=None) -> Submission`(`target` 是 `Post` 或 `Page`;`author` 是已登录的 `User` 或 `None`;站长 = `author is not None and author.is_admin`;成功时 comment 已 `db.session.add` 并 `flush`,**不 commit**)
  - `approved_threads(target) -> tuple[list[Thread], int]`(第二项是已通过评论总数,含回复)
  - `find_reply_target(target, comment_id) -> PostComment | None`(已通过、同归属的评论;用于 `?reply=`)
  - `likes.hash_address() -> str`

- [ ] **Step 1: 给 likes 加公开函数(先写测试再改)**

在 `tests/test_comment_service.py` 先放入全部测试(下一步骤一起用),此步骤只改 `app/likes.py`:把

```python
    address = _digest('ip', request.remote_addr or '')
```

改成

```python
    address = hash_address()
```

并在 `new_visitor_token` 之前新增:

```python
def hash_address():
    """A keyed hash of the requester's network address."""
    return _digest('ip', request.remote_addr or '')
```

- [ ] **Step 2: 写失败测试**

创建 `tests/test_comment_service.py`:

```python
import pytest

from app import db
from app.comments import (APPROVED, DROPPED, PENDING, CommentRejected,
                          CommentsClosed, approved_threads, count_links,
                          find_reply_target, make_form_token, submit_comment)
from app.models import Page, Post, PostComment, User


def request_context(application, address='10.0.0.1'):
    return application.test_request_context(
        '/', environ_base={'REMOTE_ADDR': address})


def make_comment(post_id, **values):
    values.setdefault('name', 'A')
    values.setdefault('email', 'a@example.com')
    values.setdefault('body', 'hello')
    comment = PostComment(post_id=post_id, **values)
    db.session.add(comment)
    db.session.commit()
    return comment


def send(post, **values):
    values.setdefault('name', 'Reader')
    values.setdefault('email', 'reader@example.com')
    values.setdefault('body', 'A fine post')
    return submit_comment(post, **values)


def test_count_links_counts_urls_and_www():
    assert count_links('no links') == 0
    assert count_links('http://a.com https://b.com www.c.com') == 3
    assert count_links('[x](https://a.com)') == 1


def test_first_comment_from_an_email_waits_for_review(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        result = send(post)
        assert result.outcome == PENDING
        assert result.comment.status == PENDING
        assert result.comment.post_id == post.id
        assert result.comment.email == 'reader@example.com'
        assert result.comment.ip_hash and len(result.comment.ip_hash) == 64


def test_email_with_an_approved_comment_is_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com')
        result = send(post, email='Reader@Example.com')
        assert result.outcome == APPROVED


def test_pending_comment_does_not_make_an_email_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com', status=PENDING)
        assert send(post).outcome == PENDING


def test_many_links_wait_even_for_a_trusted_email(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        make_comment(post.id, email='reader@example.com')
        two = send(post, body='http://a.com http://b.com')
        assert two.outcome == APPROVED
        three = send(post, body='http://a.com http://b.com http://c.com')
        assert three.outcome == PENDING


def test_site_owner_is_approved_and_recorded(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        result = send(post, author=admin, name='admin',
                      email='admin@example.com',
                      body='http://a.com http://b.com http://c.com')
        assert result.outcome == APPROVED
        assert result.comment.user_id == admin.id


def test_a_site_owners_address_does_not_make_others_trusted(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        send(post, author=admin, name='admin', email='admin@example.com')
        assert send(post, email='admin@example.com').outcome == PENDING


def test_non_admin_signed_in_user_is_a_guest(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        author = db.session.get(User, users['author'])
        result = send(post, author=author, email='author@example.com')
        assert result.outcome == PENDING
        assert result.comment.user_id is None


def test_closed_comments_refuse_everyone(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        post.comments_enabled = False
        admin = db.session.get(User, users['admin'])
        with pytest.raises(CommentsClosed):
            send(post)
        with pytest.raises(CommentsClosed):
            send(post, author=admin)


def test_honeypot_is_dropped_without_a_row(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        result = send(post, honeypot='http://spam.example')
        assert result.outcome == DROPPED and result.comment is None
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PostComment)) == 0


def test_form_filled_too_fast_or_without_token_is_dropped(application, users):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        assert send(post, form_token='').outcome == DROPPED
        assert send(post, form_token='garbage').outcome == DROPPED
        assert send(post, form_token=make_form_token()).outcome == DROPPED


def test_form_filled_slowly_enough_is_accepted(application, users, monkeypatch):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        token = make_form_token()
        import app.comments as comments
        real = comments.time.time
        monkeypatch.setattr(comments.time, 'time', lambda: real() + 10)
        post = db.session.get(Post, users['post'])
        assert send(post, form_token=token).outcome == PENDING


def test_site_owner_skips_the_bot_checks(application, users):
    application.config['COMMENTS_MIN_FILL_SECONDS'] = 3
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        admin = db.session.get(User, users['admin'])
        assert send(post, author=admin, form_token='').outcome == APPROVED


def test_per_minute_limit_per_address(application, users):
    application.config['COMMENTS_PER_MINUTE_PER_IP'] = 2
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='one')
        send(post, body='two')
        with pytest.raises(CommentRejected):
            send(post, body='three')
    with application.app_context(), request_context(application, '10.0.0.2'):
        post = db.session.get(Post, users['post'])
        assert send(post, body='four').outcome == PENDING


def test_per_hour_limit_per_address(application, users):
    application.config['COMMENTS_PER_MINUTE_PER_IP'] = 100
    application.config['COMMENTS_PER_HOUR_PER_IP'] = 2
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='one')
        send(post, body='two')
        with pytest.raises(CommentRejected):
            send(post, body='three')


def test_identical_body_from_the_same_address_is_refused(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        send(post, body='Buy now')
        with pytest.raises(CommentRejected):
            send(post, body='  Buy now ')


def test_reply_attaches_to_the_comment(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        top = make_comment(post.id, email='reader@example.com')
        result = send(post, parent_id=top.id)
        assert result.comment.parent_id == top.id
        assert result.comment.body == 'A fine post'


def test_reply_to_a_reply_joins_the_top_comment_with_a_mention(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        top = make_comment(post.id, email='reader@example.com')
        reply = make_comment(post.id, parent_id=top.id, name='Bob',
                             email='bob@example.com')
        result = send(post, parent_id=reply.id)
        assert result.comment.parent_id == top.id
        assert result.comment.body == '@Bob A fine post'


def test_reply_to_a_missing_pending_or_foreign_comment_is_refused(
        application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        other = Post(title='Other', body='x', author=db.session.get(
            User, users['author']), is_published=True)
        db.session.add(other)
        db.session.commit()
        waiting = make_comment(post.id, status=PENDING)
        foreign = make_comment(other.id)
        for parent_id in (9999, waiting.id, foreign.id):
            with pytest.raises(CommentRejected):
                send(post, parent_id=parent_id, body=f'body {parent_id}')


def test_comment_on_a_page(application, users):
    with application.app_context(), request_context(application):
        page = Page(title='About', slug='about', kind='content',
                    is_published=True, comments_enabled=True)
        db.session.add(page)
        db.session.commit()
        result = send(page)
        assert result.comment.page_id == page.id
        assert result.comment.post_id is None
        page.comments_enabled = False
        with pytest.raises(CommentsClosed):
            send(page, body='again')


def test_threads_list_only_approved_comments_with_their_replies(application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        first = make_comment(post.id, body='first')
        make_comment(post.id, body='hidden', status=PENDING)
        reply = make_comment(post.id, parent_id=first.id, body='reply')
        make_comment(post.id, parent_id=first.id, body='hidden reply',
                     status=PENDING)
        second = make_comment(post.id, body='second')

        threads, count = approved_threads(post)
        assert [t.comment.id for t in threads] == [first.id, second.id]
        assert [r.id for r in threads[0].replies] == [reply.id]
        assert threads[1].replies == []
        assert count == 3


def test_find_reply_target_only_returns_approved_comments_of_the_target(
        application, users):
    with application.app_context(), request_context(application):
        post = db.session.get(Post, users['post'])
        ok = make_comment(post.id)
        waiting = make_comment(post.id, status=PENDING)
        assert find_reply_target(post, ok.id) == ok
        assert find_reply_target(post, waiting.id) is None
        assert find_reply_target(post, 9999) is None
```

- [ ] **Step 3: 运行,确认失败**

Run: `python -m pytest tests/test_comment_service.py -q`
Expected: FAIL(`ModuleNotFoundError: app.comments`)

- [ ] **Step 4: 实现服务**

创建 `app/comments.py`:

```python
"""Taking comments in: who is trusted, what waits for review, what is refused.

Nothing here commits; the caller owns the transaction.
"""
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

from app import db
from app.likes import hash_address
from app.models import Post, PostComment

APPROVED, PENDING, DROPPED = 'approved', 'pending', 'dropped'
MAX_LINKS_FOR_AUTO_APPROVAL = 2
FORM_TOKEN_MAX_AGE = 24 * 60 * 60
_LINK = re.compile(r'https?://|www\.', re.IGNORECASE)


class CommentsClosed(Exception):
    """The post or page does not take comments."""


class CommentRejected(Exception):
    """Refused; the message is shown to the reader."""


@dataclass(frozen=True)
class Submission:
    outcome: str
    comment: PostComment | None = None


@dataclass(frozen=True)
class Thread:
    comment: PostComment
    replies: list


def _signer():
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'], salt='comment-form')


def make_form_token():
    """Stamped when the form is shown; a bot that posts at once is too quick."""
    return _signer().dumps(time.time())


def _filled_too_fast(token):
    minimum = current_app.config['COMMENTS_MIN_FILL_SECONDS']
    if minimum <= 0:
        return False
    try:
        shown_at = _signer().loads(token or '', max_age=FORM_TOKEN_MAX_AGE)
    except BadData:
        return True
    return time.time() - shown_at < minimum


def count_links(body):
    return len(_LINK.findall(body or ''))


def _target_filter(target):
    if isinstance(target, Post):
        return PostComment.post_id == target.id
    return PostComment.page_id == target.id


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _check_rate(ip_hash):
    config = current_app.config
    for seconds, limit in (
            (60, config['COMMENTS_PER_MINUTE_PER_IP']),
            (3600, config['COMMENTS_PER_HOUR_PER_IP'])):
        recent = db.session.scalar(sa.select(sa.func.count()).select_from(
            PostComment).where(
                PostComment.ip_hash == ip_hash,
                PostComment.timestamp >= _now() - timedelta(seconds=seconds)))
        if recent >= limit:
            raise CommentRejected('评论太频繁了，请稍后再试。')


def _check_duplicate(ip_hash, body):
    repeated = db.session.scalar(sa.select(sa.func.count()).select_from(
        PostComment).where(
            PostComment.ip_hash == ip_hash, PostComment.body == body,
            PostComment.timestamp >= _now() - timedelta(hours=1)))
    if repeated:
        raise CommentRejected('你已经提交过相同的评论了。')


def _decide_status(body, email, is_admin):
    if is_admin:
        return APPROVED
    if count_links(body) > MAX_LINKS_FOR_AUTO_APPROVAL:
        return PENDING
    known = db.session.scalar(sa.select(sa.func.count()).select_from(
        PostComment).where(
            PostComment.status == APPROVED, PostComment.user_id.is_(None),
            sa.func.lower(PostComment.email) == email))
    return APPROVED if known else PENDING


def find_reply_target(target, comment_id):
    """The approved comment of this post or page with that id, else None."""
    if not comment_id:
        return None
    return db.session.scalar(sa.select(PostComment).where(
        PostComment.id == comment_id, PostComment.status == APPROVED,
        _target_filter(target)))


def _resolve_parent(target, parent_id):
    """Returns (comment to attach to, comment being answered or None)."""
    answered = find_reply_target(target, parent_id)
    if answered is None:
        raise CommentRejected('要回复的评论不存在或还没有通过审核。')
    if answered.parent_id is None:
        return answered, None
    return answered.parent, answered


def submit_comment(target, *, name, email, body, parent_id=None, honeypot='',
                   form_token='', author=None):
    if not target.comments_enabled:
        raise CommentsClosed()
    is_admin = author is not None and author.is_admin
    ip_hash = hash_address()
    body = body.strip()
    email = email.strip().lower()

    if not is_admin:
        if honeypot or _filled_too_fast(form_token):
            return Submission(DROPPED)
        _check_rate(ip_hash)
        _check_duplicate(ip_hash, body)

    parent = None
    if parent_id:
        parent, answered = _resolve_parent(target, parent_id)
        if answered is not None and not body.startswith(f'@{answered.name} '):
            body = f'@{answered.name} {body}'

    comment = PostComment(
        name=name.strip(), email=email, body=body, parent=parent,
        status=_decide_status(body, email, is_admin), ip_hash=ip_hash,
        user_id=author.id if is_admin else None)
    if isinstance(target, Post):
        comment.post = target
    else:
        comment.page = target
    db.session.add(comment)
    db.session.flush()
    return Submission(comment.status, comment)


def approved_threads(target):
    """Top-level approved comments, oldest first, each with its replies."""
    rows = db.session.scalars(sa.select(PostComment).where(
        _target_filter(target), PostComment.status == APPROVED).order_by(
            PostComment.timestamp, PostComment.id)).all()
    replies = {}
    for comment in rows:
        if comment.parent_id is not None:
            replies.setdefault(comment.parent_id, []).append(comment)
    threads = [Thread(comment, replies.get(comment.id, []))
               for comment in rows if comment.parent_id is None]
    return threads, len(rows)
```

注意:`_decide_status` 的 `sa.func.lower(PostComment.email) == email` 要求入库邮箱都是小写——`submit_comment` 已经 `.lower()`;历史评论由旧路由也是 `.lower()` 存的。

- [ ] **Step 5: 运行测试**

Run: `python -m pytest tests/test_comment_service.py tests/test_anonymous_likes.py -q`
Expected: PASS。若 `test_reply_to_a_missing_pending_or_foreign_comment_is_refused` 因同一 IP 触发限流而失败(三次发送 + 前面的),在该测试开头加 `application.config['COMMENTS_PER_MINUTE_PER_IP'] = 100`。

- [ ] **Step 6: 提交**

```bash
git add app/likes.py app/comments.py tests/test_comment_service.py
git commit -m "feat(comments): review, rate limits and reply rules in one service"
```

---

### Task 4: 前台:提交、回复与共用评论区(文章页 + 内容页)

**Files:**
- Modify: `app/forms.py:73-78`
- Modify: `app/routes.py`(`post` 路由约 321-354 行、`public_page` 约 481-491 行、import)
- Create: `app/templates/_comments.html`
- Modify: `app/templates/post/post.html:41-87`、`app/templates/page/content.html`
- Create: `app/static/comment-reply.js`
- Modify: `app/static/style.css`(评论相关段落)
- Create: `tests/comment_reply.test.js`
- Create: `tests/test_comments_public.py`
- Modify: `tests/test_post_interactions.py:6-21`

**Interfaces:**
- Consumes: Task 3 的全部接口。
- Produces: `comment_context(target, form) -> dict`(放在 `app/comments.py` 末尾,键:`comment_threads`、`comment_count`、`comments_enabled`、`comment_reply_to`、`comment_form_token`),`_comments.html` 需要的模板变量就是这些加 `form`。

- [ ] **Step 1: 写前台失败测试**

创建 `tests/test_comments_public.py`:

```python
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


def test_a_redirect_slug_does_not_take_comments(client, application, users):
    assert client.post('/no-such-page', data={}).status_code == 404
```

- [ ] **Step 2: 更新现有测试**

`tests/test_post_interactions.py` 的 `test_guest_can_comment_without_exposing_email` 改成先放一条同邮箱的已通过评论(新邮箱首次评论现在要审核):

```python
def test_guest_can_comment_without_exposing_email(client, application, users):
    with application.app_context():
        db.session.add(PostComment(
            post_id=users['post'], name='Reader',
            email='reader@example.com', body='Earlier'))
        db.session.commit()
    response = client.post(f'/post/{users["post"]}', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'body': '<script>alert(1)</script>Hello',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Reader' in response.data
    assert b'Hello' in response.data
    assert b'reader@example.com' not in response.data
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;Hello' in response.data
    with application.app_context():
        comment = db.session.scalars(
            db.select(PostComment).order_by(PostComment.id.desc())).first()
        assert comment.post_id == users['post']
```

- [ ] **Step 3: 写回复脚本的失败测试**

创建 `tests/comment_reply.test.js`:

```javascript
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', 'comment-reply.js'),
  'utf8',
);

function createHarness({ hasForm = true } = {}) {
  const parent = { value: '' };
  const note = { hidden: true };
  const name = { textContent: '' };
  const body = { focused: false, focus() { this.focused = true; } };
  const form = {
    scrolled: false,
    scrollIntoView() { this.scrolled = true; },
    querySelector(selector) {
      return {
        '[data-reply-parent]': parent,
        '[data-reply-note]': note,
        '[data-reply-name]': name,
        '[data-comment-body]': body,
      }[selector] || null;
    },
  };
  let clickHandler;
  const document = {
    querySelector: (selector) => (hasForm && selector === '[data-comment-form]' ? form : null),
    addEventListener(type, handler) { if (type === 'click') clickHandler = handler; },
  };
  vm.runInNewContext(source, { document });
  const click = (selector, dataset = {}) => {
    let prevented = false;
    const element = { dataset };
    clickHandler({
      target: { closest: (wanted) => (wanted === selector ? element : null) },
      preventDefault() { prevented = true; },
    });
    return prevented;
  };
  return { parent, note, name, body, form, click, hasHandler: () => Boolean(clickHandler) };
}

test('clicking reply targets the comment and focuses the form', () => {
  const harness = createHarness();
  const prevented = harness.click('[data-reply-link]', { replyId: '7', replyName: 'Ann' });

  assert.equal(prevented, true);
  assert.equal(harness.parent.value, '7');
  assert.equal(harness.name.textContent, 'Ann');
  assert.equal(harness.note.hidden, false);
  assert.equal(harness.form.scrolled, true);
  assert.equal(harness.body.focused, true);
});

test('cancel clears the reply target', () => {
  const harness = createHarness();
  harness.click('[data-reply-link]', { replyId: '7', replyName: 'Ann' });
  const prevented = harness.click('[data-reply-cancel]');

  assert.equal(prevented, true);
  assert.equal(harness.parent.value, '');
  assert.equal(harness.note.hidden, true);
});

test('clicks elsewhere are left alone', () => {
  const harness = createHarness();
  assert.equal(harness.click('[data-unrelated]'), false);
  assert.equal(harness.parent.value, '');
});

test('pages without a comment form do nothing', () => {
  assert.equal(createHarness({ hasForm: false }).hasHandler(), false);
});
```

- [ ] **Step 4: 运行,确认全部失败**

Run: `python -m pytest tests/test_comments_public.py tests/test_post_interactions.py -q; node --test tests/comment_reply.test.js`
Expected: FAIL

- [ ] **Step 5: 表单字段**

`app/forms.py` 里把 `PostCommentForm` 换成(并在文件头 import 补 `HiddenField`、`IntegerField`、`from wtforms.widgets import HiddenInput`,若已存在则不重复):

```python
class PostCommentForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(1, 64)])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    body = TextAreaField(_l('Comment'), validators=[
        DataRequired(), Length(1, 1000)])
    # The comment being answered; empty for a new top-level comment.
    parent_id = IntegerField(widget=HiddenInput(), validators=[Optional()])
    # Bait for bots: humans never see or fill it.
    website = StringField()
    form_token = HiddenField()
    submit = SubmitField(_l('Publish comment'))
```

- [ ] **Step 6: 前台上下文函数**

在 `app/comments.py` 末尾追加:

```python
def comment_context(target, form):
    """What the shared comment section template needs."""
    threads, count = approved_threads(target)
    reply_to = None
    if target.comments_enabled:
        reply_id = form.parent_id.data or request.args.get('reply', type=int)
        reply_to = find_reply_target(target, reply_id)
    return {
        'comment_threads': threads,
        'comment_count': count,
        'comments_enabled': target.comments_enabled,
        'comment_reply_to': reply_to,
        'comment_form_token': make_form_token(),
    }
```

并把文件头 `from flask import current_app` 改为 `from flask import current_app, request`。

- [ ] **Step 7: 路由**

`app/routes.py` import 部分补:

```python
from app.comments import (APPROVED, CommentRejected, CommentsClosed,
                          comment_context, submit_comment)
```

(若 `abort` 还没从 flask 导入则补上。)在 `post` 路由之前新增共用函数:

```python
def _take_comment(target, form, destination):
    """Handle a posted comment. Returns a redirect, or None to show the form again."""
    if not target.comments_enabled:
        abort(403)
    if not form.validate_on_submit():
        return None
    try:
        result = submit_comment(
            target, name=form.name.data, email=form.email.data,
            body=form.body.data, parent_id=form.parent_id.data,
            honeypot=form.website.data, form_token=form.form_token.data,
            author=current_user if current_user.is_authenticated else None)
    except CommentsClosed:
        abort(403)
    except CommentRejected as exc:
        form.body.errors.append(str(exc))
        return None
    db.session.commit()
    if result.outcome == APPROVED:
        flash('你的评论已发布。')
        return redirect(destination(f'comment-{result.comment.id}'))
    flash('评论已提交，审核通过后显示。')
    return redirect(destination('comments'))
```

把 `post` 路由中评论处理那段(`form = PostCommentForm()` 到 `return redirect(...)` 的 `if form.validate_on_submit():` 块)换成:

```python
    form = PostCommentForm()
    if current_user.is_authenticated and request.method == 'GET':
        form.name.data = current_user.username
        form.email.data = current_user.email
    if request.method == 'POST':
        taken = _take_comment(
            post, form, lambda anchor: url_for('post', post_id=post.id, _anchor=anchor))
        if taken is not None:
            return taken
```

并把 `render_template('post/post.html', ...)` 里的 `form=form, comments=post.comments,` 换成 `form=form, **comment_context(post, form),`(保留 `liked=` 等其他参数)。

`public_page` 路由改为接收 POST:

```python
@app.route('/<slug>', methods=['GET', 'POST'])
def public_page(slug):
    resolved = page_for_public_slug(slug)
    if resolved is None:
        abort(404)
    page, is_redirect = resolved
    if is_redirect:
        if request.method == 'POST':
            abort(404)
        return _redirect_to_public_page(page)
    if page.kind != PAGE_CONTENT:
        abort(404)
    form = PostCommentForm()
    if current_user.is_authenticated and request.method == 'GET':
        form.name.data = current_user.username
        form.email.data = current_user.email
    if request.method == 'POST':
        taken = _take_comment(
            page, form, lambda anchor: url_for('public_page', slug=page.slug, _anchor=anchor))
        if taken is not None:
            return taken
    return render_template(
        'page/content.html', title=page.title, page=page, form=form,
        **comment_context(page, form))
```

- [ ] **Step 8: 共用评论区模板**

创建 `app/templates/_comments.html`:

```jinja
{% macro comment_item(comment, can_reply, is_reply=False) %}
<article class="post-comment{% if is_reply %} post-comment--reply{% endif %}" id="comment-{{ comment.id }}">
    <img src="{{ comment.avatar(36 if is_reply else 48) }}" width="{{ 36 if is_reply else 48 }}" height="{{ 36 if is_reply else 48 }}" alt="">
    <div class="post-comment__body">
        <header>
            <strong>{{ comment.name }}</strong>
            {% if comment.user_id %}<span class="comment-badge">作者</span>{% endif %}
            <time>{{ moment(comment.timestamp).fromNow() }}</time>
        </header>
        <div class="post-comment__text">{{ comment.body|comment_markdown }}</div>
        {% if can_reply %}
        <a class="comment-reply" href="{{ request.path }}?reply={{ comment.id }}#comment-form"
           data-reply-link data-reply-id="{{ comment.id }}" data-reply-name="{{ comment.name }}">回复</a>
        {% endif %}
    </div>
</article>
{% endmacro %}

{% if comments_enabled or comment_count %}
<section class="comments-section" id="comments" aria-labelledby="comments-title">
    <header class="comments-section__heading">
        <h2 id="comments-title">{{ _('Comments') }}</h2>
        <span>{{ comment_count }}</span>
        {% if not comments_enabled %}<span class="comments-closed">评论已关闭</span>{% endif %}
    </header>

    {% if comments_enabled %}
    <form method="post" class="comment-form" id="comment-form" data-comment-form novalidate>
        {{ form.csrf_token }}
        <input type="hidden" name="parent_id" value="{{ form.parent_id.data or '' }}" data-reply-parent>
        <input type="hidden" name="form_token" value="{{ comment_form_token }}">
        <p class="comment-reply-note" data-reply-note{% if not comment_reply_to %} hidden{% endif %}>
            回复 <strong data-reply-name>{{ comment_reply_to.name if comment_reply_to else '' }}</strong>
            <a href="{{ request.path }}#comment-form" data-reply-cancel>取消</a>
        </p>
        <div class="comment-form__identity">
            <div>
                {{ form.name.label(class="form-label") }}
                {{ form.name(class="form-control", autocomplete="name") }}
                {% for error in form.name.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
            </div>
            <div>
                {{ form.email.label(class="form-label") }}
                {{ form.email(class="form-control", autocomplete="email") }}
                {% for error in form.email.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
            </div>
        </div>
        <div class="comment-form__trap" aria-hidden="true">
            <label>网址 <input type="text" name="website" tabindex="-1" autocomplete="off"></label>
        </div>
        <div>
            {{ form.body.label(class="form-label") }}
            {{ form.body(class="form-control", rows="4", data_comment_body="") }}
            <p class="form-text">支持 Markdown：粗体、斜体、代码、引用、列表和链接。</p>
            {% for error in form.body.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
        </div>
        {{ form.submit(class="btn btn-primary") }}
    </form>
    <script src="{{ url_for('static', filename='comment-reply.js') }}" defer></script>
    {% endif %}

    <div class="comment-list">
        {% for thread in comment_threads %}
        {{ comment_item(thread.comment, comments_enabled) }}
        {% if thread.replies %}
        <div class="post-comment__replies">
            {% for reply in thread.replies %}{{ comment_item(reply, comments_enabled, True) }}{% endfor %}
        </div>
        {% endif %}
        {% else %}
        <p class="comments-empty">{{ _('No comments yet.') }}</p>
        {% endfor %}
    </div>
</section>
{% endif %}
```

`post/post.html`:把 `<section class="comments-section" ...>` 到对应 `</section>` 整段(41-87 行)替换为一行 `{% include '_comments.html' %}`。`like` 表单里用到的 `form.csrf_token.current_token` 不变。

`page/content.html` 在 `</article>` 之后、`{% endblock %}` 之前加 `{% include '_comments.html' %}`,并确认 `base.html` 已经提供 `moment`(文章页已用,基础模板里有 `moment.include_moment()`)。

- [ ] **Step 9: 回复脚本**

创建 `app/static/comment-reply.js`:

```javascript
(() => {
  const form = document.querySelector('[data-comment-form]');
  if (!form) return;

  const parent = form.querySelector('[data-reply-parent]');
  const note = form.querySelector('[data-reply-note]');
  const name = form.querySelector('[data-reply-name]');
  const body = form.querySelector('[data-comment-body]');

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-reply-link]');
    if (link) {
      event.preventDefault();
      parent.value = link.dataset.replyId;
      name.textContent = link.dataset.replyName;
      note.hidden = false;
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
      body.focus();
      return;
    }
    if (event.target.closest('[data-reply-cancel]')) {
      event.preventDefault();
      parent.value = '';
      note.hidden = true;
    }
  });
})();
```

- [ ] **Step 10: 样式**

在 `app/static/style.css` 里:
1. 把 `.post-comment p { margin: 0.45rem 0 0; white-space: pre-wrap; }` 改为:

```css
.post-comment__text {
    margin-top: 0.45rem;
    overflow-wrap: anywhere;
}

.post-comment__text > :first-child { margin-top: 0; }
.post-comment__text > :last-child { margin-bottom: 0; }

.post-comment__text blockquote {
    margin: 0.5rem 0;
    padding-left: 0.9rem;
    border-left: 3px solid var(--border);
    color: var(--text-secondary);
}

.post-comment__text pre {
    overflow-x: auto;
    padding: 0.6rem 0.8rem;
    border-radius: 6px;
}
```

2. 在 `.comments-empty` 规则之后追加:

```css
.comment-badge {
    margin-left: 0.4rem;
    padding: 0 0.4rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text-secondary);
    font-size: 0.75rem;
}

.comment-reply {
    display: inline-block;
    margin-top: 0.4rem;
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.comment-reply-note {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.comment-reply-note[hidden] { display: none; }

.comments-closed {
    margin-left: auto;
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.comment-form__trap {
    position: absolute;
    left: -10000px;
    width: 1px;
    height: 1px;
    overflow: hidden;
}

.post-comment__replies {
    margin-left: 62px;
    border-bottom: 1px solid var(--border);
}

.post-comment--reply {
    grid-template-columns: 36px 1fr;
    padding: 16px 0;
    border-bottom: 0;
}

.post-comment__replies + .post-comment { border-top: 0; }
```

并在 `@media (max-width: 767.98px)` 现有规则块内追加 `.post-comment__replies { margin-left: 24px; }`(若没有合适的媒体查询块,单独加一个)。

- [ ] **Step 11: 运行全部测试**

Run: `python -m pytest tests -q; node --test tests/*.test.js`
Expected: 全部 PASS。可能需要调整的既有断言:`tests/test_ui_shell.py::test_article_page_uses_reading_layout_and_divided_comments`(看它检查的类名),`tests/test_ui_pages.py::test_comment_textarea_does_not_opt_in_to_markdown_editor`(textarea 不能带 `data-markdown-editor`;我们加的是 `data-comment-body`,不冲突)。如果只是类名/结构断言变化,按新结构更新断言,并在提交说明里写明。

- [ ] **Step 12: 手动看一眼页面**

Run: `source .venv/bin/activate && flask run`(另一终端 `open http://127.0.0.1:5000`),打开一篇文章,确认:表单显示、点「回复」后出现「回复 @xxx 取消」并聚焦、提交后看到「审核通过后显示」。看完关掉服务。(只验证显示,不用保存截图。)

- [ ] **Step 13: 提交**

```bash
git add app/forms.py app/comments.py app/routes.py app/templates/_comments.html app/templates/post/post.html app/templates/page/content.html app/static/comment-reply.js app/static/style.css tests/comment_reply.test.js tests/test_comments_public.py tests/test_post_interactions.py
git commit -m "feat(comments): replies, review and a shared comment section for posts and pages"
```

---

### Task 5: 评论开关(文章与页面)

**Files:**
- Modify: `app/admin/forms.py`(`PageForm`)
- Modify: `app/admin/pages.py`(`_page_values`)
- Modify: `app/pages.py`(`save_page`)
- Modify: `app/templates/admin/pages/form.html:37-38`
- Modify: `app/admin/posts.py`(新路由 `toggle_post_comments`)
- Modify: `app/templates/admin/posts/list.html`、`app/templates/admin/posts/form.html`
- Create: `tests/test_comment_switch.py`

**Interfaces:**
- Consumes: `Post.comments_enabled`、`Page.comments_enabled`。
- Produces: 端点 `admin.toggle_post_comments`(`POST /admin/posts/<id>/comments`,翻转开关,支持 `next=list`);`PageForm.comments_enabled`;`save_page` 接受 `values['comments_enabled']`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_comment_switch.py`:

```python
from app import db
from app.models import Page, Post
from tests.conftest import login


def page_form(**overrides):
    data = {'title': 'About', 'slug': 'about', 'summary': '', 'body': 'hello',
            'is_published': 'y', 'nav_order': '0', 'submit': '保存'}
    data.update(overrides)
    return data


def test_post_author_can_switch_comments_off_and_on(client, application, users):
    login(client, 'author')
    url = f'/admin/posts/{users["post"]}/comments'

    assert client.post(url).status_code == 302
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is False

    assert client.post(url).status_code == 302
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True


def test_switch_returns_to_the_list_when_asked(client, users):
    login(client, 'author')
    response = client.post(
        f'/admin/posts/{users["post"]}/comments', data={'next': 'list'})
    assert response.headers['Location'].endswith('/admin/posts')


def test_other_members_cannot_switch_someone_elses_post(client, application, users):
    login(client, 'other')
    assert client.post(f'/admin/posts/{users["post"]}/comments').status_code in (403, 404)
    with application.app_context():
        assert db.session.get(Post, users['post']).comments_enabled is True


def test_switch_needs_a_signed_in_user(client, users):
    response = client.post(f'/admin/posts/{users["post"]}/comments')
    assert response.status_code in (302, 401)
    assert '/login' in response.headers.get('Location', '/login')


def test_post_list_and_editor_show_the_current_state(client, users):
    login(client, 'author')
    listing = client.get('/admin/posts').get_data(as_text=True)
    editor = client.get(f'/admin/posts/{users["post"]}/edit').get_data(as_text=True)
    for html in (listing, editor):
        assert 'data-comments-toggle' in html
        assert '关闭评论' in html

    client.post(f'/admin/posts/{users["post"]}/comments')
    assert '开启评论' in client.get('/admin/posts').get_data(as_text=True)


def test_new_page_defaults_to_comments_off_and_can_turn_them_on(client, application, users):
    login(client, 'admin')
    form = client.get('/admin/pages/new').get_data(as_text=True)
    assert 'name="comments_enabled"' in form
    assert 'name="comments_enabled" type="checkbox" value="y" checked' not in form

    client.post('/admin/pages/new', data=page_form())
    with application.app_context():
        page = db.session.scalar(db.select(Page).where(Page.slug == 'about'))
        assert page.comments_enabled is False
        page_id = page.id

    client.post(f'/admin/pages/{page_id}/edit', data=page_form(comments_enabled='y'))
    with application.app_context():
        assert db.session.get(Page, page_id).comments_enabled is True

    client.post(f'/admin/pages/{page_id}/edit', data=page_form())
    with application.app_context():
        assert db.session.get(Page, page_id).comments_enabled is False
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m pytest tests/test_comment_switch.py -q`
Expected: FAIL

- [ ] **Step 3: 页面开关**

`app/admin/forms.py` 的 `PageForm` 里,`show_in_nav` 之后加:

```python
    comments_enabled = BooleanField('允许评论')
```

`app/admin/pages.py` 的 `_page_values` 返回字典里加 `'comments_enabled': form.comments_enabled.data,`。

`app/pages.py` 的 `save_page` 在设置 `show_in_nav` 之后加:

```python
    page.comments_enabled = bool(values.get(
        'comments_enabled',
        page.comments_enabled if page.id is not None else False))
```

`app/templates/admin/pages/form.html` 的 `admin-form__checks` 里加:

```jinja
    <label>{{ form.comments_enabled() }} {{ form.comments_enabled.label.text }}</label>
```

- [ ] **Step 4: 文章开关路由**

`app/admin/posts.py` 在 `unpublish` 路由之后加(`ToggleForm` 从 `app.admin.forms` 引入,若该文件还没导入则补 `from app.admin.forms import ToggleForm`):

```python
@bp.route('/posts/<int:post_id>/comments', methods=['POST'])
@login_required
def toggle_post_comments(post_id):
    post = owned_post_or_404(post_id, current_user)
    if not ToggleForm().validate_on_submit():
        abort(400)
    post.comments_enabled = not post.comments_enabled
    _commit_post_change('评论设置保存失败，请重试。')
    flash('评论已开启。' if post.comments_enabled else '评论已关闭。')
    return _after_publication_change(post_id)
```

- [ ] **Step 5: 开关按钮**

`app/templates/admin/posts/list.html`:在「删除」`<form>` 之前加:

```jinja
      <form method="post" action="{{ url_for('admin.toggle_post_comments', post_id=post.id) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="next" value="list">
        <button class="button button--quiet" type="submit" data-comments-toggle>{{ '关闭评论' if post.comments_enabled else '开启评论' }}</button>
      </form>
```

`app/templates/admin/posts/form.html`:在发布按钮那一组(`{% if post and ... %}` 三个分支之后)里,仅 `post` 已存在时,放一个同样的表单(不带 `next`):

```jinja
  {% if post %}
  <form method="post" action="{{ url_for('admin.toggle_post_comments', post_id=post.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button class="button button--quiet" type="submit" data-comments-toggle>{{ '关闭评论' if post.comments_enabled else '开启评论' }}</button>
  </form>
  {% endif %}
```

放到 `post/form.html` 前先看那一段的结构(第 14-40 行),放在这些按钮的同一个容器里、最后一个按钮分支之后。注意:这个表单**不能**带 `data-draft-leave-action`,因为它不是离开编辑器的动作,也不应触发草稿保存逻辑。

- [ ] **Step 6: 运行测试**

Run: `python -m pytest tests/test_comment_switch.py tests/test_admin_editorial_ui.py tests/test_publication_buttons.py -q`
Expected: PASS。`test_publication_buttons` 如果统计了页面上的 `button`,按新增按钮更新断言。

- [ ] **Step 7: 提交**

```bash
git add app/admin/forms.py app/admin/pages.py app/pages.py app/admin/posts.py app/templates/admin/pages/form.html app/templates/admin/posts/list.html app/templates/admin/posts/form.html tests/test_comment_switch.py
git commit -m "feat(comments): switch comments on or off for each post and page"
```

---

### Task 6: 后台评论管理页

**Files:**
- Modify: `app/admin/forms.py`(新增 `BulkCommentForm`、`CommentReplyForm`)
- Modify: `app/admin/modules.py:71-91` 及其下方
- Modify: `app/templates/admin/comments/list.html`
- Modify: `app/admin/routes.py`(仪表盘)
- Create: `tests/test_admin_comments.py`

**Interfaces:**
- Consumes: `submit_comment`、`CommentsClosed`、`CommentRejected`(Task 3);`PostComment`、`Post`、`Page`。
- Produces: 端点 `admin.comments`(`GET /admin/comments?status=all|pending|approved&q=&target=post:ID|page:ID`)、`admin.approve_comment`(`POST /admin/comments/<id>/approve`)、`admin.delete_article_comment`(沿用 `POST /admin/comments/posts/<id>/delete`)、`admin.bulk_comments`(`POST /admin/comments/bulk`,字段 `action=approve|delete`、`ids` 多值)、`admin.reply_comment`(`POST /admin/comments/<id>/reply`,字段 `body`)。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_admin_comments.py`:

```python
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
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m pytest tests/test_admin_comments.py -q`
Expected: FAIL

- [ ] **Step 3: 表单**

`app/admin/forms.py` 末尾追加(`FieldList` 不需要;批量 id 直接读 `request.form.getlist`):

```python
class BulkCommentForm(FlaskForm):
    """CSRF-only; the action and ids are read from the request."""


class CommentReplyForm(FlaskForm):
    body = TextAreaField('回复', validators=[DataRequired(), Length(1, 1000)])
```

(确认文件头已导入 `TextAreaField`、`DataRequired`、`Length`;`PageForm` 已在用。)

- [ ] **Step 4: 视图**

`app/admin/modules.py` 把 `comments` 视图和 `delete_article_comment` 改写,并新增三个视图。文件头补:

```python
from app.admin.forms import BulkCommentForm, CommentReplyForm
from app.admin.pages import _like_pattern
from app.comments import CommentRejected, CommentsClosed, submit_comment
```

(`DeleteForm` 已在用;`Page`、`Post` 若未导入则补进 `from app.models import ...`。)

```python
COMMENT_STATUSES = ('all', 'pending', 'approved')


def _comment_target(raw):
    """Parse 'post:12' / 'page:3'; returns a SQL condition or None."""
    if not raw:
        return None
    kind, _, value = raw.partition(':')
    if kind not in ('post', 'page') or not value.isdigit():
        abort(400)
    column = PostComment.post_id if kind == 'post' else PostComment.page_id
    return column == int(value)


def _comments_back(default='admin.comments'):
    """Where to return to after an action: the list the admin came from."""
    target = request.form.get('next', '')
    if target.startswith('/admin/comments'):
        return redirect(target)
    return redirect(url_for(default))


@bp.route('/comments', methods=['GET'])
@login_required
@admin_required
def comments():
    status = request.args.get('status', 'all')
    if status not in COMMENT_STATUSES:
        abort(400)
    search = request.args.get('q', '').strip()
    target = request.args.get('target', '')
    condition = _comment_target(target)

    query = sa.select(PostComment).order_by(
        PostComment.timestamp.desc(), PostComment.id.desc())
    if status != 'all':
        query = query.where(PostComment.status == status)
    if condition is not None:
        query = query.where(condition)
    if search:
        pattern = _like_pattern(search)
        query = query.where(sa.or_(
            PostComment.name.ilike(pattern, escape='\\'),
            PostComment.email.ilike(pattern, escape='\\'),
            PostComment.body.ilike(pattern, escape='\\')))

    counts = dict(db.session.execute(sa.select(
        PostComment.status, sa.func.count()).group_by(PostComment.status)).all())
    pending = counts.get('pending', 0)
    approved = counts.get('approved', 0)
    return render_template(
        'admin/comments/list.html',
        post_comments=db.session.scalars(query).all(), status=status,
        search=search, target=target,
        tab_counts={'pending': pending, 'approved': approved,
                    'all': pending + approved},
        delete_form=DeleteForm(), bulk_form=BulkCommentForm(),
        reply_form=CommentReplyForm())


@bp.route('/comments/<int:comment_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_comment(comment_id):
    if not BulkCommentForm().validate_on_submit():
        abort(400)
    db.get_or_404(PostComment, comment_id).status = 'approved'
    if not _commit_or_flash('评论保存失败，请重试。'):
        abort(500)
    return _comments_back()


@bp.route('/comments/posts/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_article_comment(comment_id):
    if not DeleteForm().validate_on_submit():
        abort(400)
    db.session.delete(db.get_or_404(PostComment, comment_id))
    if not _commit_or_flash('评论删除失败，请重试。'):
        abort(500)
    return _comments_back()


@bp.route('/comments/bulk', methods=['POST'])
@login_required
@admin_required
def bulk_comments():
    if not BulkCommentForm().validate_on_submit():
        abort(400)
    action = request.form.get('action', '')
    raw_ids = request.form.getlist('ids')
    if action not in ('approve', 'delete') or not all(i.isdigit() for i in raw_ids):
        abort(400)
    selected = db.session.scalars(sa.select(PostComment).where(
        PostComment.id.in_([int(i) for i in raw_ids]))).all()
    for comment in selected:
        if action == 'approve':
            comment.status = 'approved'
        else:
            db.session.delete(comment)
    if not _commit_or_flash('批量操作失败，请重试。'):
        abort(500)
    flash(f'已处理 {len(selected)} 条评论。')
    return _comments_back()


@bp.route('/comments/<int:comment_id>/reply', methods=['POST'])
@login_required
@admin_required
def reply_comment(comment_id):
    form = CommentReplyForm()
    comment = db.get_or_404(PostComment, comment_id)
    if not form.validate_on_submit():
        flash('回复内容不能为空，且不超过 1000 字。')
        return _comments_back()
    target = comment.post or comment.page
    try:
        submit_comment(
            target, name=current_user.username, email=current_user.email,
            body=form.body.data, parent_id=comment.id, author=current_user)
    except CommentsClosed:
        flash('这里的评论已关闭，不能回复。')
        return _comments_back()
    except CommentRejected as exc:
        flash(str(exc))
        return _comments_back()
    if not _commit_or_flash('回复保存失败，请重试。'):
        abort(500)
    flash('回复已发布。')
    return _comments_back()
```

`modules.py` 里需要 `current_user`(`from flask_login import current_user, login_required`)、`flash`、`request`、`url_for`、`redirect`、`abort`——补齐缺的 import。

- [ ] **Step 5: 模板**

重写 `app/templates/admin/comments/list.html`:

```jinja
{% extends "admin/base.html" %}
{% block admin_title %}评论{% endblock %}
{% block admin_content %}
<nav class="admin-tabs" data-comment-tabs aria-label="评论状态">
  {% for key, label in (('pending', '待审核'), ('approved', '已通过'), ('all', '全部')) %}
  <a href="{{ url_for('admin.comments', status=key, q=search or None, target=target or None) }}"{% if status == key %} aria-current="page"{% endif %}>{{ label }} ({{ tab_counts[key] }})</a>
  {% endfor %}
</nav>

<form class="admin-filter" method="get" action="{{ url_for('admin.comments') }}">
  <input type="hidden" name="status" value="{{ status }}">
  {% if target %}<input type="hidden" name="target" value="{{ target }}">{% endif %}
  <input class="form-control" type="search" name="q" value="{{ search }}" placeholder="搜索昵称、邮箱或内容">
  <button class="button button--quiet" type="submit">搜索</button>
  {% if target %}<a href="{{ url_for('admin.comments', status=status, q=search or None) }}">清除筛选</a>{% endif %}
</form>

<form method="post" action="{{ url_for('admin.bulk_comments') }}" id="bulk-comments">
  {{ bulk_form.csrf_token }}
  <input type="hidden" name="next" value="{{ request.full_path.rstrip('?') }}">
  <div class="admin-bulk">
    <button class="button button--quiet" type="submit" name="action" value="approve">批量通过</button>
    <button class="button button--quiet button--danger" type="submit" name="action" value="delete" onclick="return confirm('确定删除所选评论？它们的回复也会一并删除。');">批量删除</button>
  </div>
</form>

<section class="admin-section"><div class="admin-list">
  {% for comment in post_comments %}
  {% set owner = comment.post or comment.page %}
  <article class="admin-list__row" data-comment-row>
    <label class="admin-list__select"><input type="checkbox" name="ids" value="{{ comment.id }}" form="bulk-comments" aria-label="选择这条评论"></label>
    <div class="admin-list__main">
      <strong class="comment-author">{{ comment.name }}</strong>
      <span>{{ comment.email }} · {{ '待审核' if comment.status == 'pending' else '已通过' }}{% if comment.user_id %} · 站长{% endif %}{% if comment.parent_id %} · 回复 #{{ comment.parent_id }}{% endif %}</span>
      <span>
        <a data-comment-target href="{{ url_for('post', post_id=comment.post_id) if comment.post_id else url_for('public_page', slug=comment.page.slug) }}">{{ owner.title }}</a>
        · <a href="{{ url_for('admin.comments', status=status, target=('post:%d' % comment.post_id) if comment.post_id else ('page:%d' % comment.page_id)) }}">只看这里</a>
      </span>
      <p>{{ comment.body }}</p>
    </div>
    <div class="admin-list__actions">
      {% if comment.status == 'pending' %}
      <form method="post" action="{{ url_for('admin.approve_comment', comment_id=comment.id) }}">
        {{ bulk_form.csrf_token }}
        <input type="hidden" name="next" value="{{ request.full_path.rstrip('?') }}">
        <button class="button button--quiet" type="submit">通过</button>
      </form>
      {% elif owner.comments_enabled %}
      <details>
        <summary>回复</summary>
        <form method="post" action="{{ url_for('admin.reply_comment', comment_id=comment.id) }}">
          {{ reply_form.csrf_token }}
          <input type="hidden" name="next" value="{{ request.full_path.rstrip('?') }}">
          <textarea class="form-control" name="body" rows="3" maxlength="1000" required></textarea>
          <button class="button button--cta" type="submit">发布回复</button>
        </form>
      </details>
      {% endif %}
      <form method="post" action="{{ url_for('admin.delete_article_comment', comment_id=comment.id) }}">
        {{ delete_form.hidden_tag() }}
        <input type="hidden" name="confirm" value="y">
        <input type="hidden" name="next" value="{{ request.full_path.rstrip('?') }}">
        <button class="button button--quiet button--danger" type="submit" onclick="return confirm('确定删除这条评论？它的回复也会一并删除。');">删除</button>
      </form>
    </div>
  </article>
  {% else %}
  <div class="empty-state"><p>没有符合条件的评论。</p></div>
  {% endfor %}
</div></section>
{% endblock %}
```

`admin-tabs`、`admin-filter`、`admin-bulk`、`admin-list__select` 这几个类现有样式里可能不存在:在 `style.css` 里按 `.admin-list__row` 的写法补最小样式(横排、间距、`[aria-current="page"]` 加粗),不引入新变量。

- [ ] **Step 6: 仪表盘**

`app/admin/routes.py` 评论卡片改为:

```python
        pending = _count(PostComment, PostComment.status == 'pending')
        comment_total = _count(PostComment)
        ...
            {'label': '评论', 'endpoint': 'admin.comments',
             'value': f'{comment_total} / 待审 {pending}' if pending else str(comment_total)},
```

(把 `pending`、`comment_total` 的计算放在 `metrics += [` 之前。)

- [ ] **Step 7: 运行测试**

Run: `python -m pytest tests/test_admin_comments.py tests/test_admin_modules.py tests/test_admin_dashboard.py tests/test_site_modules_removed.py tests/test_admin_access.py -q`
Expected: PASS。`test_site_modules_removed::test_admin_comments_page_lists_only_article_comments` 若断言了旧模板的具体文字,按新结构更新。

Run: `python -m pytest tests -q; node --test tests/*.test.js`
Expected: 全部 PASS。

- [ ] **Step 8: 手动看一眼后台**

Run: `flask run`,以管理员登录,打开 `/admin/comments`:三个标签、搜索、勾选批量、回复折叠框、「只看这里」。看完关掉服务。

- [ ] **Step 9: 提交**

```bash
git add app/admin/forms.py app/admin/modules.py app/admin/routes.py app/templates/admin/comments/list.html app/static/style.css tests/test_admin_comments.py
git commit -m "feat(admin): review queue, search, bulk actions and replies for comments"
```

---

### Task 7: 收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-comments-redesign-design.md`
- Modify: `README.md`(若其中有功能清单提到评论)

- [ ] **Step 1: 同步设计文档的两处偏离**

在设计文档 §5「评论开关」里把「后台编辑文章和页面时各加一个『允许评论』复选框。」改为:「页面的编辑表单里有『允许评论』复选框;文章在列表页和编辑页各有一个『关闭评论 / 开启评论』按钮,点击立即生效,不走草稿与发布流程。」

在 §6「前台」里把「回复按钮把表单移到该评论下方;没有 JS 时退化为带 `parent_id` 的锚点链接,表单仍可用。」改为:「点『回复』后表单留在原位,显示『回复 @某人 取消』,并滚动聚焦到输入框;没有 JS 时『回复』是 `?reply=ID#comment-form` 链接,效果相同。」

在 §4 末尾补一句:「站长自己的邮箱发过的评论不算『已通过的邮箱』,不会给其他人带来免审资格。」

- [ ] **Step 2: 全量验证**

Run: `source .venv/bin/activate && python -m pytest tests -q && node --test tests/*.test.js`
Expected: 全部 PASS,贴出通过数量。

Run: `git status --short`
Expected: 只剩计划/设计文档(如果还没提交),没有意外文件。

- [ ] **Step 3: README**

Run: `grep -n -i "评论\|comment" README.md`
有功能清单提到评论就补一句「评论支持回复、审核、Markdown,可按文章/页面开关」;没有就跳过。

- [ ] **Step 4: 提交**

```bash
git add docs/superpowers/specs/2026-11-06-comments-redesign-design.md README.md
git commit -m "docs: sync the comments design with what was built"
```

---

## Self-Review(已执行)

- **Spec 覆盖**:§1 数据模型 → Task 1;§2 回复 → Task 3(`_resolve_parent`)、Task 4;§3 Markdown → Task 2;§4 审核与防刷 → Task 3、4;§5 开关 → Task 5(服务端 403 在 Task 4 `_take_comment`);§6 前台共用片段 → Task 4;§7 后台 → Task 6;§8 表情 → 独立计划 `2026-11-06-emoji.md`;§9 测试散在各任务。
- **占位符**:无 TBD;唯一「看现有文件再对齐」的步骤(`app/__init__.py` 的 import 位置、`posts/form.html` 按钮容器、Task 4 Step 11 可能要更新的既有断言)都给出了判断依据。
- **类型一致**:`submit_comment` 的参数名(`name email body parent_id honeypot form_token author`)在 Task 3 定义,Task 4 `_take_comment` 与 Task 6 `reply_comment` 按同名调用;`Submission.outcome` 取值 `APPROVED/PENDING/DROPPED`;`comment_context` 的键与 `_comments.html` 使用的变量一致(`comment_threads comment_count comments_enabled comment_reply_to comment_form_token`)。
