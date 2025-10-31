"""Backfill commit messages from local git repositories.

Usage:
    # Backfill all projects (requires manual configuration)
    uv run python -m src.cli.backfill_commits

    # Backfill specific projects
    uv run python -m src.cli.backfill_commits gcc/gcc rust-lang/rust

    # Specify custom batch size
    uv run python -m src.cli.backfill_commits --batch-size 2000 rust-lang/rust
"""
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

import click
from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import Build, Project


class GitCommitFetcher:
    """Fetches commit messages from a local git repository."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

    def get_commit_messages_batch(
        self, commit_shas: list[str]
    ) -> dict[str, str | None]:
        """Get commit messages for multiple commits using git cat-file --batch."""
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
                timeout=300,  # Increased to 5 minutes for large repos
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
            print(f"Error in batch fetch: {e}")
            # Fill with None on error
            for sha in commit_shas:
                results[sha] = None

        return results


async def backfill_project(
    project: Project,
    repo_path: str,
    batch_size: int = 1000,
):
    """Backfill commit messages for a single project using git.

    Args:
        project: Project model instance
        repo_path: Path to local git repository
        batch_size: Number of commits to process per batch
    """
    print(f"\n=== Starting backfill for {project.full_name} ===")
    print(f"Repository path: {repo_path}")
    print(f"Batch size: {batch_size}")

    fetcher = GitCommitFetcher(repo_path)

    async with AsyncSessionLocal() as db:
        # Get all commit SHAs for this project without messages
        result = await db.execute(
            select(Build.commit_sha)
            .where(
                Build.project_id == project.id,
                Build.commit_message.is_(None),
                Build.commit_sha.isnot(None),
            )
        )
        # Deduplicate using set
        commit_shas = list(set(row[0] for row in result.all()))
        total_commits = len(commit_shas)
        print(f"Found {total_commits} unique commits without messages\n")

        if total_commits == 0:
            print("No commits to update!")
            return 0

        # Process in batches
        total_updated = 0
        start_time = datetime.now()

        for i in range(0, total_commits, batch_size):
            batch = commit_shas[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_commits + batch_size - 1) // batch_size

            print(
                f"Processing batch {batch_num}/{total_batches} ({len(batch)} commits)..."
            )

            # Fetch commit messages for this batch
            commit_messages = fetcher.get_commit_messages_batch(batch)

            # Update database using raw SQL with VALUES for maximum efficiency
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

            # Show progress
            elapsed = (datetime.now() - start_time).total_seconds()
            commits_per_sec = (i + len(batch)) / elapsed if elapsed > 0 else 0
            eta_seconds = (
                (total_commits - (i + len(batch))) / commits_per_sec
                if commits_per_sec > 0
                else 0
            )

            print(
                f"  Updated {updated}/{len(batch)} builds | "
                f"Total: {total_updated}/{total_commits} | "
                f"Speed: {commits_per_sec:.1f} commits/sec | "
                f"ETA: {eta_seconds:.1f}s"
            )

        elapsed_total = (datetime.now() - start_time).total_seconds()
        print(f"\nBackfill complete for {project.full_name}!")
        print(f"  Updated {total_updated} builds in {elapsed_total:.1f} seconds")
        if elapsed_total > 0:
            print(f"  Average speed: {total_commits/elapsed_total:.1f} commits/sec")

        return total_updated


@click.command()
@click.argument("projects", nargs=-1)
@click.option(
    "--batch-size",
    default=1000,
    help="Number of commits to process per batch",
    show_default=True,
)
def main(projects: tuple[str], batch_size: int):
    """Backfill commit messages from local git repositories.

    PROJECTS: Project full names to backfill (e.g., rust-lang/rust).
    If none specified, shows available projects.
    """
    # PROJECT_REPOS maps full_name to local repo path
    # Users should customize this for their setup
    PROJECT_REPOS = {
        "rust-lang/rust": "C:/src/rust",
        "gcc/gcc": "C:/src/gcc",
        "llvm/llvm-project": "C:/src/llvm-project",
        # Add more projects here
    }

    async def run():
        async with AsyncSessionLocal() as db:
            if projects:
                # Backfill specific projects
                for project_name in projects:
                    result = await db.execute(
                        select(Project).where(Project.full_name == project_name)
                    )
                    project = result.scalar_one_or_none()

                    if not project:
                        click.echo(
                            click.style(
                                f"[ERROR] Project not found: {project_name}", fg="red"
                            )
                        )
                        continue

                    if project_name not in PROJECT_REPOS:
                        click.echo(
                            click.style(
                                f"[ERROR] No repository path configured for {project_name}",
                                fg="red",
                            )
                        )
                        click.echo(f"Please add it to PROJECT_REPOS in {__file__}")
                        continue

                    await backfill_project(
                        project, PROJECT_REPOS[project_name], batch_size
                    )
            else:
                # Show available projects when no args provided
                click.echo("No projects specified. Available project mappings:\n")
                for name, path in PROJECT_REPOS.items():
                    result = await db.execute(
                        select(Project).where(Project.full_name == name)
                    )
                    project = result.scalar_one_or_none()
                    if project:
                        click.echo(f"  {name:30} -> {path}")
                    else:
                        click.echo(
                            f"  {name:30} -> {path} {click.style('[NOT IN DATABASE]', fg='yellow')}"
                        )
                click.echo()
                click.echo(
                    "Usage: uv run python -m src.cli.backfill_commits <project-name> [...]"
                )
                click.echo(
                    "Example: uv run python -m src.cli.backfill_commits rust-lang/rust gcc/gcc"
                )

    asyncio.run(run())


if __name__ == "__main__":
    main()
