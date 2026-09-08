"""Model-first conversation state classifier, with the client's own conversion
contract as the instructions and a small set of hard rules as guardrails.

States (one per conversation, see lumen-ai/product/TAXONOMY.md):
  NEW · ENQUIRY · QUALIFIED · INTENT · COMMITTED · LOST · DISQUALIFIED · NEEDS_HUMAN

Why model-first: the rules that worked for one shop knew that shop's towns, slang and
products. A different business needs different evidence, and the client can describe
that evidence in plain words far more reliably than anyone can write regexes for it.
The hard rules below are the handful that are true for every business.

The output is conservative on purpose. A wrong Purchase teaches Meta to find the
wrong people and inflates the client's numbers; abstaining costs one event.
"""
import json, os, re

PREFILL = re.compile(r"can i get more info on this|مزيد من المعلومات حول هذا|puis-je en savoir plus|"
                     r"more information about this", re.I)
LOCATION_PIN = re.compile(r"\[location", re.I)
MEDIA = re.compile(r"^\s*\[(audio|image|video|document|sticker)\b", re.I)
RUNG = {"NEW": 0, "ENQUIRY": 1, "QUALIFIED": 2, "INTENT": 3, "COMMITTED": 4}
TERMINAL = ("LOST", "DISQUALIFIED", "NEEDS_HUMAN")

PROMPT = """You are an analyst reading a WhatsApp thread between a business and one customer.
Your only job is to decide the conversation's current STATE and quote the exact
customer text that proves it. You never reply to anyone.

THE BUSINESS (in the owner's own words)
{contract}

STATES, pick exactly one for the whole thread as it stands now:
NEW          the customer has said nothing meaningful (only the ad's prefill text, a greeting, media).
ENQUIRY      the customer asked something real about price, product, availability, terms, location.
QUALIFIED    the customer has given the specifics the owner listed under "qualified lead": {qualified}
INTENT       the customer clearly said they want it or will proceed, but has NOT yet done the sale action.
COMMITTED    the customer did the exact thing the owner listed under "sale": {sale}
             Only this state counts as a sale. When unsure between INTENT and COMMITTED, choose INTENT.
LOST         the customer said no, not now, cancel, too expensive and left, or walked away after committing.
DISQUALIFIED never a customer: wholesale, job seeker, spam, asking for someone else, just looking.
NEEDS_HUMAN  a complaint, an existing-order problem, or a request no observer can judge.

RULES
- Walk the thread in order. A later "no" undoes an earlier commitment. A later commitment undoes an earlier "no".
- The ad prefill message carries zero intent.
- "ok", "yes", a thumbs up, "I'll take it" on their own are INTENT at most, never COMMITTED.
- Only customer messages carry evidence. The business's own messages give context only.
- Customers may write in any of: {languages}. Latin-letter Arabic ("badde wehde") is normal.
- If you name a product, use only names from this list when one fits: {products}

Answer with ONE line of JSON and nothing else:
{{"state": "...", "evidence": "<exact customer quote, max 160 chars>", "product": "<name or null>", "quantity": <int or null>}}

THREAD
"""


def _contract_text(client):
    c = client.contract()
    lines = []
    for k in ("business_description", "what_is_sold", "how_customers_pay", "how_fulfilment_works",
              "qualified_lead_definition", "sale_definition", "typical_objections"):
        if c.get(k):
            lines.append(f"{k.replace('_', ' ')}: {c[k]}")
    for k in ("committed_signals", "qualified_signals", "lost_signals", "disqualify_signals"):
        if c.get(k):
            lines.append(f"{k.replace('_', ' ')}: " + " | ".join(c[k]))
    if c.get("location_pin_is_commitment"):
        lines.append("a shared location pin from the customer IS the sale action")
    return "\n".join(lines) or "(no description given)"


def _hard_rules(client, msgs):
    """Rules true for every business. Return a (state, evidence) or None to defer."""
    inbound = [m for m in msgs if m["direction"] == "in"]
    real = [m for m in inbound if not PREFILL.search(m.get("body") or "") and not MEDIA.match(m.get("body") or "")]
    if not real:
        return ("NEW", (inbound[-1]["body"] if inbound else "")[:160]) if not inbound or all(
            not MEDIA.match(m.get("body") or "") for m in inbound) else ("NEEDS_HUMAN", "media only")
    if client.raw.get("location_pin_is_commitment"):
        pins = [m for m in real if m.get("msg_type") == "location" or LOCATION_PIN.search(m.get("body") or "")]
        if pins and pins[-1] is real[-1]:
            return ("COMMITTED", "[location pin]")
    return None


def _model(client, msgs):
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    try:
        import anthropic
        c = client.contract()
        prompt = PROMPT.format(
            contract=_contract_text(client),
            qualified=c.get("qualified_lead_definition") or "(not specified: use judgement, be strict)",
            sale=c.get("sale_definition") or "(not specified: the customer gives what they need for delivery or booking)",
            languages=", ".join(c.get("languages") or ["English"]),
            products=", ".join((c.get("product_values") or {}).keys()) or "(none listed)")
        lines = []
        for m in msgs[-60:]:
            who = "CUSTOMER" if m["direction"] == "in" else "BUSINESS"
            lines.append(f"{who}: {(m.get('body') or '').strip() or '[' + str(m.get('msg_type')) + ']'}")
        resp = anthropic.Anthropic(api_key=key).messages.create(
            model=client.model, max_tokens=200,
            messages=[{"role": "user", "content": prompt + "\n".join(lines)}])
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        j = json.loads(text[text.index("{"): text.rindex("}") + 1])
        st = str(j.get("state", "")).upper()
        if st not in RUNG and st not in TERMINAL:
            return None
        return {"state": st, "evidence": (j.get("evidence") or "")[:160],
                "product": j.get("product"), "quantity": j.get("quantity")}
    except Exception as e:
        print(f"[observer:{client.slug}] classifier error: {repr(e)[:120]}")
        return None


def classify(client, msgs):
    """Return {"state", "evidence", "product", "quantity", "source"}. Fails to NEW
    (abstain) rather than guessing when the model is unavailable."""
    hr = _hard_rules(client, msgs)
    if hr and hr[0] in ("NEW", "NEEDS_HUMAN"):
        return {"state": hr[0], "evidence": hr[1], "product": None, "quantity": None, "source": "rule"}
    m = _model(client, msgs)
    if m:
        if hr and hr[0] == "COMMITTED" and m["state"] not in TERMINAL:
            m["state"] = "COMMITTED"; m["evidence"] = m["evidence"] or hr[1]
        m["source"] = "model"
        return m
    if hr:
        return {"state": hr[0], "evidence": hr[1], "product": None, "quantity": None, "source": "rule"}
    return {"state": "NEW", "evidence": "", "product": None, "quantity": None, "source": "abstain"}
