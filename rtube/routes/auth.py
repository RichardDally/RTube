import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from rtube.models import db
from rtube.models_auth import User

logger = logging.getLogger(__name__)

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
            logger.info(f"User '{username}' logged in successfully")

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('videos.index'))

        logger.warning(f"Failed login attempt for username '{username}'")
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

        logger.info(f"New user '{username}' registered successfully")
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f"User '{username}' logged out")
    return redirect(url_for('videos.index'))
