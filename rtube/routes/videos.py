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


@videos_bp.route('/watch/<string:short_id>')
def watch_video(short_id):
    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return "Video not found", 404

    # Private videos require authentication
    if video.is_private() and not current_user.is_authenticated:
        flash("This video is private. Please log in to view it.", "warning")
        return redirect(url_for('auth.login', next=f'/watch/{short_id}'))

    video.increment_views()
    db.session.commit()

    video_path_to_load = f"videos/{video.filename}.m3u8"
    logger.info(f"Looking for [{video_path_to_load}]")
    return render_template(
        'index.html',
        filename=video.filename,
        video_path_to_load=video_path_to_load,
        markers=None,
        view_count=video.view_count,
        description=video.description,
        video=video,
    )


@videos_bp.route('/watch/<string:short_id>/comment', methods=['POST'])
@login_required
def post_comment(short_id):
    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return "Video not found", 404

    # Private videos require authentication
    if video.is_private() and not current_user.is_authenticated:
        return "Video not found", 404

    content = request.form.get('content', '').strip()[:5000]
    if not content:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for('videos.watch_video', short_id=short_id))

    comment = Comment(
        video_id=video.id,
        author_username=current_user.username,
        content=content
    )
    db.session.add(comment)
    db.session.commit()

    flash("Comment posted successfully.", "success")
    return redirect(url_for('videos.watch_video', short_id=short_id))
