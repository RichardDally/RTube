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
| `RTUBE_LDAP_ENABLED` | Enable LDAP authentication (`true`, `1`, or `yes`) | `false` |
| `RTUBE_LDAP_SERVER` | LDAP server URL | `ldap://localhost:389` |
| `RTUBE_LDAP_USE_SSL` | Use SSL/TLS for LDAP connection | `false` |
| `RTUBE_LDAP_BIND_DN` | DN for LDAP bind (service account) | - |
| `RTUBE_LDAP_BIND_PASSWORD` | Password for LDAP bind | - |
| `RTUBE_LDAP_USER_BASE` | Base DN for user search | - |
| `RTUBE_LDAP_USER_FILTER` | LDAP filter for user search | `(uid={username})` |
| `RTUBE_LDAP_USERNAME_ATTRIBUTE` | LDAP attribute containing username | `uid` |

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

### LDAP Authentication

RTube supports LDAP authentication as an alternative to local accounts. When LDAP is enabled:

- All users authenticate via LDAP (except the local `admin` account)
- User accounts are auto-created on first LDAP login
- Local registration is disabled
- The local `admin` account can still login with its password (fallback for emergencies)

#### Configuration Example

```bash
export RTUBE_LDAP_ENABLED=true
export RTUBE_LDAP_SERVER=ldap://ldap.example.com:389
export RTUBE_LDAP_BIND_DN="cn=readonly,dc=example,dc=com"
export RTUBE_LDAP_BIND_PASSWORD="secret"
export RTUBE_LDAP_USER_BASE="ou=users,dc=example,dc=com"
export RTUBE_LDAP_USER_FILTER="(uid={username})"
export RTUBE_LDAP_USERNAME_ATTRIBUTE="uid"
```

#### For Active Directory

```bash
export RTUBE_LDAP_SERVER=ldap://ad.example.com:389
export RTUBE_LDAP_BIND_DN="CN=Service Account,OU=Service Accounts,DC=example,DC=com"
export RTUBE_LDAP_USER_BASE="OU=Users,DC=example,DC=com"
export RTUBE_LDAP_USER_FILTER="(sAMAccountName={username})"
export RTUBE_LDAP_USERNAME_ATTRIBUTE="sAMAccountName"
```

#### How it Works

1. User enters LDAP credentials on the login page
2. RTube searches for the user in LDAP using the configured filter
3. If found, RTube attempts to bind with the user's DN and password
4. On successful authentication, a local user record is created (if first login)
5. The user is logged in with the `uploader` role

### SSO Authentication (OIDC / SAML)

RTube supports Single Sign-On via OpenID Connect (OIDC) and SAML 2.0 protocols. These can be enabled alongside local and LDAP authentication.

#### OIDC Configuration (Keycloak, Azure AD, Okta, etc.)

```bash
export RTUBE_OIDC_ENABLED=true
export RTUBE_OIDC_CLIENT_ID="your-client-id"
export RTUBE_OIDC_CLIENT_SECRET="your-client-secret"
export RTUBE_OIDC_DISCOVERY_URL="https://idp.example.com/.well-known/openid-configuration"
export RTUBE_OIDC_SCOPES="openid profile email"
export RTUBE_OIDC_USERNAME_CLAIM="preferred_username"
```

| Variable | Description | Default |
|----------|-------------|---------|
| `RTUBE_OIDC_ENABLED` | Enable OIDC authentication | `false` |
| `RTUBE_OIDC_CLIENT_ID` | OAuth2 client ID | - |
| `RTUBE_OIDC_CLIENT_SECRET` | OAuth2 client secret | - |
| `RTUBE_OIDC_DISCOVERY_URL` | OIDC discovery endpoint URL | - |
| `RTUBE_OIDC_SCOPES` | Space-separated OAuth2 scopes | `openid profile email` |
| `RTUBE_OIDC_USERNAME_CLAIM` | Claim to use for username | `preferred_username` |

**Callback URL**: Configure your IdP with the callback URL: `https://your-rtube-domain/auth/oidc/callback`

#### SAML 2.0 Configuration (ADFS, Okta, Shibboleth, etc.)

```bash
export RTUBE_SAML_ENABLED=true
export RTUBE_SAML_IDP_ENTITY_ID="https://idp.example.com"
export RTUBE_SAML_IDP_SSO_URL="https://idp.example.com/sso"
export RTUBE_SAML_IDP_CERT_FILE="/path/to/idp-cert.pem"
export RTUBE_SAML_SP_ENTITY_ID="https://rtube.example.com"
export RTUBE_SAML_USERNAME_ATTRIBUTE="uid"
```

| Variable | Description | Default |
|----------|-------------|---------|
| `RTUBE_SAML_ENABLED` | Enable SAML authentication | `false` |
| `RTUBE_SAML_IDP_ENTITY_ID` | IdP Entity ID | - |
| `RTUBE_SAML_IDP_SSO_URL` | IdP Single Sign-On URL | - |
| `RTUBE_SAML_IDP_CERT_FILE` | Path to IdP certificate file | - |
| `RTUBE_SAML_IDP_CERT` | IdP certificate (alternative to file) | - |
| `RTUBE_SAML_SP_ENTITY_ID` | Service Provider Entity ID | Auto-generated |
| `RTUBE_SAML_USERNAME_ATTRIBUTE` | SAML attribute for username | `uid` |
| `RTUBE_SAML_EMAIL_ATTRIBUTE` | SAML attribute for email | `email` |
| `RTUBE_SAML_NAME_ATTRIBUTE` | SAML attribute for display name | `displayName` |

**Service Provider Metadata**: Available at `https://your-rtube-domain/auth/saml/metadata`

**Assertion Consumer Service URL**: `https://your-rtube-domain/auth/saml/acs`

#### How SSO Works

1. User clicks "Sign in with SSO" on the login page
2. User is redirected to the Identity Provider (IdP)
3. After successful authentication, IdP redirects back to RTube
4. RTube creates a local user account on first login (with `uploader` role)
5. User is logged in

SSO users cannot change their password in RTube - authentication is managed by the IdP.

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

### Auth Database Migrations

The `users` table is stored in a separate auth database (`rtube_auth.db` or PostgreSQL). Flask-Migrate only manages the main database, so auth schema changes must be applied manually.

**For LDAP support (adding `auth_type` column):**

SQLite:
```bash
sqlite3 instance/rtube_auth.db "ALTER TABLE users ADD COLUMN auth_type VARCHAR(10) NOT NULL DEFAULT 'local';"
```

PostgreSQL:
```sql
ALTER TABLE users ADD COLUMN auth_type VARCHAR(10) NOT NULL DEFAULT 'local';
```

**For SSO support (adding `sso_subject` column):**

SQLite:
```bash
sqlite3 instance/rtube_auth.db "ALTER TABLE users ADD COLUMN sso_subject VARCHAR(255);"
```

PostgreSQL:
```sql
ALTER TABLE users ADD COLUMN sso_subject VARCHAR(255);
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
