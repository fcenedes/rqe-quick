# Redis RediSearch Performance Benchmark

High-performance Redis RediSearch benchmarking tool with optimized parallel operations, connection pooling, and comprehensive performance comparisons.

## Features

✅ **Optimized Performance**
- Parallel workers with connection pooling
- Large pipeline batches for reduced round trips
- Configurable parallelism and batch sizes

✅ **Flexible Configuration**
- Environment-based configuration via `.env` file
- Support for local Redis and Redis Cloud
- Username/password authentication support

✅ **Comprehensive Testing**
- Original vs optimized function comparison
- Top-K and cursor-based aggregation
- Detailed performance metrics

✅ **Production Ready**
- Secure credential management
- Connection pooling
- Proper resource cleanup

---

## Prerequisites

This project uses **[uv](https://github.com/astral-sh/uv)** for fast, reliable Python package management.

### Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

---

## Quick Start

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

**Requirements**:
- `redis>=5.0.0` - Redis client for Python
- `python-dotenv>=1.0.0` - Environment variable management

### 2. Configure Redis Connection

```bash
# Copy the sample configuration
cp .env.sample .env

# Edit with your settings
nano .env
```

**For local Redis** (default):
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_USERNAME=
REDIS_PASSWORD=
```

**For Redis Cloud**:
```bash
REDIS_HOST=your-redis-cloud-host.com
REDIS_PORT=11127
REDIS_USERNAME=default
REDIS_PASSWORD=your-password-here
```

### 3. Test Configuration

```bash
# Verify configuration and connection
python test_config.py
```

### 4. Run Benchmark

```bash
# Full performance comparison
python main.py

# Quick functionality test
python test_quick.py
```

---

## Configuration

All configuration is managed via the `.env` file:

### Redis Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis server hostname | `localhost` |
| `REDIS_PORT` | Redis server port | `6379` |
| `REDIS_DB` | Redis database number | `0` |
| `REDIS_USERNAME` | Redis username (empty for no auth) | _(empty)_ |
| `REDIS_PASSWORD` | Redis password (empty for no auth) | _(empty)_ |

### Performance Settings

| Variable | Description | Default | Recommended |
|----------|-------------|---------|-------------|
| `PARALLEL_WORKERS` | Number of concurrent workers | `4` | `2` for local, `4` for remote |
| `CONNECTION_POOL_SIZE` | Size of connection pool | `4` | Match `PARALLEL_WORKERS` |
| `SEED_BATCH_SIZE` | Pipeline batch size for seeding | `20000` | `50000` for local, `30000` for remote |
| `AGGREGATE_BATCH_SIZE` | Cursor batch size for aggregation | `20000` | `50000` for local, `30000` for remote |

See [`ENV_SETUP.md`](ENV_SETUP.md) for detailed configuration guide.

---

## Performance Tuning

### For Single Redis Instance (Local)

```bash
# .env
PARALLEL_WORKERS=2
CONNECTION_POOL_SIZE=2
SEED_BATCH_SIZE=50000
AGGREGATE_BATCH_SIZE=50000
```

**Why?** Redis is single-threaded, so the real performance gain comes from larger batch sizes, not parallelism.

### For Redis Cloud (Remote)

```bash
# .env
PARALLEL_WORKERS=4
CONNECTION_POOL_SIZE=4
SEED_BATCH_SIZE=30000
AGGREGATE_BATCH_SIZE=30000
```

**Why?** Parallel connections help hide network latency, and moderate batch sizes balance memory usage.

### For Redis Cluster (Multiple Shards)

```bash
# .env
PARALLEL_WORKERS=8
CONNECTION_POOL_SIZE=8
SEED_BATCH_SIZE=20000
AGGREGATE_BATCH_SIZE=20000
```

**Why?** Parallelism actually helps with multiple Redis instances/shards!

See [`WHEN_PARALLELISM_HELPS.md`](WHEN_PARALLELISM_HELPS.md) for detailed analysis.

---

## Project Structure

```
.
├── main.py                          # Main benchmark script
├── test_config.py                   # Test configuration loading
├── test_quick.py                    # Quick functionality test
├── requirements.txt                 # Python dependencies
│
├── .env                             # Your configuration (NOT committed)
├── .env.sample                      # Configuration template (committed)
├── .gitignore                       # Protects .env from being committed
│
├── README.md                        # This file
├── ENV_SETUP.md                     # Environment setup guide
├── CONFIGURATION.md                 # Performance tuning guide
├── WHEN_PARALLELISM_HELPS.md        # When to use parallelism
├── REDIS_CLOUD_SETUP.md             # Redis Cloud connection guide
├── ARCHITECTURE_IMPROVEMENTS.md     # Architecture documentation
├── OPTIMIZATION_SUMMARY.md          # Optimization details
└── config_examples.py               # Configuration examples
```

---

## Usage Examples

### Basic Usage

```python
import redis
from main import (
    seed_dummy_hash_docs_fast,
    count_by_fields_resp3_fast,
    RedisConnectionPool
)

# Create Redis client
r = redis.Redis(host="localhost", port=6379, db=0, protocol=3)

# Create connection pool
pool = RedisConnectionPool(
    host="localhost",
    port=6379,
    db=0,
    pool_size=4
)

# Seed data (fast version)
seed_dummy_hash_docs_fast(
    r,
    prefix="order:",
    n_docs=1_000_000,
    chunk=50_000,
    n_workers=4,
    connection_pool=pool
)

# Aggregate data (fast version)
counts, elapsed = count_by_fields_resp3_fast(
    r,
    index="idx_orders",
    query="*",
    fields=["country", "status"],
    batch_size=50_000,
    n_workers=4,
    connection_pool=pool
)

# Cleanup
pool.close_all()
```

### Redis Cloud Connection

```python
import redis
from main import RedisConnectionPool

# Connect to Redis Cloud
r = redis.Redis(
    host="redis-11127.internal.c48004.eu-west9-mz.gcp.cloud.rlrcp.com",
    port=11127,
    db=0,
    username="default",
    password="your-password-here",
    protocol=3
)

# Create pool with authentication
pool = RedisConnectionPool(
    host="redis-11127.internal.c48004.eu-west9-mz.gcp.cloud.rlrcp.com",
    port=11127,
    db=0,
    username="default",
    password="your-password-here",
    pool_size=4
)
```

---

## Performance Results

### Single Redis Instance (Local)

```
Configuration:
  Parallel workers:      2
  Seed batch size:       50,000

Results:
  Seeding speedup:       ~8x (from batch size increase)
  Top-K speedup:         ~1.1x (minimal from parallelism)
  Cursor speedup:        ~1.1x (minimal from parallelism)
```

**Key insight**: For single Redis, batch size matters more than parallelism.

### Redis Cluster (8 Shards)

```
Configuration:
  Parallel workers:      8
  Seed batch size:       20,000

Results:
  Seeding speedup:       ~25x (parallelism + batching)
  Top-K speedup:         ~8x (linear with shard count)
  Cursor speedup:        ~8x (linear with shard count)
```

**Key insight**: Parallelism provides linear speedup with Redis Cluster.

---

## Security

### Credential Management

✅ **DO**:
- Use `.env` file for credentials (already in `.gitignore`)
- Use environment variables in production
- Use secrets management (AWS Secrets Manager, etc.)

❌ **DON'T**:
- Commit `.env` to git (protected by `.gitignore`)
- Hardcode credentials in code
- Share `.env` files directly

### File Permissions

```bash
# Restrict .env file permissions
chmod 600 .env
```

---

## Documentation

- **[ENV_SETUP.md](ENV_SETUP.md)** - Complete environment setup guide
- **[CONFIGURATION.md](CONFIGURATION.md)** - Performance tuning guide
- **[WHEN_PARALLELISM_HELPS.md](WHEN_PARALLELISM_HELPS.md)** - When to use parallelism
- **[REDIS_CLOUD_SETUP.md](REDIS_CLOUD_SETUP.md)** - Redis Cloud connection guide
- **[ARCHITECTURE_IMPROVEMENTS.md](ARCHITECTURE_IMPROVEMENTS.md)** - Architecture details

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'dotenv'"

```bash
# Using uv
uv pip install python-dotenv
# or
uv pip install -r requirements.txt

# Using pip
pip install python-dotenv
# or
pip install -r requirements.txt
```

### "Connection refused"

Check your Redis connection settings in `.env`:
```bash
python test_config.py
```

### "Authentication failed"

Verify username and password in `.env`:
```bash
REDIS_USERNAME=default
REDIS_PASSWORD=your-actual-password
```

### Performance not improving

For single Redis instance, focus on batch size, not parallelism:
```bash
PARALLEL_WORKERS=2
SEED_BATCH_SIZE=50000
```

See [WHEN_PARALLELISM_HELPS.md](WHEN_PARALLELISM_HELPS.md) for details.

---

## License

This project is provided as-is for benchmarking and testing purposes.

---

## Contributing

Contributions welcome! Please ensure:
- Configuration stays in `.env` file
- No credentials in code
- Documentation is updated
- Tests pass

---

## Support

For issues or questions:
1. Check the documentation in the `*.md` files
2. Run `python test_config.py` to verify setup
3. Review [WHEN_PARALLELISM_HELPS.md](WHEN_PARALLELISM_HELPS.md) for performance tuning

