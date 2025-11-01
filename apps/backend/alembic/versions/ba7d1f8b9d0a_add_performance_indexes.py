"""add_performance_indexes

Revision ID: ba7d1f8b9d0a
Revises: 837b00fa3a09
Create Date: 2025-10-31 17:02:48.214068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba7d1f8b9d0a'
down_revision: Union[str, None] = '837b00fa3a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Index for efficient latest build lookups in leaderboard
    # Partial index excludes NULL durations and outliers > 24 hours
    op.create_index(
        'idx_builds_latest_by_project',
        'builds',
        ['project_id', sa.text('finished_at DESC')],
        unique=False,
        postgresql_where=sa.text('duration_seconds IS NOT NULL AND duration_seconds <= 86400')
    )

    # Composite index for duplicate detection and commit lookups
    op.create_index(
        'idx_builds_project_commit_platform',
        'builds',
        ['project_id', 'commit_sha', 'platform'],
        unique=False
    )

    # Partial index for enabled configs scheduled check
    op.create_index(
        'idx_configs_enabled_check',
        'project_configs',
        ['last_checked_at', 'check_interval_hours'],
        unique=False,
        postgresql_where=sa.text('is_enabled = true')
    )


def downgrade() -> None:
    op.drop_index('idx_configs_enabled_check', table_name='project_configs')
    op.drop_index('idx_builds_project_commit_platform', table_name='builds')
    op.drop_index('idx_builds_latest_by_project', table_name='builds')
