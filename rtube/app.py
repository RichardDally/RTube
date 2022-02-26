import os
from dotenv import load_dotenv
from flask import render_template, Flask
from flask_s3 import FlaskS3, logger


app = Flask(__name__)

# You can use S3 credentials to fetch directly videos
# app.config['FLASKS3_BUCKET_NAME'] = os.environ.get("FLASKS3_BUCKET_NAME")
# app.config['FLASKS3_ACTIVE'] = True
# app.config['USE_S3_DEBUG'] = True
# app.config['AWS_ACCESS_KEY_ID'] = os.environ.get("AWS_ACCESS_KEY_ID")
# app.config['AWS_SECRET_ACCESS_KEY'] = os.environ.get("AWS_SECRET_ACCESS_KEY")
# s3 = FlaskS3(app)


@app.route('/')
def hello():
    return "OK"


@app.route('/<string:filename>')
def distribute_video(filename):
    markers = {
        "Gameplay": [
            {"time": 10, "text": "Gameplay chapter 1", "overlayText": "Chapter 1"},
            {"time": 20, "text": "Gameplay chapter 2", "overlayText": "Chapter 2"},
            {"time": 30, "text": "Gameplay chapter 3", "overlayText": "Chapter 3"},
        ],
        "Gameplay_2": [
            {"time": 5, "text": "Gameplay 2 chapter 1", "overlayText": "Chapter 1"},
            {"time": 10, "text": "Gameplay 2 chapter 2", "overlayText": "Chapter 2"},
            {"time": 15, "text": "Gameplay 2 chapter 3", "overlayText": "Chapter 3"},
        ],
    }

    video_path_to_load = f"videos/{filename}.m3u8"
    logger.info(f"Looking for [{video_path_to_load}]")
    return render_template(
        'index.html',
        filename=filename,
        video_path_to_load=video_path_to_load,
        markers=markers.get(filename),
    )


if __name__ == '__main__':
    load_dotenv()
    app.run()
