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


@app.websocket("/ws/squads/{squad_id}")
async def squad_websocket(websocket: WebSocket, squad_id: str) -> None:
    session = store.get(squad_id)
    if session is None:
        await websocket.close(code=4404, reason="Squad not found")
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                frame = PerceptionFrame.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                error = ErrorResponse(
                    code=ErrorCode.MALFORMED_FRAME,
                    message="Invalid perception frame",
                    detail=[{"error": str(exc)}],
                )
                await websocket.send_json({"type": "error", **error.model_dump()})
                continue

            session.perception_buffer.append(frame)
            session.tick = max(session.tick, frame.tick)

            # Echo mode: acknowledge frame and echo back as directive placeholder
            echo: dict[str, Any] = {
                "type": "echo",
                "squad_id": squad_id,
                "tick": frame.tick,
                "agent_id": frame.agent_id,
                "alert_level": frame.alert_level.value,
            }
            await websocket.send_json(echo)
    except WebSocketDisconnect:
        return


def _session_to_response(session: Any) -> SquadStateResponse:
    return SquadStateResponse(
        squad_id=session.squad_id,
        agent_ids=session.agent_ids,
        tick=session.tick,
        doctrine=session.doctrine,
        last_directive=session.last_directive,
    )
