"""Tier-2 strategy layer: LLM-backed doctrine generation."""

from __future__ import annotations

import json
import os
from typing import Any

from contracts import DoctrineUpdate, RoleEnum

DEFAULT_DOCTRINE_WEIGHTS: dict[RoleEnum, float] = {
    RoleEnum.FLANK: 1.0,
    RoleEnum.DISTRACT: 1.0,
    RoleEnum.STEALTH_COVER: 1.0,
    RoleEnum.OVERWATCH: 1.0,
    RoleEnum.BREACH: 1.0,
}


class StrategyLayer:
    """Async Groq-backed doctrine generator with graceful degradation."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        self._client: Any = None
        if self._api_key:
            try:
                from groq import Groq

                self._client = Groq(api_key=self._api_key)
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def generate_doctrine(
        self,
        squad_id: str,
        context: str,
        priority_objective: str = "default",
    ) -> DoctrineUpdate:
        if not self.available:
            return self._fallback_doctrine(squad_id, priority_objective)

        try:
            response = self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return JSON with role_weights (flank,distract,stealth-cover,"
                            "overwatch,breach as floats 0-2), priority_objective, fallback_plan."
                        ),
                    },
                    {"role": "user", "content": f"Squad {squad_id} context: {context}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            weights = {
                RoleEnum(k): float(v)
                for k, v in data.get("role_weights", {}).items()
                if k in [r.value for r in RoleEnum]
            }
            return DoctrineUpdate(
                squad_id=squad_id,
                role_weights=weights or DEFAULT_DOCTRINE_WEIGHTS,
                priority_objective=data.get("priority_objective", priority_objective),
                fallback_plan=data.get("fallback_plan", "hold-position"),
            )
        except Exception:
            return self._fallback_doctrine(squad_id, priority_objective)

    def _fallback_doctrine(self, squad_id: str, priority_objective: str) -> DoctrineUpdate:
        return DoctrineUpdate(
            squad_id=squad_id,
            role_weights=DEFAULT_DOCTRINE_WEIGHTS.copy(),
            priority_objective=priority_objective,
            fallback_plan="reflex-only-fallback",
        )
