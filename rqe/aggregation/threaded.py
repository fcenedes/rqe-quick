"""
Threaded (parallel) aggregation implementation using ThreadPoolExecutor.
"""

import os
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Iterable, Optional

from ..connection import RedisConnectionPool
from ..helpers import (
    _ensure_at, _strip_at, _resp3_rows_to_dicts, _rows_from_resp2,
    _val_and_count, _parse_initial, _parse_read
)

__all__ = ["count_by_fields_resp3_threaded"]


def count_by_fields_resp3_threaded(
    r,
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
    concurrency: Optional[int] = None,
    connection_pool: Optional[RedisConnectionPool] = None
) -> Tuple[Dict[str, List[Tuple[str, int]]], float]:
    """
    Optimized parallel version of count_by_fields_resp3.
    Uses multiple threads with pre-allocated Redis connections for parallel field aggregation.

    Args:
        r: Redis client (used for connection parameters if pool not provided)
        index: RediSearch index name
        query: Search query
        fields: List of fields to aggregate
        topn: If set, use server-side Top-K aggregation
        batch_size: Cursor batch size for pagination
        max_groups_per_field: Maximum groups to return per field
        sort_by_count_desc: Sort results by count descending
        timeout_ms: Query timeout in milliseconds
        dialect: RediSearch dialect version
        concurrency: Number of worker threads (default: min(cpu_count, 8))
        connection_pool: Optional pre-allocated connection pool. If None, creates temporary connections.

    Returns:
        Tuple of (results_dict, elapsed_time)
    """
    if concurrency is None:
        concurrency = min(os.cpu_count() or 4, 8)

    start_time = perf_counter()
    fields = list(fields)
    specs = [(_ensure_at(f), _strip_at(f)) for f in fields]
    out: Dict[str, List[Tuple[str, int]]] = {plain: [] for _, plain in specs}

    # Create temporary pool if not provided
    temp_pool = None
    if connection_pool is None:
        temp_pool = RedisConnectionPool(
            host=r.connection_pool.connection_kwargs.get('host', 'localhost'),
            port=r.connection_pool.connection_kwargs.get('port', 6379),
            db=r.connection_pool.connection_kwargs.get('db', 0),
            username=r.connection_pool.connection_kwargs.get('username'),
            password=r.connection_pool.connection_kwargs.get('password'),
            pool_size=min(concurrency, len(specs))
        )
        connection_pool = temp_pool

    # --- Fast path: server-side Top-K (parallel execution) ---
    if topn is not None:
        def worker_topn(worker_id: int, f_at: str, plain: str):
            """Worker function for parallel top-K aggregation."""
            worker_r = connection_pool.get_connection(worker_id)

            args = [
                "FT.AGGREGATE", index, query,
                "GROUPBY", "1", f_at,
                "REDUCE", "COUNT", "0", "AS", "count",
                "SORTBY", "2", "@count", "DESC", "MAX", int(topn),
            ]
            if timeout_ms is not None: args += ["TIMEOUT", int(timeout_ms)]
            args += ["DIALECT", int(dialect)]

            resp = worker_r.execute_command(*args)
            rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
            result = [vc for row in rows if (vc := _val_and_count(row, plain))]

            return plain, result

        try:
            with ThreadPoolExecutor(max_workers=min(concurrency, len(specs))) as executor:
                futures = [executor.submit(worker_topn, i, f_at, plain) for i, (f_at, plain) in enumerate(specs)]
                for future in as_completed(futures):
                    plain, result = future.result()
                    out[plain] = result
        finally:
            if temp_pool is not None:
                temp_pool.close_all()

        return out, perf_counter() - start_time

    # --- Cursor path: parallel cursor management per field ---
    def worker_cursor(worker_id: int, f_at: str, plain: str):
        """Worker function for parallel cursor-based aggregation."""
        worker_r = connection_pool.get_connection(worker_id)

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

        resp = worker_r.execute_command(*args)
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
            page = worker_r.execute_command("FT.CURSOR", "READ", index, cursor, "COUNT", int(batch_size))
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
                worker_r.execute_command("FT.CURSOR", "DEL", index, cursor)
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

            resp = worker_r.execute_command(*args)
            rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
            result = [vc for row in rows if (vc := _val_and_count(row, plain))]

        return plain, result

    try:
        with ThreadPoolExecutor(max_workers=min(concurrency, len(specs))) as executor:
            futures = [executor.submit(worker_cursor, i, f_at, plain) for i, (f_at, plain) in enumerate(specs)]
            for future in as_completed(futures):
                plain, result = future.result()
                out[plain] = result
    finally:
        if temp_pool is not None:
            temp_pool.close_all()

    return out, perf_counter() - start_time

