"""
Threaded (parallel) seeding implementation using ThreadPoolExecutor.
"""

import random
import os
from time import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from ..connection import RedisConnectionPool


def seed_dummy_hash_docs_threaded(
    r,
    *,
    prefix: str,
    n_docs: int = 200_000,
    chunk: int = 10_000,
    seed: int = 42,
    n_workers: Optional[int] = None,
    connection_pool: Optional[RedisConnectionPool] = None
):
    """
    Optimized parallel version of seed_dummy_hash_docs.
    Uses multiple threads with pre-allocated Redis connections for parallel insertion.
    
    Args:
        r: Redis client (used for connection parameters if pool not provided)
        prefix: Key prefix for documents
        n_docs: Number of documents to create
        chunk: Pipeline batch size
        seed: Random seed for reproducibility
        n_workers: Number of worker threads (default: min(cpu_count, 8))
        connection_pool: Optional pre-allocated connection pool. If None, creates temporary connections.
        
    Returns:
        Total number of documents inserted
    """
    if n_workers is None:
        n_workers = min(os.cpu_count() or 4, 8)

    # Shared constants
    countries = ["US", "FR", "DE", "IN", "BR", "CN", "GB", "ES", "IT", "JP"]
    categories = ["electronics", "books", "toys", "clothing", "grocery", "beauty", "sports"]
    statuses = ["pending", "paid", "shipped", "delivered", "returned", "cancelled"]
    status_weights = [4, 10, 15, 25, 3, 2]
    now = int(time())
    day = 86400

    # Create temporary pool if not provided
    temp_pool = None
    if connection_pool is None:
        temp_pool = RedisConnectionPool(
            host=r.connection_pool.connection_kwargs.get('host', 'localhost'),
            port=r.connection_pool.connection_kwargs.get('port', 6379),
            db=r.connection_pool.connection_kwargs.get('db', 0),
            username=r.connection_pool.connection_kwargs.get('username'),
            password=r.connection_pool.connection_kwargs.get('password'),
            pool_size=n_workers
        )
        connection_pool = temp_pool

    def worker_insert(worker_id: int, start_idx: int, end_idx: int, worker_seed: int):
        """Worker function that inserts a range of documents."""
        # Get pre-allocated connection from pool
        worker_r = connection_pool.get_connection(worker_id)

        rnd = random.Random(worker_seed)
        pipe = worker_r.pipeline(transaction=False)
        written = 0

        for i in range(start_idx, end_idx):
            key = f"{prefix}{i}"
            country = countries[rnd.randint(0, len(countries) - 1)]
            category = categories[rnd.randint(0, len(categories) - 1)]
            status = rnd.choices(statuses, weights=status_weights, k=1)[0]

            # mildly skewed price & recency
            price = max(1, int(abs(rnd.gauss(60, 25)) * (1 + 0.2 * (category == "electronics"))))
            ts = now - rnd.randint(0, 30 * day)

            pipe.hset(key, mapping={
                "country": country,
                "category": category,
                "status": status,
                "price": price,
                "ts": ts
            })
            written += 1
            if written % chunk == 0:
                pipe.execute()

        if written % chunk:
            pipe.execute()

        return end_idx - start_idx

    # Divide work among workers
    docs_per_worker = n_docs // n_workers
    futures = []

    try:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            for worker_id in range(n_workers):
                start_idx = worker_id * docs_per_worker
                if worker_id == n_workers - 1:
                    end_idx = n_docs  # Last worker takes remainder
                else:
                    end_idx = start_idx + docs_per_worker

                # Different seed per worker to avoid duplicate random sequences
                worker_seed = seed + worker_id
                future = executor.submit(worker_insert, worker_id, start_idx, end_idx, worker_seed)
                futures.append(future)

            # Wait for all workers to complete
            total_inserted = 0
            for future in as_completed(futures):
                total_inserted += future.result()
    finally:
        # Clean up temporary pool if we created one
        if temp_pool is not None:
            temp_pool.close_all()

    return total_inserted

