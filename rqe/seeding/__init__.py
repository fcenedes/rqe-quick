"""
Seeding implementations for Redis RediSearch benchmarks.
"""

from .naive import seed_dummy_hash_docs_naive
from .threaded import seed_dummy_hash_docs_threaded
from .async_impl import seed_dummy_hash_docs_async

__all__ = [
    "seed_dummy_hash_docs_naive",
    "seed_dummy_hash_docs_threaded",
    "seed_dummy_hash_docs_async",
]

