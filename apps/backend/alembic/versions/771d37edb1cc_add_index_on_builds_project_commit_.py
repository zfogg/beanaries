"""add_index_on_builds_project_commit_message

Revision ID: 771d37edb1cc
Revises: 655d9abf5c46
Create Date: 2025-10-28 16:50:00.719201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '771d37edb1cc'
down_revision: Union[str, None] = '655d9abf5c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add index on project_id and commit_message for faster queries
    # This will speed up queries that filter builds by project and check for NULL commit messages
    op.create_index(
        'idx_builds_project_commit_message',
        'builds',
        ['project_id', 'commit_message'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_builds_project_commit_message', table_name='builds')
