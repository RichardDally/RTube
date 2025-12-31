import logging
from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from rtube.models import db, Video, Comment, Playlist, Favorite
from rtube.models_auth import User

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to require admin role."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """List all users with their stats."""
    users_list = User.query.order_by(User.created_at.desc()).all()

    # Get video counts per user
    video_counts = dict(
        db.session.query(Video.owner_username, func.count(Video.id))
        .group_by(Video.owner_username)
        .all()
    )

    # Get comment counts per user
    comment_counts = dict(
        db.session.query(Comment.author_username, func.count(Comment.id))
        .group_by(Comment.author_username)
        .all()
    )

    # Get playlist counts per user
    playlist_counts = dict(
        db.session.query(Playlist.owner_username, func.count(Playlist.id))
        .group_by(Playlist.owner_username)
        .all()
    )

    # Get favorite counts per user
    favorite_counts = dict(
        db.session.query(Favorite.username, func.count(Favorite.id))
        .group_by(Favorite.username)
        .all()
    )

    # Build user data with stats
    users_data = []
    for user in users_list:
        users_data.append({
            'user': user,
            'video_count': video_counts.get(user.username, 0),
            'comment_count': comment_counts.get(user.username, 0),
            'playlist_count': playlist_counts.get(user.username, 0),
            'favorite_count': favorite_counts.get(user.username, 0),
            'is_online': user.is_online(),
        })

    return render_template('admin/users.html', users_data=users_data)


@admin_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password():
    """Change admin password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Verify current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
            return render_template('admin/change_password.html')

        # Check if new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('admin/change_password.html')

        # Validate new password
        is_valid, errors = User.validate_password(new_password)
        if not is_valid:
            for error in errors:
                flash(error, 'error')
            return render_template('admin/change_password.html')

        # Update password
        current_user.set_password(new_password)
        db.session.commit()
        logger.info(f"Admin user '{current_user.username}' changed their password")
        flash('Password changed successfully', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/change_password.html')
