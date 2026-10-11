"""Write the FastAPI OpenAPI schema (deterministic JSON) to the given path."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from overclouded.api.app import create_app

    out = Path(argv[0]) if argv else Path("openapi.json")
    schema = create_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"OpenAPI schema written to {out} ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
