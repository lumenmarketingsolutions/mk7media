# -*- coding: utf-8 -*-
"""
Read-only aggregates for the client dashboard.

The conversation data lives here, in the agent's own database, because this is where
the webhook lands. The portal lives in another service and another repo. Rather than
copy rows between them — two sources of truth is how you end up with a dashboard that
quietly disagrees with reality — the portal asks this module a question over HTTP and
renders the answer.

Nothing here writes. Nothing here returns a message body either — the dashboard shows
the shape of a conversation, never its contents. A merchant reading their own funnel
does not need a transcript on screen, and the moment transcripts are on screen they are
also in screenshots.

Phone numbers ARE returned in full, deliberately. Masking them looked prudent and was
useless: the operator's next action after reading this table is to open the thread in
WhatsApp or paste the number into their order sheet, and a masked number makes both
impossible. It is the merchant's own customer list, shown to the merchant.
"""
import sqlite3
import time
from datetime import datetime, timedelta

STATE_ORDER = ["NEW", "ENQUIRY", "QUALIFIED", "INTENT", "COMMITTED"]


def _conn(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _digits(wa_id):
    return "".join(c for c in str(wa_id or "") if c.isdigit())


def _pretty(wa_id):
    """+961 81 873 275 — grouped so a human can read it back over the phone."""
    d = _digits(wa_id)
    if not d:
        return "—"
    if d.startswith("961") and len(d) >= 10:
        return f"+961 {d[3:5]} {d[5:8]} {d[8:]}"
    if len(d) == 11 and d.startswith("1"):
        return f"+1 {d[1:4]} {d[4:7]} {d[7:]}"
    return "+" + d


def _age(ts):
    """Human idle time. Rounded hard on purpose — 'about 3 hours' is what an operator
    acts on; '3h 12m 41s' is noise dressed as precision."""
    if not ts:
        return "—"
    try:
        then = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "—"
    mins = max(0, int((datetime.utcnow() - then).total_seconds() // 60))
    if mins < 60:
        return f"{mins}m"
    if mins < 60 * 48:
        return f"{mins // 60}h"
    return f"{mins // 1440}d"


def numbers(db_path):
    """Every business number that has actually received traffic, with a count.

    Read from the data rather than from configuration, so a number that was connected
    but never used does not appear as an empty tab, and a number nobody remembered to
    write down still shows up the moment a customer messages it."""
    con = _conn(db_path)
    try:
        rows = con.execute(
            "SELECT COALESCE(via_phone_id,'') pid, COUNT(*) n FROM wa_contacts "
            "GROUP BY COALESCE(via_phone_id,'') ORDER BY n DESC").fetchall()
    except Exception:
        return []
    finally:
        con.close()
    return [{"phone_number_id": r["pid"], "conversations": r["n"]}
            for r in rows if r["pid"]]


def events_detail(db_path, limit=200):
    """Row-level conversion events for the operator console.

    The client dashboard shows what happened to their customers; this shows what
    happened to our events, which is a different question and only interesting to
    whoever is running the system. Cancelled and skipped rows carry the reason,
    because 'why did this not fire' is the whole point of looking."""
    con = _conn(db_path)
    try:
        rows = con.execute(
            "SELECT wa_id, event_name, status, value, currency, state, detail, "
            "fired_at, ctwa_clid FROM wa_capi_events ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    return [{"number": _pretty(r["wa_id"]), "wa_id": _digits(r["wa_id"]),
             "event": r["event_name"], "status": r["status"], "value": r["value"],
             "currency": r["currency"], "state": r["state"],
             "detail": (r["detail"] or "")[:120], "at": str(r["fired_at"] or "")[:16],
             "attributed": bool(r["ctwa_clid"])} for r in rows]


def summary(db_path, days=30, value_per_sale=16.0, currency="USD", phone_number_id=None):
    from . import intent

    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    con = _conn(db_path)
    try:
        if phone_number_id:
            contacts = [dict(r) for r in con.execute(
                "SELECT wa_id, product, last_inbound_at, created_at, via_phone_id "
                "FROM wa_contacts WHERE via_phone_id = ?", (str(phone_number_id),)).fetchall()]
        else:
            contacts = [dict(r) for r in con.execute(
                "SELECT wa_id, product, last_inbound_at, created_at, via_phone_id "
                "FROM wa_contacts").fetchall()]

        # One pass over messages rather than a query per contact. At this size either
        # works; at ten clients the per-contact version is the thing that falls over.
        msgs = {}
        for r in con.execute(
                "SELECT wa_id, direction, body, created_at FROM wa_messages ORDER BY id"):
            msgs.setdefault(r["wa_id"], []).append(dict(r))

        clicks = {}
        for r in con.execute(
                "SELECT wa_id, campaign_name, campaign_id FROM wa_ctwa_clicks"):
            clicks[r["wa_id"]] = dict(r)

        events = [dict(r) for r in con.execute(
            "SELECT event_name, status, COUNT(*) n FROM wa_capi_events "
            "GROUP BY event_name, status").fetchall()]
    finally:
        con.close()

    counts = {k: 0 for k in STATE_ORDER}
    flags = {"objection": 0, "needs_human": 0, "lost": 0, "disqualified": 0}
    rows, attention, per_campaign = [], [], {}
    dq_reasons = {}

    for c in contacts:
        thread = msgs.get(c["wa_id"], [])
        if not thread:
            continue
        last_at = thread[-1]["created_at"]
        if str(last_at) < since:
            continue

        state, evidence, needs_human = intent.classify(
            [{"direction": m["direction"], "body": m["body"]} for m in thread],
            wa_id=c["wa_id"])

        if state in counts:
            counts[state] += 1
        elif state == "LOST":
            flags["lost"] += 1
        elif state == "DISQUALIFIED":
            flags["disqualified"] += 1
            dq_reasons[evidence or "unknown"] = dq_reasons.get(evidence or "unknown", 0) + 1
        if needs_human:
            flags["needs_human"] += 1

        camp = (clicks.get(c["wa_id"]) or {}).get("campaign_name")
        if camp:
            b = per_campaign.setdefault(camp, {"convos": 0, "sales": 0})
            b["convos"] += 1
            if state == "COMMITTED":
                b["sales"] += 1

        inbound = [m for m in thread if m["direction"] == "in"]
        rows.append({
            "number": _pretty(c["wa_id"]),
            "wa_id": _digits(c["wa_id"]),
            "wa_link": "https://wa.me/" + _digits(c["wa_id"]),
            "state": state,
            "reason": evidence if state == "DISQUALIFIED" else None,
            "campaign": camp,
            "product": c.get("product"),
            "turns": len(inbound),
            "idle": _age(last_at),
            "last_at": str(last_at),
        })

        # The follow-up list: engaged, not finished, and gone quiet. This is the
        # single most commercially useful thing on the page, because every row is a
        # customer the merchant already paid to acquire.
        if needs_human or (state in ("QUALIFIED", "INTENT") and _stale(last_at, hours=4)):
            attention.append({
                "number": _pretty(c["wa_id"]),
                "wa_link": "https://wa.me/" + _digits(c["wa_id"]),
                "state": "NEEDS_HUMAN" if needs_human else state,
                "idle": _age(last_at),
                "campaign": camp,
            })

    total = sum(counts.values()) + flags["lost"]
    sales = counts["COMMITTED"]
    return {
        "total": total,
        "counts": counts,
        "flags": flags,
        "sales": sales,
        "value": round(sales * float(value_per_sale), 2),
        "currency": currency,
        "rows": sorted(rows, key=lambda r: r["last_at"], reverse=True)[:200],
        "attention": sorted(attention, key=lambda a: a["idle"])[:25],
        "campaigns": [
            {"name": k, "convos": v["convos"], "sales": v["sales"],
             "rate": round(100 * v["sales"] / v["convos"]) if v["convos"] else 0}
            for k, v in sorted(per_campaign.items(),
                               key=lambda kv: -kv[1]["convos"])],
        "events": events,
        "days": days,
        "disqualified_reasons": [{"reason": k, "n": v} for k, v in
                                 sorted(dq_reasons.items(), key=lambda kv: -kv[1])],
        "phone_number_id": phone_number_id,
    }


def _stale(ts, hours=4):
    try:
        then = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (datetime.utcnow() - then) > timedelta(hours=hours)
