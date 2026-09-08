"""Webhook entry point. Routes each change to its client by phone_number_id, stores
the traffic, classifies after every customer message, and dispatches events.

It NEVER sends a message. There is no send function in this package.
"""
import threading
from . import config, store, capi, classifier


def is_observer_event(value):
    pid = str((value.get("metadata") or {}).get("phone_number_id") or "")
    return config.by_phone_id(pid) is not None


def _text(msg):
    t = msg.get("type") or "unknown"
    if t == "text":
        return (msg.get("text") or {}).get("body") or ""
    if t in ("button", "interactive"):
        b = msg.get("button") or (msg.get("interactive") or {}).get("button_reply") or \
            (msg.get("interactive") or {}).get("list_reply") or {}
        return b.get("text") or b.get("title") or f"[{t}]"
    if t == "location":
        loc = msg.get("location") or {}
        return f"[location pin {loc.get('latitude')},{loc.get('longitude')} {loc.get('name') or ''} {loc.get('address') or ''}]".strip()
    if t in ("image", "video", "audio", "document", "sticker"):
        cap = (msg.get(t) or {}).get("caption")
        return f"[{t} message]" + (f" {cap}" if cap else "")
    return f"[{t} message]"


def _dispatch(client, wa_id):
    """Classify the thread and turn state changes into events. Runs off-thread so a
    Graph or model call can never delay Meta's webhook acknowledgement."""
    try:
        res = classifier.classify(client, store.thread(client, wa_id))
        prev = (store.contact(client, wa_id) or {}).get("state")
        store.set_state(client, wa_id, res["state"], res["evidence"])
        if res.get("product"):
            store.set_product(client, wa_id, res["product"])
        print(f"[observer:{client.slug}] {wa_id}: {prev or '-'} -> {res['state']} ({res['source']}) {res['evidence'][:60]!r}")
        st = res["state"]
        if st in ("QUALIFIED", "INTENT", "COMMITTED"):
            capi.send(client, wa_id, client.lead_event, state=st, evidence=res["evidence"])
        if st == "COMMITTED":
            value = client.value_for(res.get("product") or store.attribution(client, wa_id).get("product"))
            if value and res.get("quantity"):
                value = value * int(res["quantity"])
            capi.queue_purchase(client, wa_id, st, res["evidence"], value)
        capi.sweep(client, classifier.classify)
    except Exception as e:
        print(f"[observer:{client.slug}] dispatch error for {wa_id}: {repr(e)[:160]}")


def handle_value(value):
    pid = str((value.get("metadata") or {}).get("phone_number_id") or "")
    client = config.by_phone_id(pid)
    if not client:
        return
    store.init(client)
    for st in value.get("statuses") or []:
        if st.get("id") and st.get("status"):
            store.set_status(client, st["id"], st["status"])
    for echo in (value.get("message_echoes") or value.get("smb_message_echoes") or []):
        to = echo.get("to")
        if to:
            store.upsert_contact(client, to)
            store.record_message(client, to, "out", echo.get("type") or "text", _text(echo), wamid=echo.get("id"))
    names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
    for msg in value.get("messages") or []:
        wa_id = msg.get("from")
        if not wa_id:
            continue
        store.upsert_contact(client, wa_id, names.get(wa_id))
        store.capture_referral(client, wa_id, msg)
        if msg.get("type") == "location":
            loc = msg.get("location") or {}
            store.set_location(client, wa_id, loc.get("latitude"), loc.get("longitude"))
        if store.record_message(client, wa_id, "in", msg.get("type") or "unknown", _text(msg), wamid=msg.get("id")):
            threading.Thread(target=_dispatch, args=(client, wa_id), daemon=True).start()


def handle_webhook(payload):
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            handle_value(change.get("value") or {})


def report(client, limit=200):
    """What the client sees: states, events, and which campaign produced them."""
    c = store.conn(client)
    states = {r["state"] or "NEW": r["n"] for r in c.execute(
        "SELECT state, COUNT(*) n FROM contacts GROUP BY state")}
    events = [dict(r) for r in c.execute(
        "SELECT wa_id, event_name, value, state, status, detail, created_at FROM events ORDER BY id DESC LIMIT ?", (limit,))]
    by_campaign = [dict(r) for r in c.execute(
        "SELECT k.campaign_name, COUNT(DISTINCT k.wa_id) clicks, "
        "SUM(CASE WHEN c.state='COMMITTED' THEN 1 ELSE 0 END) committed, "
        "SUM(CASE WHEN c.state IN ('QUALIFIED','INTENT','COMMITTED') THEN 1 ELSE 0 END) qualified "
        "FROM clicks k JOIN contacts c ON c.wa_id=k.wa_id GROUP BY k.campaign_name ORDER BY clicks DESC")]
    c.close()
    return {"client": client.name, "dry_run": client.dry_run, "states": states, "by_campaign": by_campaign,
            "events": events}
