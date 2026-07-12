"""OpenAPI schema export and documentation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app import app

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT / "openapi" / "openapi.json"


def test_openapi_json_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "TactixNet Gateway"
    paths = spec.get("paths", {})
    assert "/squads" in paths
    assert "/health" in paths
    assert "/squads/{squad_id}/events" in paths
    assert "/squads/{squad_id}/scenario" in paths
    assert "/squads/{squad_id}/simulate" in paths
    patch = paths["/squads/{squad_id}/scenario"].get("patch")
    delete = paths["/squads/{squad_id}"].get("delete")
    assert patch is not None
    assert delete is not None


def test_committed_openapi_matches_gateway() -> None:
    if not OPENAPI_PATH.exists():
        pytest.skip("run scripts/export_openapi.py to generate openapi/openapi.json")
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    live = app.openapi()
    assert committed["info"]["title"] == live["info"]["title"]
    assert set(committed["paths"]) == set(live["paths"])


def test_swagger_ui_available() -> None:
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
