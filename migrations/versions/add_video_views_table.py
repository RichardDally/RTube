"""Add video_views table for analytics

Revision ID: add_video_views_table
Revises: add_announcements_table
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_video_views_table'
down_revision = 'add_announcements_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('video_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_video_views_viewed_at', 'video_views', ['viewed_at'], unique=False)


def downgrade():
    op.drop_index('ix_video_views_viewed_at', table_name='video_views')
    op.drop_table('video_views')
