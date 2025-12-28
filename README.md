# RTube
Streaming platform Proof Of Concept.

## Prerequisites

* [Python 3.11+](https://www.python.org/downloads/)
* [Node.js](https://nodejs.org/en/download)
* [FFmpeg](https://ffmpeg.org/download.html) (must be in your `PATH`)

## Installation

### 1. Install Python dependencies

Using [uv](https://docs.astral.sh/uv/) (recommended):
```bash
uv sync
```

### 2. Install Node.js dependencies

```bash
cd rtube/static
npm install
```

## Usage

### Generate HLS playlist

Convert your MP4 video to HLS format:
```bash
python mp4_to_hls.py
```
This can take some time depending on your CPU.

### Run the server

```bash
flask --app rtube run
```

Then open http://127.0.0.1:5000 in your browser.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RTUBE_DATABASE_URL` | Database connection URL (PostgreSQL recommended for production) | `sqlite:///rtube.db` |
| `RTUBE_AUTH_DATABASE_URL` | Authentication database URL (separate for security) | `sqlite:///rtube_auth.db` |
| `RTUBE_SECRET_KEY` | Secret key for session security (generate a strong random key for production) | Auto-generated |
| `RTUBE_HTTPS` | Enable secure session cookies (`true`, `1`, or `yes` when using HTTPS) | `false` |
| `RTUBE_KEEP_ORIGINAL_VIDEO` | Keep original MP4 file after encoding (`true`, `1`, or `yes` to enable) | `false` |

## Authentication

RTube includes a built-in authentication system with three user roles:

- **Anonymous**: Can view videos but cannot upload
- **Uploader**: Can view and upload videos
- **Admin**: Can view and upload videos with additional privileges

### Default Admin Account

On first startup, a default admin account is created:
- **Username**: `admin`
- **Password**: `admin`

**Important**: Change this password immediately in production!

### Password Requirements

- Minimum 12 characters
- At least one uppercase letter (A-Z)
- At least one lowercase letter (a-z)
- At least one digit (0-9)
- At least one special character
- No common patterns or sequences

### Git LFS side note
* Download and install [Git Large File Storage](https://git-lfs.github.com/)
* Track mp4 files `$ git lfs track "*.mp4"`
* `git add/commit/push` will upload on GitHub LFS.
