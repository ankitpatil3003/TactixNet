"""Background simulation tasks started from the gateway control plane."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from simulation.driver import stream_simulation
from simulation.scenario import ScenarioConfig

SimulationStatus = Literal["idle", "running", "finished", "cancelled", "error"]


@dataclass
class SimulationState:
    squad_id: str
    status: SimulationStatus = "idle"
    scenario: str | None = None
    ticks_requested: int = 0
    ticks_run: int = 0
    mission: str = "idle"
    reason: str = ""
    directives: int = 0
    replans: int = 0
    error: str | None = None
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _cancel: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "squad_id": self.squad_id,
            "status": self.status,
            "scenario": self.scenario,
            "ticks_requested": self.ticks_requested,
            "ticks_run": self.ticks_run,
            "mission": self.mission,
            "reason": self.reason,
            "directives": self.directives,
            "replans": self.replans,
            "error": self.error,
        }


class SimulationRunner:
    def __init__(self, gateway_url: str) -> None:
        self._gateway_url = gateway_url
        self._states: dict[str, SimulationState] = {}

    def get(self, squad_id: str) -> SimulationState:
        if squad_id not in self._states:
            self._states[squad_id] = SimulationState(squad_id=squad_id)
        return self._states[squad_id]

    def is_running(self, squad_id: str) -> bool:
        state = self._states.get(squad_id)
        return state is not None and state.status == "running"

    async def start(
        self,
        squad_id: str,
        *,
        scenario: ScenarioConfig,
        scenario_label: str,
        ticks: int,
        hz: float | None = None,
    ) -> SimulationState:
        state = self.get(squad_id)
        if state.status == "running":
            raise RuntimeError(f"Simulation already running for squad {squad_id}")

        state._cancel = asyncio.Event()
        state.status = "running"
        state.scenario = scenario_label
        state.ticks_requested = ticks
        state.ticks_run = 0
        state.mission = "active"
        state.reason = ""
        state.directives = 0
        state.replans = 0
        state.error = None

        async def _run() -> None:
            try:

                async def on_tick(tick: int, mission: str, _snapshot: dict[str, Any]) -> None:
                    state.ticks_run = tick
                    state.mission = mission

                result = await stream_simulation(
                    self._gateway_url,
                    squad_id,
                    scenario,
                    ticks=ticks,
                    hz=hz,
                    cancel_event=state._cancel,
                    on_tick=on_tick,
                )
                state.ticks_run = int(result.get("ticks_run", state.ticks_run))
                state.mission = str(result.get("mission", state.mission))
                state.reason = str(result.get("reason", ""))
                state.directives = int(result.get("directives", 0))
                state.replans = int(result.get("replans", 0))
                state.status = "cancelled" if result.get("mission") == "cancelled" else "finished"
            except asyncio.CancelledError:
                state.status = "cancelled"
                raise
            except Exception as exc:
                state.status = "error"
                state.error = str(exc)
            finally:
                state._task = None

        state._task = asyncio.create_task(_run())
        return state

    async def cancel(self, squad_id: str) -> SimulationState:
        state = self.get(squad_id)
        if state.status != "running":
            return state
        state._cancel.set()
        if state._task is not None:
            try:
                await asyncio.wait_for(state._task, timeout=5.0)
            except TimeoutError:
                state._task.cancel()
        return state
