import re

import sqlalchemy as sa
from email_validator import EmailNotValidError, validate_email
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (BooleanField, DateTimeLocalField, HiddenField,
                     IntegerField, SelectField,
                     PasswordField, StringField, SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, Email, InputRequired, Length,
                                NumberRange, Optional, ValidationError, AnyOf)

from app import db
from app.models import Category, Episode, Page, PageRedirect, User
from app.pages import PageValidationError, normalize_slug


class PageForm(FlaskForm):
    title = StringField('标题', validators=[DataRequired(), Length(max=120)])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=120)])
    summary = TextAreaField('摘要', validators=[Length(max=300)])
    body = TextAreaField('正文')
    is_published = BooleanField('已发布')
    show_in_nav = BooleanField('显示在导航中')
    comments_enabled = BooleanField('允许评论')
    nav_order = IntegerField(
        '导航顺序', validators=[InputRequired(), NumberRange(min=-100000,
                                                           max=100000)])
    submit = SubmitField('保存')

    def __init__(self, *args, page=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_id = page.id if page is not None else None

    def validate_slug(self, field):
        try:
            field.data = normalize_slug(field.data)
        except PageValidationError as exc:
            raise ValidationError(str(exc)) from exc

        page_query = sa.select(Page).where(Page.slug == field.data)
        redirect_query = sa.select(PageRedirect).where(
            PageRedirect.slug == field.data)
        if self.page_id is not None:
            page_query = page_query.where(Page.id != self.page_id)
            redirect_query = redirect_query.where(
                PageRedirect.page_id != self.page_id)
        if db.session.scalar(page_query) is not None \
                or db.session.scalar(redirect_query) is not None:
            raise ValidationError('This slug is already in use.')

class DeleteForm(FlaskForm):
    confirm = BooleanField('确认删除', validators=[DataRequired()])
    submit = SubmitField('删除')


class BulkCommentForm(FlaskForm):
    """CSRF-only; the action and ids are read from the request."""


class CommentReplyForm(FlaskForm):
    body = TextAreaField('回复', validators=[DataRequired(), Length(1, 1000)])


class ToggleForm(FlaskForm):
    """CSRF-only form for one-click state toggles."""


class ImageUploadForm(FlaskForm):
    """CSRF-only form for the library's multi-file upload."""


class AvatarUploadForm(FlaskForm):
    """CSRF-only form for the avatar upload."""


class ImageEditForm(FlaskForm):
    title = StringField('名称', validators=[Length(max=120)])
    note = TextAreaField('备注', validators=[Length(max=500)])
    submit = SubmitField('保存')


class ImageDeleteForm(FlaskForm):
    force = BooleanField('我知道这些位置的图片会失效')
    submit = SubmitField('确认删除')


class CategoryAdminForm(FlaskForm):
    name = StringField('名称', validators=[DataRequired(), Length(max=120)])
    submit = SubmitField('保存')

    def __init__(self, *args, category=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id = category.id if category is not None else None

    def validate_name(self, field):
        name = field.data.strip()
        query = sa.select(Category).where(Category.name == name)
        if self.category_id is not None:
            query = query.where(Category.id != self.category_id)
        if db.session.scalar(query) is not None:
            raise ValidationError('Category name is already in use.')
        field.data = name


ROLE_CHOICES = [('user', '普通用户'), ('admin', '管理员')]


class UserDeleteForm(FlaskForm):
    """CSRF plus an optional receiver; the route decides if it is required."""
    receiver = SelectField('文章转交给', coerce=int, validate_choice=False)
    submit = SubmitField('删除用户')


class _UserFieldsMixin:
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user.id if user is not None else None

    def _unique(self, column, value, message):
        query = sa.select(User).where(column == value)
        if self.user_id is not None:
            query = query.where(User.id != self.user_id)
        if db.session.scalar(query) is not None:
            raise ValidationError(message)

    def validate_username(self, field):
        field.data = field.data.strip()
        self._unique(User.username, field.data, '用户名已被使用。')

    def validate_email(self, field):
        field.data = field.data.strip()
        self._unique(User.email, field.data, '邮箱已被使用。')


class UserCreateForm(_UserFieldsMixin, FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(max=64)])
    email = StringField(
        '邮箱', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('初始密码', validators=[DataRequired()])
    role = SelectField('角色', choices=ROLE_CHOICES,
                       validators=[DataRequired(), AnyOf(('user', 'admin'))])
    submit = SubmitField('创建用户')


class UserEditForm(_UserFieldsMixin, FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(max=64)])
    email = StringField(
        '邮箱', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('新密码', validators=[Optional()])
    role = SelectField('角色', choices=ROLE_CHOICES,
                       validators=[AnyOf(('user', 'admin'))])
    submit = SubmitField('保存')


class SiteSettingsForm(FlaskForm):
    registration_open = BooleanField('开放用户注册')
    post_revision_limit = IntegerField(
        '每篇文章可回滚版本数量',
        validators=[InputRequired(), NumberRange(min=1, max=100)])
    site_name = StringField('网站名称', validators=[Optional(), Length(max=60)])
    home_tab_title = StringField(
        '首页标签页标题', validators=[Optional(), Length(max=120)])
    home_heading = StringField('首页大标题', validators=[Optional(), Length(max=60)])
    nav_home_label = StringField(
        '导航栏：首页', validators=[Optional(), Length(max=20)])
    nav_archive_label = StringField(
        '导航栏：归档', validators=[Optional(), Length(max=20)])
    nav_categories_label = StringField(
        '分类名称（首页侧栏、分类页）', validators=[Optional(), Length(max=20)])
    submit = SubmitField('保存设置')


MAX_RECIPIENTS = 10
_MESSAGE_ID = r'<[^<>\s@]{1,100}@[^<>\s@]{1,100}>'


def clean_message_ids(value, many=False):
    """The Message-ID header value, or '' when it is not exactly that.

    Thread headers come back from the browser, so anything that is not plain
    <id@host> tokens is dropped rather than put into a header.
    """
    value = (value or '').strip()
    pattern = _MESSAGE_ID + (f'(?: {_MESSAGE_ID}){{0,9}}' if many else '')
    return value if re.fullmatch(pattern, value) else ''


class MailComposeForm(FlaskForm):
    sender = SelectField('发件人', validators=[DataRequired()])
    to = StringField('收件人', validators=[DataRequired(), Length(max=1000)])
    subject = StringField('主题', validators=[DataRequired(), Length(max=200)])
    body = TextAreaField('正文', validators=[DataRequired(), Length(max=20000)])
    in_reply_to = HiddenField()
    references = HiddenField()
    submit = SubmitField('发送')

    recipients = ()

    def validate_to(self, field):
        parts = [p for p in re.split(r'[,;\s]+', field.data or '') if p]
        if not parts:
            raise ValidationError('请填写收件人。')
        if len(parts) > MAX_RECIPIENTS:
            raise ValidationError(f'收件人最多 {MAX_RECIPIENTS} 个。')
        recipients = []
        for part in parts:
            try:
                recipients.append(validate_email(
                    part, check_deliverability=False).normalized)
            except EmailNotValidError:
                raise ValidationError(f'收件人地址无效：{part}')
        self.recipients = recipients

    def validate_subject(self, field):
        if re.search(r'[\r\n]', field.data or ''):
            raise ValidationError('主题不能换行。')


class PodcastShowForm(FlaskForm):
    title = StringField('节目名称', validators=[Optional(), Length(max=120)])
    description = TextAreaField('节目简介', validators=[Optional(), Length(max=4000)])
    author = StringField('主播 / 作者', validators=[Optional(), Length(max=120)])
    owner_email = StringField(
        '联系邮箱（Apple、小宇宙验证用）',
        validators=[Optional(), Email(), Length(max=120)])
    category = StringField('Apple 分类', validators=[Optional(), Length(max=60)])
    cover = FileField('封面（正方形，建议 1400-3000 像素）')
    apple_url = StringField('Apple Podcasts 链接', validators=[Optional(), Length(max=300)])
    xiaoyuzhou_url = StringField('小宇宙链接', validators=[Optional(), Length(max=300)])
    submit = SubmitField('保存')

    def validate_apple_url(self, field):
        _check_link(field)

    def validate_xiaoyuzhou_url(self, field):
        _check_link(field)


def _check_link(field):
    value = (field.data or '').strip()
    if value and not re.match(r'https?://', value, re.IGNORECASE):
        raise ValidationError('链接需要以 http:// 或 https:// 开头。')
    field.data = value


class EpisodeForm(FlaskForm):
    number = IntegerField(
        '期号', validators=[InputRequired(), NumberRange(min=1, max=100000)])
    title = StringField('标题', validators=[DataRequired(), Length(max=120)])
    summary = TextAreaField('摘要（列表页和 RSS 里显示）', validators=[Optional(), Length(max=500)])
    body = TextAreaField('节目笔记（Markdown）', validators=[Optional()])
    audio = FileField('音频文件（MP3 或 M4A）')
    cover = FileField('单集封面（可选，不选则用节目封面）')
    published_at = DateTimeLocalField(
        '发布时间', format='%Y-%m-%dT%H:%M', validators=[InputRequired()])
    is_published = BooleanField('已发布')
    comments_enabled = BooleanField('允许评论')
    submit = SubmitField('保存')

    def __init__(self, *args, episode=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.episode_id = episode.id if episode is not None else None

    def validate_number(self, field):
        query = sa.select(Episode).where(Episode.number == field.data)
        if self.episode_id is not None:
            query = query.where(Episode.id != self.episode_id)
        if db.session.scalar(query) is not None:
            raise ValidationError('这个期号已经有节目了。')

