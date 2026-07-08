# Benchmark Results

Generated: 2026-07-07 23:58 UTC

## Environment

| Property | Value |
|----------|-------|
| OS | Windows 11 |
| CPU | AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD |
| Python | 3.12.9 |

## Reflex Path Latency (full perceive-negotiate-commit, 5 agents)

| Metric | Value |
|--------|-------|
| Samples | 10000 |
| p50 | 0.14 ms |
| p95 | 0.22 ms |
| p99 | 0.26 ms |
| Mean | 0.15 ms |
| Max | 0.53 ms |

Target: p95 < 150 ms — MET

## Interrupt Recovery (ALERT ingest → replanned directive)

| Metric | Value |
|--------|-------|
| recovery p50 | 5.20 ms |
| recovery p95 | 5.66 ms |

## Latency Distribution

```
   0.14-   0.17 ms | ######################################## 9274
   0.17-   0.20 ms | # 164
   0.20-   0.24 ms | # 109
   0.24-   0.27 ms | # 409
   0.27-   0.30 ms | # 27
   0.30-   0.33 ms | # 5
   0.33-   0.37 ms | # 3
   0.37-   0.40 ms | # 1
   0.40-   0.43 ms | # 3
   0.43-   0.47 ms | # 1
   0.47-   0.50 ms | # 3
   0.50-   0.53 ms | # 1
```

Methodology: see [benchmark-methodology.md](benchmark-methodology.md).
Reproduce with `python -m simulation.benchmark --ticks 10000`.
