import pytest

from engine.strategy import StrategyLayer


@pytest.mark.asyncio
async def test_strategy_degrades_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    layer = StrategyLayer(api_key=None)
    assert layer.available is False
    doctrine = await layer.generate_doctrine("squad-1", context="guards ahead")
    assert doctrine.fallback_plan == "reflex-only-fallback"
    assert len(doctrine.role_weights) == 5


@pytest.mark.asyncio
async def test_strategy_degrades_on_llm_failure() -> None:
    layer = StrategyLayer(api_key="fake-key")

    class BrokenChat:
        def create(self, **kwargs):
            raise ConnectionError("LLM unavailable")

    class BrokenClient:
        chat = BrokenChat()

    layer._client = BrokenClient()
    doctrine = await layer.generate_doctrine("squad-2", context="test")
    assert doctrine.fallback_plan == "reflex-only-fallback"
