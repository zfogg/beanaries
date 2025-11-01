from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from ..cache import CacheService, get_cache
from ..database import get_db
from ..logging_config import get_logger
from ..models import Build, Platform, Project, ProjectCategory
from ..schemas import LeaderboardEntry

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.get("", response_model=list[LeaderboardEntry])
@limiter.limit("100/minute")
async def get_leaderboard(
    request: Request,
    platform: Platform | None = None,
    category: ProjectCategory | None = None,
    min_builds: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
) -> list[LeaderboardEntry]:
    """Get the leaderboard of projects by build time.

    Optimized with Redis caching and N+1 query prevention.
    Cache is automatically invalidated when build data changes.
    """
    # Try to get from cache
    cache_key = cache.leaderboard_key(
        platform=platform.value if platform else None,
        category=category.value if category else None,
    )
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        logger.info("leaderboard_cache_hit", platform=platform, category=category)
        # Convert cached dicts back to Pydantic models
        return [LeaderboardEntry(**item) for item in cached_data]

    # Base conditions for valid builds (exclude outliers >24 hours)
    build_conditions = and_(
        Build.duration_seconds.isnot(None),
        Build.duration_seconds <= 86400,
    )

    if platform:
        build_conditions = and_(build_conditions, Build.platform == platform)

    # Subquery for build statistics
    build_stats = (
        select(
            Build.project_id,
            func.avg(Build.duration_seconds).label("avg_build_time"),
            func.count(Build.id).label("total_builds"),
            func.sum(cast(case((Build.success == True, 1), else_=0), Integer())).label("successful_builds"),
        )
        .where(build_conditions)
        .group_by(Build.project_id)
        .having(func.count(Build.id) >= min_builds)
    ).subquery()

    # Subquery for latest build duration using DISTINCT ON (PostgreSQL-specific optimization)
    # This gets the latest build for each project in a single query
    from sqlalchemy import distinct
    latest_builds = (
        select(
            Build.project_id,
            Build.duration_seconds.label("latest_duration"),
        )
        .where(build_conditions)
        .distinct(Build.project_id)
        .order_by(Build.project_id, Build.finished_at.desc())
    ).subquery()

    # Main query joining everything together
    query = (
        select(
            Project,
            build_stats.c.avg_build_time,
            build_stats.c.total_builds,
            build_stats.c.successful_builds,
            latest_builds.c.latest_duration,
        )
        .join(build_stats, Project.id == build_stats.c.project_id)
        .outerjoin(latest_builds, Project.id == latest_builds.c.project_id)
        .where(Project.is_active == True)
    )

    if category:
        query = query.where(Project.category == category)

    query = query.order_by(build_stats.c.avg_build_time.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    leaderboard = []
    for row in rows:
        project, avg_time, total, successful, latest_duration = row

        success_rate = (successful / total * 100) if total > 0 else 0.0

        entry = LeaderboardEntry(
            project=project,
            avg_build_time_seconds=float(avg_time) if avg_time else None,
            latest_build_time_seconds=latest_duration,
            success_rate=success_rate,
            total_builds=total,
        )
        leaderboard.append(entry)

    # Cache the result for 5 minutes
    await cache.set(cache_key, leaderboard, ttl=300)
    logger.info("leaderboard_cached", platform=platform, category=category, count=len(leaderboard))

    return leaderboard
