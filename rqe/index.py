"""
Redis RediSearch index management.
"""

from time import time, sleep
from typing import Optional, List, Tuple
from .helpers import _to_text


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


def create_index_from_schema(r, schema, *, if_exists: str = "reuse") -> str:
    """
    Create a RediSearch index from a BenchmarkSchema.

    Args:
        r: Redis client
        schema: BenchmarkSchema object
        if_exists: What to do if index exists ("reuse", "drop", "recreate")

    Returns:
        "created" | "reused" | "recreated"
    """
    from .schema.models import BenchmarkSchema

    if not isinstance(schema, BenchmarkSchema):
        raise TypeError(f"Expected BenchmarkSchema, got {type(schema)}")

    index_name = schema.index.name

    # Check if index exists
    def _info_dict():
        try:
            return r.execute_command("FT.INFO", index_name)
        except Exception:
            return None

    info = _info_dict()
    was_recreated = False

    if info:
        if if_exists == "drop" or if_exists == "recreate":
            r.execute_command("FT.DROPINDEX", index_name, "DD")
            info = None
            was_recreated = True
        elif if_exists == "reuse":
            return "reused"

    if not info:
        # Build FT.CREATE command
        cmd = ["FT.CREATE", index_name]

        # Storage type
        cmd.extend(["ON", schema.index.storage_type.upper()])

        # Prefix
        cmd.extend(["PREFIX", "1", schema.index.prefix])

        # Schema fields
        cmd.append("SCHEMA")

        is_json = schema.index.storage_type.lower() == 'json'

        for field in schema.fields:
            # For JSON storage, use JSONPath syntax ($.fieldname)
            # For HASH storage, use plain field name
            field_path = f"$.{field.name}" if is_json else field.name

            cmd.append(field_path)
            cmd.append("AS")
            cmd.append(field.name)

            # Add field type and attributes
            if field.type == "vector":
                if not field.attrs:
                    raise ValueError(f"Vector field '{field.name}' requires attrs")

                attrs = field.attrs
                # For vector fields, the type is specified as "VECTOR <algorithm> <params>"
                cmd.append("VECTOR")
                cmd.append(attrs.algorithm.upper())

                # Count attributes
                attr_dict = {
                    "TYPE": attrs.datatype.upper(),
                    "DIM": str(attrs.dims),
                    "DISTANCE_METRIC": attrs.distance_metric.upper(),
                }

                if attrs.algorithm.upper() == "HNSW":
                    if attrs.initial_cap:
                        attr_dict["INITIAL_CAP"] = str(attrs.initial_cap)
                    if attrs.m:
                        attr_dict["M"] = str(attrs.m)
                    if attrs.ef_construction:
                        attr_dict["EF_CONSTRUCTION"] = str(attrs.ef_construction)
                    if attrs.ef_runtime:
                        attr_dict["EF_RUNTIME"] = str(attrs.ef_runtime)

                cmd.append(str(len(attr_dict) * 2))
                for k, v in attr_dict.items():
                    cmd.append(k)
                    cmd.append(v)

            elif field.type == "tag":
                cmd.append("TAG")
                if field.attrs:
                    if hasattr(field.attrs, 'separator') and field.attrs.separator:
                        cmd.append("SEPARATOR")
                        cmd.append(field.attrs.separator)
                    if hasattr(field.attrs, 'casesensitive') and field.attrs.casesensitive:
                        cmd.append("CASESENSITIVE")

            elif field.type == "text":
                cmd.append("TEXT")
                if field.attrs:
                    if hasattr(field.attrs, 'weight') and field.attrs.weight:
                        cmd.append("WEIGHT")
                        cmd.append(str(field.attrs.weight))
                    if hasattr(field.attrs, 'nostem') and field.attrs.nostem:
                        cmd.append("NOSTEM")
                    if hasattr(field.attrs, 'phonetic') and field.attrs.phonetic:
                        cmd.append("PHONETIC")
                        cmd.append(field.attrs.phonetic)

            elif field.type == "numeric":
                cmd.append("NUMERIC")
                if field.attrs:
                    if hasattr(field.attrs, 'sortable') and field.attrs.sortable:
                        cmd.append("SORTABLE")
                    if hasattr(field.attrs, 'noindex') and field.attrs.noindex:
                        cmd.append("NOINDEX")

            elif field.type == "geo":
                cmd.append("GEO")
                if field.attrs:
                    if hasattr(field.attrs, 'noindex') and field.attrs.noindex:
                        cmd.append("NOINDEX")

            else:
                # Default: just add the type
                cmd.append(field.type.upper())

        # Execute command
        result = r.execute_command(*cmd)
        if result not in (b"OK", "OK"):
            raise RuntimeError(f"FT.CREATE failed: {result}")

        return "recreated" if was_recreated else "created"


def validate_index_schema(r, schema) -> Tuple[bool, List[str]]:
    """
    Validate that a Redis index matches the schema definition.

    Args:
        r: Redis client
        schema: BenchmarkSchema object

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    from .schema.models import BenchmarkSchema

    if not isinstance(schema, BenchmarkSchema):
        raise TypeError(f"Expected BenchmarkSchema, got {type(schema)}")

    try:
        info = r.execute_command("FT.INFO", schema.index.name)
    except Exception as e:
        return False, [f"Index '{schema.index.name}' does not exist: {e}"]

    return schema.validate_against_redis_index(info)

