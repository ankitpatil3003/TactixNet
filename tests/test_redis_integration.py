import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
import websockets

from gateway.events import SquadEventLogger


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def redis_url() -> str | None:
    url = "redis://localhost:6379/0"
    try:
        import redis

        client = redis.from_url(url)
        client.ping()
        return url
    except Exception:
        return None


@pytest.mark.asyncio
async def test_event_logger_redis_round_trip(redis_url: str | None) -> None:
    if redis_url is None:
        pytest.skip("Redis not available")
    logger = SquadEventLogger()
    os.environ["REDIS_URL"] = redis_url
    await logger.connect()
    assert logger.available is True

    await logger.log("redis-it", "directive", {"type": "directive", "tick": 1})
    await logger.log("redis-it", "world_snapshot", {"type": "world_snapshot", "tick": 1})

    events = await logger.read("redis-it", count=10)
    assert len(events) >= 2
    types = {entry["type"] for entry in events}
    assert "directive" in types
    assert "world_snapshot" in types
    await logger.close()


@pytest.mark.asyncio
async def test_replay_events_chronological_via_api(redis_url: str | None) -> None:
    if redis_url is None:
        pytest.skip("Redis not available")

    from fastapi.testclient import TestClient

    from gateway.app import app

    os.environ["REDIS_URL"] = redis_url
    client = TestClient(app)

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

    replay = client.get(f"/squads/{squad_id}/events?replay_only=true&count=100").json()
    events = replay["events"]
    assert len(events) >= 1
    ticks = []
    for entry in events:
        payload = entry["payload"]
        if entry["type"] == "directive":
            ticks.append(payload["directive"]["tick"])
        elif entry["type"] == "world_snapshot":
            ticks.append(payload["tick"])
    assert ticks == sorted(ticks)


@pytest.mark.e2e
def test_live_gateway_smoke() -> None:
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "gateway.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                response = httpx.get(f"{base}/health", timeout=1.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            pytest.fail("gateway did not become healthy in time")

        create = httpx.post(f"{base}/squads", json={"agent_ids": ["a1"]}, timeout=5.0)
        create.raise_for_status()
        squad_id = create.json()["squad_id"]

        frame = {
            "agent_id": "a1",
            "tick": 1,
            "position": [1.0, 2.0],
            "heading": 0.0,
            "visibility_polygon": [[0, 0], [1, 0], [1, 1]],
            "alert_level": "CALM",
        }

        async def _ws_round_trip() -> None:
            ws_url = f"ws://127.0.0.1:{port}/ws/squads/{squad_id}"
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(frame))
                message = json.loads(await ws.recv())
                assert message["type"] == "directive"

        import asyncio

        asyncio.run(_ws_round_trip())

        events = httpx.get(f"{base}/squads/{squad_id}/events", timeout=5.0)
        events.raise_for_status()
        assert len(events.json()["events"]) >= 1
    finally:
        proc.terminate()
        proc.wait(timeout=5)
