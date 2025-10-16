"""
Helper functions shared across different implementations.
"""

from typing import Any, List, Dict, Tuple, Optional


def _ensure_at(field: str) -> str:
    """Ensure field name starts with '@'."""
    return field if field.startswith("@") else f"@{field}"


def _strip_at(field: str) -> str:
    """Remove '@' prefix from field name."""
    return field[1:] if field.startswith("@") else field


def _to_text(x: Any) -> str:
    """Convert bytes or any value to text."""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x)


def _resp3_rows_to_dicts(resp: dict, cached_attrs: Optional[List[str]] = None) -> Tuple[List[dict], Optional[List[str]]]:
    """
    RESP3: normalize rows (supports extra_attributes and attributes+values).

    Args:
        resp: RESP3 response dict
        cached_attrs: Optional cached attribute names

    Returns:
        Tuple of (rows as list of dicts, attribute names)
    """
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
    """
    RESP2 helpers: Parse RESP2 aggregation response.

    Args:
        resp_any: Raw RESP2 response

    Returns:
        List of dicts with field values
    """
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
    """
    Unified page parser for initial response.

    Args:
        resp_any: Redis response (RESP2 or RESP3)

    Returns:
        Tuple of (rows, cursor_id, attribute_names)
    """
    if isinstance(resp_any, dict):  # RESP3
        rows, attrs = _resp3_rows_to_dicts(resp_any, None)
        cursor = (resp_any.get("cursor") or resp_any.get(b"cursor") or 0)
        return rows, int(cursor), attrs

    # RESP2
    rows = _rows_from_resp2(resp_any)
    cur = 0
    if isinstance(resp_any, (list, tuple)):
        for i in range(len(resp_any) - 2):
            tok = resp_any[i]
            if isinstance(tok, (bytes, str)) and _to_text(tok).lower() == "cursor":
                try:
                    cur = int(resp_any[i + 1])
                except Exception:
                    cur = 0
                break
    return rows, cur, None


def _parse_read(resp_any, attrs_cache: Optional[List[str]]) -> List[dict]:
    """
    Parse cursor read response.

    Args:
        resp_any: Redis response (RESP2 or RESP3)
        attrs_cache: Optional cached attribute names

    Returns:
        List of row dicts
    """
    if isinstance(resp_any, dict):
        rows, _ = _resp3_rows_to_dicts(resp_any, attrs_cache)
        return rows
    return _rows_from_resp2(resp_any)


def _val_and_count(row: dict, field_plain: str) -> Optional[Tuple[str, int]]:
    """
    Extract value and count from aggregation row.

    Args:
        row: Dict with field value and count
        field_plain: Field name (without @)

    Returns:
        Tuple of (value, count) or None if missing
    """
    v = row.get(field_plain)
    c = row.get("count")
    if v is None or c is None:
        return None
    return _to_text(v), int(c)

