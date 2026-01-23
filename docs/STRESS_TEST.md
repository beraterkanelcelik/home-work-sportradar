# Stress Test Documentation

Concurrent user stress testing for the Sports Scouting Agent.

## Overview

The stress test simulates real-world load by firing simultaneous requests from multiple users. Each user creates a chat session and sends a message that triggers the full agent workflow (Temporal + LangGraph + LLM).

## Test Levels

| Level | Concurrent Users | Description |
|-------|------------------|-------------|
| 1 | 10 | Baseline load |
| 2 | 20 | Light load |
| 3 | 50 | Moderate load |
| 4 | 100 | Heavy load |
| 5 | 200 | Peak load |

## Latest Results (2 Workers)

| Level | Users | Success | Throughput | Median Latency | p95 Latency |
|-------|-------|---------|------------|----------------|-------------|
| 1 | 10 | 100% | 2.3 req/s | 3,472ms | 4,436ms |
| 2 | 20 | 100% | 6.4 req/s | 2,521ms | 3,126ms |
| 3 | 50 | 100% | 6.5 req/s | 6,529ms | 7,627ms |
| 4 | 100 | 100% | 6.2 req/s | 13,195ms | 16,024ms |
| 5 | 200 | 67.5% | 3.3 req/s | 41,228ms | 58,183ms |

**Level 5 bottleneck:** 65 requests timed out (120s limit). Scaling to 3-4 workers recommended.

## How to Run

### Prerequisites
- Docker Compose services running
- OpenAI API key
- Langfuse credentials (from http://localhost:3001)

### Scale Workers (Recommended)

```bash
# Scale to 2+ workers for better throughput
docker-compose up -d --scale worker=2
```

### Run Stress Test

```bash
# Run all levels (stops at <95% success)
docker exec django-backend python tests/stress_test_concurrent_users.py \
  --base-url http://localhost:8000 \
  --api-key "YOUR_OPENAI_KEY" \
  --langfuse-public "YOUR_LANGFUSE_PUBLIC_KEY" \
  --langfuse-secret "YOUR_LANGFUSE_SECRET_KEY"

# Run specific level
docker exec django-backend python tests/stress_test_concurrent_users.py \
  --level 3 \
  --api-key "..." --langfuse-public "..." --langfuse-secret "..."
```

## Scaling Strategy

The system scales horizontally via Temporal workers:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Backend   │────▶│   Temporal   │────▶│  Worker 1   │
│  (Django)   │     │   Server     │     │  (LangGraph)│
└─────────────┘     └──────────────┘     └─────────────┘
                           │              ┌─────────────┐
                           └─────────────▶│  Worker 2   │
                                          │  (LangGraph)│
                                          └─────────────┘
                                          ┌─────────────┐
                                          └─────────────▶│  Worker N   │
                                                         └─────────────┘
```

**Key points:**
- Workers share the same Temporal task queue
- Temporal automatically distributes work across workers
- Each worker handles `TEMPORAL_MAX_CONCURRENT_ACTIVITIES` concurrent LLM calls
- Linear scaling: 2 workers ≈ 2x throughput

### Scaling Commands

```bash
# Scale to N workers
docker-compose up -d --scale worker=N

# Or use deploy.replicas in docker-compose.yml:
# deploy:
#   mode: replicated
#   replicas: 4
```

### Scaling Guidelines

| Target Users | Recommended Workers | Expected Throughput |
|--------------|---------------------|---------------------|
| 10-50 | 1 | ~3 req/s |
| 50-100 | 2 | ~6 req/s |
| 100-200 | 3-4 | ~10-12 req/s |
| 200+ | 4+ | ~12+ req/s |

## Configuration

Environment variables for tuning (`.env`):

```env
# Temporal Worker Scaling
TEMPORAL_MAX_CONCURRENT_WORKFLOWS=250
TEMPORAL_MAX_CONCURRENT_ACTIVITIES=250
```

## Metrics Explained

- **Success Rate**: Percentage of requests completing without timeout/error
- **Throughput**: Requests processed per second during test phase
- **Median Latency**: 50th percentile end-to-end response time
- **p95 Latency**: 95th percentile (worst-case for most users)
- **TTFT**: Time to first token (streaming responsiveness)
