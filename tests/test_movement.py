from contracts import RoleEnum
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.movement import move_toward, step_agent_by_role


def test_move_toward_reaches_target() -> None:
    start = (0.0, 0.0)
    end = move_toward(start, (1.0, 0.0), step=0.5)
    assert end == (0.5, 0.0)


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
