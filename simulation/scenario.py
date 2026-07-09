"""Scenario YAML loader and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    tick_rate_hz: float
    squad_size: int
    objective: str
    objective_position: tuple[float, float]
    objective_radius: float
    win_condition: str
    hold_ticks: int
    lose_on_all_compromised: bool
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioConfig:
        agents = data.get("agents", [])
        squad_size = int(data.get("squad_size", len(agents)))
        if squad_size != len(agents):
            raise ValueError(
                f"squad_size ({squad_size}) must match agents list length ({len(agents)})"
            )
        obj_pos = data.get("objective_position", [16, 16])
        win_condition = str(data.get("win_condition", "reach_objective"))
        if win_condition not in {"reach_objective", "hold_objective"}:
            raise ValueError(f"unsupported win_condition: {win_condition}")
        return cls(
            name=str(data.get("name", "unnamed")),
            tick_rate_hz=float(data.get("tick_rate_hz", 10.0)),
            squad_size=squad_size,
            objective=str(data.get("objective", data.get("name", "objective"))),
            objective_position=(float(obj_pos[0]), float(obj_pos[1])),
            objective_radius=float(data.get("objective_radius", 1.5)),
            win_condition=win_condition,
            hold_ticks=int(data.get("hold_ticks", 30)),
            lose_on_all_compromised=bool(data.get("lose_on_all_compromised", True)),
            raw=data,
        )


def load_scenario(path: Path) -> ScenarioConfig:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return ScenarioConfig.from_dict(data)
