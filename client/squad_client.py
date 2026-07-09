"""Async HTTP + WebSocket client for TactixNet squads."""

from __future__ import annotations

import json
from typing import Any

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from contracts import DoctrineUpdate, PerceptionFrame


class SquadClient:
    """Thin client for squad REST + WebSocket integration."""

    def __init__(self, gateway: str, squad_id: str | None = None) -> None:
        self.gateway = gateway.rstrip("/")
        self.squad_id = squad_id
        self._http: httpx.AsyncClient | None = None
        self._ws: ClientConnection | None = None
        self._mode = "player"

    @classmethod
    async def create(
        cls,
        gateway: str,
        agent_ids: list[str],
        *,
        objective_ref: str | None = None,
        scenario: dict[str, Any] | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> SquadClient:
        client = cls(gateway)
        if http is not None:
            client._http = http
        else:
            await client._ensure_http()
        body: dict[str, Any] = {"agent_ids": agent_ids}
        if objective_ref is not None:
            body["objective_ref"] = objective_ref
        if scenario is not None:
            body["scenario"] = scenario
        response = await client._http.post("/squads", json=body)
        response.raise_for_status()
        client.squad_id = response.json()["squad_id"]
        return client

    async def _ensure_http(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.gateway, timeout=30.0)

    def _ws_url(self) -> str:
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        base = self.gateway.replace("http://", "ws://").replace("https://", "wss://")
        mode = f"?mode={self._mode}" if self._mode != "player" else ""
        return f"{base}/ws/squads/{self.squad_id}{mode}"

    async def connect(self, *, observer: bool = False) -> None:
        await self._ensure_http()
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        self._mode = "observer" if observer else "player"
        self._ws = await websockets.connect(self._ws_url())

    async def send_frame(self, frame: PerceptionFrame) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        await self._ws.send(frame.model_dump_json())

    async def send_snapshot(self, snapshot: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        await self._ws.send(json.dumps(snapshot))

    async def receive_json(self) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        raw = await self._ws.recv()
        return json.loads(raw)

    async def receive_directive(self) -> dict[str, Any]:
        while True:
            message = await self.receive_json()
            if message.get("type") == "directive":
                return message
            if message.get("type") == "error":
                raise RuntimeError(message.get("message", "gateway error"))

    async def apply_doctrine(self, doctrine: DoctrineUpdate) -> dict[str, Any]:
        await self._ensure_http()
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        response = await self._http.post(
            f"/squads/{self.squad_id}/doctrine",
            json=doctrine.model_dump(mode="json"),
        )
        response.raise_for_status()
        return response.json()

    async def get_state(self) -> dict[str, Any]:
        await self._ensure_http()
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        response = await self._http.get(f"/squads/{self.squad_id}")
        response.raise_for_status()
        return response.json()

    async def get_scenario(self) -> dict[str, Any]:
        await self._ensure_http()
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        response = await self._http.get(f"/squads/{self.squad_id}/scenario")
        response.raise_for_status()
        return response.json()

    async def get_events(
        self, *, count: int = 100, replay_only: bool = False
    ) -> dict[str, Any]:
        await self._ensure_http()
        if self.squad_id is None:
            raise RuntimeError("squad_id is required")
        params: dict[str, Any] = {"count": count}
        if replay_only:
            params["replay_only"] = True
        response = await self._http.get(f"/squads/{self.squad_id}/events", params=params)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> SquadClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
