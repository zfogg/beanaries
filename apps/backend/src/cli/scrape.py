"""Scrape build data for projects.

Usage:
    # Scrape all projects (new builds only, max 100 per config)
    uv run python -m src.cli.scrape

    # Scrape specific projects
    uv run python -m src.cli.scrape rust-lang/rust gcc/gcc

    # Scrape all available builds
    uv run python -m src.cli.scrape --all

    # Scrape up to 500 builds per config
    uv run python -m src.cli.scrape --max-builds 500

    # Scrape all builds (including old ones we already have)
    uv run python -m src.cli.scrape --no-only-new

    # Scrape only specific data source
    uv run python -m src.cli.scrape --source github
"""
import asyncio

import click
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import AsyncSessionLocal
from src.models import DataSource, Project, ProjectConfig
from src.scrapers.github_actions import GitHubActionsScraper
from src.scrapers.gitlab_ci import GitLabCIScraper


async def get_scraper_for_source(source: DataSource):
    """Get the appropriate scraper instance for a data source."""
    if source == DataSource.GITHUB_ACTIONS:
        from src.scrapers.github_actions import GitHubActionsScraper
        return GitHubActionsScraper()
    elif source == DataSource.BUILDKITE:
        from src.scrapers.buildkite import BuildkiteScraper
        return BuildkiteScraper()
    elif source == DataSource.LUCI:
        from src.scrapers.luci import LUCIScraper
        return LUCIScraper(project_name="")  # project_name will be read from config during scrape
    elif source == DataSource.OBS:
        from src.scrapers.opensuse_obs import OpenSuseObsScraper
        return OpenSuseObsScraper()
    elif source == DataSource.KOJI:
        from src.scrapers.fedora_koji import FedoraKojiScraper
        return FedoraKojiScraper()
    elif source == DataSource.GITLAB_CI:
        from src.scrapers.gitlab_ci import GitLabCIScraper
        return GitLabCIScraper()
    else:
        return None


@click.command()
@click.argument("projects", nargs=-1)
@click.option(
    "--max-builds",
    type=int,
    default=100,
    help="Maximum builds to fetch per config (ignored if --all is set)",
    show_default=True,
)
@click.option(
    "--all",
    "fetch_all",
    is_flag=True,
    help="Fetch all available builds (overrides --max-builds)",
)
@click.option(
    "--only-new/--no-only-new",
    default=True,
    help="Stop when reaching existing data (default: True)",
    show_default=True,
)
@click.option(
    "--source",
    type=click.Choice(
        ["github", "buildkite", "luci", "obs", "koji"], case_sensitive=False
    ),
    help="Only scrape configs for specific data source",
)
def main(
    projects: tuple[str],
    max_builds: int,
    fetch_all: bool,
    only_new: bool,
    source: str | None,
):
    """Scrape build data for projects.

    PROJECTS: Project full names to scrape (e.g., rust-lang/rust).
    If none specified, scrapes all enabled project configs.
    """

    async def run():
        # Convert --all flag
        builds_limit = None if fetch_all else max_builds

        # Convert source string to DataSource enum
        source_filter = None
        if source:
            source_map = {
                "github": DataSource.GITHUB_ACTIONS,
                "buildkite": DataSource.BUILDKITE,
                "luci": DataSource.LUCI,
                "obs": DataSource.OBS,
                "koji": DataSource.KOJI,
            }
            source_filter = source_map[source.lower()]

        async with AsyncSessionLocal() as db:
            # Build query for enabled configs
            query = (
                select(ProjectConfig, Project)
                .join(Project)
                .where(ProjectConfig.is_enabled.is_(True))
            )

            # Filter by project names if specified
            if projects:
                query = query.where(Project.full_name.in_(projects))

            # Filter by data source if specified
            if source_filter:
                query = query.where(ProjectConfig.data_source == source_filter)

            # Load related configs based on data source
            query = query.options(
                selectinload(ProjectConfig.github_actions_config),
                selectinload(ProjectConfig.buildkite_config),
                selectinload(ProjectConfig.luci_config),
                selectinload(ProjectConfig.obs_config),
                selectinload(ProjectConfig.koji_config),
            )

            result = await db.execute(query)
            configs = result.all()

            if not configs:
                click.echo(
                    click.style("No enabled configs found matching criteria", fg="yellow")
                )
                if projects:
                    click.echo(f"Projects specified: {', '.join(projects)}")
                if source_filter:
                    click.echo(f"Source filter: {source}")
                return

            click.echo(
                f"Found {len(configs)} enabled config(s) to scrape"
            )
            if builds_limit:
                click.echo(f"Max builds per config: {builds_limit}")
            else:
                click.echo("Fetching ALL available builds")
            click.echo(f"Only new: {only_new}")
            click.echo()

            total_builds = 0
            successful = 0
            failed = 0

            for config, project in configs:
                # Access all attributes before try/except to avoid detached object issues after rollback
                project_name = project.full_name
                data_source = config.data_source
                platform = config.platform if config.platform else 'N/A'

                click.echo(f"{'=' * 60}")
                click.echo(
                    f"Project: {click.style(project_name, fg='cyan', bold=True)}"
                )
                click.echo(f"Source: {data_source}")
                click.echo(f"Platform: {platform}")
                click.echo()

                try:
                    scraper = await get_scraper_for_source(config.data_source)
                    if not scraper:
                        click.echo(
                            click.style(
                                f"[SKIP] No scraper available for {config.data_source}",
                                fg="yellow",
                            )
                        )
                        continue

                    # Call scraper with appropriate parameter name. GitHub
                    # Actions uses max_runs, GitLab CI uses max_pipelines,
                    # others use max_builds.
                    if isinstance(scraper, GitHubActionsScraper):
                        builds_added = await scraper.scrape_config(
                            config=config,
                            project=project,
                            db=db,
                            max_runs=builds_limit if builds_limit else 100,
                            only_new=only_new,
                        )
                    elif isinstance(scraper, GitLabCIScraper):
                        builds_added = await scraper.scrape_config(
                            config=config,
                            project=project,
                            db=db,
                            max_pipelines=builds_limit,
                            only_new=only_new,
                        )
                    else:
                        builds_added = await scraper.scrape_config(
                            config=config,
                            project=project,
                            db=db,
                            max_builds=builds_limit,
                            only_new=only_new,
                        )

                    total_builds += builds_added
                    successful += 1

                    if builds_added > 0:
                        click.echo(
                            click.style(
                                f"[OK] Added {builds_added} build(s)", fg="green"
                            )
                        )
                    else:
                        click.echo(
                            click.style(
                                "[OK] No new builds (already up to date)", fg="green"
                            )
                        )
                    click.echo()

                    # Commit after each project to avoid losing data
                    await db.commit()

                except Exception as e:
                    failed += 1
                    click.echo(
                        click.style(f"[ERROR] {type(e).__name__}: {e}", fg="red")
                    )
                    click.echo()
                    await db.rollback()

            click.echo(f"{'=' * 60}")
            click.echo(
                click.style(
                    f"Scrape complete! Total: {total_builds} builds added",
                    fg="green",
                    bold=True,
                )
            )
            click.echo(f"Successful: {successful}/{len(configs)}")
            if failed > 0:
                click.echo(click.style(f"Failed: {failed}/{len(configs)}", fg="red"))

    asyncio.run(run())


if __name__ == "__main__":
    main()
