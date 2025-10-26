import asyncio
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Build, DataSource, Platform, Project, ProjectConfig


class LocalBuilder:
    """Build projects locally to measure compile times."""

    def __init__(self, workspace_dir: str | None = None):
        self.workspace_dir = Path(workspace_dir or tempfile.gettempdir()) / "beanaries-builds"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    async def clone_or_update_repo(
        self,
        git_url: str,
        owner: str,
        repo: str,
        branch: str
    ) -> Path:
        """Clone or update a git repository from any git URL."""
        repo_path = self.workspace_dir / owner / repo

        if repo_path.exists():
            # Update existing repo
            await asyncio.create_subprocess_exec(
                "git",
                "fetch",
                "origin",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                branch,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.create_subprocess_exec(
                "git",
                "pull",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # Clone new repo
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Cloning {git_url} to {repo_path}...")
            proc = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--branch",
                branch,
                "--single-branch",
                git_url,
                str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                raise RuntimeError(f"Git clone failed: {error_msg}")
            print(f"  Clone complete")

        return repo_path

    async def download_and_extract_source(
        self,
        source_url: str,
        extract_command: str,
        owner: str,
        name: str,
    ) -> tuple[Path, str]:
        """Download and extract source archive.

        Returns: (extracted_path, version_hash)
        """
        import hashlib

        # Use URL hash as version identifier
        version_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]

        download_dir = self.workspace_dir / owner / name / version_hash
        download_dir.mkdir(parents=True, exist_ok=True)

        # Determine filename from URL
        filename = source_url.split('/')[-1]
        download_path = download_dir / filename

        # Download if not already cached
        if not download_path.exists():
            proc = await asyncio.create_subprocess_exec(
                "wget",
                "-O",
                str(download_path),
                source_url,
                cwd=download_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        # Extract
        proc = await asyncio.create_subprocess_shell(
            f"{extract_command} {filename}",
            cwd=download_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        return download_dir, version_hash

    async def get_commit_info(self, repo_path: Path) -> tuple[str, str]:
        """Get current commit SHA and message."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        commit_sha = stdout.decode().strip()

        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "-1",
            "--pretty=%B",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        commit_message = stdout.decode().strip()[:500]

        return commit_sha, commit_message

    async def run_build(
        self,
        repo_path: Path,
        build_command: str,
        build_dir: str | None = None,
    ) -> tuple[bool, int | None]:
        """Run the build command and measure time."""
        work_dir = repo_path / build_dir if build_dir else repo_path

        # Clean any previous builds
        if (work_dir / "build").exists():
            await asyncio.create_subprocess_exec(
                "rm",
                "-rf",
                "build",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        # Run build and measure time
        start_time = datetime.now()

        proc = await asyncio.create_subprocess_shell(
            build_command,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await proc.communicate()
        end_time = datetime.now()

        duration_seconds = int((end_time - start_time).total_seconds())
        success = proc.returncode == 0

        return success, duration_seconds

    def detect_platform(self) -> Platform:
        """Detect current platform."""
        import platform

        system = platform.system().lower()

        if system == "linux":
            # Try to detect Ubuntu version
            try:
                with open("/etc/os-release") as f:
                    content = f.read()
                    if "22.04" in content:
                        return Platform.UBUNTU_22_04
                    elif "24.04" in content:
                        return Platform.UBUNTU_24_04
            except FileNotFoundError:
                pass
            return Platform.UBUNTU_LATEST
        elif system == "darwin":
            version = platform.mac_ver()[0]
            if version.startswith("13"):
                return Platform.MACOS_13
            elif version.startswith("14"):
                return Platform.MACOS_14
            return Platform.MACOS_LATEST
        elif system == "windows":
            return Platform.WINDOWS_2022

        return Platform.UBUNTU_LATEST

    async def build_config(
        self,
        config: ProjectConfig,
        project: Project,
        db: AsyncSession,
    ) -> bool:
        """Build a project locally based on configuration."""
        if not config.build_command:
            raise ValueError("build_command is required for local builds")

        # Get source code
        if config.source_url and config.extract_command:
            # Direct download
            repo_path, version_hash = await self.download_and_extract_source(
                config.source_url,
                config.extract_command,
                project.owner,
                project.name,
            )
            commit_sha = version_hash
            commit_message = f"Source from {config.source_url}"
        else:
            # Git clone/update
            repo_path = await self.clone_or_update_repo(
                project.url,  # Use project.url which can be any git URL
                project.owner,
                project.name,
                config.branch,
            )
            # Get commit info
            commit_sha, commit_message = await self.get_commit_info(repo_path)

        # Check if we already have this commit
        existing = await db.execute(
            select(Build).where(
                Build.project_id == project.id,
                Build.commit_sha == commit_sha,
                Build.platform == config.platform,
                Build.data_source == DataSource.LOCAL_BUILD,
            )
        )
        if existing.scalar_one_or_none():
            print(f"Already have build for {commit_sha}")
            return False

        # Determine build directory
        # For monorepos: combine subproject_path with build_dir
        # For example: subproject_path="llvm/", build_dir="build" => "llvm/build"
        build_dir = None
        if project.subproject_path or config.build_dir:
            parts = []
            if project.subproject_path:
                parts.append(project.subproject_path.rstrip('/'))
            if config.build_dir:
                parts.append(config.build_dir)
            build_dir = '/'.join(parts) if parts else None

        # Run build
        success, duration = await self.run_build(
            repo_path,
            config.build_command,
            build_dir,
        )

        # Save build record
        build = Build(
            project_id=project.id,
            commit_sha=commit_sha,
            commit_message=commit_message,
            branch=config.branch,
            success=success,
            duration_seconds=duration,
            platform=self.detect_platform(),
            data_source=DataSource.LOCAL_BUILD,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )

        db.add(build)
        config.last_checked_at = datetime.now()
        await db.flush()

        return True
