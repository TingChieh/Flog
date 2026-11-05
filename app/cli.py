import os
import click
from app import app


@app.cli.group()
def translate():
    """Translation and localization commands."""
    pass


@translate.command()
@click.argument('lang')
def init(lang):
    """Initialize a new language."""
    if os.system('pybabel extract -F babel.cfg -k _l -o messages.pot .'):
        raise RuntimeError('extract command failed')
    if os.system(
            'pybabel init -i messages.pot -d app/translations -l ' + lang):
        raise RuntimeError('init command failed')
    os.remove('messages.pot')


@translate.command()
def update():
    """Update all languages."""
    if os.system('pybabel extract -F babel.cfg -k _l -o messages.pot .'):
        raise RuntimeError('extract command failed')
    if os.system('pybabel update -i messages.pot -d app/translations'):
        raise RuntimeError('update command failed')
    os.remove('messages.pot')


@translate.command()
def compile():
    """Compile all languages."""
    if os.system('pybabel compile -d app/translations'):
        raise RuntimeError('compile command failed')

@app.cli.command('rebuild-search-index')
def rebuild_search():
    """Rebuild the SQLite full-text index from existing posts."""
    from app import db
    from app.search_index import rebuild_search_index
    if rebuild_search_index(db.session.connection()):
        db.session.commit()
        click.echo('Search index rebuilt.')
    else:
        click.echo('Full-text index unavailable; LIKE search remains enabled.')
