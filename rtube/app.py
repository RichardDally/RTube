import os
import re
import logging
import secrets
from datetime import datetime
from pathlib import Path
from logging.config import dictConfig
from flask import Flask, render_template
from flask.cli import load_dotenv
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_session import Session
from markupsafe import Markup, escape

from rtube.models import db
from rtube.models_auth import User, create_default_admin
from rtube.routes import videos_bp, encoding_bp, admin_bp, playlists_bp
from rtube.routes.auth import auth_bp
from rtube.services.encoder import encoder_service
from rtube.services.oidc_auth import OIDCConfig, configure_flask_oidc

# Keys that contain sensitive information and should be redacted in logs
SENSITIVE_KEYS = {'SECRET_KEY', 'PASSWORD', 'TOKEN', 'API_KEY', 'DATABASE_URL', 'SQLALCHEMY_DATABASE_URI'}


def _redact_value(key: str, value) -> str:
    """Redact sensitive values for logging."""
    key_upper = key.upper()
    # Check if any sensitive keyword is in the key name
    if any(sensitive in key_upper for sensitive in SENSITIVE_KEYS):
        if isinstance(value, dict):
            # Handle SQLALCHEMY_BINDS which is a dict
            return {k: _redact_value(k, v) for k, v in value.items()}
        return "***REDACTED***"
    return value


def _log_configuration(app):
    """Log application configuration at startup with secrets redacted."""
    import rtube
    app.logger.info("=" * 60)
    app.logger.info(f"RTube v{rtube.__version__} starting up")
    app.logger.info("=" * 60)
    app.logger.info("Configuration:")
    app.logger.info(f"  Instance path: {app.instance_path}")
    app.logger.info(f"  Static folder: {app.static_folder}")
    app.logger.info(f"  Videos folder: {app.config.get('VIDEOS_FOLDER')}")
    app.logger.info(f"  Thumbnails folder: {app.config.get('THUMBNAILS_FOLDER')}")
    app.logger.info(f"  Database URI: {_redact_value('DATABASE_URL', app.config.get('SQLALCHEMY_DATABASE_URI'))}")
    app.logger.info(f"  Auth database: {_redact_value('DATABASE_URL', app.config.get('SQLALCHEMY_BINDS', {}).get('auth'))}")
    app.logger.info(f"  Secret key: {_redact_value('SECRET_KEY', app.config.get('SECRET_KEY'))}")
    app.logger.info(f"  Session type: {app.config.get('SESSION_TYPE', 'default')}")
    app.logger.info(f"  Session cookie secure: {app.config.get('SESSION_COOKIE_SECURE')}")
    app.logger.info(f"  Keep original video: {app.config.get('KEEP_ORIGINAL_VIDEO')}")
    app.logger.info(f"  Max upload size: {app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024 * 1024):.1f} GB")
    app.logger.info(f"  OIDC enabled: {app.config.get('OIDC_ENABLED', False)}")
    app.logger.info("=" * 60)

    # Check if node_modules exists in static folder
    if app.static_folder:
        node_modules_path = Path(app.static_folder) / "node_modules"
        if not node_modules_path.exists():
            app.logger.critical(
                f"node_modules not found in static folder ({app.static_folder}). "
                f"Run 'npm install' in the static folder to install JavaScript dependencies."
            )


migrate = Migrate()

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(test_config=None):
    dictConfig(
        {
            # Specify the logging configuration version
            "version": 1,
            "formatters": {
                # Define a formatter named 'default'
                "default": {
                    # Specify log message format
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
                }
            },
            "handlers": {
                # Define a console handler configuration
                "console": {
                    # Use StreamHandler to log to stdout
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    # Use 'default' formatter for this handler
                    "formatter": "default",
                }
            },
            # Configure the root logger
            "root": {
                # Set root logger level to DEBUG
                "level": "DEBUG",
                # Attach 'console' handler to the root logger
                "handlers": ["console"]},
        }
    )
    load_dotenv()

    # Custom instance path for storing sessions, secret key, etc.
    instance_path = os.environ.get("RTUBE_INSTANCE_PATH")
    if instance_path:
        # Static folder is inside the installed package (wheel)
        package_dir = Path(__file__).parent
        static_folder = str(package_dir / "static")
        app = Flask(__name__, instance_path=instance_path, static_folder=static_folder)
    else:
        app = Flask(__name__)

    # Check if running in test mode (from environment or test_config)
    is_testing = (
        os.environ.get("TESTING", "").lower() in ("true", "1", "yes")
        or (test_config and test_config.get("TESTING"))
    )

    # Secret key for session security
    # Priority: environment variable > persistent file > generate new
    secret_key = os.environ.get("RTUBE_SECRET_KEY")
    if not secret_key and not is_testing:
        # Try to load from persistent file
        secret_key_path = Path(app.instance_path) / ".secret_key"
        secret_key_path.parent.mkdir(parents=True, exist_ok=True)
        if secret_key_path.exists():
            secret_key = secret_key_path.read_text().strip()
        else:
            # Generate and save a new key
            secret_key = secrets.token_hex(32)
            secret_key_path.write_text(secret_key)
    app.config["SECRET_KEY"] = secret_key or secrets.token_hex(32)

    # Session security settings
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RTUBE_HTTPS", "").lower() in ("true", "1", "yes")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Server-side session configuration (persists across restarts)
    if not is_testing:
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = str(Path(app.instance_path) / "sessions")
        app.config["SESSION_PERMANENT"] = True
        app.config["SESSION_USE_SIGNER"] = True
        # Create sessions directory if it doesn't exist
        Path(app.config["SESSION_FILE_DIR"]).mkdir(parents=True, exist_ok=True)

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

    # OIDC configuration
    oidc_config = OIDCConfig.from_env(os.environ)
    if oidc_config and not is_testing:
        configure_flask_oidc(app, oidc_config)
    else:
        app.config["OIDC_ENABLED"] = False

    # Media storage paths (within instance folder)
    app.config["VIDEOS_FOLDER"] = str(Path(app.instance_path) / "videos")
    app.config["THUMBNAILS_FOLDER"] = str(Path(app.instance_path) / "thumbnails")

    # Create media directories if they don't exist
    Path(app.config["VIDEOS_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["THUMBNAILS_FOLDER"]).mkdir(parents=True, exist_ok=True)

    # Log configuration at startup (redact secrets)
    if not is_testing:
        _log_configuration(app)

    # Initialize database
    db.init_app(app)

    # Initialize Flask-Migrate (skip for in-memory test databases)
    if not is_testing:
        migrate.init_app(app, db)

    # Initialize Flask-Login
    login_manager.init_app(app)

    # Initialize Flask-Session (server-side sessions, skip for tests)
    if not is_testing:
        Session(app)

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
    app.register_blueprint(admin_bp)
    app.register_blueprint(playlists_bp)

    # Error handlers
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('400.html'), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('401.html'), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template('405.html'), 405

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    @app.errorhandler(501)
    def not_implemented(e):
        return render_template('501.html'), 501

    @app.errorhandler(503)
    def service_unavailable(e):
        return render_template('503.html'), 503

    # Update last_seen timestamp for logged-in users
    @app.before_request
    def update_last_seen():
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

    # Inject version, auth status, and active announcement into all templates
    @app.context_processor
    def inject_globals():
        import rtube
        from rtube.models import Announcement

        # Get active, non-expired announcement (most recent)
        active_announcement = Announcement.query.filter(
            Announcement.is_active == True
        ).order_by(Announcement.created_at.desc()).first()

        # Filter out expired announcements
        if active_announcement and active_announcement.is_expired():
            active_announcement = None

        return {
            "rtube_version": rtube.__version__,
            "oidc_enabled": app.config.get("OIDC_ENABLED", False),
            "active_announcement": active_announcement,
        }

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

    # Configure logging for gunicorn
    # When running under gunicorn, propagate its handlers to root logger
    # so all module loggers (logging.getLogger(__name__)) also output properly
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        # Running under gunicorn - use its handlers for all loggers
        root_logger = logging.getLogger()
        root_logger.handlers = gunicorn_logger.handlers
        root_logger.setLevel(gunicorn_logger.level)
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)

    return app
