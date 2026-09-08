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
            "location_pin_is_commitment", "typical_objections", "languages", "context_notes")


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
    return {k: v for k, v in d.items() if not k.endswith("_env")}


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
qualified_lead_definition [str], sale_definition [str], committed_signals [list of str],
qualified_signals [list of str], lost_signals [list of str], disqualify_signals [list of str],
location_pin_is_commitment [bool], typical_objections [str], languages [list of str],
product_values [object name->number, the sale value Meta optimises on], currency [str, ISO code],
default_value [number], settle_minutes [number], context_notes [str, anything else worth remembering]."""


def _apply_from_model(cfg, text):
    """Ask the model to turn free text (intake answers, or an instruction) into config
    changes. Returns (new_cfg, changed_fields, reply)."""
    system = ("You maintain the configuration of a WhatsApp conversation observer for one business. "
              "The observer never replies to customers; it only decides when a conversation shows a qualified "
              "lead and when it shows a sale, then sends those to Meta as events. Prose fields are read by the "
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


@bp.post("/clients/<slug>/check")
def client_check(slug):
    """Prove the dataset accepts events from our token, without inventing a conversion:
    a deliberately invalid event returns a validation error when access is fine, and a
    permission error when it is not."""
    c = config.client_by_slug(slug)
    if not c:
        return jsonify({"error": "unknown"}), 404
    if not c.dataset_id:
        return jsonify({"ok": False, "detail": "No pixel / dataset ID set."})
    if not c.capi_token:
        return jsonify({"ok": False, "detail": "Meta token env var not set on this service."})
    url = f"https://graph.facebook.com/v21.0/{c.dataset_id}/events?access_token={c.capi_token}"
    body = {"data": [{"event_time": int(time.time()), "action_source": "business_messaging", "messaging_channel": "whatsapp",
                      "user_data": {"ctwa_clid": "probe"}}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return jsonify({"ok": True, "detail": "Accepted (unexpected): " + r.read().decode()[:200]})
    except urllib.error.HTTPError as e:
        txt = e.read().decode()[:400]
        ok = "event_name" in txt or "Invalid parameter" in txt or e.code == 400
        return jsonify({"ok": ok, "detail": ("Dataset reachable, token has write access. " if ok else "") + f"HTTP {e.code}: {txt}"})
    except Exception as e:
        return jsonify({"ok": False, "detail": repr(e)[:200]})


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
