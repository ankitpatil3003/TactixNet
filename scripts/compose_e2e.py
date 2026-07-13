"""Compose-stack E2E smoke against a live distributed gateway.

Usage (after `docker compose up -d --build`):
  GATEWAY_URL=http://127.0.0.1:8000 python scripts/compose_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from client import SquadClient

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")


async def wait_for_healthy(*, timeout: float = 120.0) -> dict:
    client = SquadClient(GATEWAY)
    deadline = time.monotonic() + timeout
    last_error = "timeout"
    try:
        while time.monotonic() < deadline:
            try:
                body = await client.health()
                if (
                    body.get("status") == "ok"
                    and body.get("engine_mode") == "distributed"
                    and body.get("engine_worker") == "connected"
                ):
                    return body
                last_error = f"health={body}"
            except Exception as exc:
                last_error = str(exc)
            await asyncio.sleep(2.0)
        raise RuntimeError(f"gateway not healthy within {timeout}s: {last_error}")
    finally:
        await client.aclose()


async def run_simulate_smoke() -> None:
    squad = await SquadClient.create_from_scenario(GATEWAY, "default")
    assert squad.squad_id
    try:
        started = await squad.start_simulation(ticks=40)
        assert started["simulation"]["status"] in {"running", "completed"}

        deadline = time.monotonic() + 90.0
        final = None
        while time.monotonic() < deadline:
            status = await squad.get_simulation()
            sim = status["simulation"]
            if sim["status"] in {"completed", "failed", "cancelled"}:
                final = sim
                break
            await asyncio.sleep(1.0)

        assert final is not None, "simulation did not finish"
        assert final["status"] == "completed", final
        assert int(final.get("ticks_run", 0)) >= 1
        print(
            f"[compose-e2e] simulate ok squad={squad.squad_id[:8]}… "
            f"ticks={final.get('ticks_run')} mission={final.get('mission')}"
        )
    finally:
        await squad.aclose()


async def main() -> int:
    health = await wait_for_healthy()
    print(
        f"[compose-e2e] health ok engine_mode={health['engine_mode']} "
        f"engine_worker={health['engine_worker']}"
    )
    await run_simulate_smoke()
    print("[compose-e2e] passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"[compose-e2e] FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
