import logging
from pathlib import Path
from flask import Blueprint, render_template, current_app, flash, redirect, url_for, request, abort, send_from_directory
from flask_login import current_user, login_required

from datetime import datetime, timedelta
from rtube.models import db, Video, VideoVisibility, Comment, EncodingJob, Favorite, PlaylistVideo, WatchHistory, VideoChapter
from rtube.models_auth import User, UserRole

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
                "preview": video.preview,
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


def get_recommended_videos(current_video: Video, limit: int = 10, include_private: bool = False) -> list:
    """Get recommended videos based on the current video.

    Scoring criteria:
    - Same author: +3 points
    - Same language: +2 points
    - Popular videos: +1 point per 100 views (max +3)
    - Recent videos (within 30 days): +1 point
    """
    # Base query - exclude current video
    query = Video.query.filter(Video.id != current_video.id)

    # Filter visibility
    if not include_private:
        query = query.filter(Video.visibility == VideoVisibility.PUBLIC.value)

    candidates = query.all()

    # Score each video
    scored = []
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    for video in candidates:
        score = 0

        # Same author (+3)
        if video.owner_username and video.owner_username == current_video.owner_username:
            score += 3

        # Same language (+2)
        if video.language and video.language == current_video.language:
            score += 2

        # Popular videos (+1 per 100 views, max +3)
        score += min(video.view_count // 100, 3)

        # Recent videos (+1)
        if video.created_at and video.created_at >= thirty_days_ago:
            score += 1

        scored.append((score, video))

    # Sort by score (desc), then by view_count (desc)
    scored.sort(key=lambda x: (x[0], x[1].view_count), reverse=True)

    return [video for score, video in scored[:limit]]


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

    # Get recommended videos (include private only if user is authenticated)
    recommended_videos = get_recommended_videos(
        video,
        limit=10,
        include_private=current_user.is_authenticated
    )

    # Comment sorting
    sort_order = request.args.get('sort', 'newest')
    if sort_order not in ('newest', 'oldest'):
        sort_order = 'newest'

    # Build videojs-markers structure if chapters exist
    markers_data = []
    if video.chapters:
        for chapter in video.chapters:
            markers_data.append({
                "time": chapter.start_time,
                "text": chapter.title,
                "class": "blue-marker"
            })

    video_url = url_for('videos.serve_video', filename=f"{video.filename}.m3u8")
    logger.info(f"Loading video from [{video_url}]")
    return render_template(
        'index.html',
        filename=video.title or video.filename,
        video_url=video_url,
        markers=markers_data,
        view_count=video.view_count,
        description=video.description,
        video=video,
        start_time=start_time,
        is_favorite=is_favorite,
        recommended_videos=recommended_videos,
        current_sort=sort_order,
    )


@videos_bp.route('/watch/vtt/<short_id>.vtt')
def chapters_vtt(short_id):
    """Dynamically generate a WebVTT file for video chapters."""
    from flask import Response
    
    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video or not video.chapters:
        return Response("WEBVTT\n\n", mimetype='text/vtt')

    # Private videos require authentication
    if video.is_private() and not current_user.is_authenticated:
        return Response("WEBVTT\n\n", mimetype='text/vtt')

    lines = ["WEBVTT", ""]
    
    chapters = video.chapters
    num_chapters = len(chapters)
    
    for i in range(num_chapters):
        current_chapter = chapters[i]
        
        # Calculate current chapter's start string
        start_ms = current_chapter.start_time * 1000
        start_hours, rem = divmod(start_ms, 3600000)
        start_mins, rem = divmod(rem, 60000)
        start_secs, start_msecs = divmod(rem, 1000)
        start_str = f"{start_hours:02d}:{start_mins:02d}:{start_secs:02d}.{start_msecs:03d}"
        
        # Determine current chapter's end timestamp
        if i + 1 < num_chapters:
            next_chapter = chapters[i + 1]
            end_ms = int(next_chapter.start_time * 1000)
        elif video.watch_history and video.watch_history[0].duration:
            # Use duration if available
            end_ms = int(video.watch_history[0].duration * 1000)
        else:
            # Arbitrarily large end time for the final chapter if duration is unknown
            end_ms = 86399999 # 23:59:59.999
            
        end_hours, rem = divmod(end_ms, 3600000)
        end_mins, rem = divmod(rem, 60000)
        end_secs, end_msecs = divmod(rem, 1000)
        end_str = f"{int(end_hours):02d}:{int(end_mins):02d}:{int(end_secs):02d}.{int(end_msecs):03d}"
        
        lines.append(f"{start_str} --> {end_str}")
        lines.append(current_chapter.title)
        lines.append("")

    response = Response("\n".join(lines), mimetype='text/vtt')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


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

    # Handle reply to parent comment
    parent_id = request.form.get('parent_id', type=int)
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.video_id != video.id:
            flash("Invalid parent comment.", "error")
            return redirect(url_for('videos.watch_video', v=short_id))

    comment = Comment(
        video_id=video.id,
        author_username=current_user.username,
        content=content,
        parent_id=parent_id
    )
    db.session.add(comment)
    db.session.commit()

    flash("Reply posted successfully." if parent_id else "Comment posted successfully.", "success")
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

    # Soft delete: mark as deleted instead of removing
    comment.is_deleted = True
    # Track who deleted it: admin takes precedence if both owner and admin
    comment.deleted_by = 'admin' if is_admin and not is_owner else 'owner'
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


def parse_time_to_seconds(time_str: str) -> int:
    """Parse 'MM:SS' or 'HH:MM:SS' to seconds."""
    parts = time_str.strip().split(':')
    try:
        if len(parts) == 2:
            m, s = map(int, parts)
            return m * 60 + s
        elif len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        else:
            return int(time_str)
    except ValueError:
        raise ValueError("Invalid time format. Use seconds or MM:SS or HH:MM:SS.")


@videos_bp.route('/watch/chapter/add', methods=['POST'])
@login_required
def add_chapter():
    short_id = request.args.get('v', '')
    if not short_id:
        return render_template('404.html', title="Video not found", message="No video ID provided."), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template('404.html', title="Video not found", message="Video not found."), 404

    is_owner = video.owner_username == current_user.username
    is_admin = current_user.is_admin()
    if not is_owner and not is_admin:
        abort(403)

    title = request.form.get('title', '').strip()[:255]
    time_str = request.form.get('time', '').strip()

    if not title or not time_str:
        flash("Title and time are required.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    try:
        start_time = parse_time_to_seconds(time_str)
        if start_time < 0:
            raise ValueError()
    except ValueError:
        flash("Invalid time format. Use seconds, MM:SS, or HH:MM:SS.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    chapter = VideoChapter(video_id=video.id, title=title, start_time=start_time)
    db.session.add(chapter)
    db.session.commit()
    flash("Chapter added successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/chapter/edit', methods=['POST'])
@login_required
def edit_chapter():
    short_id = request.args.get('v', '')
    chapter_id = request.form.get('chapter_id', type=int)

    if not short_id or not chapter_id:
        return render_template('404.html', title="Invalid request", message="Missing video ID or chapter ID."), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template('404.html', title="Video not found", message="Video not found."), 404

    is_owner = video.owner_username == current_user.username
    is_admin = current_user.is_admin()
    if not is_owner and not is_admin:
        abort(403)

    chapter = VideoChapter.query.filter_by(id=chapter_id, video_id=video.id).first()
    if not chapter:
        return render_template('404.html', title="Chapter not found", message="Chapter doesn't exist."), 404

    title = request.form.get('title', '').strip()[:255]
    time_str = request.form.get('time', '').strip()

    if not title or not time_str:
        flash("Title and time are required.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    try:
        start_time = parse_time_to_seconds(time_str)
        if start_time < 0:
            raise ValueError()
    except ValueError:
        flash("Invalid time format. Use seconds, MM:SS, or HH:MM:SS.", "error")
        return redirect(url_for('videos.watch_video', v=short_id))

    chapter.title = title
    chapter.start_time = start_time
    db.session.commit()
    flash("Chapter updated successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/chapter/delete', methods=['POST'])
@login_required
def delete_chapter():
    short_id = request.args.get('v', '')
    chapter_id = request.form.get('chapter_id', type=int)

    if not short_id or not chapter_id:
        return render_template('404.html', title="Invalid request", message="Missing video ID or chapter ID."), 404

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return render_template('404.html', title="Video not found", message="Video not found."), 404

    is_owner = video.owner_username == current_user.username
    is_admin = current_user.is_admin()
    if not is_owner and not is_admin:
        abort(403)

    chapter = VideoChapter.query.filter_by(id=chapter_id, video_id=video.id).first()
    if not chapter:
        return render_template('404.html', title="Chapter not found", message="Chapter doesn't exist."), 404

    db.session.delete(chapter)
    db.session.commit()
    flash("Chapter deleted successfully.", "success")
    return redirect(url_for('videos.watch_video', v=short_id))


@videos_bp.route('/watch/edit', methods=['GET', 'POST'])
@login_required
def edit_video():
    """Edit a video (owner or admin only)."""
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

    # Check permissions: owner can edit their own videos, admin can edit any
    is_owner = video.owner_username == current_user.username
    is_admin = current_user.is_admin()

    if not is_owner and not is_admin:
        abort(403)

    # Get list of eligible owners for admin (users who can upload: UPLOADER or ADMIN)
    eligible_owners = []
    if is_admin:
        eligible_owners = User.query.filter(
            User.role.in_([UserRole.UPLOADER.value, UserRole.ADMIN.value])
        ).order_by(User.username).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:255] or None
        description = request.form.get('description', '').strip() or None
        language = request.form.get('language', '').strip()[:10] or None
        visibility = request.form.get('visibility', VideoVisibility.PUBLIC.value)

        if visibility not in [VideoVisibility.PUBLIC.value, VideoVisibility.PRIVATE.value]:
            visibility = VideoVisibility.PUBLIC.value

        video.title = title
        video.description = description
        video.language = language
        video.visibility = visibility

        # Admin can change the owner
        if is_admin:
            new_owner = request.form.get('owner_username', '').strip()
            if new_owner:
                # Validate the new owner exists and can upload
                new_owner_user = User.query.filter_by(username=new_owner).first()
                if new_owner_user and new_owner_user.can_upload():
                    if video.owner_username != new_owner:
                        logger.info(f"Admin '{current_user.username}' changed owner of video '{video.short_id}' from '{video.owner_username}' to '{new_owner}'")
                        video.owner_username = new_owner

        db.session.commit()

        flash("Video updated successfully.", "success")
        return redirect(url_for('videos.watch_video', v=short_id))

    return render_template('videos/edit.html', video=video, is_admin=is_admin, eligible_owners=eligible_owners)


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

    # Delete associated chapters
    VideoChapter.query.filter_by(video_id=video.id).delete()

    # Delete associated comments
    Comment.query.filter_by(video_id=video.id).delete()

    # Delete associated favorites
    Favorite.query.filter_by(video_id=video.id).delete()

    # Delete associated playlist entries
    PlaylistVideo.query.filter_by(video_id=video.id).delete()

    # Delete associated encoding jobs
    EncodingJob.query.filter_by(video_id=video.id).delete()

    # Delete associated watch history
    WatchHistory.query.filter_by(video_id=video.id).delete()

    # Delete associated video views
    # Import kept inside function to avoid circular imports if any, or just for safety
    from rtube.models import VideoView
    VideoView.query.filter_by(video_id=video.id).delete()

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


@videos_bp.route('/watch/progress', methods=['POST'])
@login_required
def save_watch_progress():
    """Save watch progress for resume functionality (AJAX endpoint)."""
    from flask import jsonify

    short_id = request.args.get('v', '')
    if not short_id:
        return jsonify({"error": "No video ID provided"}), 400

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    try:
        data = request.get_json()
        position = float(data.get('position', 0))
        duration = float(data.get('duration', 0)) if data.get('duration') else None
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid position or duration"}), 400

    # Find or create watch history entry
    history = WatchHistory.query.filter_by(
        username=current_user.username,
        video_id=video.id
    ).first()

    if history:
        history.position = position
        history.duration = duration
        history.watched_at = datetime.utcnow()
    else:
        history = WatchHistory(
            username=current_user.username,
            video_id=video.id,
            position=position,
            duration=duration
        )
        db.session.add(history)

    db.session.commit()
    return jsonify({"success": True, "position": position})


@videos_bp.route('/watch/progress', methods=['GET'])
@login_required
def get_watch_progress():
    """Get watch progress for resume functionality (AJAX endpoint)."""
    from flask import jsonify

    short_id = request.args.get('v', '')
    if not short_id:
        return jsonify({"error": "No video ID provided"}), 400

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    history = WatchHistory.query.filter_by(
        username=current_user.username,
        video_id=video.id
    ).first()

    if history:
        return jsonify({
            "position": history.position,
            "duration": history.duration,
            "progress_percent": history.progress_percent()
        })

    return jsonify({"position": 0, "duration": None, "progress_percent": 0})


@videos_bp.route('/history')
@login_required
def watch_history():
    """Display user's watch history."""
    history_entries = WatchHistory.query.filter_by(
        username=current_user.username
    ).order_by(WatchHistory.watched_at.desc()).all()

    # Build history data with video info
    history_data = []
    for entry in history_entries:
        video = db.session.get(Video, entry.video_id)
        if video:  # Video might have been deleted
            history_data.append({
                'entry': entry,
                'video': video
            })

    return render_template('videos/history.html', history_data=history_data)


@videos_bp.route('/history/clear', methods=['POST'])
@login_required
def clear_watch_history():
    """Clear user's entire watch history."""
    WatchHistory.query.filter_by(username=current_user.username).delete()
    db.session.commit()
    flash("Watch history cleared.", "success")
    return redirect(url_for('videos.watch_history'))


@videos_bp.route('/history/remove', methods=['POST'])
@login_required
def remove_from_history():
    """Remove a single video from watch history."""
    short_id = request.form.get('video_id', '')
    if not short_id:
        flash("No video specified.", "error")
        return redirect(url_for('videos.watch_history'))

    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if video:
        WatchHistory.query.filter_by(
            username=current_user.username,
            video_id=video.id
        ).delete()
        db.session.commit()
        flash("Video removed from history.", "success")

    return redirect(url_for('videos.watch_history'))
