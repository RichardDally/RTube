"""Add audit_logs table

Revision ID: add_audit_logs_table
Revises: fd575abbada4
Create Date: 2026-01-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_audit_logs_table'
down_revision = 'fd575abbada4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.String(length=100), nullable=True),
        sa.Column('target_name', sa.String(length=255), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_audit_logs_timestamp', ['timestamp'], unique=False)
        batch_op.create_index('ix_audit_logs_username', ['username'], unique=False)
        batch_op.create_index('ix_audit_logs_action', ['action'], unique=False)


def downgrade():
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_logs_action')
        batch_op.drop_index('ix_audit_logs_username')
        batch_op.drop_index('ix_audit_logs_timestamp')

    op.drop_table('audit_logs')
