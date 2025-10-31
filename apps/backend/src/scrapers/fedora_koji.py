"""Scraper for Fedora Koji build system."""
import asyncio
from datetime import datetime, timezone
from typing import Any
from xmlrpc.client import dumps, loads

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Build, DataSource, Platform, Project, ProjectConfig


class FedoraKojiScraper:
    """Scraper for Fedora Koji RPM build system."""

    def __init__(self, koji_url: str = "https://koji.fedoraproject.org/kojihub"):
        """Initialize Fedora Koji scraper.

        Args:
            koji_url: The Koji hub URL (default: Fedora Koji)
        """
        self.koji_url = koji_url
        self.headers = {
            "Content-Type": "text/xml",
            "User-Agent": "Beanaries/0.1.0",
        }

    async def _call_koji_method(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call a Koji XML-RPC method.

        Args:
            method: The Koji API method name
            *args: Method arguments
            **kwargs: Keyword arguments (encoded as __starstar for Koji)

        Returns:
            The method response
        """
        # Encode keyword arguments using Koji's __starstar convention
        if kwargs:
            args = args + ({"__starstar": kwargs},)

        # Build XML-RPC request
        request_data = dumps(args, methodname=method, encoding="utf-8", allow_none=True)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.koji_url,
                headers=self.headers,
                content=request_data,
                timeout=60.0,
            )
            response.raise_for_status()

            # Parse XML-RPC response
            # loads returns a tuple where first element is a tuple of results
            result = loads(response.text)
            if isinstance(result, tuple):
                # result is ((actual_value,), method_name)
                if len(result) > 0 and isinstance(result[0], tuple) and len(result[0]) > 0:
                    return result[0][0]
                elif len(result) > 0:
                    return result[0]
            return result

    def _parse_platform_from_arch(self, arch: str) -> Platform:
        """Parse platform from architecture string."""
        arch_lower = arch.lower()

        if "x86_64" in arch_lower or "amd64" in arch_lower:
            return Platform.UBUNTU_LATEST  # Generic Linux x86_64
        elif "aarch64" in arch_lower or "arm64" in arch_lower:
            return Platform.MACOS_LATEST  # Generic ARM64
        elif "i686" in arch_lower or "i386" in arch_lower:
            return Platform.UBUNTU_LATEST  # Generic Linux x86

        return Platform.UBUNTU_LATEST  # Default fallback

    def _calculate_duration(
        self,
        start_time: float | None,
        completion_time: float | None,
    ) -> int | None:
        """Calculate duration in seconds from Unix timestamps."""
        if not start_time or not completion_time:
            return None

        try:
            return int(completion_time - start_time)
        except (ValueError, TypeError):
            return None

    def _is_build_successful(self, state: int) -> bool:
        """Determine if a build was successful based on Koji build state.

        Koji build states:
        0 = BUILDING
        1 = COMPLETE
        2 = DELETED
        3 = FAILED
        4 = CANCELED
        """
        return state == 1  # COMPLETE

    async def scrape_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
        max_builds: int | None = 100,
        only_new: bool = True,
    ) -> int:
        """
        Scrape builds for a specific Koji package configuration.

        Args:
            config: ProjectConfig with koji_config containing package_name and tag
            project: Project model instance
            db: Database session
            max_builds: Maximum number of builds to fetch (None = unlimited)
            only_new: If True, stop when reaching existing data (default True)

        Returns:
            Number of builds added to database
        """
        # Access Koji specific config through relationship
        koji_config = config.koji_config
        if not koji_config:
            raise ValueError(f"No Koji config found for config {config.id}")

        package_name = koji_config.package_name
        tag = koji_config.tag

        # Get package ID
        try:
            pkg = await self._call_koji_method("getPackage", package_name)
            if not pkg:
                print(f"Package {package_name} not found in Koji")
                return 0
            package_id = pkg["id"]
        except Exception as e:
            print(f"Error getting package {package_name}: {e}")
            return 0

        # Get most recent build_id if only_new mode
        most_recent_build_id = None
        if only_new:
            result = await db.execute(
                select(Build.scraper_metadata["build_id"].as_string())
                .where(
                    Build.project_id == project.id,
                    Build.data_source == DataSource.KOJI,
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_build_id = most_recent
                print(f"  Most recent build_id in DB: {most_recent_build_id}, will stop when reached")

        # Fetch builds from Koji
        print(f"Fetching builds for package {package_name} (limit: {max_builds or 'unlimited'})...")

        # Build query options
        query_opts = {}
        if max_builds:
            query_opts["limit"] = max_builds
        query_opts["order"] = "-build_id"  # Most recent first

        # Call listBuilds - use positional None values for optional params
        # listBuilds signature: packageID, userID, taskID, prefix, state, volumeID, source,
        # createdBefore, createdAfter, completeBefore, completeAfter, type, typeInfo, queryOpts
        builds = await self._call_koji_method(
            "listBuilds",
            package_id,  # packageID
            None,  # userID
            None,  # taskID
            None,  # prefix
            None,  # state
            None,  # volumeID
            None,  # source
            None,  # createdBefore
            None,  # createdAfter
            None,  # completeBefore
            None,  # completeAfter
            None,  # type
            None,  # typeInfo
            query_opts,  # queryOpts
        )

        print(f"Fetched {len(builds)} builds from Koji API")

        builds_to_add = []

        for build_data in builds:
            build_id = build_data.get("build_id")
            if not build_id:
                continue

            # Early exit if we've reached existing data (only_new mode)
            if only_new and most_recent_build_id and str(build_id) == most_recent_build_id:
                print(f"  Reached existing data (build_id: {build_id}), stopping")
                break

            # Check if we already have this build
            existing = await db.execute(
                select(Build).where(
                    Build.project_id == project.id,
                    Build.scraper_metadata["build_id"].as_string() == str(build_id),
                )
            )
            if existing.first():
                continue  # Skip if already exists

            # Extract build information
            state = build_data.get("state")
            nvr = build_data.get("nvr", "")  # Name-Version-Release
            task_id = build_data.get("task_id")

            # Get timestamps (Koji returns ISO format strings, not Unix timestamps)
            start_time_raw = build_data.get("creation_time")
            completion_time_raw = build_data.get("completion_time")

            # Parse ISO format timestamps to datetime objects
            started_at = None
            finished_at = None
            if start_time_raw:
                started_at = datetime.fromisoformat(str(start_time_raw).replace('+00:00', '')).replace(tzinfo=timezone.utc)
            if completion_time_raw:
                finished_at = datetime.fromisoformat(str(completion_time_raw).replace('+00:00', '')).replace(tzinfo=timezone.utc)

            # Calculate duration from datetime objects
            duration = None
            if started_at and finished_at:
                duration = int((finished_at - started_at).total_seconds())

            # Parse platform from build info
            # Note: Koji doesn't provide detailed arch in listBuilds, defaulting to generic Linux
            platform = Platform.UBUNTU_LATEST

            # Build URL
            build_url = f"{self.koji_url.replace('/kojihub', '/koji')}/buildinfo?buildID={build_id}"

            # Get git commit info from source if available
            source = build_data.get("source")
            commit_sha = None
            commit_message = None

            # Try to extract commit from source URL
            # Example source: "git+https://src.fedoraproject.org/rpms/kernel.git#commit_hash"
            if source and "#" in source:
                commit_sha = source.split("#")[-1][:40]  # Get commit hash

            # Create Build model
            build = Build(
                project_id=project.id,
                commit_sha=commit_sha or "unknown",
                commit_message=commit_message,
                branch=config.branch,
                success=self._is_build_successful(state),
                duration_seconds=duration,
                platform=platform,
                runner=f"koji-{package_name}",
                data_source=DataSource.KOJI,
                workflow_name=None,  # Not applicable for Koji
                workflow_run_id=None,  # Not applicable for Koji
                job_id=task_id,  # Store Koji task_id in job_id field
                scraper_metadata={
                    "build_id": str(build_id),
                    "nvr": nvr,
                    "task_id": task_id,
                    "state": state,
                    "package_name": package_name,
                    "tag": tag,
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
