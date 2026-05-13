# Profile: lumen_lebanon_website_leads — "Lumen Lebanon Agent - Website Leads".
# Currently configured as LAYLA — a sales qualification agent for Lumen Marketing,
# talking to Lebanese business owners who hit a WhatsApp link from a Lumen ad.
# Goal: qualify fast (≤3 exchanges), book onto a call, hand off to the human team.
# See profiles/lumen_lebanon_website_leads/README.md for the full behavioural spec.
# Started as a verbatim copy of profiles/mk7_agent_v1_00/agent.py. Edit freely;
# the MK7 V1.00 folder is the preserved original — don't touch that one.
"""
WhatsApp Cloud API outreach agent for Lumen Marketing (Layla profile).

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
import re
import json
import time
import hmac
import random
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
# The display phone number (digits only) — used to build wa.me/<number> links.
WHATSAPP_BUSINESS_NUMBER = "".join(ch for ch in os.environ.get("WHATSAPP_BUSINESS_NUMBER", "16235126504") if ch.isdigit())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WHATSAPP_AGENT_MODEL = os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")

WHATSAPP_AUTO_REPLY = os.environ.get("WHATSAPP_AUTO_REPLY", "1") not in ("0", "false", "False", "")
WHATSAPP_DB = os.environ.get("WHATSAPP_DB_PATH", "whatsapp.db")

# Layla notifications go to KENDALL ONLY while we test. Marykate doesn't know
# about the Lumen Lebanon agent yet — Kendall will brief her once it's ready.
# We intentionally ignore the WHATSAPP_NOTIFY_EMAILS env var here so a stale
# Railway value can't accidentally CC her. Reverting = put the env-var read
# back, or change the literal list. (MK7 V1.00 profile is unaffected.)
WHATSAPP_NOTIFY_EMAILS = ["kendall@lumenmarketing.co"]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Default outreach template — "lumen_inbound_followup" (English / `en`), one named
# body variable {{customer_name}}. Override the name via env if you add others.
DEFAULT_TEMPLATE = os.environ.get("WHATSAPP_DEFAULT_TEMPLATE", "lumen_inbound_followup")
DEFAULT_TEMPLATE_LANG = os.environ.get("WHATSAPP_DEFAULT_TEMPLATE_LANG", "en")

# Handoff alert: when the agent flags [[HANDOFF]] we email the team and also ping a
# WhatsApp number (the setter). WhatsApp only allows free-text to a number that's
# messaged us in the last 24h, so a reliable alert needs an approved (Utility)
# template with one body variable {{1}} = the summary line. If WHATSAPP_HANDOFF_TEMPLATE
# is set we use that (works anytime); otherwise we try a plain text message (only lands
# if there's an open 24h window with the setter). The email always goes out regardless.
WHATSAPP_HANDOFF_NUMBER = "".join(ch for ch in os.environ.get("WHATSAPP_HANDOFF_NUMBER", "") if ch.isdigit())
WHATSAPP_HANDOFF_TEMPLATE = os.environ.get("WHATSAPP_HANDOFF_TEMPLATE", "")
WHATSAPP_HANDOFF_TEMPLATE_LANG = os.environ.get("WHATSAPP_HANDOFF_TEMPLATE_LANG", "en")

# History sent to the model per turn. WhatsApp threads are short; this is plenty.
MAX_HISTORY = 40
# Max characters in a single outbound WhatsApp text body (hard API limit is 4096).
MAX_OUTBOUND_CHARS = 4000

# A reply line ending with this token tells us the agent wants a human to take over.
# It's stripped before sending. (Cheap convention; can be upgraded to a tool later.)
HANDOFF_TOKEN = "[[HANDOFF]]"

OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "remove me", "stop messaging"}

# ── The agent's persona / brain — edit this to retune behaviour ──────────────
# Layla — sales qualification agent for Lumen Marketing. Talks to Lebanese
# business owners who tap a WhatsApp link from a Lumen ad. Lebanese-direct,
# short, professional. Qualifies in 2-3 exchanges and books a call.
SYSTEM_PROMPT = """\
You are Layla, a sales qualification agent for Lumen Marketing. You work with Lebanese business owners who clicked an ad and reached out via WhatsApp. Your job is to qualify them quickly and book a call with the human team.

## Who you are
Your name is Layla. You work for Lumen Marketing. You are based in Beirut and you communicate like a Lebanese local — direct, fast, short, professional. You do NOT sound like a chatbot. You sound like a sharp marketing operator texting from her phone.

## Your core mission
Get qualified leads onto a call. Nothing else. You are not here to teach, explain, or convince. You are here to confirm fit and book.

## What Lumen does
- Custom ecommerce websites for Lebanese brands, starting at $750
- Meta ad management (Facebook + Instagram), starting at $600/month
- Full marketing systems combining both
- Track record: 880 leads at $8.38 per lead for one client, $290k in revenue over 82 days. More case studies on mk7media.com and lumenmarketing.co

Reference case studies ONLY when the lead is hesitating or asking about results. Never lead with them.

## Communication style — CRITICAL
- Lebanese Beirut style: direct, fast, short. Not American.
- Maximum 2-3 short lines per message. Often just one line. Never paragraphs.
- No emojis unless the lead uses one first
- No "great question!" or filler enthusiasm
- No American filler: never use "Awesome!" "Totally!" "Sounds great!" "Have a great day!"
- Do NOT open replies with a one-word affirmation: no "Nice." / "Got it." / "Cool." / "Makes sense." / "Sure." / "Right." / "Okay." / "Perfect." / "Awesome." / "Tamem." / "Mneeh." / "Eh." / "Akid." at the start. Open with the actual content of the message. The acknowledgment is implicit — they sent you a message, of course you read it.
- Match brevity to their messages. They write one line, you write one line.
- Sound like a person texting from her phone

## The qualification flow (loose, not rigid)
The lead came from an ad about websites or Meta ads. Use that context.

Cover these in the first 2-3 exchanges, in whatever order feels natural:
1. What kind of business they have / what they sell
2. What they're trying to fix or grow (the real problem)
3. Whether they're running ads or have a website already

MINIMUM before pushing for the call: you need to know #1 (what the business actually is) AND at least one of #2 or #3. A single data point is NOT enough. Example of what NOT to do: lead says "starting fresh on ads" and you reply "easier to explain on a quick call". That's premature — you don't even know what they sell yet. Follow up with "what's the business?" first.

MAXIMUM: three exchanges before pushing for the call. Do NOT keep interrogating. Do NOT ask 5 questions before booking.

## When to push for the call
The moment you sense they are a real business with a real need, ask for the call. Don't wait for "perfect" qualification. Lebanese leads convert on speed.

Good phrasings:
- "Sounds like something we can help with. Want to hop on a quick call?"
- "Easier to explain on a call. Free 15 mins this week?"
- "Let's do a quick call, I'll show you what we'd actually do for you"

## Pricing
- Websites: starting at $750 — say it directly if asked
- Meta ad management: starting at $600/month — say it directly if asked
- For project-specific pricing: "Depends on what you actually need. Easier to give you a real number on a quick call."

## Booking — slot logic
When the lead says yes to a call, offer specific times in Beirut time.

Primary window (always offer these first): 6pm to 11pm Beirut time, Monday through Friday. Offer 2-3 specific options across different days.

Secondary window (only if lead pushes back on evenings): 9am to 11am Beirut time, Monday through Friday.

If they need a time outside both windows: End your reply with [[HANDOFF]] [[NEEDS_CUSTOM_TIME: their requested window]] and tell the lead: "Let me check the team's availability and confirm — I'll get back to you shortly."

Example slot offering:
"Tuesday 7pm Beirut works, or Wednesday 8pm? Whichever is easier."

## Steps between the lead agreeing to a time and the booking handoff
Once they pick a time, THREE things have to happen — in this order — before you fire the booking handoff. One thing per message; do not stack them.

1. (only if they've been texting in Levantine Latin) LANGUAGE CHECK — see "Language handling" below. Skip this step entirely if they've been texting in English.
2. EMAIL for the Google Meet invite. Ask once:
   "What's the best email to send the Meet invite to?"
   (Levantine: "shu el email la3am bib3atlak fi el Meet invite?")
   If what they send back doesn't look like an email (missing @ or domain), ask one more time: "Doesn't look right — can you double-check the email?" If it's still bad, take what they gave you and flag in the SUMMARY block — don't loop on it.
3. CONFIRM + FIRE THE HANDOFF. Your closing message is a first-person plural commitment from the Lumen team. Use this exact shape:
   "Locked in for [day, time Beirut]. We'll send the Meet invite over soon."
   Levantine: "M2akkad [day, time]. Ra7 nib3atlak el Meet invite hala2."
   Then [[HANDOFF]] [[BOOKED: ...]] and the SUMMARY block.

NEVER say "the team will reach out to confirm" or "someone will be in touch" or "they'll get back to you" — that distances you from the work. YOU are the team. The phrasing is "we'll send the Meet invite over soon" — first-person plural, committal, done.

## Language handling
The lead's text language signals the call language. Match what they're writing in. Don't ask redundant English questions.

- If they're writing in ENGLISH: reply in English. Skip the language check entirely. After the time is picked, go straight to the email ask (step 2 in "Steps between the lead agreeing to a time and the booking handoff").
- If they're writing in LATIN-LETTER LEVANTINE ARABIC (transliterated, e.g. "shu akhbarak", "kifak", "ay yawm byinasbak"): reply in the same Levantine, kept extra short (1-2 lines max). Natural and casual, not formal Arabic. AFTER they pick a time but BEFORE asking for the email, ask once: "Our specialist speaks English — does that work, or want me to flag a translator for the call?"
  • If they say yes / English is fine → move to the email ask, then the booking handoff with [[BOOKED: ...]].
  • If they say no / they need Arabic → reply "No problem, we'll flag a translator for the call." then move to the email ask, then the booking handoff with BOTH [[BOOKED: ...]] AND [[NEEDS_TRANSLATION]] tags. Still book — translation is our problem to solve, not theirs.
- If they're writing in ACTUAL ARABIC SCRIPT (not Latin letters): reply once briefly in English ("Happy to help — can you write in English so we can move faster?"), then [[HANDOFF]] [[ARABIC_SCRIPT]] regardless of their response so a human can decide.

## Media handling
- Images: you can see them. Respond naturally to what's in them.
- Voice messages: reply with "Can't listen to voice messages here, can you type it?" Continue normally if they respond.
- Documents/PDFs: same as voice — ask them to type the key info

## Tone under pressure / disengagement
If a lead is rude, dismissive, or hostile — stay calm, stay professional, do NOT match their energy.

- "Not interested" / "Stop messaging me" → reply once: "All good, take care." then STOP. Do not message again.
- Insults or aggression → reply once professionally: "Understood, no pressure." then STOP.
- Going in circles → wind down naturally, stop.

NEVER argue. NEVER defend. NEVER say "I'm just trying to help." Just disengage cleanly.

If asked directly "are you a bot?" or "are you AI?" — answer honestly but briefly: "Yes, but there's a real team behind me. I'm here to get you to the right person." Then continue normally.

## Silent leads
If a lead stops responding mid-conversation, ONE soft follow-up after 4-6 hours is allowed. It MUST:
- Reference what they specifically last said
- Be under 10 words
- Not be a generic "just checking in"

Examples:
- Lead said "I'll think about it" → "Still thinking it over?"
- Lead said "Let me check my budget" → "Any luck with the budget?"
- Lead asked about timeline then went silent → "Want me to send the timeline?"

If still no response after the soft follow-up, STOP. Do not message again.

## Uncertainty self-flagging
If you encounter a question you don't know the answer to:
1. Reply: "Let me check on that and get back to you — better to be sure than guess."
2. End your reply with [[HANDOFF]] [[UNKNOWN_QUESTION: brief description of what was asked]]

This flags it for human review so the knowledge base can be updated.

## When to trigger [[HANDOFF]]
End your reply with [[HANDOFF]] in these cases:
- Lead has agreed to a specific call time (also add [[BOOKED: ...]])
- Lead booked but the call needs an Arabic-speaking translator (add [[NEEDS_TRANSLATION]] alongside [[BOOKED: ...]])
- Lead writes in Arabic script (add [[ARABIC_SCRIPT]])
- Lead needs a time outside both booking windows (add [[NEEDS_CUSTOM_TIME: ...]])
- Lead asks pricing that's outside the $750 / $600 starting ranges and can't be answered without specifics (add [[CUSTOM_PRICING]])
- Lead asks about services outside Lumen's scope (add [[OUT_OF_SCOPE: ...]])
- Lead becomes hostile or threatening (add [[HOSTILE]])
- Lead asks to speak to a human directly (add [[REQUESTED_HUMAN]])
- You genuinely don't know the answer (add [[UNKNOWN_QUESTION: ...]])

## Booking handoff format
When a call is booked, format the handoff as:

[[HANDOFF]] [[BOOKED: day, time Beirut, business type, brief context]]

Then ALSO include a brief structured summary at the very end of your message (after [[HANDOFF]]) so the email notification can extract it:

---SUMMARY---
Name: [name if shared, else "Not shared"]
Business: [what they sell, where, scale if mentioned]
Current setup: [website status, ad status]
Real problem: [in their words, paraphrased]
Time booked: [day, time Beirut + MST conversion]
Email: [the email they gave for the Meet invite — must be present for a real booking; flag if missing or malformed]
English confirmed: [yes / no — translator needed / n/a — was in English from the start]
Notes: [anything notable from the conversation]
---END---

## Things you must NOT do
- NO long paragraphs
- NO marketing-speak ("transform your business", "unlock potential")
- NO claims about results beyond the one case study above
- NO promises about specific outcomes for their business
- NO lying about being AI if directly asked
- NO continuing to message someone who has clearly disengaged
- NO more than 3 qualifying questions before asking for the call
- NO instant responses (the system handles timing)
- NO American filler language
- NO emojis unless they use one first
- NO one-word warm-up openers ("Nice." "Got it." "Cool." "Makes sense." "Sure." "Okay." "Right." "Perfect." "Awesome." "Tamem." "Mneeh.") — start the reply with the actual content, no warm-up word
"""


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
        print(f"[whatsapp] send_text {to_wa_id}: empty body, skipped")
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
    print(f"[whatsapp] send_text {to_wa_id}: {('sent wamid=' + str(wamid)) if data else 'FAILED'} body={body[:60]!r}")
    return data


def human_reply(wa_id, body):
    """A teammate replying through the admin portal. Sends the text and parks the
    conversation in 'handed_off' so the agent doesn't reply over the human. Use the
    'Hand back to agent' control to resume the agent. Returns the Graph response or None.
    (Only works inside the 24h window since the lead last messaged — which is exactly
    when handoffs happen, so that's fine.)"""
    data = send_text(wa_id, body)
    set_contact_status(wa_id, "handed_off")
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


def wa_me_link(prefill=None):
    """Build a wa.me/<our number>?text=... link. Hand this to a lead (in an email,
    on a thank-you page, in an SMS) — when they tap it, *they* message us first, which
    opens the 24h window and the agent picks it up. This is the reliable way to do
    WhatsApp outreach — cold marketing templates to people who've never messaged you
    get dropped by WhatsApp."""
    from urllib.parse import quote
    text = (prefill or "Hi! I just filled out the form on the Lumen site.").strip()
    return f"https://wa.me/{WHATSAPP_BUSINESS_NUMBER}?text={quote(text)}"


def register_lead(wa_id, *, lead_name=None, lead_business=None, lead_source="outreach"):
    """Pre-register a lead's number so the agent already knows their name/business when
    they message in. Optional — only useful if you have their WhatsApp number ahead of time."""
    wa_id = "".join(ch for ch in str(wa_id or "") if ch.isdigit())
    if not wa_id:
        return None
    if len(wa_id) == 10:
        wa_id = "1" + wa_id
    _upsert_contact(wa_id, lead_name=lead_name, lead_business=lead_business, lead_source=lead_source)
    return wa_id


def start_outreach(to_wa_id, *, template_name, lang_code=DEFAULT_TEMPLATE_LANG, body_params=None,
                   lead_name=None, lead_business=None, lead_source="form"):
    """Open a conversation with a form lead by sending the kickoff template.

    NOTE: this is the *less reliable* path — WhatsApp drops cold MARKETING templates to
    numbers that have never messaged you. Prefer `wa_me_link()` (have the lead message
    you first). Kept for when you know the recipient will accept it (e.g. they've opted in)."""
    to_wa_id = "".join(ch for ch in str(to_wa_id) if ch.isdigit())
    # A bare 10-digit number is almost certainly a US/Canada number missing its '1'
    # country code — that's the #1 reason an outreach "doesn't fire". Add it.
    if len(to_wa_id) == 10:
        to_wa_id = "1" + to_wa_id
    if len(to_wa_id) < 11:
        print(f"[whatsapp] start_outreach: number '{to_wa_id}' looks too short — needs a country code")
        return None
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


def _last_inbound_body(wa_id):
    conn = _conn()
    row = conn.execute(
        "SELECT body FROM wa_messages WHERE wa_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
        (wa_id,),
    ).fetchone()
    conn.close()
    return (row["body"] if row else "") or ""


def notify_handoff_whatsapp(wa_id, summary):
    """Ping the setter's WhatsApp number that a conversation needs a human.

    Uses the WHATSAPP_HANDOFF_TEMPLATE template if one is configured (delivers any
    time). Otherwise sends a plain text message, which only lands if the setter has
    messaged the MK7 number in the last 24h. No-op if WHATSAPP_HANDOFF_NUMBER is
    unset. System alert — not recorded in wa_messages. The email notice goes out
    separately regardless of whether this succeeds."""
    if not WHATSAPP_HANDOFF_NUMBER:
        return
    summary = (summary or "").strip()[:480] or "A WhatsApp lead needs you."
    if WHATSAPP_HANDOFF_TEMPLATE:
        payload = {
            "messaging_product": "whatsapp",
            "to": WHATSAPP_HANDOFF_NUMBER,
            "type": "template",
            "template": {
                "name": WHATSAPP_HANDOFF_TEMPLATE,
                "language": {"code": WHATSAPP_HANDOFF_TEMPLATE_LANG},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": summary}]}],
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": WHATSAPP_HANDOFF_NUMBER,
            "type": "text",
            "text": {
                "body": f"🔔 WhatsApp lead needs a human — {summary}\nInbox: https://whatsapp.mk7media.com/admin/whatsapp?id={wa_id}",
                "preview_url": False,
            },
        }
    if _graph_post(payload) is None:
        print(f"[whatsapp] handoff WhatsApp alert to {WHATSAPP_HANDOFF_NUMBER} did not send (no template + no open window, or send error)")


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

    # Reactions, system events, unsupported/ephemeral messages: log them but never reply.
    if msg_type in ("reaction", "system", "unsupported", "ephemeral"):
        if msg_type == "reaction":
            emoji = (msg.get("reaction") or {}).get("emoji", "")
            body = f"[reacted {emoji}]".strip()
        _record_message(wa_id, "in", msg_type, body, wamid=wamid)
        print(f"[whatsapp] inbound {wa_id}: {msg_type} — logged, no reply")
        return

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
        # A human owns this thread now — the agent stays out of the way, just notifies.
        print(f"[whatsapp] inbound {wa_id}: {body[:60]!r} — conversation is HANDED_OFF, not auto-replying (notify only)")
        _notify_team(
            f"WhatsApp (handed-off) — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    if text is None:
        # Non-text inbound (image / audio / location / etc.) — Layla can't read it
        # (no multimodal hookup yet). Send a brand-correct short reply and notify.
        if msg_type in ("audio", "voice"):
            fallback = "Can't listen to voice messages here, can you type it?"
        elif msg_type in ("document", "image", "video", "sticker"):
            fallback = "Can you type the key info? Easier to move from there."
        else:
            fallback = "Can you type that out? Easier on my end."
        print(f"[whatsapp] inbound {wa_id}: non-text ({msg_type}) — sending fallback + notify")
        send_text(wa_id, fallback)
        _notify_team(
            f"WhatsApp — non-text message from {contact.get('profile_name') or wa_id}",
            f"<p>Type: {msg_type}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    if not WHATSAPP_AUTO_REPLY:
        print(f"[whatsapp] inbound {wa_id}: {body[:60]!r} — auto-reply disabled, notify only")
        _notify_team(
            f"WhatsApp — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    # Generate + send the reply off the request thread so the webhook acks fast.
    print(f"[whatsapp] inbound {wa_id}: {body[:60]!r} (status={status}) — spawning reply")
    threading.Thread(target=_reply_async, args=(wa_id,), daemon=True).start()


# ── Layla handoff-tag + summary parsing ──────────────────────────────────────
# Layla emits replies that may end with one or more [[TAG: payload]] tokens
# (HANDOFF, BOOKED, ARABIC_SCRIPT, NEEDS_CUSTOM_TIME, CUSTOM_PRICING, OUT_OF_SCOPE,
# HOSTILE, REQUESTED_HUMAN, UNKNOWN_QUESTION, LANGUAGE_CHECK) and, on a booking,
# a `---SUMMARY---\nKey: value\n...\n---END---` block. None of that should reach
# the lead — strip it before sending, but keep it for the notification email.
_HANDOFF_TAG_RE = re.compile(r"\[\[\s*([A-Z_]+)(?:\s*:\s*([^\]]*))?\s*\]\]")
_SUMMARY_BLOCK_RE = re.compile(r"---\s*SUMMARY\s*---\s*(.*?)\s*---\s*END\s*---", re.DOTALL | re.IGNORECASE)


def _parse_handoff_tags(text):
    """Return {TAG_NAME: payload_str_or_True} for every [[TAG: payload]] in text.
    Includes HANDOFF so callers can check it. Insertion-ordered."""
    tags = {}
    for m in _HANDOFF_TAG_RE.finditer(text or ""):
        name = m.group(1)
        payload = (m.group(2) or "").strip()
        tags[name] = payload if payload else True
    return tags


def _parse_summary_block(text):
    """Pull the `---SUMMARY---\n key: value\n ---END---` block out.
    Returns an order-preserving dict of fields, or None if no block was found."""
    m = _SUMMARY_BLOCK_RE.search(text or "")
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip()
    return fields or None


def _strip_meta_tokens(text):
    """Remove [[...]] tags and the SUMMARY block; tidy whitespace."""
    if not text:
        return text
    cleaned = _SUMMARY_BLOCK_RE.sub("", text)
    cleaned = _HANDOFF_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).rstrip()
    return cleaned


def _summary_html(summary):
    """Render a parsed ---SUMMARY--- dict as a tidy HTML table for the email."""
    if not summary:
        return ""
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#666;white-space:nowrap'>{k}</td>"
        f"<td style='padding:4px 0'>{v}</td></tr>"
        for k, v in summary.items()
    )
    return ("<h3 style='margin:0 0 6px 0'>Booking summary</h3>"
            f"<table style='border-collapse:collapse'>{rows}</table>")


def _reply_async(wa_id):
    try:
        # Human-feel timing (per Layla spec). Webhook already ack'd; this only
        # affects how fast WE reply on the conversation thread.
        prior_assistant_text = sum(
            1 for h in _history(wa_id)
            if h["direction"] == "out" and (h.get("msg_type") or "") == "text"
        )
        delay = random.uniform(5, 15) if prior_assistant_text == 0 else random.uniform(10, 25)
        print(f"[whatsapp] _reply_async {wa_id}: sleeping {delay:.1f}s "
              f"(prior_assistant_text={prior_assistant_text})")
        time.sleep(delay)

        reply, wants_handoff, tags, summary = generate_reply(wa_id)
        print(f"[whatsapp] _reply_async {wa_id}: handoff={wants_handoff} "
              f"tags={list(tags.keys())} reply={(reply[:120] if reply else None)!r}")
        if reply:
            sent = send_text(wa_id, reply)
            print(f"[whatsapp] _reply_async {wa_id}: send_text -> {'ok' if sent else 'FAILED/empty'}")
        elif wants_handoff:
            send_text(wa_id, "One sec — let me grab the right person for this.")
        else:
            send_text(wa_id, "One sec, getting back to you.")

        if wants_handoff:
            set_contact_status(wa_id, "handed_off")
            contact = get_contact(wa_id) or {}
            label = contact.get("profile_name") or contact.get("lead_name") or ("+" + wa_id)
            business = (summary or {}).get("Business") or contact.get("lead_business") or label
            # Subject line per the Layla spec: reason tag(s) + business. For the
            # BOOKED + NEEDS_TRANSLATION case we want both tags visible at a glance.
            reason_tags = [t for t in tags.keys() if t != "HANDOFF"]
            reason = ", ".join(reason_tags) if reason_tags else "HANDOFF"
            booked_payload = tags.get("BOOKED")
            booked_str = booked_payload if isinstance(booked_payload, str) else ""
            needs_translation = "NEEDS_TRANSLATION" in tags
            # WhatsApp ping to the setter — short, scannable.
            ping = f"[Layla → {reason}] {label}"
            if booked_str:
                ping += f" — BOOKED: {booked_str[:120]}"
                if needs_translation:
                    ping += " (translator needed)"
            else:
                last_in = _last_inbound_body(wa_id)
                if last_in:
                    ping += f' — "{last_in[:120]}"'
            # Email body: summary first if present, then any non-HANDOFF tags, then
            # the inbox link and full transcript.
            tag_lines_html = ""
            if reason_tags:
                tag_lines_html = "<ul>" + "".join(
                    f"<li><b>{t}</b>{': ' + str(tags[t]) if isinstance(tags[t], str) else ''}</li>"
                    for t in reason_tags
                ) + "</ul>"
            email_body = (
                f"{_summary_html(summary)}"
                f"{tag_lines_html}"
                f"<p>Open the inbox: "
                f"<a href='https://whatsapp.mk7media.com/admin/whatsapp?id={wa_id}'>whatsapp.mk7media.com</a> "
                f"(or reply on WhatsApp: <a href='https://wa.me/{wa_id}'>wa.me/{wa_id}</a>).</p>"
                f"<hr>{_conversation_html(wa_id)}"
            )
            _notify_team(
                f"New Lumen handoff — {reason} — {business}",
                email_body,
            )
            notify_handoff_whatsapp(wa_id, ping)
    except Exception as e:
        print(f"[whatsapp] reply error for {wa_id}: {repr(e)}")
        try:
            send_text(wa_id, "One sec, getting back to you.")
        except Exception:
            pass


def generate_reply(wa_id):
    """Ask Claude for the next message in this conversation.
    Returns (reply_text_or_None, wants_handoff_bool, tags_dict, summary_dict_or_None).
    `reply` is already stripped of [[...]] tags and the ---SUMMARY--- block."""
    if not ANTHROPIC_API_KEY:
        print("[whatsapp] ANTHROPIC_API_KEY not set — cannot generate replies")
        return None, False, {}, None
    try:
        import anthropic
    except ImportError:
        print("[whatsapp] anthropic package not installed — cannot generate replies")
        return None, False, {}, None

    contact = get_contact(wa_id) or {}
    history = _history(wa_id)
    if not history:
        return None, False, {}, None

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
        context_line = "(This person filled out a form on the Lumen site"
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
        print(f"[whatsapp] anthropic call FAILED for {wa_id}: {repr(e)}")
        return None, False, {}, None

    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    print(f"[whatsapp] generate_reply {wa_id}: model={WHATSAPP_AGENT_MODEL} msgs={len(messages)} "
          f"stop={getattr(resp, 'stop_reason', '?')} raw_len={len(raw)} raw={raw[:200]!r}")
    if not raw:
        return None, False, {}, None

    tags = _parse_handoff_tags(raw)
    summary = _parse_summary_block(raw)
    wants_handoff = "HANDOFF" in tags
    clean = _strip_meta_tokens(raw)
    return (clean or None), wants_handoff, tags, summary
