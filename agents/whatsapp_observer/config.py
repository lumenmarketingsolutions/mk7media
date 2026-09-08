"""Per-client configuration. One JSON file per client in clients/, keyed by the
WhatsApp phone_number_id that receives the conversations.

Secrets never live in the JSON. Each secret field names an ENVIRONMENT VARIABLE that
holds the value, so a client file can be committed and shared safely.
"""
import json, os, glob

HERE = os.path.dirname(__file__)
CLIENTS_DIR = os.path.join(HERE, "clients")
DATA_DIR = os.environ.get("OBSERVER_DATA_DIR", "/data/observer")

DEFAULTS = {
    "currency": "USD",
    "default_value": 0,
    "product_values": {},
    "languages": ["English"],
    "settle_minutes": 30,
    "dry_run": True,
    "lead_event": "LeadSubmitted",
    "purchase_event": "Purchase",
    "committed_signals": [],
    "qualified_signals": [],
    "lost_signals": [],
    "disqualify_signals": [],
    "location_pin_is_commitment": False,
    "classifier_model": "",
}


class Client:
    def __init__(self, d):
        self.raw = {**DEFAULTS, **d}
        r = self.raw
        self.slug = r["slug"]
        self.name = r["business_name"]
        self.phone_number_id = str(r["phone_number_id"])
        self.waba_id = str(r.get("waba_id") or "")
        self.dataset_id = str(r.get("dataset_id") or "")
        self.capi_token = os.environ.get(r.get("capi_token_env") or "", "")
        self.ads_token = os.environ.get(r.get("ads_token_env") or "", "")
        self.app_secret = os.environ.get(r.get("app_secret_env") or "WHATSAPP_APP_SECRET", "")
        self.currency = r["currency"]
        self.default_value = float(r["default_value"] or 0)
        self.product_values = {k: float(v) for k, v in (r["product_values"] or {}).items()}
        self.settle_seconds = int(float(r["settle_minutes"]) * 60)
        self.dry_run = bool(r["dry_run"])
        self.lead_event = r["lead_event"]
        self.purchase_event = r["purchase_event"]
        self.model = r["classifier_model"] or os.environ.get("OBSERVER_MODEL", "") or \
            os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")
        self.db_path = os.path.join(DATA_DIR, f"{self.slug}.db")

    def contract(self):
        """The conversion contract: the client's own answers, verbatim, that tell the
        classifier what a lead and a sale look like for THIS business."""
        r = self.raw
        return {k: r.get(k) for k in (
            "business_description", "what_is_sold", "how_customers_pay", "how_fulfilment_works",
            "qualified_lead_definition", "sale_definition", "win_type", "committed_signals", "qualified_signals",
            "lost_signals", "disqualify_signals", "location_pin_is_commitment",
            "typical_objections", "languages", "product_values", "currency", "default_value")}

    def value_for(self, product):
        if product and product in self.product_values:
            return self.product_values[product]
        return self.default_value or None


# ---- storage: a small SQLite table on the data volume, editable from the admin UI.
# JSON files in clients/ act as seeds: imported once if their slug is not in the DB.
import sqlite3, time as _time

def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(os.path.join(DATA_DIR, "clients.db")); c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS observer_clients (slug TEXT PRIMARY KEY, config TEXT NOT NULL,
      created REAL, updated REAL);
    CREATE TABLE IF NOT EXISTS observer_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, role TEXT,
      text TEXT, changed TEXT, created REAL);""")
    return c


def _seed():
    c = _db()
    for p in sorted(glob.glob(os.path.join(CLIENTS_DIR, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        try:
            d = json.load(open(p)); slug = d["slug"]
            if not c.execute("SELECT 1 FROM observer_clients WHERE slug=?", (slug,)).fetchone():
                c.execute("INSERT INTO observer_clients (slug, config, created, updated) VALUES (?,?,?,?)",
                          (slug, json.dumps(d), _time.time(), _time.time()))
        except Exception as e:
            print(f"[observer] bad client file {p}: {e}")
    c.commit(); c.close()


def list_configs():
    _seed(); c = _db()
    rows = [dict(r) for r in c.execute("SELECT slug, config, created, updated FROM observer_clients ORDER BY created")]
    c.close()
    out = []
    for r in rows:
        d = json.loads(r["config"]); d["_created"] = r["created"]; d["_updated"] = r["updated"]; out.append(d)
    return out


def get_config(slug):
    _seed(); c = _db()
    r = c.execute("SELECT config FROM observer_clients WHERE slug=?", (slug,)).fetchone(); c.close()
    return json.loads(r["config"]) if r else None


def save_config(d):
    slug = d["slug"]; d = {k: v for k, v in d.items() if not k.startswith("_")}
    c = _db(); now = _time.time()
    if c.execute("SELECT 1 FROM observer_clients WHERE slug=?", (slug,)).fetchone():
        c.execute("UPDATE observer_clients SET config=?, updated=? WHERE slug=?", (json.dumps(d), now, slug))
    else:
        c.execute("INSERT INTO observer_clients (slug, config, created, updated) VALUES (?,?,?,?)",
                  (slug, json.dumps(d), now, now))
    c.commit(); c.close(); _CACHE["at"] = 0
    return d


def chat_log(slug, limit=60):
    c = _db(); rows = [dict(r) for r in c.execute(
        "SELECT role, text, changed, created FROM observer_chat WHERE slug=? ORDER BY id DESC LIMIT ?", (slug, limit))]
    c.close(); return list(reversed(rows))


def chat_append(slug, role, text, changed=None):
    c = _db(); c.execute("INSERT INTO observer_chat (slug, role, text, changed, created) VALUES (?,?,?,?,?)",
                         (slug, role, text, json.dumps(changed) if changed else None, _time.time()))
    c.commit(); c.close()


def load_all():
    out = {}
    for d in list_configs():
        try:
            c = Client(d)
            if c.phone_number_id and c.phone_number_id != DEFAULTS.get("phone_number_id"):
                out[c.phone_number_id] = c
        except Exception as e:
            print(f"[observer] bad client config {d.get('slug')}: {e}")
    return out


def client_by_slug(slug):
    d = get_config(slug)
    return Client(d) if d else None


_CACHE = {"at": 0, "clients": {}}


def by_phone_id(phone_number_id):
    import time
    if time.time() - _CACHE["at"] > 60:
        _CACHE["clients"] = load_all(); _CACHE["at"] = time.time()
    return _CACHE["clients"].get(str(phone_number_id or ""))
