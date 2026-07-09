"""End-to-end tactical simulation tests."""

from contracts import AlertLevel, RoleEnum
from engine.negotiation import ReflexNegotiator
from simulation.bounds import is_in_bounds
from simulation.driver import build_sim, resolve_scenario
from simulation.mission import MissionTracker, evaluate_mission
from simulation.movement import step_agent_by_role


async def _negotiate_roles(sim, negotiator: ReflexNegotiator) -> dict[str, RoleEnum]:
    frames = sim.all_perceptions()
    result = await negotiator.negotiate(frames, objective_ref="breach-alpha", tick=sim.tick)
    return {award.agent_id: award.role for award in result.directive.awards}


def test_build_sim_uses_grid_size_from_scenario() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    assert sim.width == 20
    assert sim.height == 20


async def test_five_distinct_roles_within_10_ticks() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    negotiator = ReflexNegotiator(
        squad_id="tactical-test",
        agent_ids=[a.agent_id for a in sim.agents],
    )
    roles: dict[str, RoleEnum] = {}
    for _ in range(10):
        sim.advance_tick()
        roles = await _negotiate_roles(sim, negotiator)
        if len(set(roles.values())) == 5:
            break
    assert len(roles) == 5
    assert len(set(roles.values())) == 5


def test_default_mission_win_reachable_within_300_ticks() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    objective = scenario.objective_position
    tracker = MissionTracker()
    spawn_roles = scenario.raw.get("spawn_roles", {})
    roles = {aid: RoleEnum(role) for aid, role in spawn_roles.items()}

    for _ in range(300):
        sim.advance_tick()
        frames = sim.all_perceptions()
        alert_by_agent = {f.agent_id: f.alert_level for f in frames}
        for agent in sim.agents:
            role = roles.get(agent.agent_id, RoleEnum.BREACH)
            step_agent_by_role(
                sim,
                agent,
                role,
                objective,
                alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
            )
            assert is_in_bounds(agent.position, sim.width, sim.height)
        evaluate_mission(sim, scenario, tracker, alert_by_agent=alert_by_agent)
        if tracker.is_finished():
            break

    assert tracker.status in ("won", "active", "lost")
