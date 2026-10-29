"""Write the API's OpenAPI document to contracts/openapi.json.

Run after any API change: `uv run python scripts/export_openapi.py`
"""

from pathlib import Path

from lumior.contract import render_openapi

OUTPUT = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"


def main() -> None:
    OUTPUT.write_text(render_openapi(), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
