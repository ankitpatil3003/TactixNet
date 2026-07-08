import json

import pytest
from fastapi.testclient import TestClient

from gateway.app import app, store

client = TestClient(app)


@pytest.mark.asyncio
async def test_replay_after_session_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.events import SquadEventLogger

    async def always_memory(self) -> None:
        self._bus = None

    monkeypatch.setattr(SquadEventLogger, "connect", always_memory)

    create = client.post("/squads", json={"agent_ids": ["a1"]})
    squad_id = create.json()["squad_id"]

    frame = {
        "agent_id": "a1",
        "tick": 1,
        "position": [1.0, 2.0],
        "heading": 0.0,
        "visibility_polygon": [[0, 0], [1, 0], [1, 1]],
        "alert_level": "CALM",
    }
    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text(json.dumps(frame))
        ws.receive_json()

    store.delete(squad_id)
    assert store.get(squad_id) is None

    events = client.get(f"/squads/{squad_id}/events?replay_only=true").json()
    assert len(events["events"]) >= 1
