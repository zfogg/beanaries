"""Scraper for LUCI (Buildbucket) builds."""
import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Build, DataSource, Platform, Project, ProjectConfig


class LUCIScraper:
    """Scraper for LUCI Buildbucket builds (Chromium, Fuchsia, Dart, Flutter, WebRTC, V8, etc.)."""

    def __init__(self, project_name: str):
        """Initialize LUCI scraper.

        Args:
            project_name: The LUCI project name (e.g., "chromium", "fuchsia", "dart", "flutter", "webrtc", "v8")
        """
        self.project_name = project_name
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
        limit: int | None = None,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Search for builds using Buildbucket SearchBuilds RPC with pagination support.

        Args:
            bucket: LUCI bucket name (e.g., "ci", "try")
            builder: Builder name (e.g., "Linux Builder")
            limit: Maximum number of builds to fetch (None = unlimited)
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
            while limit is None or len(all_builds) < limit:
                # Calculate how many builds to fetch in this page
                if limit is None:
                    current_page_size = min(page_size, 1000)  # API max is 1000
                else:
                    remaining = limit - len(all_builds)
                    current_page_size = min(page_size, remaining, 1000)  # API max is 1000

                # Build the request payload for SearchBuilds
                request_data = {
                    "predicate": {
                        "builder": {
                            "project": self.project_name,  # LUCI project name
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

                # Log progress
                if len(all_builds) % 1000 == 0 or len(builds) < current_page_size:
                    print(f"  Progress: {len(all_builds)} builds fetched...")

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
        commit_message = gitiles_commit.get("message")  # Commit message (first line)

        return commit_sha, commit_message

    def validate_commits_in_repo(
        self, repo_path: Path, commit_shas: list[str]
    ) -> set[str]:
        """Validate which commits exist in the local repository.

        Args:
            repo_path: Path to git repository
            commit_shas: List of commit SHAs to validate

        Returns:
            Set of commit SHAs that exist in the repository
        """
        if not commit_shas or not repo_path or not repo_path.exists():
            return set()

        valid_commits = set()

        try:
            # Use git cat-file --batch-check to verify commits exist
            # This is much faster than checking each commit individually
            input_data = "\n".join(commit_shas) + "\n"

            result = subprocess.run(
                ["git", "cat-file", "--batch-check"],
                cwd=repo_path,
                input=input_data,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            # Output format: <sha> <type> <size> OR <sha> missing
            for line in result.stdout.strip().split("\n"):
                if line and " missing" not in line:
                    # Extract SHA from first column
                    sha = line.split()[0]
                    if sha in commit_shas:
                        valid_commits.add(sha)

        except Exception as e:
            print(f"Warning: Error validating commits in repository: {e}")
            # Return empty set on error - fail safe by not adding builds

        return valid_commits

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_builds: int | None = None,
        only_new: bool = True,
    ) -> int:
        """
        Scrape builds for a specific LUCI configuration.

        Args:
            config: ProjectConfig with scraper_config containing project_name, bucket, and builder
            project: Project model instance
            db: Database session
            max_builds: Maximum number of builds to fetch (None = unlimited)
            only_new: If True, stop when reaching existing data (default True)

        Returns:
            Number of builds added to database
        """
        # Access LUCI specific config through relationship
        luci_config = config.luci_config
        if not luci_config:
            raise ValueError(f"No LUCI config found for config {config.id}")

        bucket = luci_config.bucket
        builder = luci_config.builder
        luci_project = luci_config.project_name

        # Get most recent build_id if only_new mode
        most_recent_build_id = None
        if only_new:
            result = await db.execute(
                select(Build.scraper_metadata["build_id"].as_string())
                .where(
                    Build.project_id == project.id,
                    Build.data_source == DataSource.LUCI,
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_build_id = most_recent
                print(f"  Most recent build_id in DB: {most_recent_build_id}, will stop when reached")

        # Fetch builds from Buildbucket
        print(f"Fetching builds from LUCI (limit: {'unlimited' if max_builds is None else max_builds})...")
        builds = await self.search_builds(
            bucket=bucket,
            builder=builder,
            limit=max_builds,
        )
        print(f"Fetched {len(builds)} builds from API")

        # Note: repo_path validation has been removed. If needed in the future,
        # add a repo_path field to the LUCIConfig model.
        repo_path = None
        if repo_path:
            repo_path = Path(repo_path)
            if not repo_path.is_absolute():
                # Make relative paths absolute (relative to project root)
                repo_path = Path(__file__).parent.parent.parent / repo_path

        # Extract commit SHAs for validation
        builds_by_commit = {}  # commit_sha -> build_data
        for build_data in builds:
            commit_sha, _ = self.extract_commit_info(build_data)
            if commit_sha:
                builds_by_commit[commit_sha] = build_data

        # Validate commits if repo_path is configured
        valid_commits = set(builds_by_commit.keys())  # Default: all commits are valid
        if repo_path and repo_path.exists():
            print(f"Validating {len(builds_by_commit)} commits against repository...")
            valid_commits = self.validate_commits_in_repo(
                repo_path, list(builds_by_commit.keys())
            )
            invalid_count = len(builds_by_commit) - len(valid_commits)
            if invalid_count > 0:
                print(
                    f"⚠️  Filtered out {invalid_count} builds with commits not in tracked repository"
                )
        elif repo_path:
            print(f"⚠️  Warning: Repository path configured but not found: {repo_path}")

        builds_to_add = []

        for build_data in builds:
            build_id = build_data.get("id")
            if not build_id:
                continue

            # Early exit if we've reached existing data (only_new mode)
            # Note: LUCI build IDs can be very large (int64), so we compare as strings
            if only_new and most_recent_build_id and str(build_id) == most_recent_build_id:
                print(f"  Reached existing data (build_id: {build_id}), stopping")
                break

            # Check if we already have this build
            # Note: Chromium build IDs can be very large (int64), so we compare as strings
            existing = await db.execute(
                select(Build).where(
                    Build.project_id == project.id,
                    Build.scraper_metadata["build_id"].as_string() == str(build_id),
                )
            )
            if existing.first():
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

            # Skip builds with commits not in the tracked repository
            if commit_sha not in valid_commits:
                continue

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
                branch=config.branch,
                success=self.is_build_successful(status),
                duration_seconds=duration,
                platform=platform,
                runner=builder_name,
                data_source=DataSource.LUCI,
                workflow_name=None,  # Not applicable for LUCI
                workflow_run_id=None,  # Not applicable for LUCI
                job_id=None,  # Not applicable for LUCI
                scraper_metadata={
                    "build_id": str(build_id),  # Store as string to handle large int64 values
                    "builder": builder_name,
                    "bucket": bucket,
                    "status": status,
                    "luci_project": luci_project,  # Store the LUCI project name
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
        """Scrape all enabled LUCI configurations."""
        # Get all enabled configs for LUCI projects
        result = await db.execute(
            select(ProjectConfig, Project)
            .join(Project)
            .where(
                ProjectConfig.is_enabled == True,
                ProjectConfig.data_source == DataSource.LUCI,
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
