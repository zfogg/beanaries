"""
Scheduled scraping service for Beanaries.

This module provides background job scheduling for scraping build data from various
CI/CD platforms. It uses APScheduler to run scraping jobs at regular intervals.

Key features:
- Respects check_interval_hours for each project config
- Only scrapes enabled configs
- Updates last_checked_at timestamps
- Handles multiple data sources (GitHub Actions, LUCI, GitLab CI, Buildkite)
- Graceful error handling per-project to prevent one failure from blocking others
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import AsyncSessionLocal
from .models import DataSource, Project, ProjectConfig
from .scraper_utils import backfill_luci_commit_messages, update_github_stars
from .scrapers.buildkite import BuildkiteScraper
from .scrapers.github_actions import GitHubActionsScraper
from .scrapers.gitlab_ci import GitLabCIScraper
from .scrapers.luci import LUCIScraper

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Manages scheduled scraping jobs for all project configurations."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    async def scrape_all_projects(self) -> None:
        """
        Scrape all enabled project configs that are due for checking.

        This job runs periodically and checks which projects need updating based on:
        - is_enabled flag
        - check_interval_hours setting
        - last_checked_at timestamp
        """
        logger.info("Starting scheduled scrape for all projects")

        try:
            async with AsyncSessionLocal() as db:
                # Get all enabled project configs that are due for checking
                result = await db.execute(
                    select(ProjectConfig, Project)
                    .join(Project)
                    .where(
                        ProjectConfig.is_enabled == True,  # noqa: E712
                        Project.is_active == True,  # noqa: E712
                    )
                )

                configs_projects = result.all()
                logger.info(f"Found {len(configs_projects)} enabled project configs")

                # Filter configs that are due for checking
                now = datetime.now(timezone.utc)
                configs_to_scrape = []

                for config, project in configs_projects:
                    if config.last_checked_at is None:
                        # Never checked, scrape it
                        configs_to_scrape.append((config, project))
                    else:
                        # Check if enough time has passed
                        time_since_check = now - config.last_checked_at
                        check_interval = timedelta(hours=config.check_interval_hours)

                        if time_since_check >= check_interval:
                            configs_to_scrape.append((config, project))

                logger.info(f"Found {len(configs_to_scrape)} configs due for scraping")

                # Scrape each config
                total_builds = 0
                for config, project in configs_to_scrape:
                    try:
                        builds = await self._scrape_config(config, project, db)
                        total_builds += builds
                        logger.info(
                            f"Scraped {builds} builds for {project.full_name} "
                            f"({config.data_source})"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error scraping {project.full_name} "
                            f"({config.data_source}): {e}",
                            exc_info=True,
                        )
                        # Continue with next config despite errors

                logger.info(f"Scheduled scrape complete. Total builds: {total_builds}")

        except Exception as e:
            logger.error(f"Error in scheduled scrape job: {e}", exc_info=True)

    async def _scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
    ) -> int:
        """
        Scrape a single project configuration.

        Args:
            config: The project configuration to scrape
            project: The project this config belongs to
            db: Database session

        Returns:
            Number of builds scraped
        """
        # Select appropriate scraper based on data source
        if config.data_source == DataSource.GITHUB_ACTIONS:
            scraper = GitHubActionsScraper(github_token=settings.github_token)
            builds_scraped = await scraper.scrape_config(
                config=config,
                project=project,
                db=db,
                max_runs=100,  # Limit to 100 most recent runs
                only_new=True,  # Only fetch new builds, stop when reaching existing data
            )

        elif config.data_source == DataSource.LUCI:
            # Get LUCI project name from config
            scraper_config = config.scraper_config or {}
            luci_project = scraper_config.get("project", "chromium")
            scraper = LUCIScraper(project_name=luci_project)
            builds_scraped = await scraper.scrape_config(
                config=config,
                project=project,
                db=db,
                max_builds=1000,  # Limit to 1000 most recent builds
                only_new=True,  # Only fetch new builds, stop when reaching existing data
            )

        elif config.data_source == DataSource.GITLAB_CI:
            # Get GitLab host from config or use default
            scraper_config = config.scraper_config or {}
            gitlab_host = scraper_config.get("gitlab_host", "https://gitlab.freedesktop.org")
            scraper = GitLabCIScraper(gitlab_host=gitlab_host)
            builds_scraped = await scraper.scrape_config(
                config=config,
                project=project,
                db=db,
                max_pipelines=100,  # Limit to 100 most recent pipelines
                only_new=True,  # Only fetch new builds, stop when reaching existing data
            )

        elif config.data_source == DataSource.BUILDKITE:
            scraper = BuildkiteScraper(api_token=settings.buildkite_api_token)
            builds_scraped = await scraper.scrape_config(
                config=config,
                project=project,
                db=db,
                max_builds=100,  # Limit to 100 most recent builds
                only_new=True,  # Only fetch new builds, stop when reaching existing data
            )

        else:
            logger.warning(f"Unsupported data source: {config.data_source}")
            builds_scraped = 0

        # Post-scraping enhancements
        if builds_scraped > 0:
            # Update GitHub stars for the project
            await update_github_stars(
                project=project,
                db=db,
                github_token=settings.github_token,
            )

            # Backfill commit messages for LUCI projects from local repos
            if config.data_source == DataSource.LUCI:
                scraper_config = config.scraper_config or {}
                luci_project = scraper_config.get("project", "chromium")
                await backfill_luci_commit_messages(
                    project=project,
                    db=db,
                    luci_project_name=luci_project,
                    batch_size=500,
                )

        # Update last_checked_at timestamp
        config.last_checked_at = datetime.now(timezone.utc)
        await db.commit()

        return builds_scraped

    async def trigger_scrape_now(self) -> dict[str, Any]:
        """
        Manually trigger a scrape job immediately.

        Returns:
            Dict with status and message
        """
        logger.info("Manual scrape triggered")
        await self.scrape_all_projects()
        return {"status": "completed", "message": "Manual scrape completed"}

    def start(self) -> None:
        """
        Start the scheduler with configured jobs.

        Jobs are scheduled to run:
        - Every 2 hours for the main scraping job
        - Can be adjusted via environment variables if needed
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        # Schedule the main scraping job to run every 2 hours
        self.scheduler.add_job(
            self.scrape_all_projects,
            trigger=IntervalTrigger(hours=2),
            id="scrape_all_projects",
            name="Scrape all enabled project configs",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            coalesce=True,  # If multiple runs are pending, coalesce into one
        )

        self.scheduler.start()
        self.is_running = True
        logger.info("Scraper scheduler started. Jobs will run every 2 hours.")

    def shutdown(self) -> None:
        """Stop the scheduler gracefully."""
        if not self.is_running:
            return

        self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("Scraper scheduler stopped")


# Global scheduler instance
_scheduler: ScraperScheduler | None = None


def get_scheduler() -> ScraperScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ScraperScheduler()
    return _scheduler


async def start_scheduler() -> None:
    """Start the background scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


async def shutdown_scheduler() -> None:
    """Shutdown the background scheduler."""
    scheduler = get_scheduler()
    scheduler.shutdown()


async def trigger_manual_scrape() -> dict[str, Any]:
    """Trigger a manual scrape immediately."""
    scheduler = get_scheduler()
    return await scheduler.trigger_scrape_now()
