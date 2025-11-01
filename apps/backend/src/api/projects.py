from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import Integer, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import verify_api_key
from ..cache import CacheService, get_cache
from ..database import get_db
from ..logging_config import get_logger
from ..models import Build, Project, ProjectConfig
from ..schemas import (
    BuildResponse,
    BuildStats,
    ProjectCreate,
    ProjectResponse,
    ProjectTimeseries,
    ProjectUpdate,
    ProjectWithConfigCreate,
    ProjectWithStats,
    TimeseriesPoint,
)

router = APIRouter(prefix="/projects", tags=["projects"])
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.get("", response_model=list[ProjectResponse])
@limiter.limit("100/minute")
async def list_projects(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    """List all projects with optional filtering."""
    query = select(Project)

    if category:
        query = query.where(Project.category == category)
    if is_active is not None:
        query = query.where(Project.is_active == is_active)

    query = query.order_by(Project.stars.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    project: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> Project:
    """Create a new project (simple version)."""
    full_name = f"{project.owner}/{project.name}"
    url = f"https://github.com/{full_name}"

    # Check if project already exists (with same subproject_path)
    existing = await db.execute(
        select(Project).where(
            Project.full_name == full_name,
            Project.subproject_path == project.subproject_path
        )
    )
    if existing.scalar_one_or_none():
        subproject_msg = f" with subproject '{project.subproject_path}'" if project.subproject_path else ""
        raise HTTPException(status_code=400, detail=f"Project already exists{subproject_msg}")

    db_project = Project(
        owner=project.owner,
        name=project.name,
        full_name=full_name,
        url=url,
        subproject_path=project.subproject_path,
        description=project.description,
        language=project.language,
        category=project.category,
    )

    db.add(db_project)
    await db.flush()
    await db.refresh(db_project)

    # Create configs if provided
    if project.configs:
        for config_data in project.configs:
            config = ProjectConfig(
                project_id=db_project.id,
                **config_data.model_dump(exclude={'project_id'}),
            )
            db.add(config)

    await db.flush()
    await db.refresh(db_project)

    return db_project


@router.post("/with-config", response_model=ProjectResponse, status_code=201)
async def create_project_with_config(
    project: ProjectWithConfigCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> Project:
    """Create a new project with full build configuration.

    This endpoint allows you to create a project and configure how to build/scrape it
    in a single request. You can configure:
    - GitHub repos (provide owner/name)
    - Arbitrary git repos (provide git_url)
    - Direct source downloads (provide source_url + extract_command)
    - GitHub Actions scraping (workflow file + job name)
    - Local builds (build command + optional build directory)
    - Multiple platforms to track
    """
    from ..models import DataSource

    # Determine source URL
    if project.git_url:
        # Custom git URL provided
        url = project.git_url
        full_name = f"{project.owner}/{project.name}"
    else:
        # Assume GitHub
        full_name = f"{project.owner}/{project.name}"
        url = f"https://github.com/{full_name}"

    # Check if project already exists (with same subproject_path)
    existing = await db.execute(
        select(Project).where(
            Project.full_name == full_name,
            Project.subproject_path == project.subproject_path
        )
    )
    if existing.scalar_one_or_none():
        subproject_msg = f" with subproject '{project.subproject_path}'" if project.subproject_path else ""
        raise HTTPException(status_code=400, detail=f"Project already exists{subproject_msg}")

    # Create the project
    db_project = Project(
        owner=project.owner,
        name=project.name,
        full_name=full_name,
        url=url,
        subproject_path=project.subproject_path,
        description=project.description,
        language=project.language,
        category=project.category,
    )

    db.add(db_project)
    await db.flush()
    await db.refresh(db_project)

    # Create configurations based on what was provided
    configs_created = []

    # GitHub Actions configuration
    if project.github_actions_workflow:
        for platform in project.platforms:
            config = ProjectConfig(
                project_id=db_project.id,
                data_source=DataSource.GITHUB_ACTIONS,
                platform=platform,
                branch=project.branch,
                workflow_file=project.github_actions_workflow,
                job_name=project.github_actions_job,
                check_interval_hours=project.check_interval_hours,
                is_enabled=True,
            )
            db.add(config)
            configs_created.append("github_actions")

    # Local build configuration
    if project.build_command:
        for platform in project.platforms:
            config = ProjectConfig(
                project_id=db_project.id,
                data_source=DataSource.LOCAL_BUILD,
                platform=platform,
                branch=project.branch,
                build_command=project.build_command,
                build_dir=project.build_dir,
                source_url=project.source_url,
                extract_command=project.extract_command,
                check_interval_hours=project.check_interval_hours,
                is_enabled=True,
            )
            db.add(config)
            configs_created.append("local_build")

    # If no config was created, raise an error
    if not configs_created:
        raise HTTPException(
            status_code=400,
            detail="At least one configuration method required: "
                   "github_actions_workflow, build_command, or source_url"
        )

    await db.flush()
    await db.refresh(db_project)

    return db_project


@router.get("/{project_id}", response_model=ProjectWithStats)
@limiter.limit("100/minute")
async def get_project(
    request: Request,
    project_id: int,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
) -> dict:
    """Get a project with statistics.

    Cached with automatic invalidation when project or build data changes.
    """
    # Try to get from cache
    cache_key = cache.project_key(project_id)
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        logger.info("project_cache_hit", project_id=project_id)
        return cached_data
    # Get project
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.builds))
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get statistics (exclude outliers >24 hours and negative durations)
    stats_query = select(
        func.count(Build.id).label("total_builds"),
        func.sum(cast(case((Build.success == True, 1), else_=0), Integer())).label("successful_builds"),
        func.avg(Build.duration_seconds).label("avg_duration"),
        func.min(Build.duration_seconds).label("min_duration"),
        func.max(Build.duration_seconds).label("max_duration"),
    ).where(
        Build.project_id == project_id,
        Build.duration_seconds.isnot(None),
        Build.duration_seconds >= 0,  # Exclude negative durations
        Build.duration_seconds <= 86400,  # Exclude outliers >24 hours
    )

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    # Get latest builds (only completed builds with finished_at and valid durations)
    latest_builds_query = (
        select(Build)
        .where(
            Build.project_id == project_id,
            Build.finished_at.isnot(None),
            # Only include builds with valid durations (null or >= 0)
            or_(Build.duration_seconds.is_(None), Build.duration_seconds >= 0)
        )
        .order_by(Build.finished_at.desc())
        .limit(10)
    )
    latest_result = await db.execute(latest_builds_query)
    latest_builds = list(latest_result.scalars().all())

    # Find latest build from the list
    latest_build = latest_builds[0] if latest_builds else None

    stats = BuildStats(
        total_builds=stats_row.total_builds or 0,
        successful_builds=stats_row.successful_builds or 0,
        failed_builds=(stats_row.total_builds or 0) - (stats_row.successful_builds or 0),
        avg_duration_seconds=float(stats_row.avg_duration) if stats_row.avg_duration else None,
        min_duration_seconds=stats_row.min_duration,
        max_duration_seconds=stats_row.max_duration,
        latest_build=latest_build,
    )

    result = {
        "id": project.id,
        "owner": project.owner,
        "name": project.name,
        "full_name": project.full_name,
        "url": project.url,
        "subproject_path": project.subproject_path,
        "description": project.description,
        "stars": project.stars,
        "language": project.language,
        "category": project.category,
        "is_active": project.is_active,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "stats": stats,
        "latest_builds": latest_builds,
    }

    # Cache the result for 10 minutes
    await cache.set(cache_key, result, ttl=600)
    logger.info("project_cached", project_id=project_id)

    return result


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    update: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
    cache: CacheService = Depends(get_cache),
) -> Project:
    """Update a project.

    Automatically invalidates project cache.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)

    # Invalidate project cache
    await cache.invalidate_project(project_id)
    logger.info("project_updated_cache_invalidated", project_id=project_id)

    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> None:
    """Delete a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(project)


@router.get("/{project_id}/timeseries", response_model=ProjectTimeseries)
@limiter.limit("100/minute")
async def get_project_timeseries(
    request: Request,
    project_id: int,
    platform: str | None = None,
    branch: str | None = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
) -> dict:
    """Get timeseries data for a project.

    Cached with automatic invalidation when build data changes.
    """
    # Try to get from cache
    cache_key = cache.project_timeseries_key(project_id, platform=platform, branch=branch)
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        logger.info("timeseries_cache_hit", project_id=project_id, platform=platform, branch=branch)
        return cached_data
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build query (exclude outliers >24 hours)
    query = (
        select(Build)
        .where(
            Build.project_id == project_id,
            Build.duration_seconds.isnot(None),
            Build.duration_seconds <= 86400,  # Exclude outliers >24 hours
        )
        .order_by(Build.finished_at.desc())
    )

    if branch:
        query = query.where(Build.branch == branch)

    if platform:
        query = query.where(Build.platform == platform)

    # Execute query
    result = await db.execute(query)
    builds = result.scalars().all()

    # Convert to timeseries points
    points = [
        TimeseriesPoint(
            timestamp=build.finished_at or build.created_at,
            duration_seconds=build.duration_seconds,
            success=build.success,
            commit_sha=build.commit_sha,
            commit_message=build.commit_message,
            build_url=build.build_url,
        )
        for build in builds
    ]

    result = {
        "project_id": project_id,
        "project_name": project.full_name,
        "platform": platform,
        "points": points,
    }

    # Cache the result for 15 minutes
    await cache.set(cache_key, result, ttl=900)
    logger.info("timeseries_cached", project_id=project_id, platform=platform, branch=branch)

    return result
