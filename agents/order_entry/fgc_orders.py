"""
FGC WhatsApp order-entry bot.

Mary (or Kendall) WhatsApps order lines to the Lumen number (+1 623 512 6504)
in the format she already uses ("3900511 / 14$ / ghazir", names/2 pcs optional,
multiple orders per message fine). This module:

  1. Only activates for senders whitelisted in FGC_ORDER_SENDERS (comma-separated
     wa_ids, digits only). Everyone else falls through to the normal agent.
  2. Parses the message with Claude into structured orders.
  3. Creates each order in the FGC Shopify store via the draft-order flow
     (identical to manual entry: agreed price includes $3 delivery, line
     discounted, COD pending, tagged WhatsApp).
  4. Replies in the chat with a confirmation or a "couldn't read that" nudge.

Env (Railway):
  FGC_ORDER_SENDERS            e.g. "96179018107,12085910132" — REQUIRED to activate
  FGC_SHOPIFY_CLIENT_ID        Jarvis Ops app client id
  FGC_SHOPIFY_CLIENT_SECRET    Jarvis Ops app client secret
  ANTHROPIC_API_KEY            shared with the agents
Conventions (fixed): Lebanese numbers get +961, price includes $3 delivery,
default product = Migraine Relief Cap. "2 pcs" = quantity 2 at that total.
"""

import os
import json
import time
import threading
import urllib.request

SHOP = "https://hd8wtv-ck.myshopify.com"
API_VERSION = "2025-07"
CAP_VARIANT = 46831330427079
CAP_PRICE = 19.99
VARIANTS = {  # product keyword -> (variant_id, unit_price)
    "cap": (46831330427079, 19.99),
    "patches": (46831330721991, 12.99),
    "strips": (46831330885831, 12.00),
}

FGC_ORDER_SENDERS = {
    "".join(ch for ch in s if ch.isdigit())
    for s in os.environ.get("FGC_ORDER_SENDERS", "").split(",") if s.strip()
}
SHOPIFY_CLIENT_ID = os.environ.get("FGC_SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("FGC_SHOPIFY_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PARSE_MODEL = os.environ.get("FGC_ORDER_PARSE_MODEL", "claude-sonnet-5")

_token_cache = {"token": None, "expires": 0}
_last_errors = []  # ring buffer of recent failures for the /fgc-orders/health endpoint


def _record_error(where, err):
    _last_errors.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "where": where, "error": str(err)[:300]})
    del _last_errors[:-10]
    print(f"[fgc-orders] {where}: {err}")


def health():
    """Status dict for the admin debug endpoint — no secrets, live checks."""
    out = {
        "senders_whitelisted": sorted(FGC_ORDER_SENDERS),
        "shopify_creds_present": bool(SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET),
        "anthropic_key_present": bool(ANTHROPIC_API_KEY),
        "recent_errors": list(_last_errors),
    }
    try:
        _shopify_token()
        shop = _shopify("GET", "/shop.json?fields=name")
        out["shopify_connection"] = "OK - " + str((shop.get("shop") or {}).get("name", shop))
    except Exception as e:
        out["shopify_connection"] = "FAILED - " + str(e)[:200]
    return out


def is_order_sender(wa_id):
    return bool(FGC_ORDER_SENDERS) and "".join(ch for ch in str(wa_id) if ch.isdigit()) in FGC_ORDER_SENDERS


def _shopify_token():
    if _token_cache["token"] and time.time() < _token_cache["expires"] - 300:
        return _token_cache["token"]
    body = json.dumps({"grant_type": "client_credentials",
                       "client_id": SHOPIFY_CLIENT_ID,
                       "client_secret": SHOPIFY_CLIENT_SECRET}).encode()
    req = urllib.request.Request(SHOP + "/admin/oauth/access_token", body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    _token_cache["token"] = d["access_token"]
    _token_cache["expires"] = time.time() + int(d.get("expires_in", 86400))
    return _token_cache["token"]


def _shopify(method, path, body=None):
    req = urllib.request.Request(SHOP + f"/admin/api/{API_VERSION}" + path, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Shopify-Access-Token", _shopify_token())
    data = json.dumps(body).encode() if body is not None else b""
    req.add_header("Content-Length", str(len(data)))
    try:
        with urllib.request.urlopen(req, data if method in ("POST", "PUT") else None, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "body": (e.read() or b"")[:300].decode("utf-8", "replace")}


PARSE_PROMPT = """You parse WhatsApp order messages for a Lebanese cash-on-delivery store. \
Messages contain one or more orders, typically "phone / price / city" with optional name, \
"2 pcs"/"2 pieces" (quantity), address details, or product hints (cap/patches/strips — \
default is cap). Reply ONLY with JSON: {"orders": [{"phone": "...", "price": 16, \
"quantity": 1, "city": "...", "name": "", "address": "", "product": "cap"}], \
"not_orders": "text that wasn't parseable as an order, or empty string"}. \
Rules: phone exactly as written (keep leading zeros / country codes). price = the total \
number they wrote (it includes delivery). quantity from "2 pcs" style notes, else 1. \
If the message contains no orders at all, return {"orders": [], "not_orders": "<the text>"}."""


def _parse_orders(text):
    body = json.dumps({
        "model": PARSE_MODEL, "max_tokens": 2000,
        "system": PARSE_PROMPT,
        "messages": [{"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", ANTHROPIC_API_KEY)
    req.add_header("anthropic-version", "2023-06-01")
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    raw = "".join(b.get("text", "") for b in d.get("content", []))
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    return json.loads(raw)


import re

_LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z][A-Za-z .']{1,30})?\s*(?P<phone>\+?\d[\d ]{5,14})\s*/\s*\$?\s*(?P<price>\d{1,3})\s*\$?\s*(?:/\s*(?P<rest>.+))?$"
)


def _regex_parse(text):
    """Deterministic fallback for the standard 'number / price / city' format —
    works without the Claude API (used when the API call fails, e.g. no credits)."""
    orders, leftovers = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            leftovers.append(line)
            continue
        rest = (m.group("rest") or "").strip()
        qty = 2 if re.search(r"2\s*(pcs|pieces|pc)", rest, re.I) else 1
        city = re.sub(r"/?\s*2\s*(pcs|pieces|pc)\s*/?", "", rest, flags=re.I).strip(" /") or "Lebanon"
        orders.append({"phone": m.group("phone").replace(" ", ""), "price": int(m.group("price")),
                       "quantity": qty, "city": city, "name": (m.group("name") or "").strip(),
                       "address": "", "product": "cap"})
    return {"orders": orders, "not_orders": "\n".join(leftovers)}


def _norm_phone(raw):
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if str(raw).strip().startswith("+") and not digits.startswith("961"):
        return "+" + digits          # explicit foreign number, keep as written
    if digits.startswith("961"):
        return "+" + digits
    if digits.startswith("0"):
        digits = digits[1:]
    return "+961" + digits


def _enter_order(o):
    product = (o.get("product") or "cap").lower()
    variant_id, unit = VARIANTS.get(product, VARIANTS["cap"])
    qty = max(1, int(o.get("quantity") or 1))
    price = float(o["price"])
    goods = round(price - 3, 2)
    disc_per_unit = round((unit * qty - goods) / qty, 2)
    name = (o.get("name") or "").strip()
    first, last = (name.split(" ", 1) + [""])[:2] if name else ("WhatsApp", "".join(ch for ch in str(o["phone"]) if ch.isdigit()))
    addr = (o.get("address") or "").strip() or o.get("city") or "Lebanon"
    note = f"Auto-entered from Mary's WhatsApp. Agreed {price:g}$ incl 3$ delivery."
    body = {"draft_order": {
        "line_items": [{"variant_id": variant_id, "quantity": qty,
                        "applied_discount": {"description": "WhatsApp agreed price",
                                             "value_type": "fixed_amount",
                                             "value": str(disc_per_unit), "amount": str(disc_per_unit)}}],
        "shipping_address": {"first_name": first, "last_name": last or first,
                             "address1": addr, "city": o.get("city") or "Lebanon",
                             "country": "Lebanon", "phone": _norm_phone(o["phone"])},
        "shipping_line": {"title": "Delivery", "price": "3.00"},
        "tags": "WhatsApp, auto-entry",
        "note": note}}
    d = _shopify("POST", "/draft_orders.json", body)
    draft = d.get("draft_order")
    if not draft:
        return None, f"draft failed: {d.get('body', d)}"
    done = _shopify("PUT", f"/draft_orders/{draft['id']}/complete.json?payment_pending=true")
    order_id = (done.get("draft_order") or {}).get("order_id")
    if not order_id:
        return None, f"complete failed: {done.get('body', done)}"
    order = _shopify("GET", f"/orders/{order_id}.json?fields=name,total_price").get("order", {})
    return order, None


def handle_order_message(wa_id, text, send_text):
    """Entry point — called from the webhook route for whitelisted senders.
    Runs async so the webhook can ack immediately."""
    def work():
        try:
            if not (SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET):
                send_text(wa_id, "Order bot isn't configured yet (missing store credentials). Tell Kendall.")
                return
            try:
                _shopify_token()
            except Exception as e:
                _record_error("shopify_token", e)
                send_text(wa_id, "Order bot can't reach the store (credentials rejected). Tell Kendall to check the Shopify vars.")
                return
            try:
                parsed = _parse_orders(text)
            except Exception as e:
                _record_error("parse", e)
                parsed = _regex_parse(text)  # AI parser down (e.g. no API credits) -> deterministic fallback
                if not parsed.get("orders"):
                    send_text(wa_id, "Order bot couldn't read that. Use: number / price / city (one order per line).")
                    return
            orders = parsed.get("orders") or []
            if not orders:
                send_text(wa_id, "I couldn't read an order in that. Format: number / price / city (name and \"2 pcs\" optional).")
                return
            lines, fails = [], []
            for o in orders:
                order, err = _enter_order(o)
                if order:
                    lines.append(f"✅ {order.get('name')} · ${order.get('total_price')} · {o.get('city', '')}".strip())
                else:
                    fails.append(f"⚠️ {o.get('phone')} / {o.get('price')}$ — {err}")
            reply = "\n".join(lines + fails)
            if len(orders) > 1:
                reply = f"Entered {len(lines)}/{len(orders)} orders:\n" + reply
            send_text(wa_id, reply[:3900])
        except Exception as e:
            _record_error("entry", e)
            try:
                send_text(wa_id, "Something broke entering that order — Kendall's been notified, try once more or send it to him.")
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()
