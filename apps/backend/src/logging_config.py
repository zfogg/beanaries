"""Structured logging configuration using structlog."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from .config import settings


def configure_logging() -> None:
    """Configure structured logging for the application.

    Uses structlog for structured logging with:
    - JSON output in production
    - Pretty console output in development
    - Automatic timestamp and log level
    - Request ID tracking (can be added via middleware)
    - File output to server.log with rotation (max 3MB, 5 backups)
    """
    # Get the backend directory path
    backend_dir = Path(__file__).parent.parent
    log_file = backend_dir / "server.log"

    # Configure standard library logging with file handler
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    # Clear any existing handlers to prevent duplicates
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # File handler with rotation (max 3MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=3 * 1024 * 1024,  # 3MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(file_handler)

    # Disable SQLAlchemy echo to prevent double logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.debug:
        # Development: Pretty console output with colors
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # Production: JSON output for log aggregation
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger instance
    """
    return structlog.get_logger(name)
