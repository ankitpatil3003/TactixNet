# Godot integration

Godot 4 games integrate with TactixNet through the gateway HTTP API and WebSocket endpoint.

## Prerequisites

- Godot 4.x
- Running gateway: `uvicorn gateway.app:app --port 8000`

## REST with HTTPRequest

```gdscript
var http := HTTPRequest.new()
add_child(http)
http.request_completed.connect(_on_squad_created)

var body := JSON.stringify({
    "agent_ids": ["a1", "a2", "a3"],
    "objective_ref": "breach-gate"
})
http.request(
    "http://127.0.0.1:8000/squads",
    ["Content-Type: application/json"],
    HTTPClient.METHOD_POST,
    body
)

func _on_squad_created(result, code, headers, body):
    var data = JSON.parse_string(body.get_string_from_utf8())
    squad_id = data["squad_id"]
    _connect_ws()
```

## WebSocket with WebSocketPeer

```gdscript
var ws := WebSocketPeer.new()

func _connect_ws() -> void:
    ws.connect_to_url("ws://127.0.0.1:8000/ws/squads/%s" % squad_id)

func _physics_process(_delta):
    ws.poll()
    while ws.get_available_packet_count() > 0:
        var packet = ws.get_packet().get_string_from_utf8()
        var message = JSON.parse_string(packet)
        if message.get("type") == "directive":
            _apply_roles(message["directive"]["awards"])

func send_perception(agent_id: String, tick: int, pos: Vector2) -> void:
    var frame = {
        "agent_id": agent_id,
        "tick": tick,
        "position": [pos.x, pos.y],
        "heading": 0.0,
        "visibility_polygon": [[0,0],[1,0],[1,1]],
        "alert_level": "CALM"
    }
    ws.send_text(JSON.stringify(frame))
```

## Game loop pattern

1. **Fixed tick** (e.g. 20 Hz): gather local perception per agent.
2. **Send** one `PerceptionFrame` per agent on the WebSocket.
3. **Receive** `directive` messages (non-blocking poll each frame).
4. **Apply** awarded roles to movement / animation systems.
5. Optionally **POST doctrine** when mission phase changes.

## Viewer

Open `http://localhost:8000/viewer?squad={squad_id}` to debug negotiations live.

## Specs

- OpenAPI: `openapi/openapi.json` or live `/openapi.json`
- Protocol details: `docs/protocol.md`
