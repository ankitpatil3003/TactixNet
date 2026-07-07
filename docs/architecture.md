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
| Message Bus | `engine/bus.py` | Redis pub/sub + Streams event log |
| Orchestrator | `engine/graph.py` | LangGraph negotiation StateGraph |
| Agents | `agents/` | Perception, utility, CNP bidder |
| Simulation | `simulation/` | Headless grid sim + benchmark rig |

## Interrupt Replanning

When any agent broadcasts `ALERT` or `COMPROMISED`, the `compromised_replan` sub-graph activates: boosts distract/stealth weights, revises objective ref, and resumes from the last LangGraph checkpoint.
