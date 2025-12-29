import os
import re
import secrets
from flask import Flask
from flask.cli import load_dotenv
from flask_login import LoginManager
from markupsafe import Markup, escape

from rtube.models import db
from rtube.models_auth import User, create_default_admin
from rtube.routes import videos_bp, encoding_bp
from rtube.routes.auth import auth_bp
from rtube.services.encoder import encoder_service

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)

    # Check if running in test mode (from environment or test_config)
    is_testing = (
        os.environ.get("TESTING", "").lower() in ("true", "1", "yes")
        or (test_config and test_config.get("TESTING"))
    )

    # Secret key for session security (generate if not set)
    app.config["SECRET_KEY"] = os.environ.get("RTUBE_SECRET_KEY") or secrets.token_hex(32)

    # Session security settings
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RTUBE_HTTPS", "").lower() in ("true", "1", "yes")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Database configuration
    if is_testing:
        # Use in-memory SQLite for tests
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_BINDS"] = {"auth": "sqlite:///:memory:"}
        app.config["TESTING"] = True
    else:
        # Main database configuration: PostgreSQL in production, SQLite in development
        database_url = os.environ.get("RTUBE_DATABASE_URL")
        if database_url:
            app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        else:
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///rtube.db"

        # Auth database configuration (separate database for security)
        auth_database_url = os.environ.get("RTUBE_AUTH_DATABASE_URL")
        if auth_database_url:
            app.config["SQLALCHEMY_BINDS"] = {"auth": auth_database_url}
        else:
            app.config["SQLALCHEMY_BINDS"] = {"auth": "sqlite:///rtube_auth.db"}

    # Apply additional test configuration if provided
    if test_config:
        app.config.update(test_config)

    # File upload configuration
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 1024  # 16 GB max

    # Encoding configuration
    app.config["KEEP_ORIGINAL_VIDEO"] = os.environ.get("RTUBE_KEEP_ORIGINAL_VIDEO", "").lower() in ("true", "1", "yes")

    # Initialize database
    db.init_app(app)

    # Initialize Flask-Login
    login_manager.init_app(app)

    # Initialize encoder service
    encoder_service.init_app(app)

    with app.app_context():
        db.create_all()
        # Create default admin if not exists (skip in testing mode)
        if not app.config.get("TESTING"):
            create_default_admin(app)

    # Register blueprints
    app.register_blueprint(videos_bp)
    app.register_blueprint(encoding_bp)
    app.register_blueprint(auth_bp)

    # Inject version into all templates
    @app.context_processor
    def inject_version():
        import rtube
        return {"rtube_version": rtube.__version__}

    # Custom Jinja2 filter to convert URLs to clickable links
    @app.template_filter('urlize')
    def urlize_filter(text):
        """Convert URLs in text to clickable hyperlinks."""
        if not text:
            return text

        # Escape HTML first to prevent XSS
        text = str(escape(text))

        # Regex pattern for URLs (http, https, ftp)
        url_pattern = re.compile(
            r'(https?://|ftp://)'  # Protocol
            r'[^\s<>\[\]()"\']+'   # URL body (no whitespace or special chars)
            r'(?<![.,;:!?\)])'     # Don't end with punctuation
        )

        def replace_url(match):
            url = match.group(0)
            # Truncate display URL if too long
            display_url = url if len(url) <= 50 else url[:47] + '...'
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{display_url}</a>'

        result = url_pattern.sub(replace_url, text)
        return Markup(result)

    return app
