import os
import secrets
from flask import Flask
from flask.cli import load_dotenv
from flask_login import LoginManager

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


def create_app():
    load_dotenv()
    app = Flask(__name__)

    # Secret key for session security (generate if not set)
    app.config["SECRET_KEY"] = os.environ.get("RTUBE_SECRET_KEY") or secrets.token_hex(32)

    # Session security settings
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RTUBE_HTTPS", "").lower() in ("true", "1", "yes")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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
        # Create default admin if not exists
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

    return app
