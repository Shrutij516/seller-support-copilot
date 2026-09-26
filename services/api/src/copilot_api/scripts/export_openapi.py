"""Write the current OpenAPI schema to services/api/openapi.json. Run via `make openapi`.

CI regenerates this into a temp file and diffs it against the committed one, failing if
they differ, so the contract can't silently drift from the code.
"""

import json
from pathlib import Path

from copilot_api.main import app

OUTPUT_PATH = Path(__file__).parents[3] / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
