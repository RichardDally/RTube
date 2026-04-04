from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session

from flask_login import login_user, logout_user, login_required, current_user

from rtube.models import db, Video, Comment, Favorite, Playlist
from rtube.models_auth import User, UserRole

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# =============================================================================
# OIDC Routes
# =============================================================================

@auth_bp.route('/oidc/login')
def oidc_login():
    """Initiate OIDC authentication flow."""
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    oidc_enabled = current_app.config.get("OIDC_ENABLED", False)
    if not oidc_enabled:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    oauth = current_app.config.get("OAUTH_INSTANCE")
    if not oauth or not oauth.oidc:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    # Store next URL if provided. Only store safe (relative) URLs to prevent open redirects.
    next_page = request.args.get('next')
    if next_page and next_page.startswith('/') and not next_page.startswith('//'):
        session['oidc_next'] = next_page

    # Redirect to OIDC provider
    redirect_uri = url_for('auth.oidc_callback', _external=True)
    return oauth.oidc.authorize_redirect(redirect_uri)


@auth_bp.route('/oidc/callback')
def oidc_callback():
    """Handle OIDC callback after authentication."""
    oidc_enabled = current_app.config.get("OIDC_ENABLED", False)
    if not oidc_enabled:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    oauth = current_app.config.get("OAUTH_INSTANCE")
    oidc_config = current_app.config.get("OIDC_CONFIG")

    if not oauth or not oauth.oidc or not oidc_config:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Get token from OIDC provider
        token = oauth.oidc.authorize_access_token()
        
        # Get user info from OIDC
        user_info = token.get('userinfo')
        if not user_info:
            flash("SSO authentication failed: missing user information.", "error")
            return redirect(url_for('auth.login'))

        sub = user_info.get('sub')
        username = user_info.get(oidc_config.username_claim) or user_info.get('preferred_username') or user_info.get('email')

        if not sub or not username:
            current_app.logger.error(f"OIDC: Missing required user information. Got: {user_info}")
            flash("SSO authentication failed: missing user information.", "error")
            return redirect(url_for('auth.login'))

        # Clean username (remove email domain if present, replace invalid characters)
        import re
        if '@' in username:
            username = username.split('@')[0]
        # Ensure alphanumeric characters only (replace other chars with underscores)
        username = re.sub(r'[^a-zA-Z0-9_]', '_', username)
        
        # Trim to max length and ensure minimum length
        username = username[:30]
        if len(username) < 3:
            username = f"{username}_user"
            while len(username) < 3:
                username += "0"

        # Find user by sub first (most secure & reliable)
        user = User.query.filter_by(sso_subject=sub).first()

        if not user:
            # Fallback to username check (for legacy SSO users without a sub, or new users)
            user_by_name = User.query.filter_by(username=username).first()

            if user_by_name:
                if user_by_name.auth_type == 'sso':
                    # Upgrade legacy SSO user to use sso_subject
                    user = user_by_name
                    user.sso_subject = sub
                else:
                    # COLLISION: This username matches a local user (like 'admin')!
                    # We must append a unique suffix to avoid Account Takeover.
                    original_username = username
                    import secrets
                    while User.query.filter_by(username=username).first():
                        suffix = secrets.token_hex(2)
                        username = f"{original_username[:25]}_{suffix}"

            # If user is STILL not found (either no collision, or we resolved collision)
            if not user:
                import secrets
                # Create new SSO user
                user = User(
                    username=username,
                    role=UserRole.VIEWER.value,
                    auth_type='sso',
                    sso_subject=sub
                )
                # Set a random password (user won't use it, they'll use OIDC)
                user.set_password(secrets.token_urlsafe(32))
                db.session.add(user)
                db.session.commit()
                current_app.logger.info(f"Auto-created OIDC user '{username}' (sub: {sub})")

        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user)
        current_app.logger.info(f"User '{username}' logged in via OIDC")

        # Redirect to stored next URL or home
        next_page = session.pop('oidc_next', None)
        if next_page:
            return redirect(next_page)
        return redirect(url_for('videos.index'))

    except Exception as e:
        current_app.logger.error(f"OIDC callback processing failed: {e}")
        flash("SSO authentication failed. Please try again.", "error")
        return redirect(url_for('auth.login'))



# =============================================================================
# Local Authentication Routes
# =============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    oidc_enabled = current_app.config.get("OIDC_ENABLED", False)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('auth/login.html', error="Username and password are required", oidc_enabled=oidc_enabled)

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            current_app.logger.info(f"User '{username}' logged in successfully")

            # Warn admin user if still using default password
            if user.username == "admin" and user.has_default_password():
                session['has_default_admin_password'] = True
                current_app.logger.warning("Admin user logged in with default password")
            elif user.is_admin():
                session['has_default_admin_password'] = False

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('videos.index'))

        current_app.logger.warning(f"Failed login attempt for username '{username}'")
        return render_template('auth/login.html', error="Invalid username or password", oidc_enabled=oidc_enabled)

    return render_template('auth/login.html', oidc_enabled=oidc_enabled)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    # Disable registration when ENABLE_REGISTRATION is False
    if not current_app.config.get("ENABLE_REGISTRATION", True):
        flash("Registration is disabled.", "error")
        return redirect(url_for('auth.login'))

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
        user = User(username=username, role=UserRole.VIEWER.value)
        user.set_password(password)
        user.last_login = datetime.utcnow()
        db.session.add(user)
        db.session.commit()
        
        login_user(user)

        current_app.logger.info(f"New user '{username}' registered and logged in successfully")
        flash("Account created successfully. You are now logged in.", "success")
        return redirect(url_for('videos.index'))

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

    # Get user's playlists
    playlists = Playlist.query.filter_by(owner_username=user.username).order_by(Playlist.updated_at.desc()).all()

    return render_template(
        'auth/profile.html',
        profile_user=user,
        videos=videos,
        comments_data=comments_data,
        favorites_data=favorites_data,
        playlists=playlists,
        is_own_profile=is_own_profile
    )
