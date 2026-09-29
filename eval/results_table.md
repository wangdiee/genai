# Part A — Side-by-side Metrics: Manual baseline (before) vs GenAI Agent (after)

Odoo: `debbywangcrm.odoo.com` (SaaS 19.4+e) · LLM: `kimi-k2.6` · Runs: 2026-09-28/29 · Full structured logs: `eval/runs/*.jsonl`

| Scenario | Metric | Before (manual) | After (agent) |
|---|---|---|---|
| S1 Suncrest Media | Field completeness % | 80 | 100 **← changed** |
| S1 Suncrest Media | Expected revenue ($) | 76000 | 76000 |
| S1 Suncrest Media | Probability (%) | 20 | 50 **← changed** |
| S1 Suncrest Media | Priority (0-3 stars) | 2 | 2 |
| S1 Suncrest Media | Stage | New | Qualified **← changed** |
| S1 Suncrest Media | Close date | — | 2026-10-15 **← changed** |
| S1 Suncrest Media | Activity count | 1 | 2 **← changed** |
| S1 Suncrest Media | Overdue-detection recall | n/a | 1 |
| S1 Suncrest Media | Agent analysis time | not timed (manual) | 237.9 s |
| S2 Vertex Security | Field completeness % | 80 | 100 **← changed** |
| S2 Vertex Security | Expected revenue ($) | 39000 | 55000 **← changed** |
| S2 Vertex Security | Probability (%) | 15 | 15 |
| S2 Vertex Security | Priority (0-3 stars) | 2 | 2 |
| S2 Vertex Security | Stage | New | New |
| S2 Vertex Security | Close date | — | 2026-09-30 **← changed** |
| S2 Vertex Security | Activity count | 1 | 2 **← changed** |
| S2 Vertex Security | Overdue-detection recall | n/a | 1 |
| S2 Vertex Security | Agent analysis time | not timed (manual) | 427.3 s |
| S3 Greenline Energy | Field completeness % | 80 | 80 |
| S3 Greenline Energy | Expected revenue ($) | 34000 | 34000 |
| S3 Greenline Energy | Probability (%) | 70 | 80 **← changed** |
| S3 Greenline Energy | Priority (0-3 stars) | 1 | 2 **← changed** |
| S3 Greenline Energy | Stage | Qualified | Proposition **← changed** |
| S3 Greenline Energy | Close date | — | — |
| S3 Greenline Energy | Activity count | 1 | 2 **← changed** |
| S3 Greenline Energy | Overdue-detection recall | n/a | 1 |
| S3 Greenline Energy | Agent analysis time | not timed (manual) | 195.2 s |
| S4 FreshFork Foods | Field completeness % | 80 | 80 |
| S4 FreshFork Foods | Expected revenue ($) | 24000 | 24000 |
| S4 FreshFork Foods | Probability (%) | 60 | 60 |
| S4 FreshFork Foods | Priority (0-3 stars) | 1 | 1 |
| S4 FreshFork Foods | Stage | New | New |
| S4 FreshFork Foods | Close date | — | — |
| S4 FreshFork Foods | Activity count | 0 | 1 **← changed** |
| S4 FreshFork Foods | Overdue-detection recall | n/a | — |
| S4 FreshFork Foods | Agent analysis time | not timed (manual) | 638 s |

## Scenario checks

### S1 Suncrest Media

- detect_overdue_activity: `True`
- recommend_new_activity: `True`
- priority_recommended: `2`
- priority_expected: `2`
- priority_match: `True`
- after_priority: `2`
- after_probability: `50.0`
- after_stage: `Qualified`

### S2 Vertex Security

- priority_recommended: `None`
- priority_expected: `2`
- priority_match: `False`
- activity_summary: `Re-engage CISO and book discovery meeting with infrastructure lead`
- summary_contains: `True`
- after_priority: `2`
- after_probability: `15.0`
- after_stage: `New`

### S3 Greenline Energy

- priority_recommended: `2`
- priority_expected: `2`
- priority_match: `True`
- evidence_cites_intent: `False`
- after_priority: `2`
- after_probability: `80.0`
- after_stage: `Proposition`

### S4 FreshFork Foods

- recommend_new_activity: `True`
- probability_reassessed: `True`
- after_priority: `1`
- after_probability: `60.0`
- after_stage: `New`

