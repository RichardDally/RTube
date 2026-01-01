"""Add auth_type column to users table

Revision ID: add_auth_type_to_users
Revises: add_playlists_tables
Create Date: 2026-01-01

Note: The users table is in the 'auth' bind, not the main database.
This migration must be applied manually to the auth database.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_auth_type_to_users'
down_revision = 'add_playlists_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Note: The users table is in the 'auth' bind (separate database).
    # Flask-Migrate doesn't handle binds automatically, so this migration
    # needs to connect to the auth database.
    #
    # For SQLite auth database, run manually:
    #   sqlite3 instance/rtube_auth.db
    #   ALTER TABLE users ADD COLUMN auth_type VARCHAR(10) NOT NULL DEFAULT 'local';
    #
    # For PostgreSQL auth database:
    #   psql -d rtube_auth
    #   ALTER TABLE users ADD COLUMN auth_type VARCHAR(10) NOT NULL DEFAULT 'local';
    #
    # The password_hash column is already nullable in SQLite (SQLite ignores NOT NULL
    # constraints on ALTER TABLE), but for PostgreSQL you may need:
    #   ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

    # Try to apply to the auth bind if available
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if users table exists in this database
    if 'users' in inspector.get_table_names():
        # Check if auth_type column already exists
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'auth_type' not in columns:
            op.add_column(
                'users',
                sa.Column('auth_type', sa.String(length=10), nullable=False, server_default='local'),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'auth_type' in columns:
            op.drop_column('users', 'auth_type')
