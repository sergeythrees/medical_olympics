import json

import pytest

from app.extraction import CASE_SCHEMA, ExtractionFailed, extract_case
from conftest import GOLDEN, golden


class ScriptedLLM:
    """Returns pre-baked outputs in order and records the prompts it received."""

    def __init__(self, *outputs: str):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def generate(self, *, system: str, prompt: str, schema: dict) -> str:
        assert schema is CASE_SCHEMA
        self.prompts.append(prompt)
        return self.outputs.pop(0)


RAW = (GOLDEN / "dka.txt").read_text()


def test_valid_output_first_try():
    llm = ScriptedLLM(json.dumps(golden("dka")))
    result = extract_case(RAW, llm)
    assert result.attempts == 1
    assert result.case.title == "Vomiting student"
    assert RAW in llm.prompts[0]


def test_repairs_invalid_json_and_business_rule_violations():
    two_correct = golden("dka")
    two_correct["diagnosis_options"][1]["points"] = 10
    llm = ScriptedLLM('{"title": "Vomiting', json.dumps(two_correct), json.dumps(golden("dka")))

    result = extract_case(RAW, llm)

    assert result.attempts == 3
    # Each retry shows the model its previous output and the exact validation error.
    assert "Invalid JSON" in llm.prompts[1]
    assert "exactly one diagnosis option must be the correct one" in llm.prompts[2]


def test_gives_up_after_max_attempts():
    llm = ScriptedLLM("{}", "{}", "{}")
    with pytest.raises(ExtractionFailed) as e:
        extract_case(RAW, llm, max_attempts=3)
    assert e.value.last_output == "{}"
    assert not llm.outputs


def test_extract_endpoint_without_credentials_is_503(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.deepseek_api_key", None)
    monkeypatch.setattr("app.main.settings.gemini_api_key", None)
    monkeypatch.setattr("app.main.settings.google_cloud_project", None)
    assert client.post("/extract", json={"text": RAW}).status_code == 503


def test_extract_endpoint_returns_draft_case(client, monkeypatch):
    monkeypatch.setattr("app.main.make_llm", lambda _settings: ScriptedLLM(json.dumps(golden("dka"))))
    r = client.post("/extract", json={"text": RAW})
    assert r.status_code == 200
    assert r.json()["diagnosis_options"][0]["label"] == "Diabetic ketoacidosis"
    # The draft is directly acceptable by POST /cases.
    assert client.post("/cases", json=r.json()).status_code == 201
