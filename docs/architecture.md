# Architecture

TactixNet uses a two-tier decision loop optimized for real-time tactics games.

## Tier 1 — Reflex Layer (<150ms)

Deterministic utility scoring + Contract Net Protocol (CNP) bidding. Pure asyncio math over localized perception vectors. Resolves tactical reactions (e.g., guard spotted → squad re-roles) without LLM latency.

**Pipeline:** ingest → detect conflict → announce tasks → collect bids → award roles → commit directive

## Tier 2 — Strategy Layer (200ms–2s, optional)

LangGraph-orchestrated Groq LLM node generates squad doctrine (role weights, priorities, fallback plans). Runs asynchronously and never blocks the game tick. Gracefully degrades to reflex-only when LLM is unavailable.

## Components

| Component | Path | Role |
|-----------|------|------|
| Contracts | `contracts/` | Pydantic v2 shared schemas |
| Gateway | `gateway/` | FastAPI WebSocket hot path + REST control plane |
| Message Bus | `engine/bus.py` | Redis pub/sub hot path + Streams event log |
| Engine Worker | `engine/worker.py`, `engine/runner.py` | Distributed negotiation consumer |
| Orchestrator | `engine/graph.py` | LangGraph negotiation StateGraph |
| Agents | `agents/` | Perception, utility, CNP bidder |
| Simulation | `simulation/` | Headless grid sim, scenarios, mission tracker, benchmark rig |

## Living Simulation (v1.9)

The grid harness (`simulation/grid.py`, `simulation/movement.py`) provides a tactics playground aligned with the architecture goals:

- **Bounded world** — `grid_size` from YAML; `simulation/bounds.py` clamps agents and guards every tick
- **Guard AI** — interpolated patrol, directional vision arc (~120°), investigate/chase state machine
- **Role movement** — flank arc, distract feint, stealth cover, overwatch hold, breach push — all in-bounds
- **Perception alignment** — agent `PerceptionFrame` uses the same directional guard detection model as movement
- **Mission outcomes** — `reach_objective` / `hold_objective` win conditions; lose on all compromised

See [simulation.md](simulation.md) for scenario YAML reference, `world_snapshot` shape, and tick-loop detail.

When any agent broadcasts `ALERT` or `COMPROMISED`, the `compromised_replan` sub-graph activates: boosts distract/stealth weights, revises objective ref, and resumes from the last LangGraph checkpoint.
