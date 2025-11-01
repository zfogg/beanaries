"""Redis caching service with automatic cache invalidation.

This module provides a clean interface for caching API responses and invalidating
caches when underlying data changes.
"""
import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class CacheService:
    """Redis cache service for API responses.

    Handles caching with TTL and provides cache invalidation methods.
    """

    def __init__(self):
        """Initialize Redis connection."""
        self.redis: Redis | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.redis = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self.redis.ping()
            self._connected = True
            logger.info("redis_connected", message=f"Connected to Redis at {settings.redis_url}")
        except Exception as e:
            logger.warning("redis_connection_failed", message=f"Failed to connect to Redis: {e}")
            self._connected = False
            self.redis = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.aclose()
            self._connected = False
            logger.info("redis_disconnected", message="Disconnected from Redis")

    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._connected and self.redis is not None

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self.is_connected():
            return None

        try:
            value = await self.redis.get(key)  # type: ignore
            if value:
                logger.debug("cache_hit", key=key)
                return json.loads(value)
            logger.debug("cache_miss", key=key)
            return None
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default: 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            # Use FastAPI's jsonable_encoder to properly handle Pydantic models and SQLAlchemy objects
            json_compatible = jsonable_encoder(value)
            serialized = json.dumps(json_compatible)
            await self.redis.setex(key, ttl, serialized)  # type: ignore
            logger.debug("cache_set", key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            await self.redis.delete(key)  # type: ignore
            logger.debug("cache_delete", key=key)
            return True
        except Exception as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: Redis pattern (e.g., "leaderboard:*", "project:123:*")

        Returns:
            Number of keys deleted
        """
        if not self.is_connected():
            return 0

        try:
            # Get all keys matching pattern
            keys = []
            async for key in self.redis.scan_iter(pattern):  # type: ignore
                keys.append(key)

            if keys:
                deleted = await self.redis.delete(*keys)  # type: ignore
                logger.info("cache_pattern_delete", pattern=pattern, deleted=deleted)
                return deleted
            return 0
        except Exception as e:
            logger.warning("cache_pattern_delete_error", pattern=pattern, error=str(e))
            return 0

    # Cache key generators
    @staticmethod
    def leaderboard_key(platform: str | None = None, category: str | None = None) -> str:
        """Generate cache key for leaderboard.

        Args:
            platform: Optional platform filter
            category: Optional category filter

        Returns:
            Cache key string
        """
        parts = ["leaderboard"]
        if platform:
            parts.append(f"platform:{platform}")
        if category:
            parts.append(f"category:{category}")
        return ":".join(parts)

    @staticmethod
    def project_key(project_id: int) -> str:
        """Generate cache key for project details.

        Args:
            project_id: Project ID

        Returns:
            Cache key string
        """
        return f"project:{project_id}"

    @staticmethod
    def project_timeseries_key(
        project_id: int,
        platform: str | None = None,
        branch: str | None = None,
    ) -> str:
        """Generate cache key for project timeseries.

        Args:
            project_id: Project ID
            platform: Optional platform filter
            branch: Optional branch filter

        Returns:
            Cache key string
        """
        parts = [f"project:{project_id}:timeseries"]
        if platform:
            parts.append(f"platform:{platform}")
        if branch:
            parts.append(f"branch:{branch}")
        return ":".join(parts)

    # Cache invalidation methods
    async def invalidate_leaderboard(self) -> None:
        """Invalidate all leaderboard caches.

        Called when build data changes that affects leaderboard rankings.
        """
        deleted = await self.delete_pattern("leaderboard:*")
        logger.info("invalidate_leaderboard", deleted=deleted)

    async def invalidate_project(self, project_id: int) -> None:
        """Invalidate all caches for a specific project.

        Called when project data or its builds change.

        Args:
            project_id: Project ID to invalidate
        """
        deleted = await self.delete_pattern(f"project:{project_id}:*")
        logger.info("invalidate_project", project_id=project_id, deleted=deleted)

    async def invalidate_project_and_leaderboard(self, project_id: int) -> None:
        """Invalidate project cache and leaderboard.

        Called when builds are created/deleted, affecting both project stats and leaderboard.

        Args:
            project_id: Project ID that changed
        """
        await self.invalidate_project(project_id)
        await self.invalidate_leaderboard()


# Global cache service instance
cache = CacheService()


async def get_cache() -> CacheService:
    """Dependency for getting cache service.

    Returns:
        Cache service instance
    """
    return cache
