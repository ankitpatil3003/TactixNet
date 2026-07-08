"""FastAPI gateway: WebSocket hot path + REST control plane."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts import (
    DoctrineUpdate,
    ErrorCode,
    ErrorResponse,
    PerceptionFrame,
    SquadDirective,
)
from gateway.events import SquadEventLogger
from gateway.live import CycleResult
from gateway.sessions import SessionStore, SquadSession

event_logger = SquadEventLogger()
store = SessionStore()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await event_logger.connect()
    yield
    await event_logger.close()


app = FastAPI(title="TactixNet Gateway", version="0.2.0", lifespan=lifespan)


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


VIEWER_HTML = Path(__file__).resolve().parent.parent / "viewer" / "index.html"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "event_log": "connected" if event_logger.available else "offline"}


@app.get("/viewer")
async def viewer() -> FileResponse:
    return FileResponse(VIEWER_HTML, media_type="text/html")


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


@app.get("/squads/{squad_id}/events")
async def get_squad_events(
    squad_id: str,
    count: int = 100,
    replay_only: bool = False,
) -> dict[str, Any]:
    session = store.get(squad_id)
    if session is None:
        # Allow replay fetch when events exist but session was dropped (e.g. after restart).
        probe = await event_logger.read(squad_id, count=1)
        if not probe:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    code=ErrorCode.SQUAD_NOT_FOUND,
                    message=f"Squad {squad_id} not found",
                ).model_dump(),
            )

    fetch_count = count if count > 0 else 10_000
    events = await event_logger.read(squad_id, count=fetch_count)
    parsed = []
    for entry in reversed(events):
        payload_raw = entry.get("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {"raw": payload_raw}
        event_type = entry.get("type")
        if replay_only and event_type not in {"world_snapshot", "directive"}:
            continue
        parsed.append({"id": entry.get("id"), "type": event_type, "payload": payload})
    return {
        "squad_id": squad_id,
        "events": parsed,
        "total": len(parsed),
        "truncated": len(events) >= fetch_count,
    }


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
    await _apply_doctrine(session, doctrine, source="rest")
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


async def _apply_doctrine(
    session: SquadSession, doctrine: DoctrineUpdate, *, source: str
) -> None:
    session.doctrine = doctrine
    if session.runner is not None:
        session.runner.apply_doctrine(doctrine)
    message = {
        "type": "doctrine",
        "source": source,
        "doctrine": doctrine.model_dump(mode="json"),
    }
    await _broadcast(session.sockets, message)
    await event_logger.log(session.squad_id, "doctrine", message)


async def _handle_cycle_results(
    session: SquadSession, frame: PerceptionFrame, results: list[CycleResult]
) -> None:
    for result in results:
        session.last_directive = result.directive
        message = result.to_message()
        await _broadcast(session.sockets, message)
        await event_logger.log(session.squad_id, "directive", message)
        if result.interrupted:
            await event_logger.log(
                session.squad_id,
                "interrupt",
                {
                    "tick": frame.tick,
                    "recovery_ms": result.recovery_ms,
                    "replan_count": result.replan_count,
                },
            )

    if session.runner is None or not results:
        return

    last = results[-1]
    context = (
        f"tick={frame.tick} interrupted={last.interrupted} "
        f"replans={last.replan_count} objective={last.objective_ref}"
    )

    async def on_doctrine_applied(doctrine: DoctrineUpdate) -> None:
        session.doctrine = doctrine
        await _apply_doctrine(session, doctrine, source="strategy")

    session.runner.schedule_strategy_refresh(
        tick=frame.tick,
        context=context,
        after_replan=last.interrupted,
        on_applied=on_doctrine_applied,
    )


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

            if isinstance(payload, dict) and payload.get("type") == "world_snapshot":
                await _broadcast(session.observers, payload)
                await event_logger.log(session.squad_id, "world_snapshot", payload)
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

            await event_logger.log(
                session.squad_id,
                "perception",
                frame.model_dump(mode="json"),
            )

            assert session.runner is not None
            results = await session.runner.ingest_frame(frame)
            await _handle_cycle_results(session, frame, results)
    except WebSocketDisconnect:
        pass
    finally:
        session.sockets.discard(websocket)
        session.observers.discard(websocket)


def _session_to_response(session: SquadSession) -> SquadStateResponse:
    return SquadStateResponse(
        squad_id=session.squad_id,
        agent_ids=session.agent_ids,
        tick=session.tick,
        doctrine=session.doctrine,
        last_directive=session.last_directive,
    )
