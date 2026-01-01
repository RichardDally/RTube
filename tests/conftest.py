"""
Pytest configuration and fixtures for RTube tests.
"""
import os
import uuid
import pytest

# Set testing environment before importing app
os.environ["TESTING"] = "true"

from rtube.app import create_app
from rtube.models import db, Video
from rtube.models_auth import User, UserRole


@pytest.fixture(scope="function")
def app():
    """Create and configure a test application instance with in-memory SQLite."""
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_BINDS": {"auth": "sqlite:///:memory:"},
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
        "LOGIN_DISABLED": False,
    }

    # Pass test config directly to create_app so it's applied before db.create_all()
    app = create_app(test_config=test_config)

    yield app

    # Cleanup
    with app.app_context():
        db.session.remove()


@pytest.fixture(scope="function")
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture(scope="function")
def sample_user(app):
    """Create a sample user for testing."""
    with app.app_context():
        # Check if user already exists
        existing = User.query.filter_by(username="testuser").first()
        if existing:
            return {"id": existing.id, "username": "testuser", "password": "TestPassword123!"}

        user = User(
            username="testuser",
            role=UserRole.UPLOADER.value
        )
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()

        db.session.refresh(user)
        user_id = user.id

    return {"id": user_id, "username": "testuser", "password": "TestPassword123!"}


@pytest.fixture(scope="function")
def sample_admin(app):
    """Create a sample admin user for testing."""
    with app.app_context():
        # Check if admin already exists
        existing = User.query.filter_by(username="testadmin").first()
        if existing:
            return {"id": existing.id, "username": "testadmin", "password": "AdminPassword123!"}

        admin = User(
            username="testadmin",
            role=UserRole.ADMIN.value
        )
        admin.set_password("AdminPassword123!")
        db.session.add(admin)
        db.session.commit()

        db.session.refresh(admin)
        admin_id = admin.id

    return {"id": admin_id, "username": "testadmin", "password": "AdminPassword123!"}


@pytest.fixture(scope="function")
def sample_video(app):
    """Create a sample video for testing."""
    unique_id = uuid.uuid4().hex[:8]
    with app.app_context():
        video = Video(
            title="Test Video",
            description="A test video description",
            language="en",
            visibility="public",
            filename=f"testvideo_{unique_id}",
            owner_username="testuser"
        )
        db.session.add(video)
        db.session.commit()

        db.session.refresh(video)
        result = {
            "id": video.id,
            "short_id": video.short_id,
            "title": video.title,
            "filename": video.filename
        }

    return result


@pytest.fixture(scope="function")
def sample_private_video(app):
    """Create a sample private video for testing."""
    unique_id = uuid.uuid4().hex[:8]
    with app.app_context():
        video = Video(
            title="Private Test Video",
            description="A private test video",
            language="fr",
            visibility="private",
            filename=f"privatevideo_{unique_id}",
            owner_username="testuser"
        )
        db.session.add(video)
        db.session.commit()

        db.session.refresh(video)
        result = {
            "id": video.id,
            "short_id": video.short_id,
            "title": video.title,
            "filename": video.filename
        }

    return result


@pytest.fixture(scope="function")
def authenticated_client(client, sample_user):
    """Create an authenticated test client."""
    client.post('/auth/login', data={
        'username': sample_user['username'],
        'password': sample_user['password']
    })
    return client


@pytest.fixture(scope="function")
def admin_client(client, sample_admin):
    """Create an admin authenticated test client."""
    client.post('/auth/login', data={
        'username': sample_admin['username'],
        'password': sample_admin['password']
    })
    return client
