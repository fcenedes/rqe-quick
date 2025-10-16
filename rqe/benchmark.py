"""
Benchmark runner for Redis RediSearch performance tests.
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
from .index import ensure_index_hash, wait_until_indexed
from .seeding import (
    seed_dummy_hash_docs_naive,
    seed_dummy_hash_docs_threaded,
    seed_dummy_hash_docs_async
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


class BenchmarkRunner:
    """Runs benchmarks for different approaches."""
    
    def __init__(
        self,
        index: str = "idx:orders",
        prefix: str = "order:",
        n_docs: int = 200_000,
        fields: List[str] = None
    ):
        """
        Initialize benchmark runner.
        
        Args:
            index: Index name
            prefix: Key prefix for documents
            n_docs: Number of documents to seed
            fields: Fields to aggregate (default: country, category, status)
        """
        self.index = index
        self.prefix = prefix
        self.n_docs = n_docs
        self.fields = fields or ["country", "category", "status"]
        
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
        Setup the index.
        
        Args:
            recreate: Whether to recreate the index
            
        Returns:
            Index state ("created", "reused", "recreated")
        """
        if_exists = "recreate_if_mismatch" if recreate else "reuse"
        return ensure_index_hash(
            self.redis_client,
            index=self.index,
            prefix=self.prefix,
            if_exists=if_exists
        )
    
    def run_seeding(self, approach: str = "naive", progress_callback=None) -> BenchmarkResult:
        """
        Run seeding benchmark.
        
        Args:
            approach: "naive", "threaded", or "async"
            progress_callback: Optional callback for progress updates
            
        Returns:
            BenchmarkResult
        """
        try:
            t0 = perf_counter()
            
            if approach == "naive":
                seed_dummy_hash_docs_naive(
                    self.redis_client,
                    prefix=self.prefix,
                    n_docs=self.n_docs,
                    chunk=Config.SEED_BATCH_SIZE,
                    seed=7
                )
            elif approach == "threaded":
                seed_dummy_hash_docs_threaded(
                    self.redis_client,
                    prefix=self.prefix,
                    n_docs=self.n_docs,
                    chunk=Config.SEED_BATCH_SIZE,
                    seed=7,
                    n_workers=Config.PARALLEL_WORKERS,
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
                    r_async = aioredis.Redis(**Config.get_redis_params())
                    try:
                        await seed_dummy_hash_docs_async(
                            r_async,
                            prefix=self.prefix,
                            n_docs=self.n_docs,
                            chunk=Config.SEED_BATCH_SIZE,
                            seed=7,
                            concurrency=Config.PARALLEL_WORKERS
                        )
                    finally:
                        await r_async.aclose()
                
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
            BenchmarkResult
        """
        try:
            if test_type == "topk":
                topn = 10
                batch_size = None
            else:  # cursor
                topn = None
                batch_size = Config.AGGREGATE_BATCH_SIZE
            
            if approach == "naive":
                _, elapsed = count_by_fields_resp3_naive(
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
                _, elapsed = count_by_fields_resp3_threaded(
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
                        _, elapsed = await count_by_fields_resp3_async(
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
                        return elapsed
                    finally:
                        await r_async.aclose()
                
                elapsed = asyncio.run(run_async())
            else:
                raise ValueError(f"Unknown approach: {approach}")
            
            result = BenchmarkResult(
                name=f"aggregation_{test_type}",
                approach=approach,
                elapsed_time=elapsed,
                success=True
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

