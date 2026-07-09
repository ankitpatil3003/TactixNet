# Unity integration

TactixNet is engine-agnostic: Unity talks to the **gateway** over HTTP and WebSocket. No Unity package is required for v1.6 — wire REST/WS from your game loop.

## Architecture

```
Unity Client  --HTTP/WS-->  TactixNet Gateway  -->  Negotiation engine
```

## REST (control plane)

Use `UnityWebRequest` for squad lifecycle:

| Action | Method | Path |
|--------|--------|------|
| Create squad | POST | `/squads` |
| Squad state | GET | `/squads/{id}` |
| Apply doctrine | POST | `/squads/{id}/doctrine` |
| Scenario meta | GET | `/squads/{id}/scenario` |
| Event replay | GET | `/squads/{id}/events` |

**Create squad body:**

```json
{
  "agent_ids": ["a1", "a2", "a3"],
  "objective_ref": "breach-gate",
  "scenario": { "name": "my-map", "grid_size": 20 }
}
```

## WebSocket (hot path)

Connect to `ws://localhost:8000/ws/squads/{squad_id}`.

**Send each tick** (one message per agent):

```json
{
  "agent_id": "a1",
  "tick": 42,
  "position": [3.5, 2.0],
  "heading": 90.0,
  "visibility_polygon": [[0,0],[1,0],[1,1]],
  "alert_level": "CALM"
}
```

**Receive** directive when the tick completes:

```json
{
  "type": "directive",
  "directive": { "tick": 42, "awards": [{ "agent_id": "a1", "role": "flank" }] },
  "latency_ms": 1.2,
  "interrupted": false
}
```

Use `ClientWebSocket` (.NET) or a third-party WebSocket library on platforms where `ClientWebSocket` is limited.

## Observer / viewer relay

Send `world_snapshot` JSON so the browser viewer at `/viewer?squad={id}` can render positions, guard vision arcs, and mission state:

```json
{
  "type": "world_snapshot",
  "tick": 42,
  "agents": [{ "id": "a1", "position": [3.5, 4.0], "alert_level": "CALM" }],
  "guards": [{
    "id": "g1", "position": [10, 10], "vision_range": 3.5,
    "vision_angle_deg": 120, "heading": 45.0, "state": "patrol"
  }],
  "mission": { "objective": "breach-gate", "status": "active" }
}
```

See [docs/simulation.md](../../docs/simulation.md) for the full scenario and snapshot reference.

## C# sketch

```csharp
// Pseudocode — adapt to your Unity version and JSON library
var create = UnityWebRequest.Post(
    "http://localhost:8000/squads",
    "{\"agent_ids\":[\"a1\",\"a2\"]}",
    "application/json");
await create.SendWebRequest();
var squadId = JsonUtility.FromJson<CreateResponse>(create.downloadHandler.text).squad_id;

var ws = new ClientWebSocket();
await ws.ConnectAsync(new Uri($"ws://localhost:8000/ws/squads/{squadId}"), CancellationToken.None);
```

## OpenAPI

Import `openapi/openapi.json` into Postman or generate C# clients with NSwag/OpenAPI Generator.

## Reference implementation

- Python SDK: `client/squad_client.py`
- TypeScript SDK: `sdk/typescript`
- Live demo driver: `simulation/run_demo.py`
