import logging
from pathlib import Path
from flask import Blueprint, render_template, current_app, flash, redirect, url_for, request, abort, send_from_directory
from flask_login import current_user, login_required

from rtube.models import db, Video, VideoVisibility, Comment, EncodingJob, Favorite, PlaylistVideo

logger = logging.getLogger(__name__)

videos_bp = Blueprint('videos', __name__)


@videos_bp.route('/media/videos/<path:filename>')
def serve_video(filename):
    """Serve video files from the instance/videos folder."""
    return send_from_directory(current_app.config["VIDEOS_FOLDER"], filename)


@videos_bp.route('/media/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    """Serve thumbnail files from the instance/thumbnails folder."""
    return send_from_directory(current_app.config["THUMBNAILS_FOLDER"], filename)


def get_available_videos(include_private: bool = False):
    """Liste les vidéos disponibles dans le dossier instance/videos."""
    videos_path = Path(current_app.config["VIDEOS_FOLDER"])
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

    # Handle search
    query = request.args.get('q', '').strip()
    if query:
        return search_videos(query, include_private)

    return render_template('videos.html', videos=videos)


def search_videos(query: str, include_private: bool = False):
    """Search videos by title, description, or author."""
    query_lower = query.lower()

    # Build base query for videos
    base_query = Video.query
    if not include_private:
        base_query = base_query.filter(Video.visibility != 'private')

    # Search by title
    by_title = base_query.filter(
        db.func.lower(Video.title).contains(query_lower)
    ).order_by(Video.created_at.desc()).all()

    # Search by description
    by_description = base_query.filter(
        db.func.lower(Video.description).contains(query_lower)
    ).order_by(Video.created_at.desc()).all()

    # Search by author
    by_author = base_query.filter(
        db.func.lower(Video.owner_username).contains(query_lower)
    ).order_by(Video.created_at.desc()).all()

    # Remove duplicates while preserving categories
    seen_ids = set()
    results_by_title = []
    for video in by_title:
        if video.id not in seen_ids:
            results_by_title.append(video)
            seen_ids.add(video.id)

    results_by_description = []
    for video in by_description:
        if video.id not in seen_ids:
            results_by_description.append(video)
            seen_ids.add(video.id)

    results_by_author = []
    for video in by_author:
        if video.id not in seen_ids:
            results_by_author.append(video)
            seen_ids.add(video.id)

    total_results = len(results_by_title) + len(results_by_description) + len(results_by_author)

    return render_template(
        'videos.html',
        videos=None,
        search_query=query,
        results_by_title=results_by_title,
        results_by_description=results_by_description,
        results_by_author=results_by_author,
        total_results=total_results
    )


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

    # Check if video is in user's favorites
    is_favorite = False
    if current_user.is_authenticated:
        is_favorite = Favorite.query.filter_by(
            username=current_user.username,
            video_id=video.id
        ).first() is not None

    video_url = url_for('videos.serve_video', filename=f"{video.filename}.m3u8")
    logger.info(f"Loading video from [{video_url}]")
    return render_template(
        'index.html',
        filename=video.title or video.filename,
        video_url=video_url,
        markers=None,
        view_count=video.view_count,
        description=video.description,
        video=video,
        start_time=start_time,
        is_favorite=is_favorite,
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


@videos_bp.route('/watch/delete', methods=['POST'])
@login_required
def delete_video():
    """Delete a video (owner or admin only)."""
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template(
            '404.html',
            title="Video not found",
            message="No video ID was provided."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    # Check permissions: owner can delete their own videos, admin can delete any
    is_owner = video.owner_username == current_user.username
    is_admin = current_user.is_admin()

    if not is_owner and not is_admin:
        abort(403)

    video_title = video.title or video.filename
    video_filename = video.filename

    # Delete associated comments
    Comment.query.filter_by(video_id=video.id).delete()

    # Delete associated favorites
    Favorite.query.filter_by(video_id=video.id).delete()

    # Delete associated playlist entries
    PlaylistVideo.query.filter_by(video_id=video.id).delete()

    # Delete associated encoding jobs
    EncodingJob.query.filter_by(video_id=video.id).delete()

    # Delete video files from disk
    videos_path = Path(current_app.config["VIDEOS_FOLDER"])
    if videos_path.exists():
        # Delete main m3u8 file
        main_m3u8 = videos_path / f"{video_filename}.m3u8"
        if main_m3u8.exists():
            main_m3u8.unlink()
            logger.info(f"Deleted file: {main_m3u8}")

        # Delete quality-specific files (e.g., video_720p.m3u8, video_720p_001.ts)
        for quality_file in videos_path.glob(f"{video_filename}_*"):
            quality_file.unlink()
            logger.info(f"Deleted file: {quality_file}")

        # Delete thumbnail if exists
        if video.thumbnail:
            thumbnail_path = Path(current_app.config["THUMBNAILS_FOLDER"]) / video.thumbnail
            if thumbnail_path.exists():
                thumbnail_path.unlink()
                logger.info(f"Deleted thumbnail: {thumbnail_path}")

    # Delete video record from database
    db.session.delete(video)
    db.session.commit()

    logger.info(f"Admin '{current_user.username}' deleted video '{video_title}' (ID: {short_id})")
    flash(f"Video '{video_title}' has been deleted.", "success")
    return redirect(url_for('videos.index'))


@videos_bp.route('/watch/favorite', methods=['POST'])
@login_required
def add_favorite():
    """Add a video to user's favorites."""
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template(
            '404.html',
            title="Video not found",
            message="No video ID was provided."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    # Check if already in favorites
    existing = Favorite.query.filter_by(
        username=current_user.username,
        video_id=video.id
    ).first()

    if not existing:
        favorite = Favorite(
            username=current_user.username,
            video_id=video.id
        )
        db.session.add(favorite)
        db.session.commit()
        flash("Video added to favorites.", "success")
    else:
        flash("Video is already in your favorites.", "info")

    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/unfavorite', methods=['POST'])
@login_required
def remove_favorite():
    """Remove a video from user's favorites."""
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template(
            '404.html',
            title="Video not found",
            message="No video ID was provided."
        ), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template(
            '404.html',
            title="Video not found",
            message=f"The video with ID '{short_id}' doesn't exist or has been removed."
        ), 404

    favorite = Favorite.query.filter_by(
        username=current_user.username,
        video_id=video.id
    ).first()

    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        flash("Video removed from favorites.", "success")
    else:
        flash("Video was not in your favorites.", "info")

    return redirect(url_for('videos.watch_video', v=short_id))
