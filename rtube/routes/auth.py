from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user

from rtube.models import db, Video, Comment, Favorite
from rtube.models_auth import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('auth/login.html', error="Username and password are required")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            current_app.logger.info(f"User '{username}' logged in successfully")

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('videos.index'))

        current_app.logger.warning(f"Failed login attempt for username '{username}'")
        return render_template('auth/login.html', error="Invalid username or password")

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        # Validate username
        username_valid, username_errors = User.validate_username(username)
        if not username_valid:
            return render_template('auth/register.html', error=username_errors[0], username=username)

        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('auth/register.html', error="Username already taken", username=username)

        # Check password confirmation
        if password != password_confirm:
            return render_template('auth/register.html', error="Passwords do not match", username=username)

        # Validate password
        password_valid, password_errors = User.validate_password(password)
        if not password_valid:
            return render_template('auth/register.html', error=password_errors[0], username=username)

        # Create user
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        current_app.logger.info(f"New user '{username}' registered successfully")
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    current_app.logger.info(f"User '{username}' logged out")
    return redirect(url_for('videos.index'))


@auth_bp.route('/profile')
@login_required
def profile():
    """Display the current user's profile with their videos and comments."""
    return view_user_profile(current_user.username)


@auth_bp.route('/profile/<username>')
@login_required
def user_profile(username):
    """Display a specific user's profile."""
    return view_user_profile(username)


def view_user_profile(username):
    """Helper function to display a user's profile."""
    # Check if user exists
    user = User.query.filter_by(username=username).first()
    if not user:
        return render_template(
            '404.html',
            title="User not found",
            message=f"The user '{username}' doesn't exist."
        ), 404

    # Get user's videos ordered by creation date (newest first)
    videos = Video.query.filter_by(owner_username=username).order_by(Video.created_at.desc()).all()

    # Get user's comments with associated video info
    comments = Comment.query.filter_by(author_username=username).order_by(Comment.created_at.desc()).all()

    # Build comment data with video info
    comments_data = []
    for comment in comments:
        video = db.session.get(Video, comment.video_id)
        comments_data.append({
            'comment': comment,
            'video': video
        })

    # Get user's favorites (visible to all authenticated users)
    favorites_data = []
    is_own_profile = current_user.is_authenticated and current_user.username == user.username
    favorites = Favorite.query.filter_by(username=user.username).order_by(Favorite.created_at.desc()).all()
    for favorite in favorites:
        video = db.session.get(Video, favorite.video_id)
        if video:  # Video might have been deleted
            favorites_data.append({
                'favorite': favorite,
                'video': video
            })

    return render_template(
        'auth/profile.html',
        profile_user=user,
        videos=videos,
        comments_data=comments_data,
        favorites_data=favorites_data,
        is_own_profile=is_own_profile
    )
