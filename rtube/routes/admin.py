import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from rtube.models import db, Video, VideoVisibility, Comment, Playlist, Favorite, EncodingJob, WatchHistory
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
    preview_count = 0
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

        # Generate preview
        preview_filename = f"{filename}_preview.webm"
        preview_path = thumbnails_folder / preview_filename
        preview_generated = encoder_service.generate_preview_from_hls(
            videos_folder, filename, preview_path
        )

        # Create new video entry
        video = Video(
            filename=filename,
            title=filename,  # Use filename as title
            visibility=VideoVisibility.PRIVATE.value,
            owner_username=current_user.username,
            thumbnail=thumbnail_filename if thumbnail_generated else None,
            preview=preview_filename if preview_generated else None,
        )
        db.session.add(video)
        imported_count += 1
        if thumbnail_generated:
            thumbnail_count += 1
        if preview_generated:
            preview_count += 1

    if imported_count > 0:
        db.session.commit()
        logger.info(f"Admin '{current_user.username}' imported {imported_count} orphan video(s) with {thumbnail_count} thumbnail(s) and {preview_count} preview(s)")
        flash(f'Successfully imported {imported_count} video(s) with {thumbnail_count} thumbnail(s) and {preview_count} preview(s)', 'success')
    else:
        flash('No videos were imported', 'warning')

    return redirect(url_for('admin.import_videos'))


@admin_bp.route('/regenerate-previews')
@login_required
@admin_required
def regenerate_previews():
    """Show videos that are missing previews."""
    videos = Video.query.filter(
        (Video.preview == None) | (Video.preview == '')
    ).order_by(Video.created_at.desc()).all()
    return render_template('admin/regenerate_previews.html', videos=videos)


@admin_bp.route('/regenerate-previews', methods=['POST'])
@login_required
@admin_required
def regenerate_previews_submit():
    """Regenerate previews for selected videos."""
    selected_ids = request.form.getlist('videos')

    if not selected_ids:
        flash('No videos selected', 'error')
        return redirect(url_for('admin.regenerate_previews'))

    videos_folder = Path(current_app.config.get('VIDEOS_FOLDER', ''))
    thumbnails_folder = Path(current_app.config.get('THUMBNAILS_FOLDER', ''))

    preview_count = 0
    for video_id in selected_ids:
        video = db.session.get(Video, int(video_id))
        if not video:
            continue

        # Generate preview
        preview_filename = f"{video.filename}_preview.webm"
        preview_path = thumbnails_folder / preview_filename
        preview_generated = encoder_service.generate_preview_from_hls(
            videos_folder, video.filename, preview_path
        )

        if preview_generated:
            video.preview = preview_filename
            preview_count += 1

    if preview_count > 0:
        db.session.commit()
        logger.info(f"Admin '{current_user.username}' regenerated {preview_count} preview(s)")
        flash(f'Successfully generated {preview_count} preview(s)', 'success')
    else:
        flash('No previews were generated', 'warning')

    return redirect(url_for('admin.regenerate_previews'))


def _get_folder_size(folder_path: Path) -> int:
    """Calculate total size of all files in a folder (in bytes)."""
    total_size = 0
    if folder_path.exists():
        for item in folder_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
    return total_size


def _format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    """Display analytics dashboard with platform statistics."""
    now = datetime.utcnow()
    today = now.date()
    week_ago = today - timedelta(days=7)

    # Get period from query param (default: 30 days)
    period = request.args.get('period', '30d')
    period_map = {
        '30d': 30,
        '6m': 180,
        '1y': 365,
        '5y': 1825,
    }
    period_days = period_map.get(period, 30)
    period_start = today - timedelta(days=period_days)

    # === Overview Stats ===
    total_videos = Video.query.count()
    total_users = User.query.count()
    total_comments = Comment.query.filter_by(is_deleted=False).count()
    total_views = db.session.query(func.sum(Video.view_count)).scalar() or 0

    # Videos by visibility
    public_videos = Video.query.filter_by(visibility='public').count()
    private_videos = Video.query.filter_by(visibility='private').count()

    # === Storage Stats ===
    videos_folder = Path(current_app.config.get('VIDEOS_FOLDER', ''))
    thumbnails_folder = Path(current_app.config.get('THUMBNAILS_FOLDER', ''))

    videos_size = _get_folder_size(videos_folder)
    thumbnails_size = _get_folder_size(thumbnails_folder)
    total_storage = videos_size + thumbnails_size

    # Count files
    video_files_count = len(list(videos_folder.glob('*.m3u8'))) if videos_folder.exists() else 0
    ts_files_count = len(list(videos_folder.glob('*.ts'))) if videos_folder.exists() else 0
    thumbnail_files_count = len(list(thumbnails_folder.glob('*'))) if thumbnails_folder.exists() else 0

    storage_stats = {
        'videos_size': _format_size(videos_size),
        'thumbnails_size': _format_size(thumbnails_size),
        'total_size': _format_size(total_storage),
        'video_files': video_files_count,
        'ts_segments': ts_files_count,
        'thumbnails': thumbnail_files_count,
    }

    # === Top Videos (by views) ===
    top_videos = Video.query.order_by(Video.view_count.desc()).limit(10).all()

    # === Recent Activity ===
    recent_videos = Video.query.order_by(Video.created_at.desc()).limit(5).all()
    recent_comments = Comment.query.filter_by(is_deleted=False).order_by(Comment.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    # === Encoding Stats ===
    encoding_stats = {
        'total': EncodingJob.query.count(),
        'completed': EncodingJob.query.filter_by(status='completed').count(),
        'failed': EncodingJob.query.filter_by(status='failed').count(),
        'pending': EncodingJob.query.filter_by(status='pending').count(),
        'encoding': EncodingJob.query.filter_by(status='encoding').count(),
    }

    # === Activity Over Time (configurable period) ===
    # Videos uploaded per day
    videos_by_day = db.session.query(
        func.date(Video.created_at).label('date'),
        func.count(Video.id).label('count')
    ).filter(
        Video.created_at >= period_start
    ).group_by(
        func.date(Video.created_at)
    ).order_by('date').all()

    # Comments per day
    comments_by_day = db.session.query(
        func.date(Comment.created_at).label('date'),
        func.count(Comment.id).label('count')
    ).filter(
        Comment.created_at >= period_start,
        Comment.is_deleted == False
    ).group_by(
        func.date(Comment.created_at)
    ).order_by('date').all()

    # Users registered per day
    users_by_day = db.session.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).filter(
        User.created_at >= period_start
    ).group_by(
        func.date(User.created_at)
    ).order_by('date').all()

    # Build chart data (fill in missing days with 0)
    chart_labels = []
    chart_videos = []
    chart_comments = []
    chart_users = []

    videos_dict = {str(row.date): row.count for row in videos_by_day}
    comments_dict = {str(row.date): row.count for row in comments_by_day}
    users_dict = {str(row.date): row.count for row in users_by_day}

    # Determine label format based on period length
    if period_days <= 60:
        date_format = '%b %d'  # Jan 15
    elif period_days <= 365:
        date_format = '%b %d'  # Jan 15
    else:
        date_format = '%b %Y'  # Jan 2024

    for i in range(period_days, -1, -1):
        day = today - timedelta(days=i)
        day_str = str(day)
        chart_labels.append(day.strftime(date_format))
        chart_videos.append(videos_dict.get(day_str, 0))
        chart_comments.append(comments_dict.get(day_str, 0))
        chart_users.append(users_dict.get(day_str, 0))

    # === User Stats ===
    # Top uploaders
    top_uploaders = db.session.query(
        Video.owner_username,
        func.count(Video.id).label('video_count'),
        func.sum(Video.view_count).label('total_views')
    ).filter(
        Video.owner_username != None
    ).group_by(
        Video.owner_username
    ).order_by(
        func.count(Video.id).desc()
    ).limit(10).all()

    # Top commenters
    top_commenters = db.session.query(
        Comment.author_username,
        func.count(Comment.id).label('comment_count')
    ).filter(
        Comment.is_deleted == False
    ).group_by(
        Comment.author_username
    ).order_by(
        func.count(Comment.id).desc()
    ).limit(10).all()

    # Users by role
    users_by_role = db.session.query(
        User.role,
        func.count(User.id).label('count')
    ).group_by(User.role).all()

    role_stats = {row.role: row.count for row in users_by_role}

    # === Week-over-week comparisons ===
    videos_this_week = Video.query.filter(Video.created_at >= week_ago).count()
    videos_last_week = Video.query.filter(
        Video.created_at >= week_ago - timedelta(days=7),
        Video.created_at < week_ago
    ).count()

    comments_this_week = Comment.query.filter(
        Comment.created_at >= week_ago,
        Comment.is_deleted == False
    ).count()
    comments_last_week = Comment.query.filter(
        Comment.created_at >= week_ago - timedelta(days=7),
        Comment.created_at < week_ago,
        Comment.is_deleted == False
    ).count()

    users_this_week = User.query.filter(User.created_at >= week_ago).count()
    users_last_week = User.query.filter(
        User.created_at >= week_ago - timedelta(days=7),
        User.created_at < week_ago
    ).count()

    weekly_comparison = {
        'videos': {'current': videos_this_week, 'previous': videos_last_week},
        'comments': {'current': comments_this_week, 'previous': comments_last_week},
        'users': {'current': users_this_week, 'previous': users_last_week},
    }

    return render_template('admin/analytics.html',
        total_videos=total_videos,
        total_users=total_users,
        total_comments=total_comments,
        total_views=total_views,
        public_videos=public_videos,
        private_videos=private_videos,
        storage_stats=storage_stats,
        top_videos=top_videos,
        recent_videos=recent_videos,
        recent_comments=recent_comments,
        recent_users=recent_users,
        encoding_stats=encoding_stats,
        chart_labels=chart_labels,
        chart_videos=chart_videos,
        chart_comments=chart_comments,
        chart_users=chart_users,
        top_uploaders=top_uploaders,
        top_commenters=top_commenters,
        role_stats=role_stats,
        weekly_comparison=weekly_comparison,
        current_period=period,
    )


@admin_bp.route('/videos')
@login_required
@admin_required
def videos():
    """List all videos for bulk management."""
    # Get filter parameters
    visibility_filter = request.args.get('visibility', 'all')
    owner_filter = request.args.get('owner', '')
    sort_by = request.args.get('sort', 'newest')

    # Base query
    query = Video.query

    # Apply filters
    if visibility_filter == 'public':
        query = query.filter(Video.visibility == VideoVisibility.PUBLIC.value)
    elif visibility_filter == 'private':
        query = query.filter(Video.visibility == VideoVisibility.PRIVATE.value)

    if owner_filter:
        query = query.filter(Video.owner_username == owner_filter)

    # Apply sorting
    if sort_by == 'oldest':
        query = query.order_by(Video.created_at.asc())
    elif sort_by == 'views':
        query = query.order_by(Video.view_count.desc())
    elif sort_by == 'title':
        query = query.order_by(Video.title.asc())
    else:  # newest (default)
        query = query.order_by(Video.created_at.desc())

    videos_list = query.all()

    # Get unique owners for filter dropdown
    owners = db.session.query(Video.owner_username).distinct().filter(
        Video.owner_username != None
    ).order_by(Video.owner_username).all()
    owners = [o[0] for o in owners]

    return render_template('admin/videos.html',
        videos=videos_list,
        owners=owners,
        current_visibility=visibility_filter,
        current_owner=owner_filter,
        current_sort=sort_by,
    )


@admin_bp.route('/videos/bulk-action', methods=['POST'])
@login_required
@admin_required
def videos_bulk_action():
    """Handle bulk actions on videos."""
    action = request.form.get('action')
    video_ids = request.form.getlist('video_ids')

    if not video_ids:
        flash('No videos selected.', 'warning')
        return redirect(url_for('admin.videos'))

    videos_folder = Path(current_app.config.get('VIDEOS_FOLDER', ''))
    thumbnails_folder = Path(current_app.config.get('THUMBNAILS_FOLDER', ''))

    if action == 'delete':
        deleted_count = 0
        for video_id in video_ids:
            video = Video.query.get(int(video_id))
            if video:
                # Delete video files
                for ext in ['.m3u8', '_master.m3u8']:
                    file_path = videos_folder / f"{video.filename}{ext}"
                    if file_path.exists():
                        file_path.unlink()

                # Delete segment files
                for ts_file in videos_folder.glob(f"{video.filename}_*.ts"):
                    ts_file.unlink()

                # Delete thumbnail
                if video.thumbnail:
                    thumb_path = thumbnails_folder / video.thumbnail
                    if thumb_path.exists():
                        thumb_path.unlink()

                # Delete preview
                if video.preview:
                    preview_path = thumbnails_folder / video.preview
                    if preview_path.exists():
                        preview_path.unlink()

                # Delete related records
                Comment.query.filter_by(video_id=video.id).delete()
                Favorite.query.filter_by(video_id=video.id).delete()
                WatchHistory.query.filter_by(video_id=video.id).delete()
                EncodingJob.query.filter_by(video_id=video.id).delete()

                # Delete from playlists
                from rtube.models import PlaylistVideo
                PlaylistVideo.query.filter_by(video_id=video.id).delete()

                db.session.delete(video)
                deleted_count += 1

        db.session.commit()
        flash(f'Successfully deleted {deleted_count} video(s).', 'success')

    elif action == 'make_public':
        updated_count = 0
        for video_id in video_ids:
            video = Video.query.get(int(video_id))
            if video and video.visibility != VideoVisibility.PUBLIC.value:
                video.visibility = VideoVisibility.PUBLIC.value
                updated_count += 1
        db.session.commit()
        flash(f'Changed {updated_count} video(s) to public.', 'success')

    elif action == 'make_private':
        updated_count = 0
        for video_id in video_ids:
            video = Video.query.get(int(video_id))
            if video and video.visibility != VideoVisibility.PRIVATE.value:
                video.visibility = VideoVisibility.PRIVATE.value
                updated_count += 1
        db.session.commit()
        flash(f'Changed {updated_count} video(s) to private.', 'success')

    else:
        flash('Unknown action.', 'error')

    return redirect(url_for('admin.videos'))
