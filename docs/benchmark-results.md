# Benchmark Results

Generated: 2026-07-07 22:55 UTC

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
| p95 | 0.15 ms |
| p99 | 0.16 ms |
| Mean | 0.14 ms |
| Max | 0.39 ms |

Target: p95 < 150 ms — MET

## Latency Distribution

```
   0.14-   0.16 ms | ######################################## 9875
   0.16-   0.18 ms | # 73
   0.18-   0.20 ms | # 23
   0.20-   0.22 ms | # 16
   0.22-   0.24 ms | # 7
   0.24-   0.27 ms | # 2
   0.27-   0.29 ms |  0
   0.29-   0.31 ms | # 1
   0.31-   0.33 ms | # 1
   0.33-   0.35 ms |  0
   0.35-   0.37 ms |  0
   0.37-   0.39 ms | # 2
```

Methodology: see [benchmark-methodology.md](benchmark-methodology.md).
Reproduce with `python -m simulation.benchmark --ticks 10000`.
