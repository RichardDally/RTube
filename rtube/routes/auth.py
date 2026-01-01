from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, Response

from flask_login import login_user, logout_user, login_required, current_user

from rtube.models import db, Video, Comment, Favorite, Playlist
from rtube.models_auth import User

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
    oidc_service = current_app.config.get("OIDC_SERVICE")

    if not oidc_enabled or not oidc_service:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Build callback URL
        callback_url = url_for('auth.oidc_callback', _external=True)

        # Get authorization URL and store state in session
        auth_url, state = oidc_service.get_authorization_url(callback_url)
        session['oidc_state'] = state

        # Store next URL if provided
        next_page = request.args.get('next')
        if next_page:
            session['oidc_next'] = next_page

        return redirect(auth_url)

    except Exception as e:
        current_app.logger.error(f"OIDC login initiation failed: {e}")
        flash("Failed to initiate SSO login. Please try again.", "error")
        return redirect(url_for('auth.login'))


@auth_bp.route('/oidc/callback')
def oidc_callback():
    """Handle OIDC callback after authentication."""
    oidc_enabled = current_app.config.get("OIDC_ENABLED", False)
    oidc_service = current_app.config.get("OIDC_SERVICE")

    if not oidc_enabled or not oidc_service:
        flash("OIDC authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    # Check for errors from the provider
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', error)
        current_app.logger.error(f"OIDC callback error: {error} - {error_description}")
        flash(f"SSO authentication failed: {error_description}", "error")
        return redirect(url_for('auth.login'))

    # Get authorization code and state
    code = request.args.get('code')
    state = request.args.get('state')

    if not code:
        flash("SSO authentication failed: no authorization code received.", "error")
        return redirect(url_for('auth.login'))

    # Validate state to prevent CSRF
    expected_state = session.pop('oidc_state', None)
    if not expected_state or state != expected_state:
        current_app.logger.warning("OIDC callback: state mismatch (possible CSRF)")
        flash("SSO authentication failed: invalid state.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Exchange code for tokens and get user info
        callback_url = url_for('auth.oidc_callback', _external=True)
        userinfo = oidc_service.handle_callback(code, state, callback_url, expected_state)

        sub = userinfo.get('sub')
        username = userinfo.get('username')

        if not sub or not username:
            raise ValueError("Missing required user information from OIDC provider")

        # Find or create user
        user = User.query.filter_by(sso_subject=sub, auth_type='oidc').first()

        if not user:
            # Check if username already exists with different auth type
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                # Username conflict - append part of subject to make unique
                username = f"{username}_{sub[:8]}"

            user = User(
                username=username,
                auth_type='oidc',
                sso_subject=sub
            )
            db.session.add(user)
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
# SAML Routes
# =============================================================================

@auth_bp.route('/saml/login')
def saml_login():
    """Initiate SAML authentication flow."""
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    saml_enabled = current_app.config.get("SAML_ENABLED", False)
    saml_service = current_app.config.get("SAML_SERVICE")

    if not saml_enabled or not saml_service:
        flash("SAML authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Store next URL if provided
        next_page = request.args.get('next')
        return_to = next_page or url_for('videos.index', _external=True)

        # Get SAML login URL and redirect
        login_url = saml_service.get_login_url(request, return_to)
        return redirect(login_url)

    except Exception as e:
        current_app.logger.error(f"SAML login initiation failed: {e}")
        flash("Failed to initiate SSO login. Please try again.", "error")
        return redirect(url_for('auth.login'))


@auth_bp.route('/saml/acs', methods=['POST'])
def saml_acs():
    """SAML Assertion Consumer Service - handle SAML response from IdP."""
    saml_enabled = current_app.config.get("SAML_ENABLED", False)
    saml_service = current_app.config.get("SAML_SERVICE")

    if not saml_enabled or not saml_service:
        flash("SAML authentication is not configured.", "error")
        return redirect(url_for('auth.login'))

    try:
        # Process SAML response
        userinfo = saml_service.process_response(request)

        name_id = userinfo.get('name_id')
        username = userinfo.get('username')

        if not name_id or not username:
            raise ValueError("Missing required user information from SAML response")

        # Find or create user
        user = User.query.filter_by(sso_subject=name_id, auth_type='saml').first()

        if not user:
            # Check if username already exists with different auth type
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                # Username conflict - append part of name_id to make unique
                username = f"{username}_{name_id[:8]}"

            user = User(
                username=username,
                auth_type='saml',
                sso_subject=name_id
            )
            db.session.add(user)
            current_app.logger.info(f"Auto-created SAML user '{username}' (NameID: {name_id})")

        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user)
        current_app.logger.info(f"User '{username}' logged in via SAML")

        # Redirect to RelayState if provided, otherwise home
        relay_state = request.form.get('RelayState')
        if relay_state:
            return redirect(relay_state)
        return redirect(url_for('videos.index'))

    except ValueError as e:
        current_app.logger.error(f"SAML ACS validation error: {e}")
        flash(f"SSO authentication failed: {e}", "error")
        return redirect(url_for('auth.login'))
    except Exception as e:
        current_app.logger.error(f"SAML ACS processing failed: {e}")
        flash("SSO authentication failed. Please try again.", "error")
        return redirect(url_for('auth.login'))


@auth_bp.route('/saml/metadata')
def saml_metadata():
    """Return SAML Service Provider metadata."""
    saml_enabled = current_app.config.get("SAML_ENABLED", False)
    saml_service = current_app.config.get("SAML_SERVICE")

    if not saml_enabled or not saml_service:
        return "SAML not configured", 404

    try:
        metadata = saml_service.get_metadata(request)
        return Response(metadata, mimetype='application/xml')
    except Exception as e:
        current_app.logger.error(f"Failed to generate SAML metadata: {e}")
        return "Failed to generate metadata", 500


# =============================================================================
# Local/LDAP Authentication Routes
# =============================================================================


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('videos.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('auth/login.html', error="Username and password are required")

        ldap_enabled = current_app.config.get("LDAP_ENABLED", False)
        ldap_service = current_app.config.get("LDAP_SERVICE")

        if ldap_enabled and ldap_service:
            # LDAP mode: admin local fallback, everyone else via LDAP
            user = User.query.filter_by(username=username).first()

            # Allow local admin to login with local password
            if username == "admin" and user and user.is_local_user() and user.check_password(password):
                user.last_login = datetime.utcnow()
                db.session.commit()
                login_user(user)
                current_app.logger.info(f"Admin '{username}' logged in via local auth (LDAP mode)")

                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('videos.index'))

            # LDAP authentication for all other users
            if ldap_service.authenticate(username, password):
                if not user:
                    # Auto-create user on first LDAP login
                    user = User(username=username, auth_type="ldap")
                    db.session.add(user)
                    current_app.logger.info(f"Auto-created LDAP user '{username}'")

                user.last_login = datetime.utcnow()
                db.session.commit()
                login_user(user)
                current_app.logger.info(f"User '{username}' logged in via LDAP")

                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('videos.index'))

            current_app.logger.warning(f"Failed LDAP login attempt for username '{username}'")
            return render_template('auth/login.html', error="Invalid username or password")

        else:
            # Local authentication mode
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

    # Disable registration when LDAP is enabled
    ldap_enabled = current_app.config.get("LDAP_ENABLED", False)
    if ldap_enabled:
        flash("Registration is disabled. Please use your LDAP credentials to login.", "info")
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
