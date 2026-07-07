import json
import time

import pytest
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


@pytest.mark.soak
def test_two_squad_soak_smoke() -> None:
    """Short soak smoke: 2 squads x 20 ticks, verify no cross-talk and latency budget."""
    squads = [
        client.post("/squads", json={"agent_ids": AGENT_IDS}).json()["squad_id"]
        for _ in range(2)
    ]
    latencies: list[float] = []

    for tick in range(1, 21):
        for squad_id in squads:
            with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
                start = time.perf_counter()
                for agent_id in AGENT_IDS:
                    ws.send_text(_frame(agent_id, tick=tick))
                msg = ws.receive_json()
                latencies.append((time.perf_counter() - start) * 1000)
                assert msg["directive"]["squad_id"] == squad_id

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 150.0
