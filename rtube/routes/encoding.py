import json
import logging
from functools import wraps
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, current_app, Response, abort
from flask_login import login_required, current_user

from rtube.models import db, Video, EncodingJob
from rtube.services.encoder import encoder_service

logger = logging.getLogger(__name__)

encoding_bp = Blueprint('encoding', __name__, url_prefix='/encode')

ALLOWED_EXTENSIONS = {'mp4', 'mkv'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def uploader_required(f):
    """Decorator to require uploader or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_upload():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@encoding_bp.route('/', methods=['GET'])
@login_required
@uploader_required
def upload_form():
    return render_template('encoding/upload.html')


@encoding_bp.route('/', methods=['POST'])
@login_required
@uploader_required
def upload_video():
    if 'video' not in request.files:
        return render_template('encoding/upload.html', error="No file selected")

    file = request.files['video']
    if file.filename == '':
        return render_template('encoding/upload.html', error="No file selected")

    if not allowed_file(file.filename):
        return render_template('encoding/upload.html', error="Only MP4 and MKV files are accepted")

    title = request.form.get('title', '').strip()
    if not title:
        return render_template('encoding/upload.html', error="Title is required")

    description = request.form.get('description', '').strip()[:5000] or None
    language = request.form.get('language', '').strip() or None
    visibility = request.form.get('visibility', 'public')
    if visibility not in ('public', 'private'):
        visibility = 'public'
    qualities = request.form.getlist('qualities')
    if not qualities:
        return render_template('encoding/upload.html', error="Select at least one quality")

    # Create video record first to get unique short_id
    video = Video(title=title, description=description, language=language, visibility=visibility, filename="temp", owner_username=current_user.username)
    db.session.add(video)
    db.session.flush()  # Get the short_id without committing

    # Use short_id as filename base to ensure uniqueness
    filename_base = video.short_id
    video.filename = filename_base
    video.thumbnail = f"{filename_base}.jpg"
    video.preview = f"{filename_base}_preview.webm"

    # Save uploaded file to instance folder
    videos_folder = Path(current_app.config["VIDEOS_FOLDER"])
    input_path = videos_folder / f"{filename_base}.mp4"
    file.save(input_path)

    db.session.commit()

    # Create encoding job
    job = EncodingJob(
        video_id=video.id,
        qualities=",".join(qualities),
        status="pending",
        started_by_username=current_user.username
    )
    db.session.add(job)
    db.session.commit()

    # Start encoding
    output_path = videos_folder / f"{filename_base}.m3u8"
    thumbnail_path = Path(current_app.config["THUMBNAILS_FOLDER"]) / video.thumbnail
    preview_path = Path(current_app.config["THUMBNAILS_FOLDER"]) / video.preview
    keep_original = current_app.config.get("KEEP_ORIGINAL_VIDEO", False)
    encoder_service.encode_video(job.id, input_path, output_path, qualities, delete_original=not keep_original, thumbnail_path=thumbnail_path, preview_path=preview_path)

    return redirect(url_for('encoding.encoding_status', job_id=job.id))


@encoding_bp.route('/status/')
def encoding_jobs_list():
    jobs = EncodingJob.query.order_by(EncodingJob.created_at.desc()).all()
    return render_template('encoding/jobs.html', jobs=jobs)


@encoding_bp.route('/status/<int:job_id>')
def encoding_status(job_id: int):
    job = db.session.get(EncodingJob, job_id)
    if not job:
        return "Job not found", 404
    return render_template('encoding/status.html', job=job)


@encoding_bp.route('/progress/<int:job_id>')
def encoding_progress(job_id: int):
    """Server-Sent Events endpoint for real-time progress updates."""
    def generate():
        import time
        while True:
            progress_data = encoder_service.get_progress(job_id)
            yield f"data: {json.dumps(progress_data)}\n\n"

            if progress_data.get("status") in ("completed", "failed"):
                break

            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')
