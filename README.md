# Redis RediSearch Performance Benchmark

High-performance Redis RediSearch benchmarking tool with beautiful CLI, multiple implementation approaches (naive, threaded, async), and comprehensive performance comparisons.

## ✨ Features

✅ **Multiple Implementation Approaches**
- **Naive**: Sequential baseline implementation
- **Threaded**: Parallel workers with connection pooling using `ThreadPoolExecutor`
- **Async**: High-performance async/await with `uvloop` event loop

✅ **Beautiful CLI Interface**
- Rich terminal output with tables and colors
- Animated progress bars with spinners
- Flexible command-line options
- Compare any combination of approaches

✅ **Comprehensive Benchmarks**
- **Seeding**: Bulk document insertion with Redis pipelines
- **Top-K Aggregation**: Fast aggregation with `LIMIT` clause
- **Cursor Aggregation**: Memory-efficient pagination with `FT.CURSOR`

✅ **Flexible Configuration**
- Environment-based configuration via `.env` file
- Support for local Redis, Redis Cloud, and Redis Cluster
- Username/password authentication support

✅ **Production Ready**
- Modular architecture for easy maintenance
- Secure credential management
- Connection pooling with lazy initialization
- Proper resource cleanup

---

## 📋 Prerequisites

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

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Using uv (recommended - uses pyproject.toml)
uv sync

# Or using pip with requirements.txt
pip install -r requirements.txt
```

**Dependencies**:
- `redis>=6.4.0` - Redis client for Python
- `dotenv>=0.9.9` - Environment variable management
- `hiredis>=3.3.0` - High-performance Redis protocol parser
- `uvloop>=0.19.0` - Fast asyncio event loop
- `click>=8.1.0` - CLI framework
- `rich>=13.0.0` - Beautiful terminal output

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

### 3. Run Benchmark

```bash
# Run all benchmarks with all approaches (default)
python main.py

# Quick test with fewer documents
python main.py --docs 10000
```

---

## 🎨 CLI Usage

### Basic Commands

```bash
# Show help and all available options
python main.py --help

# Run all benchmarks with all approaches (default)
python main.py

# Run specific approach
python main.py --approach naive
python main.py --approach threaded
python main.py --approach async

# Run multiple approaches (compare them)
python main.py --approach naive,threaded
python main.py --approach threaded,async
python main.py --approach all  # All three approaches

# Run specific test
python main.py --test seeding
python main.py --test topk
python main.py --test cursor

# Run multiple tests
python main.py --test seeding,topk
python main.py --test all  # All three tests

# Combine options
python main.py --approach threaded,async --test seeding
python main.py -a async -t topk,cursor

# Custom document count
python main.py --docs 50000
python main.py -n 100000

# Custom index and prefix
python main.py --index my_index --prefix mydata:

# Quiet mode (minimal output, CSV-like)
python main.py --quiet
python main.py -q
```

### Short Options

| Short | Long | Description |
|-------|------|-------------|
| `-a` | `--approach` | Implementation approach(es) to benchmark |
| `-t` | `--test` | Test type(s) to run |
| `-n` | `--docs` | Number of documents to seed |
| `-i` | `--index` | RediSearch index name |
| `-p` | `--prefix` | Document key prefix |
| `-q` | `--quiet` | Quiet mode (minimal output) |

### Examples

```bash
# Compare threaded vs async for seeding only
python main.py -a threaded,async -t seeding -n 50000

# Quick test with 1000 docs
python main.py -n 1000

# Full benchmark with all approaches and tests
python main.py -a all -t all

# Test async performance on cursor aggregation
python main.py -a async -t cursor

# Compare all approaches on Top-K aggregation
python main.py -a all -t topk -n 100000

# Quiet mode for scripting/logging
python main.py -q > benchmark_results.txt
```

---

## 📊 Understanding the Output

### Configuration Display

```
╭──────────────────────┬────────────────────────────────────────────────────╮
│ Setting              │ Value                                              │
├──────────────────────┼────────────────────────────────────────────────────┤
│ Redis Host           │ redis-11127.c48004.eu-west9-mz.gcp.cloud.rlrcp.com │
│ Redis Port           │ 11127                                              │
│ Redis DB             │ 0                                                  │
│ Redis Username       │ default                                            │
│ Redis Password       │ ●●●●●●●●                                           │
│ Parallel Workers     │ 8                                                  │
│ Connection Pool Size │ 8                                                  │
│ Seed Batch Size      │ 20,000                                             │
│ Aggregate Batch Size │ 20,000                                             │
│ uvloop               │ ✓ Available                                        │
╰──────────────────────┴────────────────────────────────────────────────────╯
```

### Progress Bars

```
⠋ Seeding (naive)... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0:00:05
```

### Benchmark Results

```
📊 Benchmark Results
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Test       ┃ Naive     ┃ Threaded  ┃ Async     ┃ Best      ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ Seeding    │ 100.00s   │ 94.34s    │ 74.23s    │ 🏆 Async  │
│ Top-K      │ 2.450s    │ 2.812s    │ 2.130s    │ 🏆 Async  │
│ Cursor     │ 8.920s    │ 8.415s    │ 6.980s    │ 🏆 Async  │
└────────────┴───────────┴───────────┴───────────┴───────────┘

⚡ Speedup vs Naive
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Test       ┃ Threaded  ┃ Async     ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ Seeding    │ 1.06x     │ 1.35x     │
│ Top-K      │ 0.87x     │ 1.15x     │
│ Cursor     │ 1.06x     │ 1.28x     │
└────────────┴───────────┴───────────┘
```

**Interpretation**:
- **Naive**: Baseline sequential implementation
- **Threaded**: Uses `ThreadPoolExecutor` with connection pool
- **Async**: Uses `asyncio` with `uvloop` for maximum performance
- **Best**: Highlighted with 🏆 trophy emoji
- **Speedup**: Shows how much faster compared to naive baseline

---

## ⚙️ Configuration

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

---

## 🎯 Performance Tuning

### For Single Redis Instance (Local)

```bash
# .env
PARALLEL_WORKERS=2
CONNECTION_POOL_SIZE=2
SEED_BATCH_SIZE=50000
AGGREGATE_BATCH_SIZE=50000
```

**Why?** Redis is single-threaded, so the real performance gain comes from larger batch sizes, not parallelism.

**Expected Results**:
- Async: 20-30% faster than threaded
- Threaded: 5-10% faster than naive
- Batch size increase: 5-10x speedup

### For Redis Cloud (Remote)

```bash
# .env
PARALLEL_WORKERS=4
CONNECTION_POOL_SIZE=4
SEED_BATCH_SIZE=30000
AGGREGATE_BATCH_SIZE=30000
```

**Why?** Parallel connections help hide network latency, and moderate batch sizes balance memory usage.

**Expected Results**:
- Async: 30-50% faster than threaded
- Threaded: 10-20% faster than naive
- Network latency hiding is key

### For Redis Cluster (Multiple Shards)

```bash
# .env
PARALLEL_WORKERS=8
CONNECTION_POOL_SIZE=8
SEED_BATCH_SIZE=20000
AGGREGATE_BATCH_SIZE=20000
```

**Why?** Parallelism actually helps with multiple Redis instances/shards!

**Expected Results**:
- Async: 2-3x faster than threaded
- Threaded: Linear speedup with shard count
- True parallelism across shards

---

## 📁 Project Structure

```
rqe-quick/
├── main.py                    # CLI entry point
├── main_old.py                # Original monolithic implementation (backup)
├── pyproject.toml             # Project metadata and dependencies (uv)
├── uv.lock                    # Locked dependencies (uv)
├── requirements.txt           # Python dependencies (pip fallback)
│
├── .env                       # Your configuration (NOT committed)
├── .env.sample                # Configuration template (committed)
├── .gitignore                 # Protects .env from being committed
│
├── README.md                  # This file
├── README_old.md              # Previous README (backup)
├── CLAUDE.md                  # Notes for Claude AI assistant
│
└── rqe/                       # Main package
    ├── __init__.py
    ├── config.py              # Configuration management
    ├── connection.py          # RedisConnectionPool class
    ├── helpers.py             # Shared helper functions
    ├── index.py               # Index management functions
    ├── benchmark.py           # Benchmark runner
    ├── cli.py                 # CLI interface with Rich
    │
    ├── seeding/               # Seeding implementations
    │   ├── __init__.py
    │   ├── naive.py           # Sequential seeding
    │   ├── threaded.py        # Parallel seeding with threads
    │   └── async_impl.py      # Async seeding with uvloop
    │
    └── aggregation/           # Aggregation implementations
        ├── __init__.py
        ├── naive.py           # Sequential aggregation
        ├── threaded.py        # Parallel aggregation with threads
        └── async_impl.py      # Async aggregation with uvloop
```

---

## 🔍 Implementation Approaches Explained

### 1. Naive (Sequential)

**How it works**:
- Single-threaded, sequential execution
- One operation at a time
- Simple and straightforward

**When to use**:
- Baseline for comparison
- Small datasets (< 10,000 documents)
- Debugging and testing

**Performance**: Slowest, but most predictable

### 2. Threaded (Parallel with ThreadPoolExecutor)

**How it works**:
- Uses `ThreadPoolExecutor` for parallel execution
- Connection pool with round-robin assignment
- Multiple workers process batches concurrently

**When to use**:
- Medium to large datasets (10,000 - 1,000,000 documents)
- Remote Redis instances (network latency)
- When you need predictable resource usage

**Performance**:
- Single Redis: 5-10% faster than naive
- Redis Cloud: 10-20% faster than naive
- Redis Cluster: Linear speedup with shard count

### 3. Async (Asyncio with uvloop)

**How it works**:
- Uses `asyncio` with `uvloop` event loop
- Non-blocking I/O with async/await
- Single-threaded but highly concurrent

**When to use**:
- Large datasets (> 100,000 documents)
- Remote Redis instances (best for network I/O)
- Maximum performance requirements

**Performance**:
- Single Redis: 20-30% faster than threaded
- Redis Cloud: 30-50% faster than threaded
- Redis Cluster: 2-3x faster than threaded

**Why uvloop?**
- Written in Cython (C extension)
- 2-4x faster than standard asyncio
- Drop-in replacement for asyncio event loop

---

## 🧪 Test Types Explained

### 1. Seeding

**What it does**: Bulk inserts documents into Redis using pipelines

**Metrics**:
- Documents per second
- Total time to insert N documents
- Memory usage during insertion

**Use case**: Testing write performance and pipeline efficiency

### 2. Top-K Aggregation

**What it does**: Runs `FT.AGGREGATE` with `GROUPBY` and `LIMIT` clause

**Metrics**:
- Query execution time
- Number of groups returned
- Aggregation throughput

**Use case**: Testing fast aggregation for small result sets (e.g., top 100 countries)

### 3. Cursor Aggregation

**What it does**: Runs `FT.AGGREGATE` with `FT.CURSOR` for pagination

**Metrics**:
- Total time to read all results
- Cursor read operations
- Memory efficiency

**Use case**: Testing memory-efficient aggregation for large result sets

---

## 💡 Advanced Usage

### Programmatic Usage

```python
from rqe.benchmark import BenchmarkRunner
from rqe.config import Config

# Create benchmark runner
runner = BenchmarkRunner(
    index="idx_orders",
    prefix="order:",
    n_docs=100_000,
    fields=["country", "status"]
)

# Setup index
runner.setup_index(recreate=True)

# Run seeding benchmark
result = runner.run_seeding(approach="async")
print(f"Seeding took {result.elapsed:.2f}s")

# Run aggregation benchmark
result = runner.run_aggregation(test_type="topk", approach="async")
print(f"Top-K aggregation took {result.elapsed:.2f}s")

# Cleanup
runner.cleanup()
```

### Custom Configuration

```python
from rqe.config import Config
import redis

# Override configuration
Config.PARALLEL_WORKERS = 8
Config.SEED_BATCH_SIZE = 50000

# Create Redis client with custom config
r = redis.Redis(**Config.get_redis_params())
```

### Connection Pool Usage

```python
from rqe.connection import RedisConnectionPool
from rqe.config import Config

# Create connection pool
pool = RedisConnectionPool(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    username=Config.REDIS_USERNAME,
    password=Config.REDIS_PASSWORD,
    pool_size=4
)

# Get connection for worker
r = pool.get_connection(worker_id=0)

# Use connection
r.ping()

# Cleanup
pool.close_all()
```

---

## 🔒 Security

### Credential Management

✅ **DO**:
- Use `.env` file for credentials (already in `.gitignore`)
- Use environment variables in production
- Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)
- Restrict `.env` file permissions: `chmod 600 .env`

❌ **DON'T**:
- Commit `.env` to git (protected by `.gitignore`)
- Hardcode credentials in code
- Share `.env` files directly
- Log passwords or sensitive data

### Password Masking

The CLI automatically masks passwords in output:
```
Redis Password       │ ●●●●●●●●
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'dotenv'"

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install python-dotenv
```

### "ModuleNotFoundError: No module named 'click'" or "No module named 'rich'"

```bash
# Install new dependencies
uv sync

# Or using pip
pip install click rich
```

### "Connection refused"

Check your Redis connection settings in `.env`:
```bash
# Verify your settings
cat .env

# Test connection
python -c "from rqe.config import Config; print(f'{Config.REDIS_HOST}:{Config.REDIS_PORT}')"
```

### "Authentication failed"

Verify username and password in `.env`:
```bash
REDIS_USERNAME=default
REDIS_PASSWORD=your-actual-password
```

### Performance not improving with threaded/async

For single Redis instance, focus on batch size, not parallelism:
```bash
# .env
PARALLEL_WORKERS=2
SEED_BATCH_SIZE=50000
AGGREGATE_BATCH_SIZE=50000
```

Redis is single-threaded, so batch size matters more than parallelism.

### "uvloop not available" warning

Install uvloop for maximum async performance:
```bash
uv sync
# or
pip install uvloop
```

The async implementation will fall back to standard asyncio if uvloop is not available, but performance will be lower.

---

## 📈 Benchmarking Best Practices

### 1. Warm-up Runs

Run benchmarks multiple times and discard the first run:
```bash
# First run (warm-up)
python main.py -n 10000

# Second run (actual benchmark)
python main.py -n 100000
```

### 2. Consistent Environment

- Close other applications
- Use consistent Redis configuration
- Run on same hardware/network
- Disable CPU throttling

### 3. Multiple Iterations

```bash
# Run 5 times and average results
for i in {1..5}; do
  python main.py -q >> results.txt
done
```

### 4. Document Count Selection

- **Quick test**: 1,000 - 10,000 documents
- **Standard test**: 100,000 - 200,000 documents
- **Stress test**: 1,000,000+ documents

---

## 🤝 Contributing

Contributions welcome! Please ensure:
- Code follows existing structure
- Configuration stays in `.env` file
- No credentials in code
- Documentation is updated
- Tests pass (if applicable)

---

## 📄 License

This project is provided as-is for benchmarking and testing purposes.

---

## 🆘 Support

For issues or questions:

1. **Check the README**: Most common issues are covered here
2. **Verify `.env` file**: Ensure configuration is correct
3. **Test connection**: `python -c "from rqe.config import Config; print(Config.REDIS_HOST)"`
4. **Run with verbose output**: `python main.py` (without `--quiet`)
5. **Check Redis logs**: Verify Redis is running and accessible

---

## 🎯 Quick Reference

### Common Commands

```bash
# Full benchmark (all approaches, all tests)
python main.py

# Quick test
python main.py -n 10000

# Compare async vs threaded
python main.py -a async,threaded

# Test seeding only
python main.py -t seeding

# Quiet mode for logging
python main.py -q > results.txt

# Help
python main.py --help
```

### Performance Expectations

| Setup | Naive | Threaded | Async |
|-------|-------|----------|-------|
| **Local Redis** | Baseline | +5-10% | +20-30% |
| **Redis Cloud** | Baseline | +10-20% | +30-50% |
| **Redis Cluster** | Baseline | +Linear | +2-3x |

### Configuration Quick Reference

```bash
# Local Redis (optimize for batch size)
PARALLEL_WORKERS=2
SEED_BATCH_SIZE=50000

# Redis Cloud (balance parallelism and batch size)
PARALLEL_WORKERS=4
SEED_BATCH_SIZE=30000

# Redis Cluster (maximize parallelism)
PARALLEL_WORKERS=8
SEED_BATCH_SIZE=20000
```

---

**Happy Benchmarking! 🚀**


