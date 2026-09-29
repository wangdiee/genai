# Architecture Note — Opportunity Intelligence Agent

> Part A deliverable §3 (short architecture note). Numbers below are measured
> from live runs against Odoo on 2026-09-28/29.

## 1. Overview

A GenAI agent that assists (not replaces) sales reps in the Odoo CRM
opportunity assessment process from HW1. It converts unstructured customer
communications into structured, evidence-cited CRM update recommendations,
applies them to the **live Odoo system** only after per-field human approval.

## 2. Runtime environment (measured)

- **Odoo**: `debbywangcrm.odoo.com`, SaaS **19.4+e**, 30 `crm.lead`
  opportunities (matches HW1 dataset).
- **LLM**: `kimi-k2.6` via the Moonshot skill CLI (`temperature` fixed at 1
  by the provider — the request omits it).
- **Transport**: sandbox egress goes through an HTTP proxy, so
  `xmlrpc.client.ServerProxy` fails with `SSL: WRONG_VERSION_NUMBER`.
  `agent/odoo_client.py` therefore implements XML-RPC manually over
  `urllib` (proxy-aware) with **8-try exponential backoff** — the hosted
  endpoint intermittently resets connections ("Remote end closed
  connection", roughly 1 in 3–4 calls during the test window).
- **ReAct loop**: max **8 steps** (read-only tools in the analysis phase),
  then one structured recommendation call.

## 3. Data flow

```
synthetic comms (seed/comms/*.txt) ─┐
                                     ├─► ReAct analysis (read-only tools)
live Odoo: crm.lead ────────────────┘            │
                                                 ▼
                                   recommendations JSON
                                   {field, current, proposed, evidence, confidence}
                                                 │
                                                 ▼
                                   human-in-the-loop CLI (accept/edit/reject)
                                   (batch eval used --auto-approve; logged)
                                                 │
                                                 ▼
                                   write-back tools → live Odoo
                                   (crm.lead write, mail.activity create)
                                                 │
                                                 ▼
                                   structured JSONL run log → eval/metrics.py
```

## 4. Tools (function-calling)

| Tool                        | Type  | Effect                                              |
|-----------------------------|-------|-----------------------------------------------------|
| `list_opportunities`        | read  | `crm.lead` search_read (opportunities)              |
| `get_opportunity_details`   | read  | full lead record + open activities                  |
| `get_overdue_activities`    | read  | activities with `date_deadline` < today             |
| `search_communications`     | read  | keyword search over local synthetic `.txt` comms    |
| `update_opportunity_fields` | write | `crm.lead` write (whitelisted fields only, post-HITL)|
| `create_followup_activity`  | write | `mail.activity` create (post-HITL, idempotent)      |

Write tools are **disabled** during analysis and enabled only after HITL
approval (`allow_write=True` in the dispatcher).

Odoo 19 API notes (found empirically):

- `mail.activity` create requires **`res_model_id`** (id from `ir.model`),
  not the legacy `res_model` char — the old form fails with
  *"Activities have to be linked to records with a not null res_id"*.
- `mail.activity.type` names are `To-Do` (hyphen), `Email`, `Call`,
  `Meeting`, `Document`; type resolution is tolerant (case/space/hyphen).
- A `null` recommended value means *"missing data — escalate"* and is
  never written back; nulls are filtered before the `write` call.

## 5. Prompts

- `agent/prompts.py::SYSTEM_PROMPT` — role definition + HW1 §5.4 governance:
  show current value beside recommendation; cite evidence; accept/edit/reject
  per field; flag low-confidence and conflicts; never invent missing data;
  no unapproved external sends or pricing commitments.
- Two calibration lines were added after the first dry-run:
  (1) new activity deadlines must be today or in the future (the agent had
  proposed a past date); (2) `priority=3` (Very High) is reserved for
  explicit customer urgency — the dry-run had escalated S1 to 3 without
  evidence, and the live run correctly kept it at 2.
- Analysis phase uses ReAct-style tool-calling (max 8 steps, read tools only).
- Final recommendations are requested as a strict JSON array
  (`RECOMMENDATION_SPEC`) so the HITL CLI can parse them deterministically.

## 6. Human-in-the-loop & governance

Per-field CLI approval in `agent/run.py::hitl_approve`. Rejected fields are
dropped; edited fields use the human's value. The writable field whitelist
(`WRITABLE_FIELDS` in `agent/tools.py`) is enforced again at write time.
`--dry-run` runs analysis + approval with zero Odoo writes. Batch eval runs
used `--auto-approve` (explicitly logged as `auto_approved:true`); the
default interactive mode remains per-field approval.

## 7. Eval results (measured)

| Scenario | Field completeness | Probability | Stage | Overdue recall | Time (analyze) |
|---|---|---|---|---|---|
| S1 Suncrest Media | 80% → 100% | 20 → 50 | New → Qualified | 1.0 | 237.9 s |
| S2 Vertex Security | 80% → 100% | 15 → 15 | New → New | 1.0 | 427.3 s |
| S3 Greenline Energy | 80% → 80% | 70 → 80 | Qualified → Proposition | 1.0 | 195.2 s |
| S4 FreshFork Foods | 80% → 80% | 60 → 60 (escalated) | New → New | n/a (no activities) | 638.0 s¹ |

¹ Inflated by transport-retry backoff during the write phase.

Follow-ups created: 4 (one per scenario, all in Odoo). Full before/after
table: `eval/results.json`.

### Qualitative rubric (1–5)

| Dimension | Score | Basis |
|---|---|---|
| Evidence grounding (no hallucination) | 5 | every value cites a comms file + quote; missing data → `null` + escalate |
| Recommendation quality | 4 | stage/probability/priority moves match scenario intent; S4 correctly refused to invent revenue/probability/deadline |
| Overdue detection | 5 | recall 1.0 on S1–S3; S4 correctly reported n/a |
| Write safety | 4 | whitelist + HITL enforced; nulls never written; see incident below |
| Robustness | 3 | transport flakiness handled, but see incident below |

### Write-path incident (found live, fixed, verified)

1. **Null marshaling**: S3/S4 recommendations contained `null` (correct
   "missing — escalate" behavior), but the writer passed them to XML-RPC →
   `TypeError`. Fix: nulls filtered at the tool boundary.
2. **Odoo 19 activity linking**: `res_model` rejected (§4). Fix: `res_model_id`.
3. **Type-name mismatch**: agent said "To Do", Odoo has "To-Do". Fix: tolerant match.
4. **Retry storm → duplicates**: a "connection closed" response-loss retry
   loop on a non-idempotent create produced 10 duplicate activities across
   S1/S2/S3. Duplicates were removed (verified per-record before unlink).
   Hardening: creates now use a single transport attempt; the tool does
   check-before-create and, on response loss, re-checks and *adopts* the
   landed record (self-healing any extra copies). Idempotency verified live:
   two identical calls → same id, `deduped:true`, zero duplicates.

## 8. Eval design

- Scenarios: `eval/scenarios.py` — the 4 HW1 §3.7 pain-point cases.
- Metrics: `eval/metrics.py` + `eval/collect_results.py` — time-to-update,
  field completeness %, scoring consistency, overdue-detection recall,
  qualitative rubric (1–5).
- Edge cases: `eval/edge_cases.py` — missing data → escalate; hallucination
  guard via evidence-citation check; ambiguous input; write-failure recovery.
  Live edge test (Harbor Foods, zero communications): agent returned
  evidence `"missing"` on every field and recommended escalation — no
  invented values (`eval/runs/harbor_dryrun.jsonl`).

## 9. Limitations

- Timings include LLM latency + transport backoff; not a pure "agent speed".
- `date_deadline` on `crm.lead` appears unused by the seeded data
  (False/empty) — the agent sets it from comms-derived next steps.
- Duplicate-risk under response loss is mitigated at the tool layer, not
  eliminated at the protocol layer (no server-side idempotency keys).
