from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api import builds, configs, leaderboard, projects, scheduler
from .cache import cache
from .config import settings
from .database import init_db
from .logging_config import configure_logging, get_logger
from .scheduler import shutdown_scheduler, start_scheduler

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("application_startup", message="Starting Beanaries API")
    await init_db()
    logger.info("database_initialized", message="Database initialized")
    await cache.connect()
    logger.info("cache_initialized", message="Cache initialized")
    await start_scheduler()
    logger.info("scheduler_started", message="Background scheduler started")
    yield
    # Shutdown
    logger.info("application_shutdown", message="Shutting down Beanaries API")
    await shutdown_scheduler()
    logger.info("scheduler_stopped", message="Background scheduler stopped")
    await cache.disconnect()
    logger.info("cache_disconnected", message="Cache disconnected")


app = FastAPI(
    title="Beanaries API",
    description="Build time tracking for popular open source projects",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Updated for beanaries.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://beanaries.com",
        "https://www.beanaries.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    start_time = time.time()

    # Log incoming request
    logger.info(
        "http_request_start",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else None,
    )

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = int((time.time() - start_time) * 1000)

    # Log response
    logger.info(
        "http_request_complete",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    return response

# Include routers
app.include_router(projects.router)
app.include_router(builds.router)
app.include_router(configs.router)
app.include_router(leaderboard.router)
app.include_router(scheduler.router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )
