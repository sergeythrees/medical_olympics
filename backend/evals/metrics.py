"""Field-level comparison of an extracted case with a hand-annotated gold case.

Free-text fields (findings, option labels) are matched fuzzily: the model may say
"CT pulmonary angiography" where the annotator wrote "CTPA". The numbers that matter
for the participant (vitals, lab values) are compared exactly.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.schemas import CaseIn, Finding

MATCH_THRESHOLD = 0.6

# Abbreviations clinicians and models use interchangeably. Expanded before comparison.
ABBREVIATIONS = {
    "abg": "arterial blood gas",
    "bp": "blood pressure",
    "ct": "computed tomography",
    "ctpa": "computed tomography pulmonary angiography",
    "cxr": "chest x-ray",
    "ecg": "electrocardiogram",
    "ekg": "electrocardiogram",
    "gcs": "glasgow coma scale",
    "jvp": "jugular venous pressure",
    "lp": "lumbar puncture",
}


def _norm(s: str) -> str:
    tokens = re.findall(r"[\w.%+-]+", s.casefold())
    return " ".join(ABBREVIATIONS.get(t, t) for t in tokens)


def similarity(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:  # "Warfarin" vs "Start warfarin"
        return max(0.8, SequenceMatcher(None, a, b).ratio())
    tokens_a, tokens_b = set(a.split()), set(b.split())
    jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return max(jaccard, SequenceMatcher(None, a, b).ratio())


def finding_similarity(g: Finding, p: Finding) -> float:
    """Name similarity, or value similarity when both values are descriptive enough to identify
    the finding on their own ("Legs: no oedema, calves soft" = "Leg examination: no oedema, calves soft")."""
    descriptive = min(len(_norm(g.value).split()), len(_norm(p.value).split())) >= 3
    return max(similarity(g.name, p.name), similarity(g.value, p.value) if descriptive else 0.0)


def match[T](gold: list[T], pred: list[T], sim: Callable[[T, T], float] = similarity) -> list[tuple[int, int]]:
    """Greedy one-to-one matching by descending similarity. Returns (gold_idx, pred_idx) pairs."""
    pairs = sorted(((sim(g, p), i, j) for i, g in enumerate(gold) for j, p in enumerate(pred)), reverse=True)
    used_g, used_p, out = set(), set(), []
    for score, i, j in pairs:
        if score < MATCH_THRESHOLD:
            break
        if i not in used_g and j not in used_p:
            used_g.add(i)
            used_p.add(j)
            out.append((i, j))
    return out


@dataclass
class PRF:
    tp: int
    n_gold: int
    n_pred: int

    @property
    def precision(self) -> float:
        return self.tp / self.n_pred if self.n_pred else 1.0

    @property
    def recall(self) -> float:
        return self.tp / self.n_gold if self.n_gold else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", s))


def _tokens(f: Finding) -> set[str]:
    return set(_norm(f"{f.name} {f.value}").split())


def compare(gold: CaseIn, pred: CaseIn, source: str) -> dict[str, float]:
    m: dict[str, float] = {}

    # Scalars.
    m["patient"] = float(gold.patient == pred.patient)
    vitals_g, vitals_p = gold.vitals.model_dump(), pred.vitals.model_dump()
    checked = [k for k in vitals_g if vitals_g[k] is not None or vitals_p[k] is not None]
    m["vitals_accuracy"] = (
        sum(
            vitals_g[k] is not None and vitals_p[k] is not None and abs(vitals_g[k] - vitals_p[k]) < 0.05
            for k in checked
        )
        / len(checked)
        if checked
        else 1.0
    )

    # Findings, content: is every gold fact somewhere in the prediction (however it is split
    # into findings), and is every number the model wrote actually in the source text?
    # Tokens include negations, so "no neck stiffness" does not cover "neck stiffness: present".
    m["findings_coverage"] = (
        sum(any(len(_tokens(g) & _tokens(p)) >= 0.75 * len(_tokens(g)) for p in pred.findings) for g in gold.findings)
        / len(gold.findings)
        if gold.findings
        else 1.0
    )
    source_numbers = _numbers(source)
    m["findings_grounded"] = (
        sum(_numbers(p.value) <= source_numbers for p in pred.findings) / len(pred.findings) if pred.findings else 1.0
    )

    # Findings, structure: one-to-one agreement with the annotation. Sensitive to granularity
    # ("neuro exam" as one finding vs six), so it is reported but not gated.
    pairs = match(gold.findings, pred.findings, finding_similarity)
    prf = PRF(len(pairs), len(gold.findings), len(pred.findings))
    m["findings_precision"], m["findings_recall"], m["findings_f1"] = prf.precision, prf.recall, prf.f1
    numeric = [(i, j) for i, j in pairs if _numbers(gold.findings[i].value)]
    m["finding_values_accuracy"] = (
        sum(_numbers(gold.findings[i].value) <= _numbers(pred.findings[j].value) for i, j in numeric) / len(numeric)
        if numeric
        else 1.0
    )

    # Answer key. The single most important field: is the 10-point diagnosis the right one?
    gold_dx = next(o.label for o in gold.diagnosis_options if o.points == 10)
    pred_dx = next(o.label for o in pred.diagnosis_options if o.points == 10)
    m["correct_diagnosis"] = float(similarity(gold_dx, pred_dx) >= MATCH_THRESHOLD)
    dx_pairs = match([o.label for o in gold.diagnosis_options], [o.label for o in pred.diagnosis_options])
    m["diagnosis_options_recall"] = PRF(len(dx_pairs), len(gold.diagnosis_options), 0).recall

    g_mgmt, p_mgmt = gold.management_options, pred.management_options
    mgmt_pairs = match([o.label for o in g_mgmt], [o.label for o in p_mgmt])
    prf = PRF(len(mgmt_pairs), len(g_mgmt), len(p_mgmt))
    m["management_f1"] = prf.f1
    # Safety: a harmful action scored as indicated (or vice versa) rewards dangerous answers.
    m["management_polarity_errors"] = sum(_sign(g_mgmt[i].points) != _sign(p_mgmt[j].points) for i, j in mgmt_pairs)
    m["management_points_exact"] = (
        sum(g_mgmt[i].points == p_mgmt[j].points for i, j in mgmt_pairs) / len(mgmt_pairs) if mgmt_pairs else 0.0
    )
    return m
