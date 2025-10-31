"""Scraper for GitLab CI/CD pipelines."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Build, DataSource, Platform, Project, ProjectConfig


class GitLabCIScraper:
    """Scraper for GitLab CI/CD pipelines (Mesa 3D, etc.)."""

    def __init__(self, gitlab_host: str = "https://gitlab.freedesktop.org"):
        """Initialize GitLab CI scraper.

        Args:
            gitlab_host: The GitLab instance base URL (e.g., "https://gitlab.freedesktop.org", "https://gitlab.com")
        """
        self.gitlab_host = gitlab_host.rstrip("/")
        self.api_base = f"{self.gitlab_host}/api/v4"
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "Beanaries/0.1.0",
        }

    async def get_project_id(self, project_path: str) -> int:
        """
        Get GitLab project ID from project path.

        Args:
            project_path: Project path (e.g., "mesa/mesa")

        Returns:
            GitLab project ID
        """
        # URL encode the project path
        encoded_path = quote(project_path, safe="")
        url = f"{self.api_base}/projects/{encoded_path}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["id"]

    async def search_pipelines(
        self,
        project_path: str,
        ref: str = "main",
        limit: int | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for pipelines using GitLab API with pagination support.

        Args:
            project_path: GitLab project path (e.g., "mesa/mesa")
            ref: Branch/tag name (e.g., "main", "master")
            limit: Maximum number of pipelines to fetch (None = unlimited)
            page_size: Number of pipelines per page (max 100 per GitLab API)

        Returns:
            List of pipeline dictionaries from GitLab API
        """
        # Get project ID
        project_id = await self.get_project_id(project_path)

        # URL encode the project path for API calls
        encoded_path = quote(project_path, safe="")
        url = f"{self.api_base}/projects/{encoded_path}/pipelines"

        all_pipelines = []
        page = 1

        async with httpx.AsyncClient() as client:
            while limit is None or len(all_pipelines) < limit:
                # Calculate how many pipelines to fetch in this page
                if limit is None:
                    current_page_size = min(page_size, 100)  # API max is 100
                else:
                    remaining = limit - len(all_pipelines)
                    current_page_size = min(page_size, remaining, 100)

                # Build the request parameters
                params = {
                    "ref": ref,
                    "per_page": current_page_size,
                    "page": page,
                    "order_by": "id",
                    "sort": "desc",
                }

                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=60.0,
                )
                response.raise_for_status()

                pipelines = response.json()
                if not pipelines:
                    break  # No more pipelines

                all_pipelines.extend(pipelines)

                # Log progress
                if len(all_pipelines) % 100 == 0:
                    print(f"  Progress: {len(all_pipelines)} pipelines fetched...")

                if len(pipelines) < current_page_size:
                    break  # Last page

                page += 1

        return all_pipelines

    async def get_pipeline_jobs(
        self, project_path: str, pipeline_id: int
    ) -> list[dict[str, Any]]:
        """
        Get all jobs for a specific pipeline.

        Args:
            project_path: GitLab project path (e.g., "mesa/mesa")
            pipeline_id: Pipeline ID

        Returns:
            List of job dictionaries
        """
        encoded_path = quote(project_path, safe="")
        url = f"{self.api_base}/projects/{encoded_path}/pipelines/{pipeline_id}/jobs"

        all_jobs = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                params = {"per_page": 100, "page": page}
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()

                jobs = response.json()
                if not jobs:
                    break

                all_jobs.extend(jobs)

                if len(jobs) < 100:
                    break  # Last page

                page += 1

        return all_jobs

    def parse_platform_from_job(self, job_name: str) -> Platform:
        """Parse platform from GitLab CI job name."""
        job_lower = job_name.lower()

        if "windows" in job_lower or "win" in job_lower:
            return Platform.WINDOWS_LATEST
        elif "macos" in job_lower or "darwin" in job_lower:
            return Platform.MACOS_LATEST
        elif "ubuntu-22" in job_lower:
            return Platform.UBUNTU_22_04
        elif "ubuntu-24" in job_lower:
            return Platform.UBUNTU_24_04
        elif "linux" in job_lower or "debian" in job_lower:
            return Platform.UBUNTU_LATEST

        return Platform.UBUNTU_LATEST  # Default fallback

    def is_build_successful(self, status: str) -> bool:
        """Determine if a build/job was successful based on status."""
        # GitLab CI status values: success, failed, canceled, skipped, manual, etc.
        return status == "success"

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_pipelines: int | None = None,
        only_new: bool = True,
    ) -> int:
        """
        Scrape builds for a specific GitLab CI configuration.

        Args:
            config: ProjectConfig with scraper_config containing project_path, ref, and job_filter
            project: Project model instance
            db: Database session
            max_pipelines: Maximum number of pipelines to fetch (None = unlimited)
            only_new: If True, stop when reaching existing data (default True)

        Returns:
            Number of builds added to database
        """
        # Extract config from JSON field
        scraper_config = config.scraper_config or {}
        project_path = scraper_config.get("project_path")
        ref = scraper_config.get("ref", config.branch)
        job_filter = scraper_config.get("job_filter", "")  # Filter jobs by name substring

        if not project_path:
            raise ValueError(
                f"project_path not specified in scraper_config for project {project.full_name}"
            )

        # Get most recent pipeline_id if only_new mode
        most_recent_pipeline_id = None
        if only_new:
            result = await db.execute(
                select(Build.workflow_run_id)
                .where(
                    Build.project_id == project.id,
                    Build.data_source == DataSource.GITLAB_CI,
                    Build.workflow_run_id.isnot(None),
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_pipeline_id = most_recent
                print(f"  Most recent pipeline_id in DB: {most_recent_pipeline_id}, will stop when reached")

        # Determine GitLab host from project URL
        gitlab_host = self.gitlab_host
        if project.url.startswith("https://gitlab.com"):
            gitlab_host = "https://gitlab.com"

        # Update scraper with correct host
        if gitlab_host != self.gitlab_host:
            self.gitlab_host = gitlab_host
            self.api_base = f"{self.gitlab_host}/api/v4"

        # Fetch pipelines from GitLab API
        print(
            f"Fetching pipelines from GitLab (limit: {'unlimited' if max_pipelines is None else max_pipelines})..."
        )
        pipelines = await self.search_pipelines(
            project_path=project_path,
            ref=ref,
            limit=max_pipelines,
        )
        print(f"Fetched {len(pipelines)} pipelines from API")

        builds_to_add = []

        for pipeline_data in pipelines:
            pipeline_id = pipeline_data.get("id")
            if not pipeline_id:
                continue

            # Early exit if we've reached existing data (only_new mode)
            if only_new and most_recent_pipeline_id and pipeline_id == most_recent_pipeline_id:
                print(f"  Reached existing data (pipeline_id: {pipeline_id}), stopping")
                break

            # Get jobs for this pipeline
            jobs = await self.get_pipeline_jobs(project_path, pipeline_id)

            # Filter jobs if job_filter is specified
            if job_filter:
                jobs = [j for j in jobs if job_filter.lower() in j.get("name", "").lower()]

            for job_data in jobs:
                job_id = job_data.get("id")
                if not job_id:
                    continue

                # Check if we already have this build
                existing = await db.execute(
                    select(Build).where(
                        Build.project_id == project.id,
                        Build.scraper_metadata["job_id"].as_string() == str(job_id),
                    )
                )
                if existing.first():
                    continue  # Skip if already exists

                # Extract job information
                status = job_data.get("status", "unknown")
                job_name = job_data.get("name", "")

                # Get timestamps (ISO 8601 format)
                created_at = job_data.get("created_at")
                started_at = job_data.get("started_at")
                finished_at = job_data.get("finished_at")

                # Extract commit info from pipeline
                commit_sha = pipeline_data.get("sha")

                if not commit_sha:
                    continue  # Skip jobs without commit info

                # Get commit message if available
                commit = pipeline_data.get("commit") or {}
                commit_message = commit.get("title") or commit.get("message")

                # Calculate duration
                duration = job_data.get("duration")  # Duration in seconds

                # Parse platform
                platform = self.parse_platform_from_job(job_name)

                # Build URL
                job_url = job_data.get("web_url")

                # Create Build model
                build = Build(
                    project_id=project.id,
                    commit_sha=commit_sha,
                    commit_message=commit_message,
                    branch=ref,
                    success=self.is_build_successful(status),
                    duration_seconds=duration,
                    platform=platform,
                    runner=job_data.get("runner", {}).get("description") if job_data.get("runner") else None,
                    data_source=DataSource.GITLAB_CI,
                    workflow_name=None,  # Not applicable for GitLab CI
                    workflow_run_id=pipeline_id,  # Store pipeline ID
                    job_id=None,  # Not applicable
                    scraper_metadata={
                        "pipeline_id": str(pipeline_id),
                        "job_id": str(job_id),
                        "job_name": job_name,
                        "status": status,
                        "stage": job_data.get("stage"),
                    },
                    build_url=job_url,
                    started_at=(
                        datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        if started_at
                        else None
                    ),
                    finished_at=(
                        datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                        if finished_at
                        else None
                    ),
                )

                builds_to_add.append(build)

        # Add all builds at once
        if builds_to_add:
            db.add_all(builds_to_add)

        # Update last checked time and commit
        config.last_checked_at = datetime.now(timezone.utc)
        await db.commit()

        builds_created = len(builds_to_add)

        return builds_created

    async def scrape_all_configs(self, db: AsyncSession) -> dict[str, int]:
        """Scrape all enabled GitLab CI configurations."""
        # Get all enabled configs for GitLab CI projects
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == DataSource.GITLAB_CI,
                Project.is_active == True,
            )
        )

        configs_projects = result.all()
        stats = {"total_configs": len(configs_projects), "total_builds": 0, "errors": 0}

        for config, project in configs_projects:
            # Check if we should scrape this config
            if config.last_checked_at:
                time_since_check = datetime.now(timezone.utc) - config.last_checked_at
                if time_since_check < timedelta(hours=config.check_interval_hours):
                    continue

            try:
                builds_count = await self.scrape_config(config, project, db)
                stats["total_builds"] += builds_count
                print(f"Scraped {builds_count} builds for {project.full_name}")
            except Exception as e:
                stats["errors"] += 1
                print(f"Error scraping {project.full_name}: {e}")
                continue

        await db.commit()
        return stats
