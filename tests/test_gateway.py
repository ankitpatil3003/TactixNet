import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from contracts import AlertLevel, RoleEnum
from gateway.app import app

client = TestClient(app)


def test_create_and_get_squad() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1", "a2", "a3"]})
    assert create.status_code == 200
    squad_id = create.json()["squad_id"]

    state = client.get(f"/squads/{squad_id}")
    assert state.status_code == 200
    assert state.json()["agent_ids"] == ["a1", "a2", "a3"]


def test_get_missing_squad_returns_404() -> None:
    response = client.get("/squads/missing-id")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SQUAD_NOT_FOUND"


def test_update_doctrine() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1"]})
    squad_id = create.json()["squad_id"]

    doctrine = {
        "squad_id": squad_id,
        "role_weights": {RoleEnum.FLANK.value: 1.0, RoleEnum.OVERWATCH.value: 0.5},
        "priority_objective": "breach-gate",
    }
    response = client.post(f"/squads/{squad_id}/doctrine", json=doctrine)
    assert response.status_code == 200
    assert response.json()["doctrine"]["priority_objective"] == "breach-gate"


def test_websocket_directive_round_trip() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1"]})
    squad_id = create.json()["squad_id"]

    frame = {
        "agent_id": "a1",
        "tick": 5,
        "position": [1.0, 2.0],
        "heading": 45.0,
        "visibility_polygon": [[0, 0], [1, 0], [1, 1]],
        "alert_level": AlertLevel.SUSPICIOUS.value,
    }

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text(json.dumps(frame))
        message = ws.receive_json()
        assert message["type"] == "directive"
        assert message["directive"]["tick"] == 5
        assert len(message["directive"]["awards"]) == 1


def test_websocket_malformed_frame_returns_error() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1"]})
    squad_id = create.json()["squad_id"]

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text("{not json")
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "MALFORMED_FRAME"


def test_websocket_unknown_squad() -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/squads/unknown") as ws:
            ws.receive_text()
