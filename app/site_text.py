"""Site-wide wording an administrator can change; blank falls back to defaults."""
from flask_babel import gettext as _
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import SiteSettings

DEFAULT_SITE_NAME = "Aisaka's Blog"

# SiteSettings column -> label shown in the admin form
FIELDS = {
    'site_name': '网站名称',
    'home_tab_title': '首页标签页标题',
    'home_heading': '首页大标题',
    'nav_home_label': '导航栏：首页',
    'nav_archive_label': '导航栏：归档',
    'nav_categories_label': '分类名称（首页侧栏、分类页）',
}


def default_site_text():
    """What each field shows when left blank, keyed by settings column."""
    return {
        'site_name': DEFAULT_SITE_NAME,
        'home_tab_title': DEFAULT_SITE_NAME,
        'home_heading': _('Stories'),
        'nav_home_label': _('Home'),
        'nav_archive_label': _('Archive'),
        'nav_categories_label': _('Categories'),
    }


def site_text():
    try:
        settings = db.session.get(SiteSettings, 1)
    except SQLAlchemyError:
        db.session.rollback()
        settings = None

    def custom(name):
        return ((getattr(settings, name, None) or '').strip()) or None

    site_name = custom('site_name') or DEFAULT_SITE_NAME
    return {
        'site_name': site_name,
        'home_tab_title': custom('home_tab_title') or site_name,
        'home_heading': custom('home_heading') or _('Stories'),
        'nav_home': custom('nav_home_label') or _('Home'),
        'nav_archive': custom('nav_archive_label') or _('Archive'),
        'nav_categories': custom('nav_categories_label') or _('Categories'),
    }
