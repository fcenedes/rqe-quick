"""
Schema-driven seeding implementations for Redis RediSearch benchmarks.
"""

from .schema_based import (
    seed_from_schema_naive,
    seed_from_schema_threaded,
    seed_from_schema_async,
    generate_document,
    generate_all_documents,
)

__all__ = [
    "seed_from_schema_naive",
    "seed_from_schema_threaded",
    "seed_from_schema_async",
    "generate_document",
    "generate_all_documents",
]

