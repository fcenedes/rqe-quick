# Batch Size Tuning Guide

## Overview

This guide explains how to calculate optimal pipeline batch sizes based on network MTU, document size, and Redis deployment type.

---

## Network Fundamentals

### MTU (Maximum Transmission Unit)

**Standard Ethernet MTU**: 1,500 bytes

**Breakdown**:
```
MTU:         1,500 bytes
- IP header:    20 bytes (IPv4)
- TCP header:   20 bytes (TCP without options)
= TCP payload: 1,460 bytes (usable for Redis commands)
```

### Document Size (Ecommerce Schema)

**Sample HSET command**:
```
HSET product:1 country FR category beauty status delivered price 56.39 ts 1759710274
```

**Size breakdown**:
- Key: `product:1` = 9 bytes
- Fields: 5 fields × ~14 bytes avg = 72 bytes
- Protocol overhead: ~120 bytes (RESP3 encoding)
- **Total: ~210 bytes per HSET command**

---

## Batch Size Analysis

### Commands per TCP Packet

```
TCP payload: 1,460 bytes
Command size: 210 bytes
Commands per packet: 1,460 ÷ 210 = ~6 commands
```

### Efficiency Table

| Batch Size | Total Bytes | TCP Packets | Efficiency | Memory | Use Case |
|------------|-------------|-------------|------------|--------|----------|
| 6 | 1.3 KB | 1 | 84.0% | <1 KB | Minimal latency |
| 100 | 21 KB | 15 | 93.3% | 21 KB | Testing |
| 1,000 | 210 KB | 144 | 97.2% | 0.2 MB | Balanced |
| 2,000 | 420 KB | 288 | 97.2% | 0.4 MB | Current default |
| 5,000 | 1.05 MB | 720 | 97.2% | 1.0 MB | Good for remote |
| 10,000 | 2.1 MB | 1,439 | 97.3% | 2.0 MB | **Recommended for Redis Cloud** |
| 20,000 | 4.2 MB | 2,877 | 97.3% | 4.0 MB | High throughput |
| 50,000 | 10.5 MB | 7,192 | 97.3% | 10 MB | Local Redis only |

**Key Insight**: Efficiency plateaus at ~97% for batches ≥1,000. Choose based on latency and memory constraints.

---

## Latency Considerations

### Local Redis (localhost)

**Network latency**: <1ms

**Recommendation**:
```bash
SEED_BATCH_SIZE=50000
AGGREGATE_BATCH_SIZE=50000
```

**Rationale**:
- Latency is negligible
- Maximize throughput with large batches
- Memory is not a concern (10 MB is fine)

---

### Redis Cloud (Remote)

**Network latency**: 10-50ms (typical for cloud deployments)

**Recommendation**:
```bash
SEED_BATCH_SIZE=10000
AGGREGATE_BATCH_SIZE=5000
```

**Rationale**:
- **Latency hiding**: 10K batch takes ~50ms to send, hiding 10-50ms network latency
- **TCP efficiency**: 97.3% (minimal packet overhead)
- **Memory**: 2 MB is reasonable for pipeline buffer
- **Balance**: Good throughput without excessive memory

**Example calculation**:
```
Batch size: 10,000 commands
Total bytes: 2,100,000 bytes (2.1 MB)
TCP packets: 1,439 packets
Network time: 1,439 packets × 0.1ms = ~144ms (local processing)
Network latency: 10-50ms (hidden by large batch)
Total time: ~200ms for 10K docs = 50,000 docs/sec
```

---

### Redis Cluster (Multiple Shards)

**Network latency**: Varies (10-50ms typical)

**Recommendation**:
```bash
SEED_BATCH_SIZE=20000
AGGREGATE_BATCH_SIZE=20000
PARALLEL_WORKERS=8
```

**Rationale**:
- Parallelism helps with multiple shards
- Each worker targets different shard
- Larger batches per worker = better throughput

---

## Practical Guidelines

### Rule of Thumb

1. **Batch size ≥ 1,000**: Achieve >97% TCP efficiency
2. **Remote Redis**: Use 5K-10K to hide latency
3. **Local Redis**: Use 20K-50K for maximum throughput
4. **Memory limit**: Keep batch size × doc size < 10 MB

### Calculating for Your Schema

```python
# 1. Measure document size
doc_size = len(redis_command_bytes)  # e.g., 210 bytes

# 2. Calculate commands per packet
tcp_payload = 1460  # bytes
cmds_per_packet = tcp_payload // doc_size

# 3. Choose batch size based on latency
if latency_ms < 1:
    batch_size = 50000  # Local Redis
elif latency_ms < 50:
    batch_size = 10000  # Redis Cloud
else:
    batch_size = 5000   # High latency

# 4. Verify memory usage
memory_mb = (batch_size * doc_size) / (1024 * 1024)
assert memory_mb < 10, "Batch too large!"
```

---

## Performance Impact

### Current Settings (2,000 batch)

```
Batch size: 2,000
Total bytes: 420 KB
TCP packets: 288
Efficiency: 97.2%
```

### Recommended Settings (10,000 batch)

```
Batch size: 10,000
Total bytes: 2.1 MB
TCP packets: 1,439
Efficiency: 97.3%
```

### Expected Improvement

**For Redis Cloud**:
- **5x larger batches** = better latency hiding
- **Expected speedup**: 2-3x faster seeding
- **Reason**: Fewer round trips, better pipelining

**Example**:
```
Before (2K batch): 100,000 docs in 10s = 10,000 docs/sec
After (10K batch): 100,000 docs in 4s = 25,000 docs/sec
Speedup: 2.5x
```

---

## Monitoring and Tuning

### How to Test

1. **Baseline**: Run with current settings
   ```bash
   uv run python -m rqe.cli -n 100000 -t seeding -a async
   ```

2. **Increase batch size**: Update `.env`
   ```bash
   SEED_BATCH_SIZE=10000
   ```

3. **Re-run benchmark**:
   ```bash
   uv run python -m rqe.cli -n 100000 -t seeding -a async
   ```

4. **Compare results**: Look for ops/sec improvement

### What to Monitor

- **Operations per second**: Higher is better
- **Memory usage**: Should stay reasonable (<100 MB)
- **Network utilization**: Should be high (>80%)
- **Redis CPU**: Should be high (>80%) for good utilization

---

## Summary

✅ **For Redis Cloud (your setup)**:
```bash
SEED_BATCH_SIZE=10000
AGGREGATE_BATCH_SIZE=5000
PARALLEL_WORKERS=4
```

✅ **Why it works**:
- 2.1 MB batches hide 10-50ms network latency
- 97.3% TCP efficiency (minimal overhead)
- Reasonable memory usage (2 MB)
- Expected 2-3x speedup over 2K batches

✅ **Next steps**:
1. Update `.env` with recommended settings
2. Run benchmark to measure improvement
3. Adjust based on your specific latency and memory constraints

