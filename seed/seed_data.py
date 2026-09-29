"""Seed HW1 synthetic data into the live Odoo instance.

- Creates the 4 mock opportunities from HW1 §3.7 if they do not exist
  (matched by name — the script is idempotent).
- Creates one overdue follow-up activity on Suncrest Media if it has none.
- Writes synthetic customer communications as local text files under
  ``seed/comms/`` (existing files are left untouched).

Usage:
    python seed/seed_data.py [--comms-only]
"""

import argparse
import os
from datetime import date, timedelta

from agent.odoo_client import OdooClient

# The 4 pain-point indicator opportunities from HW1 §3.7.
# Odoo ``priority`` is a 0..3 selection ("stars"): 1 = Medium, 2 = High.
OPPORTUNITIES = [
    {
        "name": "Suncrest Media",
        "expected_revenue": 76000.0,
        "probability": 40.0,
        "priority": "2",
        "date_deadline": (date.today() + timedelta(days=30)).isoformat(),
        "description": (
            "High-value media deal. Budget confirmed at $76,000; proposal "
            "requested. Follow-up activity is overdue."
        ),
    },
    {
        "name": "Vertex Security",
        "expected_revenue": 54000.0,
        "probability": 25.0,
        "priority": "2",
        "description": (
            "High-priority security deal. Discovery meeting has not been "
            "scheduled for an extended period."
        ),
    },
    {
        "name": "Greenline Energy",
        "expected_revenue": 38000.0,
        "probability": 35.0,
        "priority": "1",
        "description": (
            "Energy deal. Communication records indicate strong purchase "
            "intent, although priority is currently Medium."
        ),
    },
    {
        "name": "FreshFork Foods",
        "expected_revenue": 22000.0,
        "probability": 30.0,
        "priority": "1",
        "description": (
            "Food-service deal. Customer purchase intent has changed; no "
            "follow-up activity is scheduled."
        ),
    },
]

# Synthetic customer communications (also mirrored as files under seed/comms/).
COMMS = {
    "suncrest_email.txt": """\
Subject: Re: Proposal for Q4 media package
From: Lena Park <lena.park@suncrestmedia.example>
To: sales@debbywang.example
Date: 2026-09-10

Hi team,

Thanks for the walkthrough last week. Our budget for the Q4 media package
is confirmed at $76,000. Please send the formal proposal — we'd like to
kick off within 30 days.

Decision maker: Lena Park (VP Marketing). Timeline: start before Oct 15.

Best,
Lena

---
Internal note (2026-09-20): Proposal sent on 09-12. Follow-up activity is
now overdue — no check-in call logged in the last 8 days.
""",
    "vertex_meeting_notes.txt": """\
Meeting notes — Vertex Security intro call (2026-08-28)
Attendees: Marcus Chen (CISO, decision maker), sales rep.

- Strong interest in the enterprise security bundle; asked for a technical
  deep dive.
- Budget range discussed: ~$50-60k annually. Timeline: decision this quarter.
- ACTION: schedule discovery meeting with their infrastructure lead.

Status (2026-09-27): the discovery meeting has NOT been scheduled yet.
CRM priority: High.
""",
    "greenline_call_notes.txt": """\
Call notes — Greenline Energy (2026-09-18)
Spoke with: Dana Ruiz (Operations Director).

- "We're ready to move forward once the pilot terms are confirmed."
- Asked about implementation timeline and onboarding support.
- Strong purchase intent: explicitly requested a draft order form.
- Decision maker: Dana Ruiz. Timeline: pilot start next month.

Note: CRM priority is currently Medium — communications suggest High.
""",
    "freshfork_email.txt": """\
Subject: Re: Renewal discussion
From: Priya Nair <priya.nair@freshforkfoods.example>
To: sales@debbywang.example
Date: 2026-09-22

Hi,

Heads-up that our priorities have shifted — the catering expansion is on
hold and we are re-evaluating vendors. Let's pause the current proposal
for now; I will reach out when we have clarity.

Thanks,
Priya

---
Internal note (2026-09-27): purchase intent changed; no follow-up activity
scheduled yet. Probability should likely be lowered and a check-in planned.
""",
}


def seed_opportunities(client):
    for vals in OPPORTUNITIES:
        existing = client.find_opportunity_by_name(vals["name"])
        if existing:
            print(f"  exists: {vals['name']} (id={existing['id']})")
            continue
        new_id = client.create("crm.lead", {"type": "opportunity", **vals})
        print(f"  created: {vals['name']} (id={new_id})")


def seed_overdue_activity(client):
    """Seed the HW1 pain-point indicator: an overdue follow-up on Suncrest."""
    opp = client.find_opportunity_by_name("Suncrest Media")
    if not opp:
        print("  Suncrest Media not found; skipping overdue activity seed.")
        return
    if client.list_activities(opp["id"]):
        print("  Suncrest Media already has activities; skipping.")
        return
    overdue = (date.today() - timedelta(days=6)).isoformat()
    act_id = client.create_activity(
        opp["id"],
        activity_type="To Do",
        summary="Follow up on requested proposal",
        note="Seeded: this follow-up is overdue (HW1 pain-point indicator).",
        date_deadline=overdue,
    )
    print(f"  created overdue activity (id={act_id}) on Suncrest Media, deadline={overdue}")


def seed_comms(comms_dir="seed/comms"):
    os.makedirs(comms_dir, exist_ok=True)
    for fname, content in COMMS.items():
        path = os.path.join(comms_dir, fname)
        if os.path.exists(path):
            print(f"  exists: {path}")
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"  wrote: {path}")


def main():
    parser = argparse.ArgumentParser(description="Seed HW1 synthetic data into Odoo")
    parser.add_argument("--comms-only", action="store_true", help="Only write comms files, skip Odoo")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    print("Seeding synthetic communications...")
    seed_comms()
    if args.comms_only:
        return
    print("Seeding opportunities into Odoo...")
    client = OdooClient()
    seed_opportunities(client)
    print("Seeding overdue activity...")
    seed_overdue_activity(client)
    print("Done.")


if __name__ == "__main__":
    main()
