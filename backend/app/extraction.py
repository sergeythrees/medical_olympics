"""Raw clinical text -> CaseIn via an LLM with structured output.

The JSON schema given to the model is CaseIn's own schema, so whatever the model returns
is validated by exactly the same rules as a case POSTed to the API. Rules the schema can't
express (one correct diagnosis, unique labels) are caught by pydantic and fed back to the
model for a bounded number of repair attempts.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import CaseIn

log = logging.getLogger(__name__)

CASE_SCHEMA = CaseIn.model_json_schema()

SYSTEM_PROMPT = """\
You convert a clinical case written by a physician into structured JSON for a medical \
competition, where participants read the case, choose a diagnosis and management, and are scored.

Rules:
- Use only information stated in the text. Never invent vitals, results or history; \
leave a vital sign null if it is not given.
- Respect negation: "no chest pain", "DVT not confirmed", "troponin negative" are negative findings; \
record them as such (e.g. value "negative" / "not present"), never as positive ones.
- findings: every examination, lab, ECG and imaging result with its units, in the order given. \
One finding per examined system or test. A blood gas, a urinalysis and an ECG recording are one \
finding each (all their values together); other blood tests (sodium, creatinine, troponin...) are \
separate findings even when listed on one line. Vital signs go to `vitals`, not to findings.
- diagnosis_options: the final diagnosis gets points 10. Differential diagnoses mentioned in the \
text get 0, or 1-5 if the text says they are partially right. If the text gives fewer than 3 \
differentials, add plausible ones from the clinical picture with 0 points.
- management_options: actions from the text. Essential/indicated actions 5 (or as stated), \
reasonable but non-essential 1-3, actions the text calls contraindicated, harmful or to avoid -5.
- Keep the language of the source text. Do not copy the final diagnosis into the history or the title.
"""


class LLM(Protocol):
    def generate(self, *, system: str, prompt: str, schema: dict) -> str:
        """Return the model's raw JSON text."""
        ...


class DeepSeekLLM:
    """DeepSeek's OpenAI-compatible chat API. It has JSON mode but no schema-constrained decoding,
    so the schema goes into the system prompt and pydantic + the repair loop enforce it."""

    def __init__(self, settings: Settings):
        self.model = settings.deepseek_model
        self._client = httpx.Client(
            base_url=settings.deepseek_base_url,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            timeout=180,
        )

    def generate(self, *, system: str, prompt: str, schema: dict) -> str:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": f"{system}\nReturn one JSON object matching this JSON schema:\n{json.dumps(schema)}",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""


class GeminiLLM:
    """Gemini via the google-genai SDK: Vertex AI on GCP (ADC, no keys) or an API key locally."""

    def __init__(self, settings: Settings):
        from google import genai

        if settings.gemini_api_key:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        elif settings.google_cloud_project:
            self._client = genai.Client(
                vertexai=True, project=settings.google_cloud_project, location=settings.google_cloud_location
            )
        else:
            raise LLMNotConfigured("set GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT (Vertex AI)")
        self.model = settings.gemini_model

    def generate(self, *, system: str, prompt: str, schema: dict) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0,
            ),
        )
        return response.text or ""


class LLMNotConfigured(RuntimeError):
    pass


def make_llm(settings: Settings) -> LLM:
    if settings.deepseek_api_key:
        return DeepSeekLLM(settings)
    if settings.gemini_api_key or settings.google_cloud_project:
        return GeminiLLM(settings)
    raise LLMNotConfigured("set DEEPSEEK_API_KEY, GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT (Vertex AI)")


class ExtractionFailed(RuntimeError):
    def __init__(self, message: str, last_output: str):
        super().__init__(message)
        self.last_output = last_output


@dataclass
class Extraction:
    case: CaseIn
    attempts: int
    latency_s: float


def extract_case(text: str, llm: LLM, max_attempts: int = 3) -> Extraction:
    started = time.perf_counter()
    prompt = f"Clinical case:\n<<<\n{text}\n>>>"
    output = ""
    for attempt in range(1, max_attempts + 1):
        output = llm.generate(system=SYSTEM_PROMPT, prompt=prompt, schema=CASE_SCHEMA)
        try:
            case = CaseIn.model_validate_json(output)
            return Extraction(case=case, attempts=attempt, latency_s=time.perf_counter() - started)
        except ValidationError as e:  # malformed JSON or a broken rule, both reported precisely
            error = str(e)
            log.warning("extraction attempt %d invalid: %s", attempt, error.splitlines()[0])
            prompt = (
                f"Clinical case:\n<<<\n{text}\n>>>\n\n"
                f"Your previous answer:\n{output}\n\n"
                f"It failed validation:\n{error}\n\n"
                "Return the corrected JSON."
            )
    raise ExtractionFailed(f"no valid case after {max_attempts} attempts: {error}", output)
