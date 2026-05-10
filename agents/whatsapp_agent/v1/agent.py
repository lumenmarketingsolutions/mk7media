"""
WhatsApp Cloud API outreach agent for MK7 Media.

Two halves:
  1. Inbound webhook  — /webhooks/whatsapp (wired in app.py). Receives messages,
     runs the Claude-powered conversation, replies via the Graph API. Reply
     generation runs on a background thread so the webhook returns 200 fast
     (WhatsApp retries if you don't ack within ~5s, which would double-send).
  2. Outbound kickoff — start_outreach() opens a conversation with a lead who
     signed up on a form (cold or warm). WhatsApp requires the FIRST message to a
     number that hasn't messaged you to be an approved message template. Once the
     lead replies, the 24h customer-service window opens and the agent can
     free-text back and forth.

Number:           +1 623 512 6504  (MK7 Media)
Phone Number ID:  1082296231636502
WABA ID:          1457517218983357
App:              "MK7 messaging"  (App ID 2107067100091646)

Everything secret comes from env vars (set them in Railway):
  WHATSAPP_ACCESS_TOKEN     System User token (never expires) with scopes
                            whatsapp_business_messaging + whatsapp_business_management
  WHATSAPP_APP_SECRET       App secret for App ID 2107067100091646
                            (verifies the X-Hub-Signature-256 header on webhooks)
  WHATSAPP_VERIFY_TOKEN     any string; must match what you type into the Meta
                            webhook config "Verify token" field
  WHATSAPP_PHONE_NUMBER_ID  defaults to 1082296231636502
  WHATSAPP_WABA_ID          defaults to 1457517218983357
  ANTHROPIC_API_KEY         powers the agent's replies
  WHATSAPP_AGENT_MODEL      defaults to claude-opus-4-7 (set claude-sonnet-4-6 for
                            a cheaper high-volume bot)
  WHATSAPP_AUTO_REPLY       "0" disables auto-replies (agent just logs + notifies)
  WHATSAPP_DB_PATH          defaults to whatsapp.db
  WHATSAPP_NOTIFY_EMAILS    comma-separated; team gets handoff / failure emails
  RESEND_API_KEY            (shared with app.py) used to send those notify emails
"""

import os
import json
import time
import hmac
import hashlib
import sqlite3
import threading

import requests

# ── Config ──────────────────────────────────────────────────────────────────
GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "mk7-whatsapp-verify")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "1082296231636502")
WHATSAPP_WABA_ID = os.environ.get("WHATSAPP_WABA_ID", "1457517218983357")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WHATSAPP_AGENT_MODEL = os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")

WHATSAPP_AUTO_REPLY = os.environ.get("WHATSAPP_AUTO_REPLY", "1") not in ("0", "false", "False", "")
WHATSAPP_DB = os.environ.get("WHATSAPP_DB_PATH", "whatsapp.db")

_default_notify = "marykatezarehghazarian@gmail.com,mary@mk7media.com,kendall@lumenmarketing.co"
WHATSAPP_NOTIFY_EMAILS = [
    e.strip() for e in os.environ.get("WHATSAPP_NOTIFY_EMAILS", _default_notify).split(",") if e.strip()
]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Default outreach template — "lumen_inbound_followup" (English / `en`), one named
# body variable {{customer_name}}. Override the name via env if you add others.
DEFAULT_TEMPLATE = os.environ.get("WHATSAPP_DEFAULT_TEMPLATE", "lumen_inbound_followup")
DEFAULT_TEMPLATE_LANG = os.environ.get("WHATSAPP_DEFAULT_TEMPLATE_LANG", "en")

# History sent to the model per turn. WhatsApp threads are short; this is plenty.
MAX_HISTORY = 40
# Max characters in a single outbound WhatsApp text body (hard API limit is 4096).
MAX_OUTBOUND_CHARS = 4000

# A reply line ending with this token tells us the agent wants a human to take over.
# It's stripped before sending. (Cheap convention; can be upgraded to a tool later.)
HANDOFF_TOKEN = "[[HANDOFF]]"

OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "remove me", "stop messaging"}

# ── The agent's persona / brain — edit this to retune behaviour ──────────────
# Note: the outreach template ("lumen_inbound_followup") opens with "this is Kendall
# from MK7 Media", so the agent continues that conversation as Kendall. If you'd
# rather it speak as a team assistant, or hand straight off to the real Kendall after
# the first reply, change this prompt.
SYSTEM_PROMPT = """\
You are Kendall from MK7 Media, replying on WhatsApp. MK7 Media helps businesses \
grow through paid ads (mostly Meta — Instagram and Facebook), websites/landing \
pages, and automated follow-up systems. The people you're messaging either filled \
out a form on the MK7 Media site or got your opener ("Hi {name}, this is Kendall \
from MK7 Media... open to a quick conversation about what that could look like for \
you?") and replied. A few will message the number cold.

Your job:
1. Pick up the conversation and figure out where they're at.
2. Understand their situation: what's the business, what they're trying to grow, \
whether they're running ads now and how that's going, rough monthly budget, and \
how soon they want to move.
3. When there's a real fit, get them onto a quick call. That's the win — offer to \
find a time.
4. Be genuinely useful even to people who aren't a fit yet. Point them to what \
helps and leave the door open.

How you talk:
- Like a sharp, helpful person texting, not a marketer pitching. Short messages, \
usually one or two sentences. One question at a time. No bullet lists, no walls of \
text, no emoji spam.
- Direct and human. No corporate filler, no hype words, no em dashes, no \
"I hope this message finds you well." Don't oversell. Don't be pushy. If someone \
isn't interested, thank them and leave it open.
- You're Kendall from MK7 Media. Speak in the first person. You don't need to bring \
up that replies may be assisted, but never claim to be physically somewhere or \
doing something you're not, and never deny being automated if asked plainly — keep \
it honest and easy.
- Never invent specifics. Don't quote prices, guarantee results, or commit to \
deliverables or timelines. If they ask, say you'll walk through it on the call.
- If they want to book a call, ask to talk to a person, are clearly a strong fit, \
or are upset/confused in a way you shouldn't handle on autopilot, write your normal \
reply and then put this exact token on its own last line: %s
  (A teammate sees it and takes over. Never mention the token to the user.)
- If you're just acknowledging them and have nothing to add, keep it to one short \
human line.

Stay in the conversation. Keep it moving toward a call when a call makes sense.
""" % HANDOFF_TOKEN


# ── DB ───────────────────────────────────────────────────────────────────────
def _conn():
    conn = sqlite3.connect(WHATSAPP_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wa_contacts (
            wa_id           TEXT PRIMARY KEY,          -- E.164 without '+', e.g. 16235126504
            profile_name    TEXT,                      -- name from the WhatsApp profile
            lead_name       TEXT,                      -- name we had from the form (outbound)
            lead_business   TEXT,
            lead_source     TEXT,                      -- 'form_warm' | 'form_cold' | 'inbound' | ...
            status          TEXT DEFAULT 'active',     -- 'active' | 'handed_off' | 'opted_out'
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_inbound_at TIMESTAMP,
            last_outbound_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS wa_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id       TEXT NOT NULL,
            direction   TEXT NOT NULL,                 -- 'in' | 'out'
            msg_type    TEXT,                          -- 'text' | 'template' | 'image' | ...
            body        TEXT,
            wamid       TEXT,                          -- WhatsApp message id
            status      TEXT,                          -- delivery status for outbound
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


def _upsert_contact(wa_id, *, profile_name=None, lead_name=None, lead_business=None, lead_source=None):
    conn = _conn()
    conn.execute(
        "INSERT INTO wa_contacts (wa_id, profile_name, lead_name, lead_business, lead_source) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(wa_id) DO NOTHING",
        (wa_id, profile_name, lead_name, lead_business, lead_source),
    )
    # Fill in any fields we just learned without clobbering existing values.
    sets, params = [], []
    if profile_name:
        sets.append("profile_name = COALESCE(NULLIF(profile_name, ''), ?)"); params.append(profile_name)
    if lead_name:
        sets.append("lead_name = COALESCE(NULLIF(lead_name, ''), ?)"); params.append(lead_name)
    if lead_business:
        sets.append("lead_business = COALESCE(NULLIF(lead_business, ''), ?)"); params.append(lead_business)
    if lead_source:
        sets.append("lead_source = COALESCE(NULLIF(lead_source, ''), ?)"); params.append(lead_source)
    if sets:
        params.append(wa_id)
        conn.execute(f"UPDATE wa_contacts SET {', '.join(sets)} WHERE wa_id = ?", params)
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


def _record_message(wa_id, direction, msg_type, body, wamid=None, status=None):
    """Insert a message. Returns True if newly inserted, False if it was a duplicate wamid."""
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
        "SELECT direction, msg_type, body FROM wa_messages WHERE wa_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (wa_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def recent_conversations(limit=50):
    """For the admin viewer: contacts ordered by most recent activity, with last message."""
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


# ── Webhook verification ─────────────────────────────────────────────────────
def verify_webhook(args):
    """GET handshake. Return the challenge string to echo back, or None to 403."""
    if args.get("hub.mode") == "subscribe" and args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return args.get("hub.challenge", "")
    return None


def verify_signature(raw_body, signature_header):
    """Validate X-Hub-Signature-256: 'sha256=<hex>'. If no app secret is configured,
    accept (so the webhook works before WHATSAPP_APP_SECRET is set) but log it."""
    if not WHATSAPP_APP_SECRET:
        print("[whatsapp] WARNING: WHATSAPP_APP_SECRET not set — skipping signature check")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WHATSAPP_APP_SECRET.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


# ── Sending ──────────────────────────────────────────────────────────────────
def _graph_post(payload):
    if not WHATSAPP_ACCESS_TOKEN:
        print("[whatsapp] WARNING: WHATSAPP_ACCESS_TOKEN not set — cannot send")
        return None
    url = f"{GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            print(f"[whatsapp] send failed {r.status_code}: {json.dumps(data)[:500]}")
            return None
        return data
    except Exception as e:
        print(f"[whatsapp] send exception: {e}")
        return None


def send_text(to_wa_id, body):
    """Send a free-text WhatsApp message. Only valid inside the 24h customer-service
    window (i.e. after the contact has messaged you). Returns the Graph response or None."""
    body = (body or "").strip()
    if not body:
        return None
    if len(body) > MAX_OUTBOUND_CHARS:
        body = body[: MAX_OUTBOUND_CHARS - 1].rstrip() + "…"
    data = _graph_post(
        {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }
    )
    wamid = None
    if data and data.get("messages"):
        wamid = data["messages"][0].get("id")
    _record_message(to_wa_id, "out", "text", body, wamid=wamid, status="sent" if data else "failed")
    return data


def send_template(to_wa_id, template_name, lang_code="en_US", body_params=None):
    """Send an approved message template — the only way to start a conversation with a
    number that hasn't messaged you.

    `body_params` may be:
      - a list  -> positional placeholders {{1}}, {{2}}, ... in order
      - a dict  -> named placeholders {{customer_name}}, ... (keys = the names, no braces)
      - None    -> template has no body variables
    """
    components = []
    if isinstance(body_params, dict) and body_params:
        components.append(
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "parameter_name": str(k), "text": str(v)} for k, v in body_params.items()
                ],
            }
        )
    elif body_params:  # list / tuple -> positional
        components.append(
            {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in body_params]}
        )
    data = _graph_post(
        {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "template",
            "template": {"name": template_name, "language": {"code": lang_code}, "components": components},
        }
    )
    wamid = None
    if data and data.get("messages"):
        wamid = data["messages"][0].get("id")
    label = f"[template:{template_name}]" + (f" {body_params}" if body_params else "")
    _record_message(to_wa_id, "out", "template", label, wamid=wamid, status="sent" if data else "failed")
    return data


def start_outreach(to_wa_id, *, template_name, lang_code="en_US", body_params=None,
                   lead_name=None, lead_business=None, lead_source="form"):
    """Open a conversation with a form lead: register the contact and send the kickoff template."""
    to_wa_id = "".join(ch for ch in str(to_wa_id) if ch.isdigit())
    _upsert_contact(to_wa_id, lead_name=lead_name, lead_business=lead_business, lead_source=lead_source)
    return send_template(to_wa_id, template_name, lang_code=lang_code, body_params=body_params)


# ── Notifications ────────────────────────────────────────────────────────────
def _notify_team(subject, html):
    if not RESEND_API_KEY or not WHATSAPP_NOTIFY_EMAILS:
        return
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "MK7 WhatsApp Agent <notifications@lumenmarketing.co>",
                "to": WHATSAPP_NOTIFY_EMAILS,
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[whatsapp] notify failed: {e}")


def _conversation_html(wa_id, max_msgs=20):
    rows = conversation(wa_id, limit=max_msgs)
    lines = []
    for r in rows:
        who = "Lead" if r["direction"] == "in" else "Agent"
        lines.append(f'<p style="margin:6px 0;"><strong>{who}:</strong> {(r["body"] or "")}</p>')
    return "".join(lines) or "<p>(no messages)</p>"


# ── Inbound handling ─────────────────────────────────────────────────────────
def handle_webhook(payload):
    """Parse a WhatsApp webhook payload. Stores inbound messages synchronously and
    spawns a background thread to generate + send each reply (keeps the HTTP ack fast)."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}

            # Delivery / read receipts for our outbound messages.
            for st in value.get("statuses", []) or []:
                wamid, status = st.get("id"), st.get("status")
                if wamid and status:
                    conn = _conn()
                    conn.execute("UPDATE wa_messages SET status = ? WHERE wamid = ?", (status, wamid))
                    conn.commit()
                    conn.close()

            # Map wa_id -> profile name from the contacts block.
            profiles = {}
            for c in value.get("contacts", []) or []:
                wa_id = c.get("wa_id")
                name = (c.get("profile") or {}).get("name")
                if wa_id:
                    profiles[wa_id] = name

            for msg in value.get("messages", []) or []:
                _handle_inbound_message(msg, profiles)


def _extract_text(msg):
    """Pull a usable text body out of any inbound message type (None if it has none)."""
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

    _upsert_contact(wa_id, profile_name=profiles.get(wa_id), lead_source="inbound")

    text = _extract_text(msg)
    msg_type = msg.get("type") or "unknown"
    body = text if text is not None else f"[{msg_type} message]"

    is_new = _record_message(wa_id, "in", msg_type, body, wamid=wamid)
    if not is_new:
        return  # Meta re-delivered a message we already processed — don't reply twice.

    contact = get_contact(wa_id) or {}
    status = contact.get("status", "active")

    # Opt-out handling.
    if text and text.strip().lower() in OPT_OUT_WORDS:
        set_contact_status(wa_id, "opted_out")
        send_text(wa_id, "Done, you won't hear from us here again. If you ever want to reconnect, just message this number.")
        return

    if status == "opted_out":
        return  # they asked us to stop; stay quiet.

    if status == "handed_off":
        # A human owns this thread now — just make sure they see the new message.
        _notify_team(
            f"WhatsApp (handed-off) — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    if text is None:
        # Non-text inbound (image / audio / location / etc.) — the agent can't read it.
        send_text(wa_id, "Got it. I can't open that here, but Marykate will take a look. Anything you want to add in a quick message?")
        _notify_team(
            f"WhatsApp — non-text message from {contact.get('profile_name') or wa_id}",
            f"<p>Type: {msg_type}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    if not WHATSAPP_AUTO_REPLY:
        _notify_team(
            f"WhatsApp — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    # Generate + send the reply off the request thread so the webhook acks fast.
    threading.Thread(target=_reply_async, args=(wa_id,), daemon=True).start()


def _reply_async(wa_id):
    try:
        reply, wants_handoff = generate_reply(wa_id)
        if not reply:
            send_text(wa_id, "Thanks for the reply. Marykate will follow up with you here shortly.")
            return
        send_text(wa_id, reply)
        if wants_handoff:
            set_contact_status(wa_id, "handed_off")
            contact = get_contact(wa_id) or {}
            _notify_team(
                f"WhatsApp — HANDOFF needed: {contact.get('profile_name') or contact.get('lead_name') or wa_id}",
                f"<p>The agent flagged this conversation for a human. Jump in on WhatsApp "
                f"(<a href='https://wa.me/{wa_id}'>wa.me/{wa_id}</a>).</p><hr>{_conversation_html(wa_id)}",
            )
    except Exception as e:
        print(f"[whatsapp] reply error for {wa_id}: {e}")
        try:
            send_text(wa_id, "Thanks — Marykate will follow up with you here shortly.")
        except Exception:
            pass


def generate_reply(wa_id):
    """Ask Claude for the next message in this conversation.
    Returns (reply_text_or_None, wants_handoff_bool)."""
    if not ANTHROPIC_API_KEY:
        print("[whatsapp] ANTHROPIC_API_KEY not set — cannot generate replies")
        return None, False
    try:
        import anthropic
    except ImportError:
        print("[whatsapp] anthropic package not installed — cannot generate replies")
        return None, False

    contact = get_contact(wa_id) or {}
    history = _history(wa_id)
    if not history:
        return None, False

    # Build the message list from the stored conversation. inbound -> user, outbound -> assistant.
    messages = []
    for h in history:
        role = "user" if h["direction"] == "in" else "assistant"
        content = (h["body"] or "").strip()
        if not content:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + content
        else:
            messages.append({"role": role, "content": content})
    # The model needs the conversation to start with a user turn. If the first stored
    # message is one we sent (the kickoff template), prepend a short context line.
    lead_bits = []
    if contact.get("lead_name"):
        lead_bits.append(f"name {contact['lead_name']}")
    if contact.get("profile_name") and contact.get("profile_name") != contact.get("lead_name"):
        lead_bits.append(f"WhatsApp profile name {contact['profile_name']}")
    if contact.get("lead_business"):
        lead_bits.append(f"business {contact['lead_business']}")
    src = contact.get("lead_source") or ""
    context_line = ""
    if src.startswith("form"):
        context_line = "(This person filled out a form on the MK7 Media site"
        context_line += (" — " + ", ".join(lead_bits)) if lead_bits else ""
        context_line += ". You reached out first; this is their reply.)"
    elif lead_bits:
        context_line = "(" + ", ".join(lead_bits) + ".)"

    if messages and messages[0]["role"] == "assistant":
        messages.insert(0, {"role": "user", "content": context_line or "(start of conversation)"})

    # Static system prompt (cache breakpoint) + a small dynamic block after it.
    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    if context_line:
        system_blocks.append({"type": "text", "text": "Context for this conversation: " + context_line})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        resp = client.messages.create(
            model=WHATSAPP_AGENT_MODEL,
            max_tokens=1024,
            system=system_blocks,
            messages=messages,
        )
    except Exception as e:
        print(f"[whatsapp] anthropic call failed: {e}")
        return None, False

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        return None, False

    wants_handoff = False
    if HANDOFF_TOKEN in text:
        wants_handoff = True
        # Strip the token (and any now-empty trailing line) before sending.
        text = text.replace(HANDOFF_TOKEN, "").rstrip()
    return (text or None), wants_handoff
