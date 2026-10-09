"""FGC Syria: when the agent books an order ("تم الطلب"), push it everywhere MK needs it.

    1. read the order out of the chat (name, phone, city, area, product, quantity)
    2. check the product against what the thread actually proved (the verified ad or a
       product the customer clearly named) - a mismatch is never entered blind
    3. WhatsApp order card to MK, a Shopify order, a row in the running orders sheet,
       and an email copy

Every step is best effort and independent: a Shopify or sheet failure never stops the
WhatsApp card, and the card always says what did and did not go through.

Env (all optional except where noted):
  FGCSY_ORDER_WA            numbers that get the order card (default MK, 96179018107)
  FGCSY_ORDER_TEMPLATE      approved template used when the 24h window is closed
                            (default fgc_syria_new_order, language en)
  FGCSY_SHOPIFY_ORDERS      "0" turns Shopify entry off (default on)
  FGCSY_ORDERS_SHEET_ID     Google Sheet id for the running list (needed for the sheet)
  FGCSY_SHEETS_SA_JSON      base64 of the service-account JSON that can edit that sheet
"""
import os, json, time, base64, datetime, threading
import requests

ORDER_WA = [n.strip() for n in os.environ.get("FGCSY_ORDER_WA", "96179018107").split(",") if n.strip()]
ORDER_TEMPLATE = os.environ.get("FGCSY_ORDER_TEMPLATE", "fgc_syria_new_order")
SHOPIFY_ON = os.environ.get("FGCSY_SHOPIFY_ORDERS", "1") not in ("0", "false", "False", "")
SHEET_ID = os.environ.get("FGCSY_ORDERS_SHEET_ID", "")
SHEET_SA = os.environ.get("FGCSY_SHEETS_SA_JSON", "")
EXTRACT_MODEL = os.environ.get("FGCSY_ORDER_MODEL", "claude-opus-5-5")

PRODUCTS = ["Teeth Whitening Strips", "Nasal Strips", "Migraine Relief Cap",
            "Pimple Patches", "Whitening Toothpaste"]
# Shopify variants on the FGC store (checked live 09.10.2026), all 12$.
VARIANTS = {
    "Teeth Whitening Strips": 46831330885831,
    "Nasal Strips": 67793943593159,
    "Migraine Relief Cap": 46831330427079,
    "Pimple Patches": 46831330721991,
    "Whitening Toothpaste": 67815239024839,
}
SHEET_HEADER = ["Date (Damascus)", "Shopify order", "Name", "Phone", "City", "Area",
                "Products", "Qty", "Total $", "Delivery $", "WhatsApp", "Check", "Notes"]

_done = set()
_done_lock = threading.Lock()


def price_for(qty):
    """MK's Syria prices (training 08.10): (goods_total, delivery)."""
    if qty <= 1:
        return 12.0, 4.0
    if qty == 2:
        return 24.0, 0.0
    if qty == 3:
        return 30.0, 0.0
    return 10.0 * qty, 0.0


def syria_phone(raw, fallback_wa):
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("963"):
        return "+" + d
    if d.startswith("09") and len(d) == 10:
        return "+963" + d[1:]
    if d.startswith("9") and len(d) == 9:
        return "+963" + d
    if len(d) >= 10:
        return "+" + d
    return "+" + "".join(ch for ch in str(fallback_wa) if ch.isdigit())


# ── 1. read the order out of the chat ────────────────────────────────────────
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Customer name as they wrote it"},
        "phone": {"type": "string", "description": "Phone number the customer gave, as written; empty if none"},
        "city": {"type": "string"},
        "area": {"type": "string"},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"product": {"type": "string", "enum": PRODUCTS + ["UNKNOWN"]},
                           "quantity": {"type": "integer"}},
            "required": ["product", "quantity"], "additionalProperties": False}},
        "notes": {"type": "string", "description": "Anything MK must know (delivery time asked for, etc). Empty if nothing."},
    },
    "required": ["name", "phone", "city", "area", "items", "notes"],
    "additionalProperties": False,
}


def _extract(transcript, known_product):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    prompt = (
        "This is a WhatsApp chat between a customer in Syria and the Feels Good Club shop. "
        "The shop just confirmed an order. Read the order out of the chat.\n"
        f"The product this chat is about, verified from the ad they clicked: {known_product or 'UNKNOWN'}.\n"
        "Rules: use ONLY what the customer actually wrote. Quantity is 1 unless the customer "
        "clearly asked for more. List a product other than the verified one ONLY if the customer "
        "clearly named it. If you cannot tell the product, use UNKNOWN. Keep names, cities and "
        "areas exactly as written (Arabic stays Arabic).\n\nCHAT:\n" + transcript)
    resp = client.messages.create(
        model=EXTRACT_MODEL, max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"output_config": {"effort": "low",
                                      "format": {"type": "json_schema", "schema": SCHEMA}}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("extraction refused")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text)


# ── 2. WhatsApp card to MK ───────────────────────────────────────────────────
def _card(o, shopify_line, check):
    lines = ["New Syria order"]
    if check:
        lines.append(f"CHECK THIS ONE: {check}")
    lines += [f"Name: {o['name'] or '-'}",
              f"Phone: {o['phone_fmt']}",
              f"City / area: {o['city'] or '-'}, {o['area'] or '-'}",
              f"Product: {o['products_txt']}",
              f"Total: ${o['total']:g} ({o['price_txt']}), cash on delivery"]
    if o.get("notes"):
        lines.append(f"Notes: {o['notes']}")
    lines += [shopify_line, f"Chat: https://wa.me/{o['wa_id']}"]
    return "\n".join(lines)


def _send_card(A, body, o):
    sent = []
    for to in ORDER_WA:
        r = requests.post(
            f"{A.GRAPH_BASE}/{A.LUMEN_NOTIFY_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {A.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:3900]}},
            timeout=15)
        if r.status_code < 300:
            sent.append(to)
            continue
        # Outside the 24h window a free-form message is refused; the approved template is not.
        params = [o["name"] or "-", o["phone_fmt"], f"{o['city'] or '-'}, {o['area'] or '-'}",
                  o["products_txt"], f"${o['total']:g} ({o['price_txt']})"]
        t = requests.post(
            f"{A.GRAPH_BASE}/{A.LUMEN_NOTIFY_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {A.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to, "type": "template",
                  "template": {"name": ORDER_TEMPLATE, "language": {"code": "en"},
                               "components": [{"type": "body", "parameters": [
                                   {"type": "text", "text": p[:200]} for p in params]}]}},
            timeout=15)
        if t.status_code < 300:
            sent.append(to + " (template)")
        else:
            print(f"[fgcsy-order] card to {to} failed: text {r.status_code} {r.text[:150]} / "
                  f"template {t.status_code} {t.text[:150]}")
    return sent


# ── 3. Shopify ───────────────────────────────────────────────────────────────
def _shopify_order(o):
    from agents.order_entry import fgc_orders as S
    qty = o["qty"]
    goods, delivery = o["goods"], o["delivery"]
    lines = [{"variant_id": VARIANTS[p], "quantity": q} for p, q in o["items"]]
    list_total = 12.0 * qty
    discount = round(list_total - goods, 2)
    first, _, last = (o["name"] or "WhatsApp").partition(" ")
    addr = {"first_name": first or "WhatsApp", "last_name": last or "(Syria)",
            "address1": f"{o['area']}".strip() or o["city"] or "Syria",
            "address2": "Syria", "city": o["city"] or "Syria", "phone": o["phone_fmt"]}
    # Shopify rejects Syria as a shipping country ("isn't supported", checked 09.10.2026),
    # so the address goes in without one; "Syria" sits in address2 and the note.
    draft = {"line_items": lines,
             "shipping_address": addr,
             "shipping_line": {"title": "Delivery", "price": f"{delivery:.2f}"},
             "tags": "Syria, agent deal, WhatsApp, auto-entry",
             "note": (f"SYRIA AGENT ORDER. {o['products_txt']}. Total {o['total']:g}$ "
                      f"({o['price_txt']}), cash on delivery. Customer WhatsApp +{o['wa_id']}. "
                      f"City: {o['city']}. Area: {o['area']}." + (f" Notes: {o['notes']}" if o.get("notes") else ""))}
    if discount > 0:
        draft["applied_discount"] = {"description": "Syria multi-buy", "value_type": "fixed_amount",
                                     "value": f"{discount:.2f}", "amount": f"{discount:.2f}"}
    d = S._shopify("POST", "/draft_orders.json", {"draft_order": draft})
    dr = d.get("draft_order")
    if not dr:
        return None, f"draft failed: {str(d.get('body', d))[:200]}"
    if abs(float(dr.get("total_price") or 0) - o["total"]) > 0.01:
        S._shopify("DELETE", f"/draft_orders/{dr['id']}.json")
        return None, f"store total {dr.get('total_price')} != {o['total']:g}, not entered"
    done = S._shopify("PUT", f"/draft_orders/{dr['id']}/complete.json?payment_pending=true")
    oid = (done.get("draft_order") or {}).get("order_id")
    if not oid:
        S._shopify("DELETE", f"/draft_orders/{dr['id']}.json")
        return None, f"complete failed: {str(done)[:200]}"
    order = S._shopify("GET", f"/orders/{oid}.json?fields=name,total_price").get("order", {})
    return order, None


# ── 4. the running sheet ─────────────────────────────────────────────────────
def _sheet_append(row):
    if not (SHEET_ID and SHEET_SA):
        return "sheet not set up yet"
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = json.loads(base64.b64decode(SHEET_SA).decode())
    cr = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=cr, cache_discovery=False).spreadsheets().values()
    head = svc.get(spreadsheetId=SHEET_ID, range="A1:M1").execute().get("values")
    if not head:
        svc.update(spreadsheetId=SHEET_ID, range="A1", valueInputOption="RAW",
                   body={"values": [SHEET_HEADER]}).execute()
    svc.append(spreadsheetId=SHEET_ID, range="A:M", valueInputOption="USER_ENTERED",
               insertDataOption="INSERT_ROWS", body={"values": [row]}).execute()
    return None


# ── the whole thing ──────────────────────────────────────────────────────────
def capture(wa_id):
    """Run once per booked order. Safe to call from any thread; never raises."""
    from . import agent as A
    with _done_lock:
        key = (wa_id, int(time.time() // 600))  # one capture per thread per 10 minutes
        if key in _done:
            return
        _done.add(key)
    try:
        contact = A.get_contact(wa_id) or {}
        hist = A._history(wa_id)
        transcript = "\n".join(
            f"{'CUSTOMER' if h['direction'] == 'in' else 'SHOP'}: {h['body']}"
            for h in hist if (h.get("body") or "").strip())
        known = contact.get("product")
        named = {p for h in hist if h["direction"] == "in"
                 for p in [A._product_from_text(h["body"] or "")] if p}
        allowed = ({known} if known else set()) | named

        x = _extract(transcript, known)
        items, check = [], ""
        for it in x.get("items") or []:
            p, q = it.get("product"), max(1, int(it.get("quantity") or 1))
            if p not in VARIANTS or p not in allowed:
                check = (f"product not certain (chat read as {p}, verified: "
                         f"{', '.join(sorted(allowed)) or 'none'})")
            items.append((p, q))
        if not items:
            items, check = [(known or "UNKNOWN", 1)], (check or "no product read from the chat")
        qty = sum(q for _, q in items)
        goods, delivery = price_for(qty)
        o = {"wa_id": wa_id, "name": (x.get("name") or contact.get("profile_name") or "").strip(),
             "phone_fmt": syria_phone(x.get("phone"), wa_id),
             "city": (x.get("city") or "").strip(), "area": (x.get("area") or "").strip(),
             "notes": (x.get("notes") or "").strip(), "items": items, "qty": qty,
             "goods": goods, "delivery": delivery, "total": goods + delivery,
             "products_txt": ", ".join(f"{p} x {q}" for p, q in items),
             "price_txt": f"{goods:g} + {delivery:g} delivery" if delivery else f"{goods:g}, free delivery"}

        shop_line, order_name = "Shopify: not entered", ""
        if check:
            shop_line = "Shopify: NOT entered, check the product first"
        elif SHOPIFY_ON:
            try:
                order, err = _shopify_order(o)
                if order:
                    order_name = order.get("name", "")
                    shop_line = f"Shopify: {order_name} entered"
                else:
                    shop_line = f"Shopify: NOT entered ({err})"
            except Exception as e:
                shop_line = f"Shopify: NOT entered ({e})"

        sheet_err = None
        try:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
            sheet_err = _sheet_append([now.strftime("%Y-%m-%d %H:%M"), order_name, o["name"], o["phone_fmt"],
                                       o["city"], o["area"], o["products_txt"], qty, o["total"], delivery,
                                       f"+{wa_id}", check, o["notes"]])
        except Exception as e:
            sheet_err = str(e)[:150]

        body = _card(o, shop_line + (f"\nSheet: {sheet_err}" if sheet_err else ""), check)
        sent = _send_card(A, body, o)
        A._notify_team(f"FGC Syria order: {o['name'] or wa_id} - {o['products_txt']}",
                       "<pre style='font-family:inherit;white-space:pre-wrap'>" + body.replace("<", "&lt;")
                       + f"\n\nWhatsApp card sent to: {', '.join(sent) or 'NOBODY (check)'}</pre>")
        print(f"[fgcsy-order] {wa_id}: {o['products_txt']} {o['total']:g}$ | {shop_line} | "
              f"sheet {'ok' if not sheet_err else sheet_err} | card {sent}")
    except Exception as e:
        print(f"[fgcsy-order] capture failed for {wa_id}: {e!r}")
        try:
            A._notify_team("FGC Syria order: capture FAILED, enter it by hand",
                           f"<p>Customer +{wa_id}. Error: {e!r}</p><p>https://wa.me/{wa_id}</p>")
        except Exception:
            pass
