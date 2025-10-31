"""add_gitlab_ci_data_source

Revision ID: b9a94fff292b
Revises: 99bc8106fd3d
Create Date: 2025-10-30 09:33:04.713665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9a94fff292b'
down_revision: Union[str, None] = '99bc8106fd3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The data_source column is VARCHAR, not a PostgreSQL enum
    # So no schema changes are needed - the new value can be used directly
    pass


def downgrade() -> None:
    # No changes needed
    pass
