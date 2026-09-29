"""ReAct loop for the Opportunity Intelligence Agent.

Pipeline:
  1. READ-ONLY analysis — the LLM may only call read tools
     (list/get/search). It gathers opportunity data + communications.
  2. FINAL recommendations — the LLM returns a JSON array of
     {field, current_value, recommended_value, evidence, confidence, rationale}.
  3. HUMAN-IN-THE-LOOP approval — CLI prompt per recommendation:
     accept / edit / reject. Nothing is written without explicit approval.
  4. WRITE-BACK — approved changes are applied via the write tools
     (update_opportunity_fields, create_followup_activity).

Every tool call is appended to a structured log (JSON lines on stdout, and
optionally to a file) for the eval / screenshots deliverable.

Usage:
    python -m agent.run --opportunity "Suncrest Media" [--log runs/s1.jsonl] [--dry-run]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from agent.odoo_client import OdooClient
from agent.tools import (
    TOOL_SCHEMAS,
    READ_TOOLS,
    WRITE_TOOLS,
    WRITABLE_FIELDS,
    dispatch,
)
from agent.prompts import (
    SYSTEM_PROMPT,
    RECOMMENDATION_SPEC,
    ANALYSIS_INSTRUCTIONS,
    HITL_BANNER,
)

MAX_REACT_STEPS = 8
RESULT_SNIPPET_LEN = 600

#: Moonshot chat CLI (handles auth via the stored credential; the raw API
#: key is never exposed to this process).
CHAT_CLI = os.path.expanduser("~/workspace/skills/moonshot/bin/chat.py")
LLM_TRIES = 4


def utcnow():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------ LLM (Moonshot)
def call_llm(messages, tools=None):
    """Call Moonshot chat completions via the skill CLI (surrogate auth).

    Payload is OpenAI-compatible and supports function calling. Retries with
    backoff on HTTP 429 (rate limit) and transient transport errors.
    """
    payload = {
        "model": os.environ.get("MOONSHOT_MODEL", "kimi-k2.6"),
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    # kimi-k2.6 only accepts temperature=1; omit it (server default).
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = None
    for attempt in range(LLM_TRIES):
        try:
            proc = subprocess.run(
                [sys.executable, CHAT_CLI],
                input=body,
                capture_output=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            last = exc
            time.sleep(10 * (attempt + 1))
            continue
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            err = out or proc.stderr.decode("utf-8", "replace")
            last = RuntimeError(f"moonshot CLI failed: {err[:200]}")
        else:
            try:
                data = json.loads(out)
            except json.JSONDecodeError as exc:
                last = exc
                time.sleep(5)
                continue
            if isinstance(data, dict) and data.get("ok") is False:
                last = RuntimeError(f"moonshot error: {data.get('error')}")
            else:
                try:
                    return data["choices"][0]["message"]
                except (KeyError, IndexError, TypeError) as exc:
                    last = RuntimeError(f"unexpected moonshot reply: {out[:200]}")
        if "429" in str(last) and attempt < LLM_TRIES - 1:
            time.sleep(30 * (attempt + 1))  # rate-limit backoff (hard stop per burst)
            continue
        if attempt < LLM_TRIES - 1 and proc.returncode != 0:
            time.sleep(5 * (attempt + 1))
            continue
        break
    raise last if isinstance(last, Exception) else RuntimeError("moonshot call failed")


# ------------------------------------------------------------ structured log
class ToolLogger:
    """JSON-lines log of every tool call (also mirrored to stdout)."""

    def __init__(self, path=None):
        self.path = path
        self.entries = []
        self._fh = open(path, "w", encoding="utf-8") if path else None

    def _emit(self, entry):
        entry["ts"] = utcnow()
        self.entries.append(entry)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        print(line, flush=True)
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()

    def tool(self, name, arguments, result_summary, phase):
        self._emit(
            {
                "kind": "tool_call",
                "phase": phase,
                "tool": name,
                "arguments": arguments,
                "result_summary": result_summary,
            }
        )

    def note(self, message, **extra):
        entry = {"kind": "note", "message": message}
        entry.update(extra)
        self._emit(entry)

    def close(self):
        if self._fh:
            self._fh.close()


def _summarize(result):
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > RESULT_SNIPPET_LEN:
        return text[:RESULT_SNIPPET_LEN] + "…[truncated]"
    return text


# ------------------------------------------------------------ phase 1: ReAct
def react_analyze(client, logger, opportunity_name, comms_dir):
    """Read-only ReAct loop. Returns the message history for the final step."""
    read_schemas = [t for t in TOOL_SCHEMAS if t["function"]["name"] in READ_TOOLS]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": ANALYSIS_INSTRUCTIONS
            + f"\nOpportunity under review: {opportunity_name}",
        },
    ]
    for _ in range(MAX_REACT_STEPS):
        msg = call_llm(messages, tools=read_schemas)
        tool_calls = msg.get("tool_calls") or []
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls or None,
            }
        )
        if not tool_calls:
            break  # LLM is done gathering evidence
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name not in READ_TOOLS:
                result = {"error": f"Tool {name!r} is not allowed during analysis."}
            else:
                try:
                    result = dispatch(
                        client, name, args, comms_dir=comms_dir, allow_write=False
                    )
                except Exception as exc:  # noqa: BLE001 — surface to the LLM
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            logger.tool(name, args, _summarize(result), phase="analyze")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    else:
        logger.note("max_react_steps_reached", max_steps=MAX_REACT_STEPS)
    return messages


def extract_recommendations(messages):
    """Ask the LLM for the final recommendations JSON (no tools)."""
    messages = messages + [
        {
            "role": "user",
            "content": (
                "Based on the evidence gathered above, output your final "
                "recommendations now.\n" + RECOMMENDATION_SPEC
            ),
        }
    ]
    msg = call_llm(messages)
    text = (msg.get("content") or "").strip()
    # Tolerate ```json fences.
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


# ------------------------------------------------------------ phase 3: HITL
def _coerce(field, raw):
    if field in ("expected_revenue", "probability"):
        try:
            return float(raw)
        except ValueError:
            return raw
    if field == "priority":
        try:
            return str(int(raw))
        except ValueError:
            return raw
    return raw


def hitl_approve(recommendations, auto_approve=False):
    """Approval loop. Returns (approved_updates, approved_activities).

    With ``auto_approve=True`` every recommendation is accepted without
    prompting — used only for unattended batch eval runs; the decision is
    recorded in the log as auto-approved.
    """
    print(HITL_BANNER)
    if auto_approve:
        print("AUTO-APPROVE mode: accepting all recommendations (batch eval).")
    approved_updates = {}
    approved_activities = []
    for rec in recommendations:
        field = rec.get("field")
        current = rec.get("current_value")
        proposed = rec.get("recommended_value")
        print(f"Field        : {field}")
        print(f"  current      : {current}")
        print(f"  recommended  : {proposed}")
        print(f"  evidence     : {rec.get('evidence')}")
        print(f"  confidence   : {rec.get('confidence')}")
        print(f"  rationale    : {rec.get('rationale')}")
        if auto_approve:
            choice = "a"
            print("  decision     : auto-accept")
        else:
            while True:
                choice = input("  decision [a]ccept / [e]dit / [r]eject: ").strip().lower()
                if choice in ("a", "e", "r"):
                    break
                print("  please type a, e or r.")
        if choice == "r":
            continue
        value = proposed
        if choice == "e":
            raw = input(f"  new value for {field}: ").strip()
            value = _coerce(field, raw)
        if field == "__next_activity__":
            if not isinstance(value, dict):
                value = {"summary": str(value)}
            approved_activities.append(value)
        else:
            if field not in WRITABLE_FIELDS:
                print(f"  !! {field!r} is not writable; skipping.")
                continue
            approved_updates[field] = value
    return approved_updates, approved_activities


# ------------------------------------------------------------ phase 4: write
def apply_writes(client, logger, opp_id, updates, activities, dry_run=False):
    if dry_run:
        logger.note("dry_run: skipping write-back", updates=updates, activities=activities)
        return
    if updates:
        args = {"opp_id": opp_id, "fields": updates}
        try:
            result = dispatch(client, "update_opportunity_fields", args, allow_write=True)
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.tool("update_opportunity_fields", args, _summarize(result), phase="write")
    for act in activities:
        args = {"opp_id": opp_id, **act}
        try:
            result = dispatch(client, "create_followup_activity", args, allow_write=True)
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"{type(exc).__name__}: {exc}"}
        logger.tool("create_followup_activity", args, _summarize(result), phase="write")


# ------------------------------------------------------------ main
def resolve_opportunity(client, ref):
    if ref.isdigit():
        opp = client.get_opportunity(int(ref))
    else:
        opp = client.find_opportunity_by_name(ref)
    if not opp:
        raise SystemExit(f"Opportunity {ref!r} not found in Odoo.")
    return opp


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Opportunity Intelligence Agent (ReAct + human-in-the-loop)"
    )
    parser.add_argument("--opportunity", required=True, help="Opportunity name or numeric id")
    parser.add_argument("--comms-dir", default="seed/comms", help="Synthetic communications dir")
    parser.add_argument("--log", default=None, help="Write structured JSONL log to this file")
    parser.add_argument("--dry-run", action="store_true", help="Analyze + approve, no Odoo writes")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Accept all recommendations without prompting (batch eval only; logged)",
    )
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    logger = ToolLogger(args.log)
    t0 = time.perf_counter()
    try:
        client = OdooClient()
        opp = resolve_opportunity(client, args.opportunity)
        logger.note("opportunity_resolved", id=opp["id"], name=opp["name"])

        messages = react_analyze(client, logger, opp["name"], args.comms_dir)
        recommendations = extract_recommendations(messages)
        logger.note("recommendations_drafted", count=len(recommendations))
        logger.note("recommendations", items=recommendations)

        updates, activities = hitl_approve(recommendations, auto_approve=args.auto_approve)
        logger.note(
            "hitl_decision",
            auto_approved=args.auto_approve,
            approved_updates=updates,
            approved_activities=activities,
        )

        apply_writes(client, logger, opp["id"], updates, activities, dry_run=args.dry_run)
    finally:
        logger.note("run_finished", elapsed_seconds=round(time.perf_counter() - t0, 1))
        logger.close()


if __name__ == "__main__":
    main()
