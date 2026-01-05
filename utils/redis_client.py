import logging

import redis

from config.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for caching and queue management"""

    def __init__(self):
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,
            )
            # Test connection
            self.client.ping()
            self.enabled = True
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Continuing without cache.")
            self.client = None
            self.enabled = False

    def set_user_state(self, user_id: int, state: str, ttl: int = 3600):
        """Set user state with TTL"""
        if not self.enabled:
            return
        try:
            key = f"user_state:{user_id}"
            self.client.setex(key, ttl, state)
        except Exception as e:
            logger.error(f"Redis set_user_state error: {e}")

    def get_user_state(self, user_id: int) -> str:
        """Get user state"""
        if not self.enabled:
            return None
        try:
            key = f"user_state:{user_id}"
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get_user_state error: {e}")
            return None

    def delete_user_state(self, user_id: int):
        """Delete user state"""
        if not self.enabled:
            return
        try:
            key = f"user_state:{user_id}"
            self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete_user_state error: {e}")

    def set_video_info(self, user_id: int, video_info: dict, ttl: int = 3600):
        """Cache video info"""
        if not self.enabled:
            return
        try:
            key = f"video_info:{user_id}"
            self.client.setex(key, ttl, str(video_info))
        except Exception as e:
            logger.error(f"Redis set_video_info error: {e}")

    def get_video_info(self, user_id: int) -> str:
        """Get cached video info"""
        if not self.enabled:
            return None
        try:
            key = f"video_info:{user_id}"
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get_video_info error: {e}")
            return None

    def delete_video_info(self, user_id: int):
        """Delete cached video info"""
        if not self.enabled:
            return
        try:
            key = f"video_info:{user_id}"
            self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete_video_info error: {e}")

    def add_to_download_queue(self, user_id: int, download_id: int):
        """Add download to processing queue"""
        key = f"download_queue:{user_id}"
        self.client.rpush(key, download_id)

    def get_queue_size(self, user_id: int) -> int:
        """Get download queue size for user"""
        key = f"download_queue:{user_id}"
        return self.client.llen(key)

    def is_healthy(self) -> bool:
        """Check if Redis is healthy"""
        if not self.enabled:
            return False
        try:
            return self.client.ping()
        except:
            return False


# Global Redis client instance
redis_client = RedisClient()
