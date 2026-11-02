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
import urllib.error
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
    "nose": (67793943593159, 12.00),
    "toothpaste": (67815239024839, 12.00),
}
# Human names for the confirmation reply — Mary should see WHAT was ordered, not
# just a total, so a wrong-product entry is obvious the moment it is made.
PRODUCT_NAMES = {
    "cap": "Migraine Cap",
    "patches": "Pimple Patches",
    "strips": "Whitening Strips",
    "nose": "Nose Strips",
    "toothpaste": "Whitening Toothpaste",
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


def _xlsx_available():
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


def health():
    """Status dict for the admin debug endpoint — no secrets, live checks."""
    out = {
        "senders_whitelisted": sorted(FGC_ORDER_SENDERS),
        "shopify_creds_present": bool(SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET),
        "anthropic_key_present": bool(ANTHROPIC_API_KEY),
        "whatsapp_token_present": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")),
        "sheet_import": {"csv": True, "xlsx": _xlsx_available()},
        "recent_errors": list(_last_errors),
        "kept_sheets": kept_sheets(),
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


def _urlopen(req, data=None, timeout=30):
    """urlopen that survives a brief network drop (11.01: 'Network is unreachable'
    killed a whole sheet mid-import). Only connection failures are retried; those
    never reached Shopify, so a retried POST cannot create a second draft."""
    for wait in (2, 5, None):
        try:
            return urllib.request.urlopen(req, data, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if wait is None or "timed out" in str(e):
                raise
            time.sleep(wait)


def _shopify_token():
    if _token_cache["token"] and time.time() < _token_cache["expires"] - 300:
        return _token_cache["token"]
    body = json.dumps({"grant_type": "client_credentials",
                       "client_id": SHOPIFY_CLIENT_ID,
                       "client_secret": SHOPIFY_CLIENT_SECRET}).encode()
    req = urllib.request.Request(SHOP + "/admin/oauth/access_token", body, method="POST")
    req.add_header("Content-Type", "application/json")
    with _urlopen(req, body, timeout=20) as r:
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
        with _urlopen(req, data if method in ("POST", "PUT") else None, timeout=30) as r:
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
# Order matters: the first hit wins, so "nose strips" and "whitening toothpaste"
# must be tested before the plain "strips" / "whitening" words.
_PRODUCT_WORDS = {"nose": "nose", "nasal": "nose", "toothpaste": "toothpaste", "paste": "toothpaste",
                  "\u0645\u0639\u062c\u0648\u0646": "toothpaste", "\u0627\u0646\u0641": "nose", "\u0627\u0644\u0627\u0646\u0641": "nose",
                  "migraine": "cap", "\u0643\u0627\u0628": "cap", "\u0642\u0628\u0639\u0629": "cap",
                  "\u062a\u0628\u064a\u064a\u0636": "strips",
                  "patches": "patches", "patch": "patches", "pimple": "patches",
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


# ---------------------------------------------------------------- duplicates
# A sheet can be sent twice, or a corrected sheet can overlap an earlier one, so
# every import checks the store first. The key is the customer's phone number:
# these are one-off COD orders, so the same number appearing again is almost
# always a re-import rather than a genuine second purchase.
_orders_cache = {"index": None, "at": 0}


def _norm_digits(raw):
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if d.startswith(("961", "963")):
        d = d[3:]
    return d.lstrip("0")


def _existing_orders_index(max_pages=6):
    """{phone_digits: [{name, total, product}]} for recent store orders, cached 5min."""
    if _orders_cache["index"] is not None and time.time() - _orders_cache["at"] < 300:
        return _orders_cache["index"]
    idx = {}
    path = ("/orders.json?status=any&limit=250"
            "&fields=id,name,total_price,shipping_address,line_items,created_at")
    try:
        for _ in range(max_pages):
            d = _shopify("GET", path)
            orders = d.get("orders") or []
            if not orders:
                break
            for o in orders:
                ph = _norm_digits(((o.get("shipping_address") or {}).get("phone")))
                if not ph:
                    continue
                items = ", ".join((li.get("title") or "") for li in (o.get("line_items") or [])[:2])
                idx.setdefault(ph, []).append({
                    "name": o.get("name"), "total": float(o.get("total_price") or 0),
                    "product": items, "created": (o.get("created_at") or "")[:10]})
            if len(orders) < 250:
                break
            last = orders[-1]["id"]
            path = ("/orders.json?status=any&limit=250&since_id=%s"
                    "&fields=id,name,total_price,shipping_address,line_items,created_at" % last)
        _orders_cache["index"] = idx
        _orders_cache["at"] = time.time()
    except Exception as e:
        _record_error("orders_index", e)
        return _orders_cache["index"] or {}
    return idx


def _duplicate_of(o, index):
    """Returns (existing_order_dict, exact_bool) if this order looks already entered."""
    hits = index.get(_norm_digits(o.get("phone")))
    if not hits:
        return None, False
    price = float(o.get("price") or 0)
    for h in hits:
        if abs(h["total"] - price) <= 0.01:
            return h, True          # same number, same total -> re-import
    return hits[0], False           # same number, different total -> flag, still enter


# ------------------------------------------------------------------ media/sheets
GRAPH = "https://graph.facebook.com/v21.0"


def _download_media(media_id):
    """WhatsApp media is two hops: metadata (gives a signed url), then the bytes."""
    import requests
    tok = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    if not tok:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN not set")
    h = {"Authorization": "Bearer " + tok}
    meta = requests.get(f"{GRAPH}/{media_id}", headers=h, timeout=30).json()
    url = meta.get("url")
    if not url:
        raise RuntimeError(f"no media url: {str(meta)[:200]}")
    r = requests.get(url, headers=h, timeout=90)
    r.raise_for_status()
    return r.content, (meta.get("mime_type") or "")


# Each courier exports different columns, so columns are chosen from the header AND
# the values under it. 11.01 bug: a new courier sheet (Shamify) produced $0 on every
# row because the first column whose title merely contained a price word won.
_COL_HINTS = {
    "phone": ("phone", "mobile", "number", "contact", "whatsapp", "tel", "num",
              "هاتف", "موبايل", "جوال", "رقم"),
    "quantity": ("qty", "quantity", "pcs", "pieces", "count", "كمية", "العدد"),
    "cancelled": ("cancel", "ملغ"),
    "status": ("status", "حالة"),
    "country": ("country", "بلد", "دولة"),
    "city": ("city", "area", "region", "town", "location", "governorate",
             "مدينة", "منطقة", "محافظة"),
    "address": ("address", "عنوان"),
    "product": ("product", "item", "sku", "type", "منتج", "صنف"),
    "name": ("name", "customer", "client", "recipient", "اسم", "زبون"),
}
_COL_NOT = {
    "phone": ("order", "ref", "invoice", "tracking", "awb", "barcode", "name", "address", "id", "#"),
    "price": ("delivery", "shipping", "fee", "commission", "discount", "syp", "lbp", "ل.س", "ليرة",
              "توصيل", "شحن", "date", "id"),
    "quantity": ("discount", "account"),
    "city": ("fee", "cost", "price", "date", "status", "time", "charge"),
    "address": ("fee", "cost", "price", "date", "status", "ip"),
    "product": ("delivery", "shipping", "order", "id", "price", "cost", "total", "payment"),
    "name": ("product", "item", "file", "company", "sender", "store", "shop", "phone", "mobile", "number",
             "address", "city", "id", "tel"),
    "cancelled": ("reason",),
}
# Best first: a column labelled USD beats cash-to-collect, which beats a generic total.
_PRICE_RANKS = (
    ("usd", "dollar", "دولار", "$"),
    ("cod", "collect", "cash", "تحصيل"),
    ("total", "grand", "amount", "مجموع", "اجمالي", "إجمالي", "مبلغ"),
    ("price", "سعر", "value", "cost", "paid"),
)
_SHORT = {"id", "tel", "num", "cod", "usd", "syp", "lbp", "ref", "ip", "sku", "fee"}
_PRICE_MIN, _PRICE_MAX = 3.0, 500.0   # an FGC order in USD; SYP/LBP totals fall outside


def _has(cell, hint):
    if hint in _SHORT:
        return re.search(r"(?<![a-z])" + re.escape(hint) + r"(?![a-z])", cell) is not None
    return hint in cell


def _cell(v):
    """Excel stores phones and prices as numbers; 96170123456.0 must not gain a digit."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _parse_price(raw):
    """A USD price from a cell, or None. '16', '16.5$', 'USD 16' and '16$ / 195000 SYP'
    all work; a bare '1,500' or a SYP figure does not count as a price."""
    t = str(raw or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).strip()
    m = (re.search(r"(?:\$|usd)\s*(\d+(?:[.,]\d{1,2})?)(?!\d)", t, re.I)
         or re.search(r"(?<![\d.,])(\d+(?:[.,]\d{1,2})?)\s*(?:\$|usd|دولار)", t, re.I)
         or re.fullmatch(r"(\d+(?:[.,]\d{1,2})?)", t))
    return float(m.group(1).replace(",", ".")) if m else None


def _phone_like(raw):
    return 7 <= len(re.sub(r"\D", "", _cell(raw))) <= 15


def _candidates(header, field):
    out = []
    for i, cell in enumerate(header):
        c = _cell(cell).lower()
        if c and any(_has(c, h) for h in _COL_HINTS[field]) and not any(_has(c, x) for x in _COL_NOT.get(field, ())):
            out.append(i)
    return out


def _price_candidates(header):
    out = []
    for rank, hints in enumerate(_PRICE_RANKS):
        for i, cell in enumerate(header):
            c = _cell(cell).lower().replace("cash on delivery", "cod")
            if c and i not in out and any(_has(c, h) for h in hints) \
                    and not any(_has(c, x) for x in _COL_NOT["price"]):
                out.append(i)
    return out


def _map_columns(header, data=()):
    """header + the rows under it -> {field: column index}."""
    col = lambda r, i: r[i] if i < len(r) else None
    out = {}
    phones = _candidates(header, "phone")
    if phones:
        out["phone"] = max(phones, key=lambda i: (sum(_phone_like(col(r, i)) for r in data), -i))
    prices = [i for i in _price_candidates(header) if i != out.get("phone")]
    if prices:
        # First column, in rank order, that holds real prices on at least 30% of the
        # rows. All-zero or SYP columns lose. With none, keep the top one so the reply
        # can name the column that had no usable price in it.
        need = max(1, int(len(data) * 0.3))
        def real(i):
            n = 0
            for r in data:
                v = _parse_price(_cell(col(r, i)))
                n += v is not None and _PRICE_MIN <= v <= _PRICE_MAX
            return n
        out["price"] = next((i for i in prices if real(i) >= need), prices[0])
    used = set(out.values())
    for field in ("quantity", "cancelled", "status", "country", "city", "address", "product", "name"):
        for i in _candidates(header, field):
            if i not in used:
                out[field] = i
                used.add(i)
                break
    return out


def _find_table(rows):
    """Locate the header (exports often open with title rows). -> (cols, start, header)"""
    for i, r in enumerate(rows[:15]):
        m = _map_columns(r, rows[i + 1:])
        if "phone" in m and "price" in m:
            return m, i + 1, r
    return {}, 0, rows[0] if rows else []


def _rows_from_bytes(data, filename, mime):
    """CSV or XLSX bytes -> list of row lists."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or "spreadsheetml" in (mime or ""):
        import io
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("xlsx support not installed on the server (openpyxl)")
        # Not read_only: that mode trusts the file's stated dimensions, which exports
        # from web apps often get wrong, and it silently drops columns.
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        tabs = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
        for t in tabs:                       # first tab that actually has an order table
            kept = [r for r in t if any(_cell(c) for c in r)]
            if _find_table(kept)[0]:
                return t
        return tabs[0] if tabs else []
    import csv, io as _io
    txt = data.decode("utf-8-sig", "replace")
    # Try every common delimiter and keep the parse that actually yields a usable
    # table. Sniffer alone is unreliable on hand-made sheets (mixed separators,
    # semicolons from Excel in some locales, a stray comma inside a name).
    best, best_score = None, -1
    for delim in (",", ";", "\t", "|"):
        try:
            rows = [r for r in csv.reader(_io.StringIO(txt), delimiter=delim)]
        except Exception:
            continue
        if not rows:
            continue
        widths = [len(r) for r in rows if any(str(c or "").strip() for c in r)]
        if not widths:
            continue
        width = max(set(widths), key=widths.count)      # most common row width
        score = width * 10
        for r in rows[:5]:                              # a mappable header is worth more
            m = _map_columns(r)
            if "phone" in m and "price" in m:
                score += 100
                break
        if width < 2:
            score -= 50
        if score > best_score:
            best, best_score = rows, score
    return best or [r for r in csv.reader(_io.StringIO(txt))]


def _sheet_product(prod_raw, city):
    """-> (product key, None) or (None, reason). A product cell we can't match is a
    problem to report: guessing here means the wrong item gets packed."""
    prod = prod_raw.strip().lower()
    if prod and not re.fullmatch(r"[\d.\s]+", prod):
        found = []
        # "Nose Strips" and "Whitening Toothpaste" are one product each, not two.
        rest = re.sub(r"\b(nose|nasal)\s+strips?\b", "nose", prod)
        rest = re.sub(r"\bwhitening\s+(toothpaste|paste)\b", "toothpaste", rest)
        for w, key in _PRODUCT_WORDS.items():
            if re.search(r"\b" + w + r"\b", rest):
                rest = re.sub(r"\b" + w + r"\b", " ", rest)
                if key not in found:
                    found.append(key)
        if len(found) == 1:
            return found[0], None
        if found:
            return None, "more than one product"
        return None, f"unknown product '{prod_raw[:25]}'"
    for w, key in _PRODUCT_WORDS.items():
        if re.search(r"\b" + w + r"\b", city.lower()):
            return key, None
    return "cap", None


def _orders_from_sheet(data, filename, mime):
    """Parse a sheet into the same order dicts the text parser produces.
    Returns (orders, skipped_rows, info). Info names the columns that were used."""
    rows = [r for r in _rows_from_bytes(data, filename, mime) if any(_cell(c) for c in r)]
    if not rows:
        return [], ["sheet is empty"], {"headers": [], "used": {}}
    cols, start, header = _find_table(rows)
    info = {"headers": [_cell(c) for c in (header or [])][:30],
            "used": {f: _cell(header[i]) for f, i in cols.items()}}
    orders, skipped = [], []
    for r in rows[start:]:
        get = lambda f: (_cell(r[cols[f]]) if f in cols and cols[f] < len(r) else "")
        if not cols:                           # no usable header, fall back to the text parser
            line = " / ".join(_cell(c) for c in r if _cell(c))
            p = _regex_parse(line)
            good = [o for o in p["orders"] if _PRICE_MIN <= float(o["price"]) <= _PRICE_MAX]
            if good:
                orders.extend(good)
            elif line:
                skipped.append(line[:60])
            continue
        phone, price_raw = get("phone"), get("price")
        name, city = get("name"), get("city")
        label = (" / ".join(x for x in (name, phone, price_raw, city) if x))[:50] or "blank row"
        status = (get("status") + " " + get("cancelled")).lower()
        if get("cancelled") or "cancel" in status or "ملغ" in status:
            skipped.append(f"{label} (cancelled)")
            continue
        if not _phone_like(phone):
            skipped.append(f"{label} (no phone number)")
            continue
        price = _parse_price(price_raw)
        if price is None or not (_PRICE_MIN <= price <= _PRICE_MAX):
            skipped.append(f"{label} (no USD price)")
            continue
        prod_raw = get("product")
        product, why = _sheet_product(prod_raw, city)
        if not product:
            skipped.append(f"{label} ({why})")
            continue
        # A courier's "Items" column holds a count, not a product name.
        qty_raw = get("quantity") or (prod_raw if re.fullmatch(r"\d+(\.0+)?", prod_raw) else "")
        m = re.search(r"\d+", qty_raw)
        qty = int(m.group()) if m else 1
        orders.append({"phone": phone, "price": price, "quantity": qty if 1 <= qty <= 50 else 1,
                       "city": city or "", "name": name if len(name) >= 2 else "",
                       "address": get("address"), "country": get("country"), "product": product})
    return orders, skipped, info


def _columns_line(info):
    """One line telling Mary which columns were used, so a wrong read is obvious."""
    used = info.get("used") or {}
    if used.get("phone") and used.get("price"):
        return f"Read the phone from \"{used['phone']}\" and the price from \"{used['price']}\"."
    heads = ", ".join(h for h in (info.get("headers") or []) if h)[:400]
    return f"Columns I can see: {heads or 'none'}."


# Keep the last few sheets on the volume. WhatsApp media can't be re-fetched without
# its id, so without this a failed import can't be diagnosed from the real file.
SHEET_DIR = os.environ.get("FGC_SHEET_DIR", "/data/fgc_order_sheets")
_SHEETS_KEPT = 20


def _keep_sheet(data, filename):
    try:
        os.makedirs(SHEET_DIR, exist_ok=True)
        safe = re.sub(r"[^\w.\-]+", "_", filename or "sheet")[:80]
        with open(os.path.join(SHEET_DIR, time.strftime("%Y%m%d-%H%M%S-") + safe), "wb") as f:
            f.write(data)
        for old in sorted(os.listdir(SHEET_DIR))[:-_SHEETS_KEPT]:
            os.remove(os.path.join(SHEET_DIR, old))
    except Exception as e:
        _record_error("keep_sheet", e)


def kept_sheets():
    try:
        return sorted(os.listdir(SHEET_DIR), reverse=True)
    except OSError:
        return []


def kept_sheet_path(name):
    base = os.path.basename(name or "")
    path = os.path.join(SHEET_DIR, base)
    return path if base and os.path.isfile(path) else None


def _norm_phone(raw):
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if digits.startswith("00"):
        return "+" + digits[2:]
    if str(raw).strip().startswith("+") or digits.startswith(("961", "963")):
        return "+" + digits          # already has a country code, keep as written
    if digits.startswith("09") and len(digits) == 10:
        return "+963" + digits[1:]   # Syrian mobile, local format
    if digits.startswith("9") and len(digits) == 9:
        return "+963" + digits       # Syrian mobile, no leading zero
    if len(digits) >= 10 and not digits.startswith("0"):
        return "+" + digits          # foreign number written without the +
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
    phone_fmt = _norm_phone(o["phone"])
    # Shopify refuses Syria as a shipping country (same as syria_orders.py), so those
    # go in with no country and "Syria" in address2 + tags.
    syria = phone_fmt.startswith("+963") or bool(re.search(r"syria|\u0633\u0648\u0631\u064a", str(o.get("country") or ""), re.I))
    home = "Syria" if syria else "Lebanon"
    city = (o.get("city") or "").strip() or home
    addr = (o.get("address") or "").strip() or city
    note = f"Auto-entered from WhatsApp. Agreed {price:g}$ incl 3$ delivery."
    body = {"draft_order": {
        "line_items": [{"variant_id": variant_id, "quantity": qty,
                        "applied_discount": {"description": "WhatsApp agreed price",
                                             "value_type": "fixed_amount",
                                             "value": str(disc_per_unit), "amount": str(disc_per_unit)}}],
        "shipping_address": {"first_name": first, "last_name": last or first,
                             "address1": addr, "city": city, "phone": phone_fmt,
                             **({"address2": "Syria"} if syria else {"country": "Lebanon"})},
        "shipping_line": {"title": "Delivery", "price": f"{shipping:.2f}"},
        "tags": "Syria, WhatsApp, auto-entry" if syria else "WhatsApp, auto-entry",
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
    order["_product"] = PRODUCT_NAMES.get(product, product.title())
    order["_qty"] = qty
    return order, None


# ── Agent-closed sales → Shopify ──────────────────────────────────────────────
# When the FGC WhatsApp sales agent closes a deal (customer gave a location and
# the agent confirmed), log the order here automatically. Name = the phone number,
# $12/item (or $10 each for 2+), flat $4 delivery, tagged "agent deal".
AGENT_PRODUCT_VARIANTS = {
    "Migraine Relief Cap": 46831330427079,
    "Teeth Whitening Strips": 46831330885831,
    "Pimple Patches": 46831330721991,
    # Nasal Strips and Whitening Toothpaste are not in the Shopify store yet, so
    # orders for them cannot be auto-created — they stay with MK until added.
}


def _reverse_geocode(lat, lng):
    """Coordinates -> a Lebanese area name. Best-effort; None on any failure."""
    import requests
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 14,
                    "accept-language": "en"},
            headers={"User-Agent": "FGC-Shop-Order/1.0 (feelsgoodclub.com)"},
            timeout=12,
        ).json()
        a = r.get("address", {}) or {}
        for k in ("town", "city", "village", "suburb", "municipality",
                  "county", "state_district", "state"):
            if a.get(k):
                return a[k]
    except Exception as e:
        _record_error("reverse_geocode", f"{lat},{lng}: {e}")
    return None


def enter_agent_order(*, phone, product, lat=None, lng=None, location_text=None, qty=1):
    """Create a completed COD order from an agent-closed sale.
    Returns (order_dict, None) or (None, error_string)."""
    variant_id = AGENT_PRODUCT_VARIANTS.get(product)
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if not variant_id:
        _record_error("agent_order", f"no Shopify variant for {product!r} (phone {digits})")
        return None, f"no Shopify product for {product}"
    qty = max(1, int(qty or 1))
    unit = 10.00 if qty >= 2 else 12.00          # 2-for special
    disc = round(12.00 - unit, 2)                # per-unit discount (Shopify applies per unit)
    area = (location_text or "").strip() or (_reverse_geocode(lat, lng) if (lat and lng) else None) or "Lebanon"
    note = f"AGENT-CLOSED SALE. {product} x{qty} at {unit:g}$ each + 4$ delivery."
    if lat and lng:
        note += f" Location: https://maps.google.com/?q={lat},{lng}"
    line = {"variant_id": variant_id, "quantity": qty}
    if disc > 0:
        line["applied_discount"] = {"description": "Agent 2-for price",
                                    "value_type": "fixed_amount",
                                    "value": f"{disc:.2f}", "amount": f"{disc:.2f}"}
    body = {"draft_order": {
        "line_items": [line],
        "shipping_address": {"first_name": digits, "last_name": "(WhatsApp)",
                             "address1": area, "city": area, "country": "Lebanon",
                             "phone": _norm_phone(phone)},
        "shipping_line": {"title": "Delivery", "price": "4.00"},
        "tags": "agent deal, WhatsApp, auto-entry",
        "note": note}}
    d = _shopify("POST", "/draft_orders.json", body)
    draft = d.get("draft_order")
    if not draft:
        return None, f"draft failed: {d.get('body', d)}"
    done = _shopify("PUT", f"/draft_orders/{draft['id']}/complete.json?payment_pending=true")
    oid = (done.get("draft_order") or {}).get("order_id")
    if not oid:
        _shopify("DELETE", f"/draft_orders/{draft['id']}.json")
        return None, f"complete failed: {done.get('body', done)}"
    order = _shopify("GET", f"/orders/{oid}.json?fields=name,total_price").get("order", {})
    return order, None


def _confirm_line(order, o):
    """✅ #1201 · Migraine Cap ×2 · $16.50 · Ghazir — Mary sees the item, the money
    and the delivery area, so a wrong product is obvious immediately."""
    qty = order.get("_qty") or 1
    item = order.get("_product") or "Item"
    if qty > 1:
        item += f" \u00d7{qty}"
    city = (o.get("city") or "").strip()
    bits = [f"\u2705 {order.get('name')}", item, f"${order.get('total_price')}"]
    if city:
        bits.append(city)
    return " \u00b7 ".join(bits)


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
                    lines.append(_confirm_line(order, o))
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


def handle_order_sheet(wa_id, media_id, filename, caption, send_text):
    """Mary sends a CSV/XLSX to the order number and every row becomes an order.

    Duplicate-safe: before entering anything the store's recent orders are indexed
    by phone number. A row whose number already has an order at the same total is
    SKIPPED (that is a re-sent or overlapping sheet). A row whose number exists at
    a different total is still entered but flagged in the reply, so a genuine
    second purchase goes through while a mistake is visible.

    Put "force" in the caption to enter every row regardless.
    """
    def work():
        try:
            if not (SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET):
                send_text(wa_id, "Order bot isn't configured yet (missing store credentials). Tell Kendall.")
                return
            send_text(wa_id, f"Got the sheet ({filename or 'file'}) — reading it now, one moment.")
            try:
                data, mime = _download_media(media_id)
            except Exception as e:
                _record_error("media", e)
                send_text(wa_id, "I couldn't download that file from WhatsApp. Try sending it again as a document.")
                return
            _keep_sheet(data, filename)
            try:
                orders, skipped, info = _orders_from_sheet(data, filename, mime)
                print(f"[fgc-orders] sheet read {filename!r}: {info}")
            except Exception as e:
                _record_error("sheet_parse", f"{e} | {filename}")
                send_text(wa_id, f"I couldn't read that sheet ({e}). It needs a phone column and a price column — "
                                 "CSV or Excel both work.")
                return
            if not orders:
                msg = ("I read the sheet but entered nothing, because no row had both a phone number and a "
                       "USD price. " + _columns_line(info))
                if skipped:
                    msg += "\n\nFirst rows I couldn't use:\n" + "\n".join("\u2022 " + r for r in skipped[:5])
                msg += "\n\nKendall can see this file, so he can get it fixed."
                _record_error("sheet_no_orders", f"{filename}: {info}")
                send_text(wa_id, msg[:3900])
                return

            force = "force" in (caption or "").lower()
            index = {} if force else _existing_orders_index()
            entered, dups, flagged, fails = [], [], [], []
            for o in orders:
                if not force:
                    hit, exact = _duplicate_of(o, index)
                    if hit and exact:
                        dups.append(f"{o.get('phone')} — already entered as {hit['name']} (${hit['total']:.2f})")
                        continue
                    if hit:
                        flagged.append(f"{o.get('phone')} — also has {hit['name']} (${hit['total']:.2f})")
                try:
                    order, err = _enter_order(o)
                except Exception as e:     # one bad row must not lose the rest of the sheet
                    _record_error("sheet_row", e)
                    order, err = None, "couldn't reach the store, send the sheet again (nothing gets doubled)"
                if order:
                    entered.append(_confirm_line(order, o))
                    ph = _norm_digits(o.get("phone"))
                    index.setdefault(ph, []).append({"name": order.get("name"),
                                                     "total": float(order.get("total_price") or 0),
                                                     "product": order.get("_product", ""), "created": ""})
                else:
                    fails.append(f"⚠️ {o.get('phone')} / {o.get('price')}$ — {err}")

            head = f"Sheet done — {len(entered)} entered"
            if dups:
                head += f", {len(dups)} skipped as already in the store"
            if fails:
                head += f", {len(fails)} failed"
            parts = [head + ".", _columns_line(info)]
            if entered:
                parts.append("\n".join(entered))
            if dups:
                parts.append("Already in the store (not entered again):\n" + "\n".join("• " + d for d in dups))
            if flagged:
                parts.append("Entered, but this number already had an order — check these:\n"
                             + "\n".join("• " + d for d in flagged))
            if fails:
                parts.append("\n".join(fails))
            if skipped:
                parts.append(f"{len(skipped)} row(s) I couldn't read:\n" + "\n".join("• " + r for r in skipped[:8]))
            if dups and not force:
                parts.append('If those really are new orders, send the sheet again with "force" in the caption.')
            send_text(wa_id, "\n\n".join(parts)[:3900])
        except Exception as e:
            _record_error("sheet", e)
            try:
                send_text(wa_id, "Something broke reading that sheet — Kendall's been notified.")
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ batch import
import re as _re


def import_leads_batch(leads, product="strips"):
    try:
        _shopify_token()
    except Exception as e:
        return [{"phone": "", "status": "error", "message": f"Cannot reach Shopify: {e}"}]

    index = _existing_orders_index()
    results = []
    for lead in leads:
        phone_raw = str(lead.get("phone") or "").strip()
        price = float(lead.get("price") or 0)
        city  = str(lead.get("city")  or "Lebanon").strip()
        notes = str(lead.get("notes") or "").strip()
        num   = lead.get("num", "?")
        m = _re.search(r"(\d+)\s*(?:box(?:es)?|pcs?|pieces?|units?)", notes, _re.IGNORECASE)
        qty = int(m.group(1)) if m else 1
        o = {"phone": phone_raw, "price": price, "city": city,
             "quantity": qty, "product": product, "name": "", "address": city}
        dup, exact = _duplicate_of(o, index)
        if exact:
            results.append({"phone": phone_raw, "status": "skipped",
                            "message": f"#{num} already in Shopify ({dup['name']} ${dup['total']:.2f})"})
            continue
        order, err = _enter_order(o)
        if err:
            results.append({"phone": phone_raw, "status": "error",
                            "message": f"#{num} {phone_raw} FAILED: {err}"})
            continue
        line = _confirm_line(order, o)
        status = "flagged" if dup else "imported"
        results.append({"phone": phone_raw, "status": status,
                        "message": line + (" warning: same number had another order" if dup else "")})
        ph = _norm_digits(phone_raw)
        index.setdefault(ph, []).append(
            {"name": order.get("name"), "total": price,
             "product": PRODUCT_NAMES.get(product, product), "created": ""})
    return results
