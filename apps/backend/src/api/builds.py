from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Build, Project
from ..schemas import BuildCreate, BuildResponse

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("", response_model=list[BuildResponse])
async def list_builds(
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
) -> Build:
    """Create a new build record."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == build.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    db_build = Build(**build.model_dump())
    db.add(db_build)
    await db.flush()
    await db.refresh(db_build)

    return db_build


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(
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
) -> None:
    """Delete a build."""
    result = await db.execute(select(Build).where(Build.id == build_id))
    build = result.scalar_one_or_none()

    if not build:
        raise HTTPException(status_code=404, detail="Build not found")

    await db.delete(build)
