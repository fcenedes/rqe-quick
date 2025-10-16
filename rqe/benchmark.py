"""
Schema-driven benchmark runner for Redis RediSearch performance tests.
"""

import asyncio
from time import perf_counter
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import redis
try:
    import redis.asyncio as aioredis
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

from .config import Config
from .connection import RedisConnectionPool
from .index import create_index_from_schema, validate_index_schema, wait_until_indexed
from .schema import load_schema, BenchmarkSchema
from .seeding import (
    seed_from_schema_naive,
    seed_from_schema_threaded,
    seed_from_schema_async,
    generate_all_documents
)
from .aggregation import (
    count_by_fields_resp3_naive,
    count_by_fields_resp3_threaded,
    count_by_fields_resp3_async
)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    approach: str  # "naive", "threaded", "async"
    elapsed_time: float
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict] = None


class BenchmarkRunner:
    """Schema-driven benchmark runner for different approaches."""

    def __init__(
        self,
        schema: BenchmarkSchema = None,
        schema_path: str = "schemas/ecommerce.yaml",
        n_docs: int = 200_000
    ):
        """
        Initialize benchmark runner.

        Args:
            schema: BenchmarkSchema object (if None, loads from schema_path)
            schema_path: Path to schema YAML file (default: schemas/ecommerce.yaml)
            n_docs: Number of documents to seed
        """
        # Load schema
        if schema is None:
            self.schema = load_schema(schema_path)
        else:
            self.schema = schema

        self.schema_path = schema_path
        self.n_docs = n_docs

        # Extract info from schema
        self.index = self.schema.index.name
        self.prefix = self.schema.index.prefix
        self.fields = self.schema.get_aggregation_fields()

        # Create Redis client
        self.redis_client = redis.Redis(**Config.get_redis_params())

        # Create connection pool for threaded operations
        self.connection_pool = RedisConnectionPool(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            username=Config.REDIS_USERNAME,
            password=Config.REDIS_PASSWORD,
            pool_size=Config.CONNECTION_POOL_SIZE
        )

        self.results: List[BenchmarkResult] = []

    def setup_index(self, recreate: bool = True) -> str:
        """
        Setup the index from schema.

        Args:
            recreate: Whether to recreate the index

        Returns:
            Index state ("created", "reused", "recreated")
        """
        if_exists = "drop" if recreate else "reuse"
        return create_index_from_schema(
            self.redis_client,
            schema=self.schema,
            if_exists=if_exists
        )
    
    def run_seeding(self, approach: str = "naive", progress_callback=None) -> BenchmarkResult:
        """
        Run schema-driven seeding benchmark.

        Args:
            approach: "naive", "threaded", or "async"
            progress_callback: Optional callback for progress updates

        Returns:
            BenchmarkResult
        """
        try:
            # STEP 1: Generate all documents BEFORE timing starts (CPU-bound work)
            if progress_callback:
                progress_callback("Generating documents...")

            docs = generate_all_documents(
                self.schema,
                n_docs=self.n_docs,
                seed=Config.RANDOM_SEED
            )

            # STEP 2: Start timing HERE (only Redis I/O is timed)
            t0 = perf_counter()

            if approach == "naive":
                seed_from_schema_naive(
                    self.redis_client,
                    schema=self.schema,
                    docs=docs,
                    chunk=Config.SEED_BATCH_SIZE
                )
            elif approach == "threaded":
                seed_from_schema_threaded(
                    self.redis_client,
                    schema=self.schema,
                    docs=docs,
                    chunk=Config.SEED_BATCH_SIZE,
                    concurrency=Config.PARALLEL_WORKERS,
                    connection_pool=self.connection_pool
                )
            elif approach == "async":
                if not UVLOOP_AVAILABLE:
                    return BenchmarkResult(
                        name="seeding",
                        approach=approach,
                        elapsed_time=0,
                        success=False,
                        error="uvloop not available"
                    )

                async def run_async():
                    await seed_from_schema_async(
                        self.redis_client,
                        schema=self.schema,
                        docs=docs,
                        chunk=Config.SEED_BATCH_SIZE,
                        concurrency=Config.PARALLEL_WORKERS
                    )

                asyncio.run(run_async())
            else:
                raise ValueError(f"Unknown approach: {approach}")

            elapsed = perf_counter() - t0
            
            # Wait for indexing to complete
            if progress_callback:
                progress_callback("Waiting for indexing...")
            
            t0_index = perf_counter()
            wait_until_indexed(self.redis_client, self.index, timeout_s=600, poll_every_s=0.5)
            index_time = perf_counter() - t0_index
            
            result = BenchmarkResult(
                name="seeding",
                approach=approach,
                elapsed_time=elapsed,
                success=True
            )
            self.results.append(result)
            return result
            
        except Exception as e:
            result = BenchmarkResult(
                name="seeding",
                approach=approach,
                elapsed_time=0,
                success=False,
                error=str(e)
            )
            self.results.append(result)
            return result
    
    def run_aggregation(
        self,
        test_type: str = "topk",
        approach: str = "naive",
        progress_callback=None
    ) -> BenchmarkResult:
        """
        Run aggregation benchmark.

        Args:
            test_type: "topk" or "cursor"
            approach: "naive", "threaded", or "async"
            progress_callback: Optional callback for progress updates

        Returns:
            BenchmarkResult with aggregation_results in metadata
        """
        try:
            if test_type == "topk":
                topn = Config.TOPK_DEPTH
                batch_size = None
            else:  # cursor
                topn = None
                batch_size = Config.AGGREGATE_BATCH_SIZE

            if approach == "naive":
                counts, elapsed = count_by_fields_resp3_naive(
                    self.redis_client,
                    self.index,
                    query="*",
                    fields=self.fields,
                    topn=topn,
                    batch_size=batch_size or 10_000,
                    dialect=4,
                    timeout_ms=20_000
                )
            elif approach == "threaded":
                counts, elapsed = count_by_fields_resp3_threaded(
                    self.redis_client,
                    self.index,
                    query="*",
                    fields=self.fields,
                    topn=topn,
                    batch_size=batch_size or 10_000,
                    dialect=4,
                    timeout_ms=20_000,
                    concurrency=Config.PARALLEL_WORKERS,
                    connection_pool=self.connection_pool
                )
            elif approach == "async":
                if not UVLOOP_AVAILABLE:
                    return BenchmarkResult(
                        name=f"aggregation_{test_type}",
                        approach=approach,
                        elapsed_time=0,
                        success=False,
                        error="uvloop not available"
                    )
                
                async def run_async():
                    r_async = aioredis.Redis(**Config.get_redis_params())
                    try:
                        counts, elapsed = await count_by_fields_resp3_async(
                            r_async,
                            self.index,
                            query="*",
                            fields=self.fields,
                            topn=topn,
                            batch_size=batch_size or 10_000,
                            dialect=4,
                            timeout_ms=20_000,
                            concurrency=Config.PARALLEL_WORKERS
                        )
                        return counts, elapsed
                    finally:
                        await r_async.aclose()

                counts, elapsed = asyncio.run(run_async())
            else:
                raise ValueError(f"Unknown approach: {approach}")

            result = BenchmarkResult(
                name=f"aggregation_{test_type}",
                approach=approach,
                elapsed_time=elapsed,
                success=True,
                metadata={"aggregation_results": counts}
            )
            self.results.append(result)
            return result
            
        except Exception as e:
            result = BenchmarkResult(
                name=f"aggregation_{test_type}",
                approach=approach,
                elapsed_time=0,
                success=False,
                error=str(e)
            )
            self.results.append(result)
            return result
    
    def cleanup(self):
        """Cleanup resources."""
        try:
            self.connection_pool.close_all()
            self.redis_client.close()
        except Exception:
            pass

