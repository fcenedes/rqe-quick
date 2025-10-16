"""
Async aggregation implementation using asyncio with uvloop.
"""

import asyncio
from time import perf_counter
from typing import Dict, List, Tuple, Iterable, Optional
import redis.asyncio as aioredis

from ..helpers import (
    _ensure_at, _strip_at, _resp3_rows_to_dicts, _rows_from_resp2,
    _val_and_count, _parse_initial, _parse_read
)

__all__ = ["count_by_fields_resp3_async"]


async def count_by_fields_resp3_async(
    r: aioredis.Redis,
    index: str,
    query: str,
    fields: Iterable[str],
    *,
    topn: Optional[int] = None,
    batch_size: int = 10_000,
    max_groups_per_field: Optional[int] = None,
    sort_by_count_desc: bool = True,
    timeout_ms: Optional[int] = None,
    dialect: int = 2,
    concurrency: int = 10
) -> Tuple[Dict[str, List[Tuple[str, int]]], float]:
    """
    Async version using redis.asyncio with uvloop for maximum performance.
    Uses asyncio.gather for concurrent field aggregation with multiple connections.

    Args:
        r: Async Redis client (redis.asyncio.Redis) - used for connection parameters
        index: RediSearch index name
        query: Search query
        fields: List of fields to aggregate
        topn: If set, use server-side Top-K aggregation
        batch_size: Cursor batch size for pagination
        max_groups_per_field: Maximum groups to return per field
        sort_by_count_desc: Sort results by count descending
        timeout_ms: Query timeout in milliseconds
        dialect: RediSearch dialect version
        concurrency: Number of concurrent connections (default: 10)

    Returns:
        Tuple of (results_dict, elapsed_time)
    """
    start_time = perf_counter()
    fields = list(fields)
    specs = [(_ensure_at(f), _strip_at(f)) for f in fields]
    out: Dict[str, List[Tuple[str, int]]] = {plain: [] for _, plain in specs}

    # Create multiple async Redis connections for true parallelism
    # Each connection can handle requests independently
    num_connections = min(concurrency, len(specs))

    # Get connection parameters from the provided client
    connection_kwargs = {
        'host': r.connection_pool.connection_kwargs.get('host', 'localhost'),
        'port': r.connection_pool.connection_kwargs.get('port', 6379),
        'db': r.connection_pool.connection_kwargs.get('db', 0),
        'username': r.connection_pool.connection_kwargs.get('username'),
        'password': r.connection_pool.connection_kwargs.get('password'),
        'protocol': r.connection_pool.connection_kwargs.get('protocol', 3),
    }

    # Create connection pool for async clients
    async_clients = []
    try:
        # Create multiple async Redis clients
        for _ in range(num_connections):
            client = aioredis.Redis(**connection_kwargs)
            async_clients.append(client)

        # --- Fast path: server-side Top-K (concurrent execution) ---
        if topn is not None:
            async def fetch_topk(client_id: int, f_at: str, plain: str):
                """Async worker for top-K aggregation."""
                # Use round-robin to assign connection
                client = async_clients[client_id % num_connections]

                args = [
                    "FT.AGGREGATE", index, query,
                    "GROUPBY", "1", f_at,
                    "REDUCE", "COUNT", "0", "AS", "count",
                    "SORTBY", "2", "@count", "DESC", "MAX", int(topn),
                ]
                if timeout_ms is not None: args += ["TIMEOUT", int(timeout_ms)]
                args += ["DIALECT", int(dialect)]

                resp = await client.execute_command(*args)
                rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
                result = [vc for row in rows if (vc := _val_and_count(row, plain))]
                return plain, result

            # Execute all fields concurrently with different connections
            tasks = [fetch_topk(i, f_at, plain) for i, (f_at, plain) in enumerate(specs)]
            results = await asyncio.gather(*tasks)

            for plain, result in results:
                out[plain] = result

            return out, perf_counter() - start_time

        # --- Cursor path: concurrent cursor management per field ---
        async def fetch_cursor(client_id: int, f_at: str, plain: str):
            """Async worker for cursor-based aggregation."""
            # Use round-robin to assign connection
            client = async_clients[client_id % num_connections]

            # Initial cursor request
            args = [
                "FT.AGGREGATE", index, query,
                "GROUPBY", "1", f_at,
                "REDUCE", "COUNT", "0", "AS", "count",
                "WITHCURSOR", "COUNT", int(batch_size),
            ]
            if sort_by_count_desc:
                args += ["SORTBY", "2", "@count", "DESC"]
            if timeout_ms is not None:
                args += ["TIMEOUT", int(timeout_ms)]
            args += ["DIALECT", int(dialect)]

            resp = await client.execute_command(*args)
            rows, cursor, attrs = _parse_initial(resp)

            result = []
            for row in rows:
                if vc := _val_and_count(row, plain):
                    result.append(vc)
                    if max_groups_per_field and len(result) >= max_groups_per_field:
                        cursor = 0
                        break

            # Continue reading cursor if active
            while cursor and not (max_groups_per_field and len(result) >= max_groups_per_field):
                page = await client.execute_command("FT.CURSOR", "READ", index, cursor, "COUNT", int(batch_size))
                rows = _parse_read(page, attrs)

                if not rows:
                    break

                for row in rows:
                    if vc := _val_and_count(row, plain):
                        result.append(vc)
                        if max_groups_per_field and len(result) >= max_groups_per_field:
                            cursor = 0
                            break

            # Clean up cursor
            if cursor:
                try:
                    await client.execute_command("FT.CURSOR", "DEL", index, cursor)
                except Exception:
                    pass

            # Fallback if empty
            if not result:
                args = [
                    "FT.AGGREGATE", index, query,
                    "GROUPBY", "1", f_at,
                    "REDUCE", "COUNT", "0", "AS", "count",
                ]
                if sort_by_count_desc: args += ["SORTBY", "2", "@count", "DESC"]
                if timeout_ms is not None: args += ["TIMEOUT", int(timeout_ms)]
                args += ["DIALECT", int(dialect)]

                resp = await client.execute_command(*args)
                rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
                result = [vc for row in rows if (vc := _val_and_count(row, plain))]

            return plain, result

        # Execute all fields concurrently with different connections
        tasks = [fetch_cursor(i, f_at, plain) for i, (f_at, plain) in enumerate(specs)]
        results = await asyncio.gather(*tasks)

        for plain, result in results:
            out[plain] = result

        return out, perf_counter() - start_time

    finally:
        # Close all async connections
        await asyncio.gather(*[client.aclose() for client in async_clients])

