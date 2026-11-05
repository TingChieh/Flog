import sqlalchemy as sa
from flask_wtf import FlaskForm
from wtforms import (BooleanField, HiddenField, IntegerField, SelectField,
                     PasswordField, StringField, SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, Email, InputRequired, Length,
                                NumberRange, Optional, ValidationError, AnyOf)

from app import db
from app.models import Category, Page, PageRedirect, User
from app.pages import PageValidationError, normalize_slug


class PageForm(FlaskForm):
    title = StringField('标题', validators=[DataRequired(), Length(max=120)])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=120)])
    summary = TextAreaField('摘要', validators=[Length(max=300)])
    body = TextAreaField('正文')
    is_published = BooleanField('已发布')
    show_in_nav = BooleanField('显示在导航中')
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


class ToggleForm(FlaskForm):
    """CSRF-only form for one-click state toggles."""


class ImageUploadForm(FlaskForm):
    """CSRF-only form for the library's multi-file upload."""


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
    submit = SubmitField('保存设置')
