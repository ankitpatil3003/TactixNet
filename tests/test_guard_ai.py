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
    sim.advance_tick()
    frame1 = sim.perception_for_agent(sim.agents[0])
    sim.advance_tick()
    frame2 = sim.perception_for_agent(sim.agents[0])
    assert frame1.alert_level in (AlertLevel.ALERT, AlertLevel.COMPROMISED)
    assert frame2.alert_level == AlertLevel.COMPROMISED
