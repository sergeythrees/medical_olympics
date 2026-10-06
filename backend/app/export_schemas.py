"""Write the contract files that other parts of the repo consume:
- schemas/openapi.json             -> frontend TypeScript types (`pnpm gen:api`)
- schemas/clinical_case.schema.json -> the JSON schema the LLM extraction fills

`tests/test_contract.py` fails if they are stale.
"""

import json
from pathlib import Path

from app.main import app
from app.schemas import CaseIn

OUT = Path(__file__).parent.parent / "schemas"


def render() -> dict[str, str]:
    return {
        "openapi.json": json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        "clinical_case.schema.json": json.dumps(CaseIn.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
    }


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, content in render().items():
        (OUT / name).write_text(content)
        print(f"wrote schemas/{name}")
