from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_api_key
from ..database import get_db
from ..logging_config import get_logger
from ..models import Project, ProjectConfig
from ..schemas import ProjectConfigCreate, ProjectConfigResponse, ProjectConfigUpdate

router = APIRouter(prefix="/configs", tags=["configs"])
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.get("", response_model=list[ProjectConfigResponse])
@limiter.limit("100/minute")
async def list_configs(
    request: Request,
    project_id: int | None = None,
    is_enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ProjectConfig]:
    """List project configurations."""
    query = select(ProjectConfig)

    if project_id:
        query = query.where(ProjectConfig.project_id == project_id)
    if is_enabled is not None:
        query = query.where(ProjectConfig.is_enabled == is_enabled)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=ProjectConfigResponse, status_code=201)
async def create_config(
    config: ProjectConfigCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ProjectConfig:
    """Create a new project configuration."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == config.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    db_config = ProjectConfig(**config.model_dump())
    db.add(db_config)
    await db.flush()
    await db.refresh(db_config)

    return db_config


@router.get("/{config_id}", response_model=ProjectConfigResponse)
@limiter.limit("100/minute")
async def get_config(
    request: Request,
    config_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProjectConfig:
    """Get a specific configuration."""
    result = await db.execute(select(ProjectConfig).where(ProjectConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return config


@router.patch("/{config_id}", response_model=ProjectConfigResponse)
async def update_config(
    config_id: int,
    update: ProjectConfigUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ProjectConfig:
    """Update a configuration."""
    result = await db.execute(select(ProjectConfig).where(ProjectConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.flush()
    await db.refresh(config)

    return config


@router.delete("/{config_id}", status_code=204)
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> None:
    """Delete a configuration."""
    result = await db.execute(select(ProjectConfig).where(ProjectConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    await db.delete(config)
