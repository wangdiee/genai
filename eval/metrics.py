"""Metrics collection for the Part A before/after comparison (skeleton).

Quantitative:
  - time_to_update_seconds  — wall-clock time per scenario run
  - field_completeness_pct  — fraction of required fields populated
  - overdue_detection_recall — detected overdue/missing activities vs ground truth
  - scoring_consistency     — agreement of priority/probability across repeats

Qualitative: 1–5 rubric scored by the human reviewer (see QUALITATIVE_RUBRIC).
"""

import json
import os
import time
from collections import Counter

REQUIRED_FIELDS = [
    "expected_revenue",
    "probability",
    "priority",
    "date_deadline",
    "description",
]


def field_completeness(record, required_fields=REQUIRED_FIELDS):
    """Percentage of required CRM fields that are populated."""
    if not required_fields:
        return 100.0
    filled = sum(1 for f in required_fields if record.get(f) not in (None, "", False))
    return round(100.0 * filled / len(required_fields), 1)


class Timer:
    """Context manager measuring wall-clock seconds."""

    def __init__(self):
        self._t0 = None
        self.elapsed = None

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = round(time.perf_counter() - self._t0, 1)


def overdue_detection_recall(detected_ids, ground_truth_ids):
    """Recall of overdue/missing-activity detection. None when no ground truth."""
    gt, det = set(ground_truth_ids), set(detected_ids)
    if not gt:
        return None
    return round(len(gt & det) / len(gt), 3)


def _prob_bucket(p):
    if p is None:
        return None
    b = int(p) // 10 * 10
    return f"{b}-{b + 10}"


def scoring_consistency(runs):
    """Agreement of (priority, probability-bucket) across repeated runs.

    ``runs``: list of dicts with 'priority' and 'probability' keys.
    Returns the fraction of runs matching the modal recommendation.
    """
    if not runs:
        return None
    keys = [(r.get("priority"), _prob_bucket(r.get("probability"))) for r in runs]
    top = Counter(keys).most_common(1)[0][1]
    return round(top / len(keys), 3)


#: Qualitative rubric (1–5), scored by the human reviewer per scenario.
QUALITATIVE_RUBRIC = {
    "evidence_quality": "recommendations cite specific, checkable evidence",
    "actionability": "next steps are concrete and correctly assigned",
    "risk_flagging": "risks / missing info are surfaced, not hidden",
    "tone_and_clarity": "summary is clear and handover-ready",
}


def save_results(path, results):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False, default=str)


def load_results(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def summarize_before_after(before, after):
    """Build side-by-side metrics table rows from two result dicts."""
    rows = []
    for key in (
        "time_to_update_seconds",
        "field_completeness_pct",
        "overdue_detection_recall",
        "scoring_consistency",
    ):
        rows.append({"metric": key, "before": before.get(key), "after": after.get(key)})
    return rows
