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
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

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
    started_by_username = db.Column(db.String(80), nullable=True)  # Username who started the encoding

    video = db.relationship("Video", backref=db.backref("encoding_jobs", lazy=True))


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    author_username = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_by = db.Column(db.String(20), nullable=True)  # 'owner' or 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    video = db.relationship("Video", backref=db.backref("comments", lazy=True, order_by="Comment.created_at.desc()"))
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]), lazy=True, order_by="Comment.created_at.asc()")

    def is_reply(self) -> bool:
        """Check if this comment is a reply to another comment."""
        return self.parent_id is not None

    def get_reply_count(self) -> int:
        """Get the number of replies to this comment (excluding deleted)."""
        return sum(1 for r in self.replies if not r.is_deleted)

    def get_all_replies_count(self) -> int:
        """Get total replies including deleted (for display purposes)."""
        return len(self.replies)

    def deleted_by_admin(self) -> bool:
        """Check if comment was deleted by an admin."""
        return self.is_deleted and self.deleted_by == 'admin'

    def deleted_by_owner(self) -> bool:
        """Check if comment was deleted by the owner."""
        return self.is_deleted and self.deleted_by == 'owner'


class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    video = db.relationship("Video", backref=db.backref("favorites", lazy=True))

    __table_args__ = (
        db.UniqueConstraint('username', 'video_id', name='unique_user_video_favorite'),
    )


class Playlist(db.Model):
    __tablename__ = "playlists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(5000), nullable=True)
    owner_username = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    videos = db.relationship(
        "PlaylistVideo",
        backref="playlist",
        lazy=True,
        order_by="PlaylistVideo.position",
        cascade="all, delete-orphan"
    )

    def video_count(self) -> int:
        return len(self.videos)


class PlaylistVideo(db.Model):
    __tablename__ = "playlist_videos"

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlists.id"), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    video = db.relationship("Video", backref=db.backref("playlist_entries", lazy=True))

    __table_args__ = (
        db.UniqueConstraint('playlist_id', 'video_id', name='unique_playlist_video'),
    )


class WatchHistory(db.Model):
    """Track user watch history with playback position for resume functionality."""
    __tablename__ = "watch_history"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False)
    position = db.Column(db.Float, default=0.0, nullable=False)  # Playback position in seconds
    duration = db.Column(db.Float, nullable=True)  # Video duration in seconds
    watched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    video = db.relationship("Video", backref=db.backref("watch_history", lazy=True))

    __table_args__ = (
        db.UniqueConstraint('username', 'video_id', name='unique_user_video_history'),
    )

    def progress_percent(self) -> int:
        """Return watch progress as percentage (0-100)."""
        if not self.duration or self.duration == 0:
            return 0
        return min(100, int((self.position / self.duration) * 100))

    def is_completed(self, threshold: float = 0.9) -> bool:
        """Check if video is considered watched (default: 90% progress)."""
        if not self.duration or self.duration == 0:
            return False
        return (self.position / self.duration) >= threshold
