import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from app.email_handler import SMTP_SSLHandler
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_moment import Moment
from flask_babel import Babel, lazy_gettext as _l
from config import Config
from flask_wtf.csrf import CSRFProtect

def get_locale():
    """The site is Chinese-only, so the browser's language never matters."""
    return app.config['LANGUAGES'][0]


app = Flask(__name__)
app.config.from_object(Config)
if app.config['TRUSTED_PROXY_HOPS']:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config['TRUSTED_PROXY_HOPS'])


@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now(timezone.utc).year}


from app.security import safe_html
from app.content import render_content
from app.comment_markdown import render_comment
app.jinja_env.filters['safe_html'] = safe_html
app.jinja_env.filters['render_content'] = render_content
app.jinja_env.filters['comment_markdown'] = render_comment
from app.timezones import to_display
app.jinja_env.filters['localtime'] = to_display
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = 'login'
login.login_message = _l('Please log in to access this page.')
mail = Mail(app)
moment = Moment(app)
babel = Babel(app, locale_selector=get_locale)
csrf = CSRFProtect(app)


@app.context_processor
def inject_navigation_pages():
    from sqlalchemy.exc import SQLAlchemyError
    from app.pages import visible_navigation_pages

    try:
        return {'navigation_pages': visible_navigation_pages()}
    except SQLAlchemyError:
        db.session.rollback()
        return {'navigation_pages': []}

@app.context_processor
def inject_site_text():
    from app.site_text import site_text

    return {'site_text': site_text()}

if not app.debug:
    if app.config['MAIL_SERVER']:
        auth = None
        if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
            auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        mail_handler = SMTP_SSLHandler(
            mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
            fromaddr=app.config['MAIL_FROM'] or app.config['MAIL_USERNAME'],
            toaddrs=app.config['ADMINS'], subject='Flog Failure',
            credentials=auth, secure=())
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)

    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/flog.log', maxBytes=10240,
                                       backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Flog startup')

from app.admin import bp as admin_bp

app.register_blueprint(admin_bp)

from app import routes, models, errors, cli, static_cache, font_preload
from app import podcast_routes

from app.search import excerpt, plain_text
app.jinja_env.filters['plain_text'] = plain_text
app.jinja_env.filters['excerpt'] = excerpt
