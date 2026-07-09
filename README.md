# TactixNet

> Decentralized multi-agent coordination engine for real-time tactics games — LangGraph-orchestrated squad negotiation in-process at the gateway, with Redis for events and session metadata.

[![CI](https://github.com/ankitpatil3003/TactixNet/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitpatil3003/TactixNet/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/github/v/tag/ankitpatil3003/TactixNet?label=release)](https://github.com/ankitpatil3003/TactixNet/tags)
[![License](https://img.shields.io/github/license/ankitpatil3003/TactixNet)](LICENSE)

## What is this?

TactixNet coordinates a squad of AI agents in a real-time tactics game. Think of a 5-agent stealth squad: one flanks, one distracts, one covers, one overwatches, one breaches. When a guard spots an agent mid-plan, the squad instantly re-negotiates roles — without a central controller and without waiting on an LLM.

The core idea is a **two-tier brain**:

| Tier | Latency | What it does |
|------|---------|--------------|
| **Tier 1 — Reflex** | p95 < 150 ms (measured: **0.15 ms**) | Deterministic utility scoring + Contract Net Protocol bidding. Resolves "guard spotted me → squad re-roles" instantly. Pure asyncio, no LLM in the loop. |
| **Tier 2 — Strategy** | 200 ms – 2 s, async | A LangGraph node calls Groq to generate squad *doctrine* (role weights, priorities, fallback plans) that Tier 1 consumes. Never blocks the game tick; degrades gracefully when the LLM is down. |

Agents are **decentralized**: each sees only its local perception (position, vision cone, alert level, ammo) plus broadcast intents — never global state. Roles are won by bidding, not assigned top-down.

## Architecture

```mermaid
flowchart LR
    Client[Game Client / Sim Harness] -->|WS perception frames| Gateway[FastAPI Gateway]
    Gateway -->|per-tick negotiation| Graph[LangGraph Orchestrator]
    Graph -->|interrupt| Replan[compromised_replan subgraph]
    Graph -.->|async, non-blocking| LLM[Tier-2 Strategy: Groq]
    Graph -->|SquadDirective| Gateway
    Gateway -->|WS directives| Client
    Gateway -->|WS broadcast| Viewer[Canvas Viewer /viewer]
    Gateway <--> Redis[(Redis: events + session meta)]
```

Negotiation runs **in-process** inside the gateway by default (`ENGINE_MODE=inprocess`). Set `ENGINE_MODE=distributed` with the `engine` worker service to route perceptions and directives through Redis pub/sub — matching the diagram below for multi-process deployments.

```mermaid
flowchart LR
    Client[Game Client / Sim Harness] -->|WS perception frames| Gateway[FastAPI Gateway]
    Gateway -->|Redis pub/sub| Engine[Engine Worker]
    Engine -->|LangGraph + CNP| Engine
    Engine -->|Redis directives| Gateway
    Gateway -->|WS directives| Client
    Gateway -->|WS broadcast| Viewer[Canvas Viewer /viewer]
    Gateway <--> Redis[(Redis: events + session meta + hot path)]
```

### One negotiation cycle

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orchestrator
    participant A as Agents

    C->>G: PerceptionFrame x5 (one tick)
    G->>O: tick complete, run graph
    O->>O: detect_conflict (any ALERT?)
    alt agent compromised
        O->>O: compromised_replan (boost distract/stealth weights)
    end
    O->>A: announce role-tasks
    A->>O: utility bids (local perception only, 40ms timeout)
    O->>O: award roles (conflict resolution)
    O->>G: SquadDirective (monotonic directive_seq)
    G->>C: directive broadcast (players + observers)
```

## Live Demo

Four terminals (or three — Redis is optional for the local demo):

```bash
# 0. Install
pip install -r requirements.txt
cp .env.example .env          # set GROQ_API_KEY only if you want Tier-2

# 1. Gateway
uvicorn gateway.app:app --port 8000

# 2. Demo driver (uses scenario tick_rate_hz by default)
python -m simulation.run_demo --ticks 300

# Ambush scenario (higher pressure, 2 guards)
python -m simulation.run_demo --scenario simulation/scenarios/ambush.yaml --ticks 300

# Optional: multiple concurrent squads
python -m simulation.run_demo --ticks 300 --squads 2

# Docker stack (redis + engine worker + gateway, distributed mode)
docker compose up
```

Distributed mode (`ENGINE_MODE=distributed`) splits negotiation into a separate engine process. Local dev defaults to in-process — no engine container required:

```bash
# In-process (default) — single gateway process
uvicorn gateway.app:app --port 8000
```

The driver prints the viewer URL, e.g.:

```
Squad 3f2a... created — streaming 300 ticks at 10.0Hz
Viewer: http://localhost:8000/viewer?squad=3f2a...
tick=1 seq=1 latency=1.2ms roles={'a1': 'flank', 'a2': 'distract', ...}
tick=42 seq=42 latency=1.4ms roles={...} [REPLAN]
```

**3. Open the viewer URL in a browser.** Agents are color-coded by alert level, labeled with their awarded role, and guards show vision circles. When a guard spots the squad, the REPLAN badge flashes, `recovery_ms` appears in the HUD, and roles reshuffle live.

**4. Replay a finished session:** `http://localhost:8000/viewer?squad=<id>&replay=1` (loads events from `GET /squads/{id}/events`).

**5. Apply doctrine manually (Tier-2 weights without waiting for Groq):**
```bash
curl -X POST http://localhost:8000/squads/<id>/doctrine \
  -H "Content-Type: application/json" \
  -d '{"squad_id":"<id>","role_weights":{"distract":3.0,"flank":0.5},"priority_objective":"breach-gate"}'
```

## Benchmarks

Full perceive → negotiate → commit on the reflex path, 5 agents, 10,000 ticks:

| Metric | Measured | Budget |
|--------|----------|--------|
| p50 | 0.14 ms | — |
| p95 | **0.15 ms** | < 150 ms |
| p99 | 0.16 ms | — |
| Max | 0.39 ms | — |

Reproduce: `python -m simulation.benchmark --ticks 10000` — writes [docs/benchmark-results.md](docs/benchmark-results.md) with environment info and a latency histogram. Methodology: [docs/benchmark-methodology.md](docs/benchmark-methodology.md).

## Project Structure

```
tactixnet/
├── contracts/     # Shared Pydantic v2 schemas (extra="forbid") — single source of truth
├── gateway/       # FastAPI: WS hot path, REST control plane, live negotiation runner, /viewer
├── engine/        # LangGraph StateGraph, Redis bus, checkpointer, CNP award logic
├── agents/        # Localized perception model, per-role utility functions, CNP bidder
├── client/        # Python SDK (SquadClient)
├── simulation/    # Headless grid sim, YAML scenarios, demo driver, benchmark CLI
├── viewer/        # Canvas visualizer (served by the gateway at /viewer)
├── tests/         # Unit + integration + e2e (60+ tests)
└── docs/          # Architecture, protocol, benchmark methodology + results
```

## API Reference

### REST

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness + Redis connectivity (`event_log`, `session_store`) |
| `/squads` | POST | Create squad — `{"agent_ids": [...], "objective_ref"?, "scenario"?}` |
| `/squads/{id}` | GET | Squad state incl. `last_directive`, `objective_ref` |
| `/squads/{id}/scenario` | GET | Scenario metadata attached at squad creation |
| `/squads/{id}/doctrine` | POST | Update strategy doctrine (applies weights immediately) |
| `/squads/{id}/events` | GET | Event log for replay (`?count=10000&replay_only=true`) |
| `/viewer` | GET | Canvas viewer page |

### WebSocket `/ws/squads/{id}`

**Send** (player mode) — one `PerceptionFrame` per agent per tick:

```json
{
  "agent_id": "a1",
  "tick": 42,
  "position": [3.5, 2.0],
  "heading": 90.0,
  "visibility_polygon": [[0,0],[1,0],[1,1]],
  "visible_entities": [{"entity_id": "g1", "entity_type": "guard", "position": [10,10], "threat_level": 0.7}],
  "alert_level": "SUSPICIOUS",
  "ammo": 30
}
```

**Receive** — a directive when the tick's negotiation commits:

```json
{
  "type": "directive",
  "directive": {
    "squad_id": "…", "directive_seq": 42, "tick": 42,
    "awards": [{"agent_id": "a1", "task_id": "…", "role": "flank", "utility": 0.9}],
    "objective_ref": "breach-alpha"
  },
  "latency_ms": 1.2,
  "interrupted": false,
  "replan_count": 0,
  "recovery_ms": 2.5
}
```

Connect with `?mode=observer` to receive directives and `world_snapshot` relays without participating (used by the viewer). Malformed frames get a structured `{"type": "error", "code": "MALFORMED_FRAME", ...}` reply.

## v1.4 Highlights

- **Distributed engine:** `ENGINE_MODE=distributed` routes perceptions and directives through Redis pub/sub; `python -m engine.runner` worker process.
- **Docker Compose:** `redis` + `engine` + `gateway` stack for multi-process deployment.
- **Directive relay:** gateway subscribes to engine-published directives and doctrine updates.
- **Health:** `/health` reports `engine_mode` and `hot_path_bus` status.

## v1.3 Highlights

- **Durable sessions:** squad metadata persisted in Redis; lazy rehydration on `GET /squads/{id}` after restart.
- **Python SDK:** `client.SquadClient` for create, doctrine, scenario, WebSocket frames.
- **Scenario-driven demos:** `default` + `ambush` YAML scenarios; tick rate from scenario.
- **Ops:** fixed Docker Compose, E2E smoke in CI, nightly soak workflow.
- **Viewer:** doctrine panel, dedicated recovery HUD, scenario-aware grid.

## v1.2 Highlights

- **Doctrine is live:** `POST /doctrine` and async Groq strategy refresh apply weights to the reflex bidder; broadcasts `{"type": "doctrine"}` on update.
- **Event sourcing:** all perception/directive/interrupt events logged (Redis + in-memory fallback); replay in the viewer.
- **Living world:** guards chase spotted agents; demo agents move by awarded role; `COMPROMISED` after sustained close contact.
- **recovery_ms:** measured interrupt-to-replan latency on every interrupted cycle.
- **Concurrency:** per-session locks, multi-squad isolation, opt-in soak test (`pytest -m soak`).

See [CHANGELOG.md](CHANGELOG.md) for full release notes.

## Design Decisions

- **Why Contract Net Protocol?** It's a named, citable MAS negotiation protocol: tasks are announced, agents bid with locally-computed utility, highest bidder wins with conflict resolution. Decentralization falls out naturally — no agent needs global state to bid.
- **Why is the LLM outside the hot loop?** Even fast inference (~300 tok/s) can't reliably return structured output for 5 agents inside a 150 ms tick. So the LLM shapes *doctrine* (utility weights) asynchronously, and the deterministic reflex layer does the per-tick work. If Groq is down, `StrategyLayer` returns a fallback doctrine and the squad keeps fighting.
- **Interrupt-driven replanning:** an `ALERT`/`COMPROMISED` frame routes the graph through `compromised_replan`, which boosts distract/stealth weights and revises the objective before bidding. The chaos test injects an ALERT mid-cycle and asserts recovery with monotonic `directive_seq`.
- **Timeout as backpressure:** bids are gathered with a hard `asyncio.wait_for` deadline — a slow agent forfeits its bid rather than stalling the squad. Same policy at the tick level: an incomplete tick is flushed when a newer tick arrives.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_MODE` | `inprocess` | `inprocess` (default) or `distributed` (Redis hot path + engine worker) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for event log + session metadata |
| `USE_REDIS_CHECKPOINT` | — | Set to `1` to persist LangGraph checkpoints in Redis |
| `GROQ_API_KEY` | — | Enables Tier-2 strategy layer (optional) |
| `ENGINE_LOG_LEVEL` | `INFO` | Engine runner log level |

Get a Groq key at [console.groq.com](https://console.groq.com/keys).

## Development

```bash
# Full suite (excludes soak + e2e)
pytest

# Soak / E2E
pytest -m soak
pytest -m e2e

# Lint
ruff check .

# Docker stack
docker compose up
```

### Python SDK quickstart

```python
import asyncio
from client import SquadClient
from contracts import PerceptionFrame

async def main() -> None:
    squad = await SquadClient.create("http://localhost:8000", ["a1", "a2"])
    await squad.connect()
    frame = PerceptionFrame(
        agent_id="a1", tick=1, position=(1.0, 2.0), heading=0.0,
        visibility_polygon=[(0, 0), (1, 0), (1, 1)],
    )
    await squad.send_frame(frame)
    print(await squad.receive_directive())
    await squad.aclose()

asyncio.run(main())
```

**Branching:** `main` (release) ← PR ← `develop` (integration) ← PR ← `feature/*`. Every change lands via PR; CI (ruff + pytest + e2e with Redis) runs on all PRs.

## Documentation

- [Architecture](docs/architecture.md) — two-tier brain, components, interrupt replanning
- [Protocol](docs/protocol.md) — CNP cycle, utility functions, timeout policy
- [Benchmark methodology](docs/benchmark-methodology.md) and [latest results](docs/benchmark-results.md)

## License

See [LICENSE](LICENSE).
