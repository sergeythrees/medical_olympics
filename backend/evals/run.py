"""Extraction eval harness.

    uv run python -m evals.run                          # call the configured LLM, score, save predictions
    uv run python -m evals.run --predictions evals/runs/<run>   # re-score saved outputs offline

Every golden case is evals/golden/<name>.txt (raw text) + <name>.json (hand-annotated CaseIn).
Exits non-zero if the run misses the quality gates, so it can block a prompt/model change in CI.
"""

import argparse
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.extraction import ExtractionFailed, extract_case, make_llm
from app.schemas import CaseIn
from evals.metrics import compare

GOLDEN = Path(__file__).parent / "golden"
RUNS = Path(__file__).parent / "runs"

# Quality gates: the answer key must be right and must never reward a harmful action.
GATES = {
    "schema_valid": 1.0,
    "correct_diagnosis": 1.0,
    "vitals_accuracy": 0.95,
    "findings_coverage": 0.9,
    "findings_grounded": 1.0,
    "finding_values_accuracy": 0.95,
}
MAX_POLARITY_ERRORS = 0

METRICS = [
    "schema_valid", "attempts", "latency_s", "correct_diagnosis", "management_polarity_errors",
    "patient", "vitals_accuracy", "findings_coverage", "findings_grounded", "finding_values_accuracy",
    "findings_precision", "findings_recall", "findings_f1",
    "diagnosis_options_recall", "management_f1", "management_points_exact",
]  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, help="score saved predictions instead of calling the LLM")
    args = parser.parse_args()

    if args.predictions:
        run_dir, llm = args.predictions, None
    else:
        llm = make_llm(settings)
        run_dir = RUNS / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{llm.model}"
        run_dir.mkdir(parents=True)

    rows: dict[str, dict[str, float]] = {}
    for gold_path in sorted(GOLDEN.glob("*.json")):
        name = gold_path.stem
        gold = CaseIn.model_validate_json(gold_path.read_text())
        pred_path = run_dir / f"{name}.json"
        row: dict[str, float] = {}
        try:
            meta_path = run_dir / f"{name}.meta.json"
            source = (GOLDEN / f"{name}.txt").read_text()
            if llm:
                result = extract_case(source, llm)
                pred_path.write_text(result.case.model_dump_json(indent=2))
                meta_path.write_text(json.dumps({"attempts": result.attempts, "latency_s": round(result.latency_s, 1)}))
            if meta_path.exists():
                row |= json.loads(meta_path.read_text())
            pred = CaseIn.model_validate_json(pred_path.read_text())
            row |= {"schema_valid": 1.0} | compare(gold, pred, source)
        except (ExtractionFailed, ValueError) as e:  # ValidationError is a ValueError
            print(f"{name}: extraction failed: {e}", file=sys.stderr)
            row |= {"schema_valid": 0.0}
        rows[name] = row

    metrics = [k for k in METRICS if any(k in r for r in rows.values())]
    summary = {k: statistics.mean(r.get(k, 0.0) for r in rows.values()) for k in metrics}
    summary["management_polarity_errors"] = sum(r.get("management_polarity_errors", 0) for r in rows.values())

    print(f"run: {run_dir}\n")
    print("| metric | " + " | ".join(rows) + " | **total** |")
    print("|---" * (len(rows) + 2) + "|")
    for k in metrics:
        cells = [_fmt(r.get(k)) for r in rows.values()]
        print(f"| {k} | " + " | ".join(cells) + f" | **{_fmt(summary[k])}** |")
    (run_dir / "report.json").write_text(json.dumps({"summary": summary, "cases": rows}, indent=2))

    failed = [f"{k} {summary.get(k, 0):.2f} < {v}" for k, v in GATES.items() if summary.get(k, 0) < v]
    if summary["management_polarity_errors"] > MAX_POLARITY_ERRORS:
        failed.append(f"management_polarity_errors {summary['management_polarity_errors']:.0f} > 0")
    print("\nquality gates: " + ("PASS" if not failed else "FAIL — " + "; ".join(failed)))
    return 1 if failed else 0


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return str(v) if isinstance(v, int) else f"{v:.2f}"


if __name__ == "__main__":
    sys.exit(main())
