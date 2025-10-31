"""
Utility functions for scraping operations.

This module provides common utilities for scrapers including:
- GitHub star count updating
- Commit message backfilling from local git repositories
- Repository path mapping for LUCI projects
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Build, DataSource, Project

logger = logging.getLogger(__name__)


# Mapping of LUCI project names to local repository paths
LUCI_REPO_PATHS = {
    "chromium": "repos/chromium",
    "dart": "repos/dart-sdk",
    "flutter": "repos/flutter",
    "fuchsia": "repos/fuchsia",
    "gcc": "repos/gcc",
    "go": "repos/go",
    "llvm": "repos/llvm-googlesource",
    "qemu": "repos/qemu",
    "webrtc": "repos/webrtc",
}


class GitCommitFetcher:
    """Fetches commit messages from a local git repository."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

    def get_commit_messages_batch(
        self, commit_shas: list[str]
    ) -> dict[str, str | None]:
        """
        Get commit messages for multiple commits using git log --stdin.

        Args:
            commit_shas: List of commit SHA hashes

        Returns:
            Dict mapping SHA to commit message (or None if not found)
        """
        if not commit_shas:
            return {}

        results = {}
        try:
            # Use git log with --stdin for batch retrieval
            input_data = "\n".join(commit_shas) + "\n"
            result = subprocess.run(
                ["git", "log", "--stdin", "--no-walk", "--format=%H|||%s"],
                cwd=self.repo_path,
                input=input_data,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "|||" in line:
                        sha, message = line.split("|||", 1)
                        results[sha] = message if message else None

            # Fill in any missing SHAs with None
            for sha in commit_shas:
                if sha not in results:
                    results[sha] = None

        except Exception as e:
            logger.error(f"Error in batch commit fetch: {e}")
            # Fill with None on error
            for sha in commit_shas:
                results[sha] = None

        return results


async def update_github_stars(
    project: Project,
    db: AsyncSession,
    github_token: str | None = None,
) -> int | None:
    """
    Update GitHub star count for a project.

    Args:
        project: The project to update
        db: Database session
        github_token: Optional GitHub API token for higher rate limits

    Returns:
        New star count, or None if update failed
    """
    # Only update for GitHub projects
    if not project.url or "github.com" not in project.url:
        return None

    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Beanaries/0.1.0",
        }
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{project.full_name}",
                headers=headers,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                new_star_count = data["stargazers_count"]

                # Update in database
                project.stars = new_star_count
                await db.commit()

                logger.info(
                    f"Updated stars for {project.full_name}: {new_star_count:,}"
                )
                return new_star_count
            else:
                logger.warning(
                    f"Failed to fetch stars for {project.full_name}: "
                    f"HTTP {response.status_code}"
                )
                return None

    except Exception as e:
        logger.error(f"Error updating stars for {project.full_name}: {e}")
        return None


async def backfill_luci_commit_messages(
    project: Project,
    db: AsyncSession,
    luci_project_name: str,
    batch_size: int = 500,
) -> int:
    """
    Backfill commit messages for LUCI project builds from local git repository.

    Args:
        project: The project to backfill
        db: Database session
        luci_project_name: Name of the LUCI project (e.g., "chromium", "flutter")
        batch_size: Number of commits to process per batch

    Returns:
        Number of builds updated with commit messages
    """
    # Check if we have a local repo for this LUCI project
    repo_path = LUCI_REPO_PATHS.get(luci_project_name)
    if not repo_path:
        logger.debug(
            f"No local repo configured for LUCI project '{luci_project_name}'"
        )
        return 0

    # Check if repo exists
    full_repo_path = Path(repo_path)
    if not full_repo_path.exists():
        logger.debug(
            f"Local repo not found at {repo_path} for LUCI project '{luci_project_name}'"
        )
        return 0

    try:
        fetcher = GitCommitFetcher(full_repo_path)

        # Get all commit SHAs for this project without messages
        result = await db.execute(
            select(Build.commit_sha)
            .where(
                Build.project_id == project.id,
                Build.commit_message.is_(None),
                Build.commit_sha.isnot(None),
                Build.data_source == DataSource.LUCI,
            )
        )

        # Deduplicate using set
        commit_shas = list(set(row[0] for row in result.all()))
        total_commits = len(commit_shas)

        if total_commits == 0:
            return 0

        logger.info(
            f"Backfilling {total_commits} commits for {project.full_name} "
            f"from {repo_path}"
        )

        # Process in batches
        total_updated = 0

        for i in range(0, total_commits, batch_size):
            batch = commit_shas[i : i + batch_size]

            # Fetch commit messages for this batch
            commit_messages = fetcher.get_commit_messages_batch(batch)

            # Update database using raw SQL with VALUES for efficiency
            valid_updates = [(sha, msg) for sha, msg in commit_messages.items() if msg]

            if valid_updates:
                # Build VALUES clause using PostgreSQL dollar-quoted strings
                values_list = ", ".join(
                    f"('{sha}', $${msg}$$)" for sha, msg in valid_updates
                )

                # Raw SQL for bulk update with VALUES
                sql = f"""
                    UPDATE builds
                    SET commit_message = v.message,
                        updated_at = NOW()
                    FROM (VALUES {values_list}) AS v(sha, message)
                    WHERE builds.commit_sha = v.sha
                    AND builds.project_id = {project.id}
                """

                # Execute using raw connection
                conn = await db.connection()
                result = await conn.exec_driver_sql(sql)
                updated = result.rowcount
            else:
                updated = 0

            await db.commit()
            total_updated += updated

        if total_updated > 0:
            logger.info(
                f"Backfilled {total_updated} commit messages for {project.full_name}"
            )

        return total_updated

    except Exception as e:
        logger.error(
            f"Error backfilling commits for {project.full_name} "
            f"(LUCI project '{luci_project_name}'): {e}"
        )
        return 0
