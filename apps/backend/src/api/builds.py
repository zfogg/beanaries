from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_api_key
from ..cache import CacheService, get_cache
from ..database import get_db
from ..logging_config import get_logger
from ..models import Build, Project
from ..schemas import BuildCreate, BuildResponse

router = APIRouter(prefix="/builds", tags=["builds"])
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.get("", response_model=list[BuildResponse])
@limiter.limit("100/minute")
async def list_builds(
    request: Request,
    project_id: int | None = None,
    platform: str | None = None,
    success: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[Build]:
    """List builds with optional filtering."""
    query = select(Build).order_by(Build.finished_at.desc())

    if project_id:
        query = query.where(Build.project_id == project_id)
    if platform:
        query = query.where(Build.platform == platform)
    if success is not None:
        query = query.where(Build.success == success)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=BuildResponse, status_code=201)
async def create_build(
    build: BuildCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
    cache: CacheService = Depends(get_cache),
) -> Build:
    """Create a new build record.

    Automatically invalidates project and leaderboard caches.
    """
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == build.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    db_build = Build(**build.model_dump())
    db.add(db_build)
    await db.flush()
    await db.refresh(db_build)

    # Invalidate caches - new build affects both project stats and leaderboard
    await cache.invalidate_project_and_leaderboard(db_build.project_id)
    logger.info("build_created_cache_invalidated", build_id=db_build.id, project_id=db_build.project_id)

    return db_build


@router.get("/{build_id}", response_model=BuildResponse)
@limiter.limit("100/minute")
async def get_build(
    request: Request,
    build_id: int,
    db: AsyncSession = Depends(get_db),
) -> Build:
    """Get a specific build."""
    result = await db.execute(select(Build).where(Build.id == build_id))
    build = result.scalar_one_or_none()

    if not build:
        raise HTTPException(status_code=404, detail="Build not found")

    return build


@router.delete("/{build_id}", status_code=204)
async def delete_build(
    build_id: int,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
    cache: CacheService = Depends(get_cache),
) -> None:
    """Delete a build.

    Automatically invalidates project and leaderboard caches.
    """
    result = await db.execute(select(Build).where(Build.id == build_id))
    build = result.scalar_one_or_none()

    if not build:
        raise HTTPException(status_code=404, detail="Build not found")

    # Capture project_id before deletion
    project_id = build.project_id

    await db.delete(build)

    # Invalidate caches - removing a build affects both project stats and leaderboard
    await cache.invalidate_project_and_leaderboard(project_id)
    logger.info("build_deleted_cache_invalidated", build_id=build_id, project_id=project_id)
