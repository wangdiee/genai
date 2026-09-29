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
│   └── edge_cases.py       # edge-case detectors + recovery/escalation paths
└── docs/
    └── architecture.md     # data flow, tools, prompts, data models
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
| `MOONSHOT_MODEL`    | default `kimi-k2`                                        |

## Running

```bash
# 1. Seed the 4 HW1 mock opportunities + synthetic communications
python seed/seed_data.py

# 2. Run the agent on one opportunity (HITL approval in the terminal)
python -m agent.run --opportunity "Suncrest Media" --log runs/s1.jsonl

# 3. Dry run: analysis + approval, no Odoo writes
python -m agent.run --opportunity "Vertex Security" --dry-run

# 4. Metrics helpers (see eval/metrics.py)
python -m eval.metrics --help   # TODO: wire CLI in the eval step
```

## Notes

- `xmlrpc.client` is part of the Python standard library.
- No credentials are committed; everything sensitive comes from env vars / `.env`.
- Skeleton status: integration code paths are complete but require live
  credentials to execute; eval wiring and screenshots are collected in Part A.
