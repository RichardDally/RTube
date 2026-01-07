import logging
import re
from pathlib import Path
from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from rtube.models import db, Video, VideoVisibility, Comment, Playlist, Favorite
from rtube.models_auth import User, UserRole
from rtube.services.encoder import encoder_service

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


@admin_bp.route('/users/<username>/role', methods=['POST'])
@login_required
@admin_required
def change_user_role(username):
    """Change a user's role."""
    # Prevent changing the default admin user's role
    if username == 'admin':
        flash('Cannot change the role of the default admin user', 'error')
        return redirect(url_for('admin.users'))

    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin.users'))

    new_role = request.form.get('role', '')
    valid_roles = [UserRole.VIEWER.value, UserRole.UPLOADER.value, UserRole.ADMIN.value]

    if new_role not in valid_roles:
        flash('Invalid role', 'error')
        return redirect(url_for('admin.users'))

    old_role = user.role
    user.role = new_role
    db.session.commit()

    logger.info(f"Admin '{current_user.username}' changed role of user '{username}' from '{old_role}' to '{new_role}'")
    flash(f"Role of '{username}' changed to '{new_role}'", 'success')
    return redirect(url_for('admin.users'))


def _scan_orphan_videos():
    """Scan for encoded videos that are not in the database.

    Returns a list of dictionaries with video info:
    - filename: base name without extension (used as title)
    - m3u8_path: path to the main .m3u8 file
    - qualities: list of available qualities (e.g., ['360p', '720p', '1080p'])
    """
    videos_folder = Path(current_app.config.get('VIDEOS_FOLDER', ''))
    if not videos_folder.exists():
        return []

    # Get all video filenames currently in the database
    existing_filenames = {v.filename for v in Video.query.with_entities(Video.filename).all()}

    # Pattern to match resolution in filename (e.g., _720p.m3u8)
    resolution_pattern = re.compile(r'_(\d+p)\.m3u8$')

    orphan_videos = []

    # Find all .m3u8 files that don't have a resolution suffix (master playlists)
    for m3u8_file in videos_folder.glob('*.m3u8'):
        filename = m3u8_file.stem  # filename without .m3u8

        # Skip if this is a resolution-specific file (e.g., video_720p.m3u8)
        if resolution_pattern.search(m3u8_file.name):
            continue

        # Skip if already in database
        if filename in existing_filenames:
            continue

        # Find available qualities for this video
        qualities = []
        for quality_file in videos_folder.glob(f'{filename}_*.m3u8'):
            match = resolution_pattern.search(quality_file.name)
            if match:
                qualities.append(match.group(1))

        # Sort qualities by resolution (numeric part)
        qualities.sort(key=lambda q: int(q.replace('p', '')))

        orphan_videos.append({
            'filename': filename,
            'm3u8_path': str(m3u8_file),
            'qualities': qualities,
        })

    # Sort by filename
    orphan_videos.sort(key=lambda v: v['filename'].lower())

    return orphan_videos


@admin_bp.route('/import-videos')
@login_required
@admin_required
def import_videos():
    """Show orphan encoded videos that can be imported into the database."""
    orphan_videos = _scan_orphan_videos()
    return render_template('admin/import_videos.html', orphan_videos=orphan_videos)


@admin_bp.route('/import-videos', methods=['POST'])
@login_required
@admin_required
def import_videos_submit():
    """Import selected orphan videos into the database."""
    selected_filenames = request.form.getlist('videos')

    if not selected_filenames:
        flash('No videos selected', 'error')
        return redirect(url_for('admin.import_videos'))

    # Get orphan videos to validate selection
    orphan_videos = _scan_orphan_videos()
    orphan_filenames = {v['filename'] for v in orphan_videos}

    videos_folder = Path(current_app.config.get('VIDEOS_FOLDER', ''))
    thumbnails_folder = Path(current_app.config.get('THUMBNAILS_FOLDER', ''))

    imported_count = 0
    thumbnail_count = 0
    for filename in selected_filenames:
        # Validate that this is indeed an orphan video
        if filename not in orphan_filenames:
            continue

        # Check if already exists (race condition protection)
        if Video.query.filter_by(filename=filename).first():
            continue

        # Generate thumbnail
        thumbnail_filename = f"{filename}.jpg"
        thumbnail_path = thumbnails_folder / thumbnail_filename
        thumbnail_generated = encoder_service.generate_thumbnail_from_hls(
            videos_folder, filename, thumbnail_path
        )

        # Create new video entry
        video = Video(
            filename=filename,
            title=filename,  # Use filename as title
            visibility=VideoVisibility.PRIVATE.value,
            owner_username=current_user.username,
            thumbnail=thumbnail_filename if thumbnail_generated else None,
        )
        db.session.add(video)
        imported_count += 1
        if thumbnail_generated:
            thumbnail_count += 1

    if imported_count > 0:
        db.session.commit()
        logger.info(f"Admin '{current_user.username}' imported {imported_count} orphan video(s) with {thumbnail_count} thumbnail(s)")
        flash(f'Successfully imported {imported_count} video(s) with {thumbnail_count} thumbnail(s)', 'success')
    else:
        flash('No videos were imported', 'warning')

    return redirect(url_for('admin.import_videos'))
