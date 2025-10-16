"""
Schema-driven seeding implementations.
"""

import json
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
import asyncio

from ..generators import create_generator
from ..connection import RedisConnectionPool


def generate_document(schema, generators: Dict[str, Any], doc_id: int) -> Dict[str, Any]:
    """
    Generate a single document based on schema.
    
    Args:
        schema: BenchmarkSchema object
        generators: Dict of field_name -> generator
        doc_id: Document ID
        
    Returns:
        Dictionary of field values
    """
    doc = {}
    for field_name, generator in generators.items():
        value = generator.generate()
        
        # Handle vector fields - convert to bytes if needed
        field = schema.get_field(field_name)
        if field and field.type == 'vector':
            # For HASH storage, vectors need to be bytes
            # For JSON storage, vectors can be lists
            if schema.index.storage_type == 'hash':
                from ..generators.vector_gen import vector_to_bytes
                datatype = field.attrs.datatype if field.attrs else 'float32'
                value = vector_to_bytes(value, datatype)
        
        doc[field_name] = value
    
    return doc


def seed_from_schema_naive(
    r,
    schema,
    *,
    n_docs: int = 10_000,
    chunk: int = 2_000,
    seed: int = 42
) -> int:
    """
    Seed data from schema using naive (sequential) approach.
    
    Args:
        r: Redis client
        schema: BenchmarkSchema object
        n_docs: Number of documents to create
        chunk: Pipeline batch size
        seed: Random seed for reproducibility
        
    Returns:
        Number of documents created
    """
    from ..schema.models import BenchmarkSchema
    
    if not isinstance(schema, BenchmarkSchema):
        raise TypeError(f"Expected BenchmarkSchema, got {type(schema)}")
    
    # Create generators for each field
    generators = {}
    for field in schema.fields:
        generators[field.name] = create_generator(field, seed=seed)
    
    prefix = schema.index.prefix
    storage_type = schema.index.storage_type
    
    inserted = 0
    
    for start in range(0, n_docs, chunk):
        end = min(start + chunk, n_docs)
        pipe = r.pipeline(transaction=False)
        
        for i in range(start, end):
            key = f"{prefix}{i}"
            doc = generate_document(schema, generators, i)
            
            if storage_type == 'hash':
                pipe.hset(key, mapping=doc)
            else:  # json
                pipe.execute_command('JSON.SET', key, '$', json.dumps(doc))
        
        pipe.execute()
        inserted += (end - start)
    
    return inserted


def seed_from_schema_threaded(
    r,
    schema,
    *,
    n_docs: int = 10_000,
    chunk: int = 2_000,
    seed: int = 42,
    concurrency: int = 4,
    connection_pool: RedisConnectionPool = None
) -> int:
    """
    Seed data from schema using threaded approach.
    
    Args:
        r: Redis client (used for connection parameters if pool not provided)
        schema: BenchmarkSchema object
        n_docs: Number of documents to create
        chunk: Pipeline batch size per worker
        seed: Random seed for reproducibility
        concurrency: Number of parallel workers
        connection_pool: Optional connection pool (created if not provided)
        
    Returns:
        Number of documents created
    """
    from ..schema.models import BenchmarkSchema
    
    if not isinstance(schema, BenchmarkSchema):
        raise TypeError(f"Expected BenchmarkSchema, got {type(schema)}")
    
    # Create connection pool if not provided
    cleanup = False
    if connection_pool is None:
        connection_pool = RedisConnectionPool(
            host=r.connection_pool.connection_kwargs.get('host', 'localhost'),
            port=r.connection_pool.connection_kwargs.get('port', 6379),
            db=r.connection_pool.connection_kwargs.get('db', 0),
            username=r.connection_pool.connection_kwargs.get('username'),
            password=r.connection_pool.connection_kwargs.get('password'),
            pool_size=concurrency
        )
        cleanup = True
    
    prefix = schema.index.prefix
    storage_type = schema.index.storage_type
    
    # Calculate work distribution
    docs_per_worker = n_docs // concurrency
    remainder = n_docs % concurrency
    
    def worker(worker_id: int, start_idx: int, end_idx: int, worker_seed: int) -> int:
        """Worker function to insert a batch of documents."""
        # Get connection for this worker
        conn = connection_pool.get_connection(worker_id)
        
        # Create generators with worker-specific seed
        generators = {}
        for field in schema.fields:
            generators[field.name] = create_generator(field, seed=worker_seed)
        
        # Skip to the right position in the random sequence
        for _ in range(start_idx):
            for gen in generators.values():
                gen.generate()
        
        inserted = 0
        for batch_start in range(start_idx, end_idx, chunk):
            batch_end = min(batch_start + chunk, end_idx)
            pipe = conn.pipeline(transaction=False)
            
            for i in range(batch_start, batch_end):
                key = f"{prefix}{i}"
                doc = generate_document(schema, generators, i)
                
                if storage_type == 'hash':
                    pipe.hset(key, mapping=doc)
                else:  # json
                    pipe.execute_command('JSON.SET', key, '$', json.dumps(doc))
            
            pipe.execute()
            inserted += (batch_end - batch_start)
        
        return inserted
    
    # Create tasks
    tasks = []
    current_idx = 0
    
    for i in range(concurrency):
        worker_docs = docs_per_worker + (1 if i < remainder else 0)
        if worker_docs == 0:
            break
        
        start_idx = current_idx
        end_idx = current_idx + worker_docs
        worker_seed = seed + i
        
        tasks.append((i, start_idx, end_idx, worker_seed))
        current_idx = end_idx
    
    # Execute in parallel
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker, *task) for task in tasks]
            results = [f.result() for f in futures]
        
        return sum(results)
    
    finally:
        if cleanup:
            connection_pool.close_all()


async def seed_from_schema_async(
    r,
    schema,
    *,
    n_docs: int = 10_000,
    chunk: int = 2_000,
    seed: int = 42,
    concurrency: int = 4
) -> int:
    """
    Seed data from schema using async approach.
    
    Args:
        r: Redis client (used for connection parameters)
        schema: BenchmarkSchema object
        n_docs: Number of documents to create
        chunk: Pipeline batch size per worker
        seed: Random seed for reproducibility
        concurrency: Number of parallel workers
        
    Returns:
        Number of documents created
    """
    from ..schema.models import BenchmarkSchema
    import redis.asyncio as aioredis
    
    if not isinstance(schema, BenchmarkSchema):
        raise TypeError(f"Expected BenchmarkSchema, got {type(schema)}")
    
    # Get connection parameters
    connection_kwargs = {
        'host': r.connection_pool.connection_kwargs.get('host', 'localhost'),
        'port': r.connection_pool.connection_kwargs.get('port', 6379),
        'db': r.connection_pool.connection_kwargs.get('db', 0),
        'username': r.connection_pool.connection_kwargs.get('username'),
        'password': r.connection_pool.connection_kwargs.get('password'),
        'protocol': r.connection_pool.connection_kwargs.get('protocol', 3),
    }
    
    prefix = schema.index.prefix
    storage_type = schema.index.storage_type
    
    # Calculate work distribution
    docs_per_worker = n_docs // concurrency
    remainder = n_docs % concurrency
    
    # Create async Redis clients
    num_connections = concurrency
    async_clients = []
    
    try:
        for _ in range(num_connections):
            client = aioredis.Redis(**connection_kwargs)
            async_clients.append(client)
        
        async def insert_batch(client_id: int, start_idx: int, end_idx: int, worker_seed: int) -> int:
            """Async worker to insert a batch of documents."""
            client = async_clients[client_id % num_connections]
            
            # Create generators with worker-specific seed
            generators = {}
            for field in schema.fields:
                generators[field.name] = create_generator(field, seed=worker_seed)
            
            # Skip to the right position in the random sequence
            for _ in range(start_idx):
                for gen in generators.values():
                    gen.generate()
            
            inserted = 0
            for batch_start in range(start_idx, end_idx, chunk):
                batch_end = min(batch_start + chunk, end_idx)
                pipe = client.pipeline(transaction=False)
                
                for i in range(batch_start, batch_end):
                    key = f"{prefix}{i}"
                    doc = generate_document(schema, generators, i)
                    
                    if storage_type == 'hash':
                        await pipe.hset(key, mapping=doc)
                    else:  # json
                        await pipe.execute_command('JSON.SET', key, '$', json.dumps(doc))
                
                await pipe.execute()
                inserted += (batch_end - batch_start)
            
            return inserted
        
        # Create tasks
        tasks = []
        current_idx = 0
        
        for i in range(concurrency):
            worker_docs = docs_per_worker + (1 if i < remainder else 0)
            if worker_docs == 0:
                break
            
            start_idx = current_idx
            end_idx = current_idx + worker_docs
            worker_seed = seed + i
            
            tasks.append(insert_batch(i, start_idx, end_idx, worker_seed))
            current_idx = end_idx
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        return sum(results)
    
    finally:
        # Close all async connections
        await asyncio.gather(*[client.aclose() for client in async_clients])

