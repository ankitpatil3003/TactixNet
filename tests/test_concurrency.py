import json

from fastapi.testclient import TestClient

from gateway.app import app

client = TestClient(app)

AGENT_IDS = [f"a{i}" for i in range(1, 6)]


def _frame(agent_id: str, tick: int) -> str:
    return json.dumps(
        {
            "agent_id": agent_id,
            "tick": tick,
            "position": [float(agent_id[-1]), 2.0],
            "heading": 0.0,
            "visibility_polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "alert_level": "CALM",
        }
    )


def test_two_squads_isolated_directive_sequences() -> None:
    squad_a = client.post("/squads", json={"agent_ids": AGENT_IDS}).json()["squad_id"]
    squad_b = client.post("/squads", json={"agent_ids": AGENT_IDS}).json()["squad_id"]

    with (
        client.websocket_connect(f"/ws/squads/{squad_a}") as ws_a,
        client.websocket_connect(f"/ws/squads/{squad_b}") as ws_b,
    ):
        for agent_id in AGENT_IDS:
            ws_a.send_text(_frame(agent_id, tick=1))
            ws_b.send_text(_frame(agent_id, tick=1))
        msg_a = ws_a.receive_json()
        msg_b = ws_b.receive_json()

    assert msg_a["directive"]["squad_id"] == squad_a
    assert msg_b["directive"]["squad_id"] == squad_b
    assert msg_a["directive"]["directive_seq"] == 1
    assert msg_b["directive"]["directive_seq"] == 1
