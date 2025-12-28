import secrets
import string
from enum import Enum
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class VideoVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"


def generate_unique_short_id(length: int = 16, max_attempts: int = 10) -> str:
    """Generate a unique random alphanumeric short ID."""
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(max_attempts):
        short_id = ''.join(secrets.choice(alphabet) for _ in range(length))
        if not Video.query.filter(db.func.lower(Video.short_id) == short_id.lower()).first():
            return short_id
    raise ValueError("Failed to generate unique short_id after maximum attempts")


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(10), nullable=True)  # ISO 639-1 code (e.g., "en", "fr")
    visibility = db.Column(db.String(20), nullable=False, default=VideoVisibility.PUBLIC.value)
    thumbnail = db.Column(db.String(255), nullable=True)
    view_count = db.Column(db.Integer, default=0, nullable=False)
    owner_username = db.Column(db.String(80), nullable=True)  # Username of the uploader

    def is_public(self) -> bool:
        return self.visibility == VideoVisibility.PUBLIC.value

    def is_private(self) -> bool:
        return self.visibility == VideoVisibility.PRIVATE.value

    def __init__(self, **kwargs):
        if 'short_id' not in kwargs:
            kwargs['short_id'] = generate_unique_short_id()
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


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    author_username = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    video = db.relationship("Video", backref=db.backref("comments", lazy=True, order_by="Comment.created_at.desc()"))
