"""Eval scenarios derived from the HW1 §3.7 pain-point indicators.

Each scenario maps to one mock opportunity and states what the agent is
expected to detect / recommend. Used by eval/metrics.py for the
before/after comparison required by Part A.
"""

SCENARIOS = [
    {
        "id": "S1",
        "opportunity": "Suncrest Media",
        "description": (
            "High-value opportunity ($76,000) whose follow-up activity is overdue."
        ),
        "comms": ["suncrest_email.txt"],
        "expected": {
            "detect_overdue_activity": True,
            "recommend_new_activity": True,
            "expected_priority": "2",  # High
        },
    },
    {
        "id": "S2",
        "opportunity": "Vertex Security",
        "description": (
            "High-priority opportunity with no discovery meeting scheduled "
            "for an extended period."
        ),
        "comms": ["vertex_meeting_notes.txt"],
        "expected": {
            "recommend_activity_summary_contains": "discovery",
            "expected_priority": "2",  # High
        },
    },
    {
        "id": "S3",
        "opportunity": "Greenline Energy",
        "description": (
            "Marked Medium priority although communications indicate strong "
            "purchase intent."
        ),
        "comms": ["greenline_call_notes.txt"],
        "expected": {
            "recommend_priority": "2",  # upgrade Medium -> High
            "evidence_cites_purchase_intent": True,
        },
    },
    {
        "id": "S4",
        "opportunity": "FreshFork Foods",
        "description": (
            "Customer purchase intent has changed but no follow-up activity "
            "is scheduled."
        ),
        "comms": ["freshfork_email.txt"],
        "expected": {
            "detect_missing_activity": True,
            "recommend_new_activity": True,
            "reassess_probability_or_note": True,
        },
    },
]


def get_scenario(scenario_id):
    for sc in SCENARIOS:
        if sc["id"] == scenario_id:
            return sc
    raise KeyError(f"Unknown scenario: {scenario_id}")
