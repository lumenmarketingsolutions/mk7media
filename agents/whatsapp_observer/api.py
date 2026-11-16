"""JSON API the lumen.ai admin uses to manage observer clients. Shared-secret auth
(X-Stats-Key), same as the stats feed. This service holds the Meta token and the
Anthropic key, so the model calls that turn a client's answers into config live here."""
import json, os, re, time, hmac, urllib.request, urllib.error
from flask import Blueprint, request, jsonify
from . import config, observer, store

bp = Blueprint("observer_api", __name__, url_prefix="/api/observer")

EDITABLE = ("business_name", "phone_number_id", "waba_id", "dataset_id", "currency", "default_value",
            "product_values", "settle_minutes", "dry_run", "business_description", "what_is_sold",
            "how_customers_pay", "how_fulfilment_works", "qualified_lead_definition", "sale_definition",
            "committed_signals", "qualified_signals", "lost_signals", "disqualify_signals",
            "location_pin_is_commitment", "typical_objections", "languages", "context_notes", "win_type",
            "lead_event")


def _authed():
    want = os.environ.get("WA_STATS_KEY", ""); got = request.headers.get("X-Stats-Key") or ""
    return bool(want) and hmac.compare_digest(str(want), str(got))


@bp.before_request
def _gate():
    if not _authed():
        return jsonify({"error": "not found"}), 404


def _slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or f"client-{int(time.time())}"


def _public(d):
    """Config as the admin sees it. Secrets never leave this service: the pasted token
    is reported only as set or not, with its last four characters."""
    out = {k: v for k, v in d.items() if not k.endswith("_env") and k != "capi_token"}
    t = (d.get("capi_token") or "").strip()
    out["capi_token_set"] = bool(t)
    out["capi_token_hint"] = ("..." + t[-4:]) if t else ""
    return out


def _claude(system, user, max_tokens=1500):
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    model = os.environ.get("OBSERVER_MODEL") or os.environ.get("WHATSAPP_AGENT_MODEL", "claude-opus-4-7")
    r = anthropic.Anthropic(api_key=key).messages.create(model=model, max_tokens=max_tokens, system=system,
                                                          messages=[{"role": "user", "content": user}])
    return "".join(getattr(b, "text", "") for b in r.content).strip()


FIELDS_DOC = """Config fields you may set (JSON types in brackets):
business_description [str], what_is_sold [str], how_customers_pay [str], how_fulfilment_works [str],
qualified_lead_definition [str], sale_definition [str: the WIN, whatever the owner counts as success: an order, a booked call, an appointment, a signup, a deposit],
win_type [list of str, e.g. "A booked call"], committed_signals [list of str],
qualified_signals [list of str], lost_signals [list of str], disqualify_signals [list of str],
location_pin_is_commitment [bool], typical_objections [str], languages [list of str],
product_values [object name->number, the sale value Meta optimises on], currency [str, ISO code],
default_value [number], settle_minutes [number], context_notes [str, anything else worth remembering]."""


def _apply_from_model(cfg, text):
    """Ask the model to turn free text (intake answers, or an instruction) into config
    changes. Returns (new_cfg, changed_fields, reply)."""
    system = ("You maintain the configuration of a WhatsApp conversation observer for one business. "
              "The observer never replies to customers; it only decides when a conversation shows a qualified "
              "lead and when it shows a win (a sale, a booked call, an appointment, a signup, a deposit, whatever the owner counts), then sends those to Meta as events. Prose fields are read by the "
              "classifier verbatim, so keep the owner's own words and specifics.\n" + FIELDS_DOC +
              "\nReply with ONE JSON object: {\"changes\": {field: value, ...}, \"reply\": \"<one to three plain sentences "
              "telling the operator what you changed or what is still missing>\"}. Only include fields that should change. "
              "Merge new signals into existing lists rather than replacing them unless told to replace.")
    user = "CURRENT CONFIG:\n" + json.dumps(_public(cfg), ensure_ascii=False, indent=1) + "\n\nOPERATOR INPUT:\n" + text
    out = _claude(system, user)
    j = json.loads(out[out.index("{"): out.rindex("}") + 1])
    changes = j.get("changes") or {}
    new = dict(cfg); changed = []
    for k, v in changes.items():
        if k in EDITABLE:
            if k in ("committed_signals", "qualified_signals", "lost_signals", "disqualify_signals", "languages") \
                    and isinstance(v, list) and isinstance(cfg.get(k), list):
                v = list(dict.fromkeys([*cfg[k], *v]))
            new[k] = v; changed.append(k)
    return new, changed, j.get("reply") or "Updated."


@bp.get("/clients")
def list_clients():
    out = []
    for d in config.list_configs():
        try:
            c = config.Client(d); store.init(c); rep = observer.report(c, limit=0)
            ev = store.conn(c); n = {r["status"]: r["n"] for r in ev.execute(
                "SELECT status, COUNT(*) n FROM events GROUP BY status")}
            convos = ev.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]; ev.close()
        except Exception as e:
            rep, n, convos = {"states": {}}, {}, 0
        out.append({"slug": d["slug"], "business_name": d.get("business_name"), "dataset_id": d.get("dataset_id"),
                    "phone_number_id": d.get("phone_number_id"), "dry_run": d.get("dry_run", True),
                    "created": d.get("_created"), "conversations": convos,
                    "sales": rep["states"].get("COMMITTED", 0), "events": n})
    return jsonify({"clients": out})


@bp.post("/clients")
def create_client():
    d = request.json or {}
    name = (d.get("business_name") or "").strip()
    if not name:
        return jsonify({"error": "business_name required"}), 400
    slug = _slugify(d.get("slug") or name)
    if config.get_config(slug):
        return jsonify({"error": "slug exists", "slug": slug}), 409
    cfg = {**config.DEFAULTS, "slug": slug, "business_name": name,
           "phone_number_id": str(d.get("phone_number_id") or ""), "waba_id": str(d.get("waba_id") or ""),
           "dataset_id": str(d.get("dataset_id") or ""), "capi_token_env": "LUMEN_META_CAPI_TOKEN",
           "ads_token_env": "LUMEN_META_CAPI_TOKEN", "app_secret_env": "WHATSAPP_APP_SECRET",
           "languages": ["English", "Arabic", "Arabic in Latin letters"], "dry_run": True}
    if str(d.get("capi_token") or "").strip():
        cfg["capi_token"] = str(d["capi_token"]).strip()
    reply, changed = "", []
    if (d.get("context") or "").strip():
        try:
            cfg, changed, reply = _apply_from_model(cfg, d["context"])
        except Exception as e:
            reply = f"Saved, but the context could not be parsed: {repr(e)[:120]}"
    config.save_config(cfg)
    config.chat_append(slug, "user", d.get("context") or "(created without context)")
    config.chat_append(slug, "assistant", reply or "Client created.", changed)
    return jsonify({"slug": slug, "config": _public(cfg), "changed": changed, "reply": reply})


@bp.get("/clients/<slug>")
def get_client(slug):
    cfg = config.get_config(slug)
    if not cfg:
        return jsonify({"error": "unknown"}), 404
    return jsonify({"config": _public(cfg), "chat": config.chat_log(slug)})


@bp.put("/clients/<slug>")
def update_client(slug):
    cfg = config.get_config(slug)
    if not cfg:
        return jsonify({"error": "unknown"}), 404
    d = request.json or {}; changed = []
    # The token is write-only: blank keeps the saved one, "clear" removes it.
    tok = str(d.get("capi_token") or "").strip()
    if tok:
        if tok.lower() == "clear":
            cfg.pop("capi_token", None)
        else:
            cfg["capi_token"] = tok
        changed.append("capi_token")
    for k in ("waba_id", "phone_number_id", "dataset_id"):
        if k in d and d[k] is not None:
            d[k] = "".join(ch for ch in str(d[k]) if ch.isdigit())
    for k in EDITABLE:
        if k in d:
            v = d[k]
            if k == "dry_run": v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "on", "yes")
            if k in ("default_value", "settle_minutes"):
                try: v = float(v)
                except Exception: continue
            if k == "product_values" and isinstance(v, str):
                pv = {}
                for pair in v.split(","):
                    if ":" in pair:
                        n, val = pair.rsplit(":", 1)
                        try: pv[n.strip()] = float(val)
                        except Exception: pass
                v = pv
            cfg[k] = v; changed.append(k)
    config.save_config(cfg)
    return jsonify({"config": _public(cfg), "changed": changed})


@bp.get("/clients/<slug>/report")
def client_report(slug):
    c = config.client_by_slug(slug)
    if not c:
        return jsonify({"error": "unknown"}), 404
    store.init(c); rep = observer.report(c, limit=int(request.args.get("limit", 100)))
    db = store.conn(c)
    rep["recent"] = [dict(r) for r in db.execute(
        "SELECT wa_id, state, state_evidence, state_at, product FROM contacts WHERE state IS NOT NULL "
        "ORDER BY state_at DESC LIMIT 40")]
    rep["totals"] = {"contacts": db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
                     "with_click": db.execute("SELECT COUNT(*) FROM contacts WHERE ctwa_clid IS NOT NULL").fetchone()[0],
                     "messages": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                     "last_inbound": (db.execute("SELECT MAX(last_inbound_at) FROM contacts").fetchone()[0])}
    rep["event_status"] = {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM events GROUP BY status")}
    db.close()
    return jsonify(rep)


# ---- Meta plumbing: find the client's number, subscribe it, give it a dataset, prove it.
# Two tokens on purpose. The webhook token belongs to the app Meta delivers messages to
# (subscribing with any other app's token subscribes the wrong app, and nothing arrives).
# The business token is the Lumen system user that can see every WABA shared with us.
LUMEN_BUSINESS_ID = os.environ.get("LUMEN_BUSINESS_ID", "1531559090655146")
WEBHOOK_APP_ID = os.environ.get("WHATSAPP_APP_ID", "2107067100091646")


def _webhook_token():
    return os.environ.get("WHATSAPP_ACCESS_TOKEN", "")


def _business_token():
    return os.environ.get("LUMEN_META_CAPI_TOKEN") or os.environ.get("FGC_CAPI_TOKEN") or _webhook_token()


def _graph(method, path, token, params=None, body=None, timeout=20):
    """Returns (json, error_text). Never raises."""
    from urllib.parse import urlencode
    params = dict(params or {}); params["access_token"] = token
    url = f"https://graph.facebook.com/v21.0/{path}"
    data, headers = None, {}
    if method == "GET":
        url += "?" + urlencode(params)
    elif body is not None:
        url += "?" + urlencode(params); data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    else:
        data = urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method),
                                    timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}"), None
    except urllib.error.HTTPError as e:
        txt = e.read().decode()[:600]
        try: j = json.loads(txt)
        except Exception: j = {}
        err = (j.get("error") or {})
        return j, err.get("error_user_msg") or err.get("message") or f"HTTP {e.code}"
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


PHONE_FIELDS = "id,display_phone_number,verified_name,platform_type,status,is_on_biz_app,code_verification_status"


def _digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _find_number(waba_id="", phone_number_id="", phone=""):
    """Locate the client's number among the WABAs shared with Lumen. Accepts any of:
    the WABA ID, the phone number ID, or just the WhatsApp number the customer types
    (people paste the number into the ID box; that is fine here)."""
    tok = _business_token(); waba_id, phone_number_id, phone = _digits(waba_id), _digits(phone_number_id), _digits(phone)
    # An "ID" of 8 to 13 digits is a phone number typed into the wrong box.
    if phone_number_id and len(phone_number_id) < 14 and not phone:
        phone, phone_number_id = phone_number_id, ""
    wabas = [waba_id] if waba_id else []
    if not wabas:
        for edge in ("client_whatsapp_business_accounts", "owned_whatsapp_business_accounts"):
            j, _ = _graph("GET", f"{LUMEN_BUSINESS_ID}/{edge}", tok, {"fields": "id,name", "limit": 200})
            wabas += [w["id"] for w in j.get("data", [])]
    for w in wabas:
        j, _ = _graph("GET", f"{w}/phone_numbers", tok, {"fields": PHONE_FIELDS})
        for p in j.get("data", []):
            disp = _digits(p.get("display_phone_number"))
            if (phone_number_id and p["id"] == phone_number_id) or \
               (phone and len(phone) >= 7 and (disp.endswith(phone[-8:]) or phone.endswith(disp[-8:]))) or \
               (waba_id and not phone_number_id and not phone):
                return w, p
    return (waba_id or None), None


def _dataset_probe(c):
    """Prove the token can write to the dataset without inventing a conversion: an event
    with no event_name is rejected for exactly that reason when access is fine. Any other
    error (missing object, missing permission) means events would not land."""
    body = {"data": [{"event_time": int(time.time()), "action_source": "business_messaging",
                      "messaging_channel": "whatsapp",
                      "user_data": {"ctwa_clid": "probe", **({"whatsapp_business_account_id": c.waba_id} if c.waba_id else {})}}]}
    j, err = _graph("POST", f"{c.dataset_id}/events", c.capi_token, body=body, timeout=15)
    if err and "event_name" in err:
        return True, "Dataset found and the token can send events to it."
    if not err:
        return True, "Accepted."
    return False, err[:220]


def _diagnose(c):
    checks = []

    def add(key, ok, detail, fix=""):
        checks.append({"key": key, "ok": ok, "detail": detail, "fix": fix})

    num = None
    if c.waba_id or c.phone_number_id:
        _, num = _find_number(c.waba_id, c.phone_number_id)
    if not num:
        add("number", False, "We can't see their WhatsApp number yet.",
            "Send them the connect link. When they finish, press Connect and pick up their number.")
    else:
        live = num.get("status") == "CONNECTED"
        add("number", live, f"{num.get('display_phone_number')} ({num.get('verified_name') or 'no name'}): "
            f"{num.get('status')}, {'WhatsApp Business app linked' if num.get('is_on_biz_app') else 'not linked to the Business app'}",
            "" if live else "Meta's connection was not finished. They open the connect link again and scan the QR "
                            "code with the WhatsApp Business app on the phone that has this number.")
    if c.waba_id:
        j, err = _graph("GET", f"{c.waba_id}/subscribed_apps", _webhook_token())
        subbed = any((a.get("whatsapp_business_api_data") or {}).get("id") == WEBHOOK_APP_ID for a in j.get("data", []))
        add("webhook", subbed, "Their messages are sent to us." if subbed else f"Messages are not being sent to us. {err or ''}".strip(),
            "" if subbed else "Press Connect to subscribe the number.")
    else:
        add("webhook", False, "No WhatsApp Business account ID yet.", "Press Connect.")
    if not c.dataset_id:
        add("dataset", False, "No dataset ID.", "Paste their dataset ID, or press Connect to create one on their WhatsApp account.")
    elif not c.capi_token:
        add("dataset", False, "No Meta token.", "Paste a token with access to this dataset.")
    else:
        ok, detail = _dataset_probe(c)
        add("dataset", ok, detail, "" if ok else "Check the dataset ID, and that the token's system user is assigned to the dataset in Business Settings.")
        if c.waba_id:
            j, _ = _graph("GET", f"{c.waba_id}/dataset", _business_token())
            linked = [d.get("id") for d in j.get("data", [])]
            if linked and c.dataset_id not in linked:
                add("dataset_link", False, f"This dataset is not the one linked to their WhatsApp account ({', '.join(linked)}).",
                    "Either use the linked one, or connect their WhatsApp account to this dataset in Events Manager.")
    store.init(c); db = store.conn(c)
    msgs = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    last = db.execute("SELECT MAX(created_at) FROM messages").fetchone()[0]
    clicks = db.execute("SELECT COUNT(*) FROM contacts WHERE ctwa_clid IS NOT NULL").fetchone()[0]
    db.close()
    add("traffic", msgs > 0, f"{msgs} messages seen, last at {last} UTC; {clicks} chats came from an ad click." if msgs
        else "No messages have reached us yet.",
        "" if msgs else "Ask them to send one WhatsApp message to the number from another phone.")
    add("sending", not c.dry_run, "Live: events go to Meta." if not c.dry_run else "Dry run: decisions are logged, nothing is sent to Meta.",
        "" if not c.dry_run else "Untick dry run once the first decisions look right.")
    return checks


@bp.post("/clients/<slug>/check")
def client_check(slug):
    c = config.client_by_slug(slug)
    if not c:
        return jsonify({"error": "unknown"}), 404
    checks = _diagnose(c)
    core = [x for x in checks if x["key"] in ("number", "webhook", "dataset", "dataset_link")]
    ok = all(x["ok"] for x in core)
    detail = " · ".join(("OK " if x["ok"] else "FIX ") + x["key"] + ": " + x["detail"] for x in checks)
    return jsonify({"ok": ok, "checks": checks, "detail": detail})


@bp.post("/clients/<slug>/provision")
def client_provision(slug):
    """Find the client's number, subscribe our webhook app to it, and give it a dataset.
    Every step is idempotent, so this is the button to press whenever anything looks off."""
    cfg = config.get_config(slug)
    if not cfg:
        return jsonify({"error": "unknown"}), 404
    d = request.json or {}
    waba, num = _find_number(d.get("waba_id") or cfg.get("waba_id"), d.get("phone_number_id") or cfg.get("phone_number_id"),
                             d.get("phone") or cfg.get("phone"))
    steps = []
    if not num:
        return jsonify({"ok": False, "steps": [{"key": "number", "ok": False,
                        "detail": "No number matching that is shared with Lumen yet. They need to finish the connect link."}]})
    if d.get("phone"):
        cfg["phone"] = _digits(d["phone"])
    owner = config.by_phone_id(num["id"])
    if owner and owner.slug != slug:
        return jsonify({"ok": False, "steps": [{"key": "number", "ok": False,
                        "detail": f"That number already belongs to client {owner.slug}."}]})
    cfg["waba_id"], cfg["phone_number_id"] = waba, num["id"]
    steps.append({"key": "number", "ok": True, "detail": f"Found {num.get('display_phone_number')} ({num.get('status')})."})
    j, err = _graph("POST", f"{waba}/subscribed_apps", _webhook_token())
    steps.append({"key": "webhook", "ok": bool(j.get("success")), "detail": "Subscribed." if j.get("success") else (err or str(j))[:200]})
    if not cfg.get("dataset_id"):
        j, err = _graph("POST", f"{waba}/dataset", _business_token())
        if j.get("id"):
            cfg["dataset_id"] = j["id"]
        steps.append({"key": "dataset", "ok": bool(j.get("id")),
                      "detail": f"Dataset {j['id']} created on their WhatsApp account." if j.get("id") else (err or str(j))[:200]})
    config.save_config(cfg)
    return jsonify({"ok": all(s["ok"] for s in steps), "steps": steps, "config": _public(cfg)})


@bp.post("/clients/<slug>/chat")
def client_chat(slug):
    cfg = config.get_config(slug)
    if not cfg:
        return jsonify({"error": "unknown"}), 404
    text = ((request.json or {}).get("message") or "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    config.chat_append(slug, "user", text)
    try:
        new, changed, reply = _apply_from_model(cfg, text)
        config.save_config(new)
    except Exception as e:
        reply, changed, new = f"I couldn't apply that: {repr(e)[:160]}", [], cfg
    config.chat_append(slug, "assistant", reply, changed)
    return jsonify({"reply": reply, "changed": changed, "config": _public(new)})
