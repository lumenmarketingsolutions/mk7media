"""
FGC Agent V1.00 — Feels Good Club WhatsApp sales agent (+961 81 873 275).

COEXISTENCE profile: unlike the MK7 number (cloud-only), the FGC number stays
live in the WhatsApp Business app on MK's phone via Meta's coexistence mode.
That changes two things about how this agent behaves:

  1. Echo handling — when MK replies to a customer from the phone app, the
     webhook delivers an echo of her message. The agent records it and SNOOZES
     itself on that conversation for FGC_HUMAN_SNOOZE_HOURS (default 4h) so it
     never talks over her. Her sending a message from the app IS the takeover
     signal — no admin portal needed.
  2. Humanized pacing — replies go out after a short randomized delay
     (FGC_REPLY_DELAY, default "20-60" seconds). This number was restricted by
     WhatsApp once (08.04, spam-pattern suspicion on a fresh number); instant
     robotic replies at ad-driven volume are exactly the pattern to avoid.

Wiring: app.py routes inbound webhook events to this module when
value.metadata.phone_number_id == FGC_WHATSAPP_PHONE_NUMBER_ID. Until that env
var is set on Railway (it's known only after coexistence onboarding), this
module receives nothing and the deploy is a no-op.

Env vars (all optional until go-live):
  FGC_WHATSAPP_PHONE_NUMBER_ID  the number's ID after coexistence onboarding
  FGC_WHATSAPP_WABA_ID          defaults to 884373514193136 (Feels Good Club WABA)
  FGC_DB_PATH                   defaults to fgc_whatsapp.db
  FGC_AUTO_REPLY                "0" disables auto-replies (log + notify only)
  FGC_REPLY_DELAY               "min-max" seconds, default "20-60"
  FGC_HUMAN_SNOOZE_HOURS        default 4
  FGC_NOTIFY_EMAILS             defaults to MK + Kendall
Shared with the MK7 profile (already set on Railway):
  WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN,
  ANTHROPIC_API_KEY, RESEND_API_KEY
  WHATSAPP_AGENT_MODEL          defaults to claude-opus-4-7
"""

import os
import json
import time
import hmac
import random
import hashlib
import sqlite3
import threading

import requests

# ── Config ──────────────────────────────────────────────────────────────────
GRAPH_API_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "mk7-whatsapp-verify")

# The FGC number's phone-number ID (default = the live value, so routing works
# without any Railway config; env override kept for emergencies/re-onboarding).
FGC_PHONE_NUMBER_ID = os.environ.get("FGC_WHATSAPP_PHONE_NUMBER_ID", "1164242853447974")
FGC_WABA_ID = os.environ.get("FGC_WHATSAPP_WABA_ID", "884373514193136")
FGC_BUSINESS_NUMBER = "".join(ch for ch in os.environ.get("FGC_WHATSAPP_BUSINESS_NUMBER", "96181873275") if ch.isdigit())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AGENT_MODEL = os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")

# SHADOW MODE BY DEFAULT: the agent logs + emails every conversation but stays
# silent until FGC_AUTO_REPLY=1 is explicitly set on Railway (Kendall flips it
# after reviewing shadow output + confirming the whitening-strips pricing).
AUTO_REPLY = os.environ.get("FGC_AUTO_REPLY", "0") not in ("0", "false", "False", "")
DB_PATH = os.environ.get("FGC_DB_PATH", "fgc_whatsapp.db")

_default_notify = "marykatezarehghazarian@gmail.com,kendall@lumenmarketing.co"
NOTIFY_EMAILS = [e.strip() for e in os.environ.get("FGC_NOTIFY_EMAILS", _default_notify).split(",") if e.strip()]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Humanized reply delay (seconds): "min-max".
try:
    _lo, _hi = os.environ.get("FGC_REPLY_DELAY", "20-60").split("-")
    REPLY_DELAY = (max(0, int(_lo)), max(int(_lo), int(_hi)))
except Exception:
    REPLY_DELAY = (20, 60)

HUMAN_SNOOZE_HOURS = float(os.environ.get("FGC_HUMAN_SNOOZE_HOURS", "4"))

MAX_HISTORY = 40
MAX_OUTBOUND_CHARS = 4000
HANDOFF_TOKEN = "[[HANDOFF]]"
OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "remove me", "stop messaging"}

# ── The agent's persona / brain ──────────────────────────────────────────────
# PRODUCT FACTS: keep this block current — it is the agent's entire catalog
# knowledge. Prices/offers marked TODO must be confirmed by Kendall/MK before
# go-live (FGC_AUTO_REPLY=0 until then keeps the agent in log-only mode).
SYSTEM_PROMPT = """\
You are the Feels Good Club assistant, replying on WhatsApp. Feels Good Club \
(feelsgoodclub.com) is a Lebanese online store for feel-good self-care products. \
People message this number after tapping an Instagram/Facebook ad or visiting \
the site. Most want prices, delivery info, or to place an order. Your job is to \
answer fast, warmly, and close the order in the chat.

PRODUCTS (your entire catalog knowledge — never invent products or claims):
1. Migraine Relief Cap — $24.99, with a $5 discount applied automatically at \
checkout on the site (so $19.99). Slips on like a beanie, cold-therapy relief \
for migraines and headaches. Drug free, reusable for years, 30-day money-back \
promise. Comes with a free bonus: the "10 Ways to Stop Getting Migraines" \
guide (PDF), included with every order.
2. Teeth Whitening Strips — $12 per kit (28 enamel-safe strips, 14 \
treatments, visibly whiter in 14 days, zero sensitivity). In chat orders the \
usual all-in price is $15 including delivery.

ORDERING & DELIVERY:
- Cash on delivery across Lebanon. They pay when the order arrives. \
Delivery takes 2-3 days anywhere in Lebanon, and delivery is free.
- To place an order in chat you need: full name, phone number, delivery \
address (city + street/building), which product and how many. Read the order \
back to them to confirm, tell them delivery is 2-3 days and they pay cash on \
arrival, then use the handoff token so a teammate books it in.
- They can also order themselves at feelsgoodclub.com — offer the link when \
it's easier for them.

HOW YOU TALK:
- Like a friendly, quick person texting from a small brand. Short messages, \
one or two sentences. One question at a time. No walls of text, no emoji spam \
(one emoji now and then is fine).
- English only. Never reply in Arabic script, even if they write in Arabic — \
if they write in Arabic, reply in simple, easy English.
- Direct and human. No hype, no pressure, no "dear customer", no em dashes. \
Never say "lock in".
- Never invent discounts, delivery promises, medical claims, or stock levels. \
The cap relieves and soothes — it is not a cure and you never promise it \
treats or cures anything. If they ask if it works with their medication or \
condition: it's drug-free and worn on the head, but for medical questions \
they should ask their doctor.
- If someone just reacts to a message (thumbs-up, heart) with no words, you \
generally don't need to say anything back.

WHEN TO HAND OFF (write your normal reply, then put this exact token on its \
own last line: %s — a teammate sees it and takes over; never mention the token):
- An order is confirmed and ready to book in.
- They ask about anything not in your product facts.
- A complaint, a return/refund request, a delivery problem, or anyone upset.
- Wholesale, collaboration, influencer, or press inquiries.
- Anything medical beyond "is it drug-free".

Keep the conversation moving toward the order, but never pushy. If they're \
just browsing, answer well and leave the door open.
""" % HANDOFF_TOKEN


# ── DB ───────────────────────────────────────────────────────────────────────
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wa_contacts (
            wa_id           TEXT PRIMARY KEY,
            profile_name    TEXT,
            status          TEXT DEFAULT 'active',     -- 'active' | 'handed_off' | 'opted_out'
            human_snooze_until REAL,                   -- unix ts; agent silent until then
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_inbound_at TIMESTAMP,
            last_outbound_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS wa_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id       TEXT NOT NULL,
            direction   TEXT NOT NULL,                 -- 'in' | 'out' | 'out_app' (MK from phone)
            msg_type    TEXT,
            body        TEXT,
            wamid       TEXT,
            status      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_wa_messages_waid ON wa_messages(wa_id, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_messages_wamid
            ON wa_messages(wamid) WHERE wamid IS NOT NULL;
        """
    )
    conn.commit()
    conn.close()


init_db()


def _upsert_contact(wa_id, *, profile_name=None):
    conn = _conn()
    conn.execute("INSERT INTO wa_contacts (wa_id, profile_name) VALUES (?, ?) ON CONFLICT(wa_id) DO NOTHING",
                 (wa_id, profile_name))
    if profile_name:
        conn.execute(
            "UPDATE wa_contacts SET profile_name = COALESCE(NULLIF(profile_name, ''), ?) WHERE wa_id = ?",
            (profile_name, wa_id))
    conn.commit()
    conn.close()


def get_contact(wa_id):
    conn = _conn()
    row = conn.execute("SELECT * FROM wa_contacts WHERE wa_id = ?", (wa_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_contact_status(wa_id, status):
    conn = _conn()
    conn.execute("UPDATE wa_contacts SET status = ? WHERE wa_id = ?", (status, wa_id))
    conn.commit()
    conn.close()


def snooze_contact(wa_id, hours=HUMAN_SNOOZE_HOURS):
    """MK replied from the phone app — the agent stays out of this conversation
    until the snooze expires (each new app reply re-arms it)."""
    conn = _conn()
    conn.execute("UPDATE wa_contacts SET human_snooze_until = ? WHERE wa_id = ?",
                 (time.time() + hours * 3600, wa_id))
    conn.commit()
    conn.close()


def _is_snoozed(contact):
    su = (contact or {}).get("human_snooze_until")
    return bool(su) and float(su) > time.time()


def _record_message(wa_id, direction, msg_type, body, wamid=None, status=None):
    conn = _conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO wa_messages (wa_id, direction, msg_type, body, wamid, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (wa_id, direction, msg_type, body, wamid, status),
    )
    inserted = cur.rowcount > 0
    if inserted:
        col = "last_inbound_at" if direction == "in" else "last_outbound_at"
        conn.execute(f"UPDATE wa_contacts SET {col} = CURRENT_TIMESTAMP WHERE wa_id = ?", (wa_id,))
    conn.commit()
    conn.close()
    return inserted


def _history(wa_id, limit=MAX_HISTORY):
    conn = _conn()
    rows = conn.execute(
        "SELECT direction, msg_type, body FROM wa_messages WHERE wa_id = ? ORDER BY id DESC LIMIT ?",
        (wa_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def recent_conversations(limit=50):
    conn = _conn()
    rows = conn.execute(
        """
        SELECT c.*,
               (SELECT body FROM wa_messages m WHERE m.wa_id = c.wa_id ORDER BY m.id DESC LIMIT 1) AS last_body,
               (SELECT direction FROM wa_messages m WHERE m.wa_id = c.wa_id ORDER BY m.id DESC LIMIT 1) AS last_dir,
               (SELECT COUNT(*) FROM wa_messages m WHERE m.wa_id = c.wa_id) AS msg_count
        FROM wa_contacts c
        ORDER BY COALESCE(c.last_inbound_at, c.last_outbound_at, c.created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def conversation(wa_id, limit=200):
    conn = _conn()
    rows = conn.execute(
        "SELECT direction, msg_type, body, status, created_at FROM wa_messages "
        "WHERE wa_id = ? ORDER BY id ASC LIMIT ?",
        (wa_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Webhook verification (same app-level handshake as the MK7 profile) ───────
def verify_webhook(args):
    if args.get("hub.mode") == "subscribe" and args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return args.get("hub.challenge", "")
    return None


def verify_signature(raw_body, signature_header):
    """Validate against the FGC app's secret (Lumen Master Connect — the app the
    FGC number's events are signed by). Used as the SECOND check in app.py's
    webhook route (after the MK7 app secret), so unlike the MK7 profile this one
    returns False when unconfigured — a missing secret must not accept traffic."""
    secret = os.environ.get("FGC_WHATSAPP_APP_SECRET", "")
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


# ── Sending ──────────────────────────────────────────────────────────────────
def _graph_post(payload):
    if not WHATSAPP_ACCESS_TOKEN or not FGC_PHONE_NUMBER_ID:
        print("[fgc-wa] WARNING: token or FGC_WHATSAPP_PHONE_NUMBER_ID not set — cannot send")
        return None
    url = f"{GRAPH_BASE}/{FGC_PHONE_NUMBER_ID}/messages"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            print(f"[fgc-wa] send failed {r.status_code}: {json.dumps(data)[:500]}")
            return None
        return data
    except Exception as e:
        print(f"[fgc-wa] send exception: {e}")
        return None


def send_text(to_wa_id, body):
    body = (body or "").strip()
    if not body:
        return None
    if len(body) > MAX_OUTBOUND_CHARS:
        body = body[: MAX_OUTBOUND_CHARS - 1].rstrip() + "…"
    data = _graph_post(
        {"messaging_product": "whatsapp", "to": to_wa_id, "type": "text",
         "text": {"body": body, "preview_url": False}}
    )
    wamid = None
    if data and data.get("messages"):
        wamid = data["messages"][0].get("id")
    _record_message(to_wa_id, "out", "text", body, wamid=wamid, status="sent" if data else "failed")
    print(f"[fgc-wa] send_text {to_wa_id}: {('sent wamid=' + str(wamid)) if data else 'FAILED'} body={body[:60]!r}")
    return data


# ── Notifications ────────────────────────────────────────────────────────────
def _notify_team(subject, html):
    if not RESEND_API_KEY or not NOTIFY_EMAILS:
        return
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "FGC WhatsApp Agent <notifications@lumenmarketing.co>",
                  "to": NOTIFY_EMAILS, "subject": subject, "html": html},
            timeout=10,
        )
    except Exception as e:
        print(f"[fgc-wa] notify failed: {e}")


def _conversation_html(wa_id, max_msgs=20):
    rows = conversation(wa_id, limit=max_msgs)
    lines = []
    for r in rows:
        who = {"in": "Customer", "out": "Agent", "out_app": "MK (app)"}.get(r["direction"], r["direction"])
        lines.append(f'<p style="margin:6px 0;"><strong>{who}:</strong> {(r["body"] or "")}</p>')
    return "".join(lines) or "<p>(no messages)</p>"


def _last_inbound_body(wa_id):
    conn = _conn()
    row = conn.execute(
        "SELECT body FROM wa_messages WHERE wa_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
        (wa_id,),
    ).fetchone()
    conn.close()
    return (row["body"] if row else "") or ""


# ── Inbound handling ─────────────────────────────────────────────────────────
def is_fgc_event(value):
    """True when this webhook change belongs to the FGC number. Dormant (always
    False) until FGC_WHATSAPP_PHONE_NUMBER_ID is configured."""
    if not FGC_PHONE_NUMBER_ID:
        return False
    meta = value.get("metadata") or {}
    return str(meta.get("phone_number_id") or "") == str(FGC_PHONE_NUMBER_ID)


def handle_webhook(payload):
    """Handle a webhook payload (only FGC-number changes; app.py routes us)."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            if not is_fgc_event(value):
                continue

            # Delivery/read receipts for our outbound messages.
            for st in value.get("statuses", []) or []:
                wamid, status = st.get("id"), st.get("status")
                if wamid and status:
                    conn = _conn()
                    conn.execute("UPDATE wa_messages SET status = ? WHERE wamid = ?", (status, wamid))
                    conn.commit()
                    conn.close()

            # COEXISTENCE: echoes of messages MK sent from the phone app.
            # (Meta delivers these as message_echoes / smb_message_echoes.)
            for echo in (value.get("message_echoes") or value.get("smb_message_echoes") or []):
                to_id = echo.get("to") or ""
                if not to_id:
                    continue
                body = _extract_text(echo)
                _upsert_contact(to_id)
                _record_message(to_id, "out_app", echo.get("type") or "text",
                                body if body is not None else f"[{echo.get('type')} message]",
                                wamid=echo.get("id"))
                snooze_contact(to_id)
                print(f"[fgc-wa] app echo -> {to_id}: MK replied from phone, snoozing agent {HUMAN_SNOOZE_HOURS}h")

            profiles = {}
            for c in value.get("contacts", []) or []:
                wa_id = c.get("wa_id")
                name = (c.get("profile") or {}).get("name")
                if wa_id:
                    profiles[wa_id] = name

            for msg in value.get("messages", []) or []:
                _handle_inbound_message(msg, profiles)


def _extract_text(msg):
    t = msg.get("type")
    if t == "text":
        return (msg.get("text") or {}).get("body", "")
    if t == "button":
        return (msg.get("button") or {}).get("text", "")
    if t == "interactive":
        inter = msg.get("interactive") or {}
        if inter.get("type") == "button_reply":
            return (inter.get("button_reply") or {}).get("title", "")
        if inter.get("type") == "list_reply":
            return (inter.get("list_reply") or {}).get("title", "")
    return None


def _handle_inbound_message(msg, profiles):
    wa_id = msg.get("from")
    wamid = msg.get("id")
    if not wa_id:
        return

    _upsert_contact(wa_id, profile_name=profiles.get(wa_id))

    text = _extract_text(msg)
    msg_type = msg.get("type") or "unknown"
    body = text if text is not None else f"[{msg_type} message]"

    if msg_type in ("reaction", "system", "unsupported", "ephemeral"):
        if msg_type == "reaction":
            emoji = (msg.get("reaction") or {}).get("emoji", "")
            body = f"[reacted {emoji}]".strip()
        _record_message(wa_id, "in", msg_type, body, wamid=wamid)
        return

    is_new = _record_message(wa_id, "in", msg_type, body, wamid=wamid)
    if not is_new:
        return

    contact = get_contact(wa_id) or {}
    status = contact.get("status", "active")

    if text and text.strip().lower() in OPT_OUT_WORDS:
        set_contact_status(wa_id, "opted_out")
        send_text(wa_id, "Done, you won't hear from us here again. If you ever change your mind, just message this number.")
        return

    if status == "opted_out":
        return

    if _is_snoozed(contact) or status == "handed_off":
        # MK owns this thread (she replied from the app recently, or the agent
        # handed off). Stay quiet — she sees the message in her app anyway.
        print(f"[fgc-wa] inbound {wa_id}: {body[:60]!r} — human owns thread (snoozed/handed_off), agent silent")
        return

    if text is None:
        # Images are common in shopping chats — acknowledge without pretending to see it.
        send_text(wa_id, "Got your message! I can't open that on my end. Could you type it out for me real quick?")
        _notify_team(
            f"FGC WhatsApp — non-text message from {contact.get('profile_name') or wa_id}",
            f"<p>Type: {msg_type}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    if not AUTO_REPLY:
        print(f"[fgc-wa] inbound {wa_id}: {body[:60]!r} — auto-reply disabled, notify only")
        _notify_team(
            f"FGC WhatsApp — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    print(f"[fgc-wa] inbound {wa_id}: {body[:60]!r} (status={status}) — spawning reply")
    threading.Thread(target=_reply_async, args=(wa_id, wamid), daemon=True).start()


def _reply_async(wa_id, trigger_wamid=None):
    try:
        # Humanized pacing: wait, then re-check that MK hasn't jumped in and the
        # customer hasn't sent something newer (people often send 3 messages in
        # a row — reply once to the latest, not three times).
        time.sleep(random.uniform(*REPLY_DELAY))
        contact = get_contact(wa_id) or {}
        if _is_snoozed(contact) or contact.get("status") in ("handed_off", "opted_out"):
            print(f"[fgc-wa] _reply_async {wa_id}: human took over during delay, standing down")
            return
        if trigger_wamid:
            conn = _conn()
            row = conn.execute(
                "SELECT wamid FROM wa_messages WHERE wa_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
                (wa_id,),
            ).fetchone()
            conn.close()
            if row and row["wamid"] and row["wamid"] != trigger_wamid:
                print(f"[fgc-wa] _reply_async {wa_id}: newer inbound arrived, this thread stands down")
                return

        reply, wants_handoff = generate_reply(wa_id)
        if reply:
            send_text(wa_id, reply)
        if wants_handoff:
            set_contact_status(wa_id, "handed_off")
            label = (get_contact(wa_id) or {}).get("profile_name") or ("+" + wa_id)
            last_in = _last_inbound_body(wa_id)
            summary = f'{label} — "{last_in[:140]}"' if last_in else label
            _notify_team(
                f"FGC WhatsApp — MK, this one's yours: {summary}",
                f"<p>The agent flagged this conversation for a human (order to book, "
                f"or a question it shouldn't answer). Open WhatsApp on the FGC phone to take over — "
                f"the chat is with <a href='https://wa.me/{wa_id}'>+{wa_id}</a>. "
                f"When you reply from the app, the agent automatically stays out of that chat.</p>"
                f"<hr>{_conversation_html(wa_id)}",
            )
    except Exception as e:
        print(f"[fgc-wa] reply error for {wa_id}: {repr(e)}")


def generate_reply(wa_id):
    if not ANTHROPIC_API_KEY:
        print("[fgc-wa] ANTHROPIC_API_KEY not set — cannot generate replies")
        return None, False
    try:
        import anthropic
    except ImportError:
        print("[fgc-wa] anthropic package not installed")
        return None, False

    contact = get_contact(wa_id) or {}
    history = _history(wa_id)
    if not history:
        return None, False

    messages = []
    for h in history:
        # MK's app replies count as assistant turns — the model sees the whole thread.
        role = "user" if h["direction"] == "in" else "assistant"
        content = (h["body"] or "").strip()
        if not content:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + content
        else:
            messages.append({"role": role, "content": content})

    context_line = ""
    if contact.get("profile_name"):
        context_line = f"(The customer's WhatsApp profile name is {contact['profile_name']}. They likely came from an Instagram or Facebook ad.)"

    if messages and messages[0]["role"] == "assistant":
        messages.insert(0, {"role": "user", "content": context_line or "(start of conversation)"})

    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    if context_line:
        system_blocks.append({"type": "text", "text": context_line})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        resp = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=1024,
            system=system_blocks,
            messages=messages,
        )
    except Exception as e:
        print(f"[fgc-wa] anthropic call FAILED for {wa_id}: {repr(e)}")
        return None, False

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        return None, False

    wants_handoff = False
    if HANDOFF_TOKEN in text:
        wants_handoff = True
        text = text.replace(HANDOFF_TOKEN, "").rstrip()
    return (text or None), wants_handoff
