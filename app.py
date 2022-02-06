from flask import render_template, Flask, send_from_directory

app = Flask(__name__)


# @app.after_request
# def add_header(response):
#     response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
#     response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
#     response.headers['Pragma'] = 'no-cache'
#     response.headers['Expires'] = '0'
#     return response


@app.route('/')
def index():
    return render_template('video-player.html')
    # return render_template('index.html')


# @app.route('/videos/<string:file_name>')
# def stream(file_name):
#     video_dir = './videos'
#     return send_from_directory(directory=video_dir, path=file_name)


if __name__ == '__main__':
    app.run()
