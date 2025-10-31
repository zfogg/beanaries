"""API endpoints for scheduler management."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks

from ..scheduler import get_scheduler, trigger_manual_scrape

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
async def get_scheduler_status() -> dict[str, Any]:
    """
    Get the current status of the scheduler.

    Returns:
        Dict with scheduler status information
    """
    scheduler = get_scheduler()

    if not scheduler.is_running:
        return {
            "status": "stopped",
            "is_running": False,
            "jobs": [],
        }

    jobs = []
    for job in scheduler.scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )

    return {
        "status": "running",
        "is_running": True,
        "jobs": jobs,
    }


@router.post("/trigger")
async def trigger_scrape(background_tasks: BackgroundTasks) -> dict[str, str]:
    """
    Manually trigger a scraping job immediately.

    The scraping job will run in the background and not block the API response.

    Returns:
        Status message
    """
    background_tasks.add_task(trigger_manual_scrape)

    return {
        "status": "triggered",
        "message": "Scraping job has been triggered and will run in the background",
    }
