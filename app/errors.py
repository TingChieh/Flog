from flask import render_template
from flask_babel import _

from app import app, db
from app.seo import NOINDEX

ERROR_SEO = {'canonical_url': None, 'robots': NOINDEX, 'og_type': 'website'}


@app.errorhandler(404)
def not_found_error(error):
    return render_template('error/404.html', title=_('Not Found'), seo=ERROR_SEO), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template(
        'error/500.html', title=_('An unexpected error has occurred'), seo=ERROR_SEO), 500

