"""add_koji_config_table

Revision ID: d5a864ef89c2
Revises: dabed781b44c
Create Date: 2025-10-31 10:04:57.113655

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a864ef89c2'
down_revision: Union[str, None] = 'dabed781b44c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create koji_configs table
    op.create_table(
        'koji_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('tag', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['project_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id')
    )
    op.create_index('idx_koji_config', 'koji_configs', ['config_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_koji_config', table_name='koji_configs')
    op.drop_table('koji_configs')
