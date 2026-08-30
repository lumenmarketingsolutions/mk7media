# -*- coding: utf-8 -*-
"""
Conversions API for Business Messaging — the FGC dispatcher.

This is NOT the same thing as the web Conversions API already in app.py. Business
messaging events carry `action_source: business_messaging`, a `messaging_channel`, and
they attribute through `ctwa_clid` rather than `fbc`/`fbp`. Sending a messaging
conversion through the web path silently produces an unattributed event: Meta accepts
it, the dataset shows a green tick, and no ad ever gets credit. That failure looks
exactly like success, which is why this lives in its own module.

Two standard events are worth sending:

    LeadSubmitted   the customer is a real, qualified prospect
    Purchase        the customer committed, with a value

Nothing else. There is no "unqualified lead" event and we must never invent one —
Meta's optimiser learns from what we send it, so feeding it junk teaches it to find
more junk. Unqualified conversations, objections, dormancy and the follow-up list are
merchant-facing reporting and stay in our own dashboard, which is the half of the
product a competitor cannot copy off an ad account.

Safety posture: dry run by default. Firing events into a live ad account changes how
Meta spends the merchant's money, so this ships inert and Kendall turns it on.
"""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

GRAPH_VERSION = os.environ.get("FGC_GRAPH_VERSION", "v21.0")

DATASET_ID = os.environ.get("FGC_CAPI_DATASET_ID", "")
ACCESS_TOKEN = os.environ.get("FGC_CAPI_TOKEN", "")
TEST_EVENT_CODE = os.environ.get("FGC_CAPI_TEST_EVENT_CODE", "")

# Default ON. An operator has to set this to "0" deliberately.
DRY_RUN = os.environ.get("FGC_CAPI_DRY_RUN", "1") != "0"

# Meta rejects the ENTIRE request if any event_time is more than 7 days old, so a
# single stale event would take a whole batch down with it. We check per event and
# skip, rather than discover it as a 400 on everything.
MAX_EVENT_AGE_S = 7 * 24 * 3600 - 3600      # an hour of headroom for clock skew

# How long a commitment has to survive before it counts. The corpus has a customer who
# gave an address, heard the delivery fee, said "la2 shukran", and re-committed two
# turns later — inside five minutes. Firing on the address would have reported a sale
# that did not exist yet; firing on the walk-away would have lost one that did.
SETTLE_SECONDS = int(os.environ.get("FGC_CAPI_SETTLE_SECONDS", str(30 * 60)))

CURRENCY = os.environ.get("FGC_CAPI_CURRENCY", "USD")

VALID_EVENTS = ("LeadSubmitted", "Purchase")


def _db():
    from . import agent
    conn = sqlite3.connect(agent.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _event_id(wa_id, event_name, ctwa_clid):
    """Stable per conversation and event, so a retry or a redeploy cannot double-fire.
    Keyed on the click id too: a customer who clicks a second ad and buys again is a
    genuinely new conversion and should be allowed through."""
    return f"fgc-{event_name}-{wa_id}-{(ctwa_clid or 'noclid')[:24]}"


def _record(wa_id, event_name, event_id, ctwa_clid, value, state, status, detail=""):
    conn = _db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO wa_capi_events "
            "(wa_id, event_name, event_id, ctwa_clid, value, currency, state, status, detail) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (wa_id, event_name, event_id, ctwa_clid, value, CURRENCY, state, status,
             detail[:500]))
        conn.commit()
    finally:
        conn.close()


def already_fired(wa_id, event_name, ctwa_clid=None):
    """True if this event has been sent (or dry-run) for this conversation already."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT 1 FROM wa_capi_events WHERE event_id = ? AND status != 'failed'",
            (_event_id(wa_id, event_name, ctwa_clid),)).fetchone()
        return row is not None
    finally:
        conn.close()


def send(wa_id, event_name, ctwa_clid=None, value=None, state=None,
         event_time=None, product=None, extra=None):
    """Send one business-messaging conversion. Returns a short status string.

    Safe-fail by design: every path returns a string and none raise, because this is
    called from the webhook thread and an attribution failure must never cost the
    merchant a reply to a customer.
    """
    if event_name not in VALID_EVENTS:
        return f"skipped:unknown-event:{event_name}"

    if ctwa_clid is None:
        try:
            from . import agent
            ctwa_clid = agent.get_ctwa_clid(wa_id)
        except Exception:
            ctwa_clid = None

    event_id = _event_id(wa_id, event_name, ctwa_clid)
    ts = int(event_time or time.time())

    # ---- guards, cheapest first
    if already_fired(wa_id, event_name, ctwa_clid):
        return "skipped:duplicate"

    if not ctwa_clid:
        # Not an error. Organic WhatsApp traffic has no click id and never will; there
        # is simply no ad to credit. Recorded so the merchant report can show what
        # share of orders came from ads versus everywhere else.
        _record(wa_id, event_name, event_id, None, value, state, "skipped",
                "no ctwa_clid (organic or pre-capture conversation)")
        return "skipped:no-clid"

    age = time.time() - ts
    if age > MAX_EVENT_AGE_S:
        _record(wa_id, event_name, event_id, ctwa_clid, value, state, "skipped",
                f"event_time {int(age / 86400)}d old, past Meta's 7-day limit")
        return "skipped:too-old"

    payload = {
        "event_name": event_name,
        "event_time": ts,
        "event_id": event_id,
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": {"ctwa_clid": ctwa_clid},
        "custom_data": {},
    }
    if value is not None:
        payload["custom_data"].update({"value": float(value), "currency": CURRENCY})
    if product:
        payload["custom_data"]["content_name"] = product
    # Carried on every event even when nothing slices by it yet. Custom Conversions are
    # built on parameters that were already being sent; a parameter you did not send
    # cannot be backfilled onto events that already landed.
    if state:
        payload["custom_data"]["conversation_state"] = state
    if extra:
        payload["custom_data"].update(extra)

    if DRY_RUN or not (DATASET_ID and ACCESS_TOKEN):
        why = "dry run" if DRY_RUN else "no dataset/token configured"
        _record(wa_id, event_name, event_id, ctwa_clid, value, state, "dry_run", why)
        print(f"[fgc-capi] DRY RUN {event_name} {wa_id} "
              f"value={value} state={state} ({why})")
        return "dry_run"

    body = {"data": [payload]}
    if TEST_EVENT_CODE:
        body["test_event_code"] = TEST_EVENT_CODE

    url = (f"https://graph.facebook.com/{GRAPH_VERSION}/{DATASET_ID}/events"
           f"?access_token={ACCESS_TOKEN}")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            resp = r.read().decode()[:400]
        _record(wa_id, event_name, event_id, ctwa_clid, value, state, "sent", resp)
        print(f"[fgc-capi] sent {event_name} for {wa_id}: {resp}")
        return "sent"
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
    # Recorded as failed, which leaves already_fired() False so a later retry can run.
    _record(wa_id, event_name, event_id, ctwa_clid, value, state, "failed", detail)
    print(f"[fgc-capi] FAILED {event_name} for {wa_id}: {detail}")
    return f"failed:{detail[:80]}"


def status():
    """Config and counts, for the debug endpoint."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT event_name, status, COUNT(*) n FROM wa_capi_events "
            "GROUP BY event_name, status").fetchall()
        captured = conn.execute(
            "SELECT COUNT(*) n FROM wa_contacts WHERE ctwa_clid IS NOT NULL").fetchone()["n"]
        clicks = conn.execute("SELECT COUNT(*) n FROM wa_ctwa_clicks").fetchone()["n"]
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()
    return {
        "dry_run": DRY_RUN,
        "dataset_configured": bool(DATASET_ID),
        "token_configured": bool(ACCESS_TOKEN),
        "test_event_code": TEST_EVENT_CODE or None,
        "settle_seconds": SETTLE_SECONDS,
        "currency": CURRENCY,
        "contacts_with_ctwa_clid": captured,
        "ctwa_clicks_recorded": clicks,
        "events": [{"event": r["event_name"], "status": r["status"], "n": r["n"]}
                   for r in rows],
    }
