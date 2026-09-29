"""Tool definitions (OpenAI function-calling format) + dispatcher.

Read tools are always available. Write tools (``update_opportunity_fields``,
``create_followup_activity``) only execute when the caller passes
``allow_write=True`` — the ReAct loop in ``agent/run.py`` enables this
exclusively *after* human-in-the-loop approval.
"""

import glob
import os
from datetime import date

# ---------------------------------------------------------------------------
# Tool schemas in OpenAI function-calling format
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_opportunities",
            "description": (
                "List sales opportunities in Odoo CRM. Optionally filter by "
                "stage name or minimum expected revenue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "description": "Stage name filter, e.g. 'New', 'Qualified', 'Proposition', 'Won'.",
                    },
                    "min_revenue": {
                        "type": "number",
                        "description": "Minimum expected revenue.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max records to return.",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_opportunity_details",
            "description": (
                "Get full details of one opportunity, including its open "
                "follow-up activities. Identify it by numeric id or by name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opp_id": {"type": "integer", "description": "Odoo crm.lead id."},
                    "name": {"type": "string", "description": "Opportunity name (used if opp_id is absent)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_overdue_activities",
            "description": (
                "Find follow-up activities whose deadline has passed. "
                "Scope to one opportunity with opp_id, or scan all "
                "opportunities when omitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opp_id": {"type": "integer", "description": "Odoo crm.lead id (optional)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_opportunity_fields",
            "description": (
                "WRITE TOOL — update whitelisted fields on an opportunity "
                "(expected_revenue, probability, priority, stage_id, "
                "date_deadline, description). Requires prior human approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opp_id": {"type": "integer", "description": "Odoo crm.lead id."},
                    "fields": {
                        "type": "object",
                        "description": "Field name -> new value. Only whitelisted fields are accepted.",
                    },
                },
                "required": ["opp_id", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_followup_activity",
            "description": (
                "WRITE TOOL — schedule a follow-up activity on an opportunity. "
                "Requires prior human approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opp_id": {"type": "integer", "description": "Odoo crm.lead id."},
                    "activity_type": {
                        "type": "string",
                        "description": "Activity type name, e.g. 'To Do', 'Meeting', 'Call', 'Email'.",
                        "default": "To Do",
                    },
                    "summary": {"type": "string", "description": "Short activity title."},
                    "note": {"type": "string", "description": "Activity details / talking points."},
                    "date_deadline": {
                        "type": "string",
                        "description": "Deadline as YYYY-MM-DD.",
                    },
                },
                "required": ["opp_id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_communications",
            "description": (
                "Search the local synthetic customer communications "
                "(emails, meeting/call notes under seed/comms/) for a keyword. "
                "Returns matching snippets with their source file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword or phrase to search for."},
                },
                "required": ["query"],
            },
        },
    },
]

READ_TOOLS = {
    "list_opportunities",
    "get_opportunity_details",
    "get_overdue_activities",
    "search_communications",
}
WRITE_TOOLS = {"update_opportunity_fields", "create_followup_activity"}

#: Fields the agent is allowed to write back to crm.lead. Enforced in
#: update_opportunity_fields() as well as in the HITL step of agent/run.py.
WRITABLE_FIELDS = {
    "expected_revenue",
    "probability",
    "priority",
    "stage_id",
    "date_deadline",
    "description",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stage_name(opp):
    stage = opp.get("stage_id")
    if isinstance(stage, (list, tuple)) and len(stage) == 2:
        return stage[1]
    return None


def _summarize_opp(opp):
    return {
        "id": opp["id"],
        "name": opp["name"],
        "expected_revenue": opp.get("expected_revenue"),
        "probability": opp.get("probability"),
        "priority": opp.get("priority"),
        "stage": _stage_name(opp),
        "date_deadline": opp.get("date_deadline"),
    }


def _is_overdue(activity):
    deadline = activity.get("date_deadline")
    return bool(deadline) and deadline < date.today().isoformat()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def list_opportunities(client, stage=None, min_revenue=None, limit=20):
    domain = []
    if min_revenue is not None:
        domain.append(["expected_revenue", ">=", min_revenue])
    opps = client.list_opportunities(domain=domain, limit=limit)
    if stage:
        opps = [
            o for o in opps
            if _stage_name(o) and stage.lower() in _stage_name(o).lower()
        ]
    return [_summarize_opp(o) for o in opps]


def get_opportunity_details(client, opp_id=None, name=None):
    if opp_id is not None:
        opp = client.get_opportunity(opp_id)
    elif name:
        opp = client.find_opportunity_by_name(name)
    else:
        return {"error": "Provide opp_id or name."}
    if not opp:
        return {"error": "Opportunity not found."}
    details = _summarize_opp(opp)
    details["description"] = opp.get("description")
    details["partner"] = opp.get("partner_id")
    details["open_activities"] = client.list_activities(opp["id"])
    return details


def get_overdue_activities(client, opp_id=None):
    if opp_id is not None:
        opps = [client.get_opportunity(opp_id)]
        opps = [o for o in opps if o]
    else:
        opps = client.list_opportunities(limit=100)
    overdue = []
    for opp in opps:
        for act in client.list_activities(opp["id"]):
            if _is_overdue(act):
                overdue.append(
                    {
                        "opportunity_id": opp["id"],
                        "opportunity": opp["name"],
                        "activity_id": act["id"],
                        "summary": act.get("summary"),
                        "date_deadline": act.get("date_deadline"),
                    }
                )
    return overdue


def update_opportunity_fields(client, opp_id, fields):
    rejected = sorted(set(fields) - WRITABLE_FIELDS)
    if rejected:
        return {"error": f"Fields not writable: {rejected}. Allowed: {sorted(WRITABLE_FIELDS)}"}
    # A null recommended value means "missing data — escalate to human":
    # never write nulls back to the CRM, just skip those fields.
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return {"ok": False, "skipped": "all recommended values were null (missing data); nothing written"}
    fields = dict(fields)
    # The LLM reasons in stage names ("Qualified"); Odoo needs the numeric id.
    stage = fields.get("stage_id")
    if isinstance(stage, str) and not stage.isdigit():
        ids = client.search("crm.stage", [["name", "ilike", stage]], limit=1)
        if not ids:
            return {"error": f"Stage {stage!r} not found in crm.stage."}
        fields["stage_id"] = ids[0]
    ok = client.update_opportunity(opp_id, fields)
    return {"ok": bool(ok), "opp_id": opp_id, "updated_fields": sorted(fields)}


def create_followup_activity(
    client, opp_id, summary, activity_type="To Do", note="", date_deadline=None
):
    """Schedule a follow-up activity. Idempotent on identical summary.

    The sandbox transport intermittently drops responses *after* the server
    committed a create; retrying blindly produced duplicates in live runs.
    So: check for an identical follow-up first, create once, and if the
    single attempt's response is lost, re-check and adopt the landed record
    (cleaning up any extra copies) instead of creating another.
    """
    def _matching():
        return [a for a in client.list_activities(opp_id)
                if a.get("summary") == summary]

    prior = _matching()
    if prior:
        return {"ok": True, "activity_id": prior[0]["id"], "opp_id": opp_id,
                "deduped": True}
    try:
        act_id = client.create_activity(
            opp_id,
            activity_type=activity_type,
            summary=summary,
            note=note,
            date_deadline=date_deadline,
        )
    except Exception as exc:  # noqa: BLE001 - response may have been lost
        landed = _matching()
        if not landed:
            raise
        act_id = landed[0]["id"]
        extras = [a["id"] for a in landed[1:]]
        if extras:  # self-heal: drop copies our own retry storm made
            client.execute("mail.activity", "unlink", [extras])
        return {"ok": True, "activity_id": act_id, "opp_id": opp_id,
                "adopted_after_retry": True,
                "cleaned_duplicate_ids": extras,
                "note": f"create response lost ({type(exc).__name__}); adopted landed record"}
    return {"ok": True, "activity_id": act_id, "opp_id": opp_id}


def search_communications(query, comms_dir="seed/comms"):
    """Keyword search over local synthetic communications (stub data source)."""
    q = query.lower()
    hits = []
    for path in sorted(glob.glob(os.path.join(comms_dir, "*.txt"))):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for i, line in enumerate(lines):
            if q in line.lower():
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                hits.append(
                    {
                        "source": os.path.basename(path),
                        "snippet": " ".join(l.strip() for l in lines[start:end] if l.strip()),
                    }
                )
    return {"query": query, "hits": hits[:20]}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch(client, name, arguments, comms_dir="seed/comms", allow_write=False):
    """Execute a tool call by name.

    Write tools raise PermissionError unless ``allow_write=True`` (granted by
    agent/run.py only after human-in-the-loop approval).
    """
    arguments = arguments or {}
    if name in WRITE_TOOLS and not allow_write:
        raise PermissionError(
            f"Tool {name!r} writes to Odoo and requires human approval first."
        )
    if name == "list_opportunities":
        return list_opportunities(client, **arguments)
    if name == "get_opportunity_details":
        return get_opportunity_details(client, **arguments)
    if name == "get_overdue_activities":
        return get_overdue_activities(client, **arguments)
    if name == "update_opportunity_fields":
        return update_opportunity_fields(client, **arguments)
    if name == "create_followup_activity":
        return create_followup_activity(client, **arguments)
    if name == "search_communications":
        return search_communications(arguments.get("query", ""), comms_dir=comms_dir)
    raise ValueError(f"Unknown tool: {name!r}")
