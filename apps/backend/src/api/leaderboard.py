from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Build, Platform, Project, ProjectCategory
from ..schemas import LeaderboardEntry

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    platform: Platform | None = None,
    category: ProjectCategory | None = None,
    min_builds: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get the leaderboard of projects by build time."""

    # Subquery for build statistics (exclude outliers >24 hours)
    build_stats = (
        select(
            Build.project_id,
            func.avg(Build.duration_seconds).label("avg_build_time"),
            func.count(Build.id).label("total_builds"),
            func.sum(cast(case((Build.success == True, 1), else_=0), Integer())).label("successful_builds"),
        )
        .where(
            Build.duration_seconds.isnot(None),
            Build.duration_seconds <= 86400,  # Exclude outliers >24 hours
        )
        .group_by(Build.project_id)
        .having(func.count(Build.id) >= min_builds)
    )

    if platform:
        build_stats = build_stats.where(Build.platform == platform)

    build_stats = build_stats.subquery()

    # Main query joining with projects
    query = (
        select(
            Project,
            build_stats.c.avg_build_time,
            build_stats.c.total_builds,
            build_stats.c.successful_builds,
        )
        .join(build_stats, Project.id == build_stats.c.project_id)
        .where(Project.is_active == True)
    )

    if category:
        query = query.where(Project.category == category)

    query = query.order_by(build_stats.c.avg_build_time.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    leaderboard = []
    for row in rows:
        project, avg_time, total, successful = row

        # Get latest build for this project (exclude outliers)
        latest_query = (
            select(Build.duration_seconds)
            .where(
                Build.project_id == project.id,
                Build.duration_seconds.isnot(None),
                Build.duration_seconds <= 86400,  # Exclude outliers >24 hours
            )
            .order_by(Build.finished_at.desc())
            .limit(1)
        )
        if platform:
            latest_query = latest_query.where(Build.platform == platform)

        latest_result = await db.execute(latest_query)
        latest_duration = latest_result.scalar_one_or_none()

        success_rate = (successful / total * 100) if total > 0 else 0.0

        leaderboard.append(
            {
                "project": project,
                "avg_build_time_seconds": float(avg_time) if avg_time else None,
                "latest_build_time_seconds": latest_duration,
                "success_rate": success_rate,
                "total_builds": total,
            }
        )

    return leaderboard
