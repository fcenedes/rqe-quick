import random
import os
from time import perf_counter, time, sleep
from typing import Dict, Iterable, List, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import redis
from dotenv import load_dotenv


# -----------------------------
# Configuration (Load from .env)
# -----------------------------
# Load environment variables from .env file
load_dotenv()

# Redis Connection Settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME") or None  # Empty string becomes None
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None  # Empty string becomes None

# Performance Settings
PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "4"))
CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", "4"))
SEED_BATCH_SIZE = int(os.getenv("SEED_BATCH_SIZE", "20000"))
AGGREGATE_BATCH_SIZE = int(os.getenv("AGGREGATE_BATCH_SIZE", "20000"))


# -----------------------------
# Connection Pool Manager
# -----------------------------
class RedisConnectionPool:
    """Thread-safe pool of pre-allocated Redis connections for parallel workers."""

    def __init__(self, host: str, port: int, db: int, pool_size: int,
                 username: Optional[str] = None, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.db = db
        self.pool_size = pool_size
        self.username = username
        self.password = password
        self._connections = []
        self._lock = Lock()
        self._initialized = False

    def _initialize(self):
        """Lazy initialization of connection pool."""
        with self._lock:
            if not self._initialized:
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
                    self._connections.append(conn)
                self._initialized = True

    def get_connection(self, worker_id: int) -> redis.Redis:
        """Get a connection for a specific worker (round-robin)."""
        if not self._initialized:
            self._initialize()
        return self._connections[worker_id % self.pool_size]

    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
            self._initialized = False


# -----------------------------
# RESP3-only GROUPBY/COUNT helper
# -----------------------------

# Helper functions (externalized for reuse in fast version)
def _ensure_at(f: str) -> str:
    return f if f.startswith("@") else f"@{f}"

def _strip_at(f: str) -> str:
    return f[1:] if f.startswith("@") else f

def _to_text(x: Any) -> str:
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x)

def _resp3_rows_to_dicts(resp: dict, cached_attrs: Optional[List[str]] = None) -> Tuple[List[dict], Optional[List[str]]]:
    """RESP3: normalize rows (supports extra_attributes and attributes+values)"""
    attrs = cached_attrs
    if attrs is None:
        a = resp.get("attributes") or resp.get(b"attributes")
        if isinstance(a, (list, tuple)) and a:
            attrs = [_to_text(x).lstrip("@") for x in a]
    rows = resp.get("results") or resp.get(b"results") or []
    out: List[dict] = []
    for row in rows:
        rowmap: dict = {}
        ea = row.get("extra_attributes") or row.get(b"extra_attributes")
        if isinstance(ea, dict):
            for k, v in ea.items():
                rowmap[_to_text(k).lstrip("@")] = v
        if attrs:
            vals = row.get("values") or row.get(b"values")
            if isinstance(vals, (list, tuple)):
                for name, val in zip(attrs, vals):
                    rowmap[name] = val
        out.append(rowmap)
    return out, attrs

def _rows_from_resp2(resp_any) -> List[dict]:
    """RESP2 helpers"""
    if not isinstance(resp_any, (list, tuple)) or not resp_any:
        return []
    out = []
    for row in resp_any[1:]:
        if isinstance(row, (list, tuple)):
            d = {}
            it = iter(row)
            for k, v in zip(it, it):
                d[_to_text(k).lstrip("@")] = v
            out.append(d)
    return out

def _parse_initial(resp_any) -> Tuple[List[dict], int, Optional[List[str]]]:
    """Unified page parser for initial response"""
    if isinstance(resp_any, dict):  # RESP3
        rows, attrs = _resp3_rows_to_dicts(resp_any, None)
        cursor = (resp_any.get("cursor") or resp_any.get(b"cursor") or 0)
        return rows, int(cursor), attrs
    rows = _rows_from_resp2(resp_any)  # RESP2
    cur = 0
    if isinstance(resp_any, (list, tuple)):
        for i in range(len(resp_any) - 2):
            tok = resp_any[i]
            if isinstance(tok, (bytes, str)) and _to_text(tok).lower() == "cursor":
                try: cur = int(resp_any[i + 1])
                except Exception: cur = 0
                break
    return rows, cur, None

def _parse_read(resp_any, attrs_cache: Optional[List[str]]) -> List[dict]:
    """Parse cursor read response"""
    if isinstance(resp_any, dict):
        rows, _ = _resp3_rows_to_dicts(resp_any, attrs_cache)
        return rows
    return _rows_from_resp2(resp_any)

def _val_and_count(row: dict, field_plain: str) -> Optional[Tuple[str, int]]:
    """Extract value and count from row"""
    v = row.get(field_plain)
    c = row.get("count")
    if v is None or c is None: return None
    return _to_text(v), int(c)


def count_by_fields_resp3(
    r,
    index: str,
    fields: Iterable[str],
    query: str = "*",
    *,
    batch_size: int = 10_000,
    topn: Optional[int] = None,
    dialect: int = 4,
    timeout_ms: Optional[int] = None,
    max_groups_per_field: Optional[int] = None,
    sort_by_count_desc: bool = True
) -> Tuple[Dict[str, List[Tuple[str, int]]], float]:
    """Counts docs per distinct value for each field. RESP3/RESP2 tolerant."""

    start_time = perf_counter()
    fields = list(fields)
    specs = [(_ensure_at(f), _strip_at(f)) for f in fields]
    out: Dict[str, List[Tuple[str, int]]] = {plain: [] for _, plain in specs}

    # --- Fast path: server-side Top-K (no cursor) ---
    if topn is not None:
        pipe = r.pipeline(transaction=False)
        for f_at, _ in specs:
            args = [
                "FT.AGGREGATE", index, query,
                "GROUPBY", "1", f_at,
                "REDUCE", "COUNT", "0", "AS", "count",
                "SORTBY", "2", "@count", "DESC", "MAX", int(topn),
            ]
            if timeout_ms is not None: args += ["TIMEOUT", int(timeout_ms)]
            args += ["DIALECT", int(dialect)]
            pipe.execute_command(*args)
        replies = pipe.execute()

        for (f_at, plain), resp in zip(specs, replies):
            rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
            out[plain] = [vc for row in rows if (vc := _val_and_count(row, plain))]
        return out, perf_counter() - start_time

    # --- Cursor path: kick off cursors (NO MAXIDLE) ---
    pipe = r.pipeline(transaction=False)
    for f_at, _ in specs:
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
        pipe.execute_command(*args)
    initial_replies = pipe.execute()

    attr_names_by_field: Dict[str, Optional[List[str]]] = {}
    active: Dict[int, str] = {}  # cursor_id -> field

    # Parse initial pages
    for (f_at, plain), resp in zip(specs, initial_replies):
        rows, cursor, attrs = _parse_initial(resp)
        attr_names_by_field[plain] = attrs
        buf = out[plain]
        for row in rows:
            if vc := _val_and_count(row, plain):
                buf.append(vc)
                if max_groups_per_field and len(buf) >= max_groups_per_field:
                    cursor = 0
                    break
        if cursor and not (max_groups_per_field and len(buf) >= max_groups_per_field):
            active[cursor] = plain

    # If no active cursor and empty rows, fallback once without cursor
    if not active:
        need_fallback = [plain for (_, plain) in specs if len(out[plain]) == 0]
        if need_fallback:
            pipe = r.pipeline(transaction=False)
            for f_at, plain in [(_ensure_at(x), x) for x in need_fallback]:
                args = [
                    "FT.AGGREGATE", index, query,
                    "GROUPBY", "1", f_at,
                    "REDUCE", "COUNT", "0", "AS", "count",
                ]
                if sort_by_count_desc: args += ["SORTBY", "2", "@count", "DESC"]
                if timeout_ms is not None: args += ["TIMEOUT", int(timeout_ms)]
                args += ["DIALECT", int(dialect)]
                pipe.execute_command(*args)
            for plain, resp in zip(need_fallback, pipe.execute()):
                rows = _resp3_rows_to_dicts(resp, None)[0] if isinstance(resp, dict) else _rows_from_resp2(resp)
                out[plain] = [vc for row in rows if (vc := _val_and_count(row, plain))]
        return out, perf_counter() - start_time

    # Round-robin READ
    while active:
        pipe = r.pipeline(transaction=False)
        order: List[int] = []
        for c in list(active.keys()):
            pipe.execute_command("FT.CURSOR", "READ", index, c, "COUNT", int(batch_size))
            order.append(c)
        pages = pipe.execute()

        to_close: List[int] = []
        for c, page in zip(order, pages):
            plain = active[c]
            rows = _parse_read(page, attr_names_by_field.get(plain))
            if not rows:
                to_close.append(c)
                continue
            buf = out[plain]
            stop = False
            for row in rows:
                if vc := _val_and_count(row, plain):
                    buf.append(vc)
                    if max_groups_per_field and len(buf) >= max_groups_per_field:
                        stop = True
                        break
            if stop:
                to_close.append(c)

        if to_close:
            pipe = r.pipeline(transaction=False)
            for c in to_close: pipe.execute_command("FT.CURSOR", "DEL", index, c)
            try: pipe.execute()
            except Exception: pass
            for c in to_close: active.pop(c, None)

    return out, perf_counter() - start_time


def count_by_fields_resp3_fast(
    r: redis.Redis,
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
    n_workers: Optional[int] = None,
    connection_pool: Optional[RedisConnectionPool] = None
) -> Tuple[Dict[str, List[Tuple[str, int]]], float]:
    """
    Optimized parallel version of count_by_fields_resp3.
    Uses multiple threads with pre-allocated Redis connections for parallel field aggregation.

    Args:
        connection_pool: Optional pre-allocated connection pool. If None, creates temporary connections.
    """
    if n_workers is None:
        n_workers = min(os.cpu_count() or 4, 8)

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
            pool_size=min(n_workers, len(specs))
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
            with ThreadPoolExecutor(max_workers=min(n_workers, len(specs))) as executor:
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
        with ThreadPoolExecutor(max_workers=min(n_workers, len(specs))) as executor:
            futures = [executor.submit(worker_cursor, i, f_at, plain) for i, (f_at, plain) in enumerate(specs)]
            for future in as_completed(futures):
                plain, result = future.result()
                out[plain] = result
    finally:
        if temp_pool is not None:
            temp_pool.close_all()

    return out, perf_counter() - start_time


# -----------------------------
# Schema + Dummy data generator
# -----------------------------
def ensure_index_hash(
    r,
    index: str,
    prefix: str,
    *,
    if_exists: str = "reuse"  # "reuse" | "drop" | "recreate_if_mismatch"
) -> str:
    """
    Ensure a HASH index exists with expected schema.
    Returns: "created" | "reused" | "recreated"
    """
    expected = [
        ("country",  "TAG"),
        ("category", "TAG"),
        ("status",   "TAG"),
        ("price",    "NUMERIC"),
        ("ts",       "NUMERIC"),
    ]

    def _ok(resp): return resp in (b"OK", "OK")

    def _info_dict():
        try:
            return r.execute_command("FT.INFO", index)
        except Exception:
            return None

    info = _info_dict()
    if info:
        if if_exists == "drop":
            r.execute_command("FT.DROPINDEX", index, "DD")
            info = None
        elif if_exists == "recreate_if_mismatch":
            # Check prefix + attribute names/types
            prefixes = (info.get("index_definition") or info.get(b"index_definition") or {}).get("prefixes") \
                       or (info.get(b"index_definition") or {}).get(b"prefixes")
            prefixes = [p.decode() if isinstance(p, bytes) else p for p in (prefixes or [])]
            attrs = info.get("attributes") or info.get(b"attributes") or []
            got = [( (a.get("attribute") or a.get(b"attribute")),
                     (a.get("type") or a.get(b"type")) ) for a in attrs]
            got = [(x.decode() if isinstance(x, bytes) else x,
                    y.decode() if isinstance(y, bytes) else y) for x, y in got]
            exp_ok = set(expected).issubset(set(got)) and (prefix in prefixes)
            if not exp_ok:
                r.execute_command("FT.DROPINDEX", index, "DD")
                info = None

    if not info:
        # Create fresh index
        args = [
            "FT.CREATE", index,
            "ON", "HASH",
            "PREFIX", 1, prefix,
            "SCHEMA",
            "country",  "TAG",     "SORTABLE",
            "category", "TAG",     "SORTABLE",
            "status",   "TAG",     "SORTABLE",
            "price",    "NUMERIC", "SORTABLE",
            "ts",       "NUMERIC", "SORTABLE",
        ]
        ok = r.execute_command(*args)
        if not _ok(ok):
            raise RuntimeError(f"FT.CREATE failed: {ok}")
        return "created" if if_exists != "recreate_if_mismatch" else "recreated"

    return "reused"

def seed_dummy_hash_docs(
    r: redis.Redis,
    *,
    prefix: str,
    n_docs: int = 200_000,
    chunk: int = 2_000,
    seed: int = 42
):
    """
    Insert n_docs HASH docs under the given prefix, pipelined in chunks for speed.
    Fields:
      - country (TAG)
      - category (TAG)
      - status (TAG)
      - price (NUMERIC)
      - ts (NUMERIC epoch seconds)
    """
    rnd = random.Random(seed)
    countries = ["US", "FR", "DE", "IN", "BR", "CN", "GB", "ES", "IT", "JP"]
    categories = ["electronics", "books", "toys", "clothing", "grocery", "beauty", "sports"]
    statuses = ["pending", "paid", "shipped", "delivered", "returned", "cancelled"]

    now = int(time.time())
    day = 86400

    pipe = r.pipeline(transaction=False)
    written = 0
    for i in range(n_docs):
        key = f"{prefix}{i}"
        country = rnd.choice(countries)
        category = rnd.choice(categories)
        status = rnd.choices(statuses, weights=[4, 10, 15, 25, 3, 2], k=1)[0]

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

def seed_dummy_hash_docs_fast(
    r: redis.Redis,
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
        connection_pool: Optional pre-allocated connection pool. If None, creates temporary connections.
    """
    if n_workers is None:
        n_workers = min(os.cpu_count() or 4, 8)

    # Shared constants
    countries = ["US", "FR", "DE", "IN", "BR", "CN", "GB", "ES", "IT", "JP"]
    categories = ["electronics", "books", "toys", "clothing", "grocery", "beauty", "sports"]
    statuses = ["pending", "paid", "shipped", "delivered", "returned", "cancelled"]
    status_weights = [4, 10, 15, 25, 3, 2]
    now = int(time.time())
    day = 86400

    # Create temporary pool if not provided
    temp_pool = None
    if connection_pool is None:
        temp_pool = RedisConnectionPool(
            host=r.connection_pool.connection_kwargs.get('host', 'localhost'),
            port=r.connection_pool.connection_kwargs.get('port', 6379),
            db=r.connection_pool.connection_kwargs.get('db', 0),
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


def wait_until_indexed(
    r,
    index: str,
    *,
    timeout_s: float = 300.0,
    poll_every_s: float = 0.25,
    target: float = 0.999  # 99.9%
) -> float:
    """Poll FT.INFO until percent_indexed >= target (or indexing==0), or timeout."""
    t0 = time()
    last = 0.0

    def _get(info, key):
        if isinstance(info, dict):
            return info.get(key) or info.get(key.encode())
        # RESP2 flat list fallback
        if isinstance(info, (list, tuple)):
            it = iter(info)
            for k, v in zip(it, it):
                if _to_text(k) == key: return v
        return None

    while True:
        info = r.execute_command("FT.INFO", index)
        pct = _get(info, "percent_indexed")
        pct = float(pct) if pct is not None else 1.0
        idx = _get(info, "indexing")
        idx = int(idx) if idx is not None else 0
        last = pct
        if pct >= target or idx == 0:
            return pct
        if time() - t0 > timeout_s:
            return last
        sleep(poll_every_s)

# -----------------------------
# Tiny test harness
# -----------------------------
def main():
    # IMPORTANT: Use a Redis client that talks RESP3 to the server.
    # redis-py will decode RESP3 maps into Python dicts when the server is in RESP3 mode.
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        username=REDIS_USERNAME,
        password=REDIS_PASSWORD,
        decode_responses=False,
        protocol=3
    )

    index = "idx_demo_orders"
    prefix = "order:"
    n_docs = 2_500_000

    # Display configuration
    print("=" * 80)
    print("PERFORMANCE COMPARISON: Original vs Fast (Optimized) Versions")
    print("=" * 80)

    print("\n┌─ CONFIGURATION " + "─" * 62 + "┐")
    print("│")
    print("│ Redis Connection:")
    print(f"│   Host:                  {REDIS_HOST}")
    print(f"│   Port:                  {REDIS_PORT}")
    print(f"│   Database:              {REDIS_DB}")
    print(f"│   Username:              {REDIS_USERNAME if REDIS_USERNAME else '(none)'}")
    print(f"│   Password:              {'●' * 8 if REDIS_PASSWORD else '(none)'}")
    print("│")
    print("│ Performance Settings:")
    print(f"│   Parallel workers:      {PARALLEL_WORKERS}")
    print(f"│   Connection pool size:  {CONNECTION_POOL_SIZE}")
    print(f"│   Seed batch size:       {SEED_BATCH_SIZE:,}")
    print(f"│   Aggregate batch size:  {AGGREGATE_BATCH_SIZE:,}")
    print("│")
    print("│ Test Parameters:")
    print(f"│   Documents to seed:     {n_docs:,}")
    print(f"│   Index name:            {index}")
    print(f"│   Key prefix:            {prefix}")
    print("│")
    print("└" + "─" * 79 + "┘")

    # Initialize connection pool once at the start
    print(f"\nInitializing connection pool ({CONNECTION_POOL_SIZE} connections)...")
    pool = RedisConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        username=REDIS_USERNAME,
        password=REDIS_PASSWORD,
        pool_size=CONNECTION_POOL_SIZE
    )
    print("✓ Connection pool ready")

    # ========== SEEDING COMPARISON ==========
    print("\n" + "=" * 80)
    print("SEEDING PERFORMANCE TEST")
    print("=" * 80)

    # Test 1: Original seeding
    print("\n[1/2] Testing ORIGINAL seed_dummy_hash_docs...")
    state = ensure_index_hash(r, index=index, prefix=prefix, if_exists="recreate_if_mismatch")
    print(f"Index state: {state}")

    t0 = perf_counter()
    seed_dummy_hash_docs(r, prefix=prefix, n_docs=n_docs, chunk=2_000, seed=7)
    time_original_seed = perf_counter() - t0
    print(f"✓ Original seeding completed in {time_original_seed:.2f}s")

    t0 = perf_counter()
    pct = wait_until_indexed(r, index, timeout_s=600, poll_every_s=0.5)
    time_index_original = perf_counter() - t0
    print(f"✓ Index ready: percent_indexed={pct:.4f} in {time_index_original:.2f}s")

    # Test 2: Fast seeding
    print("\n[2/2] Testing OPTIMIZED seed_dummy_hash_docs_fast...")
    state = ensure_index_hash(r, index=index, prefix=prefix, if_exists="recreate_if_mismatch")
    print(f"Index state: {state}")

    t0 = perf_counter()
    seed_dummy_hash_docs_fast(
        r,
        prefix=prefix,
        n_docs=n_docs,
        chunk=SEED_BATCH_SIZE,
        seed=7,
        n_workers=PARALLEL_WORKERS,
        connection_pool=pool
    )
    time_fast_seed = perf_counter() - t0
    print(f"✓ Fast seeding completed in {time_fast_seed:.2f}s")

    t0 = perf_counter()
    pct = wait_until_indexed(r, index, timeout_s=600, poll_every_s=0.5)
    time_index_fast = perf_counter() - t0
    print(f"✓ Index ready: percent_indexed={pct:.4f} in {time_index_fast:.2f}s")

    # Seeding summary
    print("\n" + "-" * 80)
    print("SEEDING SUMMARY:")
    print("-" * 80)
    print(f"Original seeding:  {time_original_seed:>8.2f}s")
    print(f"Fast seeding:      {time_fast_seed:>8.2f}s")
    speedup_seed = time_original_seed / time_fast_seed if time_fast_seed > 0 else 0
    print(f"Speedup:           {speedup_seed:>8.2f}x")
    print(f"\nOriginal indexing: {time_index_original:>8.2f}s")
    print(f"Fast indexing:     {time_index_fast:>8.2f}s")

    # ========== AGGREGATION COMPARISON ==========
    print("\n" + "=" * 80)
    print("AGGREGATION PERFORMANCE TEST (Top-K)")
    print("=" * 80)

    # Test 1: Original Top-K
    print("\n[1/2] Testing ORIGINAL count_by_fields_resp3 (Top-10)...")
    counts_topk_orig, time_topk_orig = count_by_fields_resp3(
        r, index, fields=["country", "category", "status"],
        query="*", topn=10, dialect=4, timeout_ms=20_000
    )
    print(f"✓ Original Top-K completed in {time_topk_orig:.3f}s")

    # Test 2: Fast Top-K
    print("\n[2/2] Testing OPTIMIZED count_by_fields_resp3_fast (Top-10)...")
    counts_topk_fast, time_topk_fast = count_by_fields_resp3_fast(
        r, index,
        query="*",
        fields=["country", "category", "status"],
        topn=10,
        dialect=4,
        timeout_ms=20_000,
        n_workers=PARALLEL_WORKERS,
        connection_pool=pool
    )
    print(f"✓ Fast Top-K completed in {time_topk_fast:.3f}s")

    # Top-K summary
    print("\n" + "-" * 80)
    print("TOP-K AGGREGATION SUMMARY:")
    print("-" * 80)
    print(f"Original Top-K:    {time_topk_orig:>8.3f}s")
    print(f"Fast Top-K:        {time_topk_fast:>8.3f}s")
    speedup_topk = time_topk_orig / time_topk_fast if time_topk_fast > 0 else 0
    print(f"Speedup:           {speedup_topk:>8.2f}x")

    # Show sample results
    print("\nSample Top-10 results (from fast version):")
    for f, rows in counts_topk_fast.items():
        print(f"\nField: {f}")
        for v, c in rows[:5]:  # Show first 5
            print(f"  {v:>12} : {c}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")

    # ========== CURSOR AGGREGATION COMPARISON ==========
    print("\n" + "=" * 80)
    print("AGGREGATION PERFORMANCE TEST (Cursor-based)")
    print("=" * 80)

    # Test 1: Original cursor
    print("\n[1/2] Testing ORIGINAL count_by_fields_resp3 (cursor)...")
    counts_cur_orig, time_cur_orig = count_by_fields_resp3(
        r, index,
        query="*",
        fields=["country", "category", "status"],
        batch_size=AGGREGATE_BATCH_SIZE,
        dialect=4,
        timeout_ms=20_000,
        max_groups_per_field=None
    )
    print(f"✓ Original cursor completed in {time_cur_orig:.3f}s")

    # Test 2: Fast cursor
    print("\n[2/2] Testing OPTIMIZED count_by_fields_resp3_fast (cursor)...")
    counts_cur_fast, time_cur_fast = count_by_fields_resp3_fast(
        r, index,
        query="*",
        fields=["country", "category", "status"],
        batch_size=AGGREGATE_BATCH_SIZE,
        dialect=4,
        timeout_ms=20_000,
        max_groups_per_field=None,
        n_workers=PARALLEL_WORKERS,
        connection_pool=pool
    )
    print(f"✓ Fast cursor completed in {time_cur_fast:.3f}s")

    # Cursor summary
    print("\n" + "-" * 80)
    print("CURSOR AGGREGATION SUMMARY:")
    print("-" * 80)
    print(f"Original cursor:   {time_cur_orig:>8.3f}s")
    print(f"Fast cursor:       {time_cur_fast:>8.3f}s")
    speedup_cur = time_cur_orig / time_cur_fast if time_cur_fast > 0 else 0
    print(f"Speedup:           {speedup_cur:>8.2f}x")

    # Show group counts
    print("\nGroup counts per field (from fast version):")
    for f, rows in counts_cur_fast.items():
        print(f"  {f:>12} : {len(rows)} groups")

    # ========== OVERALL SUMMARY ==========
    print("\n" + "=" * 80)
    print("OVERALL PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"\nSeeding speedup:        {speedup_seed:>8.2f}x")
    print(f"Top-K speedup:          {speedup_topk:>8.2f}x")
    print(f"Cursor speedup:         {speedup_cur:>8.2f}x")
    print("\n" + "=" * 80)

    # Clean up connection pool
    print("\nCleaning up connection pool...")
    pool.close_all()
    print("✓ Connection pool closed")


if __name__ == "__main__":
    main()
