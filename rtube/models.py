import secrets
import string
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_short_id(length: int = 8) -> str:
    """Generate a random alphanumeric short ID."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(10), nullable=True)  # ISO 639-1 code (e.g., "en", "fr")
    thumbnail = db.Column(db.String(255), nullable=True)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    def __init__(self, **kwargs):
        if 'short_id' not in kwargs:
            kwargs['short_id'] = generate_short_id()
        super().__init__(**kwargs)

    def increment_views(self):
        self.view_count += 1


class EncodingJob(db.Model):
    __tablename__ = "encoding_jobs"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)  # pending, encoding, completed, failed
    progress = db.Column(db.Integer, default=0, nullable=False)
    qualities = db.Column(db.String(255), nullable=False)  # comma-separated: "144p,360p,720p"
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    video = db.relationship("Video", backref=db.backref("encoding_jobs", lazy=True))
