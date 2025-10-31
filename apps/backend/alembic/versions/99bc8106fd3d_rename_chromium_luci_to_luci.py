"""rename_chromium_luci_to_luci

Revision ID: 99bc8106fd3d
Revises: 771d37edb1cc
Create Date: 2025-10-28 18:17:25.264960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99bc8106fd3d'
down_revision: Union[str, None] = '771d37edb1cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update data_source from 'chromium_luci' to 'luci' in project_configs
    op.execute("""
        UPDATE project_configs
        SET data_source = 'luci'
        WHERE data_source = 'chromium_luci'
    """)

    # Update data_source from 'chromium_luci' to 'luci' in builds
    op.execute("""
        UPDATE builds
        SET data_source = 'luci'
        WHERE data_source = 'chromium_luci'
    """)


def downgrade() -> None:
    # Revert data_source from 'luci' back to 'chromium_luci' in project_configs
    op.execute("""
        UPDATE project_configs
        SET data_source = 'chromium_luci'
        WHERE data_source = 'luci'
    """)

    # Revert data_source from 'luci' back to 'chromium_luci' in builds
    op.execute("""
        UPDATE builds
        SET data_source = 'chromium_luci'
        WHERE data_source = 'luci'
    """)

