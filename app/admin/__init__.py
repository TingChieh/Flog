from flask import Blueprint


bp = Blueprint('admin', __name__, url_prefix='/admin')

from app.admin import images, modules, pages, posts, routes, settings, users  # noqa: E402,F401
