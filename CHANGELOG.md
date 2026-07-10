# Changelog

## v2.0.0

### Added
- `spawn_roles` from scenario YAML seed live simulation movement from tick 1 (before first CNP directive).
- Richer simulation status: `reason`, `directives`, `replans` on `GET /squads/{id}/simulation`.
- Patrol route polylines in viewer `world_snapshot` and canvas overlay.
- Console: scenario column, scenario override on Start, mission reason/directives/replans in status panel.
- Viewer: mission `reason`, `compromised_count`, `win_condition`; `wss://` when served over HTTPS.
- Integration tests: `tests/test_simulation_integration.py` (simulate flow, cancel, spawn_roles, mission win).
- Hold scenario 300-tick bounds soak; hold added to e2e smoke.
- Console world editor: add/remove guards, edit patrol routes, objective position, grid size; reset to base YAML.
- `PATCH /squads/{id}/scenario` and `DELETE /squads/{id}` control-plane endpoints.
- Inline squad scenario edits used by live simulation (`resolve_scenario_for_squad`).
- Scenario list includes `guard_count`; squad list shows per-squad guard count.

### Changed
- `world_snapshot` guards include `patrol` waypoint arrays for viewer overlay.

## v1.9.0

### Added
- Tactical role movement: flank arcs, distract feints, stealth cover positions, overwatch hold — all bounded to the grid with heading updates.
- Interpolated guard patrol (no waypoint teleporting), directional vision arc (~120°), and guard state labels in the viewer.
- `simulation/bounds.py` with `clamp_position` / `is_in_bounds` helpers.
- Scenario tuning: spawns kept ≥2 units from edges; optional `spawn_roles` hints in YAML.
- Viewer HUD: guard vision arcs, patrol/investigate/chase state badges, soft clip for off-grid entities.
- Tests: 300-tick in-bounds soak tests, guard AI patrol/vision tests, `tests/test_tactical_sim.py`.
- Documentation: `docs/simulation.md` (scenario YAML, guard AI, world_snapshot); updated architecture, protocol, and integration guides.

### Changed
- `build_sim()` wires `grid_size` and per-guard `vision_range`, `vision_angle_deg`, `patrol_speed` from scenario YAML.
- Overwatch utility scoring uses visible threat distance instead of polygon vertex count.
- Agent movement passes `alert_level` for pressure-aware role behavior.

## v1.8.0

### Fixed
- Agents and guards no longer drift off the viewer canvas — positions clamped to grid bounds after every movement update.
- `move_away` blends toward objective when flee direction would exit bounds (prevents corner trapping).

## v1.7.0

### Added
- Squad Console at `/console`: create idle squads, apply doctrine, then start simulation on demand.
- Control-plane endpoints: `GET /squads`, `GET /scenarios`, `POST /squads/from-scenario`, `POST /squads/{id}/simulate`, `GET /squads/{id}/simulation`, `POST /squads/{id}/simulate/cancel`.
- Gateway-side background `SimulationRunner` streaming ticks via reusable `simulation/driver.py`.
- `run_demo --create-only` and `--squad-id` to split squad creation from streaming on the CLI.
- Session metadata persists `scenario_file` so simulations resolve the correct scenario YAML after rehydration.

### Fixed
- Doctrine events are now included in `replay_only` event queries; the viewer doctrine panel updates during replay.
- Repaired `scripts/e2e_smoke.py` (broken imports, stale `world_snapshot` signature) and extended it to cover console endpoints.

## v1.6.0

### Added
- TypeScript SDK (`@tactixnet/client` in `sdk/typescript`) — REST + WebSocket parity with Python `SquadClient`.
- Committed OpenAPI spec at `openapi/openapi.json`; export via `python scripts/export_openapi.py`.
- Interactive API docs at `/docs` and `/openapi.json` on the gateway.
- Integration guides: `examples/node`, `examples/unity`, `examples/godot`.
- Python `SquadClient.get_events()` for replay/event log access.

### Changed
- README documents SDK paths, OpenAPI workflow, and engine integration examples.

## v1.5.0

### Added
- Mission win/lose evaluation: `reach_objective` and `hold_objective` win conditions; lose on all agents compromised.
- `simulation/mission.py` with `MissionTracker` and per-tick mission state in `world_snapshot`.
- Scenario fields: `objective_radius`, `win_condition`, `hold_ticks`, `lose_on_all_compromised`.
- New `hold-point` scenario (`simulation/scenarios/hold.yaml`).
- Viewer mission HUD: objective zone circle, status panel, WON/LOST overlay.

### Changed
- Demo driver stops early on mission win/loss and reports outcome.
- `world_snapshot` includes `mission` block for viewer and replay.

## v1.4.0

### Added
- Distributed engine mode (`ENGINE_MODE=distributed`): gateway publishes perceptions to Redis; `engine.runner` worker negotiates and publishes directive envelopes.
- `DirectiveRelay` in gateway fans out engine directives/doctrine to WebSocket clients.
- `EngineWorker` with squad registration via `squad:{id}:control` channel.
- Docker Compose `engine` service; gateway defaults to distributed in compose stack.
- `/health` fields: `engine_mode`, `hot_path_bus`.
- `engine/live.py` — negotiation runner moved from gateway for shared in-process and distributed use.

### Changed
- `ENGINE_MODE=inprocess` remains the default for local single-process dev.
- `engine/bus.py` extended with control, directive envelope, and pattern subscribe helpers.

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
