"""Per-client SQLite store: contacts, messages, ad clicks, and conversion events.
Same shape that carried the first live account, with the business-specific columns
(product names, snooze, greeting) removed."""
import os, sqlite3, time, json, requests

GRAPH = "https://graph.facebook.com/v21.0"


def conn(client):
    os.makedirs(os.path.dirname(client.db_path), exist_ok=True)
    c = sqlite3.connect(client.db_path)
    c.row_factory = sqlite3.Row
    return c


def init(client):
    c = conn(client)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS contacts (
      wa_id TEXT PRIMARY KEY, profile_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_inbound_at TIMESTAMP, ctwa_clid TEXT, ctwa_clid_at TIMESTAMP, product TEXT,
      state TEXT, state_evidence TEXT, state_at TIMESTAMP, last_lat REAL, last_lng REAL);
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT, wa_id TEXT, direction TEXT, msg_type TEXT, body TEXT,
      wamid TEXT UNIQUE, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS clicks (
      id INTEGER PRIMARY KEY AUTOINCREMENT, wa_id TEXT, ctwa_clid TEXT, ad_id TEXT, adset_id TEXT,
      campaign_id TEXT, ad_name TEXT, adset_name TEXT, campaign_name TEXT, headline TEXT, ad_body TEXT,
      source_url TEXT, seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, wa_id TEXT, event_name TEXT, event_id TEXT, ctwa_clid TEXT,
      value REAL, currency TEXT, state TEXT, status TEXT, detail TEXT, evidence TEXT,
      fire_after REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS ix_msg_wa ON messages(wa_id, id);
    CREATE INDEX IF NOT EXISTS ix_ev_wa ON events(wa_id, event_name);
    """)
    c.commit(); c.close()


def upsert_contact(client, wa_id, profile_name=None):
    c = conn(client)
    c.execute("INSERT INTO contacts (wa_id, profile_name) VALUES (?, ?) ON CONFLICT(wa_id) DO NOTHING",
              (wa_id, profile_name))
    if profile_name:
        c.execute("UPDATE contacts SET profile_name = COALESCE(NULLIF(profile_name,''), ?) WHERE wa_id = ?",
                  (profile_name, wa_id))
    c.commit(); c.close()


def record_message(client, wa_id, direction, msg_type, body, wamid=None, status=None):
    """True if new, False if this wamid was already stored (Meta redelivers)."""
    c = conn(client)
    try:
        c.execute("INSERT INTO messages (wa_id, direction, msg_type, body, wamid, status) VALUES (?,?,?,?,?,?)",
                  (wa_id, direction, msg_type, body, wamid, status))
        if direction == "in":
            c.execute("UPDATE contacts SET last_inbound_at = CURRENT_TIMESTAMP WHERE wa_id = ?", (wa_id,))
        c.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        c.close()


def set_status(client, wamid, status):
    c = conn(client); c.execute("UPDATE messages SET status=? WHERE wamid=?", (status, wamid)); c.commit(); c.close()


def thread(client, wa_id, limit=80):
    c = conn(client)
    rows = c.execute("SELECT direction, msg_type, body, created_at FROM messages WHERE wa_id=? "
                     "ORDER BY id DESC LIMIT ?", (wa_id, limit)).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]


def contact(client, wa_id):
    c = conn(client); r = c.execute("SELECT * FROM contacts WHERE wa_id=?", (wa_id,)).fetchone(); c.close()
    return dict(r) if r else None


def set_state(client, wa_id, state, evidence):
    c = conn(client)
    c.execute("UPDATE contacts SET state=?, state_evidence=?, state_at=CURRENT_TIMESTAMP WHERE wa_id=?",
              (state, (evidence or "")[:300], wa_id))
    c.commit(); c.close()


def set_location(client, wa_id, lat, lng):
    c = conn(client); c.execute("UPDATE contacts SET last_lat=?, last_lng=? WHERE wa_id=?", (lat, lng, wa_id)); c.commit(); c.close()


# ---- attribution ---------------------------------------------------------------
def _lineage(client, ad_id):
    """Ad set + campaign for an ad id. Not scoped to an ad account on purpose, so it
    keeps working if the client's ads move accounts. Needs the client's ads token."""
    if not (client.ads_token and ad_id):
        return {}
    try:
        r = requests.get(f"{GRAPH}/{ad_id}", params={
            "fields": "name,adset{id,name},campaign{id,name}", "access_token": client.ads_token}, timeout=15).json()
        return {"ad_name": r.get("name"), "adset_id": (r.get("adset") or {}).get("id"),
                "adset_name": (r.get("adset") or {}).get("name"),
                "campaign_id": (r.get("campaign") or {}).get("id"),
                "campaign_name": (r.get("campaign") or {}).get("name")}
    except Exception as e:
        print(f"[observer:{client.slug}] lineage lookup failed for {ad_id}: {e}")
        return {}


def capture_referral(client, wa_id, msg):
    """Click-to-WhatsApp referral arrives ONLY on the first message of a conversation.
    Store the click id first (unrecoverable), then enrich with lineage."""
    ref = msg.get("referral") or {}
    if not ref:
        return None
    clid = ref.get("ctwa_clid"); ad_id = str(ref.get("source_id") or "") or None
    c = conn(client)
    c.execute("INSERT INTO clicks (wa_id, ctwa_clid, ad_id, headline, ad_body, source_url) VALUES (?,?,?,?,?,?)",
              (wa_id, clid, ad_id, ref.get("headline"), ref.get("body"), ref.get("source_url")))
    if clid:
        c.execute("UPDATE contacts SET ctwa_clid=?, ctwa_clid_at=CURRENT_TIMESTAMP WHERE wa_id=?", (clid, wa_id))
    c.commit(); c.close()
    lin = _lineage(client, ad_id)
    if lin:
        c = conn(client)
        c.execute("UPDATE clicks SET ad_name=?, adset_id=?, adset_name=?, campaign_id=?, campaign_name=? "
                  "WHERE wa_id=? AND ad_id=? AND adset_id IS NULL",
                  (lin.get("ad_name"), lin.get("adset_id"), lin.get("adset_name"),
                   lin.get("campaign_id"), lin.get("campaign_name"), wa_id, ad_id))
        c.commit(); c.close()
    print(f"[observer:{client.slug}] click {wa_id}: clid={'yes' if clid else 'NO'} ad={ad_id} "
          f"campaign={lin.get('campaign_name')!r}")
    return clid


def attribution(client, wa_id):
    c = conn(client)
    r = c.execute("SELECT ctwa_clid, ad_id, ad_name, adset_id, adset_name, campaign_id, campaign_name, "
                  "headline, ad_body, source_url FROM clicks WHERE wa_id=? ORDER BY seen_at DESC LIMIT 1",
                  (wa_id,)).fetchone()
    ct = c.execute("SELECT product FROM contacts WHERE wa_id=?", (wa_id,)).fetchone()
    c.close()
    d = dict(r) if r else {}
    d["product"] = (ct["product"] if ct else None)
    return d


def set_product(client, wa_id, product):
    if not product:
        return
    c = conn(client); c.execute("UPDATE contacts SET product=? WHERE wa_id=? AND (product IS NULL OR product='')",
                                (product, wa_id)); c.commit(); c.close()
