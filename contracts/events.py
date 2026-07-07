from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import AlertLevel, RoleEnum


class VisibleEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    entity_type: str
    position: tuple[float, float]
    threat_level: float = Field(ge=0.0, le=1.0)


class PerceptionFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    tick: int = Field(ge=0)
    position: tuple[float, float]
    heading: float
    visibility_polygon: list[tuple[float, float]]
    visible_entities: list[VisibleEntity] = Field(default_factory=list)
    alert_level: AlertLevel = AlertLevel.CALM
    ammo: int = Field(default=30, ge=0)
    cooldown_ticks: int = Field(default=0, ge=0)


class TaskAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    role: RoleEnum
    objective_ref: str
    deadline_tick: int = Field(ge=0)


class Bid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    task_id: str
    utility: float
    constraints: list[str] = Field(default_factory=list)


class RoleAward(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    task_id: str
    role: RoleEnum
    utility: float


class SquadDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    squad_id: str
    directive_seq: int = Field(ge=0)
    tick: int = Field(ge=0)
    awards: list[RoleAward]
    objective_ref: str


class InterruptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    squad_id: str
    tick: int = Field(ge=0)
    trigger_agent_id: str
    alert_level: AlertLevel
    reason: str


class DoctrineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    squad_id: str
    role_weights: dict[RoleEnum, float]
    priority_objective: str
    fallback_plan: str = ""


def alert_level_rank(level: AlertLevel) -> int:
    match level:
        case AlertLevel.CALM:
            return 0
        case AlertLevel.SUSPICIOUS:
            return 1
        case AlertLevel.ALERT:
            return 2
        case AlertLevel.COMPROMISED:
            return 3
        case _ as unreachable:
            assert_never(unreachable)
