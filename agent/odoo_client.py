"""XML-RPC client for the Odoo CRM instance.

Connection settings come from environment variables (see .env.example)::

    ODOO_URL        e.g. https://debbywangcrm.odoo.com
    ODOO_DB         database name
    ODOO_USER       login (email)
    ODOO_PASSWORD   password, or ODOO_API_KEY (API key preferred)

No credentials are hard-coded anywhere in this repository.

Transport note: this client POSTs XML-RPC via ``urllib.request`` (instead of
``xmlrpc.client.ServerProxy``) so that proxy environment variables are
honored and flaky connections are retried with backoff.
"""

import os
import time
import urllib.request
import xmlrpc.client

#: Retries for each XML-RPC round-trip (the hosted endpoint occasionally
#: resets connections; backoff below keeps runs robust).
_RPC_TRIES = 8
_RPC_TIMEOUT = 40


def _post_xmlrpc(url, method, params, tries=_RPC_TRIES, timeout=_RPC_TIMEOUT):
    """POST one XML-RPC call and return the decoded result value.

    ``tries`` stays >1 for idempotent reads/writes. Callers must pass
    ``tries=1`` for non-idempotent creates: blind transport retries of a
    create whose response was lost will commit duplicates server-side
    (observed live: one "connection closed" retry storm created 6 dupes).
    """
    body = xmlrpc.client.dumps(params, methodname=method).encode("utf-8")
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "text/xml"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
            result, _ = xmlrpc.client.loads(payload)
            return result[0] if result else None
        except Exception as exc:  # noqa: BLE001 - retry, then raise
            last = exc
            time.sleep(min(2**attempt, 15))
    raise RuntimeError(f"XML-RPC {method} failed after {tries} tries: {last}")


class OdooClient:
    """Thin wrapper around Odoo's XML-RPC API.

    Uses ``/xmlrpc/2/common`` for authentication and ``/xmlrpc/2/object``
    (``execute_kw``) for all model operations.
    """

    # Fields we read/write on crm.lead (opportunities).
    # Odoo notes: ``priority`` is a Selection 0..3 ("stars");
    # ``expected_revenue`` is a computed monetary field; ``activity_ids``
    # lists the open mail.activity records linked to the lead.
    LEAD_FIELDS = [
        "name",
        "partner_id",
        "expected_revenue",
        "probability",
        "priority",
        "stage_id",
        "date_deadline",
        "description",
        "activity_ids",
    ]

    ACTIVITY_FIELDS = [
        "activity_type_id",
        "summary",
        "note",
        "date_deadline",
        "user_id",
        "res_model",
        "res_id",
    ]

    def __init__(self, url=None, db=None, user=None, password=None):
        self.url = (url or os.environ["ODOO_URL"]).rstrip("/")
        self.db = db or os.environ["ODOO_DB"]
        self.user = user or os.environ["ODOO_USER"]
        # Prefer an API key when one is configured.
        self.password = (
            password
            or os.environ.get("ODOO_API_KEY")
            or os.environ.get("ODOO_PASSWORD")
        )
        if not self.password:
            raise RuntimeError("Set ODOO_API_KEY or ODOO_PASSWORD in the environment.")
        self.uid = None
        self._common_url = f"{self.url}/xmlrpc/2/common"
        self._object_url = f"{self.url}/xmlrpc/2/object"

    # ------------------------------------------------------------------ auth
    def authenticate(self):
        """Authenticate against ``/xmlrpc/2/common`` and store the uid."""
        self.uid = _post_xmlrpc(
            self._common_url, "authenticate", (self.db, self.user, self.password, {})
        )
        if not self.uid:
            raise RuntimeError(
                "Odoo authentication failed; check ODOO_DB / ODOO_USER / credentials."
            )
        return self.uid

    def _ensure_auth(self):
        if not self.uid:
            self.authenticate()

    # ------------------------------------------------------------- primitives
    def execute(self, model, method, args=None, kwargs=None, tries=_RPC_TRIES):
        """Call ``execute_kw`` on the object endpoint."""
        self._ensure_auth()
        return _post_xmlrpc(
            self._object_url,
            "execute_kw",
            (self.db, self.uid, self.password, model, method, args or [], kwargs or {}),
            tries=tries,
        )

    def search(self, model, domain, limit=None):
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        return self.execute(model, "search", [domain], kwargs)

    def search_read(self, model, domain, fields, limit=80):
        return self.execute(
            model, "search_read", [domain], {"fields": fields, "limit": limit}
        )

    def read(self, model, ids, fields):
        return self.execute(model, "read", [ids], {"fields": fields})

    def write(self, model, ids, vals):
        """Write ``vals`` on ``ids``. Returns True on success."""
        return self.execute(model, "write", [ids, vals])

    def create(self, model, vals, tries=1):
        """Create a record; returns the new id.

        Defaults to a single attempt: creates are not idempotent, so
        transport-level retries are unsafe here. Callers that retry a
        create must re-check server state first (see
        ``tools.create_followup_activity``).
        """
        return self.execute(model, "create", [vals], tries=tries)

    # ------------------------------------------------- crm.lead (opportunities)
    def list_opportunities(self, domain=None, limit=50):
        """List opportunities (crm.lead records of type 'opportunity')."""
        domain = [["type", "=", "opportunity"]] + (domain or [])
        return self.search_read("crm.lead", domain, self.LEAD_FIELDS, limit=limit)

    def get_opportunity(self, opp_id):
        """Read a single opportunity by id; None if missing."""
        recs = self.read("crm.lead", [opp_id], self.LEAD_FIELDS)
        return recs[0] if recs else None

    def find_opportunity_by_name(self, name):
        """Find an opportunity by (case-insensitive) name; None if missing."""
        ids = self.search(
            "crm.lead",
            [["name", "ilike", name], ["type", "=", "opportunity"]],
            limit=5,
        )
        return self.get_opportunity(ids[0]) if ids else None

    def update_opportunity(self, opp_id, vals):
        """Write back approved field updates on an opportunity."""
        return self.write("crm.lead", [opp_id], vals)

    # ------------------------------------------------------- mail.activity
    def list_activities(self, opp_id):
        """List open activities linked to an opportunity."""
        return self.search_read(
            "mail.activity",
            [["res_model", "=", "crm.lead"], ["res_id", "=", opp_id]],
            self.ACTIVITY_FIELDS,
        )

    def get_activity_type_id(self, name="To Do"):
        """Resolve a mail.activity.type id by name.

        Tolerant matching: case-insensitive, ignores spaces/hyphens, so the
        LLM's "To Do" matches Odoo's "To-Do".
        """
        norm = name.lower().replace(" ", "").replace("-", "")
        types = self.search_read("mail.activity.type", [], ["id", "name"], limit=20)
        for t in types:
            if t["name"].lower().replace(" ", "").replace("-", "") == norm:
                return t["id"]
        raise RuntimeError(
            f"Activity type {name!r} not found in mail.activity.type."
        )

    def _res_model_id(self, model="crm.lead"):
        """Resolve (and cache) the ir.model id Odoo 19 requires on activities."""
        if not hasattr(self, "_model_id_cache"):
            self._model_id_cache = {}
        if model not in self._model_id_cache:
            ids = self.search("ir.model", [["model", "=", model]], limit=1)
            if not ids:
                raise RuntimeError(f"Model {model!r} not found in ir.model.")
            self._model_id_cache[model] = ids[0]
        return self._model_id_cache[model]

    def create_activity(
        self,
        opp_id,
        activity_type="To Do",
        summary="",
        note="",
        date_deadline=None,
        user_id=None,
    ):
        """Schedule a follow-up activity on an opportunity.

        Odoo 19 links activities via ``res_model_id`` (ir.model) + ``res_id``;
        the legacy ``res_model`` char field is not accepted on create.
        """
        vals = {
            "res_model_id": self._res_model_id("crm.lead"),
            "res_id": opp_id,
            "activity_type_id": self.get_activity_type_id(activity_type),
            "summary": summary,
            "note": note or "",
        }
        if date_deadline:
            vals["date_deadline"] = date_deadline
        if user_id:
            vals["user_id"] = user_id
        return self.create("mail.activity", vals)
