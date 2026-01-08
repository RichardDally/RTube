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

### Playlists

- Create and manage custom playlists
- Add/remove videos from playlists
- Reorder videos within playlists
- Public playlist viewing

### Favorites

- Mark videos as favorites
- Quick access to favorite videos from profile

### Search

- Search videos by title, description, or author
- Results grouped by match type

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
| `RTUBE_OIDC_ENABLED` | Enable OIDC authentication (`true`, `1`, or `yes`) | `false` |
| `RTUBE_OIDC_CLIENT_ID` | OAuth2/OIDC client ID | - |
| `RTUBE_OIDC_CLIENT_SECRET` | OAuth2/OIDC client secret | - |
| `RTUBE_OIDC_DISCOVERY_URL` | OIDC discovery endpoint URL (`.well-known/openid-configuration`) | - |
| `RTUBE_OIDC_SCOPES` | Space-separated OAuth2 scopes | `openid profile email` |
| `RTUBE_OIDC_USERNAME_CLAIM` | Claim to use for username | `preferred_username` |
| `RTUBE_OIDC_REDIRECT_URI` | Redirect URI for OIDC callback | `http://127.0.0.1:5000/auth/oidc/callback` |

## Authentication

RTube includes a built-in authentication system with four user roles:

- **Anonymous**: Can view public videos only (not logged in)
- **Viewer**: Can view videos, create playlists, and add favorites, but cannot upload
- **Uploader**: Can view and upload videos, encode videos, manage own content
- **Admin**: Full access including user management, role changes, and moderation

### User Profiles

Each user has a profile page accessible at `/profile` (own profile) or `/profile/<username>` (any authenticated user). Profiles display:
- Uploaded videos with thumbnails and view counts
- Posted comments with links to the videos

### Admin Features

Administrators have access to the **Admin** dropdown menu which provides:

#### User Management (`/admin/users`)
- List of all registered users with their roles
- Online/offline status based on recent activity
- Video, comment, playlist, and favorite counts per user
- Role management: change user roles (Viewer, Uploader, Admin)
- Direct links to user profiles for moderation
- Password change for admin account

#### Import Videos (`/admin/import-videos`)
- Scan for orphan encoded videos (HLS files not in database)
- Display available quality variants for each video
- Bulk import with automatic thumbnail generation
- Videos are imported as private by default

#### Video Editing (`/watch/edit`)
- Admins can edit any video (not just their own)
- Change video owner to any Uploader or Admin user

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

### OIDC Authentication (SSO)

RTube supports Single Sign-On via OpenID Connect (OIDC). This works with any OIDC-compliant identity provider (Keycloak, Authentik, Azure AD, Okta, Google, etc.).

#### Configuration Example

```bash
export RTUBE_OIDC_ENABLED=true
export RTUBE_OIDC_CLIENT_ID="rtube"
export RTUBE_OIDC_CLIENT_SECRET="your-client-secret"
export RTUBE_OIDC_DISCOVERY_URL="https://auth.example.com/realms/master/.well-known/openid-configuration"
export RTUBE_OIDC_SCOPES="openid profile email"
export RTUBE_OIDC_USERNAME_CLAIM="preferred_username"
```

#### How it Works

1. User clicks "Sign in with SSO (OIDC)" on the login page
2. User is redirected to the Identity Provider (IdP)
3. After successful authentication, IdP redirects back to RTube
4. RTube creates a local user account on first login (with `uploader` role)
5. User is logged in

OIDC users can also use local credentials if they have a local account.

#### Testing OIDC Locally

For local development and testing, you can use one of these OIDC providers:

##### Option 1: Authentik (Recommended)

[Authentik](https://goauthentik.io/) is an open-source identity provider that's easy to set up with Docker.

```bash
# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  postgresql:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - database:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: authentik
      POSTGRES_USER: authentik
      POSTGRES_DB: authentik

  redis:
    image: redis:alpine
    restart: unless-stopped

  server:
    image: ghcr.io/goauthentik/server:latest
    restart: unless-stopped
    command: server
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: authentik
      AUTHENTIK_SECRET_KEY: "generate-a-random-secret-key-here"
    ports:
      - "9000:9000"
      - "9443:9443"
    depends_on:
      - postgresql
      - redis

  worker:
    image: ghcr.io/goauthentik/server:latest
    restart: unless-stopped
    command: worker
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: authentik
      AUTHENTIK_SECRET_KEY: "generate-a-random-secret-key-here"
    depends_on:
      - postgresql
      - redis

volumes:
  database:
EOF

# Start Authentik
docker compose up -d
```

Then:
1. Open http://localhost:9000/if/flow/initial-setup/ to create admin account
2. Create a new OAuth2/OIDC Provider in Admin > Providers
3. Create an Application linked to this provider
4. Configure RTube with the client credentials

##### Option 2: Keycloak

```bash
docker run -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:latest start-dev
```

Then:
1. Open http://localhost:8080 and log in with admin/admin
2. Create a new Realm (e.g., "rtube")
3. Create a new Client with:
   - Client ID: `rtube`
   - Client authentication: ON
   - Valid redirect URIs: `http://127.0.0.1:5000/auth/oidc/callback`
4. Copy the client secret from Credentials tab
5. Configure RTube:
   ```bash
   export RTUBE_OIDC_ENABLED=true
   export RTUBE_OIDC_CLIENT_ID="rtube"
   export RTUBE_OIDC_CLIENT_SECRET="your-client-secret"
   export RTUBE_OIDC_DISCOVERY_URL="http://localhost:8080/realms/rtube/.well-known/openid-configuration"
   ```

##### Option 3: mock-oidc-server (Lightweight)

For quick testing without a full IdP, you can use a mock OIDC server:

```bash
# Using Node.js
npx mock-oidc-server --port 9090

# Or using Python
pip install oidc-provider
python -m oidc_provider
```

**Note**: Mock servers are for development only - never use in production!

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

### Auth Database Migrations

The `users` table is stored in a separate auth database (`rtube_auth.db` or PostgreSQL). Flask-Migrate only manages the main database, so auth schema changes must be applied manually.

**For role column (if upgrading from older version):**

The `role` column should already exist with default value `uploader`. Valid roles are: `viewer`, `uploader`, `admin`.

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

## Publishing to PyPI

RTube includes a GitHub Actions workflow to build and publish packages to PyPI using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC).

### Setup

1. **Configure Trusted Publisher on PyPI**:
   - Go to [PyPI Publishing Settings](https://pypi.org/manage/account/publishing/)
   - Click "Add a new pending publisher" (for new projects) or configure on the project page (for existing projects)
   - Fill in the form:
     - **PyPI Project Name**: `rtube`
     - **Owner**: your GitHub username or organization
     - **Repository name**: `RTube`
     - **Workflow name**: `publish.yml`
     - **Environment name**: `pypi`
   - Click "Add"

2. **Create a GitHub Environment**:
   - Go to your repository on GitHub
   - Navigate to **Settings** > **Environments**
   - Click **New environment**
   - Name: `pypi` (must match the name configured on PyPI)
   - Add protection rules if desired (e.g., required reviewers)

No API tokens or secrets are required - authentication is handled automatically via OIDC.

### Triggering a Release

The workflow is triggered automatically when you push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Or manually via the Actions tab using "workflow_dispatch".

### Workflow Steps

1. **Build**: Creates wheel and sdist using `uv build`
2. **Publish to PyPI**: Uploads packages using OIDC trusted publishing
3. **Create GitHub Release**: Creates a release with the built artifacts
4. **Rollback on failure**: Logs errors and provides guidance if any step fails

### Git LFS side note
* Download and install [Git Large File Storage](https://git-lfs.github.com/)
* Track mp4 files `$ git lfs track "*.mp4"`
* `git add/commit/push` will upload on GitHub LFS.
