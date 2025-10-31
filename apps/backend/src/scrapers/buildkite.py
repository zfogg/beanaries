"""Scraper for Buildkite CI builds."""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from firecrawl import Firecrawl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Build, DataSource, Platform, Project, ProjectConfig


class BuildkiteScraper:
    """Scraper for Buildkite CI builds."""

    def __init__(self, api_token: str | None = None):
        """Initialize Buildkite scraper.

        Args:
            api_token: Buildkite API access token (optional, for private builds)
        """
        self.api_token = api_token
        self.base_url = "https://api.buildkite.com/v2"
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "Beanaries/0.1.0",
        }
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    async def list_builds(
        self,
        org_slug: str,
        pipeline_slug: str,
        limit: int | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List builds for a pipeline with pagination support.

        Args:
            org_slug: Organization slug (e.g., "bazel" from github.com/bazelbuild/bazel)
            pipeline_slug: Pipeline slug (e.g., "bazel-bazel")
            limit: Maximum number of builds to fetch (None = unlimited)
            page_size: Number of builds per page (max 100 per API docs)

        Returns:
            List of build dictionaries from Buildkite API
        """
        url = f"{self.base_url}/organizations/{org_slug}/pipelines/{pipeline_slug}/builds"
        all_builds = []
        page = 1

        async with httpx.AsyncClient() as client:
            while limit is None or len(all_builds) < limit:
                # Calculate how many builds to fetch in this page
                if limit is None:
                    current_page_size = min(page_size, 100)  # API max is 100
                else:
                    remaining = limit - len(all_builds)
                    current_page_size = min(page_size, remaining, 100)

                params = {
                    "page": page,
                    "per_page": current_page_size,
                }

                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=60.0,
                )
                response.raise_for_status()

                builds = response.json()
                if not builds:
                    break  # No more builds

                all_builds.extend(builds)

                # Log progress
                if len(all_builds) % 100 == 0 or len(builds) < current_page_size:
                    print(f"  Progress: {len(all_builds)} builds fetched...")

                # Check if there are more pages
                if len(builds) < current_page_size:
                    break  # No more pages

                page += 1

        return all_builds

    async def list_builds_from_web(
        self,
        org_slug: str,
        pipeline_slug: str,
        branch: str = "master",
        limit: int | None = None,
        scroll_count: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Scrape builds from public Buildkite pipeline pages using Firecrawl.

        This method extracts build data from the public web interface,
        which is accessible without organization membership. Uses pagination
        to load multiple pages of builds from a specific branch.

        Args:
            org_slug: Organization slug
            pipeline_slug: Pipeline slug
            branch: Branch name to filter builds (default: "master")
            limit: Maximum number of builds to fetch (None = unlimited)
            scroll_count: Number of times to paginate (default: 5)
                         Each page loads ~20 builds

        Returns:
            List of build dictionaries extracted from web page
        """
        if not settings.firecrawl_api_key:
            raise ValueError("FIRECRAWL_API_KEY is required for web scraping")

        # Scrape branch-specific page to get more builds per page
        base_url = f"https://buildkite.com/{org_slug}/{pipeline_slug}/builds"

        # Use Firecrawl to scrape the page
        app = Firecrawl(api_key=settings.firecrawl_api_key)

        try:
            # Scrape multiple pages using URL pagination
            # Buildkite uses ?branch=X&page=N for pagination
            all_builds = []

            for page_num in range(1, scroll_count + 1):
                page_url = f"{base_url}?branch={branch}&page={page_num}"

                print(f"  Scraping page {page_num} (branch: {branch})...")

                # Scrape with markdown format (no scrolling needed with URL pagination)
                result = app.scrape(
                    page_url,
                    formats=["markdown"]
                )

                # Extract build data from markdown
                markdown = result.markdown or ""

                # New pattern to match actual markdown format from Firecrawl:
                # [Title\\
                # \\
                # #BUILD_NUM](URL)
                # ...
                # Author\n·\n
                # [branch](branch_url) [GitHub Icon\\
                # COMMIT_SHA](commit_url)

                # First extract all build links
                build_link_pattern = r'\[([^\]]+)\\+\s*#(\d+)\]\((https://buildkite\.com/[^)]+/builds/\d+)\)'
                build_links = list(re.finditer(build_link_pattern, markdown))

                page_builds = []
                for i, link_match in enumerate(build_links):
                    title = link_match.group(1).strip()
                    build_number = link_match.group(2)
                    build_url = link_match.group(3)

                    # Extract build ID from URL
                    build_id_match = re.search(r'/builds/(\d+)', build_url)
                    build_id = build_id_match.group(1) if build_id_match else build_number

                    # Find the GitHub Icon link after this build link
                    # Pattern: [GitHub Icon\\nCOMMIT_SHA](commit_url)
                    github_icon_pattern = r'\[GitHub Icon\\+\s*([a-f0-9]{6,})\]\(https://github\.com/[^)]+/commit/([a-f0-9]{40})\)'

                    # Search for GitHub Icon in the text after this build link
                    search_start = link_match.end()
                    # Limit search to next 1000 chars to avoid matching wrong build's commit
                    search_end = min(search_start + 1000, len(markdown))
                    search_text = markdown[search_start:search_end]

                    commit_match = re.search(github_icon_pattern, search_text)
                    if commit_match:
                        commit_sha = commit_match.group(2)  # Full 40-char SHA
                    else:
                        # Fallback: try shorter SHA pattern
                        commit_short_pattern = r'\[GitHub Icon\\+\s*([a-f0-9]{6,})\]'
                        commit_short_match = re.search(commit_short_pattern, search_text)
                        if commit_short_match:
                            commit_sha = commit_short_match.group(1)  # Short SHA
                        else:
                            # Skip builds without commit info
                            continue

                    # Try to extract author name (appears before the ·)
                    # Look for pattern: \n\nAuthor Name\n·\n
                    author_pattern = r'\n\n([^\n]+)\n·\n'
                    author_match = re.search(author_pattern, search_text)
                    author = author_match.group(1).strip() if author_match else None

                    page_builds.append({
                        "id": build_id,
                        "number": int(build_number),
                        "message": title,
                        "commit": commit_sha,
                        "branch": branch,
                        "web_url": build_url,
                        "state": "passed",  # We'll assume passed for now
                        "creator": {"name": author} if author else None,
                        "started_at": None,  # Not available in list view
                        "finished_at": None,  # Not available in list view
                        "created_at": None,  # Not available in list view
                        "jobs": [],  # Not available in list view
                    })

                if not page_builds:
                    print(f"    No builds found on page {page_num}, stopping pagination")
                    break  # No more builds, stop paginating

                print(f"    Found {len(page_builds)} builds on page {page_num}")
                all_builds.extend(page_builds)

                # Check if we've reached the limit
                if limit and len(all_builds) >= limit:
                    all_builds = all_builds[:limit]
                    print(f"    Reached limit of {limit} builds")
                    break

            if not all_builds:
                print(f"  Warning: No builds found for {org_slug}/{pipeline_slug} (branch: {branch})")
                return []

            print(f"  Scraped total of {len(all_builds)} builds from {page_num} page(s)")

            return all_builds

        except Exception as e:
            print(f"  Error scraping with Firecrawl: {e}")
            import traceback
            traceback.print_exc()
            return []

    def parse_platform_from_agent_query(self, build_data: dict[str, Any]) -> Platform:
        """Parse platform from build metadata or jobs."""
        # Try to determine platform from jobs
        jobs = build_data.get("jobs", [])
        for job in jobs:
            if job.get("type") != "script":
                continue

            # Check agent query rules
            agent_query_rules = job.get("agent_query_rules", [])
            for rule in agent_query_rules:
                if "os" in rule.lower() or "platform" in rule.lower():
                    rule_lower = rule.lower()
                    if "linux" in rule_lower or "ubuntu" in rule_lower:
                        return Platform.UBUNTU_LATEST
                    elif "mac" in rule_lower or "darwin" in rule_lower:
                        return Platform.MACOS_LATEST
                    elif "win" in rule_lower or "windows" in rule_lower:
                        return Platform.WINDOWS_LATEST

        # Default fallback
        return Platform.UBUNTU_LATEST

    def calculate_duration_from_times(
        self,
        started_at: str | None,
        finished_at: str | None,
    ) -> int | None:
        """Calculate duration in seconds from ISO8601 timestamps."""
        if not started_at or not finished_at:
            return None

        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            return int((end - start).total_seconds())
        except (ValueError, AttributeError):
            return None

    def is_build_successful(self, state: str) -> bool:
        """Determine if a build was successful based on state."""
        # Buildkite states: passed, failed, blocked, canceled, canceling, skipped, not_run, scheduled, running
        return state == "passed"

    def extract_commit_info(self, build_data: dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract commit SHA and message from build."""
        commit_sha = build_data.get("commit")
        commit_message = build_data.get("message")
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
        Scrape builds for a specific Buildkite configuration.

        Args:
            config: ProjectConfig with scraper_config containing org_slug and pipeline_slug
            project: Project model instance
            db: Database session
            max_builds: Maximum number of builds to fetch (None = unlimited)
            only_new: If True, stop when reaching existing data (default True)

        Returns:
            Number of builds added to database
        """
        # Access Buildkite specific config through relationship
        bk_config = config.buildkite_config
        if not bk_config:
            raise ValueError(f"No Buildkite config found for config {config.id}")

        org_slug = bk_config.org_slug
        pipeline_slug = bk_config.pipeline_slug

        # Get branch from config (use configured branch, not scraper_config)
        branch = config.branch or "master"

        # Get most recent build_id if only_new mode
        most_recent_build_id = None
        if only_new:
            result = await db.execute(
                select(Build.scraper_metadata["build_id"].as_string())
                .where(
                    Build.project_id == project.id,
                    Build.data_source == DataSource.BUILDKITE,
                )
                .order_by(Build.started_at.desc())
                .limit(1)
            )
            most_recent = result.scalar_one_or_none()
            if most_recent:
                most_recent_build_id = most_recent
                print(f"  Most recent build_id in DB: {most_recent_build_id}, will stop when reached")

        # Get pagination configuration (hardcoded for now, can be added to model if needed)
        scroll_count = 5  # Default: 5 pages

        # Fetch builds from Buildkite public web pages (not API, since API requires org membership)
        print(f"Fetching builds from Buildkite web page (branch: {branch}, limit: {'unlimited' if max_builds is None else max_builds}, pages: {scroll_count})...")
        builds = await self.list_builds_from_web(
            org_slug=org_slug,
            pipeline_slug=pipeline_slug,
            branch=branch,
            limit=max_builds,
            scroll_count=scroll_count,
        )
        print(f"Fetched {len(builds)} builds from {scroll_count} page(s)")

        # Note: repo_path validation has been removed. If needed in the future,
        # add a repo_path field to the BuildkiteConfig model.
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
                    f"  Filtered out {invalid_count} builds with commits not in tracked repository"
                )
        elif repo_path:
            print(f"  Warning: Repository path configured but not found: {repo_path}")

        builds_to_add = []

        for build_data in builds:
            build_id = build_data.get("id")
            build_number = build_data.get("number")
            if not build_id:
                continue

            # Early exit if we've reached existing data (only_new mode)
            if only_new and most_recent_build_id and build_id == most_recent_build_id:
                print(f"  Reached existing data (build_id: {build_id}), stopping")
                break

            # Check if we already have this build
            existing = await db.execute(
                select(Build).where(
                    Build.project_id == project.id,
                    Build.scraper_metadata["build_id"].as_string() == build_id,
                )
            )
            if existing.first():
                continue  # Skip if already exists

            # Extract build information
            state = build_data.get("state", "unknown")
            branch = build_data.get("branch", "main")

            # Get timestamps
            started_at = build_data.get("started_at")
            finished_at = build_data.get("finished_at")
            created_at = build_data.get("created_at")

            # Extract commit info
            commit_sha, commit_message = self.extract_commit_info(build_data)

            if not commit_sha:
                continue  # Skip builds without commit info

            # Skip builds with commits not in the tracked repository
            if commit_sha not in valid_commits:
                continue

            # Calculate duration
            duration = self.calculate_duration_from_times(started_at, finished_at)

            # Parse platform
            platform = self.parse_platform_from_agent_query(build_data)

            # Build URL
            build_url = build_data.get("web_url")

            # Get creator info
            creator = build_data.get("creator", {})
            creator_name = creator.get("name") if creator else None

            # Create Build model
            build = Build(
                project_id=project.id,
                commit_sha=commit_sha,
                commit_message=commit_message,
                branch=branch,
                success=self.is_build_successful(state),
                duration_seconds=duration,
                platform=platform,
                runner=f"buildkite-{org_slug}",
                data_source=DataSource.BUILDKITE,
                workflow_name=pipeline_slug,  # Pipeline name as workflow
                workflow_run_id=None,  # Not applicable for Buildkite
                job_id=None,  # Not applicable for Buildkite
                scraper_metadata={
                    "build_id": build_id,
                    "build_number": build_number,
                    "pipeline_slug": pipeline_slug,
                    "org_slug": org_slug,
                    "state": state,
                    "creator": creator_name,
                },
                build_url=build_url,
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

        # Update last checked time
        config.last_checked_at = datetime.now(timezone.utc)
        await db.commit()

        builds_created = len(builds_to_add)

        return builds_created
