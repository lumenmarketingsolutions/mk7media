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
# Fallback prices only — the live price is fetched from Shopify per order (see
# _live_unit_price). NEVER trust these for discount math: when the store gets
# repriced and this table lags, the discount lands on the wrong base price
# (08.25-08.27 bug: cap repriced 19.99 -> 12.00, orders entered at 8.51 instead
# of the agreed 16.50).
VARIANTS = {  # product keyword -> (variant_id, fallback_unit_price)
    "cap": (46831330427079, 12.00),
    "patches": (46831330721991, 12.00),
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
"2 pcs"/"2 pieces"/"2 boxes" (quantity), address details, or product hints (cap/patches/strips — \
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

# Accepts: "3900511 / 14$ / ghazir", "03-900-511 - 14 - ghazir", "3900511 14$ ghazir",
# "+961 3 900 511 | 16.5$ | Beirut 2 pcs", optional leading name, optional product word.
_SEP = r"\s*(?:/|-|\||,|\s)\s*"
_LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF .']{1,30}?)?\s*"
    r"(?P<phone>\+?\d[\d \-]{5,16}\d)"
    + _SEP +
    r"\$?\s*(?P<price>\d{1,3}(?:[.,]\d{1,2})?)\s*(?:\$|usd|dollars?)?"
    r"(?:" + _SEP + r"(?P<rest>.+))?\s*$",
    re.I,
)
_QTY_RE = re.compile(r"(?:(?P<a>\d)\s*(?:pcs?|pieces?|pc|boxes|box|x)\b|\bx\s*(?P<b>\d)\b)", re.I)
_PRODUCT_WORDS = {"patches": "patches", "patch": "patches", "pimple": "patches",
                  "strips": "strips", "strip": "strips", "whitening": "strips", "cap": "cap", "caps": "cap"}


def _regex_parse(text):
    """Deterministic parser for the 'number / price / city' format — runs FIRST so
    orders never depend on the Claude API (credits, outages)."""
    orders, leftovers = [], []
    for line in text.splitlines():
        line = line.strip().strip("•-* ")
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            leftovers.append(line)
            continue
        rest = (m.group("rest") or "").strip()
        qm = _QTY_RE.search(rest)
        qty = int(qm.group("a") or qm.group("b")) if qm else 1
        product = "cap"
        for w, prod in _PRODUCT_WORDS.items():
            if re.search(r"\b" + w + r"\b", rest, re.I):
                product = prod
                rest = re.sub(r"\b" + w + r"\b", "", rest, flags=re.I)
                break
        city = _QTY_RE.sub("", rest).strip(" /|,-") or "Lebanon"
        phone = re.sub(r"[\s\-]", "", m.group("phone"))
        price = float(m.group("price").replace(",", "."))
        orders.append({"phone": phone, "price": price, "quantity": max(1, qty), "city": city,
                       "name": (m.group("name") or "").strip(), "address": "", "product": product})
    return {"orders": orders, "not_orders": "\n".join(leftovers)}


_price_cache = {}  # variant_id -> (price, fetched_at)


def _live_unit_price(variant_id, fallback):
    """Current store price for a variant, cached 1h. Falls back to the static
    table only if Shopify can't be reached (order still gets total-verified)."""
    hit = _price_cache.get(variant_id)
    if hit and time.time() - hit[1] < 3600:
        return hit[0]
    try:
        v = _shopify("GET", f"/variants/{variant_id}.json?fields=price")
        price = float(v["variant"]["price"])
        _price_cache[variant_id] = (price, time.time())
        return price
    except Exception as e:
        _record_error("live_price", f"variant {variant_id}: {e}")
        return hit[0] if hit else fallback


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
    variant_id, fallback = VARIANTS.get(product, VARIANTS["cap"])
    unit = _live_unit_price(variant_id, fallback)
    qty = max(1, int(o.get("quantity") or 1))
    price = float(o["price"])
    goods = round(price - 3, 2)
    disc_per_unit = max(0.0, round((unit * qty - goods) / qty, 2))
    # If the agreed price is above list, no discount applies; put the difference on
    # the delivery line so the order total always equals what was agreed.
    shipping = round(price - (unit * qty - disc_per_unit * qty), 2)
    name = (o.get("name") or "").strip()
    first, last = (name.split(" ", 1) + [""])[:2] if name else ("WhatsApp", "".join(ch for ch in str(o["phone"]) if ch.isdigit()))
    addr = (o.get("address") or "").strip() or o.get("city") or "Lebanon"
    note = f"Auto-entered from WhatsApp. Agreed {price:g}$ incl 3$ delivery."
    body = {"draft_order": {
        "line_items": [{"variant_id": variant_id, "quantity": qty,
                        "applied_discount": {"description": "WhatsApp agreed price",
                                             "value_type": "fixed_amount",
                                             "value": str(disc_per_unit), "amount": str(disc_per_unit)}}],
        "shipping_address": {"first_name": first, "last_name": last or first,
                             "address1": addr, "city": o.get("city") or "Lebanon",
                             "country": "Lebanon", "phone": _norm_phone(o["phone"])},
        "shipping_line": {"title": "Delivery", "price": f"{shipping:.2f}"},
        "tags": "WhatsApp, auto-entry",
        "note": note}}
    d = _shopify("POST", "/draft_orders.json", body)
    draft = d.get("draft_order")
    if not draft:
        return None, f"draft failed: {d.get('body', d)}"
    # HARD RULE: the order total must equal the agreed price before it becomes a
    # real order. If Shopify's computed total disagrees (repriced product, math
    # drift), the draft is deleted and nothing is entered.
    draft_total = float(draft.get("total_price") or 0)
    if abs(draft_total - price) > 0.01:
        _shopify("DELETE", f"/draft_orders/{draft['id']}.json")
        _record_error("total_mismatch",
                      f"draft total {draft_total:.2f} != agreed {price:g} (variant {variant_id}, qty {qty})")
        return None, (f"store total came out ${draft_total:.2f} but agreed price is ${price:g} — "
                      "NOT entered (store prices may have changed). Tell Kendall.")
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
            parsed = _regex_parse(text)
            if not parsed.get("orders"):
                # Standard format didn't match -> let Claude try the messy version.
                try:
                    parsed = _parse_orders(text)
                except Exception as e:
                    _record_error("parse", f"{e} | text={text[:120]!r}")
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
