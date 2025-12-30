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

## Features

### Video Player

- HLS streaming with adaptive quality selection
- Keyboard shortcuts (hotkeys)
- Video markers support
- Timestamp sharing via URL parameter (`?t=120` for 2 minutes)

### Video Management

- Upload and encode videos to HLS format
- Video visibility (public/private)
- Video deletion by owner or admin
- Thumbnail generation
- View count tracking

### Comments

- Post, edit, and delete comments on videos
- Automatic URL detection and linking (urlize)
- Character limit (5000 characters)

### Share Button

Each video page includes a share button that copies the current URL to the clipboard. The button provides visual feedback when the URL is copied.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RTUBE_DATABASE_URL` | Database connection URL (PostgreSQL recommended for production) | `sqlite:///rtube.db` |
| `RTUBE_AUTH_DATABASE_URL` | Authentication database URL (separate for security) | `sqlite:///rtube_auth.db` |
| `RTUBE_SECRET_KEY` | Secret key for session security (generate a strong random key for production) | Auto-generated |
| `RTUBE_HTTPS` | Enable secure session cookies (`true`, `1`, or `yes` when using HTTPS) | `false` |
| `RTUBE_KEEP_ORIGINAL_VIDEO` | Keep original MP4 file after encoding (`true`, `1`, or `yes` to enable) | `false` |
| `RTUBE_INSTANCE_PATH` | Custom path for instance folder (sessions, secret key). Must be an absolute path. | `instance/` |

## Authentication

RTube includes a built-in authentication system with three user roles:

- **Anonymous**: Can view videos but cannot upload
- **Uploader**: Can view and upload videos
- **Admin**: Full access including user management and moderation

### User Profiles

Each user has a profile page accessible at `/profile` (own profile) or `/profile/<username>` (any authenticated user). Profiles display:
- Uploaded videos with thumbnails and view counts
- Posted comments with links to the videos

### Admin Features

Administrators have access to `/admin/users` which provides:
- List of all registered users with their roles
- Online/offline status based on recent activity
- Video and comment counts per user
- Direct links to user profiles for moderation

### Session Persistence

User sessions persist across server restarts. Sessions are stored server-side using Flask-Session with filesystem storage. The secret key is automatically generated and saved to `instance/.secret_key` on first run.

### Storage

All media files are stored in the `instance/` folder:
- `instance/videos/` - HLS video files (.m3u8 and .ts segments)
- `instance/thumbnails/` - Video thumbnail images
- `instance/sessions/` - User session data
- `instance/.secret_key` - Persistent secret key

Use `RTUBE_INSTANCE_PATH` to customize the storage location.

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

## Database Migrations

RTube uses [Flask-Migrate](https://flask-migrate.readthedocs.io/) (Alembic) to manage database schema changes.

### For New Installations

If you're setting up RTube for the first time, the database will be created automatically when you start the application. Then stamp the database to mark it as up-to-date:

```bash
flask --app rtube.app:create_app db stamp head
```

### Applying Migrations

After pulling new changes that include database migrations:

```bash
flask --app rtube.app:create_app db upgrade
```

### Creating New Migrations

When you modify the data models (`models.py` or `models_auth.py`):

1. **Auto-generate a migration** based on model changes:
   ```bash
   flask --app rtube.app:create_app db migrate -m "Description of changes"
   ```

2. **Review the generated migration** in `migrations/versions/` before applying it.

3. **Apply the migration**:
   ```bash
   flask --app rtube.app:create_app db upgrade
   ```

### Common Commands

| Command | Description |
|---------|-------------|
| `flask db upgrade` | Apply all pending migrations |
| `flask db downgrade` | Revert the last migration |
| `flask db current` | Show current migration revision |
| `flask db history` | Show migration history |
| `flask db stamp head` | Mark database as up-to-date without running migrations |

**Note**: Always use `--app rtube.app:create_app` with Flask commands, or set the `FLASK_APP` environment variable:
```bash
export FLASK_APP=rtube.app:create_app  # Linux/macOS
set FLASK_APP=rtube.app:create_app     # Windows
```

### Git LFS side note
* Download and install [Git Large File Storage](https://git-lfs.github.com/)
* Track mp4 files `$ git lfs track "*.mp4"`
* `git add/commit/push` will upload on GitHub LFS.
