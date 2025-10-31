import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Build, DataSource, Platform, Project, ProjectConfig
from ..schemas import BuildCreate


class GitHubActionsScraper:
    """Scraper for GitHub Actions workflow runs."""

    def __init__(self, github_token: str | None = None):
        self.github_token = github_token or settings.github_token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Beanaries/0.1.0",
        }
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

    async def fetch_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: str | None = None,
        branch: str = "main",
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch workflow runs from GitHub Actions API."""
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs"

        params: dict[str, Any] = {
            "branch": branch,
            "per_page": per_page,
        }

        if workflow_id:
            # If workflow_id is provided, fetch for specific workflow
            url = f"{self.base_url}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("workflow_runs", [])

    async def fetch_workflow_jobs(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> list[dict[str, Any]]:
        """Fetch jobs for a specific workflow run."""
        url = f"{self.base_url}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("jobs", [])

    def parse_platform_from_labels(self, labels: list[str]) -> Platform:
        """Parse platform from runner labels array."""
        if not labels:
            return Platform.UBUNTU_LATEST

        # Convert all labels to lowercase for case-insensitive matching
        labels_lower = [label.lower() for label in labels]
        labels_str = " ".join(labels_lower)

        # Check for Windows
        if any("windows" in label for label in labels_lower):
            if "windows-2022" in labels_lower or "2022" in labels_str:
                return Platform.WINDOWS_2022
            return Platform.WINDOWS_LATEST

        # Check for macOS
        if any("macos" in label or "mac" in label for label in labels_lower):
            if "macos-13" in labels_lower or "macos-13.0" in labels_lower:
                return Platform.MACOS_13
            elif "macos-14" in labels_lower or "macos-14.0" in labels_lower:
                return Platform.MACOS_14
            return Platform.MACOS_LATEST

        # Check for Ubuntu
        if any("ubuntu" in label for label in labels_lower):
            if "ubuntu-22.04" in labels_lower or "22.04" in labels_str:
                return Platform.UBUNTU_22_04
            elif "ubuntu-24.04" in labels_lower or "24.04" in labels_str:
                return Platform.UBUNTU_24_04
            return Platform.UBUNTU_LATEST

        # Default to Ubuntu if no specific platform found
        return Platform.UBUNTU_LATEST

    def calculate_duration(self, started_at: str | None, completed_at: str | None) -> int | None:
        """Calculate duration in seconds from timestamps."""
        if not started_at or not completed_at:
            return None

        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            return int((end - start).total_seconds())
        except (ValueError, AttributeError):
            return None

    def _filter_build_jobs(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out non-build jobs (linting, formatting, validation, etc)."""
        # Exclusion patterns for job names - be conservative to avoid excluding real builds
        exclude_patterns = [
            "lint", "linting",
            "format", "formatting", "prettier",
            "eslint", "flake8", "mypy",
            "type-check", "type check",
            "clippy", "rustfmt",
            "spell", "spellcheck",
            "style check", "code style",
            "dead-code", "unused",
            # Only filter very specific doc/setup jobs
            "documentation only", "docs only", "generate docs",
            "code formatting",
        ]

        filtered_jobs = []
        for job in jobs:
            job_name = job.get("name", "").lower()

            # Skip if name contains exclusion patterns
            if any(pattern in job_name for pattern in exclude_patterns):
                continue

            # Calculate duration to filter out very short jobs
            duration = self.calculate_duration(
                job.get("started_at"),
                job.get("completed_at"),
            )

            # Skip SUCCESSFUL jobs that completed in less than 15 seconds (likely not builds)
            # Reduced from 30s to catch more real builds
            # Keep failed builds regardless of duration as they indicate broken builds
            if duration is not None and duration < 15 and job.get("conclusion") == "success":
                continue

            # Skip jobs that haven't started or completed
            if not job.get("started_at") or not job.get("completed_at"):
                continue

            filtered_jobs.append(job)

        return filtered_jobs

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_runs: int = 100,
        only_new: bool = True,
    ) -> int:
        """Scrape builds for a specific project configuration.

        Args:
            config: ProjectConfig to scrape
            project: Project model instance
            db: Database session
            max_runs: Maximum runs to fetch from API
            only_new: If True, stop when reaching existing data (default True)
        """
        owner = project.owner
        repo = project.name

        # Access GitHub Actions specific config through relationship
        gh_config = config.github_actions_config
        if not gh_config:
            raise ValueError(f"No GitHub Actions config found for config {config.id}")

        workflow_file = gh_config.workflow_file
        job_name = gh_config.job_name

        # Get most recent workflow_run_id if only_new mode
        most_recent_run_id = None
        if only_new:
            result = await db.execute(
                select(Build.workflow_run_id)
                .where(
                    Build.project_id == project.id,
                    Build.workflow_run_id.isnot(None),
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_run_id = most_recent
                print(f"  Most recent run_id in DB: {most_recent_run_id}, will stop when reached")

        # Fetch workflow runs
        runs = await self.fetch_workflow_runs(
            owner=owner,
            repo=repo,
            workflow_id=workflow_file,
            branch=config.branch,
            per_page=max_runs,
        )

        builds_to_add = []

        for run in runs:
            run_id = run["id"]
            commit_sha = run["head_sha"]

            # Early exit if we've reached existing data (only_new mode)
            if only_new and most_recent_run_id and run_id == most_recent_run_id:
                print(f"  Reached existing data (run_id: {run_id}), stopping")
                break

            # Fetch jobs for this run
            jobs = await self.fetch_workflow_jobs(owner, repo, run_id)

            # Filter jobs if job_name is specified
            if job_name:
                jobs = [j for j in jobs if j["name"] == job_name]
            else:
                # Filter out non-build jobs
                jobs = self._filter_build_jobs(jobs)

            # Process each job
            for job in jobs:
                # Check if we already have this specific job
                existing = await db.execute(
                    select(Build).where(
                        Build.project_id == project.id,
                        Build.workflow_run_id == run_id,
                        Build.job_id == job["id"],
                    )
                )
                if existing.first():
                    continue  # Skip if already exists
                platform = self.parse_platform_from_labels(job.get("labels", []))
                duration = self.calculate_duration(
                    job.get("started_at"),
                    job.get("completed_at"),
                )

                build = Build(
                    project_id=project.id,
                    commit_sha=commit_sha,
                    commit_message=run.get("head_commit", {}).get("message", "")[:500],
                    branch=config.branch,
                    success=job["conclusion"] == "success",
                    duration_seconds=duration,
                    platform=platform,
                    runner=job.get("runner_name"),
                    data_source=DataSource.GITHUB_ACTIONS,
                    workflow_name=run["name"],
                    workflow_run_id=run_id,
                    job_id=job["id"],
                    build_url=job["html_url"],
                    started_at=(
                        datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
                        if job.get("started_at")
                        else None
                    ),
                    finished_at=(
                        datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
                        if job.get("completed_at")
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
        """Scrape all enabled GitHub Actions configurations."""
        # Get all enabled configs with eager loading
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .options(selectinload(ProjectConfig.github_actions_config))
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == DataSource.GITHUB_ACTIONS,
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
