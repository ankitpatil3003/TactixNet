# @tactixnet/client

TypeScript/Node client for the TactixNet gateway (REST + WebSocket).

## Install

```bash
npm install @tactixnet/client
```

From this monorepo:

```bash
cd sdk/typescript
npm install
npm run build
```

## Quickstart

```typescript
import { SquadClient } from "@tactixnet/client";

const squad = await SquadClient.create("http://localhost:8000", ["a1", "a2"]);
await squad.connect();

await squad.sendFrame({
  agent_id: "a1",
  tick: 1,
  position: [1, 2],
  heading: 0,
  visibility_polygon: [[0, 0], [1, 0], [1, 1]],
  alert_level: "CALM",
});

const directive = await squad.receiveDirective();
console.log(directive.directive.awards);

await squad.close();
```

## API

| Method | Description |
|--------|-------------|
| `SquadClient.create()` | `POST /squads` |
| `createFromScenario()` | `POST /squads/from-scenario` |
| `health()` | `GET /health` |
| `listScenarios()` / `listSquads()` | Control-plane lists |
| `updateScenario()` | `PATCH /squads/{id}/scenario` |
| `deleteSquad()` | `DELETE /squads/{id}` |
| `startSimulation()` / `getSimulation()` / `cancelSimulation()` | Simulate lifecycle |
| `connect({ observer })` | WebSocket `/ws/squads/{id}` |
| `sendFrame()` | Send `PerceptionFrame` |
| `sendSnapshot()` | Relay `world_snapshot` to observers (see `docs/simulation.md`) |
| `receiveDirective()` | Wait for next directive message |
| `applyDoctrine()` | `POST /squads/{id}/doctrine` |
| `getState()` | `GET /squads/{id}` |
| `getScenario()` | `GET /squads/{id}/scenario` |
| `getEvents()` | `GET /squads/{id}/events` |

OpenAPI spec: `/openapi.json` on the gateway (see `openapi/openapi.json` in the repo).
