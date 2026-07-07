"""Contract Net Protocol bidder."""

import asyncio

from agents.perception import AgentPerception
from agents.utility import DEFAULT_ROLE_WEIGHTS, utility_for_role
from contracts import Bid, PerceptionFrame, RoleEnum, TaskAnnouncement


class CNPBidder:
    """Agent-side CNP bidder computing utility bids for announced tasks."""

    def __init__(
        self,
        agent_id: str,
        bid_timeout_s: float = 0.04,
        weights: dict[RoleEnum, float] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.bid_timeout_s = bid_timeout_s
        self.weights = weights or DEFAULT_ROLE_WEIGHTS.copy()

    async def compute_bid(
        self,
        frame: PerceptionFrame,
        task: TaskAnnouncement,
    ) -> Bid | None:
        try:
            return await asyncio.wait_for(
                self._compute_bid_inner(frame, task),
                timeout=self.bid_timeout_s,
            )
        except TimeoutError:
            return None

    async def _compute_bid_inner(
        self,
        frame: PerceptionFrame,
        task: TaskAnnouncement,
    ) -> Bid:
        perception = AgentPerception(frame)
        utility = utility_for_role(perception, task.role, self.weights)
        constraints: list[str] = []
        if perception.is_compromised() and task.role == RoleEnum.BREACH:
            constraints.append("compromised-no-breach")
            utility *= 0.1
        return Bid(
            agent_id=self.agent_id,
            task_id=task.task_id,
            utility=utility,
            constraints=constraints,
        )

    def update_weights(self, weights: dict[RoleEnum, float]) -> None:
        self.weights.update(weights)
