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

# A staging number running the same code as the live client number. Everything learned
# on it transfers, and nothing learned on it risks a client's traffic. Set
# FGC_TEST_PHONE_NUMBER_ID once the number is onboarded and this profile answers on
# both without a code change.
FGC_TEST_PHONE_NUMBER_ID = os.environ.get("FGC_TEST_PHONE_NUMBER_ID", "")
FGC_TEST_BUSINESS_NUMBER = "".join(
    ch for ch in os.environ.get("FGC_TEST_BUSINESS_NUMBER", "") if ch.isdigit())

# Only these wa_ids may run the in-chat test commands. Without an allow-list a real
# customer who happens to type "reset" would wipe their own order history, which is a
# far worse outcome than a slightly awkward test flow.
FGC_TESTERS = {"".join(c for c in n if c.isdigit())
               for n in os.environ.get("FGC_TESTERS", "").split(",") if n.strip()}

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
# Admin monitoring: a live email every time the agent acts, so Kendall can watch
# it try to sell. FGC_MONITOR=0 turns it off without touching the agent.
MONITOR_ON = os.environ.get("FGC_MONITOR", "1") not in ("0", "false", "False", "")
MONITOR_EMAILS = [e.strip() for e in os.environ.get(
    "FGC_MONITOR_EMAILS", "kendall@lumenmarketing.co").split(",") if e.strip()]
# Same monitoring, pushed to WhatsApp. Sent FROM the Lumen Cloud API number.
MONITOR_WA = [n.strip() for n in os.environ.get(
    "FGC_MONITOR_WA", "12085910132").split(",") if n.strip()]

# Humanized reply delay (seconds): "min-max".
try:
    _lo, _hi = os.environ.get("FGC_REPLY_DELAY", "0-0").split("-")
    REPLY_DELAY = (max(0, int(_lo)), max(int(_lo), int(_hi)))
except Exception:
    REPLY_DELAY = (20, 60)

HUMAN_SNOOZE_HOURS = float(os.environ.get("FGC_HUMAN_SNOOZE_HOURS", "4"))

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
            print(f"[fgc-wa] reasoning leak stripped, kept tail: {tail[:60]!r}")
            return tail, False
        print(f"[fgc-wa] reasoning leak, unsalvageable — suppressing: {t[:80]!r}")
        return "", True
    if len(t.split()) > 20:
        print(f"[fgc-wa] reply too long ({len(t.split())} words) — suppressing: {t[:80]!r}")
        return "", True
    return t, False
# Media the agent cannot interpret -> straight to MK, no reply attempted.
HANDOFF_MEDIA_TYPES = {"audio", "voice", "video", "image", "document"}
# The agent ONLY works conversations it watched start from an ad. Old leads
# replying to a months-old thread get no reply — we never saw that history, so
# any answer would be guesswork. MK handles those in her app as she always has.
AD_PREFILL_MARKERS = ("more info on this", "مزيد من المعلومات", "المعلومات حول هذا")
# The WhatsApp Business app fires an automated greeting ("Hello this item is for
# $12 / Would you like to order?"). It arrives as an app echo, identical in shape
# to MK typing by hand. If we snooze on it, the agent silences itself on EVERY
# new lead. These markers identify the canned greeting so we ignore it.
GREETING_MARKERS = ("would you like to order", "this item is for")
# Where handoff pings go: the FGC number itself, so the alert lands in the
# WhatsApp Business app MK already works in. Sent FROM the Lumen Cloud API number.
LUMEN_NOTIFY_PHONE_ID = os.environ.get("LUMEN_NOTIFY_PHONE_ID", "1082296231636502")
HANDOFF_WA_NUMBERS = [n.strip() for n in os.environ.get(
    "FGC_HANDOFF_WA", "96181873275").split(",") if n.strip()]
OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "remove me", "stop messaging"}

# ── The agent's persona / brain ──────────────────────────────────────────────
# PRODUCT FACTS: keep this block current — it is the agent's entire catalog
# knowledge. Prices/offers marked TODO must be confirmed by Kendall/MK before
# go-live (FGC_AUTO_REPLY=0 until then keeps the agent in log-only mode).
SYSTEM_PROMPT = """\
You are answering WhatsApp messages for Feels Good Club (FGC), a small Lebanese
online shop. Customers arrive by clicking an Instagram or Facebook ad, so they
already saw the product. They have ALREADY received our opening message:
"Hello\U0001F495 this item is for $12 / Would you like to order?" — never repeat it.

WHO YOU SOUND LIKE
You are the FGC shop account, the same person who sent that opening message.
Warm, fast, and extremely short. This is a WhatsApp shop chat, not customer
service and not a sales pitch.

HOW YOU WRITE — this matters more than anything
OUTPUT RULE, absolute: your entire output is the message the customer receives.
Nothing else. Never explain yourself, never narrate what you are doing, never
write about "the customer" or "the client", never reconsider out loud, never
write a preamble. If you catch yourself writing a sentence ABOUT the
conversation instead of IN it, stop and send only the message.

LENGTH, absolute: these are real replies from this shop, and this is the whole
range. Match it.
  "12$"            "4$"              "4$ delivery"       "3-6 days"
  "Location please"  "Name ? Location?"   "Confirm?"     "Done"   "Ok"
  "Yes"            "14"              "20 minutes"        "This week"
  "كل لبنان"        "سعر 12$"         "٤$ ديليفري"        "مرحبا"
Two to five words is normal. NEVER exceed 12 words. One line. One fact.
Answer exactly what was asked and nothing more. Do not stack extra selling
points onto an answer. Do not add "Would you like to order?" — the greeting
already asked that.

- No greetings after the first message. No "I hope this helps".
- NEVER use emojis. Not one, ever.
- Never ask "what would you like to know?" — it wastes the customer's time.
  They already saw the ad and the price. If they only said hi, ask for the
  order or the location instead.

LANGUAGE — mirror the customer exactly
- English -> English.
- Arabic script -> Arabic script.
- Arabizi (Lebanese Arabic in Latin letters/numbers, e.g. "adde bado wa2et ta
  yousal", "btn7at freezer?", "shu bi2awes") -> reply in the SAME arabizi style.
- French -> French.
Keep it Lebanese and casual, never formal Modern Standard Arabic.

THE FACTS YOU KNOW
- Every product is $12.
- Delivery is a flat $4, anywhere in Lebanon.
- Delivery time: 3 to 5 days typically. Beirut is faster, 1 to 2 days.
- Payment: cash on delivery is the default and most customers expect it.
  If they ask about Whish, the Whish number is 79018107. Otherwise they pay
  the driver at the door.
- Teeth Whitening Strips: 14 strips per box.
- Migraine Relief Cap: keep it in the freezer; stays cold 2 to 3 hours after
  you take it out; reaches about 0C; there is gel inside, not water; one size,
  stretchable.

THE ONE JOB
Get the customer to confirm they want it, then get their LOCATION.
The order is only real once they give a location (a pin, or an area plus
address). Ask with exactly: "Location please" or "Kindly share your location".

WHEN TO HAND OFF — end your reply with [[HANDOFF]]
Hand off (and say nothing else useful) when:
- They have given their location or full address. The order is ready to book —
  MK takes it from here. Reply "Confirmed" or "Done" then [[HANDOFF]].
- They ask for a discount or to negotiate the price.
- They ask anything you are not certain about: stock, a specific medical
  question, a complaint, a refund, a delivery that is late or missing, changing
  or cancelling an existing order.
- They want to order several different products, or a quantity that needs
  checking.
- Anything about an order that already exists.
HOW to hand off, this is important:
- If they gave their location and the order is ready: reply "Confirmed" (or
  "Done") and then [[HANDOFF]].
- For EVERY other handoff reason: output ONLY the token [[HANDOFF]] and no
  other text at all. Do not apologise, do not stall, do not promise anyone will
  reply, do not mention MK or any person by name. Say nothing. MK is alerted
  instantly and picks it up herself.

If you are not sure, hand off. It is always better to hand off than to guess.
Never invent stock levels, delivery dates, medical claims, discounts or
promotions. If they ask for a discount, do not answer it yourself at all.

Do not mention that you are an AI, an assistant, or a bot. You are the shop.
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
                     ("ad_name", "TEXT"), ("resolved_at", "TIMESTAMP")):
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
                     ("via_phone_id", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE wa_contacts ADD COLUMN {col} {ddl}")
        except Exception:
            pass
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
FGC_ADS_TOKEN = os.environ.get("FGC_ADS_TOKEN", "")
FGC_AD_ACCOUNT = os.environ.get("FGC_AD_ACCOUNT", "act_1337494034720023")
_AD_MAP = {"at": 0.0, "map": {}}
_AD_MAP_TTL = 3600.0

PRODUCT_RULES = (
    ("migraine cap", "Migraine Relief Cap"),
    ("migraine", "Migraine Relief Cap"),
    ("whitening strips", "Teeth Whitening Strips"),
    ("toothpaste", "Whitening Toothpaste"),
    ("whitening", "Teeth Whitening Strips"),
    ("acne patch", "Pimple Patches"),
    ("pimple", "Pimple Patches"),
    ("posture", "Posture Corrector"),
)


def _product_from_name(name):
    n = (name or "").lower()
    for needle, product in PRODUCT_RULES:
        if needle in n:
            return product
    return None


def _refresh_ad_map(force=False):
    if not FGC_ADS_TOKEN:
        return _AD_MAP["map"]
    if not force and (time.time() - _AD_MAP["at"]) < _AD_MAP_TTL:
        return _AD_MAP["map"]
    try:
        r = requests.get(
            f"{GRAPH_BASE}/{FGC_AD_ACCOUNT}/ads",
            params={"fields": "id,name", "limit": 500, "access_token": FGC_ADS_TOKEN},
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
            print(f"[fgc-wa] ad map refreshed: {len(m)} ads")
    except Exception as e:
        print(f"[fgc-wa] ad map refresh failed: {e}")
    return _AD_MAP["map"]


# Ad lineage cache. Meta's referral payload carries `source_id` — the AD id — and
# nothing above it. Campaign and ad set have to be resolved through the Graph API, so
# the lineage is cached per ad: a campaign's ads are stable, and the same ad produces
# hundreds of conversations.
_LINEAGE = {}


def _resolve_ad_lineage(ad_id, force=False):
    """ad_id -> {ad_name, adset_id, adset_name, campaign_id, campaign_name} or None.

    One Graph call returns the whole chain. Deliberately NOT scoped to
    FGC_AD_ACCOUNT: when the destination number moves between accounts, or an ad runs
    from a different account, resolving by ad id still works where an account-scoped
    map would silently miss.
    """
    ad_id = str(ad_id or "")
    if not ad_id:
        return None
    if not force and ad_id in _LINEAGE:
        return _LINEAGE[ad_id]
    if not FGC_ADS_TOKEN:
        return None
    try:
        r = requests.get(
            f"{GRAPH_BASE}/{ad_id}",
            params={"fields": "name,adset{id,name},campaign{id,name}",
                    "access_token": FGC_ADS_TOKEN},
            timeout=15,
        )
        d = r.json() or {}
        if "error" in d:
            print(f"[fgc-wa] lineage lookup failed for ad {ad_id}: "
                  f"{d['error'].get('message', '')[:120]}")
            return None
        out = {
            "ad_name": d.get("name"),
            "adset_id": (d.get("adset") or {}).get("id"),
            "adset_name": (d.get("adset") or {}).get("name"),
            "campaign_id": (d.get("campaign") or {}).get("id"),
            "campaign_name": (d.get("campaign") or {}).get("name"),
        }
        _LINEAGE[ad_id] = out
        return out
    except Exception as e:
        print(f"[fgc-wa] lineage lookup error for ad {ad_id}: {e}")
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
            print(f"[fgc-wa] lineage backfilled for {fixed} ad(s)")
        return fixed
    except Exception as e:
        print(f"[fgc-wa] lineage backfill error: {e}")
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
            " campaign_name, source_type, headline, resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (wa_id, clid or None, ad_id or None, lin.get("ad_name"),
             lin.get("adset_id"), lin.get("adset_name"), lin.get("campaign_id"),
             lin.get("campaign_name"), ref.get("source_type"),
             (ref.get("headline") or "")[:300],
             time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
             if lin.get("campaign_id") else None))
        if clid:
            conn.execute(
                "UPDATE wa_contacts SET ctwa_clid = ?, ctwa_clid_at = CURRENT_TIMESTAMP "
                "WHERE wa_id = ?", (clid, wa_id))
        conn.commit()
    except Exception as e:
        print(f"[fgc-wa] ctwa capture error for {wa_id}: {e}")
    finally:
        conn.close()

    if clid:
        camp = lin.get("campaign_name") or lin.get("campaign_id") or "campaign unresolved"
        print(f"[fgc-wa] ctwa_clid captured for {wa_id} — ad {ad_id or '?'} / {camp}")
    elif ad_id:
        # Organic-looking referral, or an ad format that does not carry a click id.
        # Worth a line in the log because a run of these means broken attribution.
        print(f"[fgc-wa] referral ad {ad_id} for {wa_id} with NO ctwa_clid")

    if not ad_id:
        return None
    product = _refresh_ad_map().get(ad_id)
    if not product:
        # Fall back to the ad copy Meta ships with the referral.
        product = _product_from_name(
            f"{ref.get('headline') or ''} {ref.get('body') or ''}")
    if not product:
        print(f"[fgc-wa] referral ad {ad_id}: product UNKNOWN")
        return None

    conn = _conn()
    conn.execute("UPDATE wa_contacts SET product = ?, product_ad_id = ? WHERE wa_id = ?",
                 (product, ad_id, wa_id))
    conn.execute("UPDATE wa_ctwa_clicks SET product = ? WHERE wa_id = ? AND product IS NULL",
                 (product, wa_id))
    conn.commit()
    conn.close()
    print(f"[fgc-wa] referral ad {ad_id} -> product {product} for {wa_id}")
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
        print(f"[fgc-wa] reset failed for {wa_id}: {e}")
    finally:
        conn.close()
    print(f"[fgc-wa] conversation reset for {wa_id}")


def _mark_agent_eligible(wa_id, why):
    conn = _conn()
    cur = conn.execute("UPDATE wa_contacts SET agent_ok = 1 WHERE wa_id = ? AND "
                       "COALESCE(agent_ok, 0) = 0", (wa_id,))
    conn.commit()
    conn.close()
    if cur.rowcount:
        print(f"[fgc-wa] {wa_id}: agent eligible ({why})")


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
def _phone_id_for(wa_id):
    """The number this contact reached us on, falling back to the live FGC number."""
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
    return FGC_PHONE_NUMBER_ID


def _graph_post(payload, phone_id=None):
    phone_id = phone_id or _phone_id_for(payload.get("to") or "")
    if not WHATSAPP_ACCESS_TOKEN or not phone_id:
        print("[fgc-wa] WARNING: token or phone number id not set — cannot send")
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

    body = (f"FGC handoff needed\n\n"
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
                print(f"[fgc-wa] handoff ping to {to} failed {r.status_code}: {r.text[:160]}")
            else:
                print(f"[fgc-wa] handoff ping sent to {to}")
        except Exception as e:
            print(f"[fgc-wa] handoff ping to {to} error: {e}")

    _notify_team(
        f"FGC WhatsApp — handoff: {name} ({product})",
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
            f"<a href='https://mk7media.com/fgc-wa/debug'>Agent debug</a></p>"
            f"<hr style='border:0;border-top:1px solid #e4e1d8'>{_conversation_html(wa_id)}</div>")

        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "FGC Agent Monitoring <notifications@lumenmarketing.co>",
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
                    print(f"[fgc-wa] monitor WA to {to} failed: {e}")
    except Exception as e:
        print(f"[fgc-wa] monitor email failed: {e}")


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
            if not wa_id or wa_id == FGC_BUSINESS_NUMBER:
                continue
            _upsert_contact(wa_id)
            for m in thread.get("messages") or []:
                sender = "".join(ch for ch in str(m.get("from") or "") if ch.isdigit())
                direction = "out_app" if sender == FGC_BUSINESS_NUMBER else "in"
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
        print(f"[fgc-wa] history sync: phase {phase}, {n_msgs} messages stored so far")
    print(f"[fgc-wa] history sync payload processed: {n_msgs} new messages")


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
    print(f"[fgc-wa] state sync: {n} contact names updated")


def is_fgc_event(value):
    """True when this webhook change belongs to the FGC number, or to the staging
    number. Dormant (always False) until a phone number id is configured."""
    meta = value.get("metadata") or {}
    pid = str(meta.get("phone_number_id") or "")
    if not pid:
        return False
    return pid in {str(x) for x in (FGC_PHONE_NUMBER_ID, FGC_TEST_PHONE_NUMBER_ID) if x}


def handle_webhook(payload):
    """Handle a webhook payload (only FGC-number changes; app.py routes us)."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            if not is_fgc_event(value):
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
                    conn = _conn()
                    conn.execute("UPDATE wa_contacts SET greeted = 1 WHERE wa_id = ?", (to_id,))
                    conn.commit()
                    conn.close()
                    print(f"[fgc-wa] app echo -> {to_id}: automated greeting sent, agent now armed")
                else:
                    snooze_contact(to_id)
                    print(f"[fgc-wa] app echo -> {to_id}: MK replied from phone, snoozing agent {HUMAN_SNOOZE_HOURS}h")

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
    if wa_id in {n for n in (FGC_BUSINESS_NUMBER, FGC_TEST_BUSINESS_NUMBER) if n}:
        print(f"[fgc-wa] ignoring self-addressed message {wamid}")
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
    if text and wa_id in FGC_TESTERS:
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
            print(f"[fgc-intent] pass failed for {wa_id}: {e}")
    threading.Thread(target=_intent_pass, daemon=True).start()

    contact = get_contact(wa_id) or {}
    status = contact.get("status", "active")

    if text and text.strip().lower() in OPT_OUT_WORDS:
        set_contact_status(wa_id, "opted_out")
        send_text(wa_id, "Done, you won't hear from us here again. If you ever change your mind, just message this number.")
        return

    if status == "opted_out":
        return

    if text and any(mk in text.lower() for mk in AD_PREFILL_MARKERS):
        # This is the ad's canned opener. The shop's greeting answers it.
        print(f"[fgc-wa] inbound {wa_id}: ad prefill — greeting handles this, agent silent")
        return

    if not contact.get("greeted"):
        # Greeting has not gone out yet. The agent only ever answers a REPLY to
        # the greeting, never the opening message.
        print(f"[fgc-wa] inbound {wa_id}: no greeting sent yet, agent silent")
        return

    if not contact.get("agent_ok"):
        # Old lead replying to an ancient thread, or a conversation that did not
        # start from one of our ads. No reply, no alert — MK owns it in the app.
        print(f"[fgc-wa] inbound {wa_id}: {body[:60]!r} — not an ad-started thread, agent silent")
        _admin_monitor(wa_id, body, None,
                       note="Old/non-ad thread — agent deliberately silent, MK owns it")
        return

    if _is_snoozed(contact) or status == "handed_off":
        # MK owns this thread (she replied from the app recently, or the agent
        # handed off). Stay quiet — she sees the message in her app anyway.
        print(f"[fgc-wa] inbound {wa_id}: {body[:60]!r} — human owns thread (snoozed/handed_off), agent silent")
        return

    if msg_type in HANDOFF_MEDIA_TYPES:
        # Voice notes, video, photos, documents: the agent cannot read these.
        # Per Kendall: do not reply, hand straight to MK.
        print(f"[fgc-wa] inbound {wa_id}: {msg_type} — cannot read, handing off to MK")
        set_contact_status(wa_id, "handed_off")
        _alert_handoff(wa_id, reason=f"{msg_type} message the agent cannot read")
        _admin_monitor(wa_id, body, None, handoff=True,
                       note=f"{msg_type} received — agent cannot read it")
        return

    if text is None:
        print(f"[fgc-wa] inbound {wa_id}: unreadable {msg_type} — handing off")
        set_contact_status(wa_id, "handed_off")
        _alert_handoff(wa_id, reason=f"unreadable {msg_type} message")
        _admin_monitor(wa_id, body, None, handoff=True,
                       note=f"unreadable {msg_type}")
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


_reply_locks = {}
_reply_locks_guard = threading.Lock()
_last_reply_at = {}


def _reply_lock(wa_id):
    with _reply_locks_guard:
        if wa_id not in _reply_locks:
            _reply_locks[wa_id] = threading.Lock()
        return _reply_locks[wa_id]


def _reply_async(wa_id, trigger_wamid=None):
    lock = _reply_lock(wa_id)
    if not lock.acquire(blocking=False):
        print(f"[fgc-wa] _reply_async {wa_id}: a reply is already in flight, dropping this one")
        return
    try:
        # Debounce: never fire two replies to the same person within 25s. People
        # send three messages in a row; they get ONE answer.
        since = time.time() - _last_reply_at.get(wa_id, 0)
        if since < 25:
            print(f"[fgc-wa] _reply_async {wa_id}: replied {since:.0f}s ago, standing down")
            return
        # Humanized pacing: wait, then re-check that MK hasn't jumped in and the
        # customer hasn't sent something newer (people often send 3 messages in
        # a row — reply once to the latest, not three times).
        if REPLY_DELAY[1] > 0:
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

        last_in = _last_inbound_body(wa_id)
        reply, wants_handoff = generate_reply(wa_id)
        reply, leaked = _sanitize_reply(reply)
        if leaked:
            # Model misbehaved. Say nothing, give it to MK.
            wants_handoff = True
        if reply:
            send_text(wa_id, reply)
            _last_reply_at[wa_id] = time.time()
        if wants_handoff:
            set_contact_status(wa_id, "handed_off")
            _alert_handoff(wa_id, reason="agent flagged this for MK (order to book, "
                                         "or a question it should not answer)")
        _admin_monitor(wa_id, last_in, reply, handoff=wants_handoff)
    except Exception as e:
        print(f"[fgc-wa] reply error for {wa_id}: {repr(e)}")
    finally:
        try:
            lock.release()
        except Exception:
            pass


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

    bits = []
    if contact.get("profile_name"):
        bits.append(f"The customer's WhatsApp profile name is {contact['profile_name']}.")
    if contact.get("product"):
        bits.append(f"They clicked the ad for: {contact['product']}. "
                    f"THIS is the product they are asking about — never ask them which product.")
    else:
        bits.append("We do NOT know which product they came from. Do not guess or name a "
                    "product. Everything is $12, so you can still answer price, delivery "
                    "and payment questions normally.")
    if contact.get("last_lat") is not None:
        bits.append(f"They already sent a location pin ({contact['last_lat']},{contact['last_lng']}"
                    f"{' - ' + contact['last_location_text'] if contact.get('last_location_text') else ''}).")
    context_line = "(" + " ".join(bits) + ")"

    if messages and messages[0]["role"] == "assistant":
        # Model requires a user turn first. Use a neutral placeholder — never the
        # meta context, which taught the model that narration is normal here.
        messages.insert(0, {"role": "user", "content": "..."})

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
        print(f"[fgc-wa] {wa_id}: thread ends with our own turn — nothing to reply to")
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
