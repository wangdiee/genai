# GenAI Opportunity Intelligence Agent (MSIS-613-01, Part A)

GenAI-powered assistant for the **sales opportunity information capture and
assessment** process in Odoo CRM (the HW1 process). The agent:

1. Reads opportunity records from the **live Odoo system** via XML-RPC and
   scans synthetic customer communications (emails, meeting/call notes).
2. Produces structured, explainable recommendations — priority, probability,
   stage, expected revenue, close date, next follow-up activity — each paired
   with the current CRM value and an evidence citation.
3. Writes back to Odoo **only after human-in-the-loop approval** of every
   field (accept / edit / reject per recommendation).

Course: MSIS-613-01 · Student: Debby Wang · HW1 process: Odoo CRM opportunity
assessment.

## Repository layout

```
genai-crm-agent/
├── README.md               # this file
├── requirements.txt
├── .env.example            # copy to .env and fill in (never commit .env)
├── agent/
│   ├── odoo_client.py      # Odoo XML-RPC client (auth, search_read, write, activities)
│   ├── tools.py            # OpenAI function-calling tool schemas + dispatcher
│   ├── prompts.py          # system prompt with HW1 governance rules
│   └── run.py              # ReAct loop: analyze → HITL approval → write-back
├── seed/
│   ├── seed_data.py        # seeds the 4 HW1 mock opportunities + synthetic comms
│   └── comms/              # synthetic customer communications (local .txt files)
├── eval/
│   ├── scenarios.py        # the 4 HW1 §3.7 scenarios as eval cases
│   ├── metrics.py          # before/after metrics collection
│   ├── collect_results.py  # builds eval/results.json + results_table.md from run logs
│   ├── results.json        # measured before/after metrics (machine-readable)
│   ├── results_table.md    # side-by-side metrics table (human-readable)
│   ├── edge_cases.py       # edge-case detectors + recovery/escalation paths
│   └── runs/               # structured JSONL logs of every agent run
└── docs/
    ├── architecture.md     # data flow, tools, prompts, data models + measured results
    └── prompt_iteration_log.md  # prompt/harness changes and the evidence behind them
```

## Prerequisites

- Python 3.10+
- Access to the course Odoo instance (URL, database name, user + password or API key)
- A Moonshot (Kimi) API key — the agent calls its OpenAI-compatible
  `POST /v1/chat/completions` endpoint with tool-calling

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your values
```

Environment variables (all required unless noted):

| Variable            | Description                                              |
|---------------------|----------------------------------------------------------|
| `ODOO_URL`          | e.g. `https://debbywangcrm.odoo.com`                     |
| `ODOO_DB`           | Odoo database name                                       |
| `ODOO_USER`         | Odoo login (email)                                       |
| `ODOO_PASSWORD`     | Odoo password (or use `ODOO_API_KEY`)                    |
| `ODOO_API_KEY`      | Odoo API key — preferred over password (optional)        |
| `MOONSHOT_API_KEY`  | Moonshot / Kimi API key                                  |
| `MOONSHOT_BASE_URL` | default `https://api.moonshot.ai/v1`                     |
| `MOONSHOT_MODEL`    | default `kimi-k2.6` (temperature fixed at 1 by the provider) |

## Running

```bash
# 1. Seed the 4 HW1 mock opportunities + synthetic communications
python seed/seed_data.py

# 2. Run the agent on one opportunity (HITL approval in the terminal)
python -m agent.run --opportunity "Suncrest Media" --log eval/runs/s1.jsonl

# 3. Dry run: analysis + approval, no Odoo writes
python -m agent.run --opportunity "Vertex Security" --dry-run

# 4. Batch eval (auto-approve; every decision logged) + metrics table
python -m agent.run --opportunity "Suncrest Media" --log eval/runs/s1.jsonl --auto-approve
# ... repeat for S2-S4, then:
python eval/collect_results.py   # Odoo creds via ODOO_* env vars; writes results.json
```

## Run on your own machine

The repo detects its environment automatically:

- **In the author's sandbox** it calls Moonshot through the installed skill
  CLI (no API key needed in env).
- **Anywhere else** it calls Moonshot's OpenAI-compatible API directly —
  you need your own key from [platform.moonshot.ai](https://platform.moonshot.ai)
  (or `platform.moonshot.cn`; set `MOONSHOT_BASE_URL` accordingly):

```bash
git clone https://github.com/wangdiee/genai.git
cd genai
pip install -r requirements.txt
cp .env.example .env   # fill in ODOO_URL / ODOO_DB / ODOO_USER / ODOO_PASSWORD
                       # + MOONSHOT_API_KEY (+ MOONSHOT_BASE_URL if using .cn)
set -a; source .env; set +a   # or export the vars your own way

# Dry run first: full analysis, zero Odoo writes
python -m agent.run --opportunity "Suncrest Media" --dry-run
```

Odoo writes only happen after you approve each field in the terminal
(`--auto-approve` skips the prompts; every auto-decision is logged).

## Notes

- `xmlrpc.client` is part of the Python standard library.
- No credentials are committed; everything sensitive comes from env vars / `.env`.
- Status: Part A complete — live runs against Odoo 19.4 SaaS done 2026-09-28/29;
  see `eval/results_table.md` and `docs/architecture.md` §7 for measured results.
