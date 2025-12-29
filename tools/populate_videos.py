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
from rtube.models import db, Video, VideoVisibility

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
    """Get the videos folder path."""
    return Path(current_app.static_folder) / "videos"


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


def create_fake_videos(count: int, owner_username: str = "admin") -> list[Video]:
    """Create fake video records in the database and placeholder files."""
    videos = []

    for i in range(count):
        title = generate_title()
        description = generate_description()
        language = random.choice(LANGUAGES)
        visibility = random.choices(
            [VideoVisibility.PUBLIC.value, VideoVisibility.PRIVATE.value],
            weights=[0.8, 0.2]  # 80% public, 20% private
        )[0]

        filename = f"fake_video_{i}"

        video = Video(
            title=title,
            description=description,
            language=language,
            visibility=visibility,
            filename=filename,
            owner_username=owner_username,
            view_count=random.randint(0, 10000),
        )

        db.session.add(video)
        videos.append(video)

        # Create placeholder .m3u8 file
        create_placeholder_m3u8(filename)

        # Print progress
        if (i + 1) % 10 == 0:
            typer.echo(f"Created {i + 1}/{count} videos...")

    db.session.commit()
    return videos


def clear_fake_videos_from_db() -> int:
    """Remove all fake videos (those with filename starting with 'fake_video_')."""
    # Get all fake videos to delete their files
    fake_videos = Video.query.filter(Video.filename.like("fake_video_%")).all()

    # Delete placeholder files
    for video in fake_videos:
        delete_placeholder_m3u8(video.filename)

    # Delete from database
    deleted = Video.query.filter(Video.filename.like("fake_video_%")).delete()
    db.session.commit()

    return deleted


@app.command()
def populate(
    count: Annotated[int, typer.Option("--count", "-n", help="Number of videos to create")] = 100,
    owner: Annotated[str, typer.Option("--owner", "-o", help="Username of the video owner")] = "admin",
) -> None:
    """Populate the database with fake videos for testing."""
    flask_app = create_app()

    with flask_app.app_context():
        typer.echo(f"Creating {count} fake videos owned by '{owner}'...")
        videos = create_fake_videos(count, owner)

        typer.echo(f"\nSuccessfully created {len(videos)} fake videos!")
        typer.echo(f"Placeholder .m3u8 files created in: {get_videos_folder()}")
        typer.echo("\nSample videos created:")
        for video in videos[:5]:
            typer.echo(f"  - [{video.short_id}] {video.title} ({video.visibility})")

        if len(videos) > 5:
            typer.echo(f"  ... and {len(videos) - 5} more")

        # Print statistics
        public_count = sum(1 for v in videos if v.visibility == VideoVisibility.PUBLIC.value)
        private_count = len(videos) - public_count
        typer.echo(f"\nStatistics:")
        typer.echo(f"  Public videos: {public_count}")
        typer.echo(f"  Private videos: {private_count}")


@app.command()
def clear() -> None:
    """Clear all fake videos from the database and filesystem."""
    flask_app = create_app()

    with flask_app.app_context():
        deleted = clear_fake_videos_from_db()
        typer.echo(f"Cleared {deleted} fake videos (database + files).")


if __name__ == "__main__":
    app()
