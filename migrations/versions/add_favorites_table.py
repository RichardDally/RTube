"""Add favorites table

Revision ID: add_favorites_table
Revises: ce7c7ff2a0aa
Create Date: 2025-12-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_favorites_table'
down_revision = 'ce7c7ff2a0aa'
branch_labels = None
depends_on = None


def upgrade():
    # Favorites table
    op.create_table('favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', 'video_id', name='unique_user_video_favorite')
    )


def downgrade():
    op.drop_table('favorites')
