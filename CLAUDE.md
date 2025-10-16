# Claude's Notes - Redis RediSearch Performance Benchmark

This file contains notes and context for Claude (AI assistant) to maintain continuity across sessions.

---

## Project Overview

High-performance Redis RediSearch benchmarking tool with:
- Optimized parallel operations with connection pooling
- Original vs fast function comparisons
- Configuration via `.env` file using `python-dotenv`

---

## Key Decisions & Architecture

### 1. Configuration Management
- **Uses**: `python-dotenv` (standard library, not custom loader)
- **Location**: `.env` file (protected by `.gitignore`)
- **Template**: `.env.sample` (committed to git)
- **Variables**: Redis connection + performance settings

### 2. Connection Pooling
- **Class**: `RedisConnectionPool` in `main.py`
- **Lifecycle**: Created once in `main()`, reused across all operations
- **Thread-safe**: Uses `Lock` for initialization
- **Lazy init**: Connections created on first use

### 3. Performance Optimization Strategy

**For Single Redis Instance** (user's current setup):
- Parallelism provides **minimal benefit** (~5-10% speedup)
- Real gains come from **larger batch sizes** (5-10x speedup)
- Redis is single-threaded, so workers just queue commands

**Recommended settings for single Redis**:
```
PARALLEL_WORKERS=2-4
SEED_BATCH_SIZE=50000
AGGREGATE_BATCH_SIZE=50000
```

**For Redis Cluster** (future):
- Parallelism provides **linear speedup** with shard count
- Each worker → different shard = true parallelism

### 4. User's Current Setup
- **Redis**: Redis Cloud (remote instance)
- **Host**: `redis-11127.c48004.eu-west9-mz.gcp.cloud.rlrcp.com`
- **Port**: `11127`
- **Auth**: Username/password authentication
- **Package Manager**: `uv` (not pip)
- **Dependencies**: Managed via `pyproject.toml` and `uv.lock`

---

## Code Structure

### Main Functions

1. **Original Functions** (baseline):
   - `seed_dummy_hash_docs()` - Sequential seeding
   - `count_by_fields_resp3()` - Sequential aggregation

2. **Optimized Functions** (fast versions):
   - `seed_dummy_hash_docs_fast()` - Parallel seeding with connection pool
   - `count_by_fields_resp3_fast()` - Parallel aggregation with connection pool

3. **Helper Functions** (externalized from original):
   - `_ensure_at()`, `_strip_at()`, `_to_text()`
   - `_resp3_rows_to_dicts()`, `_rows_from_resp2()`
   - `_parse_initial()`, `_parse_read()`, `_val_and_count()`
   - Shared by both original and fast versions

### Configuration Loading

```python
from dotenv import load_dotenv
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
# ... etc
```

### Main Function Flow

```python
def main():
    # 1. Create Redis client with config
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, ...)
    
    # 2. Display configuration (nice box format)
    print("┌─ CONFIGURATION ─...")
    
    # 3. Initialize connection pool ONCE
    pool = RedisConnectionPool(...)
    
    # 4. Run benchmarks (original vs fast)
    # 5. Display results and speedup metrics
    
    # 6. Clean up pool
    pool.close_all()
```

---

## Important Implementation Details

### 1. Password Masking
Passwords displayed as `●●●●●●●●` in output for security

### 2. Empty String → None Conversion
```python
REDIS_USERNAME = os.getenv("REDIS_USERNAME") or None
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
```
Empty strings in `.env` become `None` (no auth)

### 3. Connection Pool Parameters
```python
RedisConnectionPool(
    host, port, db,
    username=None,  # Optional
    password=None,  # Optional
    pool_size=4
)
```

### 4. Worker Assignment
Round-robin: `worker_id % pool_size`

---

## Performance Insights

### Benchmark Results (Single Redis Instance)

User's actual results:
```
Seeding speedup:   1.06x  (minimal)
Top-K speedup:     0.87x  (actually slower!)
Cursor speedup:    1.06x  (minimal)
```

**Why?**
- Redis is single-threaded
- 8 workers just queue commands for 1 Redis thread
- Overhead of thread management > benefit
- Batch size matters more than parallelism

### Optimal Configuration

**Current** (not optimal for single Redis):
```
PARALLEL_WORKERS=8
SEED_BATCH_SIZE=20000
```

**Recommended** (for single Redis):
```
PARALLEL_WORKERS=2
SEED_BATCH_SIZE=50000
```

**For Redis Cloud** (remote, network latency):
```
PARALLEL_WORKERS=4
SEED_BATCH_SIZE=30000
```

---

## Files in Project

### Core Files
- `main.py` - Main script with all functions
- `pyproject.toml` - Project metadata and dependencies (uv)
- `uv.lock` - Locked dependencies (uv)
- `requirements.txt` - Python dependencies (pip fallback)
- `.env` - User's configuration (NOT committed)
- `.env.sample` - Configuration template (committed)
- `.gitignore` - Protects `.env`

### Documentation
- `README.md` - Main documentation (consolidated)
- `CLAUDE.md` - Notes for Claude (this file)

**Note**: User removed all other `.md` files and test files (`test_config.py`, `test_quick.py`, etc.) to keep the project minimal.

---

## Common Tasks

### Add New Configuration Variable

1. Add to `.env.sample`:
   ```
   NEW_VARIABLE=default_value
   ```

2. Add to `main.py`:
   ```python
   NEW_VARIABLE = os.getenv("NEW_VARIABLE", "default_value")
   ```

3. Update display in `main()` if needed

### Modify Connection Pool

Location: `main.py`, class `RedisConnectionPool` (around line 35-70)

Key methods:
- `__init__()` - Store parameters
- `_initialize()` - Lazy connection creation
- `get_connection(worker_id)` - Round-robin assignment
- `close_all()` - Cleanup

### Add New Fast Function

Pattern:
```python
def my_function_fast(..., n_workers=4, connection_pool=None):
    # Create temp pool if not provided
    if connection_pool is None:
        pool = RedisConnectionPool(...)
        cleanup = True
    else:
        pool = connection_pool
        cleanup = False
    
    # Worker function
    def worker(worker_id, ...):
        r = pool.get_connection(worker_id)
        # ... do work ...
    
    # Use ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(worker, i, ...) for i in range(n_workers)]
        # ... collect results ...
    
    # Cleanup if we created pool
    if cleanup:
        pool.close_all()
    
    return results
```

---

## User Preferences

- **Package manager**: `uv` (not pip)
- **Documentation**: Minimal, consolidated (removed most `.md` files)
- **Notes**: Single `CLAUDE.md` file (this file)
- **Configuration**: `.env` file with `python-dotenv`

---

## Known Issues / Limitations

1. **Single Redis bottleneck**: Parallelism doesn't help much
2. **Top-K can be slower**: Thread overhead > benefit for small operations
3. **Memory usage**: Large batch sizes use more memory
4. **Redis Cluster**: Code ready but not tested with actual cluster

---

## Future Improvements (If Requested)

1. **Dynamic batch sizing**: Auto-adjust based on document count
2. **Progress bars**: Show progress during long operations
3. **Metrics export**: Export results to JSON/CSV
4. **Redis Cluster support**: Test and optimize for cluster mode
5. **SSL/TLS support**: Add SSL configuration options
6. **Retry logic**: Handle transient connection failures

---

## Testing

### Quick Config Test
```bash
python -c "from main import REDIS_HOST, REDIS_PORT; print(f'Config loaded: {REDIS_HOST}:{REDIS_PORT}')"
```

### Full Benchmark
```bash
python main.py
```

**Note**: User removed `test_config.py` and `test_quick.py` - only `main.py` remains.

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'dotenv'"
```bash
# User uses uv as package manager
uv sync
```

### Configuration not loading
1. Check `.env` exists
2. Check format: `KEY=value` (no spaces around `=`)
3. Check `load_dotenv()` is called before reading env vars

### Poor performance
1. Check if single Redis instance → reduce workers, increase batch size
2. Check network latency → increase batch size
3. Monitor Redis CPU usage

---

## Last Updated

2025-10-16 - Initial creation with project context and architecture notes

