"""
Configuration management for Redis RediSearch benchmarks.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Configuration settings loaded from environment variables."""
    
    # Redis connection
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_USERNAME = os.getenv("REDIS_USERNAME") or None
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
    
    # Performance settings
    PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS") or os.cpu_count() or 4)
    CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE") or PARALLEL_WORKERS)
    SEED_BATCH_SIZE = int(os.getenv("SEED_BATCH_SIZE", "20000"))
    AGGREGATE_BATCH_SIZE = int(os.getenv("AGGREGATE_BATCH_SIZE", "20000"))

    # Data generation settings
    RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
    
    @classmethod
    def get_redis_params(cls):
        """Get Redis connection parameters as a dict."""
        return {
            "host": cls.REDIS_HOST,
            "port": cls.REDIS_PORT,
            "db": cls.REDIS_DB,
            "username": cls.REDIS_USERNAME,
            "password": cls.REDIS_PASSWORD,
            "decode_responses": False,
            "protocol": 3,
        }
    
    @classmethod
    def display(cls):
        """Return configuration as a dict for display."""
        return {
            "Redis Host": cls.REDIS_HOST,
            "Redis Port": cls.REDIS_PORT,
            "Redis DB": cls.REDIS_DB,
            "Redis Username": cls.REDIS_USERNAME if cls.REDIS_USERNAME else "(none)",
            "Redis Password": "●" * 8 if cls.REDIS_PASSWORD else "(none)",
            "Parallel Workers": cls.PARALLEL_WORKERS,
            "Connection Pool Size": cls.CONNECTION_POOL_SIZE,
            "Seed Batch Size": f"{cls.SEED_BATCH_SIZE:,}",
            "Aggregate Batch Size": f"{cls.AGGREGATE_BATCH_SIZE:,}",
            "Random Seed": cls.RANDOM_SEED,
        }

