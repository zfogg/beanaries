"""Backfill commit messages for Chromium builds using local git repository."""
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update

from src.database import AsyncSessionLocal
from src.models import Build

# Set UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


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
            # Use git cat-file --batch for efficient batch retrieval
            # Format: commit_sha + ":subject" to get just the subject line
            input_data = "\n".join(f"{sha}" for sha in commit_shas) + "\n"

            process = subprocess.Popen(
                ["git", "cat-file", "--batch=%(objectname) %(objecttype) %(rest)"],
                cwd=self.repo_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )

            stdout, stderr = process.communicate(input=input_data, timeout=30)

            if process.returncode != 0:
                # Fallback: get messages one by one
                for sha in commit_shas:
                    try:
                        result = subprocess.run(
                            ["git", "log", "-1", "--format=%s", sha],
                            cwd=self.repo_path,
                            capture_output=True,
                            text=True,
                            timeout=1,
                        )
                        if result.returncode == 0:
                            message = result.stdout.strip()
                            results[sha] = message if message else None
                        else:
                            results[sha] = None
                    except Exception:
                        results[sha] = None
                return results

            # Parse commit data - need to extract subject from commit object
            # Since cat-file doesn't directly give subject, use git log --batch
            # Actually, let's use a single git log command with --stdin
            input_data = "\n".join(commit_shas) + "\n"
            result = subprocess.run(
                ["git", "log", "--stdin", "--no-walk", "--format=%H|||%s"],
                cwd=self.repo_path,
                input=input_data,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
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
            print(f"Error in batch fetch: {e}")
            # Fill with None on error
            for sha in commit_shas:
                results[sha] = None

        return results


async def backfill_commit_messages(
    repo_path: str, batch_size: int = 1000, progress_interval: int = 100
):
    """Backfill commit messages for all Chromium builds using git."""
    print("Starting commit message backfill for Chromium builds using git...")
    print(f"Repository path: {repo_path}")
    print(f"Batch size: {batch_size}")

    fetcher = GitCommitFetcher(repo_path)

    async with AsyncSessionLocal() as db:
        # Get all commit SHAs for Chromium builds without messages
        # Don't use DISTINCT in SQL - deduplicate in Python for better performance
        result = await db.execute(
            select(Build.commit_sha)
            .where(
                Build.project_id == 9,
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
            return

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

            # Fetch commit messages for this batch (synchronous, but fast with local git)
            commit_messages = fetcher.get_commit_messages_batch(batch)

            # Update database using raw SQL with VALUES for maximum efficiency
            # Filter commits that have messages
            valid_updates = [(sha, msg) for sha, msg in commit_messages.items() if msg]

            if valid_updates:
                # Use PostgreSQL UPDATE FROM with VALUES for bulk update
                # This is much faster than CASE statements
                # Use raw connection to bypass SQLAlchemy's bind parameter parsing

                # Build VALUES clause using PostgreSQL dollar-quoted strings
                values_list = ", ".join(
                    f"('{sha}', $${msg}$$)"
                    for sha, msg in valid_updates
                )

                # Raw SQL for bulk update with VALUES
                sql = f"""
                    UPDATE builds
                    SET commit_message = v.message,
                        updated_at = NOW()
                    FROM (VALUES {values_list}) AS v(sha, message)
                    WHERE builds.commit_sha = v.sha
                    AND builds.project_id = 9
                """

                # Execute using raw connection to avoid SQLAlchemy's bind parameter parsing
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
        print(f"\nBackfill complete!")
        print(f"  Updated {total_updated} builds in {elapsed_total:.1f} seconds")
        print(f"  Average speed: {total_commits/elapsed_total:.1f} commits/sec")


if __name__ == "__main__":
    # Use the chromium repository path
    # You'll need to clone it first: git clone --filter=blob:none https://chromium.googlesource.com/chromium/src.git chromium
    repo_path = r"C:\Users\zachf\src\chromium"  # Adjust this path as needed
    asyncio.run(backfill_commit_messages(repo_path, batch_size=1000))
