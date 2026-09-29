# Prompt & Iteration Log — Opportunity Intelligence Agent

Chronological record of every prompt / harness change and the evidence
that motivated it. All runs against live Odoo (`debbywangcrm.odoo.com`).

## v1 — Initial build (2026-09-28)

- `agent/prompts.py::SYSTEM_PROMPT`: role = CRM opportunity analyst;
  HW1 §5.4 governance (show current vs proposed, cite evidence per field,
  accept/edit/reject per field, flag low-confidence + conflicts, never
  invent missing data, no unapproved external sends/pricing commitments).
- `RECOMMENDATION_SPEC`: strict JSON array so `run.py` parses
  deterministically (fields: expected_revenue, probability, priority,
  stage_id, date_deadline, description, __next_activity__).
- ReAct analysis, max 12 steps, read-only tools.

## v2 — After S1 dry-run (2026-09-29 05:03 UTC)

Dry-run produced 6 recommendations; two defects found on review:

1. **Past activity deadline**: agent proposed `__next_activity__`
   with `date_deadline: 2026-09-24` — 5 days in the past, instantly overdue.
   → Added to spec: *"The activity date_deadline must be today or a future
   date — never in the past."*
2. **Priority inflation**: agent raised S1 `priority` 2 → 3 (Very High)
   with no customer-urgency evidence. → Added `PRIORITY CALIBRATION`:
   0=Low, 1=Medium, 2=High, 3=Very High; reserve 3 for explicit urgency.

Result in live S1 run: priority stayed at 2, activity deadline 2026-10-15.
Both fixes verified in `eval/runs/s1.jsonl`.

## v3 — Harness fixes during live batch (2026-09-29 05:05–05:30 UTC)

Not prompt changes, but agent-behavior fixes found by live runs:

1. **Stage name → id**: LLM outputs `"Qualified"`; Odoo needs the numeric
   `stage_id`. `update_opportunity_fields` now resolves names via
   `crm.stage` search (ilike). Verified: S1 New→Qualified, S3
   Qualified→Proposition.
2. **`MAX_REACT_STEPS` 12 → 8**: analysis consistently finished in ≤8
   steps; tighter bound cuts runaway cost.
3. **`--auto-approve`**: batch eval bypass for the HITL CLI; every
   auto-decision logged with `auto_approved:true`. Interactive per-field
   approval remains the default.
4. **Recommendations logging**: `logger.note("recommendations", …)` added
   so the evidence chain is in the JSONL (took effect after the batch).

## v4 — Write-path incident fixes (2026-09-29 05:30–06:00 UTC)

Live batch write phase surfaced 4 defects (all fixed, verified, see
`docs/architecture.md` §7):

1. Null recommendations (correct "missing — escalate") crashed XML-RPC
   marshaling → nulls now filtered at the tool boundary (never written).
2. Odoo 19 `mail.activity` create needs `res_model_id` (ir.model id),
   not legacy `res_model` → `_res_model_id()` resolver + cache.
3. `mail.activity.type` name is `To-Do`, not `To Do` → tolerant
   case/space/hyphen matching in `get_activity_type_id`.
4. Transport response-loss + blind retries → 10 duplicate activities.
   → creates are single-attempt at transport level;
   `create_followup_activity` is now idempotent (check-before-create,
   adopt-on-response-loss with self-healing cleanup). Verified live:
   duplicate call → same id, `deduped:true`.

## Final prompt (essence)

> You are an Opportunity Intelligence Agent assisting a sales rep… For each
> field give current value, recommendation, evidence (file + quote),
> confidence. Never invent missing data — return null and escalate.
> Activity deadlines: today or future, never past. Priority 3 only on
> explicit customer urgency. One JSON array, no prose.

Full text: `agent/prompts.py`.
