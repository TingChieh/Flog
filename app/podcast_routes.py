"""Public pages of the podcast, its feed, and the old podcast domain's redirect."""
from flask import abort, redirect, render_template, request, url_for

from app import app, db
from app.comments import comment_context
from app.models import Episode
from app.podcast import (UploadRequest, audio_url, build_feed, cover_url, format_duration,
                         latest_episodes, legacy_redirect_target,
                         podcast_enabled,
                         public_episode_or_404, show_text)
from app.routes import handle_comment_request

app.jinja_env.filters['duration'] = format_duration
app.request_class = UploadRequest


PUBLIC_ENDPOINTS = frozenset({'podcast_index', 'podcast_episode', 'podcast_feed'})


@app.before_request
def podcast_switch():
    """The podcast only exists while an admin has switched it on."""
    if request.endpoint in PUBLIC_ENDPOINTS and not podcast_enabled():
        abort(404)


@app.before_request
def redirect_old_podcast_domain():
    """Redirect configured legacy podcast hostnames to the integrated podcast."""
    hosts = app.config['PODCAST_REDIRECT_HOSTS']
    base = app.config['SITE_URL']
    if not hosts or not base or request.host.split(':')[0].lower() not in hosts:
        return None
    target = legacy_redirect_target(request.path, request.args)
    return redirect(base.rstrip('/') + target, code=301)


@app.route('/podcast/')
def podcast_index():
    show = show_text()
    episodes = db.session.scalars(latest_episodes()).all()
    return render_template(
        'podcast/index.html', title=show['title'], show=show,
        episodes=episodes, show_cover=cover_url(show['cover_filename']))


@app.route('/podcast/<int:number>', methods=['GET', 'POST'])
def podcast_episode(number):
    episode = public_episode_or_404(number)
    form, taken = handle_comment_request(
        episode,
        lambda anchor: url_for('podcast_episode', number=episode.number,
                               _anchor=anchor))
    if taken is not None:
        return taken

    show = show_text()
    newer = db.session.scalar(latest_episodes().where(
        Episode.number > episode.number).order_by(None).order_by(
            Episode.number).limit(1))
    older = db.session.scalar(latest_episodes().where(
        Episode.number < episode.number).order_by(None).order_by(
            Episode.number.desc()).limit(1))
    return render_template(
        'podcast/episode.html', title=episode.title, episode=episode,
        form=form, show=show, newer=newer, older=older,
        audio_src=audio_url(episode),
        cover=cover_url(episode.cover_filename or show['cover_filename']),
        **comment_context(episode, form))


@app.route('/podcast/feed.xml')
def podcast_feed():
    response = app.response_class(
        build_feed(), content_type='application/rss+xml; charset=utf-8')
    # Podcast apps poll the feed all day; an ETag lets them get a 304 when
    # nothing changed instead of the whole document.
    response.add_etag()
    response.cache_control.public = True
    response.cache_control.max_age = 300
    return response.make_conditional(request)
