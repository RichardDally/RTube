"""Initial schema

Revision ID: ce7c7ff2a0aa
Revises:
Create Date: 2025-12-29 22:52:58.229957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ce7c7ff2a0aa'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### Main database tables ###

    # Videos table
    op.create_table('videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('short_id', sa.String(length=16), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('visibility', sa.String(length=20), nullable=False),
        sa.Column('thumbnail', sa.String(length=255), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=False),
        sa.Column('owner_username', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename')
    )
    op.create_index(op.f('ix_videos_short_id'), 'videos', ['short_id'], unique=True)

    # Encoding jobs table
    op.create_table('encoding_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('qualities', sa.String(length=255), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('started_by_username', sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Comments table
    op.create_table('comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('author_username', sa.String(length=80), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ### Auth database tables (bind: auth) ###
    # Note: These tables are in a separate database when using SQLALCHEMY_BINDS
    # For SQLite, they will be in the main database
    # For production with separate auth DB, run migrations separately

    # Users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade():
    # ### Auth database tables ###
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')

    # ### Main database tables ###
    op.drop_table('comments')
    op.drop_table('encoding_jobs')
    op.drop_index(op.f('ix_videos_short_id'), table_name='videos')
    op.drop_table('videos')
