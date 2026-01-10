"""Add announcements table

Revision ID: add_announcements_table
Revises: add_audit_logs_table
Create Date: 2026-01-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_announcements_table'
down_revision = 'add_audit_logs_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('announcements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('announcements')
