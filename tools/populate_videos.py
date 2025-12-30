#!/usr/bin/env python
"""
Tool to populate the database with fake videos for testing purposes.
This creates video records in the database AND placeholder .m3u8 files
so they appear on the main page.

Usage:
    python tools/populate_videos.py [OPTIONS]
    python tools/populate_videos.py --help
"""
import random
import sys
from pathlib import Path
from typing import Annotated

import typer

# Add parent directory to path to import rtube
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import current_app
from rtube.app import create_app
from rtube.models import db, Video, VideoVisibility, Comment
from rtube.models_auth import User, UserRole

app = typer.Typer(help="Populate database with fake videos for testing.")

# Sample data for generating realistic fake videos
TITLES = [
    "Introduction to {topic}",
    "Advanced {topic} Tutorial",
    "{topic} for Beginners",
    "Mastering {topic}",
    "Learn {topic} in 10 Minutes",
    "{topic} Deep Dive",
    "The Ultimate {topic} Guide",
    "{topic} Tips and Tricks",
    "Understanding {topic}",
    "{topic} Explained",
    "How to {action} with {topic}",
    "{topic} Best Practices",
    "Getting Started with {topic}",
    "{topic} Crash Course",
    "Professional {topic} Techniques",
]

TOPICS = [
    "Python", "JavaScript", "React", "Docker", "Kubernetes", "AWS",
    "Machine Learning", "Data Science", "Web Development", "API Design",
    "Database Design", "Git", "Linux", "DevOps", "Cybersecurity",
    "Cloud Computing", "Microservices", "GraphQL", "REST APIs", "Testing",
    "CI/CD", "Agile", "TypeScript", "Node.js", "Flask", "Django",
    "Vue.js", "Angular", "MongoDB", "PostgreSQL", "Redis", "Elasticsearch",
    "Terraform", "Ansible", "Jenkins", "GitHub Actions", "Neural Networks",
    "Deep Learning", "Computer Vision", "NLP", "Blockchain", "Rust",
    "Go", "Java", "C++", "Swift", "Kotlin", "SQL", "NoSQL", "WebSockets",
]

ACTIONS = [
    "Build", "Deploy", "Scale", "Optimize", "Debug", "Test",
    "Automate", "Monitor", "Secure", "Configure", "Integrate",
]

DESCRIPTIONS = [
    "In this comprehensive tutorial, we explore {topic} from the ground up. "
    "Perfect for developers of all skill levels who want to enhance their knowledge.",

    "A detailed walkthrough of {topic} concepts and practical applications. "
    "This video covers everything you need to know to get started.",

    "Join us as we dive deep into {topic}. We'll cover advanced techniques "
    "and real-world examples that you can apply immediately.",

    "This beginner-friendly guide to {topic} will help you understand "
    "the fundamentals and build a solid foundation for future learning.",

    "Discover the power of {topic} in this hands-on tutorial. "
    "We'll build a complete project from scratch while explaining each step.",

    "Learn professional {topic} techniques used by industry experts. "
    "This video is packed with tips and best practices.",

    None,  # Some videos have no description
]

LANGUAGES = [
    "en", "fr", "de", "es", "it", "pt", "ru", "ja", "zh", "ko",
    "ar", "hi", "nl", "pl", "sv", "tr", None,  # Some have no language
]

# Sample usernames for fake users
USERNAMES = [
    "dev_master", "code_ninja", "tech_guru", "pixel_artist", "data_wizard",
    "cloud_surfer", "byte_hunter", "stack_hero", "git_pusher", "docker_fan",
    "react_dev", "python_lover", "rust_crab", "go_gopher", "java_bean",
    "swift_bird", "kotlin_dev", "ts_pro", "vue_master", "angular_hero",
]

# Sample comments
COMMENTS = [
    "Great video! Very helpful.",
    "Thanks for sharing this!",
    "This is exactly what I was looking for.",
    "Could you make a follow-up video?",
    "Excellent explanation, very clear.",
    "I learned so much from this.",
    "Please make more videos like this!",
    "This helped me solve my problem.",
    "Very well explained, thank you!",
    "Subscribed! Looking forward to more.",
    "What software are you using?",
    "Can you share the source code?",
    "This is the best tutorial I've found.",
    "Finally someone explains it properly!",
    "Love the quality of your videos.",
]

# Placeholder HLS playlist content (minimal valid m3u8)
PLACEHOLDER_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.0,
placeholder.ts
#EXT-X-ENDLIST
"""


def generate_title() -> str:
    """Generate a random video title."""
    template = random.choice(TITLES)
    topic = random.choice(TOPICS)
    action = random.choice(ACTIONS)
    return template.format(topic=topic, action=action)


def generate_description() -> str | None:
    """Generate a random video description."""
    template = random.choice(DESCRIPTIONS)
    if template is None:
        return None
    topic = random.choice(TOPICS)
    return template.format(topic=topic)


def get_videos_folder() -> Path:
    """Get the videos folder path from app configuration."""
    return Path(current_app.config["VIDEOS_FOLDER"])


def get_thumbnails_folder() -> Path:
    """Get the thumbnails folder path from app configuration."""
    return Path(current_app.config["THUMBNAILS_FOLDER"])


def create_placeholder_m3u8(filename: str) -> None:
    """Create a placeholder .m3u8 file for a fake video."""
    videos_folder = get_videos_folder()
    videos_folder.mkdir(parents=True, exist_ok=True)

    m3u8_path = videos_folder / f"{filename}.m3u8"
    m3u8_path.write_text(PLACEHOLDER_M3U8)


def delete_placeholder_m3u8(filename: str) -> None:
    """Delete a placeholder .m3u8 file."""
    videos_folder = get_videos_folder()
    m3u8_path = videos_folder / f"{filename}.m3u8"
    if m3u8_path.exists():
        m3u8_path.unlink()


def create_placeholder_thumbnail(filename: str) -> None:
    """Create a placeholder thumbnail file for a fake video."""
    thumbnails_folder = get_thumbnails_folder()
    thumbnails_folder.mkdir(parents=True, exist_ok=True)

    thumbnail_path = thumbnails_folder / f"{filename}.jpg"
    # Create a minimal valid JPEG (1x1 pixel, gray)
    # This is a valid JPEG file that can be displayed
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xA0, 0x02, 0x80,
        0x0A, 0x00, 0xFF, 0xD9
    ])
    thumbnail_path.write_bytes(minimal_jpeg)


def delete_placeholder_thumbnail(filename: str) -> None:
    """Delete a placeholder thumbnail file."""
    thumbnails_folder = get_thumbnails_folder()
    thumbnail_path = thumbnails_folder / f"{filename}.jpg"
    if thumbnail_path.exists():
        thumbnail_path.unlink()


def generate_password() -> str:
    """Generate a valid password that meets requirements."""
    import secrets
    import string
    # Ensure at least one of each required character type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+")
    ]
    # Fill rest with random characters
    remaining = 12 - len(password)
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    password.extend(secrets.choice(all_chars) for _ in range(remaining))
    random.shuffle(password)
    return "".join(password)


def create_fake_users(count: int) -> list[User]:
    """Create fake user records in the database."""
    from datetime import datetime, timedelta

    users = []
    available_usernames = USERNAMES.copy()
    random.shuffle(available_usernames)

    for i in range(count):
        if i < len(available_usernames):
            username = available_usernames[i]
        else:
            username = f"user_{i}"

        # Skip if user already exists
        existing = User.query.filter_by(username=username).first()
        if existing:
            users.append(existing)
            continue

        user = User(
            username=username,
            role=UserRole.UPLOADER.value,
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 365))
        )
        user.set_password(generate_password())

        # Randomly set last_login for some users
        if random.random() > 0.3:
            user.last_login = datetime.utcnow() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23)
            )

        # Randomly set last_seen for some users (make some "online")
        if random.random() > 0.5:
            user.last_seen = datetime.utcnow() - timedelta(
                minutes=random.randint(0, 60)
            )

        db.session.add(user)
        users.append(user)

    db.session.commit()
    return users


def create_fake_comments(videos: list[Video], users: list[User], count: int) -> list[Comment]:
    """Create fake comments on videos."""
    from datetime import datetime, timedelta

    comments = []
    for _ in range(count):
        video = random.choice(videos)
        user = random.choice(users)

        comment = Comment(
            video_id=video.id,
            author_username=user.username,
            content=random.choice(COMMENTS),
            created_at=datetime.utcnow() - timedelta(
                days=random.randint(0, 60),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
        )
        db.session.add(comment)
        comments.append(comment)

    db.session.commit()
    return comments


def create_fake_videos(count: int, owners: list[User] | str = "admin") -> list[Video]:
    """Create fake video records in the database and placeholder files.

    Args:
        count: Number of videos to create
        owners: Either a list of User objects to randomly assign, or a username string
    """
    videos = []

    # Handle both list of users and single username string
    if isinstance(owners, str):
        owner_usernames = [owners]
    else:
        owner_usernames = [u.username for u in owners]

    for i in range(count):
        title = generate_title()
        description = generate_description()
        language = random.choice(LANGUAGES)
        visibility = random.choices(
            [VideoVisibility.PUBLIC.value, VideoVisibility.PRIVATE.value],
            weights=[0.8, 0.2]  # 80% public, 20% private
        )[0]

        filename = f"fake_video_{i}"
        owner_username = random.choice(owner_usernames)

        video = Video(
            title=title,
            description=description,
            language=language,
            visibility=visibility,
            filename=filename,
            owner_username=owner_username,
            view_count=random.randint(0, 10000),
            thumbnail=f"{filename}.jpg",
        )

        db.session.add(video)
        videos.append(video)

        # Create placeholder .m3u8 file and thumbnail
        create_placeholder_m3u8(filename)
        create_placeholder_thumbnail(filename)

        # Print progress
        if (i + 1) % 10 == 0:
            typer.echo(f"Created {i + 1}/{count} videos...")

    db.session.commit()
    return videos


def clear_fake_data() -> dict[str, int]:
    """Remove all fake data (videos, users, comments)."""
    results = {"videos": 0, "users": 0, "comments": 0}

    # Get all fake videos to delete their files and associated comments
    fake_videos = Video.query.filter(Video.filename.like("fake_video_%")).all()
    fake_video_ids = [v.id for v in fake_videos]

    # Delete comments on fake videos
    if fake_video_ids:
        results["comments"] = Comment.query.filter(Comment.video_id.in_(fake_video_ids)).delete(synchronize_session=False)

    # Delete placeholder files (m3u8 and thumbnails)
    for video in fake_videos:
        delete_placeholder_m3u8(video.filename)
        delete_placeholder_thumbnail(video.filename)

    # Delete fake videos from database
    results["videos"] = Video.query.filter(Video.filename.like("fake_video_%")).delete(synchronize_session=False)

    # Delete fake users (those in USERNAMES list or starting with "user_")
    fake_usernames = USERNAMES + [f"user_{i}" for i in range(100)]
    results["users"] = User.query.filter(User.username.in_(fake_usernames)).delete(synchronize_session=False)

    db.session.commit()
    return results


@app.command()
def populate(
    count: Annotated[int, typer.Option("--count", "-n", help="Number of videos to create")] = 100,
    owner: Annotated[str, typer.Option("--owner", "-o", help="Username of the video owner (ignored if --users > 0)")] = "admin",
    users: Annotated[int, typer.Option("--users", "-u", help="Number of fake users to create and assign videos to")] = 5,
    comments: Annotated[int, typer.Option("--comments", "-c", help="Number of fake comments to create")] = 50,
) -> None:
    """Populate the database with fake users, videos, and comments for testing."""
    flask_app = create_app()

    with flask_app.app_context():
        # Create users if requested
        if users > 0:
            typer.echo(f"Creating {users} fake users...")
            fake_users = create_fake_users(users)
            typer.echo(f"  Created {len(fake_users)} users")
            for user in fake_users[:5]:
                typer.echo(f"    - {user.username}")
            if len(fake_users) > 5:
                typer.echo(f"    ... and {len(fake_users) - 5} more")

            typer.echo(f"\nCreating {count} fake videos (randomly assigned to users)...")
            videos = create_fake_videos(count, fake_users)
        else:
            typer.echo(f"Creating {count} fake videos owned by '{owner}'...")
            videos = create_fake_videos(count, owner)
            fake_users = []

        typer.echo(f"\nSuccessfully created {len(videos)} fake videos!")
        typer.echo(f"Placeholder .m3u8 files created in: {get_videos_folder()}")
        typer.echo("\nSample videos created:")
        for video in videos[:5]:
            typer.echo(f"  - [{video.short_id}] {video.title} (by {video.owner_username})")

        if len(videos) > 5:
            typer.echo(f"  ... and {len(videos) - 5} more")

        # Create comments if users exist
        if comments > 0 and (fake_users or users == 0):
            comment_users = fake_users if fake_users else [User.query.filter_by(username=owner).first()]
            comment_users = [u for u in comment_users if u is not None]
            if comment_users:
                typer.echo(f"\nCreating {comments} fake comments...")
                fake_comments = create_fake_comments(videos, comment_users, comments)
                typer.echo(f"  Created {len(fake_comments)} comments")

        # Print statistics
        public_count = sum(1 for v in videos if v.visibility == VideoVisibility.PUBLIC.value)
        private_count = len(videos) - public_count
        typer.echo(f"\nStatistics:")
        if fake_users:
            typer.echo(f"  Users: {len(fake_users)}")
        typer.echo(f"  Public videos: {public_count}")
        typer.echo(f"  Private videos: {private_count}")
        if comments > 0:
            typer.echo(f"  Comments: {comments}")


@app.command()
def clear() -> None:
    """Clear all fake data (videos, users, comments) from the database."""
    flask_app = create_app()

    with flask_app.app_context():
        results = clear_fake_data()
        typer.echo("Cleared fake data:")
        typer.echo(f"  Videos: {results['videos']}")
        typer.echo(f"  Users: {results['users']}")
        typer.echo(f"  Comments: {results['comments']}")


if __name__ == "__main__":
    app()
