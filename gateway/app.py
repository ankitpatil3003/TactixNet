"""FastAPI gateway: WebSocket hot path + REST control plane."""

import json
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts import (
    DoctrineUpdate,
    ErrorCode,
    ErrorResponse,
    PerceptionFrame,
    SquadDirective,
)
from gateway.sessions import SessionStore

app = FastAPI(title="TactixNet Gateway", version="0.1.0")
store = SessionStore()


class CreateSquadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_ids: list[str] = Field(min_length=1)


class SquadStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    squad_id: str
    agent_ids: list[str]
    tick: int
    doctrine: DoctrineUpdate | None
    last_directive: SquadDirective | None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/squads", response_model=SquadStateResponse)
async def create_squad(body: CreateSquadRequest) -> SquadStateResponse:
    session = store.create(body.agent_ids)
    return _session_to_response(session)


@app.get("/squads/{squad_id}", response_model=SquadStateResponse)
async def get_squad_state(squad_id: str) -> SquadStateResponse:
    session = store.get(squad_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code=ErrorCode.SQUAD_NOT_FOUND,
                message=f"Squad {squad_id} not found",
            ).model_dump(),
        )
    return _session_to_response(session)


@app.post("/squads/{squad_id}/doctrine", response_model=SquadStateResponse)
async def update_doctrine(squad_id: str, doctrine: DoctrineUpdate) -> SquadStateResponse:
    session = store.get(squad_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code=ErrorCode.SQUAD_NOT_FOUND,
                message=f"Squad {squad_id} not found",
            ).model_dump(),
        )
    if doctrine.squad_id != squad_id:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code=ErrorCode.VALIDATION_ERROR,
                message="doctrine.squad_id must match path squad_id",
            ).model_dump(),
        )
    session.doctrine = doctrine
    return _session_to_response(session)


async def _broadcast(sockets: set[Any], message: dict[str, Any]) -> None:
    dead: list[Any] = []
    for socket in sockets:
        try:
            await socket.send_json(message)
        except Exception:
            dead.append(socket)
    for socket in dead:
        sockets.discard(socket)


@app.websocket("/ws/squads/{squad_id}")
async def squad_websocket(websocket: WebSocket, squad_id: str) -> None:
    session = store.get(squad_id)
    if session is None:
        await websocket.close(code=4404, reason="Squad not found")
        return

    mode = websocket.query_params.get("mode", "player")
    await websocket.accept()
    session.sockets.add(websocket)
    if mode == "observer":
        session.observers.add(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            if mode == "observer":
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                error = ErrorResponse(
                    code=ErrorCode.MALFORMED_FRAME,
                    message="Invalid perception frame",
                    detail=[{"error": str(exc)}],
                )
                await websocket.send_json({"type": "error", **error.model_dump()})
                continue

            # World snapshots are relayed to observers for rendering; they do
            # not participate in negotiation.
            if isinstance(payload, dict) and payload.get("type") == "world_snapshot":
                await _broadcast(session.observers, payload)
                continue

            try:
                frame = PerceptionFrame.model_validate(payload)
            except ValidationError as exc:
                error = ErrorResponse(
                    code=ErrorCode.MALFORMED_FRAME,
                    message="Invalid perception frame",
                    detail=[{"error": str(exc)}],
                )
                await websocket.send_json({"type": "error", **error.model_dump()})
                continue

            session.perception_buffer.append(frame)
            if len(session.perception_buffer) > 1000:
                del session.perception_buffer[:-1000]
            session.tick = max(session.tick, frame.tick)

            assert session.runner is not None
            results = await session.runner.ingest_frame(frame)
            for result in results:
                session.last_directive = result.directive
                await _broadcast(session.sockets, result.to_message())
    except WebSocketDisconnect:
        pass
    finally:
        session.sockets.discard(websocket)
        session.observers.discard(websocket)


def _session_to_response(session: Any) -> SquadStateResponse:
    return SquadStateResponse(
        squad_id=session.squad_id,
        agent_ids=session.agent_ids,
        tick=session.tick,
        doctrine=session.doctrine,
        last_directive=session.last_directive,
    )
