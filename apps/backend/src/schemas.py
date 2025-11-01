from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .models import DataSource, Platform, ProjectCategory


# Project schemas
class ProjectBase(BaseModel):
    owner: str = Field(max_length=255)
    name: str = Field(max_length=255)
    subproject_path: str | None = Field(
        None,
        max_length=511,
        description="Path to subproject within monorepo (e.g., 'llvm/', 'clang/'). Leave empty for non-monorepos."
    )
    description: str | None = None
    language: str | None = Field(None, max_length=50)
    category: ProjectCategory = ProjectCategory.OTHER


class ProjectCreate(ProjectBase):
    # Optional: include configuration on creation
    configs: list["ProjectConfigCreate"] | None = None


class ProjectUpdate(BaseModel):
    description: str | None = None
    category: ProjectCategory | None = None
    is_active: bool | None = None


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    url: str
    subproject_path: str | None
    stars: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Build schemas
class BuildBase(BaseModel):
    commit_sha: str = Field(min_length=7, max_length=40)
    commit_message: str | None = None
    branch: str = Field(max_length=255)
    success: bool
    duration_seconds: int | None = Field(None, ge=0)
    platform: Platform
    data_source: DataSource


class BuildCreate(BuildBase):
    project_id: int
    workflow_name: str | None = Field(None, max_length=255)
    workflow_run_id: int | None = None
    job_id: int | None = None
    build_url: str | None = None
    runner: str | None = Field(None, max_length=100)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BuildResponse(BuildBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    workflow_name: str | None
    workflow_run_id: int | None
    job_id: int | None
    build_url: str | None
    runner: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


# Config schemas
class ProjectConfigBase(BaseModel):
    data_source: DataSource
    platform: Platform
    branch: str = "main"
    workflow_name: str | None = None
    workflow_file: str | None = None
    job_name: str | None = None
    build_command: str | None = None
    build_dir: str | None = None
    source_url: str | None = None
    extract_command: str | None = None
    check_interval_hours: int = Field(24, ge=1, le=168)


class ProjectConfigCreate(ProjectConfigBase):
    project_id: int | None = None  # Optional when creating with project


class ProjectConfigUpdate(BaseModel):
    data_source: DataSource | None = None
    platform: Platform | None = None
    branch: str | None = None
    workflow_name: str | None = None
    workflow_file: str | None = None
    job_name: str | None = None
    build_command: str | None = None
    build_dir: str | None = None
    source_url: str | None = None
    extract_command: str | None = None
    is_enabled: bool | None = None
    check_interval_hours: int | None = Field(None, ge=1, le=168)


class ProjectConfigResponse(ProjectConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    is_enabled: bool
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


# Statistics schemas
class BuildStats(BaseModel):
    total_builds: int
    successful_builds: int
    failed_builds: int
    avg_duration_seconds: float | None
    min_duration_seconds: int | None
    max_duration_seconds: int | None
    latest_build: BuildResponse | None


class ProjectWithStats(ProjectResponse):
    stats: BuildStats
    latest_builds: list[BuildResponse]


# Timeseries schemas
class TimeseriesPoint(BaseModel):
    timestamp: datetime
    duration_seconds: int | None
    success: bool
    commit_sha: str
    commit_message: str | None
    build_url: str | None


class ProjectTimeseries(BaseModel):
    project_id: int
    project_name: str
    platform: Platform | None
    points: list[TimeseriesPoint]


# Leaderboard schemas
class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    avg_build_time_seconds: float | None
    latest_build_time_seconds: int | None
    success_rate: float
    total_builds: int


# Enhanced project creation with full configuration
class ProjectWithConfigCreate(ProjectBase):
    """Create a project with full build configuration in one request.

    Supports three source types:
    1. GitHub repos (provide owner/name, optional git_url)
    2. Arbitrary git repos (provide git_url)
    3. Direct downloads (provide source_url + extract_command)
    """

    # Git repository (GitHub or arbitrary)
    git_url: str | None = Field(
        None,
        description="Git repository URL (auto-generated for GitHub, or provide custom git URL)"
    )

    # GitHub Actions configuration
    github_actions_workflow: str | None = Field(
        None,
        description="GitHub Actions workflow file (e.g., 'build.yml')"
    )
    github_actions_job: str | None = Field(
        None,
        description="Specific job name in the workflow to track"
    )

    # Local build configuration
    build_command: str | None = Field(
        None,
        description="Command to build the project (e.g., 'make -j$(nproc)')"
    )
    build_dir: str | None = Field(
        None,
        description="Directory to run build in (relative to repo root)"
    )

    # Direct source download (alternative to git)
    source_url: str | None = Field(
        None,
        description="Direct download URL for source tarball/zip (alternative to git)"
    )
    extract_command: str | None = Field(
        None,
        description="Command to extract archive (e.g., 'tar -xzf', 'unzip')"
    )

    # Common settings
    platforms: list[Platform] = Field(
        default_factory=lambda: [Platform.UBUNTU_LATEST],
        description="Platforms to track builds on"
    )
    branch: str = Field(
        default="main",
        description="Branch to track (for git sources)"
    )
    check_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="How often to check for new builds (hours)"
    )
