from app.schemas import CaseIn, Finding
from conftest import GOLDEN, golden
from evals.metrics import compare, finding_similarity, match, similarity

SOURCE = (GOLDEN / "inferior-stemi.txt").read_text()


def test_gold_against_itself_is_perfect():
    gold = CaseIn.model_validate(golden("inferior-stemi"))
    m = compare(gold, gold, SOURCE)
    assert m["management_polarity_errors"] == 0
    assert all(v == 1.0 for k, v in m.items() if k != "management_polarity_errors")


def test_fuzzy_matching_tolerates_wording():
    assert similarity("Warfarin", "Start warfarin") >= 0.8
    assert similarity("Pulmonary embolism", "Acute pulmonary embolism") >= 0.6
    assert similarity("Aspirin", "Lumbar puncture") < 0.6
    assert match(["CTPA", "D-dimer"], ["D-dimer level", "Chest X-ray"]) == [(1, 0)]
    assert similarity("CTPA", "CT pulmonary angiography") >= 0.8
    assert similarity("GCS", "Glasgow Coma Scale") == 1.0


def test_findings_match_on_descriptive_values():
    g = Finding(kind="exam", name="Legs", value="No oedema, calves soft and non-tender")
    p = Finding(kind="exam", name="Leg examination", value="no oedema, calves soft and non-tender")
    assert finding_similarity(g, p) >= 0.9
    # Short values ("15", "Normal") are not specific enough to match on.
    assert (
        finding_similarity(
            Finding(kind="lab", name="INR", value="1.0"), Finding(kind="lab", name="Troponin", value="1.0")
        )
        < 0.6
    )


def test_errors_are_detected():
    gold_raw = golden("inferior-stemi")
    pred_raw = golden("inferior-stemi")
    pred_raw["vitals"]["heart_rate"] = 125  # wrong vital
    pred_raw["findings"] = pred_raw["findings"][:-2]  # dropped two findings
    pred_raw["findings"][6]["value"] = "18 ng/L"  # troponin 180 -> 18
    pred_raw["management_options"][4]["points"] = 5  # nitroglycerin: harmful -> indicated
    for o in pred_raw["diagnosis_options"]:  # NSTEMI marked as the answer
        o["points"] = 10 if o["label"] == "NSTEMI" else 0

    m = compare(CaseIn.model_validate(gold_raw), CaseIn.model_validate(pred_raw), SOURCE)

    assert m["vitals_accuracy"] == 5 / 6
    assert m["findings_recall"] == 9 / 11 and m["findings_precision"] == 1.0
    assert m["finding_values_accuracy"] < 1.0
    assert m["findings_grounded"] < 1.0  # "18 ng/L" is not in the source text
    assert m["findings_coverage"] == 9 / 11
    assert m["correct_diagnosis"] == 0.0
    assert m["management_polarity_errors"] == 1


def test_coverage_is_robust_to_granularity_but_not_to_negation():
    gold = CaseIn.model_validate(golden("sah"))
    exam = [f for f in gold.findings if f.kind == "exam"]
    merged = "; ".join(f"{f.name} {f.value}" for f in exam)
    pred = gold.model_copy(
        update={
            "findings": [Finding(kind="exam", name="Neurological examination", value=merged)]
            + [f for f in gold.findings if f.kind != "exam"]
        }
    )
    source = (GOLDEN / "sah.txt").read_text()
    m = compare(gold, pred, source)
    assert m["findings_coverage"] == 1.0
    assert m["findings_recall"] < 1.0

    no_stiffness = Finding(kind="exam", name="Neck stiffness", value="No")
    negated = gold.model_copy(
        update={"findings": [no_stiffness if f.name == "Neck stiffness" else f for f in gold.findings]}
    )
    assert compare(gold, negated, source)["findings_coverage"] < 1.0
