"""Add sso_subject column to users table

Revision ID: add_sso_subject_to_users
Revises: add_auth_type_to_users
Create Date: 2026-01-01

Note: The users table is in the 'auth' bind, not the main database.
This migration must be applied manually to the auth database.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sso_subject_to_users'
down_revision = 'add_auth_type_to_users'
branch_labels = None
depends_on = None


def upgrade():
    # Note: The users table is in the 'auth' bind (separate database).
    # Flask-Migrate doesn't handle binds automatically, so this migration
    # needs to connect to the auth database.
    #
    # For SQLite auth database, run manually:
    #   sqlite3 instance/rtube_auth.db
    #   ALTER TABLE users ADD COLUMN sso_subject VARCHAR(255);
    #
    # For PostgreSQL auth database:
    #   psql -d rtube_auth
    #   ALTER TABLE users ADD COLUMN sso_subject VARCHAR(255);

    # Try to apply to the auth bind if available
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if users table exists in this database
    if 'users' in inspector.get_table_names():
        # Check if sso_subject column already exists
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'sso_subject' not in columns:
            op.add_column(
                'users',
                sa.Column('sso_subject', sa.String(length=255), nullable=True),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        if 'sso_subject' in columns:
            op.drop_column('users', 'sso_subject')
