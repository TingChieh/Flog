import os
import subprocess
import sys

import click
from app import app


def _run_pybabel(*args):
    subprocess.run(
        [sys.executable, '-m', 'babel.messages.frontend', *args],
        check=True,
    )


@app.cli.group()
def translate():
    """Translation and localization commands."""
    pass


@translate.command()
@click.argument('lang')
def init(lang):
    """Initialize a new language."""
    try:
        _run_pybabel('extract', '-F', 'babel.cfg', '-k', '_l', '-o', 'messages.pot', '.')
        _run_pybabel('init', '-i', 'messages.pot', '-d', 'app/translations', '-l', lang)
    finally:
        if os.path.exists('messages.pot'):
            os.remove('messages.pot')


@translate.command()
def update():
    """Update all languages."""
    try:
        _run_pybabel('extract', '-F', 'babel.cfg', '-k', '_l', '-o', 'messages.pot', '.')
        _run_pybabel('update', '-i', 'messages.pot', '-d', 'app/translations')
    finally:
        if os.path.exists('messages.pot'):
            os.remove('messages.pot')


@translate.command()
def compile():
    """Compile all languages."""
    _run_pybabel('compile', '-d', 'app/translations')

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
    except ValueError as exc:
        raise click.BadParameter(
            'use a form like "2022-01-29 16:04"', param_hint='--published') from exc
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
        raise click.ClickException(str(exc)) from exc
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
    if recompress:
        from app.avatars import shrink_existing_avatars
        shrunk, saved = shrink_existing_avatars()
        click.echo(f'Shrank {shrunk} avatar(s) (saved {saved / 1024:.0f} KB).')


@app.cli.group()
def content():
    """Batch Markdown + media export and import."""
    pass


@content.command('export')
@click.argument('output_dir', type=click.Path(file_okay=False))
@click.option('--published-only', is_flag=True,
              help='Export only published posts (skip drafts and scheduled posts).')
@click.option('--allow-missing-media', is_flag=True,
              help='Continue even if a referenced local media file is missing on disk.')
def export_content(output_dir, published_only, allow_missing_media):
    """Export posts to Markdown with front matter and paired media files."""
    from app.content_io import ContentExportError, export_posts_bundle

    try:
        result = export_posts_bundle(
            output_dir,
            include_drafts=not published_only,
            allow_missing_media=allow_missing_media,
        )
    except ContentExportError as exc:
        for line in exc.diagnostics:
            click.echo(f'ERROR: {line}', err=True)
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f'Exported {result.exported_posts} post(s), '
        f'{result.exported_media} image(s), '
        f'{result.exported_videos} Live Photo clip(s) to {result.output_dir}.'
    )
    if result.missing_media:
        click.echo(
            f'Warning: {len(result.missing_media)} missing media reference(s) skipped.',
            err=True,
        )


@content.command('import')
@click.argument('input_dir', type=click.Path(exists=True, file_okay=False))
@click.option('--author', default=None,
              help='Username to assign imported posts to (falls back to front matter or admin).')
@click.option('--dry-run', is_flag=True,
              help='Validate and preview changes without writing to the database or uploads.')
@click.option('--overwrite', is_flag=True,
              help='Explicitly confirm overwriting conflicting existing posts or media.')
def import_content(input_dir, author, dry_run, overwrite):
    """Validate, stage, and import a Markdown + media bundle."""
    from app.content_io import ContentImportError, import_posts_bundle

    try:
        result = import_posts_bundle(
            input_dir,
            default_author=author,
            overwrite=overwrite,
            dry_run=dry_run,
        )
    except ContentImportError as exc:
        for line in exc.diagnostics:
            click.echo(f'ERROR: {line}', err=True)
        raise click.ClickException(str(exc)) from exc

    prefix = '[dry-run] ' if result.dry_run else ''
    click.echo(
        f'{prefix}Posts: +{result.created_posts} created, '
        f'{result.updated_posts} updated, {result.skipped_posts} skipped; '
        f'Media: +{result.created_media} created, '
        f'{result.overwritten_media} overwritten, {result.reused_media} reused.'
    )
    for warning in result.warnings:
        click.echo(f'WARNING: {warning}', err=True)


@app.cli.group()
def posts():
    """Post publishing maintenance."""
    pass


@posts.command('publish-due')
@click.option('--at', 'at_time', default=None,
              help='Override reference time (ISO-8601, e.g. "2026-06-01T08:00:00+08:00").')
def publish_due(at_time):
    """Publish all scheduled posts whose scheduled time has arrived."""
    from datetime import datetime
    from app import db
    from app.post_drafts import publish_due_posts

    now = None
    if at_time:
        raw = at_time.strip()
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        try:
            now = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise click.BadParameter(
                'use ISO-8601 format, e.g. "2026-06-01T08:00:00+08:00"',
                param_hint='--at') from exc

    result = publish_due_posts(now=now)
    db.session.commit()
    click.echo(f'Published {len(result.published_ids)} scheduled post(s).')
    if result.failed:
        for post_id, reason in result.failed:
            click.echo(f'FAILED post #{post_id}: {reason}', err=True)
        raise SystemExit(1)


@app.cli.group()
def backup():
    """Backup retention, manifest, and failure alerting helpers."""
    pass


@backup.command('alert')
@click.option('--stage', required=True, help='Backup stage where the failure occurred.')
@click.option('--exit-code', type=int, required=True, help='Non-zero exit status.')
@click.option('--detail', required=True, help='Failure summary or command error detail.')
@click.option('--stamp', default=None, help='Backup run timestamp (YYYYMMDDTHHMMSSZ).')
@click.option('--target', default=None, help='Backup target label (bucket/prefix or local path).')
@click.option('--webhook', default=None, help='Optional webhook URL override.')
def backup_alert(stage, exit_code, detail, stamp, target, webhook):
    """Log and dispatch a backup failure alert through configured channels."""
    from app.backup import notify_backup_failure

    outcome = notify_backup_failure(
        stage=stage,
        exit_code=exit_code,
        detail=detail,
        stamp=stamp,
        target=target,
        webhook_url=webhook,
    )
    click.echo(
        f'Alert recorded: logged={outcome.logged}, '
        f'email_sent={outcome.email_sent}, webhook_sent={outcome.webhook_sent}.'
    )
    for err in outcome.errors:
        click.echo(f'Alert channel warning: {err}', err=True)


@app.cli.command('stats')
@click.option('--top', 'top_limit', type=int, default=10,
              help='Number of top published posts to list.')
@click.option('--days', 'recent_days', type=int, default=30,
              help='Lookback window in days for recent comments and likes.')
@click.option('--json', 'as_json', is_flag=True, help='Output statistics as JSON.')
def site_stats_cli(top_limit, recent_days, as_json):
    """Show aggregated post, view, comment, reaction, and category statistics."""
    import json
    from app.stats import collect_site_stats

    stats = collect_site_stats(top_limit=top_limit, recent_days=recent_days)
    if as_json:
        click.echo(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(
        f'Posts: {stats.total_posts} total '
        f'({stats.published_posts} published, {stats.scheduled_posts} scheduled, '
        f'{stats.draft_posts} drafts)'
    )
    click.echo(f'Views: {stats.total_views} total ({stats.published_views} published)')
    click.echo(
        f'Comments: {stats.total_comments} total '
        f'({stats.approved_comments} approved, {stats.pending_comments} pending, '
        f'{stats.recent_comments} in last {stats.recent_days}d)'
    )
    click.echo(
        f'Reactions: {stats.total_likes} total '
        f'({stats.recent_likes} in last {stats.recent_days}d)'
    )
    if stats.top_posts:
        click.echo('Top published posts:')
        for item in stats.top_posts:
            click.echo(
                f'  #{item.id} {item.title} — '
                f'{item.view_count} views, {item.comment_count} comments, '
                f'{item.like_count} reactions'
            )
