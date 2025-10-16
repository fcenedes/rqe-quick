"""
Redis connection pool management.
"""

import redis
from threading import Lock


class RedisConnectionPool:
    """
    Thread-safe Redis connection pool.
    
    Creates a pool of Redis connections that can be reused across multiple workers.
    Connections are created lazily on first use.
    """
    
    def __init__(self, host, port, db, username=None, password=None, pool_size=4):
        """
        Initialize the connection pool.
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            username: Optional Redis username
            password: Optional Redis password
            pool_size: Number of connections in the pool
        """
        self.host = host
        self.port = port
        self.db = db
        self.username = username
        self.password = password
        self.pool_size = pool_size
        self.connections = []
        self.lock = Lock()
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization of connections."""
        with self.lock:
            if self._initialized:
                return
            
            for _ in range(self.pool_size):
                conn = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    username=self.username,
                    password=self.password,
                    decode_responses=False,
                    protocol=3
                )
                self.connections.append(conn)
            
            self._initialized = True
    
    def get_connection(self, worker_id):
        """
        Get a connection for a specific worker.
        
        Args:
            worker_id: Worker ID (0-based)
            
        Returns:
            Redis connection
        """
        if not self._initialized:
            self._initialize()
        
        # Round-robin assignment
        idx = worker_id % self.pool_size
        return self.connections[idx]
    
    def close_all(self):
        """Close all connections in the pool."""
        with self.lock:
            for conn in self.connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self.connections.clear()
            self._initialized = False

