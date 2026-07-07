# Benchmark Methodology

## Target

Full perceive → negotiate → commit resolution at **p95 < 150ms** on the Tier-1 reflex path.

## Latency Budget

| Stage | Budget |
|-------|--------|
| WebSocket ingest + validation | ~5ms |
| Redis publish + pickup | ~5ms |
| Conflict detection + task announcement | ~10ms |
| Parallel bid computation (5 agents) | ~40ms |
| Award + conflict resolution | ~20ms |
| Directive commit + broadcast | ~10ms |
| **Total p95 target** | **<100ms** (headroom to 150ms) |

## Running Benchmarks

```bash
pytest tests/test_benchmark.py -v
```

The benchmark runner (`simulation/benchmark.py`) drives 50–10,000 ticks through `ReflexNegotiator` and reports p50/p95/p99.

## Environment Notes

- Benchmarks run on the host Python process (no network I/O in reflex path)
- Results vary by CPU; document your hardware when publishing numbers
- CI runs a 50-tick smoke benchmark; full 10k runs are local

## Interrupt Recovery Metric

Chaos test in `tests/test_graph.py` injects `ALERT` mid-cycle and asserts:
- `interrupted == True`
- `replan_count >= 1`
- Directive still committed with monotonic `directive_seq`
