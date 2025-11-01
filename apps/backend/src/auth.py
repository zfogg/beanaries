"""Authentication utilities for API endpoints."""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

# HTTP Bearer security scheme for API key authentication
security = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    """Verify API key for write operations.

    In debug mode (DEBUG=true), API key is not required.
    In production (DEBUG=false), API key is required.

    Args:
        credentials: Bearer token credentials from Authorization header

    Returns:
        The API key if valid, or "debug" in debug mode

    Raises:
        HTTPException: 401 if API key is missing or invalid (only in production)
    """
    # In debug mode, skip API key requirement
    if settings.debug:
        logger.debug("debug_mode_auth_bypass", message="Debug mode enabled - skipping API key check")
        return "debug"

    # Production mode - require API key
    if not settings.api_key:
        logger.error("api_key_not_configured", message="API key not set but debug mode is disabled!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error - contact administrator",
        )

    if not credentials:
        logger.warning("missing_api_key", message="No credentials provided for write operation")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required for write operations. Provide in Authorization header as Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != settings.api_key:
        logger.warning(
            "invalid_api_key",
            message="Invalid API key provided",
            key_prefix=credentials.credentials[:8] if len(credentials.credentials) >= 8 else "short",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("api_key_verified", message="Valid API key provided for write operation")
    return credentials.credentials
