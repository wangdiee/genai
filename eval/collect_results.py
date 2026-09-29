#!/usr/bin/env python3
"""Collect before/after results for the 4 eval scenarios.

Reads:
  eval/before_snapshot.json      (captured before any agent run)
  eval/runs/s{1..4}.jsonl        (structured agent run logs)

Queries Odoo for the AFTER state of the 4 scenario opportunities.

Writes eval/results.json and prints a Markdown before/after table.

Odoo credentials come from the environment (ODOO_URL/ODOO_DB/ODOO_USER/
ODOO_PASSWORD or ODOO_API_KEY). Usage:
    python -m eval.collect_results
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.odoo_client import OdooClient  # noqa: E402
from eval.metrics import field_completeness, overdue_detection_recall  # noqa: E402
from eval.scenarios import SCENARIOS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = {
    "S1": "Suncrest Media",
    "S2": "Vertex Security",
    "S3": "Greenline Energy",
    "S4": "FreshFork Foods",
}


def load_log(scenario_id):
    path = os.path.join(REPO, "eval", "runs", f"{scenario_id.lower()}.jsonl")
    entries = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    out = {"tool_calls": [], "recommendations": [], "hitl": {}, "elapsed": None,
           "auto_approved": None}
    for e in entries:
        if e.get("kind") == "tool_call":
            out["tool_calls"].append(e)
        elif e.get("kind") == "note" and e.get("message") == "recommendations":
            out["recommendations"] = e.get("items", [])
        elif e.get("kind") == "note" and e.get("message") == "hitl_decision":
            out["hitl"] = {"updates": e.get("approved_updates", {}),
                           "activities": e.get("approved_activities", [])}
            out["auto_approved"] = e.get("auto_approved")
        elif e.get("kind") == "note" and e.get("message") == "run_finished":
            out["elapsed"] = e.get("elapsed_seconds")
    return out


def after_state(client):
    from datetime import date
    today = date.today().isoformat()
    state = {}
    for sid, name in NAMES.items():
        opp = client.find_opportunity_by_name(name)
        acts = client.list_activities(opp["id"])
        state[sid] = {
            "id": opp["id"],
            "expected_revenue": opp["expected_revenue"],
            "probability": opp["probability"],
            "priority": opp["priority"],
            "stage": opp["stage_id"][1] if opp["stage_id"] else None,
            "date_deadline": opp["date_deadline"],
            "description": bool(opp["description"]),
            "activities": [
                {"id": a["id"], "summary": a["summary"],
                 "date_deadline": a["date_deadline"],
                 "overdue": bool(a.get("date_deadline")) and a["date_deadline"] < today}
                for a in acts
            ],
        }
    return state


def check_scenario(scenario_id, log, after):
    """Check the scenario's expected detections against log + after state."""
    sc = next(s for s in SCENARIOS if s["id"] == scenario_id)
    exp = sc["expected"]
    got = {}
    tools = [(t["tool"], t["result_summary"]) for t in log["tool_calls"]]
    recs = {r.get("field"): r for r in log["recommendations"]} or {
        # fall back to approved updates when full recs were not logged
        k: {"recommended_value": v, "evidence": "", "confidence": None}
        for k, v in log["hitl"].get("updates", {}).items()
    }
    if "__next_activity__" not in recs and log["hitl"].get("activities"):
        recs["__next_activity__"] = {"recommended_value": log["hitl"]["activities"][0],
                                     "evidence": "", "confidence": None}

    if "detect_overdue_activity" in exp:
        summaries = " ".join(s for t, s in tools if t == "get_overdue_activities")
        got["detect_overdue_activity"] = "OVERDUE" in summaries or "overdue" in summaries.lower()
    if "recommend_new_activity" in exp or "detect_missing_activity" in exp:
        got["recommend_new_activity"] = "__next_activity__" in recs
    if "expected_priority" in exp:
        got["priority_recommended"] = str(recs.get("priority", {}).get("recommended_value"))
        got["priority_expected"] = exp["expected_priority"]
        got["priority_match"] = got["priority_recommended"] == exp["expected_priority"]
    if "recommend_priority" in exp:
        got["priority_recommended"] = str(recs.get("priority", {}).get("recommended_value"))
        got["priority_expected"] = exp["recommend_priority"]
        got["priority_match"] = got["priority_recommended"] == exp["recommend_priority"]
    if "recommend_activity_summary_contains" in exp:
        act = recs.get("__next_activity__", {}).get("recommended_value", {})
        got["activity_summary"] = (act.get("summary", "") if isinstance(act, dict) else str(act))
        got["summary_contains"] = exp["recommend_activity_summary_contains"].lower() in got["activity_summary"].lower()
    if "evidence_cites_purchase_intent" in exp:
        ev = (recs.get("priority", {}).get("evidence", "") or "").lower()
        got["evidence_cites_intent"] = any(
            w in ev for w in ("purchase intent", "move forward", "order form", "ready"))
    if "reassess_probability_or_note" in exp:
        got["probability_reassessed"] = "probability" in recs or "__next_activity__" in recs
    got["after_priority"] = after["priority"]
    got["after_probability"] = after["probability"]
    got["after_stage"] = after["stage"]
    return got


def main():
    with open(os.path.join(REPO, "eval", "before_snapshot.json"), encoding="utf-8") as fh:
        before = {o["name"].split(" - ")[-1]: o
                 for o in json.load(fh)["opportunities"]}

    client = OdooClient()
    client.authenticate()
    after = after_state(client)

    results = {}
    for sid, name in NAMES.items():
        log = load_log(sid)
        b = before[name]
        a = after[sid]
        b_rec = {"expected_revenue": b["expected_revenue"], "probability": b["probability"],
                 "priority": b["priority"], "date_deadline": b["date_deadline"],
                 "description": b["description"]}
        a_rec = {"expected_revenue": a["expected_revenue"], "probability": a["probability"],
                 "priority": a["priority"], "date_deadline": a["date_deadline"],
                 "description": "x" if a["description"] else None}
        gt_overdue = [x["id"] for x in b["activities"] if x["overdue"]]
        det_overdue = []
        for t in log["tool_calls"]:
            if t["tool"] == "get_overdue_activities":
                try:
                    det_overdue += [r["activity_id"]
                                    for r in json.loads(t["result_summary"])]
                except Exception:
                    pass
        results[sid] = {
            "opportunity": name,
            "before": {**b_rec, "stage": b["stage"],
                       "field_completeness_pct": field_completeness(b_rec),
                       "overdue_activity_ids": gt_overdue,
                       "activity_count": len(b["activities"])},
            "after": {**a_rec, "stage": a["stage"],
                      "field_completeness_pct": field_completeness(a_rec),
                      "activity_count": len(a["activities"]),
                      "overdue_now": [x["id"] for x in a["activities"] if x["overdue"]]},
            "agent": {"elapsed_seconds": log["elapsed"],
                       "tool_calls": len(log["tool_calls"]),
                       "auto_approved": log["auto_approved"],
                       "approved_updates": log["hitl"].get("updates", {}),
                       "approved_activities": log["hitl"].get("activities", [])},
            "overdue_detection_recall": overdue_detection_recall(det_overdue, gt_overdue),
            "checks": check_scenario(sid, log, a),
        }

    out = os.path.join(REPO, "eval", "results.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False, default=str)
    print(f"wrote {out}\n")

    print("| Scenario | Metric | Before | After |")
    print("|---|---|---|---|")
    for sid in ("S1", "S2", "S3", "S4"):
        r = results[sid]
        b, a = r["before"], r["after"]
        rows = [
            ("field_completeness_pct", b["field_completeness_pct"], a["field_completeness_pct"]),
            ("probability", b["probability"], a["probability"]),
            ("priority", b["priority"], a["priority"]),
            ("stage", b["stage"], a["stage"]),
            ("date_deadline", b["date_deadline"], a["date_deadline"]),
            ("activity_count", b["activity_count"], a["activity_count"]),
            ("overdue_detection_recall", "n/a", r["overdue_detection_recall"]),
            ("time_to_update_seconds", "manual (not timed)", r["agent"]["elapsed_seconds"]),
        ]
        for m, bv, av in rows:
            print(f"| {sid} {r['opportunity']} | {m} | {bv} | {av} |")
    print("\nScenario checks:")
    for sid in ("S1", "S2", "S3", "S4"):
        print(f"  {sid}: {json.dumps(results[sid]['checks'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
