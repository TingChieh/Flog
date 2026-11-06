from flask_wtf import FlaskForm
from flask_babel import _, lazy_gettext as _l
from wtforms import HiddenField, IntegerField, SelectField, StringField, PasswordField, \
    BooleanField, SubmitField, TextAreaField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, \
    Length, Optional
from wtforms.widgets import HiddenInput
import sqlalchemy as sa
from app import db
from app.models import Category, User


class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Sign In'))


class RegistrationForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(
        _l('Repeat Password'), validators=[DataRequired(),
                                           EqualTo('password')])
    submit = SubmitField(_l('Register'))

    def validate_username(self, username):
        user = db.session.scalar(sa.select(User).where(
            User.username == username.data))
        if user is not None:
            raise ValidationError(_('Please use a different username.'))

    def validate_email(self, email):
        user = db.session.scalar(sa.select(User).where(
            User.email == email.data))
        if user is not None:
            raise ValidationError(_('Please use a different email address.'))


class ResetPasswordRequestForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Request Password Reset'))


class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(
        _l('Repeat Password'), validators=[DataRequired(),
                                           EqualTo('password')])
    submit = SubmitField(_l('Request Password Reset'))


class PostForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired(), Length(1, 120)])
    category = SelectField(
        _l('Category'), coerce=int, default=1, validators=[DataRequired()])
    post = TextAreaField(_l('Say something'), validators=[
        DataRequired()])
    submit = SubmitField(_l('Submit'))
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = db.session.execute(sa.select(Category).order_by(Category.name)).scalars()
        self.category.choices = [(category.id, category.name) for category in categories]


class PostDraftForm(PostForm):
    title = StringField(_l('Title'), validators=[Optional(), Length(max=120)])
    post = TextAreaField(_l('Say something'), validators=[Optional()])


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
    
    
    
class SearchForm(FlaskForm):
    query = StringField('Search', validators=[Optional()])
    submit = SubmitField('Search')
    
    
class CategoryForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(1, 128)])
    submit = SubmitField(_l('Submit'))
    
    def validate_name(self, field):
        if db.session.execute(sa.select(Category).filter_by(name=field.data)).scalar():
            raise ValidationError('Name already in use.')
        
