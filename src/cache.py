import os

from flask_caching import Cache

CACHE_TTL = 3600

cache = Cache(
    config={
        "CACHE_TYPE": "RedisCache",
        "CACHE_REDIS_HOST": os.environ.get("REDIS_HOST", "localhost"),
        "CACHE_REDIS_PORT": int(os.environ.get("REDIS_PORT", "6379")),
        "CACHE_REDIS_DB": 0,
        "CACHE_DEFAULT_TIMEOUT": CACHE_TTL,
    }
)
