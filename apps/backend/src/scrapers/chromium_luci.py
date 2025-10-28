"""Scraper for Chromium LUCI (Buildbucket) builds."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Build, DataSource, Platform, Project, ProjectConfig


class ChromiumLUCIScraper:
    """Scraper for Chromium LUCI Buildbucket builds."""

    def __init__(self):
        self.base_url = "https://cr-buildbucket.appspot.com"
        self.prpc_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Beanaries/0.1.0",
        }

    async def search_builds(
        self,
        bucket: str,
        builder: str,
        limit: int = 100,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for builds using Buildbucket SearchBuilds RPC with pagination support.

        Args:
            bucket: LUCI bucket name (e.g., "ci", "try")
            builder: Builder name (e.g., "Linux Builder")
            limit: Maximum number of builds to fetch (total across all pages)
            page_size: Number of builds per page (max 1000 per API docs)

        Returns:
            List of build dictionaries from Buildbucket API
        """
        # Buildbucket uses pRPC protocol
        # The SearchBuilds endpoint is at /prpc/buildbucket.v2.Builds/SearchBuilds
        url = f"{self.base_url}/prpc/buildbucket.v2.Builds/SearchBuilds"

        all_builds = []
        page_token = None

        async with httpx.AsyncClient() as client:
            while len(all_builds) < limit:
                # Calculate how many builds to fetch in this page
                remaining = limit - len(all_builds)
                current_page_size = min(page_size, remaining, 1000)  # API max is 1000

                # Build the request payload for SearchBuilds
                request_data = {
                    "predicate": {
                        "builder": {
                            "project": "chromium",  # Chromium project
                            "bucket": bucket,
                            "builder": builder,
                        }
                    },
                    "page_size": current_page_size,
                    # Request specific fields to reduce response size
                    "fields": "builds.*.id,builds.*.builder,builds.*.status,builds.*.create_time,builds.*.start_time,builds.*.end_time,builds.*.input,builds.*.infra,nextPageToken"
                }

                if page_token:
                    request_data["page_token"] = page_token

                response = await client.post(
                    url,
                    headers=self.prpc_headers,
                    json=request_data,
                    timeout=60.0,
                )
                response.raise_for_status()

                # pRPC responses are JSON with first line being a XSSI protection
                # Format: )]}'\n{actual json}
                text = response.text
                if text.startswith(")]}'"):
                    text = text[4:].strip()

                data = json.loads(text) if text else {}
                builds = data.get("builds", [])
                all_builds.extend(builds)

                # Check if there are more pages
                page_token = data.get("nextPageToken")
                if not page_token or len(builds) == 0:
                    break  # No more pages

        return all_builds

    def parse_platform_from_builder(self, builder_name: str) -> Platform:
        """Parse platform from Chromium builder name."""
        builder_lower = builder_name.lower()

        if "linux" in builder_lower:
            return Platform.UBUNTU_LATEST
        elif "mac" in builder_lower:
            return Platform.MACOS_LATEST
        elif "win" in builder_lower:
            return Platform.WINDOWS_LATEST

        return Platform.UBUNTU_LATEST  # Default fallback

    def calculate_duration_from_times(
        self,
        start_time: str | None,
        end_time: str | None,
    ) -> int | None:
        """Calculate duration in seconds from RFC3339 timestamps."""
        if not start_time or not end_time:
            return None

        try:
            # Buildbucket uses RFC3339 timestamps
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            return int((end - start).total_seconds())
        except (ValueError, AttributeError):
            return None

    def is_build_successful(self, status: str) -> bool:
        """Determine if a build was successful based on status."""
        # Buildbucket status values: SUCCESS, FAILURE, INFRA_FAILURE, CANCELED
        return status == "SUCCESS"

    def extract_commit_info(self, build: dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract commit SHA and message from build input."""
        # Chromium builds have gitiles commits in input.gitilesCommit (camelCase)
        input_data = build.get("input", {})
        gitiles_commit = input_data.get("gitilesCommit", {})

        commit_sha = gitiles_commit.get("id")  # Git commit hash
        # Commit message not always available in SearchBuilds, may need GetBuild
        commit_message = None

        return commit_sha, commit_message

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_builds: int = 5000,
    ) -> int:
        """
        Scrape builds for a specific Chromium LUCI configuration.

        Args:
            config: ProjectConfig with scraper_config containing bucket and builder
            project: Project model instance
            db: Database session
            max_builds: Maximum number of builds to fetch (default 5000)

        Returns:
            Number of builds added to database
        """
        # Extract config from JSON field
        scraper_config = config.scraper_config or {}
        bucket = scraper_config.get("bucket", "ci")
        builder = scraper_config.get("builder")

        if not builder:
            raise ValueError(f"Builder not specified in scraper_config for project {project.full_name}")

        # Fetch builds from Buildbucket
        builds = await self.search_builds(
            bucket=bucket,
            builder=builder,
            limit=max_builds,
        )

        builds_to_add = []

        for build_data in builds:
            build_id = build_data.get("id")
            if not build_id:
                continue

            # Check if we already have this build
            # Note: Chromium build IDs can be very large (int64), so we compare as strings
            existing = await db.execute(
                select(Build).where(
                    Build.project_id == project.id,
                    Build.scraper_metadata["build_id"].as_string() == str(build_id),
                )
            )
            if existing.scalar_one_or_none():
                continue  # Skip if already exists

            # Extract build information
            status = build_data.get("status", "UNKNOWN")
            builder_info = build_data.get("builder", {})
            builder_name = builder_info.get("builder", builder)

            # Get timestamps (API returns camelCase)
            start_time = build_data.get("startTime")
            end_time = build_data.get("endTime")
            create_time = build_data.get("createTime")

            # Extract commit info
            commit_sha, commit_message = self.extract_commit_info(build_data)

            if not commit_sha:
                continue  # Skip builds without commit info

            # Calculate duration
            duration = self.calculate_duration_from_times(start_time, end_time)

            # Parse platform
            platform = self.parse_platform_from_builder(builder_name)

            # Build URL - construct from build ID
            build_url = f"https://ci.chromium.org/b/{build_id}"

            # Create Build model
            build = Build(
                project_id=project.id,
                commit_sha=commit_sha,
                commit_message=commit_message,
                branch=config.branch,  # Chromium uses 'main' or 'master'
                success=self.is_build_successful(status),
                duration_seconds=duration,
                platform=platform,
                runner=builder_name,
                data_source=DataSource.CHROMIUM_LUCI,
                workflow_name=None,  # Not applicable for LUCI
                workflow_run_id=None,  # Not applicable for LUCI
                job_id=None,  # Not applicable for LUCI
                scraper_metadata={
                    "build_id": str(build_id),  # Store as string to handle large int64 values
                    "builder": builder_name,
                    "bucket": bucket,
                    "status": status,
                },
                build_url=build_url,
                started_at=(
                    datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    if start_time
                    else None
                ),
                finished_at=(
                    datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    if end_time
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
        """Scrape all enabled Chromium LUCI configurations."""
        # Get all enabled configs for Chromium LUCI
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == DataSource.CHROMIUM_LUCI,
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
