"""
Redis RediSearch index management.
"""

from time import time, sleep
from .helpers import _to_text


def ensure_index_hash(
    r,
    index: str,
    prefix: str,
    *,
    if_exists: str = "reuse"  # "reuse" | "drop" | "recreate_if_mismatch"
) -> str:
    """
    Ensure a HASH index exists with expected schema.
    
    Args:
        r: Redis client
        index: Index name
        prefix: Key prefix for the index
        if_exists: What to do if index exists ("reuse", "drop", "recreate_if_mismatch")
        
    Returns:
        "created" | "reused" | "recreated"
    """
    expected = [
        ("country",  "TAG"),
        ("category", "TAG"),
        ("status",   "TAG"),
        ("price",    "NUMERIC"),
        ("ts",       "NUMERIC"),
    ]

    def _ok(resp): 
        return resp in (b"OK", "OK")

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


def wait_until_indexed(
    r,
    index: str,
    *,
    timeout_s: float = 300.0,
    poll_every_s: float = 0.25,
    target: float = 0.999  # 99.9%
) -> float:
    """
    Poll FT.INFO until percent_indexed >= target (or indexing==0), or timeout.
    
    Args:
        r: Redis client
        index: Index name
        timeout_s: Maximum time to wait in seconds
        poll_every_s: Polling interval in seconds
        target: Target percent_indexed value (0.0-1.0)
        
    Returns:
        Final percent_indexed value
        
    Raises:
        TimeoutError: If timeout is reached before indexing completes
    """
    t0 = time()
    last = 0.0

    def _get(info, key):
        if isinstance(info, dict):
            return info.get(key) or info.get(key.encode())
        # RESP2 flat list fallback
        if isinstance(info, (list, tuple)):
            it = iter(info)
            for k, v in zip(it, it):
                if _to_text(k) == key: 
                    return v
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
        
        elapsed = time() - t0
        if elapsed > timeout_s:
            raise TimeoutError(
                f"Index '{index}' not ready after {timeout_s}s (percent_indexed={last:.4f})"
            )
        
        sleep(poll_every_s)

