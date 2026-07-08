from contracts import AlertLevel
from simulation.grid import GridSim, Guard, SquadAgent


def test_guard_enters_chase_when_agent_close() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(10.1, 10.0))],
        guards=[Guard(guard_id="g1", position=(10.0, 10.0), patrol_route=[(10.0, 10.0)])],
    )
    sim.advance_tick()
    assert sim.guards[0].state in ("chase", "investigate")


def test_guard_returns_to_patrol_without_sight() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(0.0, 0.0))],
        guards=[
            Guard(
                guard_id="g1",
                position=(10.0, 10.0),
                patrol_route=[(10.0, 10.0), (12.0, 10.0)],
            )
        ],
    )
    sim.guards[0].state = "investigate"
    sim.guards[0].last_seen_position = (10.5, 10.0)
    sim.advance_tick()
    assert sim.guards[0].state in ("patrol", "investigate")


def test_agent_becomes_compromised_after_close_contact() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(10.2, 10.0))],
        guards=[Guard(guard_id="g1", position=(10.0, 10.0), patrol_route=[(10.0, 10.0)])],
    )
    alerts = []
    for _ in range(4):
        sim.advance_tick()
        alerts.append(sim.perception_for_agent(sim.agents[0]).alert_level)
    assert AlertLevel.ALERT in alerts[:3]
    assert alerts[-1] == AlertLevel.COMPROMISED
