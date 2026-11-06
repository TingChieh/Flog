from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from urllib.parse import urlsplit
from flask import abort, render_template, flash, redirect, send_from_directory, url_for, request, g, make_response, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from flask_babel import _, ngettext, get_locale
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from langdetect import detect, LangDetectException
from app import app, db
from app.forms import LoginForm, RegistrationForm, \
    PostCommentForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, SearchForm
from app.models import Category, User, Post, Page, PageRedirect, PostComment, PostLike, get_site_settings
from app.email import send_password_reset_email
from feedgen.feed import FeedGenerator

from app.security import admin_required
from app.content import (normalize_body_format, prepare_content_source,
                         render_content, render_article)
from app.post_drafts import DraftValues, publish_draft, save_draft
from app.pages import PAGE_CONTENT, page_for_public_slug
from app.post_views import (
    attach_view_cookie, has_recent_view, record_view, view_cookie_name,
)
from app.authorization import owned_post_or_404
from app.images import (VARIANT_FOLDER, ImageUploadError, make_variant,
                        save_uploaded_image)
from app.admin.forms import CategoryAdminForm


def published_post_statement():
    return sa.select(Post).where(Post.is_published.is_(True))


def public_post_or_404(post_id):
    return db.first_or_404(
        published_post_statement().where(Post.id == post_id))


@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()
    g.locale = str(get_locale())


@app.route('/')
@app.route('/index')
def index():
    page = request.args.get('page', 1, type=int)
    query = published_post_statement().order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page,
                        per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('index', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('index'),
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == form.username.data))
        if user is None or not user.check_password(form.password.data):
            flash(_('Invalid username or password'))
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('user/login.html', title=_('Sign In'), form=form)


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if not get_site_settings().registration_open:
        abort(403)
    form = RegistrationForm()
    if form.validate_on_submit():
        if not get_site_settings().registration_open:
            abort(403)
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(_('Congratulations, you are now a registered user!'))
        return redirect(url_for('login'))
    return render_template('user/register.html', title=_('Register'), form=form)


@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.email == form.email.data))
        if user:
            send_password_reset_email(user)
        flash(
            _('Check your email for the instructions to reset your password'))
        return redirect(url_for('login'))
    return render_template('user/reset_password_request.html',
                           title=_('Reset Password'), form=form)


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_('Your password has been reset.'))
        return redirect(url_for('login'))
    return render_template('user/reset_password.html', form=form)


def _redirect_to_public_page(page):
    target = url_for('public_page', slug=page.slug)
    if request.query_string:
        target = f'{target}?{request.query_string.decode("latin1")}'
    return redirect(target, code=301)


def _commit_legacy_mutation(message):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash(message)
        abort(500)



@app.route('/post/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = owned_post_or_404(post_id, current_user)
    db.session.execute(post.likes.delete())
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.')
    return redirect(url_for('admin.posts'))


    
        


def _search_query():
    query = request.args.get('q', '').strip()
    if len(query) > app.config['SEARCH_QUERY_MAX_LENGTH']:
        abort(400)
    return query


@app.route('/search')
def search():
    from app.search import search_posts, result_data, highlight
    query = _search_query()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = app.config['POSTS_PER_PAGE']
    posts = search_posts(query, per_page + 1, (page - 1) * per_page)
    results = [result_data(post, query) for post in posts[:per_page]]
    return render_template('post/search_results.html', title=_('Search'),
                           query=query, results=results, items=zip(posts[:per_page], results), highlight=highlight,
                           result_count=search_posts(query, count=True), ngettext=ngettext,
                           next_url=url_for('search', q=query, page=page + 1) if len(posts) > per_page else None,
                           prev_url=url_for('search', q=query, page=page - 1) if page > 1 else None)


@app.route('/api/search')
def api_search():
    from app.search import search_posts, result_data
    query = _search_query()
    limit = min(20, max(1, request.args.get('limit', 8, type=int)))
    return jsonify(results=[result_data(post, query) for post in search_posts(query, limit)])


UPLOAD_MAX_AGE = 365 * 24 * 60 * 60


@app.route('/files/<path:filename>')
def uploaded_files(filename):
    return send_upload(filename)


@app.route('/files/_w/<int:width>/<stem>.webp')
def variant_file(width, stem):
    """A resized WebP copy of an upload, made the first time it is asked for."""
    if make_variant(stem, width) is None:
        abort(404)
    return send_upload(f'{VARIANT_FOLDER}/{width}/{stem}.webp')


def send_upload(filename):
    # Stored names are random and a file is never rewritten, so browsers and
    # proxies may keep them for good.
    response = send_from_directory(
        app.config['UPLOAD_FOLDER'], filename, max_age=UPLOAD_MAX_AGE)
    response.cache_control.immutable = True
    return response


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    try:
        image = save_uploaded_image(request.files.get('post'), current_user)
    except ImageUploadError as exc:
        return {'uploaded': 0, 'error': {'message': str(exc)}}, 400
    url = url_for('uploaded_files', filename=image.filename)
    return {'uploaded': 1, 'filename': '', 'url': url}, 200


@app.route('/archive')
def archive():
    posts = db.session.scalars(
        published_post_statement().order_by(Post.timestamp.desc(), Post.id.desc())
    ).all()
    return render_template('post/archive.html', title=_('Archive'), posts=posts)


@app.route('/categories', methods=['GET'])
def categories():
    categories = db.session.execute(sa.select(Category)).scalars().all()
    category_post_counts = dict(db.session.execute(
        sa.select(Post.category_id, sa.func.count(Post.id)).where(
            Post.is_published.is_(True)
        ).group_by(Post.category_id)
    ).all())
    return render_template(
        'post/categories.html', title=_('Categories'), categories=categories,
        category_post_counts=category_post_counts)

# Route for deleting a category
@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = db.get_or_404(Category, category_id)
    in_use = db.session.scalar(sa.select(sa.func.count()).select_from(
        Post).where(Post.category_id == category.id))
    if in_use:
        abort(400)
    db.session.delete(category)
    _commit_legacy_mutation('分类删除失败，请重试。')
    flash(f'Category "{category.name}" has been deleted.')
    return redirect(url_for('admin.categories'))

@app.route('/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = db.get_or_404(Category, category_id)
    if request.method == 'GET':
        return redirect(url_for('admin.categories'))
    form = CategoryAdminForm(category=category, obj=category)
    if not form.validate_on_submit():
        abort(400)
    category.name = form.name.data
    _commit_legacy_mutation('分类保存失败，请重试。')
    flash('The category has been updated.', 'success')
    return redirect(url_for('admin.categories'))

@app.route('/category/<int:category_id>', methods=['GET'])
def posts_by_category(category_id):
    # Query for the category by its ID
    category = Category.query.get_or_404(category_id)
    
    # Get all posts that belong to this category
    posts = db.session.scalars(published_post_statement().where(
        Post.category_id == category.id
    )).all()

    # Render the posts in the category using a template
    return render_template('post/posts_by_category.html', category=category, posts=posts)

@app.route('/archives/<int:legacy_id>/')
def legacy_archive(legacy_id):
    """Addresses of the old blog keep working: /archives/5/ -> the new post."""
    post = db.first_or_404(
        published_post_statement().where(Post.legacy_id == legacy_id))
    return redirect(url_for('post', post_id=post.id), code=301)


@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def post(post_id):
    post = public_post_or_404(post_id)
    form = PostCommentForm()
    if current_user.is_authenticated and request.method == 'GET':
        form.name.data = current_user.username
        form.email.data = current_user.email
    if form.validate_on_submit():
        comment = PostComment(
            post=post,
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            body=form.body.data.strip(),
        )
        db.session.add(comment)
        db.session.commit()
        flash(_('Your comment has been published.'))
        return redirect(url_for('post', post_id=post.id, _anchor='comments'))

    counted = False
    if request.method == 'GET':
        marker = request.cookies.get(view_cookie_name(post.id))
        if not has_recent_view(post.id, marker):
            counted = record_view(post)

    article_html, article_toc = render_article(post.body, post.body_format)
    response = make_response(render_template(
        'post/post.html', article_html=article_html, article_toc=article_toc, title=_('Post'), post=post, form=form,
        comments=post.comments,
    ))
    if counted:
        attach_view_cookie(response, post.id)
    return response


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_post_like(post_id):
    post = public_post_or_404(post_id)
    like = db.session.scalar(sa.select(PostLike).where(
        PostLike.post_id == post.id,
        PostLike.user_id == current_user.id,
    ))
    if like:
        db.session.delete(like)
    else:
        db.session.add(PostLike(post=post, user=current_user))
    db.session.commit()
    return redirect(url_for('post', post_id=post.id, _anchor='post-actions'))


@app.route('/post-comment/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_post_comment(comment_id):
    comment = db.get_or_404(PostComment, comment_id)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash(_('Comment deleted.'))
    return redirect(url_for('admin.comments'))

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = owned_post_or_404(post_id, current_user)

    if request.method == 'GET':
        return redirect(url_for('admin.edit_post', post_id=post.id))

    form = PostForm()

    if form.validate_on_submit():
        post.body_format = normalize_body_format(post.body_format)
        save_draft(
            current_user, post,
            DraftValues(form.title.data, form.post.data, form.category.data))
        publish_draft(current_user, post.id)
        db.session.commit()
        flash(_('Your post has been updated!'))
        return redirect(url_for('admin.posts'))

    # Populate form with the current post data
    form.title.data = post.title
    form.post.data = post.body
    form.category.data = post.category_id

    return redirect(url_for('admin.edit_post', post_id=post.id))

@app.route('/rss')
def rss_feed():
    return redirect(url_for('feed'), code=301)


@app.route('/feed.xml')
def feed():
    fg = FeedGenerator()
    fg.title("Aisaka's Blog")
    fg.link(href=url_for('feed', _external=True), rel='self')
    # feedgen uses the last registered link for the RSS channel link.
    fg.link(href=request.url_root, rel='alternate')
    fg.description("Aisaka's Blog")
    posts = db.session.scalars(
        published_post_statement().order_by(Post.timestamp.desc(), Post.id.desc())
    ).all()
    for post in posts:
        entry = fg.add_entry(order='append')
        permalink = url_for('post', post_id=post.id, _external=True)
        entry.title(post.title)
        entry.link(href=permalink)
        entry.guid(permalink, permalink=True)
        entry.description(str(render_content(post.body, post.body_format, images=False)))
        timestamp = post.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        entry.pubDate(timestamp)
    return app.response_class(fg.rss_str(), content_type='application/rss+xml; charset=utf-8')


@app.route('/sitemap.xml')
def sitemap():
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    root = ET.Element(f'{{{namespace}}}urlset')

    def add_url(location, modified=None):
        item = ET.SubElement(root, f'{{{namespace}}}url')
        ET.SubElement(item, f'{{{namespace}}}loc').text = location
        if modified is not None:
            ET.SubElement(item, f'{{{namespace}}}lastmod').text = modified.isoformat()

    add_url(request.url_root)
    add_url(url_for('archive', _external=True))
    for post in db.session.scalars(published_post_statement()):
        add_url(url_for('post', post_id=post.id, _external=True), post.timestamp)
    for page in db.session.scalars(sa.select(Page).where(Page.is_published.is_(True))):
        add_url(url_for('public_page', slug=page.slug, _external=True), page.updated_at)
    return app.response_class(ET.tostring(root, encoding='utf-8', xml_declaration=True),
                              content_type='application/xml; charset=utf-8')


@app.route('/robots.txt')
def robots():
    return app.response_class('User-agent: *\n'
                              'Disallow: /admin\n'
                              'Disallow: /login\n'
                              'Disallow: /logout\n'
                              'Disallow: /register\n'
                              'Disallow: /reset_password_request\n'
                              'Disallow: /reset_password/\n'
                              f'Sitemap: {url_for("sitemap", _external=True)}\n',
                              content_type='text/plain; charset=utf-8')


@app.route('/<slug>')
def public_page(slug):
    resolved = page_for_public_slug(slug)
    if resolved is None:
        abort(404)
    page, is_redirect = resolved
    if is_redirect:
        return _redirect_to_public_page(page)
    if page.kind != PAGE_CONTENT:
        abort(404)
    return render_template('page/content.html', title=page.title, page=page)
