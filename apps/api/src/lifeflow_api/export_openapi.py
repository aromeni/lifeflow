"""Print the OpenAPI schema for contract generation.

Used by scripts/generate-contracts.sh:
    uv run python -m lifeflow_api.export_openapi > packages/contracts/openapi.json
"""

import json

from lifeflow_api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
