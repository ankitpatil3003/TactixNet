# Architecture

TactixNet uses a two-tier decision loop optimized for real-time tactics games.

## Tier 1 — Reflex Layer (<150ms)

Deterministic utility scoring + Contract Net Protocol (CNP) bidding. Pure asyncio math over localized perception vectors. Resolves tactical reactions (e.g., guard spotted → squad re-roles) without LLM latency.

**Pipeline:** ingest → detect conflict → announce tasks → collect bids → award roles → commit directive → schedule_strategy

## Tier 2 — Strategy Layer (200ms–2s, optional)

A LangGraph `schedule_strategy` node decides when Tier-2 should refresh doctrine
(after compromise replan, or every N ticks). The node itself **never awaits** the
LLM: it only sets `strategy_refresh_requested` on graph state. The live runner then
schedules `StrategyLayer` (Groq) asynchronously so the reflex tick stays under
150 ms. Gracefully degrades to reflex-only when the LLM is unavailable or
`fallback_plan=reflex-only-fallback`.

**Pipeline:** ingest → detect conflict → (optional replan) → announce → bids →
award → commit → schedule_strategy

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
