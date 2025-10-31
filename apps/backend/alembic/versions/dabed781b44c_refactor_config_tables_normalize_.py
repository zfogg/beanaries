"""refactor_config_tables_normalize_scrapers

Revision ID: dabed781b44c
Revises: b9a94fff292b
Create Date: 2025-10-31 09:21:38.566006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dabed781b44c'
down_revision: Union[str, None] = 'b9a94fff292b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new tables for each scraper type

    # GitHub Actions configs table
    op.create_table(
        'github_actions_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('workflow_file', sa.String(length=255), nullable=False),
        sa.Column('workflow_name', sa.String(length=255), nullable=True),
        sa.Column('job_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['project_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id')
    )
    op.create_index('idx_gh_actions_config', 'github_actions_configs', ['config_id'], unique=False)

    # LUCI configs table
    op.create_table(
        'luci_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('bucket', sa.String(length=255), nullable=False),
        sa.Column('builder', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['project_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id')
    )
    op.create_index('idx_luci_config', 'luci_configs', ['config_id'], unique=False)

    # Buildkite configs table
    op.create_table(
        'buildkite_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('org_slug', sa.String(length=255), nullable=False),
        sa.Column('pipeline_slug', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['project_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id')
    )
    op.create_index('idx_buildkite_config', 'buildkite_configs', ['config_id'], unique=False)

    # Add data_source index to project_configs
    op.create_index('idx_configs_data_source', 'project_configs', ['data_source'], unique=False)

    # Migrate data from old schema to new schema
    connection = op.get_bind()

    # Migrate GitHub Actions configs
    connection.execute(sa.text("""
        INSERT INTO github_actions_configs (config_id, workflow_file, workflow_name, job_name, created_at, updated_at)
        SELECT
            id,
            COALESCE(workflow_file, 'unknown.yml'),
            workflow_name,
            job_name,
            created_at,
            updated_at
        FROM project_configs
        WHERE data_source = 'github_actions'
    """))

    # Migrate LUCI configs
    connection.execute(sa.text("""
        INSERT INTO luci_configs (config_id, project_name, bucket, builder, created_at, updated_at)
        SELECT
            id,
            COALESCE(scraper_config->>'project', 'unknown'),
            COALESCE(scraper_config->>'bucket', 'ci'),
            COALESCE(scraper_config->>'builder', 'unknown'),
            created_at,
            updated_at
        FROM project_configs
        WHERE data_source = 'luci'
    """))

    # Migrate Buildkite configs
    connection.execute(sa.text("""
        INSERT INTO buildkite_configs (config_id, org_slug, pipeline_slug, created_at, updated_at)
        SELECT
            id,
            COALESCE(scraper_config->>'org_slug', 'unknown'),
            COALESCE(scraper_config->>'pipeline_slug', 'unknown'),
            created_at,
            updated_at
        FROM project_configs
        WHERE data_source = 'buildkite'
    """))

    # Drop old columns from project_configs
    op.drop_column('project_configs', 'workflow_name')
    op.drop_column('project_configs', 'workflow_file')
    op.drop_column('project_configs', 'job_name')
    op.drop_column('project_configs', 'build_command')
    op.drop_column('project_configs', 'build_dir')
    op.drop_column('project_configs', 'source_url')
    op.drop_column('project_configs', 'extract_command')
    op.drop_column('project_configs', 'scraper_config')

    # Make platform nullable (it's used for filtering, not all configs need it)
    op.alter_column('project_configs', 'platform',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)


def downgrade() -> None:
    # Restore platform to non-nullable
    op.alter_column('project_configs', 'platform',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)

    # Re-add old columns to project_configs
    op.add_column('project_configs', sa.Column('scraper_config', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('project_configs', sa.Column('extract_command', sa.VARCHAR(length=255), nullable=True))
    op.add_column('project_configs', sa.Column('source_url', sa.VARCHAR(length=1023), nullable=True))
    op.add_column('project_configs', sa.Column('build_dir', sa.VARCHAR(length=511), nullable=True))
    op.add_column('project_configs', sa.Column('build_command', sa.TEXT(), nullable=True))
    op.add_column('project_configs', sa.Column('job_name', sa.VARCHAR(length=255), nullable=True))
    op.add_column('project_configs', sa.Column('workflow_file', sa.VARCHAR(length=255), nullable=True))
    op.add_column('project_configs', sa.Column('workflow_name', sa.VARCHAR(length=255), nullable=True))

    # Migrate data back from new tables to old schema
    connection = op.get_bind()

    # Migrate GitHub Actions configs back
    connection.execute(sa.text("""
        UPDATE project_configs pc
        SET
            workflow_file = gac.workflow_file,
            workflow_name = gac.workflow_name,
            job_name = gac.job_name
        FROM github_actions_configs gac
        WHERE pc.id = gac.config_id
    """))

    # Migrate LUCI configs back
    connection.execute(sa.text("""
        UPDATE project_configs pc
        SET scraper_config = jsonb_build_object(
            'project', lc.project_name,
            'bucket', lc.bucket,
            'builder', lc.builder
        )
        FROM luci_configs lc
        WHERE pc.id = lc.config_id
    """))

    # Migrate Buildkite configs back
    connection.execute(sa.text("""
        UPDATE project_configs pc
        SET scraper_config = jsonb_build_object(
            'org_slug', bc.org_slug,
            'pipeline_slug', bc.pipeline_slug
        )
        FROM buildkite_configs bc
        WHERE pc.id = bc.config_id
    """))

    # Drop data_source index
    op.drop_index('idx_configs_data_source', table_name='project_configs')

    # Drop new tables
    op.drop_index('idx_buildkite_config', table_name='buildkite_configs')
    op.drop_table('buildkite_configs')
    op.drop_index('idx_luci_config', table_name='luci_configs')
    op.drop_table('luci_configs')
    op.drop_index('idx_gh_actions_config', table_name='github_actions_configs')
    op.drop_table('github_actions_configs')
