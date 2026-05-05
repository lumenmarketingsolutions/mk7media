import os
import json
import hashlib
import time
import uuid
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ── Config ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "marykatezarehghazarian@gmail.com")
NOTIFY_RECIPIENTS = [NOTIFY_EMAIL, "mary@mk7media.com", "kendall@lumenmarketing.co"]

# Meta Conversions API — DPSmgmt dataset
META_DATASET_ID = os.environ.get("META_DATASET_ID", "2251653638703742")
META_CAPI_ACCESS_TOKEN = os.environ.get("META_CAPI_ACCESS_TOKEN", "")
META_TEST_EVENT_CODE = os.environ.get("META_TEST_EVENT_CODE", "")  # optional, for Events Manager Test Events tab

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


def _send_capi_event(event_name, event_id, user_data, custom_data=None, event_source_url=None):
    """POST a server-side event to Meta Conversions API. Safe-fail: returns silently on any error."""
    if not META_CAPI_ACCESS_TOKEN or not META_DATASET_ID:
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
        if META_TEST_EVENT_CODE:
            payload["test_event_code"] = META_TEST_EVENT_CODE

        url = f"https://graph.facebook.com/v19.0/{META_DATASET_ID}/events?access_token={META_CAPI_ACCESS_TOKEN}"
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

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/marlatabet")
def marlatabet_proposal():
    return render_template("marlatabet.html")


@app.route("/marlatabet/reel")
def marlatabet_reel():
    return render_template("marlatabet_reel.html")

def _whatsapp_digits(value):
    return "".join(c for c in (value or "") if c.isdigit())

def _build_inquiry_email(name, email, whatsapp, business, website, service_type, budget, worked_with_agency, goals):
    dash = "\u2014"
    goals_block = ""
    if goals:
        goals_block = (
            '<div style="margin-top: 24px; padding: 16px; background: #f9f9f9; border-radius: 8px;">'
            '<p style="margin: 0 0 4px; color: #888; font-size: 13px;">Goals</p>'
            f'<p style="margin: 0; color: #111;">{goals}</p>'
            '</div>'
        )

    wa_button = ""
    wa_digits = _whatsapp_digits(whatsapp)
    if wa_digits:
        first_name = (name or "there").split(" ", 1)[0]
        prefill = f"Hi {first_name}, this is Marykate from MK7 Media. Saw your inquiry \u2014 happy to dig in. When works for a quick chat?"
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
        f'<tr><td style="padding: 8px 0; color: #888;">Email</td><td style="padding: 8px 0; color: #111;">{email}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Business</td><td style="padding: 8px 0; color: #111;">{business or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Website</td><td style="padding: 8px 0; color: #111;">{website or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Service</td><td style="padding: 8px 0; color: #111;">{service_type or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Monthly Budget</td><td style="padding: 8px 0; color: #111;">{budget or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Worked w/ Agency</td><td style="padding: 8px 0; color: #111;">{worked_with_agency or dash}</td></tr>'
        '</table>'
        f'{goals_block}'
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
    worked_with_agency = data.get("worked_with_agency", "").strip()
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
                "html": _build_inquiry_email(name, email, whatsapp, business, website, service_type, budget, worked_with_agency, goals)
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

    try:
        amount = float(payload.get("price") or payload.get("amount") or payload.get("total") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    currency = (payload.get("currency") or "USD").upper()
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


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5050)
