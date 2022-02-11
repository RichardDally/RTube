# RTube
Streaming platform Proof Of Concept.


### Step by step
* Install [FFmpeg](https://ffmpeg.org/download.html), must be in your `PATH`.
* [Install](https://stackoverflow.com/a/39537053/5037799) Python [`requirements.txt`](requirements.txt)
* Install Javascript [`package.json`](rtube/static/package.json)
* Run [`mp4_to_hls.py`](mp4_to_hls.py) to generate playlist from [`Gameplay.mp4`](rtube/static/Gameplay.mp4) (this can be long depending on your CPU power).
* Run [`app.py`](rtube/app.py) to serve local segments
* Enjoy.

### Git LFS side note
* Download and install [Git Large File Storage](https://git-lfs.github.com/)
* Track mp4 files `$ git lfs track "*.mp4"`
* `git add/commit/push` will upload on GitHub LFS. 
