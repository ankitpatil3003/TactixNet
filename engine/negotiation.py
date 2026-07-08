"""Reflex negotiation: task announcement, bid collection, award with conflict resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from agents.bidder import CNPBidder
from contracts import (
    Bid,
    PerceptionFrame,
    RoleAward,
    RoleEnum,
    SquadDirective,
    TaskAnnouncement,
)


@dataclass
class NegotiationResult:
    directive: SquadDirective
    bids_received: list[Bid]
    forfeited_agents: list[str]


ROLE_COOLDOWN_TICKS = 3


@dataclass
class ReflexNegotiator:
    """Tier-1 deterministic negotiation engine."""

    squad_id: str
    agent_ids: list[str]
    bid_timeout_s: float = 0.04
    role_cooldown_ticks: int = ROLE_COOLDOWN_TICKS
    _directive_seq: int = 0
    _bidders: dict[str, CNPBidder] = field(default_factory=dict, init=False)
    _cooldown_until: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._bidders = {
            agent_id: CNPBidder(agent_id, bid_timeout_s=self.bid_timeout_s)
            for agent_id in self.agent_ids
        }

    async def negotiate(
        self,
        frames: list[PerceptionFrame],
        objective_ref: str,
        tick: int,
    ) -> NegotiationResult:
        tasks = self._announce_tasks(objective_ref, tick)
        bids, forfeited = await self._collect_bids(frames, tasks)
        awards = self._award_roles(bids, tasks)
        for award in awards:
            self._cooldown_until[award.agent_id] = tick + self.role_cooldown_ticks
        self._directive_seq += 1
        directive = SquadDirective(
            squad_id=self.squad_id,
            directive_seq=self._directive_seq,
            tick=tick,
            awards=awards,
            objective_ref=objective_ref,
        )
        return NegotiationResult(
            directive=directive,
            bids_received=bids,
            forfeited_agents=forfeited,
        )

    def _announce_tasks(self, objective_ref: str, tick: int) -> list[TaskAnnouncement]:
        roles = list(RoleEnum)
        return [
            TaskAnnouncement(
                task_id=f"{objective_ref}-{role.value}",
                role=role,
                objective_ref=objective_ref,
                deadline_tick=tick + 10,
            )
            for role in roles[: len(self.agent_ids)]
        ]

    async def _collect_bids(
        self,
        frames: list[PerceptionFrame],
        tasks: list[TaskAnnouncement],
    ) -> tuple[list[Bid], list[str]]:
        frame_map = {f.agent_id: f for f in frames}
        bids: list[Bid] = []
        forfeited: list[str] = []

        async def bid_for_agent(agent_id: str) -> list[Bid]:
            frame = frame_map.get(agent_id)
            if frame is None:
                return []
            if frame.cooldown_ticks > 0:
                return []
            if self._cooldown_until.get(agent_id, 0) > frame.tick:
                return []
            bidder = self._bidders[agent_id]
            agent_bids: list[Bid] = []
            for task in tasks:
                bid = await bidder.compute_bid(frame, task)
                if bid is not None:
                    agent_bids.append(bid)
            return agent_bids

        results = await asyncio.gather(
            *[bid_for_agent(aid) for aid in self.agent_ids],
            return_exceptions=True,
        )

        for agent_id, result in zip(self.agent_ids, results, strict=True):
            if isinstance(result, Exception):
                forfeited.append(agent_id)
            elif not result:
                forfeited.append(agent_id)
            else:
                bids.extend(result)

        return bids, forfeited

    def _award_roles(
        self,
        bids: list[Bid],
        tasks: list[TaskAnnouncement],
    ) -> list[RoleAward]:
        """Award roles to highest bidders with conflict resolution."""
        task_map = {t.task_id: t for t in tasks}
        sorted_bids = sorted(bids, key=lambda b: b.utility, reverse=True)
        awarded_agents: set[str] = set()
        awarded_tasks: set[str] = set()
        awards: list[RoleAward] = []

        for bid in sorted_bids:
            if bid.agent_id in awarded_agents or bid.task_id in awarded_tasks:
                continue
            task = task_map.get(bid.task_id)
            if task is None:
                continue
            awards.append(
                RoleAward(
                    agent_id=bid.agent_id,
                    task_id=bid.task_id,
                    role=task.role,
                    utility=bid.utility,
                )
            )
            awarded_agents.add(bid.agent_id)
            awarded_tasks.add(bid.task_id)

        return awards

    def update_bidder_weights(self, weights: dict[RoleEnum, float]) -> None:
        for bidder in self._bidders.values():
            bidder.update_weights(weights)
