from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import abort, current_app, render_template, flash, redirect, send_from_directory, url_for, request, g
from flask_login import login_user, logout_user, current_user, login_required
from flask_babel import _, get_locale
import sqlalchemy as sa
from langdetect import detect, LangDetectException
from app import app, db
from app.forms import AboutForm, CategoryForm, CommentForm, LinkForm, LoginForm, MessageForm, RegistrationForm, EditProfileForm, \
    EmptyForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, SearchForm, TodoForm
from app.models import About, Category, Link, Notification, Comment, Message, Todo, User, Post, Movie
from app.email import send_password_reset_email
from app.translate import translate
from flask_ckeditor import upload_success, upload_fail
import os


@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()
    g.locale = str(get_locale())


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        try:
            language = detect(form.post.data)
        except LangDetectException:
            language = ''
        post = Post(body=form.post.data, author=current_user,
                    language=language, category_id=form.category.data)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('index'))
    page = request.args.get('page', 1, type=int)
    categories = Category.query.order_by(Category.id.asc()).all()
    posts = db.paginate(current_user.following_posts(), page=page,
                        per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('index', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Home'), form=form,categories=categories,
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@app.route('/explore')
def explore():
    page = request.args.get('page', 1, type=int)
    query = sa.select(Post).order_by(Post.timestamp.desc())
    categories = Category.query.order_by(Category.id.asc()).all()
    posts = db.paginate(query, page=page,
                        per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('explore', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('explore', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Explore'),
                           posts=posts.items, categories=categories, next_url=next_url,
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


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
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


@app.route('/user/<username>')
@login_required
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    page = request.args.get('page', 1, type=int)
    query = user.posts.select().order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page,
                        per_page=app.config['POSTS_PER_PAGE'],
                        error_out=False)
    next_url = url_for('user', username=user.username, page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('user', username=user.username, page=posts.prev_num) \
        if posts.has_prev else None
    form = EmptyForm()
    return render_template('user/user.html', title=_('User Profile'),user=user, posts=posts.items,
                           next_url=next_url, prev_url=prev_url, form=form)

@app.route('/user/<username>/popup')
def user_popup(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    form = EmptyForm()
    return render_template('user/user_popup.html', user=user, form=form)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title=_('Edit Profile'),
                           form=form)


@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == username))
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('index'))
        if user == current_user:
            flash(_('You cannot follow yourself!'))
            return redirect(url_for('user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(_('You are following %(username)s!', username=username))
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))


@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == username))
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('index'))
        if user == current_user:
            flash(_('You cannot unfollow yourself!'))
            return redirect(url_for('user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(_('You are not following %(username)s.', username=username))
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))


@app.route('/translate', methods=['POST'])
@login_required
def translate_text():
    data = request.get_json()
    return {'text': translate(data['text'],
                              data['source_language'],
                              data['dest_language'])}
   
@app.route('/movie', methods=['GET', 'POST'])
def movie():
    if request.method == 'POST':
        if not current_user.is_authenticated:  # 如果当前用户未认证
            return redirect(url_for('movie'))  # 重定向到主页
        # 获取表单数据
        title = request.form.get('title')
        year = request.form.get('year')
        # 验证数据
        if not title or not year or len(year) != 4 or len(title) > 60:
            flash('Invalid input.')
            return redirect(url_for('movie'))
        movie = Movie(title=title, year=year)
        db.session.add(movie)
        db.session.commit()
        flash('Item created.')
        return redirect(url_for('movie'))
    
    movies = Movie.query.all()
    return render_template('movie/movie.html', title=_('Movie'),movies=movies)

@app.route('/movie/edit/<int:movie_id>', methods=['GET', 'POST'])
@login_required
def movie_edit(movie_id):
    movie = Movie.query.get_or_404(movie_id)

    if request.method == 'POST':  # 处理编辑表单的提交请求
        title = request.form['title']
        year = request.form['year']

        if not title or not year or len(year) != 4 or len(title) > 60:
            flash('Invalid input.')
            return redirect(url_for('movie_edit', movie_id=movie_id))  # 重定向回对应的编辑页面

        movie.title = title  # 更新标题
        movie.year = year  # 更新年份
        db.session.commit()  # 提交数据库会话
        flash('Item updated.')
        return redirect(url_for('movie'))  # 重定向回主页

    return render_template('movie/movie_edit.html', title=_('Edit Movie'), movie=movie)  # 传入被编辑的电影记录


@app.route('/movie/delete/<int:movie_id>', methods=['POST'])
@login_required
def delete(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    db.session.delete(movie)
    db.session.commit()
    flash('Item deleted.')
    return redirect(url_for('movie'))

@app.route('/post/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.')
    return redirect(url_for('index'))

@app.route('/comment', methods=['GET', 'POST'])
def comment():
    form = CommentForm()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        body = form.body.data
        comment = Comment(body=body, name=name, email=email)
        
        db.session.add(comment)
        db.session.commit()
        flash(_('Your comment has been sent to the world!'))
        return redirect(url_for('comment'))
    
    page = request.args.get('page', 1, type=int)
    query = sa.select(Comment).order_by(Comment.timestamp.desc())
    comments = db.paginate(query, page=page,
                           per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('comment', page=comments.next_num) \
        if comments.has_next else None
    prev_url = url_for('comment', page=comments.prev_num) \
        if comments.has_prev else None   
    return render_template('comment/comment.html', title=_('Comment'), form=form, comments=comments.items,
                           next_url=next_url, prev_url=prev_url)

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash('Comment Deleted.')
    return redirect(url_for('comment'))
    
@app.route('/todo', methods=['GET', 'POST'])
def todo():
    form = TodoForm()
    if form.validate_on_submit():
        title = form.title.data
        todo = Todo(title=title, complete=False)
        
        db.session.add(todo)
        db.session.commit()
        flash(_('Your todo have been added!'))
        return redirect(url_for('todo'))
    
    page = request.args.get('page', 1, type=int)
    query = sa.select(Todo).order_by(Todo.id.desc())
    todos = db.paginate(query, page=page,
                           per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('todo', page=todos.next_num) \
        if todos.has_next else None
    prev_url = url_for('todo', page=todos.prev_num) \
        if todos.has_prev else None
    
    return render_template('todo/todo.html', title=_('Todo'), form=form, todos=todos.items,
                           next_url=next_url, prev_url=prev_url)
        
@app.route('/todo/update/<int:todo_id>', methods=['POST'])
@login_required
def update_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id).first()
    todo.complete = not todo.complete
    db.session.commit()
    return redirect(url_for("todo"))

@app.route('/todo/delete/<int:todo_id>', methods=['POST'])
@login_required
def delete_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    flash('Todo Deleted.')
    return redirect(url_for('todo'))

@app.route('/todo/edit/<int:todo_id>', methods=['GET', 'POST'])
@login_required
def todo_edit(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    form = TodoForm(obj=todo)  # Initialize the form with the existing todo data

    if form.validate_on_submit():  # Check if the form was submitted and is valid
        todo.title = form.title.data  # Update the todo title with form data
        todo.complete = form.complete.data  # Update the completion status
        db.session.commit()
        flash('Todo updated.')
        return redirect(url_for('todo'))

    return render_template('todo/todo_edit.html', title=_('Edit Todo'), form=form, todo=todo)


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')  # Get the search query from the URL
    posts = Post.query.all()  # Default to showing all posts

    if query:
        # Search in the 'body' of the posts
        posts = Post.query.filter(Post.body.contains(query)).all()

    return render_template('post/search_results.html', title=_('Search'), query=query, posts=posts)

@app.route('/files/<path:filename>')
def uploaded_files(filename):
    path = '/file/upload/directory/'
    return send_from_directory(path, filename)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('post')
    extension = file.filename.split('.')[1].lower()
    if extension not in ['jpg', 'gif', 'png', 'jpeg']:
        return upload_fail(message='Image only!')
    file.save(os.path.join('/file/upload/directory', file.filename))
    url = url_for('uploaded_files', filename=file.filename)
    return upload_success(url=url)

@app.route('/send_message/<recipient>', methods=['GET', 'POST'])
@login_required
def send_message(recipient):
    user = db.first_or_404(sa.select(User).where(User.username == recipient))
    form = MessageForm()
    if form.validate_on_submit():
        msg = Message(author=current_user, recipient=user,
                      body=form.message.data)
        db.session.add(msg)
        user.add_notification('unread_message_count',
                              user.unread_message_count())
        db.session.commit()
        flash(_('Your message has been sent.'))
        return redirect(url_for('user', username=recipient))
    return render_template('send_message.html', title=_('Send Message'),
                           form=form, recipient=recipient)
    
@app.route('/messages')
@login_required
def messages():
    current_user.last_message_read_time = datetime.now(timezone.utc)
    current_user.add_notification('unread_message_count', 0)
    db.session.commit()
    page = request.args.get('page', 1, type=int)
    query = current_user.messages_received.select().order_by(
        Message.timestamp.desc())
    messages = db.paginate(query, page=page,
                           per_page=app.config['POSTS_PER_PAGE'],
                           error_out=False)
    next_url = url_for('messages', page=messages.next_num) \
        if messages.has_next else None
    prev_url = url_for('messages', page=messages.prev_num) \
        if messages.has_prev else None
    return render_template('messages.html', title=_('Messages'), messages=messages.items,
                           next_url=next_url, prev_url=prev_url)
    
@app.route('/notifications')
@login_required
def notifications():
    since = request.args.get('since', 0.0, type=float)
    query = current_user.notifications.select().where(
        Notification.timestamp > since).order_by(Notification.timestamp.asc())
    notifications = db.session.scalars(query)
    return [{
        'name': n.name,
        'data': n.get_data(),
        'timestamp': n.timestamp
    } for n in notifications]
    
@app.route('/export_posts')
@login_required
def export_posts():
    if current_user.get_task_in_progress('export_posts'):
        flash(_('An export task is currently in progress'))
    else:
        current_user.launch_task('export_posts', _('Exporting posts...'))
        db.session.commit()
    return redirect(url_for('user', username=current_user.username))

@app.route('/test_redis')
def test_redis():
    try:
        app.redis.ping()
        return "Redis is connected!"
    except Exception as e:
        app.logger.error(f"Redis connection error: {e}")
        return "Redis connection failed."

@app.route('/categories', methods=['GET', 'POST'])
def categories():
    form = CategoryForm()
    
    # Handle form submission for adding a new category
    if form.validate_on_submit():
        if db.session.execute(sa.select(Category).filter_by(name=form.name.data)).scalar():
            flash('Category name already exists.')
            return redirect(url_for('categories'))

        new_category = Category(name=form.name.data)
        db.session.add(new_category)
        db.session.commit()

        flash('New category created successfully.')
        return redirect(url_for('categories'))

    # Retrieve all categories for display
    categories = db.session.execute(sa.select(Category)).scalars().all()
    return render_template('post/categories.html', title=_('Categories'), form=form, categories=categories)

# Route for deleting a category
@app.route('/delete_category/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    category = db.session.get(Category, category_id)
    if category:
        db.session.delete(category)
        db.session.commit()
        flash(f'Category "{category.name}" has been deleted.')
    else:
        flash('Category not found.')
    return redirect(url_for('categories'))

@app.route('/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        category.name = form.name.data
        db.session.commit()
        flash('The category has been updated.', 'success')
        return redirect(url_for('categories'))
    return render_template('post/edit_category.html', title=_('Category'), form=form, category=category)

@app.route('/category/<int:category_id>', methods=['GET'])
def posts_by_category(category_id):
    # Query for the category by its ID
    category = Category.query.get_or_404(category_id)
    
    # Get all posts that belong to this category
    posts = Post.query.filter_by(category_id=category.id).all()

    # Render the posts in the category using a template
    return render_template('post/posts_by_category.html', category=category, posts=posts)

@app.route('/post/<int:post_id>', methods=['GET'])
def post(post_id):
    # Query the database to get the post by its id
    post = Post.query.get_or_404(post_id)
    return render_template('post/post.html', title=_('Post'), post=post)

@app.route('/about', methods=['GET'])
def about():
    # Fetch the current "About" content from the database
    about_content = About.query.first()  # Assuming there's only one 'About' entry
    return render_template('about/about.html', title=_('About'), about_content=about_content)

@app.route('/about/edit', methods=['GET', 'POST'])
@login_required  # Only authenticated users can edit
def edit_about():
    # Fetch the current "About" content from the database
    about_content = About.query.first()

    form = AboutForm()

    if form.validate_on_submit():
        if not about_content:
            about_content = About(body=form.body.data)
        else:
            about_content.body = form.body.data
        db.session.add(about_content)
        db.session.commit()
        flash(_('The about page has been updated.'))
        return redirect(url_for('about'))

    if request.method == 'GET' and about_content:
        form.body.data = about_content.body

    return render_template('about/edit_about.html', title=_('Edit About'),form=form)

# Display all links
@app.route('/links', methods=['GET', 'POST'])
def links():
    form = LinkForm()
    if form.validate_on_submit():
        # Ensure URL has a valid scheme
        url = form.url.data
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url  # Default to https if no scheme provided

        # Add the new link to the database
        link = Link(name=form.name.data, email=form.email.data, text=form.text.data, url=url)
        db.session.add(link)
        db.session.commit()
        flash(_('Link added successfully!'))
        return redirect(url_for('links'))

    # Query and display all links, ordered by creation date
    links = Link.query.order_by(Link.created_at.desc()).all()
    return render_template('links.html', title=_('Links'), form=form, links=links)


@app.route('/edit_link/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_link(id):
    link = Link.query.get_or_404(id)
    form = LinkForm(obj=link)
    
    if form.validate_on_submit():
        # 如果 URL 不以 http:// 或 https:// 开头，自动加上 https://
        if not form.url.data.startswith(('http://', 'https://')):
            form.url.data = 'https://' + form.url.data
        
        # 更新数据库中的链接
        form.populate_obj(link)
        db.session.commit()
        flash('Link has been updated successfully.')
        return redirect(url_for('links'))
    
    return render_template('edit_link.html', title=_('Edit Link'), form=form, link=link)

@app.route('/link/<int:id>/delete', methods=['POST'])
@login_required
def delete_link(id):
    link = Link.query.get_or_404(id)
    db.session.delete(link)
    db.session.commit()
    flash(_('Link deleted successfully!'))
    return redirect(url_for('links'))

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author != current_user:
        abort(403)  # Unauthorized access

    form = PostForm()

    if form.validate_on_submit():
        post.body = form.post.data
        post.category_id = form.category.data
        db.session.commit()
        flash(_('Your post has been updated!'))
        return redirect(url_for('post', post_id=post.id))

    # Populate form with the current post data
    form.post.data = post.body
    form.category.data = post.category_id

    return render_template('post/edit_post.html', title=_('Edit Post'), form=form, post=post)
