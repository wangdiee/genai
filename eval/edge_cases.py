"""Edge-case handling skeletons for Part A.

Each edge case has a detector and a clear recovery / escalation path.
The agent must never silently invent data or perform unapproved writes.
"""

EDGE_CASES = [
    "missing_data",        # required signal absent from comms -> escalate to human
    "hallucination_guard",  # every recommendation must cite evidence found in comms
    "ambiguous_input",     # conflicting signals -> surface conflict, ask human
    "odoo_write_failure",  # write-back error -> retry once, then escalate with log
]

#: Signals the agent needs before it may recommend priority/probability changes.
REQUIRED_SIGNALS = ("budget", "decision maker", "timeline")


def check_missing_data(opportunity, comms_text, required=REQUIRED_SIGNALS):
    """Detector for the missing-data edge case.

    Returns {"status": "ok"} or {"status": "escalate", "missing": [...]}.
    Escalation means: no CRM write for the affected fields; route to a human.
    """
    haystack = (comms_text or "").lower()
    missing = [sig for sig in required if sig not in haystack]
    if missing:
        return {
            "status": "escalate",
            "missing": missing,
            "message": (
                "Insufficient evidence in communications for: "
                + ", ".join(missing)
                + ". Routed to human reviewer; no CRM write performed."
            ),
        }
    return {"status": "ok", "missing": []}


def verify_evidence_citations(recommendations, comms_text):
    """Hallucination guard: every recommendation must quote evidence that
    actually appears in the communications.

    Returns findings: [{"field", "evidence", "found_in_comms"}].
    Any finding with found_in_comms=False must block write-back for that field.
    """
    haystack = (comms_text or "").lower()
    findings = []
    for rec in recommendations:
        evidence = str(rec.get("evidence") or "")
        snippet = evidence.strip().lower()[:80]
        findings.append(
            {
                "field": rec.get("field"),
                "evidence": evidence,
                "found_in_comms": bool(snippet) and snippet in haystack,
            }
        )
    return findings


def check_ambiguous_input(recommendations):
    """Detector for conflicting signals (skeleton).

    Flags recommendations whose evidence contradicts another recommendation
    for the same opportunity, e.g. timeline says "30 days" in one doc and
    "on hold" in another. Returns the conflicting pairs for human review.
    """
    # TODO: implement conflict detection across evidence spans.
    return {"status": "ok", "conflicts": []}


def handle_odoo_write_failure(tool_name, arguments, error, logger=None):
    """Recovery path for write-back failures: log, retry once, then escalate."""
    record = {
        "tool": tool_name,
        "arguments": arguments,
        "error": str(error),
        "action": "retry_once_then_escalate",
    }
    # TODO: implement the single retry against the live Odoo instance.
    record["action"] = "escalated_to_human"
    if logger is not None:
        logger.note("write-back failed; escalated to human", **record)
    return record


def run_edge_case(name, **kwargs):
    """Entry point used by eval runs."""
    if name == "missing_data":
        return check_missing_data(
            kwargs.get("opportunity", {}), kwargs.get("comms_text", "")
        )
    if name == "hallucination_guard":
        return verify_evidence_citations(
            kwargs.get("recommendations", []), kwargs.get("comms_text", "")
        )
    if name == "ambiguous_input":
        return check_ambiguous_input(kwargs.get("recommendations", []))
    if name == "odoo_write_failure":
        return handle_odoo_write_failure(
            kwargs.get("tool_name", ""),
            kwargs.get("arguments", {}),
            kwargs.get("error", ""),
            logger=kwargs.get("logger"),
        )
    raise ValueError(f"Unknown edge case: {name!r}")
