# Changelog

## v1.3.1

### Fixed
- Interrupt replans clear role cooldown so contact renegotiation always awards roles.
- Demo retains last assigned roles when cooldown blocks bidding (default `STEALTH_COVER` instead of `BREACH`).
- Guard tuning: shorter vision, slower chase, compromise after 4 ticks (was 2).
- Alert-aware movement: agents flee/slow under `ALERT+` instead of charging into guards.
- Double compromise counting when perceptions run twice in the same tick.

## v1.3.0

### Added
- Redis-backed session metadata persistence (`squad:{id}:meta`) with lazy rehydration after gateway restart.
- `GET /squads/{id}/scenario` for viewer grid sizing and scenario metadata.
- Python client SDK (`client.SquadClient`) for REST + WebSocket integration.
- Scenario-driven demos: YAML `tick_rate_hz`, `objective`, `squad_size`, `grid_size`; new `ambush` scenario.
- Role bid cooldown after awards (`cooldown_ticks` on frames + negotiator-side cooldown).
- E2E smoke test (subprocess uvicorn), Redis integration tests, nightly soak workflow.
- Viewer doctrine panel and dedicated recovery HUD field.
- Optional `USE_REDIS_CHECKPOINT=1` for Redis-backed LangGraph checkpoints.

### Changed
- `docker compose up` runs redis + gateway only (removed broken `engine` service).
- Demo driver uses `SquadClient` and scenario defaults for tick rate.
- Gateway version 0.3.0; package version 0.3.0.
- Replay fetches full session with `replay_only=true` (from v1.2.1 patch).

## v1.2.0

### Added
- Tier-2 doctrine wired into the live pipeline: `POST /squads/{id}/doctrine` applies role weights immediately; async strategy refresh after replans and every 100 ticks broadcasts `{"type": "doctrine"}` messages.
- Redis event sourcing in the gateway (degrades silently when Redis is down): `GET /squads/{id}/events` for replay.
- `recovery_ms` metric on interrupted directive cycles (ALERT ingest → replanned directive).
- Viewer replay mode: `/viewer?squad=<id>&replay=1` with play/pause and speed control.
- Living simulation: guard patrol/investigate/chase state machine; agents execute awarded roles in the demo driver.
- `COMPROMISED` alert when an agent stays within half a guard's vision range for 2+ ticks.
- Per-session `asyncio.Lock` for concurrent frame ingestion; multi-squad isolation test.
- Opt-in soak test (`pytest -m soak`); `run_demo --squads N` for concurrent squads.
- Benchmark CLI now reports interrupt recovery p50/p95.

### Changed
- Demo driver moves agents by role instead of marching straight to the objective.
- Gateway version bumped to 0.2.0 with lifespan-managed event logger.

## v1.1.0

### Added
- Live per-tick negotiation in the gateway WebSocket (replaces echo mode).
- Demo driver (`python -m simulation.run_demo`).
- Canvas viewer served at `/viewer` with alert colors, guard vision circles, and HUD.
- Benchmark CLI with committed 10k-tick results.
- README overhaul with architecture diagrams and API reference.

## v1.0.0

### Added
- Initial release: Pydantic contracts, FastAPI gateway, Redis message bus, CNP reflex negotiation, LangGraph orchestration with interrupt replanning, Groq strategy layer (standalone), simulation harness, and documentation.
