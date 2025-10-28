"""add_custom_scraper_support

Revision ID: 655d9abf5c46
Revises: 80d458ac424c
Create Date: 2025-10-28 10:33:43.840465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '655d9abf5c46'
down_revision: Union[str, None] = '80d458ac424c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add JSON fields for flexible scraper configuration
    # Note: chromium_luci enum value is already added in models.py DataSource enum
    # SQLAlchemy handles string enums at the application level, no database migration needed
    op.add_column('project_configs', sa.Column('scraper_config', sa.JSON(), nullable=True))
    op.add_column('builds', sa.Column('scraper_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove JSON columns
    op.drop_column('builds', 'scraper_metadata')
    op.drop_column('project_configs', 'scraper_config')
