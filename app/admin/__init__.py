from flask import Blueprint


bp = Blueprint('admin', __name__, url_prefix='/admin')

from app.admin import account, images, mail, modules, pages, podcast, posts, routes, settings, users  # noqa: E402,F401
