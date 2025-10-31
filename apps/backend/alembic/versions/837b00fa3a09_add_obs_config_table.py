"""add_obs_config_table

Revision ID: 837b00fa3a09
Revises: d5a864ef89c2
Create Date: 2025-10-31 11:29:29.031405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '837b00fa3a09'
down_revision: Union[str, None] = 'd5a864ef89c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create obs_configs table
    op.create_table(
        'obs_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('repository', sa.String(length=255), nullable=True),
        sa.Column('arch', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['project_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id')
    )
    op.create_index('idx_obs_config', 'obs_configs', ['config_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_obs_config', table_name='obs_configs')
    op.drop_table('obs_configs')
