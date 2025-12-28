import os
from flask import Flask
from flask.cli import load_dotenv

from rtube.models import db
from rtube.routes import videos_bp, encoding_bp
from rtube.services.encoder import encoder_service


def create_app():
    load_dotenv()
    app = Flask(__name__)

    # Database configuration: PostgreSQL in production, SQLite in development
    database_url = os.environ.get("RTUBE_DATABASE_URL")
    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///rtube.db"

    # File upload configuration
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 1024  # 16 GB max

    # Encoding configuration
    app.config["KEEP_ORIGINAL_VIDEO"] = os.environ.get("RTUBE_KEEP_ORIGINAL_VIDEO", "").lower() in ("true", "1", "yes")

    db.init_app(app)
    encoder_service.init_app(app)

    with app.app_context():
        db.create_all()

    app.register_blueprint(videos_bp)
    app.register_blueprint(encoding_bp)

    return app
