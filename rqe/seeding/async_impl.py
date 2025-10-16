"""
Async seeding implementation using asyncio with uvloop.
"""

import random
import asyncio
from time import time
import redis.asyncio as aioredis


async def seed_dummy_hash_docs_async(
    r,
    *,
    prefix: str,
    n_docs: int = 200_000,
    chunk: int = 10_000,
    seed: int = 42,
    concurrency: int = 10
):
    """
    Async version using redis.asyncio with uvloop for maximum performance.
    Uses asyncio.gather for concurrent batch insertion with multiple connections.

    Args:
        r: Async Redis client (redis.asyncio.Redis) - used for connection parameters
        prefix: Key prefix for documents
        n_docs: Number of documents to create
        chunk: Pipeline batch size
        seed: Random seed for reproducibility
        concurrency: Number of concurrent connections (default: 10)

    Returns:
        Total number of documents inserted
    """
    # Shared constants
    countries = ["US", "FR", "DE", "IN", "BR", "CN", "GB", "ES", "IT", "JP"]
    categories = ["electronics", "books", "toys", "clothing", "grocery", "beauty", "sports"]
    statuses = ["pending", "paid", "shipped", "delivered", "returned", "cancelled"]
    status_weights = [4, 10, 15, 25, 3, 2]
    now = int(time())
    day = 86400

    # Get connection parameters from the provided client
    connection_kwargs = {
        'host': r.connection_pool.connection_kwargs.get('host', 'localhost'),
        'port': r.connection_pool.connection_kwargs.get('port', 6379),
        'db': r.connection_pool.connection_kwargs.get('db', 0),
        'username': r.connection_pool.connection_kwargs.get('username'),
        'password': r.connection_pool.connection_kwargs.get('password'),
        'protocol': r.connection_pool.connection_kwargs.get('protocol', 3),
    }

    # Create multiple async Redis clients for true parallelism
    num_connections = concurrency
    async_clients = []

    try:
        # Create multiple async Redis clients
        for _ in range(num_connections):
            client = aioredis.Redis(**connection_kwargs)
            async_clients.append(client)

        async def insert_batch(client_id: int, start_idx: int, end_idx: int, worker_seed: int):
            """Async worker that inserts a batch of documents."""
            # Use round-robin to assign connection
            client = async_clients[client_id % num_connections]
            rnd = random.Random(worker_seed)
            pipe = client.pipeline(transaction=False)
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
                    await pipe.execute()

            if written % chunk:
                await pipe.execute()

            return end_idx - start_idx

        # Divide work into batches
        docs_per_batch = n_docs // concurrency
        tasks = []

        for batch_id in range(concurrency):
            start_idx = batch_id * docs_per_batch
            if batch_id == concurrency - 1:
                end_idx = n_docs  # Last batch takes remainder
            else:
                end_idx = start_idx + docs_per_batch

            # Different seed per batch to avoid duplicate random sequences
            worker_seed = seed + batch_id
            tasks.append(insert_batch(batch_id, start_idx, end_idx, worker_seed))

        # Execute all batches concurrently
        results = await asyncio.gather(*tasks)
        return sum(results)

    finally:
        # Close all async connections
        await asyncio.gather(*[client.aclose() for client in async_clients])

