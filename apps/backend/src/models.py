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
    BUILD_TOOL = "build_tool"
    GRAPHICS = "graphics"
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
    LUCI = "luci"  # Generic LUCI/Buildbucket (Chromium, Fuchsia, Dart, Flutter, WebRTC, V8, etc.)
    BUILDKITE = "buildkite"  # Buildkite CI (Bazel, Elasticsearch, Terraform, etc.)
    KOJI = "koji"  # Fedora Koji build system (RPM packages, Fedora ecosystem)
    OBS = "obs"  # OpenSUSE Build Service (RPM/DEB packages, openSUSE ecosystem)
    GITLAB_CI = "gitlab_ci"  # GitLab CI/CD (Mesa 3D, etc.)
    LOCAL_BUILD = "local_build"
    MANUAL = "manual"

    # Backward compatibility alias
    CHROMIUM_LUCI = LUCI


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
    """Base configuration for how to collect build data for a project.

    This is the parent table that links projects to their specific scraper configs.
    Each config record points to a specific scraper configuration table.
    """

    __tablename__ = "project_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    # Data source configuration
    data_source: Mapped[DataSource] = mapped_column(String(50), nullable=False)

    # Common scraping configuration
    platform: Mapped[Platform | None] = mapped_column(String(50), nullable=True)  # For filtering specific platforms
    branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    # Scheduling
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="configs")
    github_actions_config: Mapped["GitHubActionsConfig | None"] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        uselist=False,
    )
    luci_config: Mapped["LUCIConfig | None"] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        uselist=False,
    )
    buildkite_config: Mapped["BuildkiteConfig | None"] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        uselist=False,
    )
    koji_config: Mapped["KojiConfig | None"] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        uselist=False,
    )
    obs_config: Mapped["ObsConfig | None"] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_configs_project", "project_id"),
        Index("idx_configs_enabled", "is_enabled"),
        Index("idx_configs_data_source", "data_source"),
        Index("idx_configs_next_check", "last_checked_at", "check_interval_hours"),
    )


class GitHubActionsConfig(Base, TimestampMixin):
    """GitHub Actions specific configuration."""

    __tablename__ = "github_actions_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(
        ForeignKey("project_configs.id"),
        nullable=False,
        unique=True,
    )

    # GitHub Actions workflow configuration
    workflow_file: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship
    config: Mapped["ProjectConfig"] = relationship(back_populates="github_actions_config")

    __table_args__ = (Index("idx_gh_actions_config", "config_id"),)


class LUCIConfig(Base, TimestampMixin):
    """LUCI/Buildbucket specific configuration."""

    __tablename__ = "luci_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(
        ForeignKey("project_configs.id"),
        nullable=False,
        unique=True,
    )

    # LUCI configuration
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "chromium", "fuchsia"
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "ci", "try"
    builder: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Linux Builder"

    # Relationship
    config: Mapped["ProjectConfig"] = relationship(back_populates="luci_config")

    __table_args__ = (Index("idx_luci_config", "config_id"),)


class BuildkiteConfig(Base, TimestampMixin):
    """Buildkite specific configuration."""

    __tablename__ = "buildkite_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(
        ForeignKey("project_configs.id"),
        nullable=False,
        unique=True,
    )

    # Buildkite configuration
    org_slug: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "llvm-project"
    pipeline_slug: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "libcxx-ci"

    # Relationship
    config: Mapped["ProjectConfig"] = relationship(back_populates="buildkite_config")

    __table_args__ = (Index("idx_buildkite_config", "config_id"),)


class KojiConfig(Base, TimestampMixin):
    """Fedora Koji build system specific configuration."""

    __tablename__ = "koji_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(
        ForeignKey("project_configs.id"),
        nullable=False,
        unique=True,
    )

    # Koji configuration
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "kernel", "systemd", "gcc"
    tag: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g., "f41-build", "f40-updates"

    # Relationship
    config: Mapped["ProjectConfig"] = relationship(back_populates="koji_config")

    __table_args__ = (Index("idx_koji_config", "config_id"),)


class ObsConfig(Base, TimestampMixin):
    """OpenSUSE Build Service specific configuration."""

    __tablename__ = "obs_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int] = mapped_column(
        ForeignKey("project_configs.id"),
        nullable=False,
        unique=True,
    )

    # OBS configuration
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "openSUSE:Factory", "KDE:Frameworks"
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "kernel-default", "systemd", "gcc"
    repository: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g., "standard", "snapshot"
    arch: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g., "x86_64", "aarch64"

    # Relationship
    config: Mapped["ProjectConfig"] = relationship(back_populates="obs_config")

    __table_args__ = (Index("idx_obs_config", "config_id"),)


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
