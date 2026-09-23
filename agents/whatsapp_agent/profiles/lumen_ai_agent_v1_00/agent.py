"""
Lumen Ai Agent V1.00 — the WhatsApp agent for Lumen itself (+961 70 836 908).
It is both the live demo prospects meet and the agent that books the call.

COEXISTENCE profile: unlike the MK7 number (cloud-only), this number stays
live in the WhatsApp Business app on MK's phone via Meta's coexistence mode.
That changes two things about how this agent behaves:

  1. Echo handling — when MK replies to a customer from the phone app, the
     webhook delivers an echo of her message. The agent records it and SNOOZES
     itself on that conversation for LUMENAI_HUMAN_SNOOZE_HOURS (default 4h) so it
     never talks over her. Her sending a message from the app IS the takeover
     signal — no admin portal needed.
  2. Humanized pacing — replies go out after a short randomized delay
     (LUMENAI_REPLY_DELAY, default "20-60" seconds). This number was restricted by
     WhatsApp once (08.04, spam-pattern suspicion on a fresh number); instant
     robotic replies at ad-driven volume are exactly the pattern to avoid.

Wiring: app.py routes inbound webhook events to this module when
value.metadata.phone_number_id == LUMENAI_WHATSAPP_PHONE_NUMBER_ID. Until that env
var is set on Railway (it's known only after coexistence onboarding), this
module receives nothing and the deploy is a no-op.

Env vars (all optional until go-live):
  LUMENAI_WHATSAPP_PHONE_NUMBER_ID  the number's ID after coexistence onboarding
  LUMENAI_WHATSAPP_WABA_ID          defaults to 1041685491957098 (Lumen Ai WABA)
  LUMENAI_DB_PATH                   defaults to lumen_ai_whatsapp.db
  LUMENAI_AUTO_REPLY                "0" disables auto-replies (log + notify only)
  LUMENAI_REPLY_DELAY               "min-max" seconds, default "20-60"
  LUMENAI_HUMAN_SNOOZE_HOURS        default 4
  LUMENAI_NOTIFY_EMAILS             defaults to Kendall
Shared with the MK7 profile (already set on Railway):
  WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN,
  ANTHROPIC_API_KEY, RESEND_API_KEY
  WHATSAPP_AGENT_MODEL          defaults to claude-opus-4-7
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
GRAPH_API_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "mk7-whatsapp-verify")

# The Lumen Ai number's phone-number ID (default = the live value, so routing works
# without any Railway config; env override kept for emergencies/re-onboarding).
LUMENAI_PHONE_NUMBER_ID = os.environ.get("LUMENAI_WHATSAPP_PHONE_NUMBER_ID", "1386086784582081")
LUMENAI_WABA_ID = os.environ.get("LUMENAI_WHATSAPP_WABA_ID", "1041685491957098")
LUMENAI_BUSINESS_NUMBER = "".join(ch for ch in os.environ.get("LUMENAI_WHATSAPP_BUSINESS_NUMBER", "96170836908") if ch.isdigit())

# A staging number running the same code as the live client number. Everything learned
# on it transfers, and nothing learned on it risks a client's traffic. Set
# LUMENAI_TEST_PHONE_NUMBER_ID once the number is onboarded and this profile answers on
# both without a code change.
LUMENAI_TEST_PHONE_NUMBER_ID = os.environ.get("LUMENAI_TEST_PHONE_NUMBER_ID", "")
LUMENAI_TEST_BUSINESS_NUMBER = "".join(
    ch for ch in os.environ.get("LUMENAI_TEST_BUSINESS_NUMBER", "") if ch.isdigit())

# Only these wa_ids may run the in-chat test commands. Without an allow-list a real
# customer who happens to type "reset" would wipe their own order history, which is a
# far worse outcome than a slightly awkward test flow.
LUMENAI_TESTERS = {"".join(c for c in n if c.isdigit())
               for n in os.environ.get("LUMENAI_TESTERS", "").split(",") if n.strip()}

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AGENT_MODEL = os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")

# SHADOW MODE BY DEFAULT: the agent logs + emails every conversation but stays
# silent until LUMENAI_AUTO_REPLY=1 is explicitly set on Railway (Kendall flips it
# after reviewing shadow output + confirming the whitening-strips pricing).
AUTO_REPLY = os.environ.get("LUMENAI_AUTO_REPLY", "0") not in ("0", "false", "False", "")
DB_PATH = os.environ.get("LUMENAI_DB_PATH", "lumen_ai_whatsapp.db")

_default_notify = "kendall@lumenmarketing.co"
NOTIFY_EMAILS = [e.strip() for e in os.environ.get("LUMENAI_NOTIFY_EMAILS", _default_notify).split(",") if e.strip()]
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
# Admin monitoring: a live email every time the agent acts, so Kendall can watch
# it try to sell. LUMENAI_MONITOR=0 turns it off without touching the agent.
MONITOR_ON = os.environ.get("LUMENAI_MONITOR", "1") not in ("0", "false", "False", "")
MONITOR_EMAILS = [e.strip() for e in os.environ.get(
    "LUMENAI_MONITOR_EMAILS", "kendall@lumenmarketing.co").split(",") if e.strip()]
# Same monitoring, pushed to WhatsApp. Sent FROM the Lumen Cloud API number.
MONITOR_WA = [n.strip() for n in os.environ.get(
    "LUMENAI_MONITOR_WA", "12085910132").split(",") if n.strip()]

# Humanized reply delay (seconds): "min-max".
try:
    _lo, _hi = os.environ.get("LUMENAI_REPLY_DELAY", "0-0").split("-")
    REPLY_DELAY = (max(0, int(_lo)), max(int(_lo), int(_hi)))
except Exception:
    REPLY_DELAY = (20, 60)

HUMAN_SNOOZE_HOURS = float(os.environ.get("LUMENAI_HUMAN_SNOOZE_HOURS", "4"))

# Burst window: a customer who sends three messages in a row gets ONE answer, to the
# latest one. This used to be a hard 25s DROP ("standing down"), which silently lost
# real orders: "Location please" -> "Aley" -> nothing, because "Aley" landed 20s after
# our reply. Now the follow-up waits out the window and is answered.
try:
    DEBOUNCE_SECONDS = max(0.0, float(os.environ.get("LUMENAI_DEBOUNCE_SECONDS", "8")))
except Exception:
    DEBOUNCE_SECONDS = 8.0

# A customer who comes back to a thread that already reached an order (location on
# file, a "Confirmed"/"تم", or the classifier's COMMITTED) after this many hours is
# asking about an EXISTING order. MK owns those; the agent must never say "Confirmed"
# a second time (seen live: "hii" six days after the address -> "Confirmed").
try:
    STALE_ORDER_HOURS = max(1.0, float(os.environ.get("LUMENAI_STALE_ORDER_HOURS", "36")))
except Exception:
    STALE_ORDER_HOURS = 36.0

# When the customer's FIRST message carries a real question on top of the ad's canned
# opener ("Hello! Can I get more info on this? how many in a pack, delivery to Tripoli?"),
# the greeting alone leaves them hanging ("لم تجبني ع سؤالي" — you did not answer my
# question, seen live). With this on, the greeting still goes out first and the agent
# then answers the question as a reply to THEIR message. A bare "price?" / "hi" opener
# is still answered by the greeting alone.
ANSWER_OPENER = os.environ.get("LUMENAI_ANSWER_OPENER", "1") not in ("0", "false", "False", "")
OPENER_MIN_WORDS = 4

# Server-owned greeting (added 04.09.2026). The WhatsApp Business app's automated
# greeting only fires while MK's phone is on and online, and the agent used to wait
# for it. Every offline minute silenced the agent on every new lead. Now the server
# greets ad-started threads itself, so the phone is no longer in the critical path.
#   LUMENAI_GREETING_MODE  fallback (default): wait LUMENAI_GREETING_WAIT seconds; if the
#                      app's greeting echo landed meanwhile, skip ours (never a
#                      double). Otherwise send ours.
#                      always: send at once, never wait for the app.
#                      off: old behaviour, wait for the app greeting.
#   LUMENAI_GREETING_WAIT  seconds to give the phone in fallback mode, default 30.
#   LUMENAI_GREETING_TEXT  the message. Default is the app's pink-heart greeting.
#                      A literal "\n" in the env value becomes a line break.
GREETING_MODE = os.environ.get("LUMENAI_GREETING_MODE", "always").strip().lower() or "fallback"
try:
    GREETING_WAIT = max(0.0, float(os.environ.get("LUMENAI_GREETING_WAIT", "0")))
except Exception:
    GREETING_WAIT = 30.0
GREETING_TEXT = os.environ.get(
    "LUMENAI_GREETING_TEXT",
    "Hey, you are actually talking to it right now.\n\n"
    "This is the agent we set up for businesses here. What do you do?"
).replace("\\n", "\n").strip()

MAX_HISTORY = 40
MAX_OUTBOUND_CHARS = 4000
HANDOFF_TOKEN = "[[HANDOFF]]"
# If the model narrates its own thinking, that text must NEVER reach a customer.
# Seen in production: "Wait - let me reconsider. They just said hi in Arabic..."
LEAK_MARKERS = (
    "let me reconsider", "let me think", "i should", "i'll respond", "i will respond",
    "wait —", "wait -", "actually,", "the customer", "the client", "they just said",
    "that's not a handoff", "thats not a handoff", "as an ai", "system prompt",
    "handoff reason", "reconsider", "my response", "i need to",
)


def _sanitize_reply(text):
    """Return (clean_text, leaked). Strips model self-narration; if the result is
    not a clean short customer message, we send nothing and hand off instead."""
    if not text:
        return "", False
    t = text.strip()
    low = t.lower()
    leaked = any(mk in low for mk in LEAK_MARKERS)
    if leaked:
        # The real message is usually the last paragraph after the musing.
        parts = [p.strip() for p in t.split("\n\n") if p.strip()]
        tail = parts[-1] if parts else ""
        if tail and not any(mk in tail.lower() for mk in LEAK_MARKERS) and len(tail.split()) <= 14:
            print(f"[lumen-ai] reasoning leak stripped, kept tail: {tail[:60]!r}")
            return tail, False
        print(f"[lumen-ai] reasoning leak, unsalvageable — suppressing: {t[:80]!r}")
        return "", True
    if len(t.split()) > 20:
        print(f"[lumen-ai] reply too long ({len(t.split())} words) — suppressing: {t[:80]!r}")
        return "", True
    return t, False
# Media the agent cannot interpret -> straight to MK, no reply attempted.
HANDOFF_MEDIA_TYPES = {"audio", "voice", "video", "image", "document"}
# The agent ONLY works conversations it watched start from an ad. Old leads
# replying to a months-old thread get no reply — we never saw that history, so
# any answer would be guesswork. MK handles those in her app as she always has.
# Meta's default click-to-WhatsApp opener, plus the product-naming openers Kendall
# sets per ad set ("Hi, I want to know more about the Migraine Cap"). A prefill that
# names the product is the strongest product signal there is: it is what THEY tapped.
AD_PREFILL_MARKERS = ("more info on this", "مزيد من المعلومات", "المعلومات حول هذا",
                      "want to know more about", "know more about the",
                      "بدي أعرف أكتر عن", "بدي اعرف اكتر عن", "أريد معرفة المزيد عن", "اريد معرفة المزيد عن")
# The exact canned openers Meta prepends for the click-to-WhatsApp button, so we can
# strip them and see what the customer typed on top.
AD_PREFILL_SENTENCES = (
    "Hello! Can I get more info on this?",
    "مرحبًا! هل يمكنني الحصول على مزيد من المعلومات حول هذا؟",
    "مرحبا! هل يمكنني الحصول على مزيد من المعلومات حول هذا؟",
)


def _prefill_product(text):
    """Product named inside a CTA prefill (NOT stripped), or None."""
    low = (text or "").lower()
    if not any(mk in low for mk in AD_PREFILL_MARKERS):
        return None
    return _product_from_text(text, keep_prefill=True)


def _opener_question(text):
    """What the customer typed beyond the ad's canned opener, if it is substantive
    enough to deserve an answer of its own (a real question, not "hi" or "price?")."""
    rest = _strip_prefill(text)
    words = re.findall(r"[\w\u0600-\u06FF$]+", rest)
    return rest if len(words) >= OPENER_MIN_WORDS else ""
# The WhatsApp Business app fires an automated greeting ("Hello this item is for
# $12 / Would you like to order?"). It arrives as an app echo, identical in shape
# to MK typing by hand. If we snooze on it, the agent silences itself on EVERY
# new lead. These markers identify the canned greeting so we ignore it.
GREETING_MARKERS = ("would you like to order", "this item is for")
# Where handoff pings go: the FGC number itself, so the alert lands in the
# WhatsApp Business app MK already works in. Sent FROM the Lumen Cloud API number.
LUMEN_NOTIFY_PHONE_ID = os.environ.get("LUMEN_NOTIFY_PHONE_ID", "1082296231636502")
HANDOFF_WA_NUMBERS = [n.strip() for n in os.environ.get(
    "LUMENAI_HANDOFF_WA", "12085910132").split(",") if n.strip()]
OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "remove me", "stop messaging"}

# ── The agent's persona / brain ──────────────────────────────────────────────
# PRODUCT FACTS: keep this block current — it is the agent's entire catalog
# knowledge. Prices/offers marked TODO must be confirmed by Kendall/MK before
# go-live (LUMENAI_AUTO_REPLY=0 until then keeps the agent in log-only mode).
SYSTEM_PROMPT = """\
You are the WhatsApp agent for Lumen, answering on Lumen's own number. Everyone
who messages you clicked a Meta ad about WhatsApp agents for Lebanese businesses.

WHAT YOU ARE DOING — both at once, never one without the other
1. You are the DEMO. They are not reading about what we do, they are watching it
   happen to them. Every reply IS the product.
2. You are BOOKING A CALL. That is the goal and you move toward it from the
   second message.

The demo is not a separate stage before the booking. You show what this thing can
do BY how you handle them while you book them. Fast, in their language, and
understanding their business without being told twice.

THE SHORT PATH — this matters most
Do NOT interview them. One question about their business, then go for the call.
That is the whole shape:

  1. They say what their business is.
  2. You show, in ONE line, the specific thing this would do for THAT business.
  3. You ask for a time.
  4. You get their email.
  5. You confirm and hand off.

Never ask a second qualifying question before offering the call. No "who answers
them now", no "how many do you get", no "what happens at 11pm" unless THEY opened
that door. If they answer your first question with anything real, go straight to
step 2 and 3.

THE ONE EXCEPTION: if they are clearly enjoying it and keep asking what it can
do, keep demoing. Answer them, show off, and offer the time again after. A
prospect who wants to play with it is a good sign, do not cut them off to book.

SHOWING OFF — one line, about THEIR business, never a feature list
When they name their business, come back with the concrete thing this would do
for that exact business. Specific, not generic. One line.

  Clinic     -> "So it books the appointment and chases the ones who go quiet."
  Online shop-> "So it answers the price and delivery question at 2am and takes
                 the order."
  Salon      -> "So it fills the empty slots without you touching your phone."
  Restaurant -> "So it takes the reservation while you are in service."
  Gym        -> "So it answers the membership questions and books the trial."

If you do not know the business type, do not guess. Ask once, then do this.

Never list features. Never say "we can also". One line, their business, move on.

BOOKING — what you must walk away with
You need TWO things, in this order:
  1. A DAY and a TIME.
  2. Their EMAIL.

Get the time first. Never ask for both in one message.
- Ask plainly: "What day and time suits you?"
- If they give a day but no time: "Morning or afternoon?" then pin an actual hour.
- If they are vague ("this week", "whenever"): offer two concrete options, e.g.
  "Tomorrow 11am or Thursday 4pm?" Concrete beats open every time.
- Once the time is set, and only then: "Perfect. What is the best email for the
  invite?"
- When you have both, confirm in one line and stop.

Times are Beirut time. Do not ask where they are and do not ask them to confirm
the timezone. If they are clearly outside Lebanon, say the time in Beirut time
so it is unambiguous, and carry on.

The call is 15 minutes with Kendall. The invite comes by email.
Never offer a time in the past. Never invent a slot that is already taken, you do
not have a calendar, so speak in day-and-time terms they propose or that you
offer as options.

HOW YOU WRITE
OUTPUT RULE, absolute: your entire output is the message they receive. Nothing
else. Never explain yourself, never narrate, never write about "the customer" or
"the lead", never reconsider out loud, never write a preamble. If you catch
yourself writing a sentence ABOUT the conversation instead of IN it, stop and
send only the message.

LENGTH: one to two lines. Usually one. Never more than about 30 words. One idea
per message. Most messages end with a question, because a question is what keeps
a conversation moving toward the time.

- NEVER use emojis. Not one, ever.
- No corporate words. Never say: solution, platform, leverage, streamline,
  optimise, seamless, cutting-edge, empower, unlock, revolutionise, game-changer,
  reach out, circle back, touch base, at your earliest convenience.
- Never say "I hope this helps" or "let me know if you have any questions".
- Do not use em dashes.
- Never mention that you are an AI, a bot, an assistant, or a model. If they ask
  outright, tell the truth in one line and turn it into the point: "Yes. That is
  the whole idea, this is the thing working. What day suits you for a quick call?"

LANGUAGE — mirror them exactly
- English -> English.
- Arabic script -> Arabic script.
- Lebanese Arabic written in Latin letters and numbers ("kifak", "shu badak",
  "3andi mahal", "bade a3rif") -> reply in that same style.
- French -> French.
Keep it Lebanese and casual. Never formal Modern Standard Arabic. Never translate
their words back at them.

THE META PREFILL MEANS NOTHING
About a third of first messages are Meta's canned text, usually exactly
"Hello! Can I get more info on this?" or a close variant. That is a button press,
not a question. Do NOT answer it with an explanation of Lumen. Treat it as hello
and ask what their business is.

THEY HAVE ALREADY BEEN GREETED
Our opener has gone out. Never greet twice and never repeat it.

THINGS THEY WILL ASK, AND THE WHOLE ANSWER
One or two lines each, then straight back to the time.
- "How much?" -> "Starts at 250 a month depending on what you need. Kendall goes
  through it properly on the call. What day suits you?"
- "How does it work?" -> "It answers every message the second it lands, in your
  voice, and hands you the ones ready to buy."
- "Is it a chatbot?" -> "No buttons, no menus. It just talks, the way this is
  talking to you."
- "Does it speak Arabic?" -> "Arabic, Lebanese, arabizi, English, French.
  Whatever the customer writes in."
- "Can it take orders / bookings?" -> "Yes, straight into your calendar."
- "Do I need ads?" -> "No. It works on the messages you already get."
- "Who are you?" -> "Lumen. We set this up for businesses here in Lebanon."
- "Can I see it?" -> "You are seeing it."
- "Can it do what you are doing now for me?" -> "This is exactly it, in your
  voice instead of ours."

NEVER INVENT A FACT
If a fact is not in these instructions, you do not have it. Never invent a client
name, a case study, a number, a guarantee, a timeline, or a feature. Never name
another client. If you do not know, say Kendall covers it on the call, and ask
for the time.

NEVER PROMISE
No guarantees of results, revenue, or a number of sales. Never quote a setup time
or a go-live date. Never negotiate the price.

WHEN TO HAND OFF — end your reply with [[HANDOFF]]
- You have a DAY, a TIME and an EMAIL: confirm in one line, then [[HANDOFF]].
  Example: "Done. Thursday 4pm, invite is on its way to that email." [[HANDOFF]]
- They ask for Kendall by name or ask to speak to a person.
- An existing client with a problem, a complaint, or a billing question.
- A voice note, photo, video or document you cannot read.
- A language that is not Arabic, arabizi, English or French.
For every handoff except the booked-call one, output ONLY the token [[HANDOFF]]
and nothing else. No apology, no stalling, no naming anyone.

Do NOT hand off for: price, how it works, what it does, languages, whether it is
a bot, whether they need ads, or someone being blunt. Answer and keep going.

IF THEY ARE NOT A BUSINESS
Someone selling to you, a job seeker, a student doing research: one polite line,
then [[HANDOFF]]. Do not argue and do not try to convert them.

IF THEY GO QUIET ON THE TIME
If they have shown interest but dodge the time twice, stop selling and make it
easy: offer two concrete slots. If they dodge a third time, leave it open with
one line and stop pushing: "No rush. Tell me a day that works and I will set it."
"""


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
        -- Every click-to-WhatsApp referral we have ever seen, one row per click.
        -- `ctwa_clid` is the ONLY join key between a WhatsApp thread and the ad that
        -- produced it. Meta emits it once, on the referral object of the first inbound
        -- message after a click, and never again. It cannot be recovered later from
        -- any API. If we do not write it down in the second it arrives, that
        -- conversation is permanently unattributable — which is exactly what happened
        -- to the 141 conversations in the August export.
        CREATE TABLE IF NOT EXISTS wa_ctwa_clicks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id        TEXT NOT NULL,
            ctwa_clid    TEXT,
            ad_id        TEXT,
            adset_id     TEXT,
            adset_name   TEXT,
            campaign_id  TEXT,
            campaign_name TEXT,
            ad_name      TEXT,
            source_type  TEXT,
            headline     TEXT,
            product      TEXT,
            resolved_at  TIMESTAMP,
            seen_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ctwa_waid ON wa_ctwa_clicks(wa_id, seen_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ctwa_clid
            ON wa_ctwa_clicks(ctwa_clid) WHERE ctwa_clid IS NOT NULL;

        -- Conversion events sent to Meta, so we never send one twice. Dedup here is
        -- not politeness: a duplicate Purchase inflates the merchant's reported ROAS
        -- and teaches the algorithm to chase a customer who already bought.
        CREATE TABLE IF NOT EXISTS wa_capi_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id       TEXT NOT NULL,
            event_name  TEXT NOT NULL,
            event_id    TEXT NOT NULL UNIQUE,
            ctwa_clid   TEXT,
            value       REAL,
            currency    TEXT,
            state       TEXT,
            status      TEXT,                          -- 'pending' | 'dry_run' | 'sent' | 'failed' | 'skipped' | 'cancelled'
            detail      TEXT,
            fire_after  REAL,                          -- unix ts; settle window for Purchase
            fired_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_capi_waid ON wa_capi_events(wa_id, event_name);

        CREATE TABLE IF NOT EXISTS wa_history_raw (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            payload     TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    # Lineage columns, for databases created before ad set / campaign capture existed.
    try:
        conn.execute("ALTER TABLE wa_capi_events ADD COLUMN fire_after REAL")
    except Exception:
        pass
    for col, ddl in (("adset_id", "TEXT"), ("adset_name", "TEXT"),
                     ("campaign_id", "TEXT"), ("campaign_name", "TEXT"),
                     ("ad_name", "TEXT"), ("resolved_at", "TIMESTAMP"),
                     # The ad copy Meta ships with every click — the most reliable
                     # product signal, and it never expires like the ads token does.
                     ("source_url", "TEXT"), ("ad_body", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE wa_ctwa_clicks ADD COLUMN {col} {ddl}")
        except Exception:
            pass
    conn.commit()
    # Additive migrations — safe to run every boot.
    for col, ddl in (("product", "TEXT"), ("product_ad_id", "TEXT"),
                     ("last_lat", "REAL"), ("last_lng", "REAL"),
                     ("last_location_text", "TEXT"), ("agent_ok", "INTEGER DEFAULT 0"),
                     ("greeted", "INTEGER DEFAULT 0"),
                     # Most recent click wins for attribution: someone who clicks a
                     # second ad weeks later and then buys converted on the second ad.
                     # The full history stays in wa_ctwa_clicks.
                     ("ctwa_clid", "TEXT"), ("ctwa_clid_at", "TIMESTAMP"),
                     ("via_phone_id", "TEXT"),
                     # Recovery sweep: one re-engagement message per contact, inside
                     # the 24h window. reengaged_at is the atomic dedup claim.
                     ("reengaged_at", "TIMESTAMP"), ("reengage_kind", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE wa_contacts ADD COLUMN {col} {ddl}")
        except Exception:
            pass
    # Single-runner lock so only one gunicorn worker runs the recovery sweep per tick.
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS wa_sweep_lock "
                     "(id INTEGER PRIMARY KEY CHECK(id=1), last_run REAL)")
    except Exception:
        pass
    # Every contact that existed before via_phone_id was introduced arrived on the FGC
    # number, because it was the only number this profile answered. Without this they
    # sit outside every per-number view and the dashboard reads zero on an account with
    # 141 real conversations in it.
    try:
        conn.execute(
            "UPDATE wa_contacts SET via_phone_id = ? WHERE via_phone_id IS NULL",
            (LUMENAI_PHONE_NUMBER_ID,))
        conn.commit()
    except Exception as e:
        print(f"[lumen-ai] via_phone_id backfill skipped: {e}")

    conn.commit()
    conn.close()


init_db()


# --------------------------------------------------------------------------
# Product detection from the click-to-WhatsApp ad the customer came from.
# Meta puts a `referral` object on the FIRST inbound message of an ad-started
# conversation, carrying source_id = the ad id. Ad names are self-describing
# ("FGC | Migraine Cap | Aug 22 F"), so we resolve product from the name and
# refresh the map periodically — new ads work with no code change.
# --------------------------------------------------------------------------
LUMENAI_ADS_TOKEN = os.environ.get("LUMENAI_ADS_TOKEN", "")
LUMENAI_AD_ACCOUNT = os.environ.get("LUMENAI_AD_ACCOUNT", "act_1337494034720023")
_AD_MAP = {"at": 0.0, "map": {}}
_AD_MAP_TTL = 3600.0

PRODUCT_RULES = (
    ("migraine cap", "Migraine Relief Cap"),
    ("migraine", "Migraine Relief Cap"),
    ("nasal", "Nasal Strips"),
    ("nose strip", "Nasal Strips"),
    ("toothpaste", "Whitening Toothpaste"),
    ("whitening strips", "Teeth Whitening Strips"),
    ("whitening", "Teeth Whitening Strips"),
    ("teeth", "Teeth Whitening Strips"),
    ("acne patch", "Pimple Patches"),
    ("pimple", "Pimple Patches"),
    ("acne", "Pimple Patches"),
    # Posture Corrector is NOT an active product — deliberately excluded.
)


def _product_from_name(name):
    n = (name or "").lower()
    for needle, product in PRODUCT_RULES:
        if needle in n:
            return product
    return None


# What the CUSTOMER types beats the ad they came from — but only when they actually
# NAME a product. The previous version was plain substring matching and it is why the
# agent quoted "360 patches" on teeth threads and "150 nasal strips" on strips threads:
# the Arabic needle "حب" (pimple) is inside "مرحبا" (hello, i.e. EVERY Arabic ad opener),
# "حبة" (a piece) and "بتحبي" (would you like); "نفس" (breath) is inside "نفس شي" (same
# thing); "cap" is inside half the English dictionary. Now: Latin needles match whole
# words, Arabic needles match whole tokens after stripping the usual prefixes/suffixes,
# and the generic words (لزقة/لصقة strip-or-patch, حبة piece, breath) are not signals.
# Ordered: nose/breathing signals before a bare "strip(s)" falls through to teeth.
_TEXT_PRODUCT_RULES = (
    (("nasal", "nose", "nose strip", "nose strips",
      "منخار", "خشم", "انف", "الانف", "تنفس", "اتنفس", "بتنفس", "التنفس", "يتنفس", "نتنفس"),
     "Nasal Strips"),
    (("toothpaste", "معجون"), "Whitening Toothpaste"),
    (("migraine", "migraines", "headache", "headaches", "cap", "ice cap", "cold cap",
      "صداع", "الصداع", "شقيقة", "الشقيقة", "قبعة", "كاب", "راس", "الراس", "راسي"),
     "Migraine Relief Cap"),
    (("pimple", "pimples", "acne", "blemish", "blemishes", "patch", "patches",
      "حبوب", "الحبوب", "بثور", "البثور", "حب الشباب"),
     "Pimple Patches"),
    (("teeth", "tooth", "dental", "whitening", "whitening strip", "whitening strips",
      "strip", "strips",
      "سنان", "اسنان", "الاسنان", "سناني", "سنانك", "تبييض", "التبييض", "ستريبس", "سترايبس"),
     "Teeth Whitening Strips"),
)

_AR_PREFIXES = ("وبال", "وال", "فال", "بال", "عال", "لل", "ال", "و", "ف", "ب", "ل", "ك", "ع")
_AR_SUFFIXES = ("هم", "هن", "كم", "كن", "نا", "ها", "ي", "ك", "و", "ه", "ن")
_AR_DIACRITICS = re.compile("[\u064B-\u0652\u0670\u0640]")


def _ar_norm(tok):
    t = _AR_DIACRITICS.sub("", tok)
    return (t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
             .replace("ة", "ه").replace("ى", "ي"))


def _ar_stems(tok):
    """A token plus its de-prefixed / de-suffixed forms, all alef-normalised."""
    t = _ar_norm(tok)
    out = {t}
    bases = {t}
    for pre in _AR_PREFIXES:
        if t.startswith(pre) and len(t) - len(pre) >= 2:
            bases.add(t[len(pre):])
    for b in list(bases):
        out.add(b)
        for suf in _AR_SUFFIXES:
            if b.endswith(suf) and len(b) - len(suf) >= 2:
                out.add(b[:-len(suf)])
    return out


_LATIN_WORD = re.compile(r"[a-z0-9]+")
_AR_WORD = re.compile(r"[\u0600-\u06FF]+")


def _strip_prefill(text):
    """Remove Meta's canned ad opener from a message and return what the customer
    actually typed (possibly nothing)."""
    t = text or ""
    for canned in AD_PREFILL_SENTENCES:
        t = t.replace(canned, " ")
    low = t.lower()
    if any(mk in low for mk in AD_PREFILL_MARKERS):
        # A variant we do not have verbatim: drop the sentence that carries the marker.
        parts = re.split(r"(?<=[?؟!.\n])", t)
        t = " ".join(p for p in parts if not any(mk in p.lower() for mk in AD_PREFILL_MARKERS))
    return t.strip()


def _product_from_text(text, keep_prefill=False):
    """Detect the product the customer is talking about from their message.
    Returns None when nothing is clearly named."""
    t = ((text or "") if keep_prefill else _strip_prefill(text)).lower()
    if not t:
        return None
    latin_tokens = set(_LATIN_WORD.findall(t))
    ar_tokens = set()
    for tok in _AR_WORD.findall(t):
        ar_tokens |= _ar_stems(tok)
    t_norm = _ar_norm(t)
    for needles, product in _TEXT_PRODUCT_RULES:
        for n in needles:
            if _AR_WORD.search(n):
                nn = _ar_norm(n)
                if " " in nn:
                    if nn in t_norm:
                        return product
                elif nn in ar_tokens:
                    return product
            else:
                if " " in n:
                    if re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", t):
                        return product
                elif n in latin_tokens:
                    return product
    return None


# The authoritative source of truth: each FGC ad SET / campaign sells exactly one
# product, so the referral's ad -> its ad set/campaign id -> the product, with zero
# guessing from what the customer typed or what the ad headline said. Pulled from
# act_1337494034720023 on 2026-09-06; extend when new products/campaigns launch (the
# ad-set-NAME fallback below already covers new ones that follow the naming convention).
PRODUCT_BY_CAMPAIGN = {
    "120247759799100353": "Teeth Whitening Strips",
    "120248292003920353": "Pimple Patches",
    "120248291945840353": "Pimple Patches",
    "120247923099400353": "Pimple Patches",
    "120248296188790353": "Migraine Relief Cap",
    "120247809603120353": "Migraine Relief Cap",
    "120247915433860353": "Migraine Relief Cap",
    "120248345125330353": "Nasal Strips",
    "120248346999360353": "Whitening Toothpaste",
    "120248233595000353": "Whitening Toothpaste",
}
# Ad-level overrides, checked BEFORE ad set / campaign. Only for ads whose creative sells
# a different product than the ad set they sit in. 120248397391060353 sits in the
# "Migraine Cap | Leads" ad set but runs the purple teeth-whitening video (video
# 18140058307544571, the same file as the Whitening Strips ad) — verified 15.09.2026
# after MK corrected four "cap" threads to "14 strips". Fixing the ad is Kendall/MK's
# call; this keeps the agent honest meanwhile.
PRODUCT_BY_AD = {
    "120248397391060353": "Teeth Whitening Strips",
}

# ── The verified product map (product_map.json, next to this file) ─────────────
# Built 15.09.2026 by pulling EVERY ad on act_1337494034720023 with its ad set and
# campaign, then looking at the frames of each ad's video / image and recording what
# the creative actually sells. Titles are only the fallback: the live account had a
# whitening video running inside the "Migraine Cap" ad set, so the name lied for
# weeks. Regenerate with tools/fgc_ad_map.py (see that file), then re-verify frames.
#   ads[ad_id]         -> product  (verified: "frames" or "title")
#   videos[video_id]   -> product  (a NEW ad that reuses a known video resolves at once)
#   adsets / campaigns -> product  (from titles; last resort before text parsing)
_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "product_map.json")
PRODUCT_MAP = {"ads": {}, "videos": {}, "adsets": {}, "campaigns": {}}
try:
    with open(_MAP_PATH, encoding="utf-8") as _f:
        _pm = json.load(_f)
    for _k in PRODUCT_MAP:
        PRODUCT_MAP[_k] = {str(i): (v if isinstance(v, dict) else {"product": v})
                           for i, v in (_pm.get(_k) or {}).items()}
    print(f"[lumen-ai] product map loaded: {len(PRODUCT_MAP['ads'])} ads, "
          f"{len(PRODUCT_MAP['videos'])} videos, {len(PRODUCT_MAP['adsets'])} ad sets, "
          f"{len(PRODUCT_MAP['campaigns'])} campaigns")
except Exception as _e:
    print(f"[lumen-ai] product map NOT loaded ({_e}); falling back to code maps")
for _ad, _v in PRODUCT_MAP["ads"].items():
    if _v.get("product"):
        PRODUCT_BY_AD.setdefault(_ad, _v["product"])
PRODUCT_BY_ADSET = {
    # Mixed-product campaigns (Website Sales CBO, Instagram DM) — resolve at ad-set level.
    "120248252363870353": "Pimple Patches",
    "120248252355420353": "Teeth Whitening Strips",
    "120248252348610353": "Migraine Relief Cap",
    "120248250989170353": "Whitening Toothpaste",
    "120248250981930353": "Teeth Whitening Strips",
}


# One block per product, injected on its own when we know the product, so the model
# answers "how many in the pack" from THIS product's line and never from a neighbour's.
PRODUCT_FACTS = {
    "Teeth Whitening Strips":
        "14 strips per pack. One strip per session, about 20 minutes, one-time use. "
        "They notice a difference after the first use, best after finishing the pack. "
        "Standard whitening gel, fine for most people. Works on crooked / crowded teeth "
        "(mlabasin) too, the answer there is simply yes. 'How many in the pack?' -> 14.",
    "Nasal Strips":
        "150 strips per pack, one-time use. An adhesive fabric strip across the nose to "
        "breathe better. No special ingredient, just the strip. 'How many in the pack?' -> 150.",
    "Migraine Relief Cap":
        "ONE reusable cap per pack. Keep it in the freezer, about 45 minutes of cold relief "
        "per use, stays cold 2 to 3 hours out, about 0C, gel inside (not water), one size "
        "stretchable, hand wash and air dry. 'How many in the pack?' -> one cap, reusable.",
    "Pimple Patches":
        "360 patches per pack, one size, one-time use. Stick one on a pimple, best overnight "
        "or 4 to 6 hours. 'How many in the pack?' -> 360.",
    "Whitening Toothpaste":
        "One bottle of purple whitening toothpaste, used like normal toothpaste. "
        "'How many in the pack?' -> one bottle.",
}


def _product_from_lineage(lin):
    """Product from the ad's OWN structure, most reliable first:
    the creative's video/image (verified by looking at frames), then ad set id, then
    campaign id, then the ad-set/campaign name. Returns (product, how)."""
    if not lin:
        return None, None
    vid = str(lin.get("video_id") or "")
    if vid and PRODUCT_MAP["videos"].get(vid, {}).get("product"):
        return PRODUCT_MAP["videos"][vid]["product"], "video"
    img = str(lin.get("image_hash") or "")
    if img and PRODUCT_MAP["videos"].get(img, {}).get("product"):
        return PRODUCT_MAP["videos"][img]["product"], "image"
    aid = str(lin.get("adset_id") or "")
    if aid and (PRODUCT_MAP["adsets"].get(aid, {}).get("product") or PRODUCT_BY_ADSET.get(aid)):
        return (PRODUCT_MAP["adsets"].get(aid, {}).get("product") or PRODUCT_BY_ADSET.get(aid)), "adset"
    cid = str(lin.get("campaign_id") or "")
    if cid and (PRODUCT_MAP["campaigns"].get(cid, {}).get("product") or PRODUCT_BY_CAMPAIGN.get(cid)):
        return (PRODUCT_MAP["campaigns"].get(cid, {}).get("product") or PRODUCT_BY_CAMPAIGN.get(cid)), "campaign"
    p = _product_from_text(f"{lin.get('adset_name') or ''} {lin.get('campaign_name') or ''} {lin.get('ad_name') or ''}")
    return (p, "title") if p else (None, None)


def _register_ad(ad_id, product, how, lin):
    """Every ad the webhook ever sees lands in wa_ad_registry with how its product was
    decided. An ad resolved by anything weaker than the verified map ("video"/"ads")
    is alerted ONCE so it gets looked at and added to product_map.json."""
    if not ad_id:
        return
    conn = _conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS wa_ad_registry (ad_id TEXT PRIMARY KEY, product TEXT, "
            "how TEXT, ad_name TEXT, adset_id TEXT, adset_name TEXT, campaign_id TEXT, "
            "campaign_name TEXT, video_id TEXT, first_seen TEXT DEFAULT CURRENT_TIMESTAMP, "
            "last_seen TEXT, hits INTEGER DEFAULT 0, alerted INTEGER DEFAULT 0)")
        row = conn.execute("SELECT alerted, how FROM wa_ad_registry WHERE ad_id=?", (ad_id,)).fetchone()
        lin = lin or {}
        conn.execute(
            "INSERT INTO wa_ad_registry (ad_id, product, how, ad_name, adset_id, adset_name, "
            "campaign_id, campaign_name, video_id, last_seen, hits) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,1) "
            "ON CONFLICT(ad_id) DO UPDATE SET product=excluded.product, how=excluded.how, "
            "ad_name=COALESCE(excluded.ad_name, ad_name), adset_id=COALESCE(excluded.adset_id, adset_id), "
            "adset_name=COALESCE(excluded.adset_name, adset_name), campaign_id=COALESCE(excluded.campaign_id, campaign_id), "
            "campaign_name=COALESCE(excluded.campaign_name, campaign_name), video_id=COALESCE(excluded.video_id, video_id), "
            "last_seen=CURRENT_TIMESTAMP, hits=hits+1",
            (ad_id, product, how, lin.get("ad_name"), lin.get("adset_id"), lin.get("adset_name"),
             lin.get("campaign_id"), lin.get("campaign_name"), lin.get("video_id")))
        conn.commit()
        verified = how in ("verified", "video", "image", "prefill")
        if not verified and not (row and row["alerted"]):
            conn.execute("UPDATE wa_ad_registry SET alerted=1 WHERE ad_id=?", (ad_id,))
            conn.commit()
            try:
                _notify_team(
                    f"Lumen Ai agent: unmapped ad — {ad_id}",
                    f"<p>An ad the agent has never verified just sent a customer in.</p>"
                    f"<p><b>Ad</b> {ad_id} — {lin.get('ad_name') or '?'}<br>"
                    f"<b>Ad set</b> {lin.get('adset_id') or '?'} — {lin.get('adset_name') or '?'}<br>"
                    f"<b>Campaign</b> {lin.get('campaign_id') or '?'} — {lin.get('campaign_name') or '?'}<br>"
                    f"<b>Video</b> {lin.get('video_id') or '?'}</p>"
                    f"<p>Product guessed from <b>{how or 'nothing'}</b>: <b>{product or 'UNKNOWN'}</b>. "
                    f"Until it is verified from the frames and added to product_map.json the agent "
                    f"{'uses that guess' if product else 'will not name any product on these threads'}.</p>")
            except Exception as e:
                print(f"[lumen-ai] ad registry alert failed: {e}")
    except Exception as e:
        print(f"[lumen-ai] ad registry error for {ad_id}: {e}")
    finally:
        conn.close()


def ad_registry():
    """Everything the webhook has seen, for the admin endpoint."""
    conn = _conn()
    try:
        try:
            rows = conn.execute("SELECT * FROM wa_ad_registry ORDER BY last_seen DESC").fetchall()
        except Exception:
            return {"ads": [], "verified_map": {k: len(v) for k, v in PRODUCT_MAP.items()}}
        return {"ads": [dict(r) for r in rows],
                "unverified": [dict(r) for r in rows if r["how"] not in ("verified", "video", "image", "prefill")],
                "verified_map": {k: len(v) for k, v in PRODUCT_MAP.items()}}
    finally:
        conn.close()


def backfill_products(limit=500):
    """Resolve product for existing contacts that never got one, using each stored
    click's ad id -> ad-set/campaign lineage. Safe to run repeatedly."""
    conn = _conn()
    rows = conn.execute(
        "SELECT DISTINCT c.wa_id, k.ad_id, k.adset_id, k.campaign_id, k.adset_name, k.campaign_name "
        "FROM wa_contacts c JOIN wa_ctwa_clicks k ON k.wa_id = c.wa_id "
        "WHERE (c.product IS NULL OR c.product = '') AND k.ad_id IS NOT NULL "
        "ORDER BY k.seen_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    fixed = {}
    # Known mismatched ads first: contacts already labelled from the ad set get the
    # product the creative actually sells.
    for ad_id, product in PRODUCT_BY_AD.items():
        c = _conn()
        rows_o = c.execute("SELECT wa_id FROM wa_contacts WHERE product_ad_id=? AND "
                           "COALESCE(product,'') != ?", (ad_id, product)).fetchall()
        for r in rows_o:
            fixed[r["wa_id"]] = product
        c.execute("UPDATE wa_contacts SET product=? WHERE product_ad_id=? AND "
                  "COALESCE(product,'') != ?", (product, ad_id, product))
        c.execute("UPDATE wa_ctwa_clicks SET product=? WHERE ad_id=? AND "
                  "COALESCE(product,'') != ?", (product, ad_id, product))
        c.commit(); c.close()
    for r in rows:
        wa_id = r["wa_id"]
        if wa_id in fixed:
            continue
        lin = {"adset_id": r["adset_id"], "campaign_id": r["campaign_id"],
               "adset_name": r["adset_name"], "campaign_name": r["campaign_name"]}
        product = PRODUCT_BY_AD.get(str(r["ad_id"])) or _product_from_lineage(lin)[0]
        if not product:  # lineage not stored yet — resolve it live
            lin = _resolve_ad_lineage(r["ad_id"]) or {}
            product = _product_from_lineage(lin)[0] or _refresh_ad_map().get(str(r["ad_id"]))
        if not product:
            continue
        c = _conn()
        c.execute("UPDATE wa_contacts SET product=?, product_ad_id=? WHERE wa_id=? "
                  "AND (product IS NULL OR product='')", (product, r["ad_id"], wa_id))
        c.execute("UPDATE wa_ctwa_clicks SET product=? WHERE wa_id=? AND product IS NULL",
                  (product, wa_id))
        c.commit(); c.close()
        fixed[wa_id] = product
    return fixed


def _referral_hint(wa_id):
    """The ad copy (headline / body / URL) from this contact's most recent click,
    so the model can infer the product when our mapping failed. Short, safe on error."""
    try:
        conn = _conn()
        r = conn.execute(
            "SELECT headline, ad_body, source_url FROM wa_ctwa_clicks "
            "WHERE wa_id=? ORDER BY seen_at DESC LIMIT 1", (wa_id,)).fetchone()
        conn.close()
        if not r:
            return None
        parts = [r["headline"], r["ad_body"], r["source_url"]]
        hint = " ".join(p for p in parts if p).strip()
        return hint[:240] or None
    except Exception:
        return None


def _refresh_ad_map(force=False):
    if not LUMENAI_ADS_TOKEN:
        return _AD_MAP["map"]
    if not force and (time.time() - _AD_MAP["at"]) < _AD_MAP_TTL:
        return _AD_MAP["map"]
    try:
        r = requests.get(
            f"{GRAPH_BASE}/{LUMENAI_AD_ACCOUNT}/ads",
            params={"fields": "id,name", "limit": 500, "access_token": LUMENAI_ADS_TOKEN},
            timeout=20,
        )
        data = (r.json() or {}).get("data") or []
        m = {}
        for ad in data:
            prod = _product_from_name(ad.get("name"))
            if prod:
                m[str(ad.get("id"))] = prod
        if m:
            _AD_MAP["map"] = m
            _AD_MAP["at"] = time.time()
            print(f"[lumen-ai] ad map refreshed: {len(m)} ads")
    except Exception as e:
        print(f"[lumen-ai] ad map refresh failed: {e}")
    return _AD_MAP["map"]


# Ad lineage cache. Meta's referral payload carries `source_id` — the AD id — and
# nothing above it. Campaign and ad set have to be resolved through the Graph API, so
# the lineage is cached per ad: a campaign's ads are stable, and the same ad produces
# hundreds of conversations.
_LINEAGE = {}


def _resolve_ad_lineage(ad_id, force=False):
    """ad_id -> {ad_name, adset_id, adset_name, campaign_id, campaign_name} or None.

    One Graph call returns the whole chain. Deliberately NOT scoped to
    LUMENAI_AD_ACCOUNT: when the destination number moves between accounts, or an ad runs
    from a different account, resolving by ad id still works where an account-scoped
    map would silently miss.
    """
    ad_id = str(ad_id or "")
    if not ad_id:
        return None
    if not force and ad_id in _LINEAGE:
        return _LINEAGE[ad_id]
    if not LUMENAI_ADS_TOKEN:
        return None
    try:
        r = requests.get(
            f"{GRAPH_BASE}/{ad_id}",
            params={"fields": "name,adset{id,name},campaign{id,name},"
                              "creative{video_id,image_hash,object_story_spec{video_data{video_id}}}",
                    "access_token": LUMENAI_ADS_TOKEN},
            timeout=15,
        )
        d = r.json() or {}
        if "error" in d:
            print(f"[lumen-ai] lineage lookup failed for ad {ad_id}: "
                  f"{d['error'].get('message', '')[:120]}")
            return None
        cr = d.get("creative") or {}
        vd = ((cr.get("object_story_spec") or {}).get("video_data") or {})
        out = {
            "ad_name": d.get("name"),
            "adset_id": (d.get("adset") or {}).get("id"),
            "adset_name": (d.get("adset") or {}).get("name"),
            "campaign_id": (d.get("campaign") or {}).get("id"),
            "campaign_name": (d.get("campaign") or {}).get("name"),
            "video_id": cr.get("video_id") or vd.get("video_id"),
            "image_hash": cr.get("image_hash"),
        }
        _LINEAGE[ad_id] = out
        return out
    except Exception as e:
        print(f"[lumen-ai] lineage lookup error for ad {ad_id}: {e}")
        return None


def backfill_ad_lineage(limit=200):
    """Fill in campaign/ad set for clicks captured while the API was unreachable.

    Attribution capture must never depend on a Graph call succeeding in the moment —
    the click id is unrecoverable, the lineage is not. So capture writes the row
    immediately and this repairs it afterwards. Called from the CAPI status endpoint,
    and safe to call as often as you like.
    """
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT ad_id FROM wa_ctwa_clicks "
            "WHERE ad_id IS NOT NULL AND campaign_id IS NULL LIMIT ?", (limit,)
        ).fetchall()
        fixed = 0
        for row in rows:
            lin = _resolve_ad_lineage(row["ad_id"])
            if not lin or not lin.get("campaign_id"):
                continue
            conn.execute(
                "UPDATE wa_ctwa_clicks SET ad_name=?, adset_id=?, adset_name=?, "
                "campaign_id=?, campaign_name=?, resolved_at=CURRENT_TIMESTAMP "
                "WHERE ad_id=? AND campaign_id IS NULL",
                (lin["ad_name"], lin["adset_id"], lin["adset_name"],
                 lin["campaign_id"], lin["campaign_name"], row["ad_id"]))
            fixed += 1
        conn.commit()
        if fixed:
            print(f"[lumen-ai] lineage backfilled for {fixed} ad(s)")
        return fixed
    except Exception as e:
        print(f"[lumen-ai] lineage backfill error: {e}")
        return 0
    finally:
        conn.close()


def get_attribution(wa_id):
    """Everything we know about where this conversation came from: click id, ad,
    ad set, campaign. This is what the CAPI dispatcher and the merchant report read."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT ctwa_clid, ad_id, ad_name, adset_id, adset_name, campaign_id, "
            "campaign_name, product, seen_at FROM wa_ctwa_clicks "
            "WHERE wa_id = ? ORDER BY seen_at DESC LIMIT 1", (wa_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _handle_referral(wa_id, msg):
    """Record the click-to-WhatsApp referral: the click id, the ad, and the product.

    The click id is written FIRST and unconditionally, before any product lookup can
    fail. The previous version returned early when the ad name did not resolve to a
    known product, which threw away the attribution along with it — a product we
    cannot name is still a sale we can attribute, and the ad map goes stale every time
    someone launches an ad with a new naming convention.
    """
    ref = msg.get("referral") or {}
    ad_id = str(ref.get("source_id") or "")
    clid = ref.get("ctwa_clid") or ""
    if not ad_id and not clid:
        return None

    # Resolve the campaign BEFORE the insert where possible, but never let a failed
    # lookup stop the write — the click id is the irreplaceable part and
    # backfill_ad_lineage() repairs the rest later.
    lin = _resolve_ad_lineage(ad_id) or {}

    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO wa_ctwa_clicks "
            "(wa_id, ctwa_clid, ad_id, ad_name, adset_id, adset_name, campaign_id, "
            " campaign_name, source_type, headline, source_url, ad_body, resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wa_id, clid or None, ad_id or None, lin.get("ad_name"),
             lin.get("adset_id"), lin.get("adset_name"), lin.get("campaign_id"),
             lin.get("campaign_name"), ref.get("source_type"),
             (ref.get("headline") or "")[:300],
             (ref.get("source_url") or "")[:500],
             (ref.get("body") or "")[:500],
             time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
             if lin.get("campaign_id") else None))
        if clid:
            conn.execute(
                "UPDATE wa_contacts SET ctwa_clid = ?, ctwa_clid_at = CURRENT_TIMESTAMP "
                "WHERE wa_id = ?", (clid, wa_id))
        conn.commit()
    except Exception as e:
        print(f"[lumen-ai] ctwa capture error for {wa_id}: {e}")
    finally:
        conn.close()

    if clid:
        camp = lin.get("campaign_name") or lin.get("campaign_id") or "campaign unresolved"
        print(f"[lumen-ai] ctwa_clid captured for {wa_id} — ad {ad_id or '?'} / {camp}")
    elif ad_id:
        # Organic-looking referral, or an ad format that does not carry a click id.
        # Worth a line in the log because a run of these means broken attribution.
        print(f"[lumen-ai] referral ad {ad_id} for {wa_id} with NO ctwa_clid")

    if not ad_id:
        return None
    # 0) The verified map: this exact ad, checked from its frames.
    # 1) The ad's OWN structure: its video/image (verified), ad set id, campaign id,
    #    then titles. Reference this over anything the click text claims.
    how = None
    product = PRODUCT_BY_AD.get(ad_id)
    if product:
        how = "verified"
    else:
        product, how = _product_from_lineage(lin)
    # 2) Ad-name map (also structural), then 3) the ad copy Meta shipped, last.
    if not product:
        product = _refresh_ad_map().get(ad_id); how = "ad_name" if product else None
    if not product:
        product = _product_from_text(
            f"{ref.get('headline') or ''} {ref.get('body') or ''} {ref.get('source_url') or ''}")
        how = "ad_copy" if product else None
    threading.Thread(target=_register_ad, args=(ad_id, product, how, lin), daemon=True).start()
    if not product:
        print(f"[lumen-ai] referral ad {ad_id}: product UNKNOWN "
              f"(adset={lin.get('adset_id')} camp={lin.get('campaign_id')} "
              f"name={lin.get('adset_name')!r})")
        return None

    conn = _conn()
    conn.execute("UPDATE wa_contacts SET product = ?, product_ad_id = ? WHERE wa_id = ?",
                 (product, ad_id, wa_id))
    conn.execute("UPDATE wa_ctwa_clicks SET product = ? WHERE wa_id = ? AND product IS NULL",
                 (product, wa_id))
    conn.commit()
    conn.close()
    print(f"[lumen-ai] referral ad {ad_id} -> product {product} ({how}) for {wa_id}")
    return product


def get_ctwa_clid(wa_id):
    """Most recent click id for a contact, or None. Used by the CAPI dispatcher."""
    conn = _conn()
    try:
        row = conn.execute("SELECT ctwa_clid FROM wa_contacts WHERE wa_id = ?",
                           (wa_id,)).fetchone()
        return (row["ctwa_clid"] if row else None) or None
    finally:
        conn.close()


def _reset_conversation(wa_id):
    """Wipe one thread back to nothing: messages, attribution, queued events, and the
    contact's own flags. Used by the /reset test command and the admin endpoint."""
    conn = _conn()
    try:
        for table in ("wa_messages", "wa_ctwa_clicks", "wa_capi_events"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE wa_id = ?", (wa_id,))
            except Exception:
                pass
        conn.execute(
            "UPDATE wa_contacts SET status='active', greeted=0, agent_ok=0, "
            "human_snooze_until=NULL, product=NULL, product_ad_id=NULL, "
            "ctwa_clid=NULL, ctwa_clid_at=NULL, last_lat=NULL, last_lng=NULL, "
            "last_location_text=NULL WHERE wa_id = ?", (wa_id,))
        conn.commit()
    except Exception as e:
        print(f"[lumen-ai] reset failed for {wa_id}: {e}")
    finally:
        conn.close()
    print(f"[lumen-ai] conversation reset for {wa_id}")


def _mark_agent_eligible(wa_id, why):
    conn = _conn()
    cur = conn.execute("UPDATE wa_contacts SET agent_ok = 1 WHERE wa_id = ? AND "
                       "COALESCE(agent_ok, 0) = 0", (wa_id,))
    conn.commit()
    conn.close()
    if cur.rowcount:
        print(f"[lumen-ai] {wa_id}: agent eligible ({why})")


def _save_location(wa_id, lat, lng, text):
    conn = _conn()
    conn.execute("UPDATE wa_contacts SET last_lat = ?, last_lng = ?, last_location_text = ? "
                 "WHERE wa_id = ?", (lat, lng, text, wa_id))
    conn.commit()
    conn.close()


def _upsert_contact(wa_id, *, profile_name=None, via_phone_id=None):
    conn = _conn()
    conn.execute("INSERT INTO wa_contacts (wa_id, profile_name) VALUES (?, ?) ON CONFLICT(wa_id) DO NOTHING",
                 (wa_id, profile_name))
    if via_phone_id:
        # Which of our numbers this person reached us on. Replies must go back out the
        # same way — answering a staging tester from the client's live number would be
        # both confusing and, on a client number, genuinely damaging.
        conn.execute("UPDATE wa_contacts SET via_phone_id = ? WHERE wa_id = ?",
                     (str(via_phone_id), wa_id))
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
    """Validate against the MK7 messaging app secret — the app this WABA is
    subscribed to (verified 23.09: subscribed_apps returns MK7 messaging only). Used as the SECOND check in app.py's
    webhook route (after the MK7 app secret), so unlike the MK7 profile this one
    returns False when unconfigured — a missing secret must not accept traffic."""
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


# ── Sending ──────────────────────────────────────────────────────────────────
def _phone_id_for(wa_id):
    """The number this contact reached us on, falling back to the live Lumen Ai number."""
    try:
        conn = _conn()
        try:
            row = conn.execute("SELECT via_phone_id FROM wa_contacts WHERE wa_id = ?",
                               (wa_id,)).fetchone()
        finally:
            conn.close()
        if row and row["via_phone_id"]:
            return str(row["via_phone_id"])
    except Exception:
        pass
    return LUMENAI_PHONE_NUMBER_ID


def _graph_post(payload, phone_id=None):
    phone_id = phone_id or _phone_id_for(payload.get("to") or "")
    if not WHATSAPP_ACCESS_TOKEN or not phone_id:
        print("[lumen-ai] WARNING: token or phone number id not set — cannot send")
        return None
    url = f"{GRAPH_BASE}/{phone_id}/messages"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            print(f"[lumen-ai] send failed {r.status_code}: {json.dumps(data)[:500]}")
            return None
        return data
    except Exception as e:
        print(f"[lumen-ai] send exception: {e}")
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
    print(f"[lumen-ai] send_text {to_wa_id}: {('sent wamid=' + str(wamid)) if data else 'FAILED'} body={body[:60]!r}")
    return data


# ── Recovery / re-engagement sweep ────────────────────────────────────────────
# WhatsApp only allows a free-form message within 24h of the customer's last
# message. This sweep uses that window: exactly one recovery message per contact,
# fired ~20-23h after their last inbound (their last chance before it shuts).
#   - never truly replied (only the ad opener) -> offer 10$ if they order today
#   - a real conversation that went quiet      -> a light "still interested?"
REENGAGE_ON = os.environ.get("LUMENAI_REENGAGE", "0") not in ("0", "false", "False", "")
REENGAGE_MIN_H = float(os.environ.get("LUMENAI_REENGAGE_MIN_H", "20"))
REENGAGE_MAX_H = float(os.environ.get("LUMENAI_REENGAGE_MAX_H", "23"))
REENGAGE_INTERVAL = int(os.environ.get("LUMENAI_REENGAGE_INTERVAL", "1800"))  # 30 min

_ARABIC_RE = re.compile(r"[؀-ۿ]")

REENGAGE_MSG = {
    "noreply": {
        "ar": "لسا مهتم؟ إذا طلبت اليوم بصير السعر 10$ بدل 12$ (زائد 4$ توصيل).",
        "en": "Still interested? Order today and it's 10$ instead of 12$ (+ 4$ delivery).",
    },
    "died": {
        "ar": "لسا مهتم؟",
        "en": "Still interested?",
    },
}


def _genuine_inbound_count(conn, wa_id):
    """Real customer messages, excluding the ad opener and media/system placeholders."""
    rows = conn.execute(
        "SELECT body, msg_type FROM wa_messages WHERE wa_id=? AND direction='in'", (wa_id,)
    ).fetchall()
    n = 0
    for r in rows:
        b = (r["body"] or "")
        if r["msg_type"] in ("reaction", "system", "unsupported", "ephemeral"):
            continue
        if b.startswith("[") and b.endswith("]"):
            continue
        if any(mk in b.lower() for mk in AD_PREFILL_MARKERS):
            continue
        n += 1
    return n


def _last_inbound_lang(conn, wa_id):
    r = conn.execute("SELECT body FROM wa_messages WHERE wa_id=? AND direction='in' "
                     "ORDER BY id DESC LIMIT 1", (wa_id,)).fetchone()
    return "ar" if (r and _ARABIC_RE.search(r["body"] or "")) else "en"


def _reengage_candidates(conn):
    """Contacts inside the 20-23h band who never got a recovery message."""
    return conn.execute(
        "SELECT wa_id, last_inbound_at FROM wa_contacts "
        "WHERE COALESCE(agent_ok,0)=1 AND status='active' AND reengaged_at IS NULL "
        "AND (human_snooze_until IS NULL OR human_snooze_until < strftime('%s','now')) "
        "AND last_inbound_at IS NOT NULL "
        "AND (julianday('now') - julianday(last_inbound_at))*24 BETWEEN ? AND ?",
        (REENGAGE_MIN_H, REENGAGE_MAX_H),
    ).fetchall()


# ── Re-engagement gate (added 07.09.2026) ─────────────────────────────────────
# The sweep used to fire "still interested?" at anyone still marked active, which
# included people who had already ordered: MK closes most sales from her phone, so
# nothing ever flips those threads to handed_off. Two layers now sit in front of
# every send, and BOTH must clear:
#   1. hard rules on the thread (any sign of an order, a walk-away, or an unanswered
#      customer message) -> never send;
#   2. the model reads the whole thread and says what happened; only an explicit
#      "safe to nudge" verdict sends. Any failure fails closed.
# Blocked contacts are stamped so they are never re-judged; the conversation stops.
REENGAGE_JUDGE_MODEL = os.environ.get("LUMENAI_REENGAGE_JUDGE_MODEL", "") or AGENT_MODEL

REENGAGE_JUDGE_PROMPT = """You review a WhatsApp sales thread for a small Lebanese online shop (Lumen Ai). \
Messages marked CUSTOMER are from the customer. Messages marked SHOP are from the shop \
(the owner typing from her phone, or the shop's assistant). Customers write in English, \
Arabic script, Lebanese arabizi (Latin letters with numbers, e.g. "badde we7de") or French.

The shop wants to send this one-line nudge to people who went quiet: "Still interested?"

Decide whether that nudge is appropriate. Answer with exactly one word:
PURCHASED  - the customer ordered, gave a location/address/name/phone for delivery, \
confirmed an order, or the shop confirmed an order. Any sign at all that a sale happened \
or is in progress. When in doubt, choose this.
CLOSED     - the customer said no, not interested, cancel, later, or the conversation is \
otherwise finished and a nudge would be unwelcome.
NEEDS_REPLY - the customer's last message is a real question or request that nobody \
answered. They need a proper answer, not a nudge.
NUDGE_OK   - the shop answered everything, the customer simply stopped replying, and \
there is no sign of an order. Only this answer allows the nudge.

Thread:
"""


def _thread_for_judge(conn, wa_id, limit=60):
    rows = conn.execute(
        "SELECT direction, body, msg_type FROM wa_messages WHERE wa_id=? "
        "ORDER BY id DESC LIMIT ?", (wa_id, limit)).fetchall()
    lines = []
    for r in reversed(rows):
        who = "CUSTOMER" if r["direction"] == "in" else "SHOP"
        body = (r["body"] or "").strip()
        if not body:
            body = f"[{r['msg_type']} message]"
        lines.append(f"{who}: {body}")
    return "\n".join(lines)


def _reengage_hard_block(conn, wa_id):
    """Return a reason string if the thread must never get a nudge, else None."""
    rows = conn.execute(
        "SELECT direction, body, msg_type FROM wa_messages WHERE wa_id=? ORDER BY id",
        (wa_id,)).fetchall()
    msgs = [dict(r) for r in rows]
    if not msgs:
        return "empty thread"
    try:
        from . import intent
        state = intent.classify(msgs, wa_id=wa_id)[0]
    except Exception as e:
        return f"classifier failed ({e})"
    if state in ("COMMITTED", "INTENT"):
        return f"order signal ({state})"
    if state in ("LOST", "DISQUALIFIED"):
        return f"walked away ({state})"
    asked_location = False
    for m in msgs:
        body = (m.get("body") or "").strip()
        low = body.lower()
        if m["direction"] == "in":
            if m.get("msg_type") == "location" or "[location" in low:
                return "customer sent a location pin"
            if asked_location and body and not any(mk in low for mk in AD_PREFILL_MARKERS):
                return "customer answered the shop's location request"
        else:
            if re.match(r"^\s*(done|confirmed|تم|تمام)\s*[.!]?\s*$", body, re.I):
                return "shop confirmed the order"
            try:
                from . import intent
                if intent.ASK_LOCATION.search(body):
                    asked_location = True
            except Exception:
                pass
    if msgs[-1]["direction"] == "in":
        last = (msgs[-1].get("body") or "")
        if not any(mk in last.lower() for mk in AD_PREFILL_MARKERS):
            return "customer's last message is unanswered"
    return None


def _reengage_judge(conn, wa_id):
    """Ask the model what happened in the thread. Returns one of PURCHASED / CLOSED /
    NEEDS_REPLY / NUDGE_OK, or 'ERROR:<why>'. Anything but NUDGE_OK blocks."""
    if not ANTHROPIC_API_KEY:
        return "ERROR:no api key"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=REENGAGE_JUDGE_MODEL, max_tokens=10,
            messages=[{"role": "user",
                       "content": REENGAGE_JUDGE_PROMPT + _thread_for_judge(conn, wa_id)}])
        text = "".join(getattr(b, "text", "") for b in resp.content).strip().upper()
        for v in ("PURCHASED", "NEEDS_REPLY", "CLOSED", "NUDGE_OK"):
            if v in text:
                return v
        return f"ERROR:unparsed {text[:30]!r}"
    except Exception as e:
        return f"ERROR:{repr(e)[:80]}"


def reengage_decide(conn, wa_id):
    """(send: bool, reason: str). Both gates must clear for send to be True."""
    block = _reengage_hard_block(conn, wa_id)
    if block:
        return False, f"rule: {block}"
    verdict = _reengage_judge(conn, wa_id)
    if verdict == "NUDGE_OK":
        return True, "judge: NUDGE_OK"
    return False, f"judge: {verdict}"


def reengage_sweep(dry=False):
    """Nudge everyone in the recovery band who clears both gates, once. Blocked
    contacts are stamped too, so a buyer is never re-examined. Returns the list
    considered, each with its decision."""
    conn = _conn()
    out = []
    for r in _reengage_candidates(conn):
        wa_id = r["wa_id"]
        kind = "died" if _genuine_inbound_count(conn, wa_id) >= 1 else "noreply"
        lang = _last_inbound_lang(conn, wa_id)
        msg = REENGAGE_MSG[kind][lang]
        send, reason = reengage_decide(conn, wa_id)
        out.append({"wa_id": wa_id, "kind": kind, "lang": lang, "msg": msg,
                    "send": send, "reason": reason,
                    "last_inbound_at": r["last_inbound_at"]})
        if dry:
            continue
        stamp = kind if send else f"blocked:{reason[:60]}"
        # Atomic claim — whichever worker stamps first acts; others skip.
        cur = conn.execute("UPDATE wa_contacts SET reengaged_at=CURRENT_TIMESTAMP, "
                           "reengage_kind=? WHERE wa_id=? AND reengaged_at IS NULL",
                           (stamp, wa_id))
        conn.commit()
        if cur.rowcount != 1:
            continue
        if send:
            send_text(wa_id, msg)
            print(f"[lumen-ai-reengage] {wa_id}: nudged ({kind}/{lang}) — {reason}")
        else:
            print(f"[lumen-ai-reengage] {wa_id}: NOT nudged — {reason}")
    conn.close()
    return out


def _claim_sweep():
    """True for exactly one worker per interval."""
    import time as _t
    now = _t.time()
    conn = _conn()
    conn.execute("INSERT OR IGNORE INTO wa_sweep_lock(id, last_run) VALUES(1, 0)")
    cur = conn.execute("UPDATE wa_sweep_lock SET last_run=? WHERE id=1 AND ?-last_run > ?",
                       (now, now, REENGAGE_INTERVAL - 5))
    conn.commit()
    conn.close()
    return cur.rowcount == 1


_sweeper_started = False
_sweeper_guard = threading.Lock()


def ensure_sweeper():
    """Start the recovery loop once per worker process (post-fork safe)."""
    global _sweeper_started
    if _sweeper_started or not REENGAGE_ON:
        return
    with _sweeper_guard:
        if _sweeper_started:
            return
        _sweeper_started = True

    def _loop():
        import time as _t
        while True:
            try:
                if _claim_sweep():
                    seen = reengage_sweep(dry=False)
                    if seen:
                        n = sum(1 for x in seen if x["send"])
                        print(f"[lumen-ai-reengage] considered {len(seen)}, nudged {n}, "
                              f"blocked {len(seen) - n}")
            except Exception as e:
                print(f"[lumen-ai-reengage] sweep error: {e}")
            _t.sleep(REENGAGE_INTERVAL)

    threading.Thread(target=_loop, daemon=True).start()
    print("[lumen-ai-reengage] sweeper started")


# ── Notifications ────────────────────────────────────────────────────────────
def _notify_team(subject, html):
    if not RESEND_API_KEY or not NOTIFY_EMAILS:
        return
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "Lumen Ai Agent <notifications@lumenmarketing.co>",
                  "to": NOTIFY_EMAILS, "subject": subject, "html": html},
            timeout=10,
        )
    except Exception as e:
        print(f"[lumen-ai] notify failed: {e}")


def _alert_handoff(wa_id, reason="", draft=None):
    """Tell MK a conversation needs her: WhatsApp ping (with a one-tap deep
    link to the customer chat) plus the email. Best effort — a failed WhatsApp
    ping never blocks the email, and neither ever raises into the webhook."""
    contact = get_contact(wa_id) or {}
    name = contact.get("profile_name") or wa_id
    product = contact.get("product") or "unknown product"
    last = _last_inbound_body(wa_id) or ""
    loc = ""
    if contact.get("last_lat") is not None:
        loc = (f"\nLocation: https://maps.google.com/?q="
               f"{contact.get('last_lat')},{contact.get('last_lng')}")
        if contact.get("last_location_text"):
            loc += f" ({contact.get('last_location_text')})"

    body = (f"Lumen Ai handoff needed\n\n"
            f"Customer: {name} (+{wa_id})\n"
            f"Product: {product}\n"
            f"Reason: {reason or 'agent handed off'}\n"
            f"Last message: {last[:200]}{loc}\n\n"
            f"Open chat: https://wa.me/{wa_id}")
    if draft:
        body += f"\n\nAgent draft (not sent):\n{draft[:400]}"

    for to in HANDOFF_WA_NUMBERS:
        try:
            r = requests.post(
                f"{GRAPH_BASE}/{LUMEN_NOTIFY_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                         "Content-Type": "application/json"},
                json={"messaging_product": "whatsapp", "to": to,
                      "type": "text", "text": {"body": body[:3900]}},
                timeout=10,
            )
            if r.status_code >= 300:
                print(f"[lumen-ai] handoff ping to {to} failed {r.status_code}: {r.text[:160]}")
            else:
                print(f"[lumen-ai] handoff ping sent to {to}")
        except Exception as e:
            print(f"[lumen-ai] handoff ping to {to} error: {e}")

    _notify_team(
        f"Lumen Ai WhatsApp — handoff: {name} ({product})",
        f"<p><b>Reason:</b> {reason or 'agent handed off'}</p>"
        f"<p><b>Product:</b> {product}</p>"
        + (f"<p><b>Location:</b> <a href='https://maps.google.com/?q="
           f"{contact.get('last_lat')},{contact.get('last_lng')}'>map</a></p>" if loc else "")
        + f"<p><b>Open chat:</b> <a href='https://wa.me/{wa_id}'>wa.me/{wa_id}</a></p>"
        + (f"<p><b>Agent draft (not sent):</b><br>{draft}</p>" if draft else "")
        + f"<hr>{_conversation_html(wa_id)}",
    )


def _admin_monitor(wa_id, customer_msg, agent_reply, handoff=False, note=""):
    """Live 'Agent Monitoring' email — one per agent action. Never raises."""
    if not (MONITOR_ON and RESEND_API_KEY and MONITOR_EMAILS):
        return
    try:
        contact = get_contact(wa_id) or {}
        name = contact.get("profile_name") or f"+{wa_id}"
        product = contact.get("product") or "unknown (no ad referral)"
        turns = len(_history(wa_id))
        loc = ""
        if contact.get("last_lat") is not None:
            loc = (f"<a href='https://maps.google.com/?q={contact['last_lat']},"
                   f"{contact['last_lng']}'>{contact['last_lat']}, {contact['last_lng']}</a>")
            if contact.get("last_location_text"):
                loc += f" &middot; {contact['last_location_text']}"

        if handoff:
            state, colour = "HANDED OFF TO MK", "#c9a227"
        elif agent_reply:
            state, colour = "AGENT REPLIED", "#12a090"
        else:
            state, colour = "NO REPLY SENT", "#6f737a"

        rows = "".join(
            f"<tr><td style='padding:4px 10px;color:#6f737a;white-space:nowrap'>{k}</td>"
            f"<td style='padding:4px 10px'>{v}</td></tr>"
            for k, v in (("Customer", name), ("Product", product),
                         ("Turns in thread", turns),
                         ("Location", loc or "not given yet"),
                         ("Note", note or "&mdash;")) if v not in (None, ""))

        html = (
            f"<div style=\"font-family:Inter,Helvetica,Arial,sans-serif;color:#16181d\">"
            f"<p style='font-size:11px;letter-spacing:.12em;text-transform:uppercase;"
            f"color:{colour};font-weight:700;margin:0 0 10px'>{state}</p>"
            f"<table style='border-collapse:collapse;font-size:13px;margin-bottom:16px'>{rows}</table>"
            f"<p style='margin:0 0 4px;color:#6f737a;font-size:12px'>Customer said</p>"
            f"<div style='background:#f5f5f3;border-radius:8px;padding:10px 14px;margin-bottom:12px'>"
            f"{(customer_msg or '&mdash;')}</div>"
            f"<p style='margin:0 0 4px;color:#6f737a;font-size:12px'>Agent sent</p>"
            f"<div style='background:#eaf5f3;border-radius:8px;padding:10px 14px;margin-bottom:16px'>"
            f"{(agent_reply or '<i>nothing &mdash; stayed silent</i>')}</div>"
            f"<p style='font-size:12px'><a href='https://wa.me/{wa_id}'>Open chat</a> &middot; "
            f"<a href='https://mk7media.com/lumen-ai-wa/debug'>Agent debug</a></p>"
            f"<hr style='border:0;border-top:1px solid #e4e1d8'>{_conversation_html(wa_id)}</div>")

        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "Lumen Ai Agent Monitoring <notifications@lumenmarketing.co>",
                  "to": MONITOR_EMAILS,
                  "subject": f"[{state}] {name} — {product}",
                  "html": html},
            timeout=10,
        )

        # WhatsApp mirror of the same event
        if MONITOR_WA and WHATSAPP_ACCESS_TOKEN:
            loc_txt = ""
            if contact.get("last_lat") is not None:
                loc_txt = (f"\nLocation: https://maps.google.com/?q="
                           f"{contact['last_lat']},{contact['last_lng']}")
            wa_body = (f"{state}\n"
                       f"{name} · {product} · turn {turns}\n\n"
                       f"Them: {(customer_msg or '-')[:220]}\n"
                       f"Agent: {(agent_reply or '(silent)')[:220]}"
                       f"{loc_txt}"
                       + (f"\nNote: {note}" if note else "")
                       + f"\n\nhttps://wa.me/{wa_id}")
            for to in MONITOR_WA:
                try:
                    requests.post(
                        f"{GRAPH_BASE}/{LUMEN_NOTIFY_PHONE_ID}/messages",
                        headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                                 "Content-Type": "application/json"},
                        json={"messaging_product": "whatsapp", "to": to,
                              "type": "text", "text": {"body": wa_body[:3900]}},
                        timeout=10,
                    )
                except Exception as e:
                    print(f"[lumen-ai] monitor WA to {to} failed: {e}")
    except Exception as e:
        print(f"[lumen-ai] monitor email failed: {e}")


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
def _handle_history_sync(value):
    """COEXISTENCE history sync: after MK scans the onboarding QR with
    chat-history sharing enabled, Meta pushes her past conversations (up to
    ~6 months) in chunked `history` webhook payloads. Pure receive-side:
    nothing is sent, nothing on the phone is touched. We raw-dump every
    payload (lossless, the push only happens once) and best-effort parse
    messages into wa_messages with their ORIGINAL timestamps. Historical
    messages NEVER trigger agent replies."""
    conn = _conn()
    conn.execute("INSERT INTO wa_history_raw (payload) VALUES (?)",
                 (json.dumps(value, ensure_ascii=False),))
    conn.commit()
    conn.close()

    n_msgs = 0
    for chunk in value.get("history") or []:
        phase = (chunk.get("metadata") or {}).get("phase")
        for thread in chunk.get("threads") or []:
            wa_id = "".join(ch for ch in str(thread.get("id") or "") if ch.isdigit())
            if not wa_id or wa_id == LUMENAI_BUSINESS_NUMBER:
                continue
            _upsert_contact(wa_id)
            for m in thread.get("messages") or []:
                sender = "".join(ch for ch in str(m.get("from") or "") if ch.isdigit())
                direction = "out_app" if sender == LUMENAI_BUSINESS_NUMBER else "in"
                body = _extract_text(m)
                if body is None:
                    body = f"[{m.get('type') or 'unknown'} message]"
                ts = m.get("timestamp")
                conn = _conn()
                cur = conn.execute(
                    "INSERT OR IGNORE INTO wa_messages "
                    "(wa_id, direction, msg_type, body, wamid, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'history', "
                    "COALESCE(datetime(?, 'unixepoch'), CURRENT_TIMESTAMP))",
                    (wa_id, direction, m.get("type") or "text", body, m.get("id"),
                     ts if ts and str(ts).isdigit() else None),
                )
                n_msgs += cur.rowcount
                conn.commit()
                conn.close()
        print(f"[lumen-ai] history sync: phase {phase}, {n_msgs} messages stored so far")
    print(f"[lumen-ai] history sync payload processed: {n_msgs} new messages")


def _handle_state_sync(value):
    """COEXISTENCE contact sync (smb_app_state_sync): MK's saved contact
    names from her phone. Read-only upsert of names into wa_contacts."""
    n = 0
    for item in value.get("state_sync") or []:
        if (item.get("type") or "") != "contact":
            continue
        contact = item.get("contact") or {}
        wa_id = "".join(ch for ch in str(contact.get("phone_number") or "") if ch.isdigit())
        name = contact.get("full_name") or contact.get("first_name")
        if wa_id and name:
            _upsert_contact(wa_id, profile_name=name)
            n += 1
    print(f"[lumen-ai] state sync: {n} contact names updated")


def is_lumen_ai_event(value):
    """True when this webhook change belongs to the FGC number, or to the staging
    number. Dormant (always False) until a phone number id is configured."""
    meta = value.get("metadata") or {}
    pid = str(meta.get("phone_number_id") or "")
    if not pid:
        return False
    return pid in {str(x) for x in (LUMENAI_PHONE_NUMBER_ID, LUMENAI_TEST_PHONE_NUMBER_ID) if x}


def handle_webhook(payload):
    """Handle a webhook payload (only FGC-number changes; app.py routes us)."""
    ensure_sweeper()  # lazy-start the recovery loop once per worker (no scheduler exists)
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            if not is_lumen_ai_event(value):
                continue

            # COEXISTENCE onboarding syncs (one-time pushes after QR scan).
            # Handled fully here; historical messages never reach the reply path.
            if value.get("history"):
                _handle_history_sync(value)
                continue
            if value.get("state_sync"):
                _handle_state_sync(value)
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
                low = (body or "").lower()
                if low and any(g in low for g in GREETING_MARKERS):
                    if _claim_greeting(to_id):
                        print(f"[lumen-ai] app echo -> {to_id}: automated greeting sent, agent now armed")
                    else:
                        # We already greeted from the server. The app greeting is still
                        # switched on in MK's phone, so this customer saw two. Log loudly.
                        print(f"[lumen-ai] app echo -> {to_id}: DOUBLE GREETING — app greeting fired "
                              "after the server one; switch the app greeting off")
                else:
                    snooze_contact(to_id)
                    print(f"[lumen-ai] app echo -> {to_id}: MK replied from phone, snoozing agent {HUMAN_SNOOZE_HOURS}h")

            profiles = {}
            for c in value.get("contacts", []) or []:
                wa_id = c.get("wa_id")
                name = (c.get("profile") or {}).get("name")
                if wa_id:
                    profiles[wa_id] = name

            via = str((value.get("metadata") or {}).get("phone_number_id") or "")
            for msg in value.get("messages", []) or []:
                _handle_inbound_message(msg, profiles, via_phone_id=via)


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
    if t == "location":
        loc = msg.get("location") or {}
        lat, lng = loc.get("latitude"), loc.get("longitude")
        label = ", ".join(x for x in (loc.get("name"), loc.get("address")) if x)
        pin = f"[location pin {lat},{lng}]" if lat is not None else "[location pin]"
        return f"{pin} {label}".strip()
    return None


def _handle_inbound_message(msg, profiles, via_phone_id=None):
    wa_id = msg.get("from")
    wamid = msg.get("id")
    if not wa_id:
        return
    # Never let the shop's own number become a contact. Some coexistence payloads put
    # the business's outbound messages in the `messages` array rather than in
    # `message_echoes`, and without this the agent creates a contact for itself, files
    # its own replies as customer messages, and can end up answering itself. The
    # history importer has always guarded this; the live path did not.
    if wa_id in {n for n in (LUMENAI_BUSINESS_NUMBER, LUMENAI_TEST_BUSINESS_NUMBER) if n}:
        print(f"[lumen-ai] ignoring self-addressed message {wamid}")
        return

    _upsert_contact(wa_id, profile_name=profiles.get(wa_id), via_phone_id=via_phone_id)
    _handle_referral(wa_id, msg)

    text = _extract_text(msg)
    msg_type = msg.get("type") or "unknown"
    body = text if text is not None else f"[{msg_type} message]"

    # Test commands, allow-listed numbers only. Resetting from inside the chat is what
    # makes iterating on the agent practical: run a conversation to its end, type
    # /reset, and the next message starts a genuinely fresh thread — no laptop, no
    # admin page, no leftover state quietly changing the next result.
    if text and wa_id in LUMENAI_TESTERS:
        cmd = text.strip().lower()
        if cmd in ("/reset", "reset", "/clear"):
            _reset_conversation(wa_id)
            send_text(wa_id, "Thread cleared. Next message starts fresh.")
            return
        if cmd in ("/state", "/status"):
            try:
                from . import intent
                st, ev, human = intent.classify_wa(wa_id, DB_PATH)
                att = get_attribution(wa_id) or {}
                send_text(wa_id, (
                    f"state: {st}\n"
                    f"evidence: {ev or '—'}\n"
                    f"needs human: {'yes' if human else 'no'}\n"
                    f"campaign: {att.get('campaign_name') or '—'}\n"
                    f"click id: {'yes' if att.get('ctwa_clid') else 'no'}"))
            except Exception as e:
                send_text(wa_id, f"state check failed: {e}")
            return

    if msg_type in ("reaction", "system", "unsupported", "ephemeral"):
        if msg_type == "reaction":
            emoji = (msg.get("reaction") or {}).get("emoji", "")
            body = f"[reacted {emoji}]".strip()
        _record_message(wa_id, "in", msg_type, body, wamid=wamid)
        return

    # Eligibility: an ad click (referral) or the ad's prefill greeting means this
    # conversation started with us and we hold the whole thread.
    if (msg.get("referral") or {}).get("source_id"):
        _mark_agent_eligible(wa_id, "ad referral")
    if text and any(mk in text.lower() for mk in AD_PREFILL_MARKERS):
        _mark_agent_eligible(wa_id, "ad prefill greeting")

    pf_product = _prefill_product(text) if text else None
    if pf_product:
        # The CTA they tapped names the product. Overrides the ad/creative lookup.
        conn = _conn()
        conn.execute("UPDATE wa_contacts SET product = ? WHERE wa_id = ?", (pf_product, wa_id))
        conn.commit(); conn.close()
        ref_ad = str(((msg.get("referral") or {}).get("source_id")) or "")
        if ref_ad:
            threading.Thread(target=_register_ad, args=(ref_ad, pf_product, "prefill", None), daemon=True).start()
        print(f"[lumen-ai] inbound {wa_id}: CTA prefill names the product -> {pf_product}")

    if msg_type == "location":
        loc = msg.get("location") or {}
        _save_location(wa_id, loc.get("latitude"), loc.get("longitude"),
                       ", ".join(x for x in (loc.get("name"), loc.get("address")) if x))

    is_new = _record_message(wa_id, "in", msg_type, body, wamid=wamid)
    if not is_new:
        return

    # Re-read intent and dispatch conversion events. On its own thread and wrapped,
    # because a customer waiting on a reply must never pay for a Graph call — and
    # because an attribution bug must never be able to take the sales agent down.
    def _intent_pass():
        try:
            from . import intent, capi_bm
            intent.on_conversation_update(wa_id)
            capi_bm.sweep_pending()
        except Exception as e:
            print(f"[lumen-ai-intent] pass failed for {wa_id}: {e}")
    threading.Thread(target=_intent_pass, daemon=True).start()

    contact = get_contact(wa_id) or {}
    status = contact.get("status", "active")

    if text and text.strip().lower() in OPT_OUT_WORDS:
        set_contact_status(wa_id, "opted_out")
        send_text(wa_id, "Done, you won't hear from us here again. If you ever change your mind, just message this number.")
        return

    if status == "opted_out":
        return

    opener_q = _opener_question(text) if (text and ANSWER_OPENER and AUTO_REPLY) else ""

    if text and any(mk in text.lower() for mk in AD_PREFILL_MARKERS):
        # This is the ad's canned opener. The greeting answers it: the app's if the
        # phone is on, ours otherwise (see _schedule_greeting). If they typed a real
        # question on top of it, that question is answered right after the greeting.
        scheduled = _schedule_greeting(wa_id)
        print(f"[lumen-ai] inbound {wa_id}: ad prefill — greeting handles this"
              + (" (server greeting scheduled)" if scheduled else "")
              + (f", then answering their question {opener_q[:50]!r}" if opener_q else ", agent silent"))
        if opener_q and contact.get("agent_ok"):
            threading.Thread(target=_answer_opener_async, args=(wa_id, wamid), daemon=True).start()
        return

    if not contact.get("greeted"):
        # Greeting has not gone out yet. On an ad-started thread the server now
        # guarantees that greeting goes out. A bare "hi"/"price?" is answered by the
        # greeting itself; a real question typed before it gets answered after it.
        scheduled = _schedule_greeting(wa_id)
        print(f"[lumen-ai] inbound {wa_id}: no greeting sent yet"
              + (" (server greeting scheduled)" if scheduled else "")
              + (f", then answering their question {opener_q[:50]!r}" if opener_q else ", agent silent"))
        if opener_q and contact.get("agent_ok"):
            threading.Thread(target=_answer_opener_async, args=(wa_id, wamid), daemon=True).start()
        return

    if not contact.get("agent_ok"):
        # Old lead replying to an ancient thread, or a conversation that did not
        # start from one of our ads. No reply, no alert — MK owns it in the app.
        print(f"[lumen-ai] inbound {wa_id}: {body[:60]!r} — not an ad-started thread, agent silent")
        _admin_monitor(wa_id, body, None,
                       note="Old/non-ad thread — agent deliberately silent, MK owns it")
        return

    if _is_snoozed(contact) or status == "handed_off":
        # MK owns this thread (she replied from the app recently, or the agent
        # handed off). Stay quiet — she sees the message in her app anyway.
        print(f"[lumen-ai] inbound {wa_id}: {body[:60]!r} — human owns thread (snoozed/handed_off), agent silent")
        return

    if msg_type in HANDOFF_MEDIA_TYPES:
        # Voice notes, video, photos, documents: the agent cannot read these.
        # Per Kendall: do not reply, hand straight to MK.
        print(f"[lumen-ai] inbound {wa_id}: {msg_type} — cannot read, handing off to MK")
        set_contact_status(wa_id, "handed_off")
        _alert_handoff(wa_id, reason=f"{msg_type} message the agent cannot read")
        _admin_monitor(wa_id, body, None, handoff=True,
                       note=f"{msg_type} received — agent cannot read it")
        return

    if text is None:
        print(f"[lumen-ai] inbound {wa_id}: unreadable {msg_type} — handing off")
        set_contact_status(wa_id, "handed_off")
        _alert_handoff(wa_id, reason=f"unreadable {msg_type} message")
        _admin_monitor(wa_id, body, None, handoff=True,
                       note=f"unreadable {msg_type}")
        return

    if not AUTO_REPLY:
        print(f"[lumen-ai] inbound {wa_id}: {body[:60]!r} — auto-reply disabled, notify only")
        _notify_team(
            f"Lumen Ai WhatsApp — new message from {contact.get('profile_name') or wa_id}",
            f"<p>{body}</p><hr>{_conversation_html(wa_id)}",
        )
        return

    print(f"[lumen-ai] inbound {wa_id}: {body[:60]!r} (status={status}) — spawning reply")
    threading.Thread(target=_reply_async, args=(wa_id, wamid), daemon=True).start()


_SETTLED_WORDS = ("confirmed", "confirm", "done", "تم", "تمام", "تم التأكيد")


def _returning_on_settled_thread(wa_id):
    """True when the latest inbound arrived STALE_ORDER_HOURS+ after the previous one
    AND the thread had already reached an order: a location on file, a
    Confirmed/Done/تم from us or MK, or the classifier's COMMITTED."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT direction, body, created_at FROM wa_messages WHERE wa_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 60", (wa_id,)).fetchall()
    finally:
        conn.close()
    inbound = [r for r in rows if r["direction"] == "in"]
    if len(inbound) < 2:
        return False
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        latest = time.mktime(time.strptime(inbound[0]["created_at"][:19], fmt))
        previous = time.mktime(time.strptime(inbound[1]["created_at"][:19], fmt))
    except Exception:
        return False
    if latest - previous < STALE_ORDER_HOURS * 3600:
        return False
    contact = get_contact(wa_id) or {}
    if contact.get("last_lat") is not None or contact.get("last_location_text"):
        return True
    for r in rows[1:]:
        if r["direction"] in ("out", "out_app"):
            b = (r["body"] or "").strip().lower()
            if b and any(w == b or b.startswith(w) for w in _SETTLED_WORDS):
                return True
    try:
        from . import intent
        res = intent.classify_wa(wa_id, DB_PATH)  # (state, evidence, needs_human, ...)
        if str(res[0]).upper() == "COMMITTED":
            return True
    except Exception:
        pass
    return False


_reply_locks = {}
_reply_locks_guard = threading.Lock()
_last_reply_at = {}


def _reply_lock(wa_id):
    with _reply_locks_guard:
        if wa_id not in _reply_locks:
            _reply_locks[wa_id] = threading.Lock()
        return _reply_locks[wa_id]


_greeting_pending = set()
_greeting_lock = threading.Lock()


def _claim_greeting(wa_id):
    """Atomically flip greeted 0 -> 1. True only for the one caller that won, so two
    webhook deliveries for the same thread can never produce two greetings."""
    conn = _conn()
    cur = conn.execute("UPDATE wa_contacts SET greeted = 1 WHERE wa_id = ? AND "
                       "COALESCE(greeted, 0) = 0", (wa_id,))
    conn.commit()
    conn.close()
    return bool(cur.rowcount)


def _unclaim_greeting(wa_id):
    conn = _conn()
    conn.execute("UPDATE wa_contacts SET greeted = 0 WHERE wa_id = ?", (wa_id,))
    conn.commit()
    conn.close()


def _mk_has_spoken(wa_id):
    conn = _conn()
    row = conn.execute("SELECT 1 FROM wa_messages WHERE wa_id = ? AND direction = 'out_app' "
                       "LIMIT 1", (wa_id,)).fetchone()
    conn.close()
    return bool(row)


def _schedule_greeting(wa_id):
    """Kick off the server-side greeting for an ad-started thread. Idempotent: one
    timer per contact, and nothing at all once the contact is greeted."""
    if GREETING_MODE == "off":
        return False
    contact = get_contact(wa_id) or {}
    if contact.get("greeted") or not contact.get("agent_ok"):
        return False
    if contact.get("status") in ("handed_off", "opted_out"):
        return False
    with _greeting_lock:
        if wa_id in _greeting_pending:
            return True
        _greeting_pending.add(wa_id)
    threading.Thread(target=_greet_async, args=(wa_id,), daemon=True).start()
    return True


def _answer_opener_async(wa_id, wamid):
    """Wait for the greeting to land, then answer the question the customer typed
    on top of the ad opener, as a reply to THEIR message (never unprompted)."""
    try:
        deadline = time.time() + GREETING_WAIT + 20
        while time.time() < deadline:
            contact = get_contact(wa_id) or {}
            if contact.get("greeted"):
                break
            if _is_snoozed(contact) or contact.get("status") in ("handed_off", "opted_out"):
                return
            time.sleep(1)
        else:
            print(f"[lumen-ai] opener {wa_id}: greeting never landed, not answering the opener")
            return
        time.sleep(3)
        _reply_async(wa_id, trigger_wamid=wamid, answer_opener=True)
    except Exception as e:
        print(f"[lumen-ai] opener answer error for {wa_id}: {repr(e)}")


def _greet_async(wa_id):
    try:
        if GREETING_MODE == "fallback" and GREETING_WAIT > 0:
            time.sleep(GREETING_WAIT)
        contact = get_contact(wa_id) or {}
        if contact.get("greeted"):
            print(f"[lumen-ai] greeting {wa_id}: app greeting arrived in time, ours not needed")
            return
        if _is_snoozed(contact) or contact.get("status") in ("handed_off", "opted_out"):
            print(f"[lumen-ai] greeting {wa_id}: MK already in this thread, not greeting")
            return
        if _mk_has_spoken(wa_id):
            # An older thread MK has already handled from her phone. A "$12, would
            # you like to order?" opener there would be nonsense. She keeps it.
            print(f"[lumen-ai] greeting {wa_id}: MK has spoken in this thread before, not greeting")
            return
        if not _claim_greeting(wa_id):
            return
        data = send_text(wa_id, GREETING_TEXT)
        if not data:
            # Send failed. Give the claim back so a later app greeting can still arm us.
            _unclaim_greeting(wa_id)
            print(f"[lumen-ai] greeting {wa_id}: send FAILED, contact left ungreeted")
            return
        # The greeting is the only thing we send unprompted. Whatever they typed
        # before it, the agent speaks again only when they reply to this.
        print(f"[lumen-ai] greeting {wa_id}: server greeting sent ({GREETING_MODE}), "
              "agent now armed, waiting for their reply")
    except Exception as e:
        print(f"[lumen-ai] greeting error for {wa_id}: {repr(e)}")
    finally:
        with _greeting_lock:
            _greeting_pending.discard(wa_id)


def _reply_async(wa_id, trigger_wamid=None, answer_opener=False):
    lock = _reply_lock(wa_id)
    # Wait for an in-flight reply instead of dropping this one. The reply already
    # running read the thread before this message existed; once it finishes, the
    # newer-inbound check below decides which thread answers, so a follow-up sent
    # while we were typing is answered instead of lost.
    if not lock.acquire(timeout=90):
        print(f"[lumen-ai] _reply_async {wa_id}: reply lock busy for 90s, giving up on this one")
        return
    try:
        # Burst window: three messages in a row get ONE answer, to the latest. Wait
        # the window out rather than dropping (see DEBOUNCE_SECONDS).
        since = time.time() - _last_reply_at.get(wa_id, 0)
        if since < DEBOUNCE_SECONDS:
            wait = DEBOUNCE_SECONDS - since
            print(f"[lumen-ai] _reply_async {wa_id}: replied {since:.0f}s ago, waiting "
                  f"{wait:.0f}s then answering the latest message")
            time.sleep(wait)
        # Humanized pacing: wait, then re-check that MK hasn't jumped in and the
        # customer hasn't sent something newer (people often send 3 messages in
        # a row — reply once to the latest, not three times).
        if REPLY_DELAY[1] > 0:
            time.sleep(random.uniform(*REPLY_DELAY))
        contact = get_contact(wa_id) or {}
        if _is_snoozed(contact) or contact.get("status") in ("handed_off", "opted_out"):
            print(f"[lumen-ai] _reply_async {wa_id}: human took over during delay, standing down")
            return
        if trigger_wamid:
            conn = _conn()
            row = conn.execute(
                "SELECT wamid FROM wa_messages WHERE wa_id = ? AND direction = 'in' ORDER BY id DESC LIMIT 1",
                (wa_id,),
            ).fetchone()
            conn.close()
            if row and row["wamid"] and row["wamid"] != trigger_wamid:
                print(f"[lumen-ai] _reply_async {wa_id}: newer inbound arrived, this thread stands down")
                return

        last_in = _last_inbound_body(wa_id)
        if _returning_on_settled_thread(wa_id):
            # An old thread that already reached an order. Whatever they say now is
            # about that order (late, missing, changing it) — MK's, and never a second
            # "Confirmed".
            print(f"[lumen-ai] _reply_async {wa_id}: returning customer on a settled thread, handing to MK")
            set_contact_status(wa_id, "handed_off")
            _alert_handoff(wa_id, reason="returning customer on a thread that already reached an order")
            _admin_monitor(wa_id, last_in, None, handoff=True,
                           note="Settled thread (order already reached) — existing-order question, agent silent")
            return
        reply, wants_handoff = generate_reply(wa_id, answer_opener=answer_opener)
        reply, leaked = _sanitize_reply(reply)
        if leaked:
            # Model misbehaved. Say nothing, give it to MK.
            wants_handoff = True
        if reply:
            send_text(wa_id, reply)
            _last_reply_at[wa_id] = time.time()
        if wants_handoff:
            set_contact_status(wa_id, "handed_off")
            # A confirmed order (a location on file + a "Confirmed"/"Done" reply) is
            # a closed sale — log it straight to Shopify before handing to MK.
            _maybe_log_agent_order(wa_id, reply)
            _alert_handoff(wa_id, reason="agent flagged this for MK (order to book, "
                                         "or a question it should not answer)")
        _admin_monitor(wa_id, last_in, reply, handoff=wants_handoff)
    except Exception as e:
        print(f"[lumen-ai] reply error for {wa_id}: {repr(e)}")
    finally:
        try:
            lock.release()
        except Exception:
            pass


AGENT_ORDERS_ON = os.environ.get("LUMENAI_AGENT_ORDERS", "0") not in ("0", "false", "False", "")
_CONFIRM_WORDS = ("confirm", "done", "تم", "تمام", "confirmed")


def _maybe_log_agent_order(wa_id, reply):
    """No-op for this profile.

    The FGC agent closed orders and wrote them into Shopify. This agent closes a
    BOOKED CALL: there is no order, no product and no store to write to, so the
    whole path is removed rather than left to fail quietly on every handoff."""
    return


def generate_reply(wa_id, answer_opener=False):
    if not ANTHROPIC_API_KEY:
        print("[lumen-ai] ANTHROPIC_API_KEY not set — cannot generate replies")
        return None, False
    try:
        import anthropic
    except ImportError:
        print("[lumen-ai] anthropic package not installed")
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

    bits = []
    # No product catalogue here: this agent sells one thing, a call. What matters
    # is which ad they came from, because it tells us what promise is in their head.
    ad_hint = _referral_hint(wa_id)
    if ad_hint:
        bits.append(f"They clicked an ad that said: \"{ad_hint}\". That is the promise "
                    f"already in their head. Do not re-explain it, build on it.")
    if answer_opener:
        bits.append("Their first message carried a real question on top of the ad's canned "
                    "opener, and our greeting has already gone out. Answer THAT question in "
                    "one short line, then ask about their business.")
    if not bits:
        bits.append("No ad context. Treat them as a business owner who just saw an ad about "
                    "WhatsApp agents. Ask what their business is.")
    context_line = "(" + " ".join(bits) + ")"

    if messages and messages[0]["role"] == "assistant":
        # Model requires a user turn first. Use a neutral placeholder — never the
        # meta context, which taught the model that narration is normal here.
        messages.insert(0, {"role": "user", "content": "..."})

    if (answer_opener and len(messages) >= 2 and messages[-1]["role"] == "assistant"
            and messages[-1]["content"].strip() == GREETING_TEXT.strip()):
        # The greeting went out AFTER their question. The system prompt already tells
        # the model the greeting was received, so drop it here and answer the question.
        messages.pop()

    if messages and messages[-1]["role"] == "assistant":
        # The thread already ends with one of our turns, so somebody has answered and
        # there is nothing to reply to. This happens for real: MK answers from her
        # phone while the agent is inside its reply delay, and her echo lands before
        # generate_reply re-reads the history.
        #
        # Left unhandled the API rejects the whole call — "does not support assistant
        # message prefill" — and the agent simply goes quiet with a 400 in the logs.
        # Two of five real threads replayed from the August export hit this. Staying
        # silent is the correct behaviour anyway; the bug was doing it by accident and
        # only after paying for a failed request.
        print(f"[lumen-ai] {wa_id}: thread ends with our own turn — nothing to reply to")
        return None, False

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
        print(f"[lumen-ai] anthropic call FAILED for {wa_id}: {repr(e)}")
        return None, False

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        return None, False

    wants_handoff = False
    if HANDOFF_TOKEN in text:
        wants_handoff = True
        text = text.replace(HANDOFF_TOKEN, "").rstrip()
    return (text or None), wants_handoff
