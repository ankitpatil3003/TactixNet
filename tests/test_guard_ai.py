import math

from simulation.grid import GridSim, Guard, SquadAgent, _guard_can_see_agent


def test_guard_enters_chase_when_agent_close() -> None:
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(10.1, 10.0))],
        guards=[
            Guard(
                guard_id="g1",
                position=(10.0, 10.0),
                patrol_route=[(10.0, 10.0)],
                heading=0.0,
            )
        ],
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


def test_guard_patrol_interpolates_not_teleport() -> None:
    guard = Guard(
        guard_id="g1",
        position=(10.0, 10.0),
        patrol_route=[(10.0, 10.0), (14.0, 10.0)],
        patrol_speed=0.2,
    )
    sim = GridSim(agents=[], guards=[guard])
    start = guard.position
    sim.advance_tick()
    moved = math.hypot(
        guard.position[0] - start[0],
        guard.position[1] - start[1],
    )
    assert 0.0 < moved <= guard.patrol_speed + 1e-6
    assert guard.position != (14.0, 10.0)


def test_directional_vision_blocks_rear_approach() -> None:
    guard = Guard(
        guard_id="g1",
        position=(10.0, 10.0),
        patrol_route=[(10.0, 10.0)],
        heading=0.0,
        vision_range=5.0,
        vision_angle_deg=120.0,
    )
    front = (12.0, 10.0)
    rear = (8.0, 10.0)
    assert _guard_can_see_agent(guard, front)
    assert not _guard_can_see_agent(guard, rear)


def test_directional_vision_allows_front_approach() -> None:
    guard = Guard(
        guard_id="g1",
        position=(10.0, 10.0),
        patrol_route=[(10.0, 10.0)],
        heading=90.0,
        vision_range=4.0,
        vision_angle_deg=120.0,
    )
    assert _guard_can_see_agent(guard, (10.0, 12.0))
    assert not _guard_can_see_agent(guard, (10.0, 8.0))


def test_agent_becomes_compromised_after_close_contact() -> None:
    from contracts import AlertLevel

    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=(10.2, 10.0))],
        guards=[
            Guard(
                guard_id="g1",
                position=(10.0, 10.0),
                patrol_route=[(10.0, 10.0)],
                heading=0.0,
            )
        ],
    )
    alerts = []
    for _ in range(4):
        sim.advance_tick()
        alerts.append(sim.perception_for_agent(sim.agents[0]).alert_level)
    assert AlertLevel.ALERT in alerts[:3]
    assert alerts[-1] == AlertLevel.COMPROMISED
