import os
from flask import Flask, render_template
from logging.config import dictConfig


def create_app(test_config=None):
    dictConfig({
        'version': 1,
        'formatters': {'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }},
        'handlers': {'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        }},
        'root': {
            'level': 'INFO',
            'handlers': ['wsgi']
        }
    })

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'rtube.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    db.init_app(app)

    from . import auth
    app.register_blueprint(auth.bp)

    @app.route('/')
    def index():
        return render_template('index.html')

    # @app.route('/<string:filename>')
    # def distribute_video(filename):
    # markers = {
    #     "Gameplay": [
    #         {"time": 10, "text": "Gameplay chapter 1", "overlayText": "Chapter 1"},
    #         {"time": 20, "text": "Gameplay chapter 2", "overlayText": "Chapter 2"},
    #         {"time": 30, "text": "Gameplay chapter 3", "overlayText": "Chapter 3"},
    #     ],
    #     "Gameplay_2": [
    #         {"time": 5, "text": "Gameplay 2 chapter 1", "overlayText": "Chapter 1"},
    #         {"time": 10, "text": "Gameplay 2 chapter 2", "overlayText": "Chapter 2"},
    #         {"time": 15, "text": "Gameplay 2 chapter 3", "overlayText": "Chapter 3"},
    #     ],
    # }

    # video_path_to_load = f"videos/{filename}.m3u8"
    # logger.info(f"Looking for [{video_path_to_load}]")
    # return render_template(
    #     'video.html',
    #     filename=filename,
    #     video_path_to_load=video_path_to_load,
    #     markers=markers.get(filename),
    # )

    return app
