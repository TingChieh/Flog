import sqlalchemy as sa
import sqlalchemy.orm as so
from app import app, db
from app.models import (Page, PageRedirect, Post, PostComment, PostLike,
                        User)
from app import cli

@app.shell_context_processor
def make_shell_context():
    return {'sa': sa, 'so': so, 'db': db, 'User': User, 'Post': Post,
            'PostComment': PostComment, 'PostLike': PostLike,
            'Page': Page, 'PageRedirect': PageRedirect}
