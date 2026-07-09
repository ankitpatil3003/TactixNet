from contracts import AlertLevel, RoleEnum
from simulation.bounds import clamp_position, is_in_bounds
from simulation.driver import build_sim, resolve_scenario
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.movement import move_away, move_toward, step_agent_by_role


def test_move_toward_reaches_target() -> None:
    start = (0.0, 0.0)
    end = move_toward(start, (1.0, 0.0), step=0.5)
    assert end == (0.5, 0.0)


def test_clamp_position_keeps_entity_inside_grid() -> None:
    assert clamp_position((-1.0, 25.0), 20, 20) == (0.5, 19.5)


def test_is_in_bounds() -> None:
    assert is_in_bounds((10.0, 10.0), 20, 20)
    assert not is_in_bounds((21.0, 10.0), 20, 20)


def test_breach_role_moves_toward_objective() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(0.0, 0.0))],
        guards=[],
    )
    objective = (10.0, 0.0)
    step_agent_by_role(sim, sim.agents[0], RoleEnum.BREACH, objective, step=1.0)
    assert sim.agents[0].position[0] > 0.0


def test_distract_role_moves_toward_guard() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(0.0, 0.0))],
        guards=[Guard(guard_id="g1", position=(5.0, 0.0), patrol_route=[(5.0, 0.0)])],
    )
    step_agent_by_role(sim, sim.agents[0], RoleEnum.DISTRACT, (10.0, 10.0), step=0.5)
    assert sim.agents[0].position[0] > 0.0


def test_move_away_blends_toward_objective_at_edge() -> None:
    pos = (19.5, 10.0)
    threat = (18.0, 10.0)
    result = move_away(
        pos,
        threat,
        step=2.0,
        objective=(10.0, 10.0),
        bounds=(20.0, 20.0),
    )
    assert is_in_bounds(result, 20, 20)
    assert result[0] <= pos[0]


def test_agent_heading_updates_on_movement() -> None:
    sim = GridSim(agents=[SquadAgent(agent_id="a1", position=(5.0, 5.0))], guards=[])
    step_agent_by_role(sim, sim.agents[0], RoleEnum.BREACH, (15.0, 5.0), step=0.5)
    assert sim.agents[0].heading != 0.0 or sim.agents[0].position[0] > 5.0


def _run_soak_ticks(scenario_name: str, ticks: int = 300) -> GridSim:
    scenario = resolve_scenario(scenario_name)
    sim = build_sim(scenario)
    objective = scenario.objective_position
    spawn_roles = scenario.raw.get("spawn_roles", {})
    roles = {aid: RoleEnum(role) for aid, role in spawn_roles.items()}
    default_role = RoleEnum.STEALTH_COVER

    for _ in range(ticks):
        sim.advance_tick()
        frames = sim.all_perceptions()
        alert_by_agent = {f.agent_id: f.alert_level for f in frames}
        for agent in sim.agents:
            role = roles.get(agent.agent_id, default_role)
            step_agent_by_role(
                sim,
                agent,
                role,
                objective,
                alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
            )
    return sim


def test_default_scenario_agents_stay_in_bounds_300_ticks() -> None:
    sim = _run_soak_ticks("default", ticks=300)
    for agent in sim.agents:
        assert is_in_bounds(agent.position, sim.width, sim.height), agent.agent_id


def test_ambush_scenario_agents_stay_in_bounds_300_ticks() -> None:
    sim = _run_soak_ticks("ambush", ticks=300)
    for agent in sim.agents:
        assert is_in_bounds(agent.position, sim.width, sim.height), agent.agent_id


def test_guards_stay_in_bounds_during_soak() -> None:
    sim = _run_soak_ticks("default", ticks=300)
    for guard in sim.guards:
        assert is_in_bounds(guard.position, sim.width, sim.height), guard.guard_id
