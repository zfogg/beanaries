"""Scraper for OpenSUSE Build Service (OBS)."""
import asyncio
from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Build, DataSource, Platform, Project, ProjectConfig


class OpenSuseObsScraper:
    """Scraper for OpenSUSE Build Service (OBS)."""

    def __init__(self, obs_url: str = "https://api.opensuse.org", token: str | None = None, username: str | None = None):
        """Initialize OpenSUSE OBS scraper.

        Args:
            obs_url: The OBS API URL (default: openSUSE OBS)
            token: Optional authentication token (if None, will use settings.opensuse_build_token)
            username: Optional username for Basic Auth (if None, will use settings.opensuse_build_username)
        """
        self.obs_url = obs_url.rstrip("/")
        self.token = token or settings.opensuse_build_token
        self.username = username or settings.opensuse_build_username
        self.headers = {
            "Accept": "application/xml",
            "User-Agent": "Beanaries/0.1.0",
        }
        # Add Authorization header if token is available
        if self.token:
            self.headers["Authorization"] = f"Token {self.token}"

        # Set up Basic Auth if username is provided (with token as password)
        self.auth = None
        if self.username and self.token:
            self.auth = (self.username, self.token)

    def _parse_platform_from_arch(self, arch: str) -> Platform:
        """Parse platform from architecture string."""
        arch_lower = arch.lower()

        if "x86_64" in arch_lower or "amd64" in arch_lower:
            return Platform.UBUNTU_LATEST  # Generic Linux x86_64
        elif "aarch64" in arch_lower or "arm64" in arch_lower:
            return Platform.MACOS_LATEST  # Generic ARM64
        elif "i586" in arch_lower or "i386" in arch_lower:
            return Platform.UBUNTU_LATEST  # Generic Linux x86

        return Platform.UBUNTU_LATEST  # Default fallback

    def _is_build_successful(self, status: str) -> bool:
        """Determine if a build was successful based on OBS build status.

        OBS build states:
        - succeeded: Build completed successfully
        - failed: Build failed
        - building: Currently building
        - scheduled: Scheduled to build
        - dispatching: Being dispatched to builder
        - blocked: Blocked by dependencies
        - excluded: Excluded from building
        - disabled: Disabled
        """
        return status.lower() == "succeeded"

    async def _get_build_history(
        self,
        project: str,
        package: str,
        repository: str | None = None,
        arch: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch build history from OBS API.

        Args:
            project: OBS project name (e.g., "openSUSE:Factory")
            package: Package name (e.g., "kernel-default-base")
            repository: Repository name (e.g., "standard", "snapshot")
            arch: Architecture (e.g., "x86_64", "aarch64")

        Returns:
            List of build history entries
        """
        # Get package revision history using public API (no auth needed for public projects)
        url = f"{self.obs_url}/public/source/{project}/{package}/_history"

        print(f"Fetching build history from: {url}")

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            try:
                # Use public API without authentication for reading public project data
                response = await client.get(url, headers={"Accept": "application/xml", "User-Agent": "Beanaries/0.1.0"})
                response.raise_for_status()
                # Read response body while client is still open
                response_text = response.text
            except httpx.HTTPError as e:
                print(f"Error fetching history for {project}/{package}: {e}")
                return []

        # Parse XML response
        try:
            root = ET.fromstring(response_text)
            history_entries = []

            for revision in root.findall("revision"):
                srcmd5 = revision.find("srcmd5")
                version = revision.find("version")
                revision_num = revision.get("rev")
                time_elem = revision.find("time")
                user = revision.find("user")
                comment = revision.find("comment")

                if srcmd5 is None or time_elem is None:
                    continue

                entry = {
                    "srcmd5": srcmd5.text,
                    "revision": int(revision_num) if revision_num else None,
                    "version": version.text if version is not None else None,
                    "time": int(time_elem.text) if time_elem.text else None,
                    "user": user.text if user is not None else None,
                    "comment": comment.text if comment is not None else None,
                }

                # Skip fetching build status here - too slow to fetch for every revision
                # Build status should be fetched separately if needed for specific revisions
                # if repository and arch:
                #     status = await self._get_build_status(
                #         project, package, repository, arch, srcmd5.text
                #     )
                #     entry["build_status"] = status

                history_entries.append(entry)

            return history_entries

        except ET.ParseError as e:
            print(f"Error parsing XML for {project}/{package}: {e}")
            return []

    async def _get_build_status(
        self,
        project: str,
        package: str,
        repository: str,
        arch: str,
        srcmd5: str | None = None,
    ) -> dict[str, Any] | None:
        """Get build status for a specific package/repo/arch combination.

        Args:
            project: OBS project name
            package: Package name
            repository: Repository name
            arch: Architecture
            srcmd5: Optional source MD5 to get status for specific revision

        Returns:
            Build status information or None
        """
        # Try public API first, fallback to regular API if needed
        urls_to_try = [
            f"{self.obs_url}/public/build/{project}/{repository}/{arch}/{package}/_status",
            f"{self.obs_url}/build/{project}/{repository}/{arch}/{package}/_status",
        ]

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for url in urls_to_try:
                try:
                    response = await client.get(url, headers={"Accept": "application/xml", "User-Agent": "Beanaries/0.1.0"})
                    response.raise_for_status()
                    # Read response body while client is still open
                    response_text = response.text
                    break  # Success, exit loop
                except httpx.HTTPError:
                    continue  # Try next URL
            else:
                return None  # All URLs failed

        try:
            root = ET.fromstring(response_text)
            status_elem = root.find("status")

            if status_elem is None:
                return None

            status = {
                "code": status_elem.get("code"),
                "starttime": status_elem.find("starttime").text if status_elem.find("starttime") is not None else None,
                "endtime": status_elem.find("endtime").text if status_elem.find("endtime") is not None else None,
                "workerid": status_elem.find("workerid").text if status_elem.find("workerid") is not None else None,
            }

            return status

        except ET.ParseError:
            return None

    async def _get_build_log(
        self,
        project: str,
        repository: str,
        arch: str,
        package: str,
    ) -> str | None:
        """Get build log URL (but don't fetch the entire log).

        Args:
            project: OBS project name
            repository: Repository name
            arch: Architecture
            package: Package name

        Returns:
            Build log URL or None
        """
        # OBS build log is at /build/:project/:repository/:arch/:package/_log
        return f"{self.obs_url}/build/{project}/{repository}/{arch}/{package}/_log"

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_builds: int | None = 100,
        only_new: bool = True,
    ) -> int:
        """
        Scrape builds for a specific OBS package configuration.

        Args:
            config: ProjectConfig with obs_config containing project_name, package_name, repository, arch
            project: Project model instance
            db: Database session
            max_builds: Maximum number of builds to fetch (None = unlimited)
            only_new: If True, stop when reaching existing data (default True)

        Returns:
            Number of builds added to database
        """
        # Access OBS specific config through relationship
        obs_config = config.obs_config
        if not obs_config:
            raise ValueError(f"No OBS config found for config {config.id}")

        obs_project = obs_config.project_name
        package_name = obs_config.package_name
        repository = obs_config.repository or "standard"  # Default to "standard" if not specified
        arch = obs_config.arch or "x86_64"  # Default to x86_64 if not specified

        print(f"Fetching builds for {obs_project}/{package_name} ({repository}/{arch})...")

        # Get most recent srcmd5 if only_new mode
        most_recent_srcmd5 = None
        if only_new:
            result = await db.execute(
                select(Build.scraper_metadata["srcmd5"].as_string())
                .where(
                    Build.project_id == project.id,
                    Build.data_source == DataSource.OBS,
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_srcmd5 = most_recent
                print(f"  Most recent srcmd5 in DB: {most_recent_srcmd5[:8]}..., will stop when reached")

        # Fetch build history
        history = await self._get_build_history(obs_project, package_name, repository, arch)

        if not history:
            print(f"No build history found for {obs_project}/{package_name}")
            return 0

        # Reverse to get oldest first, then limit
        history = list(reversed(history))
        if max_builds:
            history = history[-max_builds:]

        print(f"Fetched {len(history)} revisions from OBS API")

        # Batch load all existing srcmd5 values for this project to avoid N+1 queries
        result = await db.execute(
            select(Build.scraper_metadata["srcmd5"].as_string())
            .where(
                Build.project_id == project.id,
                Build.data_source == DataSource.OBS,
            )
        )
        existing_srcmd5s = {row[0] for row in result.all()}
        print(f"  Found {len(existing_srcmd5s)} existing builds in DB")

        builds_to_add = []

        for entry in history:
            srcmd5 = entry.get("srcmd5")
            if not srcmd5:
                continue

            # Early exit if we've reached existing data (only_new mode)
            if only_new and most_recent_srcmd5 and srcmd5 == most_recent_srcmd5:
                print(f"  Reached existing data (srcmd5: {srcmd5[:8]}...), stopping")
                break

            # Check if we already have this build (in-memory lookup)
            if srcmd5 in existing_srcmd5s:
                continue  # Skip if already exists

            # Get build status
            build_status = entry.get("build_status")

            # If no build status, try to fetch it
            if not build_status:
                build_status = await self._get_build_status(
                    obs_project, package_name, repository, arch, srcmd5
                )

            # Determine success status
            status_code = build_status.get("code") if build_status else "unknown"
            success = self._is_build_successful(status_code)

            # Parse timestamps
            time_unix = entry.get("time")
            started_at = None
            finished_at = None
            duration = None

            if time_unix:
                # Revision time is when the source was committed
                started_at = datetime.fromtimestamp(time_unix, tz=timezone.utc)

            # If we have build status with timing
            if build_status:
                starttime = build_status.get("starttime")
                endtime = build_status.get("endtime")

                if starttime:
                    try:
                        started_at = datetime.fromtimestamp(int(starttime), tz=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                if endtime:
                    try:
                        finished_at = datetime.fromtimestamp(int(endtime), tz=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                if started_at and finished_at:
                    duration = int((finished_at - started_at).total_seconds())

            # Parse platform
            platform = self._parse_platform_from_arch(arch)

            # Build URL - link to build results page
            build_url = f"{self.obs_url.replace('api.', 'build.')}/package/show/{obs_project}/{package_name}"

            # Get comment as commit message (truncate to avoid PostgreSQL index size limit)
            commit_message = entry.get("comment")
            if commit_message and len(commit_message) > 2000:
                commit_message = commit_message[:1997] + "..."
            version = entry.get("version")

            # Create Build model
            build = Build(
                project_id=project.id,
                commit_sha=srcmd5[:40],  # Use srcmd5 as commit identifier
                commit_message=commit_message,
                branch=config.branch,
                success=success,
                duration_seconds=duration,
                platform=platform,
                runner=f"obs-{repository}-{arch}",
                data_source=DataSource.OBS,
                workflow_name=None,  # Not applicable for OBS
                workflow_run_id=None,  # Not applicable for OBS
                job_id=entry.get("revision"),  # Store revision number in job_id field
                scraper_metadata={
                    "srcmd5": srcmd5,
                    "revision": entry.get("revision"),
                    "version": version,
                    "obs_project": obs_project,
                    "package_name": package_name,
                    "repository": repository,
                    "arch": arch,
                    "status": status_code,
                    "user": entry.get("user"),
                },
                build_url=build_url,
                started_at=started_at,
                finished_at=finished_at,
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
