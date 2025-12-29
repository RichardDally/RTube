import logging
from pathlib import Path
from flask import Blueprint, render_template, current_app, flash, redirect, url_for, request
from flask_login import current_user, login_required

from rtube.models import db, Video, VideoVisibility, Comment

logger = logging.getLogger(__name__)

videos_bp = Blueprint('videos', __name__)


def get_available_videos(include_private: bool = False):
    """Liste les vidéos disponibles dans le dossier static/videos."""
    videos_path = Path(current_app.static_folder) / "videos"
    if not videos_path.exists():
        return []

    available_filenames = []
    for f in videos_path.glob("*.m3u8"):
        name = f.stem
        if not any(res in name for res in ["_144p", "_240p", "_360p", "_480p", "_720p", "_1080p", "_1440p", "_2160p"]):
            available_filenames.append(name)

    # Get video records from database, matching available files
    videos = []
    for filename in sorted(available_filenames):
        video = Video.query.filter_by(filename=filename).first()
        if video:
            # Skip private videos if user is not authenticated
            if video.is_private() and not include_private:
                continue
            videos.append({
                "short_id": video.short_id,
                "filename": filename,
                "title": video.title or filename,
                "description": video.description,
                "language": video.language,
                "visibility": video.visibility,
                "view_count": video.view_count,
                "thumbnail": video.thumbnail,
                "owner_username": video.owner_username
            })

    return videos


@videos_bp.route('/')
def index():
    # Show private videos only to authenticated users
    include_private = current_user.is_authenticated
    videos = get_available_videos(include_private=include_private)
    return render_template('videos.html', videos=videos)


@videos_bp.route('/watch/<path:invalid_path>')
def watch_video_invalid_url(invalid_path):
    """Handle malformed URLs like /watch/VIDEO_ID instead of /watch?v=VIDEO_ID"""
    # Check if the invalid_path looks like a video ID (redirect to correct URL)
    potential_id = invalid_path.split('/')[0]  # Get first segment
    video = Video.query.filter(db.func.lower(Video.short_id) == potential_id.lower()).first()

    if video:
        # Video exists, redirect to correct URL format
        return redirect(url_for('videos.watch_video', v=video.short_id))

    # Video doesn't exist, show helpful error
    return render_template(
        '404.html',
        title="Invalid URL format",
        message=f"The URL format '/watch/{potential_id}' is incorrect. Use '/watch?v={potential_id}' instead."
    ), 404


@videos_bp.route('/watch')
def watch_video():
    # YouTube-style URL: /watch?v=SHORT_ID&t=90
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template(
            '404.html',
            title="Video not found",
            message="No video ID was provided in the URL. Please check the link and try again."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    # Private videos require authentication
    if video.is_private() and not current_user.is_authenticated:
        flash("This video is private. Please log in to view it.", "warning")
        return redirect(url_for('auth.login', next=f'/watch?v={short_id}'))

    video.increment_views()
    db.session.commit()

    # Get time offset from query parameter (e.g., &t=90 for 90 seconds)
    start_time = request.args.get('t', 0, type=int)
    if start_time < 0:
        start_time = 0

    video_path_to_load = f"videos/{video.filename}.m3u8"
    logger.info(f"Looking for [{video_path_to_load}]")
    return render_template(
        'index.html',
        filename=video.title or video.filename,
        video_path_to_load=video_path_to_load,
        markers=None,
        view_count=video.view_count,
        description=video.description,
        video=video,
        start_time=start_time,
    )


@videos_bp.route('/watch/comment', methods=['POST'])
@login_required
def post_comment():
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template(
            '404.html',
            title="Video not found",
            message="No video ID was provided. Cannot post comment."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    # Private videos require authentication
    if video.is_private() and not current_user.is_authenticated:
        return render_template(
            '404.html',
            title="Video not found",
            message="This video is not accessible."
        ), 404

    content = request.form.get('content', '').strip()[:5000]
    if not content:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    comment = Comment(
        video_id=video.id,
        author_username=current_user.username,
        content=content
    )
    db.session.add(comment)
    db.session.commit()

    flash("Comment posted successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/comment/delete', methods=['POST'])
@login_required
def delete_comment():
    short_id = request.args.get('v', '')
    comment_id = request.form.get('comment_id', type=int)

    if not short_id or not comment_id:
        return render_template(
            '404.html',
            title="Invalid request",
            message="Missing video ID or comment ID."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    comment = Comment.query.filter_by(id=comment_id, video_id=video.id).first()
    if not comment:
        return render_template(
            '404.html',
            title="Comment not found",
            message="The comment doesn't exist or has already been deleted."
        ), 404

    # Check permissions: owner can delete their own comments, admin can delete any
    is_owner = comment.author_username == current_user.username
    is_admin = current_user.is_admin()

    if not is_owner and not is_admin:
        flash("You don't have permission to delete this comment.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    db.session.delete(comment)
    db.session.commit()

    flash("Comment deleted successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/comment/edit', methods=['POST'])
@login_required
def edit_comment():
    short_id = request.args.get('v', '')
    comment_id = request.form.get('comment_id', type=int)

    if not short_id or not comment_id:
        return render_template(
            '404.html',
            title="Invalid request",
            message="Missing video ID or comment ID."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    comment = Comment.query.filter_by(id=comment_id, video_id=video.id).first()
    if not comment:
        return render_template(
            '404.html',
            title="Comment not found",
            message="The comment doesn't exist or has already been deleted."
        ), 404

    # Only the owner can edit their own comment
    if comment.author_username != current_user.username:
        flash("You can only edit your own comments.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    content = request.form.get('content', '').strip()[:5000]
    if not content:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    comment.content = content
    db.session.commit()

    flash("Comment updated successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))
