"""Demo driver: streams a scenario through the live gateway at a fixed tick rate."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx

from simulation.driver import resolve_scenario, scenario_name_from_path, stream_simulation
from simulation.scenario import ScenarioConfig

DEFAULT_SCENARIO = Path(__file__).parent / "scenarios" / "default.yaml"


async def create_squad_for_scenario(
    gateway: str,
    scenario_path: Path,
) -> tuple[str, ScenarioConfig]:
    scenario = resolve_scenario(str(scenario_path))
    file_name = scenario_name_from_path(scenario_path)
    async with httpx.AsyncClient(base_url=gateway.rstrip("/"), timeout=30.0) as http:
        response = await http.post("/squads/from-scenario", json={"scenario": file_name})
        response.raise_for_status()
        squad_id = response.json()["squad_id"]
    return squad_id, scenario


async def run_demo(
    gateway: str,
    scenario_path: Path,
    hz: float | None,
    ticks: int,
    squad_index: int = 0,
    *,
    squad_id: str | None = None,
) -> dict[str, int]:
    scenario = resolve_scenario(str(scenario_path))
    effective_hz = hz if hz is not None else scenario.tick_rate_hz

    if squad_id is None:
        squad_id, _scenario = await create_squad_for_scenario(gateway, scenario_path)

    prefix = f"[squad-{squad_index}] " if squad_index else ""
    print(f"{prefix}Squad {squad_id} — streaming {ticks} ticks at {effective_hz}Hz")
    print(f"{prefix}Scenario: {scenario.name} -> {scenario.objective}")
    print(f"{prefix}Viewer: {gateway}/viewer?squad={squad_id}")
    print(f"{prefix}Console: {gateway}/console")

    stats = await stream_simulation(
        gateway,
        squad_id,
        scenario,
        ticks=ticks,
        hz=effective_hz,
    )
    print(
        f"{prefix}Done: {stats['directives']} directives, {stats['replans']} replans, "
        f"mission={stats['mission']}"
    )
    return {
        "directives": int(stats["directives"]),
        "replans": int(stats["replans"]),
        "mission": stats["mission"],
    }


async def run_multi_demo(
    gateway: str,
    scenario_path: Path,
    hz: float | None,
    ticks: int,
    squads: int,
) -> None:
    await asyncio.gather(
        *[
            run_demo(gateway, scenario_path, hz, ticks, squad_index=i + 1)
            for i in range(squads)
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="TactixNet demo driver")
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument(
        "--hz",
        type=float,
        default=None,
        help="Tick rate (default: scenario tick_rate_hz)",
    )
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--squads", type=int, default=1, help="Number of concurrent squads")
    parser.add_argument(
        "--squad-id",
        default=None,
        help="Use an existing squad (create via /console or POST /squads first)",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Create squad for scenario and print IDs without streaming ticks",
    )
    args = parser.parse_args()

    if args.create_only:
        async def _create() -> None:
            squad_id, scenario = await create_squad_for_scenario(args.gateway, args.scenario)
            print(f"Squad {squad_id} created (not started)")
            print(f"Scenario: {scenario.name}")
            print(f"Console: {args.gateway}/console")
            print(f"Viewer: {args.gateway}/viewer?squad={squad_id}")

        asyncio.run(_create())
        return

    if args.squads > 1:
        if args.squad_id is not None:
            parser.error("--squad-id cannot be used with --squads > 1")
        asyncio.run(run_multi_demo(args.gateway, args.scenario, args.hz, args.ticks, args.squads))
    else:
        asyncio.run(
            run_demo(
                args.gateway,
                args.scenario,
                args.hz,
                args.ticks,
                squad_id=args.squad_id,
            )
        )


if __name__ == "__main__":
    main()
