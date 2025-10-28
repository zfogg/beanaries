from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, TimestampMixin


class ProjectCategory(str, Enum):
    """Categories for projects."""

    COMPILER = "compiler"
    KERNEL = "kernel"
    BROWSER = "browser"
    ML = "ml"
    ML_FRAMEWORK = "ml_framework"
    RUNTIME = "runtime"
    LANGUAGE_RUNTIME = "language_runtime"
    DATABASE = "database"
    DEVTOOLS = "devtools"
    GAMEENGINE = "gameengine"
    INFRASTRUCTURE = "infrastructure"
    MEDIA = "media"
    SECURITY = "security"
    CRYPTO = "crypto"
    NETWORKING = "networking"
    VIRTUALIZATION = "virtualization"
    OS = "os"
    OTHER = "other"


class Platform(str, Enum):
    """Build platforms."""

    UBUNTU_LATEST = "ubuntu-latest"
    MACOS_LATEST = "macos-latest"
    WINDOWS_LATEST = "windows-latest"
    UBUNTU_22_04 = "ubuntu-22.04"
    UBUNTU_24_04 = "ubuntu-24.04"
    MACOS_13 = "macos-13"
    MACOS_14 = "macos-14"
    WINDOWS_2022 = "windows-2022"


class DataSource(str, Enum):
    """How build data was collected."""

    GITHUB_ACTIONS = "github_actions"
    CHROMIUM_LUCI = "chromium_luci"
    LOCAL_BUILD = "local_build"
    MANUAL = "manual"


class Project(Base, TimestampMixin):
    """A project being tracked for build times."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Project identification
    # For GitHub: owner="rust-lang", name="rust", full_name="rust-lang/rust"
    # For other git: owner="git.savannah.gnu.org/git", name="gcc", full_name="git.savannah.gnu.org/git/gcc"
    # For direct sources: owner="kernel.org", name="linux-6.6.1", full_name="kernel.org/linux-6.6.1"
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(511), nullable=False)

    # Source location - can be GitHub URL, git URL, or direct download URL
    url: Mapped[str] = mapped_column(String(511), nullable=False)

    # Monorepo support - path to subproject within the repo
    # Examples: "llvm/", "clang/", "compiler-rt/" for llvm/llvm-project
    #           "" (empty) or None for repos that aren't monorepos
    subproject_path: Mapped[str | None] = mapped_column(String(511), nullable=True)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[ProjectCategory] = mapped_column(
        String(50),
        default=ProjectCategory.OTHER,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    configs: Mapped[list["ProjectConfig"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    builds: Mapped[list["Build"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_projects_category", "category"),
        Index("idx_projects_active", "is_active"),
        Index("idx_projects_stars", "stars"),
        # Unique constraint: same repo can have multiple entries with different subproject_path
        Index("idx_projects_unique", "full_name", "subproject_path", unique=True),
    )


class ProjectConfig(Base, TimestampMixin):
    """Configuration for how to collect build data for a project."""

    __tablename__ = "project_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # Data source configuration
    data_source: Mapped[DataSource] = mapped_column(String(50), nullable=False)

    # GitHub Actions specific
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workflow_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Local build specific
    build_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_dir: Mapped[str | None] = mapped_column(String(511), nullable=True)

    # Direct source download (alternative to git)
    source_url: Mapped[str | None] = mapped_column(String(1023), nullable=True)
    extract_command: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Common
    platform: Mapped[Platform] = mapped_column(String(50), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    # Custom scraper configuration (flexible JSON for scraper-specific settings)
    # For chromium_luci: {"bucket": "ci", "builder": "Linux Builder", "buildbucket_host": "cr-buildbucket.appspot.com"}
    # For github_actions: can migrate workflow_file, job_name here eventually
    scraper_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Scheduling
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="configs")

    __table_args__ = (
        Index("idx_configs_project", "project_id"),
        Index("idx_configs_enabled", "is_enabled"),
        Index("idx_configs_next_check", "last_checked_at", "check_interval_hours"),
    )


class Build(Base, TimestampMixin):
    """A single build record."""

    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # Build info
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)

    # Build results
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Platform info
    platform: Mapped[Platform] = mapped_column(String(50), nullable=False)
    runner: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Source info
    data_source: Mapped[DataSource] = mapped_column(String(50), nullable=False)
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Custom scraper metadata (flexible JSON for scraper-specific build data)
    # For chromium_luci: {"build_id": 12345, "builder": "Linux Builder", "bucket": "ci"}
    # For github_actions: can store additional workflow/job metadata here
    scraper_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # External links
    build_url: Mapped[str | None] = mapped_column(String(511), nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="builds")

    __table_args__ = (
        Index("idx_builds_project_time", "project_id", "finished_at"),
        Index("idx_builds_commit", "commit_sha"),
        Index("idx_builds_platform", "platform"),
        Index("idx_builds_success", "success"),
        Index("idx_builds_source", "data_source"),
    )
