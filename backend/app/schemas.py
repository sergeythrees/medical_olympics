"""API contract. The same models are:
- the request/response bodies of the REST API (-> OpenAPI -> TypeScript types in the frontend);
- the JSON schema the LLM must fill when extracting a case from raw text
  (exported to ../schemas/clinical_case.schema.json).
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sex = Literal["female", "male"]
FindingKind = Literal["exam", "lab", "imaging", "ecg", "other"]
OptionKind = Literal["diagnosis", "management"]

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class Patient(BaseModel):
    age: int = Field(ge=0, le=120, description="Age in full years.")
    sex: Sex


class Vitals(BaseModel):
    """Vital signs at presentation. Null when not stated in the source."""

    heart_rate: int | None = Field(None, ge=0, le=300, description="Beats per minute.")
    systolic_bp: int | None = Field(None, ge=0, le=300, description="mmHg.")
    diastolic_bp: int | None = Field(None, ge=0, le=200, description="mmHg.")
    respiratory_rate: int | None = Field(None, ge=0, le=80, description="Breaths per minute.")
    temperature_c: float | None = Field(None, ge=25, le=45, description="Degrees Celsius.")
    spo2: int | None = Field(None, ge=0, le=100, description="Oxygen saturation, %.")


class Finding(BaseModel):
    kind: FindingKind
    name: Label = Field(description="What was examined or measured, e.g. 'Troponin I'.")
    value: Label = Field(description="Result with units, e.g. '2.1 ng/mL' or 'ST elevation II, III, aVF'.")


class DiagnosisOption(BaseModel):
    label: Label
    points: int = Field(ge=0, le=10, description="10 = correct diagnosis, 1-5 = partially correct, 0 = wrong.")
    explanation: str | None = Field(None, max_length=2000, description="Why it is (in)correct. Shown after answering.")


class ManagementOption(BaseModel):
    label: Label
    points: int = Field(
        ge=-10, le=10, description="Positive = indicated (5 essential), 0 = neutral, negative = harmful (-5)."
    )
    explanation: str | None = Field(None, max_length=2000)


class CaseIn(BaseModel):
    """A clinical case with answer key, as written by a case author."""

    title: Label
    patient: Patient
    presenting_complaint: Text
    history: Text = Field(description="History of present illness, past history, medications.")
    vitals: Vitals = Field(default_factory=Vitals)
    findings: list[Finding] = Field(default_factory=list, max_length=100)
    diagnosis_options: list[DiagnosisOption] = Field(min_length=2, max_length=20)
    management_options: list[ManagementOption] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _check_answer_key(self) -> "CaseIn":
        if sum(o.points == 10 for o in self.diagnosis_options) != 1:
            raise ValueError("exactly one diagnosis option must be the correct one (points = 10)")
        for kind, options in (("diagnosis", self.diagnosis_options), ("management", self.management_options)):
            labels = [o.label.strip().casefold() for o in options]
            if len(labels) != len(set(labels)):
                raise ValueError(f"{kind} option labels must be unique")
        if not any(o.points > 0 for o in self.management_options):
            raise ValueError("at least one management option must be indicated (points > 0)")
        return self


# ---- what a participant sees: no points, no explanations ----


class OptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str


class CaseSummary(BaseModel):
    id: int
    title: str
    presenting_complaint: str
    patient: Patient


class CasePublic(CaseSummary):
    history: str
    vitals: Vitals
    findings: list[Finding]
    diagnosis_options: list[OptionPublic]
    management_options: list[OptionPublic]


# ---- answers and scoring ----


class SubmissionIn(BaseModel):
    participant: Label
    diagnosis_option_id: int
    management_option_ids: list[int] = Field(default_factory=list, max_length=30)


class ScoredOption(BaseModel):
    id: int
    kind: OptionKind
    label: str
    points: int
    explanation: str | None
    chosen: bool


class SubmissionResult(BaseModel):
    submission_id: int
    case_id: int
    participant: str
    created_at: datetime
    score: int
    max_score: int
    diagnosis_correct: bool
    options: list[ScoredOption] = Field(description="Full answer key with the participant's choices marked.")


class LeaderboardEntry(BaseModel):
    rank: int
    participant: str
    score: int
    max_score: int
    submitted_at: datetime


class ExtractIn(BaseModel):
    text: str = Field(min_length=20, max_length=50_000)
