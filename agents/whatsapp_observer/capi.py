"""Conversions API for Business Messaging, per client.

Meta accepts these standard events on WhatsApp threads: Purchase, LeadSubmitted,
QualifiedLead, InitiateCheckout, AddToCart, ViewContent, OrderCreated, OrderShipped,
OrderDelivered, OrderCanceled, OrderReturned, CartAbandoned, RatingProvided,
ReviewProvided. Click-to-WhatsApp ad sets can OPTIMISE on Purchase. That is why the
sale milestone always maps to Purchase here, whatever the business calls it, and the
qualified milestone maps to LeadSubmitted for reporting.

One event per (contact, event name, click id). Purchase waits a settle window and is
cancelled if the customer walks away inside it. Everything fails safe and returns a
string; nothing here may raise into the webhook.
"""
import json, time, urllib.request, urllib.error
from . import store

GRAPH_VERSION = "v21.0"
MAX_AGE_S = 7 * 86400


def _event_id(client, wa_id, event_name, clid):
    return f"{client.slug}-{event_name}-{wa_id}-{(clid or 'noclid')[:24]}"


def _record(client, wa_id, event_name, event_id, clid, value, state, status, detail="", evidence="", fire_after=None):
    c = store.conn(client)
    c.execute("INSERT INTO events (wa_id, event_name, event_id, ctwa_clid, value, currency, state, status, detail, "
              "evidence, fire_after) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (wa_id, event_name, event_id, clid, value, client.currency, state, status, detail[:400],
               (evidence or "")[:300], fire_after))
    c.commit(); c.close()


def already_fired(client, wa_id, event_name, clid):
    c = store.conn(client)
    r = c.execute("SELECT 1 FROM events WHERE event_id=? AND status IN ('sent','dry_run','pending')",
                  (_event_id(client, wa_id, event_name, clid),)).fetchone()
    c.close(); return bool(r)


def send(client, wa_id, event_name, value=None, state=None, evidence=""):
    att = store.attribution(client, wa_id)
    clid = att.get("ctwa_clid"); product = att.get("product")
    eid = _event_id(client, wa_id, event_name, clid); ts = int(time.time())
    if already_fired(client, wa_id, event_name, clid):
        return "skipped:duplicate"
    if not clid:
        _record(client, wa_id, event_name, eid, None, value, state, "skipped", "no ctwa_clid (organic)", evidence)
        return "skipped:no-clid"
    payload = {"event_name": event_name, "event_time": ts, "event_id": eid,
               "action_source": "business_messaging", "messaging_channel": "whatsapp",
               "user_data": {"ctwa_clid": clid}, "custom_data": {}}
    if client.waba_id:
        payload["user_data"]["whatsapp_business_account_id"] = client.waba_id
    if value is not None:
        payload["custom_data"].update({"value": float(value), "currency": client.currency})
    if product:
        payload["custom_data"]["content_name"] = product
    if state:
        payload["custom_data"]["conversation_state"] = state
    for k in ("ad_id", "adset_id", "campaign_id", "campaign_name", "adset_name", "ad_name"):
        if att.get(k):
            payload["custom_data"][k] = att[k]
    if client.dry_run or not (client.dataset_id and client.capi_token):
        why = "dry run" if client.dry_run else "no dataset/token configured"
        _record(client, wa_id, event_name, eid, clid, value, state, "dry_run", why, evidence)
        print(f"[observer:{client.slug}] DRY RUN {event_name} {wa_id} value={value} ({why})")
        return "dry_run"
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{client.dataset_id}/events?access_token={client.capi_token}"
    req = urllib.request.Request(url, data=json.dumps({"data": [payload]}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            resp = r.read().decode()[:400]
        _record(client, wa_id, event_name, eid, clid, value, state, "sent", resp, evidence)
        print(f"[observer:{client.slug}] sent {event_name} for {wa_id}: {resp}")
        return "sent"
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
    _record(client, wa_id, event_name, eid, clid, value, state, "failed", detail, evidence)
    print(f"[observer:{client.slug}] FAILED {event_name} for {wa_id}: {detail}")
    return f"failed:{detail[:80]}"


def queue_purchase(client, wa_id, state, evidence, value):
    clid = store.attribution(client, wa_id).get("ctwa_clid")
    eid = _event_id(client, wa_id, client.purchase_event, clid)
    if already_fired(client, wa_id, client.purchase_event, clid):
        return "skipped:duplicate"
    _record(client, wa_id, client.purchase_event, eid, clid, value, state, "pending",
            "settling", evidence, time.time() + client.settle_seconds)
    print(f"[observer:{client.slug}] queued {client.purchase_event} for {wa_id}, settles in {client.settle_seconds}s")
    return "queued"


def sweep(client, classify_fn):
    """Fire settled purchases, cancel the ones where the customer walked away."""
    c = store.conn(client)
    rows = c.execute("SELECT id, wa_id, value, state, evidence FROM events WHERE status='pending' AND fire_after<=?",
                     (time.time(),)).fetchall()
    c.close()
    for r in rows:
        res = classify_fn(client, store.thread(client, r["wa_id"]))
        c = store.conn(client)
        if res["state"] in ("LOST", "DISQUALIFIED"):
            c.execute("UPDATE events SET status='cancelled', detail=? WHERE id=?",
                      (f"walked away during settle: {res['state']} {res['evidence'][:120]}", r["id"]))
            c.commit(); c.close()
            print(f"[observer:{client.slug}] cancelled purchase for {r['wa_id']} ({res['state']})")
            continue
        c.execute("DELETE FROM events WHERE id=?", (r["id"],)); c.commit(); c.close()
        send(client, r["wa_id"], client.purchase_event, value=r["value"], state="COMMITTED", evidence=r["evidence"])
