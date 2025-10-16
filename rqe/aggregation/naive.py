"""
Naive (sequential) aggregation implementation.
"""

from time import perf_counter
from typing import Iterable, Optional, Dict, List, Tuple

from ..helpers import (
    _ensure_at, _strip_at, _to_text,
    _resp3_rows_to_dicts, _rows_from_resp2,
    _parse_initial, _parse_read, _val_and_count
)


def count_by_fields_resp3_naive(
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
    """
    Counts docs per distinct value for each field. RESP3/RESP2 tolerant.
    
    This is the baseline sequential implementation.
    
    Args:
        r: Redis client
        index: Index name
        fields: List of field names to aggregate
        query: Search query (default: "*")
        batch_size: Cursor batch size for pagination
        topn: If set, use server-side Top-K instead of cursor
        dialect: RediSearch dialect version
        timeout_ms: Query timeout in milliseconds
        max_groups_per_field: Maximum groups to return per field
        sort_by_count_desc: Sort results by count descending
        
    Returns:
        Tuple of (results dict, elapsed_time)
        Results dict maps field_name -> [(value, count), ...]
    """
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
            if timeout_ms is not None: 
                args += ["TIMEOUT", int(timeout_ms)]
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
                if sort_by_count_desc: 
                    args += ["SORTBY", "2", "@count", "DESC"]
                if timeout_ms is not None: 
                    args += ["TIMEOUT", int(timeout_ms)]
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
            for c in to_close: 
                pipe.execute_command("FT.CURSOR", "DEL", index, c)
            try: 
                pipe.execute()
            except Exception: 
                pass
            for c in to_close: 
                active.pop(c, None)

    return out, perf_counter() - start_time

