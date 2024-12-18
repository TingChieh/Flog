from flask_wtf import FlaskForm
from flask_ckeditor import CKEditorField
from flask_babel import _, lazy_gettext as _l
from wtforms import SelectField, StringField, PasswordField, BooleanField, SubmitField, \
    TextAreaField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo, \
    Length, Optional
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


class EditProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    about_me = TextAreaField(_l('About me'),
                             validators=[Length(min=0, max=140)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = db.session.scalar(sa.select(User).where(
                User.username == username.data))
            if user is not None:
                raise ValidationError(_('Please use a different username.'))


class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')

class PostForm(FlaskForm):
    title = StringField(_l('Title'), validators=[DataRequired(), Length(1, 120)])
    category = SelectField(_l('Category'), coerce=int, default=1)
    post = CKEditorField(_l('Say something'), validators=[
        DataRequired()])
    submit = SubmitField(_l('Submit'))
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = db.session.execute(sa.select(Category).order_by(Category.name)).scalars()
        self.category.choices = [(category.id, category.name) for category in categories]

class CommentForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(1, 20)])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    body = CKEditorField(_l('Message'), validators=[DataRequired(), Length(1, 240)])
    submit = SubmitField(_l('Submit'))
    
class TodoForm(FlaskForm):
    title = StringField(_l('title'), validators=[DataRequired(), Length(1, 120)])
    complete = BooleanField(validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))
    
class TodoEditForm(FlaskForm):
    title = StringField(_l('title'), validators=[DataRequired(), Length(1, 120)])
    complete = BooleanField(validators=[DataRequired()])
    submit = SubmitField(_l('Update'))
    
class SearchForm(FlaskForm):
    query = StringField('Search', validators=[Optional()])
    submit = SubmitField('Search')
    
class MessageForm(FlaskForm):
    message = TextAreaField(_l('Message'), validators=[
        DataRequired(), Length(min=0, max=140)])
    submit = SubmitField(_l('Submit'))
    
class CategoryForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(1, 128)])
    submit = SubmitField(_l('Submit'))
    
    def validate_name(self, field):
        if db.session.execute(sa.select(Category).filter_by(name=field.data)).scalar():
            raise ValidationError('Name already in use.')
        
class AboutForm(FlaskForm):
    body = CKEditorField(_l('About'), validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))
    
class LinkForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(), Length(1, 128)])
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    url = StringField(_l('URL'), validators=[DataRequired(), Length(1, 255)])
    text = StringField(_l('Text'), validators=[DataRequired(), Length(1, 128)])
    submit = SubmitField(_l('Submit'))