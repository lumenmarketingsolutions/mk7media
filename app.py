import os
import json
import hashlib
import threading
import time
import uuid
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from agents.whatsapp_agent import agent as wa  # which profile is live: see ACTIVE_PROFILE in agents/whatsapp_agent/__init__.py
from agents.whatsapp_agent.profiles.fgc_agent_v1_00 import agent as fgc_wa  # FGC number (coexistence); dormant until FGC_WHATSAPP_PHONE_NUMBER_ID is set
from agents.order_entry import fgc_orders  # Mary's WhatsApp -> Shopify order bot; dormant until FGC_ORDER_SENDERS is set

app = Flask(__name__)

# Session secret — set FLASK_SECRET_KEY in Railway. Random fallback for local dev only.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-" + uuid.uuid4().hex)

# Session config — keep admin sessions usable across the mk7media subdomains
# (mk7media.com + whatsapp.mk7media.com) and durable on mobile browsers.
# On Railway we set the cookie domain to .mk7media.com so logging in on either
# host gives you a session valid on both, and mark sessions permanent with a
# 30-day lifetime so phone browsers can't aggressively expire them. Skipped
# locally so dev on 127.0.0.1 still works.
app.permanent_session_lifetime = timedelta(days=30)
if os.environ.get("RAILWAY_PROJECT_ID") or os.environ.get("RAILWAY_ENVIRONMENT"):
    app.config["SESSION_COOKIE_DOMAIN"] = ".mk7media.com"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

# Admin login credentials. Override via Railway env vars. Two accounts are accepted
# so both Marykate (analytics) and Kendall (WhatsApp portal) can log in.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "mary@mk7media.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Ghazarian123$$")
ADMIN_EMAIL_2 = os.environ.get("ADMIN_EMAIL_2", "kendall@lumenmarketing.co")
ADMIN_PASSWORD_2 = os.environ.get("ADMIN_PASSWORD_2", "Wifimoney420!")
_ADMIN_ACCOUNTS = {(ADMIN_EMAIL.strip().lower(), ADMIN_PASSWORD)}
if ADMIN_EMAIL_2 and ADMIN_PASSWORD_2:
    _ADMIN_ACCOUNTS.add((ADMIN_EMAIL_2.strip().lower(), ADMIN_PASSWORD_2))

# IPs to log but exclude from analytics averages (Kendall's phone, etc.)
ANALYTICS_IGNORE_IPS = {"209.127.238.130"}

# Local SQLite analytics store
ANALYTICS_DB = os.environ.get("ANALYTICS_DB_PATH", "mk7_analytics.db")

def _analytics_conn():
    conn = sqlite3.connect(ANALYTICS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _init_analytics_db():
    conn = _analytics_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            page_path TEXT NOT NULL,
            session_id TEXT,
            ip TEXT,
            user_agent TEXT,
            referrer TEXT,
            time_on_page INTEGER,
            button_source TEXT,
            event_metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_path_created ON analytics_events(page_path, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON analytics_events(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON analytics_events(event_type)")
    conn.commit()
    conn.close()

_init_analytics_db()


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            # Save where they were trying to go so login bounces them back to it
            # (so a /admin/whatsapp?id=... deep-link from a WhatsApp ping survives).
            if request.method == "GET":
                session["next_url"] = request.full_path.rstrip("?")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapper

# ── Config ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "marykatezarehghazarian@gmail.com")
NOTIFY_RECIPIENTS = [NOTIFY_EMAIL, "mary@mk7media.com", "kendall@lumenmarketing.co"]

# Meta Conversions API — DPSmgmt dataset
META_DATASET_ID = os.environ.get("META_DATASET_ID", "2251653638703742")
META_CAPI_ACCESS_TOKEN = os.environ.get("META_CAPI_ACCESS_TOKEN", "")
META_TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE", "")  # optional, for Events Manager Test Events tab

# Meta Conversions API — Lumen Marketing dataset (used to fire a Lead event
# whenever a brand-new cold WhatsApp conversation starts on +1 623 512 6504,
# so the Lumen ad set driving /lumenlb can optimise on actual convo-starts).
# Inert until LUMEN_META_CAPI_TOKEN is set on the Railway service.
LUMEN_META_DATASET_ID = os.environ.get("LUMEN_META_DATASET_ID", "1119566303064711")
LUMEN_META_CAPI_TOKEN = os.environ.get("LUMEN_META_CAPI_TOKEN", "")
# Test event code is PER-DATASET in Events Manager, so the Lumen dataset needs
# its own. Pull this code from Events Manager → Lumen dataset → Test Events tab.
# Leave empty for production firing into the dataset's Overview.
LUMEN_META_TEST_EVENT_CODE = os.environ.get("LUMEN_META_TEST_EVENT_CODE", "")

# Payhip purchase webhook — secret comes from the "Paid" webhook config in Payhip dashboard
PAYHIP_WEBHOOK_SECRET = os.environ.get("PAYHIP_WEBHOOK_SECRET", "")

# Map Payhip product IDs to product display names + landing page URLs (used for richer Purchase events)
PAYHIP_PRODUCTS = {
    "J0xhM": {
        "name": "Land Your First 5 Ad Clients",
        "page": "https://mk7media.com/playbooks/land-5-clients",
    },
    "29jwK": {
        "name": "Double Your Clients in 30 Days",
        "page": "https://mk7media.com/playbooks/double-clients",
    },
}


def _hash(value):
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


# Meta CAPI reserves these top-level keys in custom_data with strict types.
# Anything else gets nested into custom_properties so we never trip type validation.
_CAPI_STANDARD_KEYS = {
    "value", "currency", "content_name", "content_category", "content_ids",
    "contents", "content_type", "order_id", "predicted_ltv", "num_items",
    "search_string", "status", "delivery_category",
}


def _sanitize_custom_data(custom_data):
    """Coerce reserved Meta keys to valid types and bundle the rest under custom_properties."""
    if not custom_data:
        return {}
    clean = {}
    extras = {}
    for k, v in custom_data.items():
        if v is None or v == "":
            continue
        if k in _CAPI_STANDARD_KEYS:
            if k == "value":
                try:
                    clean["value"] = float(v)
                except (TypeError, ValueError):
                    continue  # drop invalid value rather than letting Meta reject the event
            elif k == "currency":
                s = str(v).strip().upper()
                if len(s) == 3 and s.isalpha():
                    clean["currency"] = s
            elif k == "num_items":
                try:
                    clean["num_items"] = int(v)
                except (TypeError, ValueError):
                    continue
            elif k in ("content_ids", "contents"):
                if isinstance(v, list):
                    clean[k] = v
            else:
                clean[k] = str(v)
        else:
            extras[k] = v
    if extras:
        clean["custom_properties"] = extras
    return clean


def _send_capi_event(event_name, event_id, user_data, custom_data=None, event_source_url=None,
                     dataset_id=None, access_token=None, test_event_code=None):
    """POST a server-side event to Meta Conversions API. Safe-fail: returns silently on any error.

    `dataset_id` + `access_token` override the module-level MK7 dataset (used so the
    WhatsApp webhook can fire Lead events into the Lumen dataset on cold-inbound convos).
    `test_event_code` overrides the module-level META_TEST_EVENT_CODE — Test Events
    codes are per-dataset in Meta Events Manager, so cross-dataset firing needs the
    matching code or no code at all (NOT the MK7 dataset's code on a Lumen event).
    Pass an explicit value (including "") to opt out of the module-level fallback."""
    dataset = dataset_id or META_DATASET_ID
    token = access_token or META_CAPI_ACCESS_TOKEN
    if not token or not dataset:
        return
    try:
        import requests as req
        ud = {}
        if user_data.get("email"):
            ud["em"] = [_hash(user_data["email"])]
        if user_data.get("phone"):
            digits = "".join(c for c in user_data["phone"] if c.isdigit())
            if digits:
                ud["ph"] = [_hash(digits)]
        if user_data.get("first_name"):
            ud["fn"] = [_hash(user_data["first_name"])]
        if user_data.get("last_name"):
            ud["ln"] = [_hash(user_data["last_name"])]
        if user_data.get("client_ip"):
            ud["client_ip_address"] = user_data["client_ip"]
        if user_data.get("client_ua"):
            ud["client_user_agent"] = user_data["client_ua"]
        if user_data.get("fbp"):
            ud["fbp"] = user_data["fbp"]
        if user_data.get("fbc"):
            ud["fbc"] = user_data["fbc"]

        event = {
            "event_name": event_name,
            "event_time": int(time.time()),
            "event_id": event_id,
            "action_source": "website",
            "user_data": ud,
        }
        if event_source_url:
            event["event_source_url"] = event_source_url
        cleaned = _sanitize_custom_data(custom_data)
        if cleaned:
            event["custom_data"] = cleaned

        payload = {"data": [event]}
        # If the caller passed test_event_code explicitly (incl. empty string) honour
        # that. Otherwise fall back to the module-level MK7 code.
        tec = test_event_code if test_event_code is not None else META_TEST_EVENT_CODE
        if tec:
            payload["test_event_code"] = tec

        url = f"https://graph.facebook.com/v19.0/{dataset}/events?access_token={token}"
        r = req.post(url, json=payload, timeout=5)
        if r.status_code >= 400:
            print(f"[capi] {event_name} failed {r.status_code}: {r.text[:300]}")
        else:
            print(f"[capi] {event_name} sent event_id={event_id}")
    except Exception as e:
        print(f"[capi] {event_name} exception: {e}")


def _client_ctx():
    """Pull IP/UA/cookies from the current request for CAPI user_data."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return {
        "client_ip": ip,
        "client_ua": request.headers.get("User-Agent", ""),
    }

def _is_whatsapp_host():
    return (request.host or "").lower().split(":")[0].startswith("whatsapp.")


@app.route("/")
def home():
    # whatsapp.mk7media.com is the WhatsApp portal's front door — drop straight into it.
    if _is_whatsapp_host():
        return redirect(url_for("admin_whatsapp"))
    return render_template("index.html")

@app.route("/saas0801")
def saas0801_proposal():
    return render_template("saas0801.html")


@app.route("/marlatabet")
def marlatabet_proposal():
    return render_template("marlatabet.html")


@app.route("/marlatabet/reel")
def marlatabet_reel():
    return render_template("marlatabet_reel.html")

def _whatsapp_digits(value):
    return "".join(c for c in (value or "") if c.isdigit())

def _build_inquiry_email(name, whatsapp, website):
    dash = "\u2014"
    wa_button = ""
    wa_digits = _whatsapp_digits(whatsapp)
    if wa_digits:
        first_name = (name or "there").split(" ", 1)[0]
        prefill = f"Hey {first_name}, MaryKate from MK7. Quick one: are you running ads now or starting fresh?"
        from urllib.parse import quote
        wa_url = f"https://wa.me/{wa_digits}?text={quote(prefill)}"
        wa_button = (
            '<div style="margin-top: 28px; text-align: center;">'
            f'<a href="{wa_url}" style="display: inline-block; background: #25D366; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 10px; font-weight: 600; font-family: sans-serif; font-size: 15px;">'
            '\ud83d\udcac Reply on WhatsApp'
            '</a>'
            '<p style="margin: 12px 0 0; color: #888; font-size: 12px;">Opens a chat with this lead, pre-filled.</p>'
            '</div>'
        )

    return (
        '<div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px;">'
        '<h2 style="margin: 0 0 24px; color: #111;">New Inquiry from MK7 Media</h2>'
        '<table style="width: 100%; border-collapse: collapse;">'
        f'<tr><td style="padding: 8px 0; color: #888; width: 140px;">Name</td><td style="padding: 8px 0; color: #111; font-weight: 600;">{name}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">WhatsApp</td><td style="padding: 8px 0; color: #111; font-weight: 600;">{whatsapp or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Website</td><td style="padding: 8px 0; color: #111;">{website or dash}</td></tr>'
        '</table>'
        f'{wa_button}'
        '</div>'
    )

@app.route("/api/inquiry", methods=["POST"])
def inquiry():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    whatsapp = data.get("whatsapp", "").strip()
    business = data.get("business", "").strip()
    website = data.get("website", "").strip()
    service_type = data.get("service_type", "").strip()
    budget = data.get("budget", "").strip()
    goals = data.get("goals", "").strip()

    # Min 10 digits guarantees an international number with a country code.
    # An 8-digit Lebanon local sneaking through here is what caused the
    # "can't message the lead" bug — frontend now forces a country code,
    # backend enforces it as a second line of defense.
    if not name or len(_whatsapp_digits(whatsapp)) < 10:
        return jsonify({"error": "Name and a full WhatsApp number with country code are required"}), 400

    # Two-stage capture: step 1 sends a "new inquiry" email + fires Lead CAPI;
    # step 5 sends an "enrichment" email with the qualifying answers and skips the CAPI re-fire.
    is_enrichment = bool(data.get("is_enrichment"))

    # Send notification email
    if RESEND_API_KEY:
        try:
            import resend
            resend.api_key = RESEND_API_KEY
            subject_prefix = "Inquiry Enrichment" if is_enrichment else "New Inquiry"
            resend.Emails.send({
                "from": "MK7 Media <notifications@lumenmarketing.co>",
                "to": NOTIFY_RECIPIENTS,
                "subject": f"{subject_prefix}: {name}" + (f" — {service_type}" if service_type else ""),
                "html": _build_inquiry_email(name, whatsapp, website)
            })
        except Exception as e:
            print(f"[email] Failed to send notification: {e}")

    # On enrichment, return early without re-firing the CAPI Lead event
    if is_enrichment:
        return jsonify({"ok": True, "stage": "enrichment"})

    # Meta CAPI — Lead event (deduped against browser Pixel via event_id)
    event_id = (data.get("event_id") or str(uuid.uuid4())).strip()
    parts = name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    ctx = _client_ctx()
    _send_capi_event(
        event_name="Lead",
        event_id=event_id,
        user_data={
            "email": email,
            "phone": whatsapp,
            "first_name": first_name,
            "last_name": last_name,
            "client_ip": ctx["client_ip"],
            "client_ua": ctx["client_ua"],
            "fbp": (data.get("fbp") or "").strip() or None,
            "fbc": (data.get("fbc") or "").strip() or None,
        },
        custom_data={
            "lead_source": "homepage_quiz",
            "service_type": service_type,
            "budget": budget,
            "content_name": "MK7 Media inquiry",
        },
        event_source_url=data.get("page_url") or "https://mk7media.com/",
    )

    return jsonify({"ok": True})


# Lightweight CAPI passthrough for funnel-stage events fired before the form
# submit (ViewContent on form-in-viewport, InitiateCheckout on first
# qualifier tap). Each event is deduped with the browser Pixel via the
# shared event_id sent from the client. Kept narrow on purpose — only the
# specific events we want feeding the algorithm are allowed.
_ALLOWED_FUNNEL_EVENTS = {"ViewContent", "InitiateCheckout"}

@app.route("/api/event", methods=["POST"])
def fire_funnel_event():
    data = request.get_json(silent=True) or {}
    event_name = (data.get("event_name") or "").strip()
    if event_name not in _ALLOWED_FUNNEL_EVENTS:
        return jsonify({"error": "unsupported event"}), 400

    event_id = (data.get("event_id") or str(uuid.uuid4())).strip()
    ctx = _client_ctx()
    _send_capi_event(
        event_name=event_name,
        event_id=event_id,
        user_data={
            "client_ip": ctx["client_ip"],
            "client_ua": ctx["client_ua"],
            "fbp": (data.get("fbp") or "").strip() or None,
            "fbc": (data.get("fbc") or "").strip() or None,
        },
        custom_data={
            "content_name": (data.get("content_name") or "").strip() or "MK7 Media inquiry form",
            "lead_source": (data.get("lead_source") or "homepage_inquiry").strip(),
        },
        event_source_url=data.get("page_url") or "https://mk7media.com/",
    )
    return jsonify({"ok": True})


@app.route("/playbooks")
def playbooks_catalog():
    return render_template("playbooks_catalog.html")


@app.route("/playbooks/land-5-clients")
def playbook_land_5():
    return render_template("playbook_land_5.html")


@app.route("/playbooks/double-clients")
def playbook_double_clients():
    return render_template("playbook_double_clients.html")


@app.route("/api/playbook-waitlist", methods=["POST"])
def playbook_waitlist():
    """Capture emails for coming-soon Vol 03/04 playbooks. Notifies team via Resend, fires CAPI Lead."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    product_id = (data.get("product_id") or "").strip()
    page_url = (data.get("page_url") or "").strip()

    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400

    # Send notification email
    if RESEND_API_KEY:
        try:
            import resend
            resend.api_key = RESEND_API_KEY
            resend.Emails.send({
                "from": "MK7 Media <notifications@lumenmarketing.co>",
                "to": NOTIFY_RECIPIENTS,
                "subject": f"Playbook waitlist: {product_id}",
                "html": (
                    f'<div style="font-family:Inter,sans-serif;color:#1a1a1a;padding:20px;">'
                    f'<h2 style="margin:0 0 16px;">New Playbook Waitlist Signup</h2>'
                    f'<p><strong>Email:</strong> {email}</p>'
                    f'<p><strong>Product:</strong> {product_id}</p>'
                    f'<p><strong>Source:</strong> {page_url}</p>'
                    f'</div>'
                )
            })
        except Exception as e:
            print(f"[email] Waitlist notification failed: {e}")

    # CAPI Lead event
    event_id = (data.get("event_id") or str(uuid.uuid4())).strip()
    ctx = _client_ctx()
    _send_capi_event(
        event_name="Lead",
        event_id=event_id,
        user_data={
            "email": email,
            "client_ip": ctx["client_ip"],
            "client_ua": ctx["client_ua"],
            "fbp": (data.get("fbp") or "").strip() or None,
            "fbc": (data.get("fbc") or "").strip() or None,
        },
        custom_data={
            "lead_source": "playbook_waitlist",
            "content_name": f"Waitlist: {product_id}",
        },
        event_source_url=page_url or "https://mk7media.com/playbooks",
    )

    return jsonify({"ok": True})


@app.route("/grow")
@app.route("/grow/<market>")
def grow_page(market=None):
    valid = {"lb": "Lebanon", "gcc": "GCC"}
    if market not in valid:
        market = "lb"
    return render_template("grow.html", market=market, market_name=valid[market])


@app.route("/api/grow/lead", methods=["POST"])
def grow_lead_submit():
    data = request.get_json() or {}
    whatsapp = (data.get("whatsapp") or "").strip()
    name = (data.get("name") or "").strip()
    business = (data.get("business") or "").strip()
    need = (data.get("need") or "").strip()
    source_page = (data.get("source_page") or "").strip()
    market = (data.get("market") or "").strip()

    # Min 10 digits = country code + reasonable national number
    if len(_whatsapp_digits(whatsapp)) < 10:
        return jsonify({"error": "Valid WhatsApp number with country code is required"}), 400

    market_labels = {"lb": "Lebanon", "gcc": "GCC/Dubai", "": "Unknown"}
    ml = market_labels.get(market, market)
    subject = f"New Lead from Grow Page ({ml})"
    body = (
        '<div style="font-family:Inter,sans-serif;color:#1a1a1a;padding:20px;">'
        f'<h2 style="margin:0 0 16px;">New Lead — {ml}</h2>'
        f'<p><strong>WhatsApp:</strong> {whatsapp}</p>'
        f'<p><strong>Name:</strong> {name or "Not provided"}</p>'
        f'<p><strong>Business:</strong> {business or "Not provided"}</p>'
        f'<p><strong>Need:</strong> {need or "Not provided"}</p>'
        f'<p><strong>Source:</strong> {source_page}</p>'
        '</div>'
    )

    if RESEND_API_KEY:
        try:
            import requests as req
            for email in NOTIFY_RECIPIENTS:
                req.post("https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={"from": "MK7 Media <notifications@lumenmarketing.co>", "to": [email], "subject": subject, "html": body})
        except Exception as e:
            print(f"[email] Failed: {e}")

    # Meta CAPI — only fire Lead on full submit (not on the partial whatsapp blur capture)
    is_full_submit = bool(name)
    if is_full_submit:
        event_id = (data.get("event_id") or str(uuid.uuid4())).strip()
        parts = name.split(" ", 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""
        ctx = _client_ctx()
        _send_capi_event(
            event_name="Lead",
            event_id=event_id,
            user_data={
                "phone": whatsapp,
                "first_name": first_name,
                "last_name": last_name,
                "client_ip": ctx["client_ip"],
                "client_ua": ctx["client_ua"],
                "fbp": (data.get("fbp") or "").strip() or None,
                "fbc": (data.get("fbc") or "").strip() or None,
            },
            custom_data={
                "lead_source": "grow_page",
                "market": ml,
                "need": need,
                "content_name": f"Grow page lead — {ml}",
            },
            event_source_url=data.get("page_url") or f"https://mk7media.com{source_page}",
        )

    return jsonify({"ok": True})


@app.route("/api/payhip-webhook", methods=["POST"])
def payhip_webhook():
    """Receive Payhip purchase webhooks and fire Meta CAPI Purchase events server-side.

    Payhip sends form-encoded POST data with a `signature` field that's the SHA1 HMAC
    of the body (excluding the signature itself), keyed by the webhook secret.
    Reference: https://payhip.com/docs/webhook
    """
    import hmac

    raw_body = request.get_data(as_text=True) or ""
    print(f"[payhip] webhook received, body length={len(raw_body)}")

    # Payhip sends form-encoded by default. We'll also accept JSON if they ever change it.
    payload = {}
    if request.content_type and "application/json" in request.content_type:
        payload = request.get_json(silent=True) or {}
    else:
        payload = request.form.to_dict()

    event_type = (payload.get("type") or payload.get("event") or "").lower()
    signature_in = payload.get("signature") or request.headers.get("X-Payhip-Signature", "")

    # Verify signature when a secret is configured. SHA1 HMAC of the body without the signature param.
    if PAYHIP_WEBHOOK_SECRET:
        try:
            # Build the canonical body Payhip signed: same body but without the `signature=...` field
            if request.content_type and "application/json" in request.content_type:
                # JSON path: hash the body that omits the signature key
                pl_no_sig = {k: v for k, v in payload.items() if k != "signature"}
                canonical = json.dumps(pl_no_sig, separators=(",", ":"), sort_keys=True)
            else:
                # Form path: rebuild query string without the signature param, in original order
                from urllib.parse import urlencode
                pairs = [(k, v) for k, v in request.form.items(multi=True) if k != "signature"]
                canonical = urlencode(pairs)

            expected_sha1 = hmac.new(
                PAYHIP_WEBHOOK_SECRET.encode("utf-8"),
                canonical.encode("utf-8"),
                hashlib.sha1,
            ).hexdigest()
            expected_sha256 = hmac.new(
                PAYHIP_WEBHOOK_SECRET.encode("utf-8"),
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if signature_in not in (expected_sha1, expected_sha256):
                print(f"[payhip] signature mismatch (got {signature_in[:12]}..., expected SHA1 {expected_sha1[:12]}... or SHA256 {expected_sha256[:12]}...)")
                # Don't 401 in production yet — Payhip might use a slightly different canonicalization.
                # Log it but accept the event so we don't lose conversions while we tune the verifier.
                # Once we confirm the canonical form matches, flip this to a 401.
        except Exception as e:
            print(f"[payhip] signature verify exception: {e}")

    # Only fire Purchase on the paid event. Refund/dispute logic can come later.
    if event_type not in ("paid", "purchase", "sale"):
        print(f"[payhip] ignoring event type='{event_type}'")
        return jsonify({"ok": True, "ignored": event_type})

    # Pull what we need to construct the Purchase event
    product_id = (payload.get("product_link") or payload.get("product_id") or payload.get("items_link") or "").strip()
    # Payhip sometimes sends the full URL in product_link — extract the trailing slug
    if "/" in product_id:
        product_id = product_id.rstrip("/").split("/")[-1]

    customer_email = (payload.get("email") or payload.get("customer_email") or "").strip()
    customer_name = (payload.get("name") or payload.get("customer_name") or "").strip()
    parts = customer_name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    # Payhip sends amounts in the smallest currency unit (cents for USD).
    # A $5.00 sale arrives as 500 in `price`/`amount`/`total`. Divide by 100 to get dollars.
    try:
        raw_amount = float(payload.get("price") or payload.get("amount") or payload.get("total") or 0)
    except (TypeError, ValueError):
        raw_amount = 0.0
    amount = raw_amount / 100.0
    currency = (payload.get("currency") or "USD").upper()
    print(f"[payhip] sale parsed: product={product_id} amount=${amount:.2f} {currency} email={customer_email}")
    transaction_id = (payload.get("transaction_id") or payload.get("order_id") or payload.get("id") or str(uuid.uuid4())).strip()

    product_meta = PAYHIP_PRODUCTS.get(product_id, {})
    product_name = product_meta.get("name") or payload.get("product_name") or "MK7 Media Playbook"
    page_url = product_meta.get("page") or "https://mk7media.com/playbooks"

    # Server-side Purchase event. event_id matches Payhip's transaction_id so any future browser
    # Purchase event we add (e.g. from the post-purchase thank-you page) will dedupe against this.
    _send_capi_event(
        event_name="Purchase",
        event_id=transaction_id,
        user_data={
            "email": customer_email,
            "first_name": first_name,
            "last_name": last_name,
            # No fbp/fbc available server-to-server; email match handles attribution.
        },
        custom_data={
            "value": amount,
            "currency": currency,
            "content_name": product_name,
            "content_ids": [product_id] if product_id else [],
            "content_type": "product",
            "order_id": transaction_id,
            "num_items": 1,
        },
        event_source_url=page_url,
    )

    # Notify the team via email. Useful both for live sales and for spotting silent failures.
    if RESEND_API_KEY and customer_email:
        try:
            import resend
            resend.api_key = RESEND_API_KEY
            resend.Emails.send({
                "from": "MK7 Media <notifications@lumenmarketing.co>",
                "to": NOTIFY_RECIPIENTS,
                "subject": f"Sale: {product_name} (${amount:.2f}) — {customer_email}",
                "html": (
                    f'<div style="font-family:Inter,sans-serif;color:#1a1a1a;padding:20px;">'
                    f'<h2 style="margin:0 0 16px;">New Playbook Sale</h2>'
                    f'<p><strong>Product:</strong> {product_name}</p>'
                    f'<p><strong>Customer:</strong> {customer_name or customer_email}</p>'
                    f'<p><strong>Email:</strong> {customer_email}</p>'
                    f'<p><strong>Amount:</strong> ${amount:.2f} {currency}</p>'
                    f'<p><strong>Transaction:</strong> {transaction_id}</p>'
                    f'</div>'
                )
            })
        except Exception as e:
            print(f"[email] Sale notification failed: {e}")

    return jsonify({"ok": True, "event_id": transaction_id})


@app.route("/api/track", methods=["POST"])
def track_event():
    """Generic engagement tracker: forwards browser-side events to Meta CAPI for dedup + iOS/blocker resilience."""
    data = request.get_json(silent=True) or {}
    event_name = (data.get("event_name") or "").strip()
    if not event_name:
        return jsonify({"ok": False, "error": "missing event_name"}), 400
    event_id = (data.get("event_id") or str(uuid.uuid4())).strip()
    ctx = _client_ctx()
    _send_capi_event(
        event_name=event_name,
        event_id=event_id,
        user_data={
            "client_ip": ctx["client_ip"],
            "client_ua": ctx["client_ua"],
            "fbp": (data.get("fbp") or "").strip() or None,
            "fbc": (data.get("fbc") or "").strip() or None,
        },
        custom_data=data.get("custom_data") or {},
        event_source_url=data.get("page_url") or "https://mk7media.com/",
    )
    return jsonify({"ok": True})


@app.route("/api/admin-track", methods=["POST"])
def admin_track():
    """Local analytics ingestion. Stores pageview / time_on_page / button_click events to SQLite."""
    data = request.get_json(silent=True) or {}
    event_type = (data.get("event_type") or "").strip()
    page_path = (data.get("page_path") or request.headers.get("Referer", "")).strip()
    session_id = (data.get("session_id") or "").strip()
    referrer = (data.get("referrer") or "").strip()

    if not event_type or event_type not in ("pageview", "time_on_page", "button_click"):
        return jsonify({"ok": False, "error": "invalid event_type"}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ua = request.headers.get("User-Agent", "")[:500]

    time_on_page = data.get("time_on_page")
    if time_on_page is not None:
        try:
            time_on_page = int(time_on_page)
        except (TypeError, ValueError):
            time_on_page = None

    button_source = (data.get("button_source") or "").strip() or None
    metadata = data.get("metadata")
    metadata_json = json.dumps(metadata) if metadata else None

    try:
        conn = _analytics_conn()
        conn.execute(
            """INSERT INTO analytics_events
               (event_type, page_path, session_id, ip, user_agent, referrer, time_on_page, button_source, event_metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, page_path, session_id, ip, ua, referrer, time_on_page, button_source, metadata_json)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[admin-track] insert failed: {e}")
        return jsonify({"ok": False}), 500

    return jsonify({"ok": True})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        ok = (email, password) in _ADMIN_ACCOUNTS
        print(f"[admin-login] attempt: ok={ok} email_known={any(e == email for e, _ in _ADMIN_ACCOUNTS)} "
              f"submitted_email_len={len(email)} submitted_pw_len={len(password)}")
        if ok:
            session["admin_logged_in"] = True
            session["admin_email"] = email
            session.permanent = True  # 30-day lifetime per app.permanent_session_lifetime
            # If they were trying to reach a specific page (e.g. a WhatsApp ping's
            # /admin/whatsapp?id=... deep-link), honour that.
            next_url = session.pop("next_url", None)
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            # Otherwise: WhatsApp subdomain -> portal; otherwise analytics dashboard.
            return redirect(url_for("admin_whatsapp" if _is_whatsapp_host() else "admin_dashboard"))
        error = "Wrong email or password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    """Analytics dashboard. Shows page views, time on page, button clicks, and recent visits."""
    page_filter = request.args.get("page", "").strip()
    days = int(request.args.get("days", "7"))
    days = max(1, min(days, 90))

    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    ignore_ip_placeholders = ",".join("?" * len(ANALYTICS_IGNORE_IPS)) or "''"
    ignore_ip_list = list(ANALYTICS_IGNORE_IPS)

    conn = _analytics_conn()

    # Pages summary (counts and avg time on page; excludes ignore-IPs from avg only)
    page_rows = conn.execute(f"""
        SELECT
            page_path,
            COUNT(CASE WHEN event_type = 'pageview' THEN 1 END) as views,
            COUNT(CASE WHEN event_type = 'pageview' AND ip NOT IN ({ignore_ip_placeholders}) THEN 1 END) as views_clean,
            COUNT(CASE WHEN event_type = 'button_click' THEN 1 END) as clicks,
            ROUND(AVG(CASE WHEN event_type = 'time_on_page' AND ip NOT IN ({ignore_ip_placeholders}) THEN time_on_page END), 1) as avg_seconds,
            COUNT(DISTINCT session_id) as sessions
        FROM analytics_events
        WHERE created_at >= ?
        GROUP BY page_path
        ORDER BY views DESC
    """, ignore_ip_list + ignore_ip_list + [since]).fetchall()

    # Button click breakdown (by source)
    where_page = "AND page_path = ?" if page_filter else ""
    button_params = [since] + ([page_filter] if page_filter else [])
    button_rows = conn.execute(f"""
        SELECT button_source, COUNT(*) as clicks
        FROM analytics_events
        WHERE event_type = 'button_click' AND created_at >= ? {where_page}
        GROUP BY button_source
        ORDER BY clicks DESC
    """, button_params).fetchall()

    # Recent sessions (one row per session, with key metrics)
    session_params = [since] + ([page_filter] if page_filter else [])
    recent_rows = conn.execute(f"""
        SELECT
            session_id,
            MAX(page_path) as page_path,
            MAX(ip) as ip,
            MAX(user_agent) as user_agent,
            MAX(referrer) as referrer,
            MIN(created_at) as visited_at,
            MAX(time_on_page) as time_on_page,
            COUNT(CASE WHEN event_type = 'button_click' THEN 1 END) as clicks
        FROM analytics_events
        WHERE created_at >= ? AND session_id != '' {where_page}
        GROUP BY session_id
        ORDER BY visited_at DESC
        LIMIT 100
    """, session_params).fetchall()

    # Top-line totals (clean = excludes ignore IPs)
    totals_row = conn.execute(f"""
        SELECT
            COUNT(CASE WHEN event_type = 'pageview' AND ip NOT IN ({ignore_ip_placeholders}) THEN 1 END) as views,
            COUNT(CASE WHEN event_type = 'button_click' AND ip NOT IN ({ignore_ip_placeholders}) THEN 1 END) as clicks,
            COUNT(DISTINCT CASE WHEN ip NOT IN ({ignore_ip_placeholders}) THEN session_id END) as sessions,
            ROUND(AVG(CASE WHEN event_type = 'time_on_page' AND ip NOT IN ({ignore_ip_placeholders}) THEN time_on_page END), 1) as avg_seconds
        FROM analytics_events
        WHERE created_at >= ?
    """, ignore_ip_list * 4 + [since]).fetchone()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        days=days,
        page_filter=page_filter,
        pages=[dict(r) for r in page_rows],
        buttons=[dict(r) for r in button_rows],
        recent=[dict(r) for r in recent_rows],
        totals=dict(totals_row) if totals_row else {"views": 0, "clicks": 0, "sessions": 0, "avg_seconds": 0},
    )


# ── WhatsApp agent ───────────────────────────────────────────────────────────
@app.route("/webhooks/whatsapp", methods=["GET"])
def whatsapp_verify():
    """Meta webhook verification handshake."""
    challenge = wa.verify_webhook(request.args)
    if challenge is not None:
        return challenge, 200
    return "Forbidden", 403


def _cold_inbound_wa_ids(payload):
    """Walk an inbound WhatsApp webhook payload and return the set of wa_ids whose
    contact doesn't exist in our DB yet. These are the brand-new cold convos —
    each one fires a Meta CAPI Lead into the Lumen dataset (post-handle_webhook)."""
    cold = []
    seen = set()
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                for msg in (change.get("value", {}) or {}).get("messages", []) or []:
                    wid = msg.get("from")
                    if not wid or wid in seen:
                        continue
                    seen.add(wid)
                    if not wa.get_contact(wid):
                        cold.append(wid)
    except Exception as e:
        print(f"[capi-lead] pre-pass error: {e}")
    return cold


def _fire_lumen_whatsapp_lead(wa_id):
    """Fire a Meta CAPI Lead into the Lumen dataset for a cold WhatsApp convo-start.
    Runs in a background thread so the webhook 200s fast. Safe-fail."""
    try:
        # wa_id is already E.164 digits (e.g. "16235126504"); _send_capi_event will hash it.
        _send_capi_event(
            event_name="Lead",
            event_id=f"wa-lead-{wa_id}",
            user_data={"phone": wa_id},
            custom_data={
                "content_name": "WhatsApp conversation started",
                "lead_source": "whatsapp_inbound_cold",
            },
            event_source_url="https://lumenmarketing.co/lumenlb",
            dataset_id=LUMEN_META_DATASET_ID,
            access_token=LUMEN_META_CAPI_TOKEN,
            # Use the LUMEN dataset's own test-event code (empty in prod). Never the
            # MK7/DPSmgmt code — Meta would reject it for this dataset.
            test_event_code=LUMEN_META_TEST_EVENT_CODE,
        )
    except Exception as e:
        print(f"[capi-lead] fire error for {wa_id}: {e}")


def _notify_lumen_cold_start(wa_id):
    """On a brand-new cold WhatsApp convo, ping Kendall (email + WhatsApp text)
    so he knows it's happening before Layla even replies. Fires off the request
    thread and is safe-fail: any exception just prints, never blocks the webhook."""
    try:
        contact = wa.get_contact(wa_id) or {}
        label = contact.get("profile_name") or contact.get("lead_name") or ("+" + wa_id)
        snippet = (wa._last_inbound_body(wa_id) or "").strip()[:160]
        # Email notification.
        subject = f"New Lumen WhatsApp convo — {label}"
        html = (
            f"<p><b>{label}</b> just started a new WhatsApp conversation on +1 623 512 6504.</p>"
            f"<p><b>Their first message:</b> &ldquo;{snippet}&rdquo;</p>"
            f"<p>Layla is replying now. Open the thread: "
            f"<a href='https://whatsapp.mk7media.com/admin/whatsapp?id={wa_id}'>whatsapp.mk7media.com</a> "
            f"(or reply on WhatsApp: <a href='https://wa.me/{wa_id}'>wa.me/{wa_id}</a>).</p>"
        )
        wa._notify_team(subject, html)
        # WhatsApp ping to Kendall's other phone — uses kind='cold_start' so the
        # prefix reads as an FYI ('Layla is on it') instead of the alarming
        # 'lead needs a human' wording reserved for actual handoffs.
        ping = f"{label}: \"{snippet[:120]}\""
        wa.notify_handoff_whatsapp(wa_id, ping, kind="cold_start")
        print(f"[lumen-cold-notify] notified for {wa_id} ({label})")
    except Exception as e:
        print(f"[lumen-cold-notify] error for {wa_id}: {e}")


@app.route("/webhooks/whatsapp", methods=["POST"])
def whatsapp_receive():
    """Inbound WhatsApp events. Always 200s quickly so Meta doesn't retry-storm."""
    raw = request.get_data()
    _sig = request.headers.get("X-Hub-Signature-256", "")
    # Two apps deliver to this route: MK7 messaging (MK7/Lumen number) and
    # Lumen Master Connect (FGC coexistence number) — each signs with its own
    # app secret, so accept a payload that verifies against either.
    if not (wa.verify_signature(raw, _sig) or fgc_wa.verify_signature(raw, _sig)):
        return "Forbidden", 403
    payload = request.get_json(silent=True) or {}

    # Multi-number routing: both WABAs (MK7/Lumen number + the FGC coexistence
    # number) subscribe to this same app, so every event lands here. Split the
    # payload by value.metadata.phone_number_id — FGC changes go ONLY to the FGC
    # agent, everything else goes ONLY to the active profile. Without the split
    # the active profile would answer FGC customers from the wrong number.
    fgc_entries, main_entries = [], []
    for entry in payload.get("entry", []) or []:
        fgc_ch = [c for c in entry.get("changes", []) or [] if fgc_wa.is_fgc_event(c.get("value", {}) or {})]
        main_ch = [c for c in entry.get("changes", []) or [] if not fgc_wa.is_fgc_event(c.get("value", {}) or {})]
        if fgc_ch:
            fgc_entries.append({**entry, "changes": fgc_ch})
        if main_ch:
            main_entries.append({**entry, "changes": main_ch})
    # Order-entry bot: messages from whitelisted senders (Mary/Kendall) are
    # orders for the FGC store, not leads — route them to the order bot and
    # strip them out so the sales agent never replies to an order line.
    for entry in main_entries:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            msgs = value.get("messages") or []
            keep = []
            for msg in msgs:
                sender = msg.get("from", "")
                text = (msg.get("text") or {}).get("body")
                doc = msg.get("document") or {}
                is_sheet = bool(doc.get("id")) and (
                    (doc.get("filename") or "").lower().endswith((".csv", ".xlsx", ".xlsm", ".tsv"))
                    or "spreadsheet" in (doc.get("mime_type") or "")
                    or (doc.get("mime_type") or "") in ("text/csv", "application/csv"))
                if fgc_orders.is_order_sender(sender) and is_sheet:
                    # Mary can drop a whole order sheet into the chat; the bot reads
                    # it, skips anything already in the store, and enters the rest.
                    print(f"[fgc-orders] order SHEET from {sender}: {doc.get('filename')!r}")
                    fgc_orders.handle_order_sheet(sender, doc["id"], doc.get("filename"),
                                                  doc.get("caption") or msg.get("caption") or "",
                                                  wa.send_text)
                elif fgc_orders.is_order_sender(sender) and text:
                    print(f"[fgc-orders] order message from {sender}: {text[:80]!r}")
                    fgc_orders.handle_order_message(sender, text, wa.send_text)
                elif fgc_orders.is_order_sender(sender):
                    keep.append(msg)  # non-text from Mary (voice etc) -> normal agent logs it
                else:
                    keep.append(msg)
            if len(keep) != len(msgs):
                value["messages"] = keep

    main_payload = {**payload, "entry": main_entries}

    if fgc_entries:
        try:
            fgc_wa.handle_webhook({**payload, "entry": fgc_entries})
        except Exception as e:
            print(f"[fgc-wa] webhook handler error: {e}")

    # Snapshot cold-inbound wa_ids BEFORE handle_webhook creates their contact rows.
    # Pre-registered leads (via register_lead / wa.me-link flow) already have a
    # wa_contacts row with lead_source != 'inbound', so they're excluded here —
    # only people who messaged us cold (e.g. tapped the WhatsApp button on
    # /lumenlb without us knowing them first) end up in this list.
    cold = _cold_inbound_wa_ids(main_payload)

    try:
        wa.handle_webhook(main_payload)
    except Exception as e:
        print(f"[whatsapp] webhook handler error: {e}")

    # On every cold convo-start: (1) fire a CAPI Lead into the Lumen dataset
    # (only if token is set), (2) notify Kendall via email + WhatsApp ping that
    # the convo is happening so he knows BEFORE the booking handoff. Both fire
    # off the request thread so we still 200 to Meta within the retry window.
    for wid in cold:
        if LUMEN_META_CAPI_TOKEN:
            threading.Thread(target=_fire_lumen_whatsapp_lead, args=(wid,), daemon=True).start()
        threading.Thread(target=_notify_lumen_cold_start, args=(wid,), daemon=True).start()

    return "EVENT_RECEIVED", 200


@app.route("/fgc-wa/unsnooze", methods=["GET", "POST"])
@admin_required
def fgc_wa_unsnooze():
    """Clear agent snoozes. The app's automated greeting used to be mistaken for
    MK taking over, which snoozed every new lead for 4h. Use after that fix, or
    any time you want the agent back on all threads."""
    import sqlite3 as _sq
    conn = _sq.connect(fgc_wa.DB_PATH)
    n = conn.execute("UPDATE wa_contacts SET human_snooze_until = NULL "
                     "WHERE human_snooze_until IS NOT NULL").rowcount
    m = 0
    if request.args.get("release_handoffs") == "1":
        m = conn.execute("UPDATE wa_contacts SET status = 'active' "
                         "WHERE status = 'handed_off'").rowcount
    conn.commit()
    conn.close()
    return jsonify({"snoozes_cleared": n, "handoffs_released": m})


@app.route("/fgc-wa/debug")
@admin_required
def fgc_wa_debug():
    """FGC WhatsApp agent: DB state + coexistence history-sync status."""
    import sqlite3 as _sq
    out = {"db_path": fgc_wa.DB_PATH,
           "config": {"phone_number_id": fgc_wa.FGC_PHONE_NUMBER_ID,
                      "auto_reply": fgc_wa.AUTO_REPLY,
                      "reply_delay": fgc_wa.REPLY_DELAY,
                      "snooze_hours": fgc_wa.HUMAN_SNOOZE_HOURS}}
    try:
        conn = _sq.connect(fgc_wa.DB_PATH); conn.row_factory = _sq.Row
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        out["tables"] = tables
        def count(t):
            try: return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception: return None
        out["counts"] = {t: count(t) for t in tables}
        if "wa_messages" in tables:
            out["by_status"] = {r["status"]: r["n"] for r in conn.execute(
                "SELECT COALESCE(status,'live') AS status, COUNT(*) AS n "
                "FROM wa_messages GROUP BY 1")}
            out["recent"] = [dict(r) for r in conn.execute(
                "SELECT * FROM wa_messages ORDER BY id DESC LIMIT 40")]
        if "wa_contacts" in tables:
            out["contacts"] = [dict(r) for r in conn.execute(
                "SELECT * FROM wa_contacts ORDER BY wa_id")]
        conn.close()
    except Exception as e:
        out["error"] = str(e)
    return jsonify(out)


@app.route("/fgc-wa/capi")
@admin_required
def fgc_wa_capi_status():
    """CAPI dispatcher state: how many conversations carry a click id, what has fired,
    and whether we are still in dry run. The click-id count is the number that matters —
    it is the ceiling on how many conversions can ever be attributed."""
    from agents.whatsapp_agent.profiles.fgc_agent_v1_00 import capi_bm
    # Repair any clicks whose campaign could not be resolved when they arrived. Cheap
    # when there is nothing to fix, and it means the numbers below are never stale.
    try:
        fgc_wa.backfill_ad_lineage()
    except Exception as e:
        print(f"[fgc-capi] backfill skipped: {e}")
    return jsonify(capi_bm.status())


@app.route("/fgc-wa/export")
@admin_required
def fgc_wa_export():
    """Conversation transcripts, oldest-first per contact — training corpus."""
    import sqlite3 as _sq
    from collections import defaultdict
    convos = defaultdict(list)
    try:
        conn = _sq.connect(fgc_wa.DB_PATH); conn.row_factory = _sq.Row
        for r in conn.execute(
                "SELECT wa_id, direction, body, created_at, status "
                "FROM wa_messages ORDER BY created_at ASC, id ASC"):
            if not (r["body"] or "").strip():
                continue
            convos[r["wa_id"]].append({"dir": r["direction"], "text": r["body"],
                                       "at": r["created_at"], "src": r["status"]})
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)})
    return jsonify({"conversations": convos, "n_contacts": len(convos),
                    "n_messages": sum(len(v) for v in convos.values())})


@app.route("/fgc-orders/health")
@admin_required
def fgc_orders_health():
    """Debug status for the WhatsApp order-entry bot (no secrets)."""
    return jsonify(fgc_orders.health())


@app.route("/fgc-coexistence")
@admin_required
def fgc_coexistence_launcher():
    """One-time launcher for the FGC WhatsApp coexistence embedded-signup flow.
    Served from mk7media.com so the FB JS SDK gets the HTTPS origin it demands.
    Admin-gated; harmless to leave in place after onboarding (reusable for
    future client coexistence setups — swap CONFIG_ID)."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>FGC WhatsApp Coexistence</title>
<style>
  body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; max-width: 720px;
         margin: 60px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.6; }
  h1 { font-size: 22px; }
  button { background: #1877f2; color: #fff; border: none; border-radius: 8px;
           font-size: 16px; font-weight: 600; padding: 14px 28px; cursor: pointer; }
  #log { margin-top: 24px; background: #f5f5f5; border-radius: 8px; padding: 16px;
         font-family: Menlo, monospace; font-size: 12px; white-space: pre-wrap; }
  .warn { background: #fff6e0; border-left: 4px solid #e0a800; padding: 10px 14px;
          border-radius: 0 8px 8px 0; font-size: 14px; margin: 16px 0; }
</style></head><body>
<h1>Feels Good Club — connect the WhatsApp app number to Cloud API</h1>
<div class="warn">In the Meta window: choose the <strong>Lumen Marketing</strong> business →
pick <strong>connect your existing WhatsApp Business app</strong> (do NOT create a new number) →
enter <strong>+961 81 873 275</strong> → QR appears → MK scans it in her WhatsApp Business app
and approves chat-history sharing.</div>
<button onclick="launch()">Launch Meta signup flow</button>
<div id="log">Ready. Copy everything that appears here to Jarvis when done.</div>
<script>
  const APP_ID = "2107067100091646";
  const CONFIG_ID = "3590341451114523";
  function log(m){ document.getElementById("log").textContent += "\\n" + m; console.log("[fgc]", m); }
  window.fbAsyncInit = function () {
    FB.init({ appId: APP_ID, autoLogAppEvents: true, xfbml: true, version: "v25.0" });
    log("SDK loaded. App " + APP_ID + ", config " + CONFIG_ID + ".");
  };
  window.addEventListener("message", (event) => {
    if (!String(event.origin).endsWith("facebook.com")) return;
    try {
      const d = JSON.parse(event.data);
      if (d.type === "WA_EMBEDDED_SIGNUP") log("EVENT: " + JSON.stringify(d, null, 2));
    } catch (e) {}
  });
  function launch() {
    if (typeof FB === "undefined") { log("SDK not loaded yet — wait 2s, click again."); return; }
    FB.login((r) => { log("Login response: " + JSON.stringify(r, null, 2)); }, {
      config_id: CONFIG_ID,
      response_type: "code",
      override_default_response_type: true,
      extras: { setup: {}, featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" },
    });
  }
</script>
<script async defer crossorigin="anonymous" src="https://connect.facebook.net/en_US/sdk.js"></script>
</body></html>"""


@app.route("/admin/whatsapp")
@admin_required
def admin_whatsapp():
    """Lightweight viewer for WhatsApp conversations + a form to kick off an outreach template."""
    detail_id = (request.args.get("id") or "").strip()
    convos = wa.recent_conversations(limit=60)
    detail = None
    if detail_id:
        detail = {"wa_id": detail_id, "contact": wa.get_contact(detail_id), "messages": wa.conversation(detail_id)}
    return render_template(
        "admin_whatsapp.html", convos=convos, detail=detail,
        generated_link=request.args.get("link"), registered_number=request.args.get("registered"),
    )


@app.route("/admin/whatsapp/send", methods=["POST"])
@admin_required
def admin_whatsapp_send():
    """Open a conversation with a lead by sending an approved message template.

    `params` accepts either `name=value|name=value` (named placeholders, e.g.
    customer_name=Sarah) or `a|b|c` (positional). With the default template and no
    params given, customer_name is auto-filled from the lead's first name.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()
    to = "".join(ch for ch in (data.get("to") or "") if ch.isdigit())
    template_name = (data.get("template") or wa.DEFAULT_TEMPLATE).strip()
    lang_code = (data.get("lang") or wa.DEFAULT_TEMPLATE_LANG).strip() or wa.DEFAULT_TEMPLATE_LANG
    lead_name = (data.get("name") or "").strip() or None
    lead_business = (data.get("business") or "").strip() or None
    lead_source = (data.get("source") or "form").strip() or "form"

    raw_params = (data.get("params") or "").strip()
    parts = [p.strip() for p in raw_params.split("|") if p.strip()] if raw_params else []
    if parts and all("=" in p for p in parts):
        body_params = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip() for p in parts}
    elif parts:
        body_params = parts
    else:
        body_params = None
    # If you left "Lead name" blank but we already know this number (they've messaged
    # in, or you pre-registered them), use the name on file.
    if not lead_name and len(to) >= 10:
        _norm = ("1" + to) if len(to) == 10 else to
        existing = wa.get_contact(_norm)
        if existing:
            lead_name = existing.get("lead_name") or existing.get("profile_name") or None
    # Our templates use a single named var {{customer_name}} — if you didn't pass any
    # params, auto-fill it from the lead name (or "there"). (If you ever make a template
    # with no variables, pass `params` = anything so this doesn't add an extra one.)
    if body_params is None:
        first_name = (lead_name or "").split(" ", 1)[0].strip() or "there"
        body_params = {"customer_name": first_name}

    if len(to) < 10 or not template_name:
        msg = "A full number with country code and a template name are required."
        if request.is_json:
            return jsonify({"error": msg}), 400
        return redirect(url_for("admin_whatsapp"))

    result = wa.start_outreach(
        to, template_name=template_name, lang_code=lang_code, body_params=body_params,
        lead_name=lead_name, lead_business=lead_business, lead_source=lead_source,
    )
    ok = bool(result)
    if request.is_json:
        return jsonify({"ok": ok, "result": result})
    return redirect(url_for("admin_whatsapp", id=to))


@app.route("/admin/whatsapp/reply", methods=["POST"])
@admin_required
def admin_whatsapp_reply():
    """A teammate replying to a lead through the MK7 number. Pauses the agent on that
    conversation (sets it to handed_off) so it doesn't reply over the human."""
    wa_id = "".join(ch for ch in (request.form.get("wa_id") or "") if ch.isdigit())
    body = (request.form.get("body") or "").strip()
    if wa_id and body:
        wa.human_reply(wa_id, body)
    return redirect(url_for("admin_whatsapp", id=wa_id))


@app.route("/admin/whatsapp/outreach-link", methods=["POST"])
@admin_required
def admin_whatsapp_outreach_link():
    """Generate a wa.me link to hand a lead so THEY message us first (the reliable
    outreach path). Optionally pre-registers the lead's number so the agent knows them."""
    data = request.form.to_dict()
    prefill = (data.get("prefill") or "").strip() or None
    lead_name = (data.get("name") or "").strip() or None
    lead_business = (data.get("business") or "").strip() or None
    number = "".join(ch for ch in (data.get("to") or "") if ch.isdigit())
    if number:
        wa.register_lead(number, lead_name=lead_name, lead_business=lead_business, lead_source="outreach")
    link = wa.wa_me_link(prefill)
    return redirect(url_for("admin_whatsapp", link=link, registered=number or None))


@app.route("/admin/whatsapp/debug")
@admin_required
def admin_whatsapp_debug():
    """Raw dump of the WhatsApp tables + config — for troubleshooting."""
    conn = sqlite3.connect(wa.WHATSAPP_DB)
    conn.row_factory = sqlite3.Row
    msgs = [dict(r) for r in conn.execute("SELECT * FROM wa_messages ORDER BY id DESC LIMIT 100")]
    cts = [dict(r) for r in conn.execute("SELECT * FROM wa_contacts ORDER BY wa_id")]
    conn.close()
    return jsonify({
        "db_path": wa.WHATSAPP_DB,
        "config": {
            "auto_reply": wa.WHATSAPP_AUTO_REPLY,
            "model": wa.WHATSAPP_AGENT_MODEL,
            "has_anthropic_key": bool(wa.ANTHROPIC_API_KEY),
            "has_access_token": bool(wa.WHATSAPP_ACCESS_TOKEN),
            "has_app_secret": bool(wa.WHATSAPP_APP_SECRET),
            "handoff_number": wa.WHATSAPP_HANDOFF_NUMBER,
            "default_template": wa.DEFAULT_TEMPLATE,
            "default_template_lang": wa.DEFAULT_TEMPLATE_LANG,
        },
        "contacts": cts,
        "messages": msgs,
    })


@app.route("/admin/whatsapp/handoff", methods=["POST"])
@admin_required
def admin_whatsapp_handoff():
    """Toggle a conversation between agent-driven ('active') and human-owned ('handed_off')."""
    wa_id = "".join(ch for ch in (request.form.get("wa_id") or "") if ch.isdigit())
    new_status = (request.form.get("status") or "handed_off").strip()
    if wa_id and new_status in ("active", "handed_off", "opted_out"):
        wa.set_contact_status(wa_id, new_status)
    return redirect(url_for("admin_whatsapp", id=wa_id))


@app.route("/admin/whatsapp/reset", methods=["POST"])
@admin_required
def admin_whatsapp_reset():
    """Delete a contact and all their stored messages. For profile-testing:
    lets you re-run a cold-lead flow from your own phone after we've swapped
    agent profiles. Does NOT touch anything on Meta's side — the lead's
    phone still shows the full thread; they just look 'new' to our DB."""
    wa_id = "".join(ch for ch in (request.form.get("wa_id") or "") if ch.isdigit())
    if not wa_id:
        return redirect(url_for("admin_whatsapp"))
    conn = sqlite3.connect(wa.WHATSAPP_DB)
    try:
        n_msgs = conn.execute("DELETE FROM wa_messages WHERE wa_id = ?", (wa_id,)).rowcount
        n_contacts = conn.execute("DELETE FROM wa_contacts WHERE wa_id = ?", (wa_id,)).rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"[admin] wiped wa_id={wa_id}: {n_contacts} contact(s), {n_msgs} message(s)")
    return redirect(url_for("admin_whatsapp"))


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5050)
