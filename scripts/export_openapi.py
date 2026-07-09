"""Export the gateway OpenAPI schema to openapi/openapi.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gateway.app import app  # noqa: E402


def main() -> None:
    output = ROOT / "openapi" / "openapi.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
