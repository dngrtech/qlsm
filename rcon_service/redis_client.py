"""
Redis client wrapper for RCON service.

Provides async Redis Pub/Sub functionality for communication 
between rcon_service and the Flask backend.
"""

import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional

import redis.asyncio as redis

log = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for RCON service communication."""
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis client.
        
        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var
                      or redis://localhost:6379/0
        """
        self.redis_url = redis_url or os.environ.get(
            'REDIS_URL', 'redis://localhost:6379/0'
        )
        self._redis_password = os.environ.get('REDIS_PASSWORD')
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
    
    async def connect(self) -> None:
        """Connect to Redis."""
        log.info(f"Connecting to Redis at {self.redis_url}...")
        self._redis = redis.from_url(
            self.redis_url, 
            decode_responses=True,
            password=self._redis_password
        )
        await self._redis.ping()
        log.info("Connected to Redis successfully.")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        log.info("Disconnected from Redis.")
    
    async def publish(self, channel: str, message: dict) -> int:
        """Publish a message to a Redis channel.
        
        Args:
            channel: The channel to publish to
            message: The message dict to publish (will be JSON encoded)
            
        Returns:
            Number of subscribers that received the message
        """
        if not self._redis:
            raise RuntimeError("Redis client not connected")
        
        json_message = json.dumps(message)
        result = await self._redis.publish(channel, json_message)
        log.debug(f"Published to {channel}: {message}")
        return result
    
    async def subscribe_pattern(self, *patterns: str) -> AsyncIterator[dict]:
        """Subscribe to channels matching one or more patterns.

        Args:
            *patterns: Redis patterns to subscribe to (e.g., 'rcon:cmd:*')

        Yields:
            Dict with 'channel' and 'data' keys for each message
        """
        if not self._redis:
            raise RuntimeError("Redis client not connected")

        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(*patterns)
        log.info(f"Subscribed to patterns: {patterns}")
        
        async for message in self._pubsub.listen():
            if message['type'] == 'pmessage':
                try:
                    data = json.loads(message['data'])
                    yield {
                        'channel': message['channel'],
                        'pattern': message['pattern'],
                        'data': data
                    }
                except json.JSONDecodeError as e:
                    log.error(f"Failed to parse message from {message['channel']}: {e}")
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from Redis."""
        if not self._redis:
            raise RuntimeError("Redis client not connected")
        return await self._redis.get(key)
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiry."""
        if not self._redis:
            raise RuntimeError("Redis client not connected")
        return await self._redis.set(key, value, ex=ex)
