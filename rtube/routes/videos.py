import logging
from pathlib import Path
from flask import Blueprint, render_template, current_app

from rtube.models import db, Video

logger = logging.getLogger(__name__)

videos_bp = Blueprint('videos', __name__)


def get_available_videos():
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
            videos.append({
                "short_id": video.short_id,
                "filename": filename,
                "title": video.title or filename,
                "description": video.description,
                "language": video.language,
                "view_count": video.view_count,
                "thumbnail": video.thumbnail
            })

    return videos


@videos_bp.route('/')
def index():
    videos = get_available_videos()
    return render_template('videos.html', videos=videos)


@videos_bp.route('/watch/<string:short_id>')
def watch_video(short_id):
    video = Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first()
    if not video:
        return "Video not found", 404

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
    )
