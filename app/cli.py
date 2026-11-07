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


@app.cli.group()
def podcast():
    """Podcast maintenance."""
    pass


@podcast.command('add')
@click.option('--number', type=int, required=True, help='Episode number.')
@click.option('--title', required=True)
@click.option('--audio', 'audio_path', type=click.Path(exists=True, dir_okay=False),
              required=True, help='MP3 or M4A file; it is copied into the uploads.')
@click.option('--published', required=True,
              help='Release time in the display time zone, e.g. "2022-01-29 16:04".')
@click.option('--summary', default=None)
@click.option('--notes', 'notes_path', type=click.Path(exists=True, dir_okay=False),
              default=None, help='Markdown file with the show notes.')
@click.option('--cover', 'cover_path', type=click.Path(exists=True, dir_okay=False),
              default=None)
@click.option('--legacy-path', default=None,
              help='Path of this episode on the old site, kept for redirects.')
@click.option('--feed-guid', default=None,
              help='Id the episode had in the old feed; keep it so apps do not list it twice.')
@click.option('--draft', is_flag=True, help='Leave the episode unpublished.')
def add_episode(number, title, audio_path, published, summary, notes_path,
                cover_path, legacy_path, feed_guid, draft):
    """Add an episode from files on this machine."""
    from datetime import datetime
    from app import db
    from app.podcast import AudioUploadError, import_episode
    from app.timezones import from_display

    try:
        release = from_display(datetime.fromisoformat(published))
    except ValueError:
        raise click.BadParameter(
            'use a form like "2022-01-29 16:04"', param_hint='--published')
    body = None
    if notes_path:
        with open(notes_path, encoding='utf-8') as notes:
            body = notes.read()
    try:
        episode = import_episode(
            number=number, title=title, audio_path=audio_path,
            published_at=release, summary=summary, body=body,
            cover_path=cover_path, legacy_path=legacy_path,
            feed_guid=feed_guid, is_published=not draft)
        db.session.commit()
    except AudioUploadError as exc:
        raise click.ClickException(str(exc))
    click.echo(f'Added EP-{episode.number:03d} {episode.title} '
               f'({episode.audio_duration} s, {episode.audio_size} bytes).')


@app.cli.group()
def images():
    """Uploaded image maintenance."""
    pass


@images.command()
@click.option('--recompress', is_flag=True,
              help='Also shrink stored files in place (same name and format).')
def optimize(recompress):
    """Record pixel sizes of older uploads so pages can use responsive images."""
    from app.images import optimize_existing_images
    stats = optimize_existing_images(recompress=recompress)
    click.echo(f'Registered {stats.untracked} untracked file(s), '
               f'recorded sizes for {stats.dimensions}, '
               f'recompressed {stats.recompressed} '
               f'(saved {stats.saved_bytes / 1024:.0f} KB), '
               f'{stats.missing} missing on disk.')
