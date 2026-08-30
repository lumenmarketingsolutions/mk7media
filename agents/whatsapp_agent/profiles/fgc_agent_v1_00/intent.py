# -*- coding: utf-8 -*-
"""
Runtime intent detection for FGC conversations, and the trigger that turns a state
change into a Meta conversion event.

This is deliberately NOT the probabilistic label model from the lumen-ai repo. That
model exists to manufacture training data offline, where recall matters and a wrong
label costs one row in a dataset. Here a wrong label costs the merchant real money:
a false Purchase inflates reported ROAS and teaches the algorithm to chase people who
never bought. So at runtime we run only the high-precision subset of the rules, and
we abstain loudly rather than guess.

The rules and the thresholds come from `lumen-ai/product/labeling/lfs.py` and the
findings in `CORPUS-FINDINGS.md`. Three of them are doing most of the work:

  * The Meta ad prefill is a quarter of all inbound and carries no intent whatsoever.
  * A Lebanese town means "do you deliver here" before the shop asks for an address
    and means "send it here" afterwards. Same words, two states, one turn of context.
  * A commitment can be withdrawn. One customer in a 22-hour export gave an address,
    heard the delivery fee, said la2 shukran, and re-committed two turns later. That
    is why COMMITTED settles before it fires instead of firing on the address.
"""
import re
import sqlite3
import time

ABSTAIN = None


def rx(p):
    return re.compile(p, re.I | re.U)


PREFILL = rx(r"can i get more info on this|مزيد من المعلومات حول هذا|puis-je en savoir plus")

ASK_LOCATION = rx(r"\blocation\b|\bwen bad+ak\b|وين بدك|بعتلي ال ?location|\bname\s*\?|"
                  r"\baddress\b|وين بتحب|عنوان")

PLACES = rx(r"\b(be[iy]rou?t|bayrut|tripoli|tarablus|trablos|sa[iy]da|sidon|sour|tyre|"
            r"zahl[ée]h?|jounieh?|jbeil|byblos|batroun|baalbe[ck]k?|hermel|akkar|"
            r"koura|kfer\w*|kfar\w*|ghazir|zouk|jdeide\w*|dekwaneh?|hazmieh?|hadath|"
            r"chiyah|mansourieh?|antelias|dbaye\w*|zalka|bourj\s*hammoud|achrafieh?|"
            r"hamra|verdun|mazraa|aley|bhamdoun|broummana|beit\s*mery|nabatieh?|"
            r"marjeyoun|halba|chekka|amioun|bcharre|zgharta|kaslik|tabarja|adma|"
            r"bikfaya|choueifat|khalde|damour|jiyeh|sin\s*el\s*fil|barelias|bar\s*elias|"
            r"riyaq|rayak|minyeh?|miny[ei]|hour\s*taala)\b|"
            r"بيروت|طرابلس|صيدا|صور|زحلة|جونية|جبيل|بعلبك|الهرمل|عكار|الكورة|"
            r"برجا|رياق|المنية|حور تعلا|الشوف|البقاع|بشري|زغرتا|النبطية")

ADDR = rx(r"\b(bld?g|building|bnaye|bneye|flo?r|floor|tabe2|etage|street|shar3|jenb|"
          r"janb|near|2rib|ha[yi]\b|mahal|ma7al|snack|super\s*market|kenise|jem3a|"
          r"khalf|wara|addres+|adres+|3enw[ae]n)\b|"
          r"شارع|بناية|طابق|قرب|جنب|خلف|حي |محل|منطقة|عنوان|بلدة")

NAME_FIELD = rx(r"\b(name|esm|nom)\s*[:：]|\bاسم\s*[:：]")
PHONE = rx(r"(?<!\d)0?(?:3|70|71|76|78|79|81)\s?\d{6}(?!\d)")
LOCATION_PIN = rx(r"\[location pin")

COLOUR = r"(?:black|blue|bleu|noir|red|pink|white|abyad|aswad)"
UNIT = r"(?:pcs|pieces?|3elab|3elbe|3olbe|box(?:es)?|strips?)"
WANT = r"(?:bad+[eiy]|baddy|bde|please|plz|i want)"
QTY = rx(rf"\b\d{{1,2}}\s*(?:{UNIT}|{COLOUR})\b|\b{WANT}\s*\d{{1,2}}\b|"
         rf"\b\d{{1,2}}\s*{WANT}\b|^\s*{COLOUR}\s*$|"
         rf"\b(?:we7de|wehde|wehdi|wa7de|tnen|tneen)\b|واحدة|واحده|تنين")

ORDER_INTENT = rx(r"\b(et?l[oa]u?b|etlob|eetlob|i.?ll take|i want to order)\b|"
                  r"بدي اطلب|بدي طلب|عتمدت")

NO = rx(r"^\s*(la2?\s*(shukran|chokran|kalas|khalas)?|no+( thanks?| thank you)?|"
        r"ma\s*ba2a\s*bad+[iy]|ma\s*bad+[iy]|non merci)\b|"
        r"لا شكرا|لا شكراً|^\s*لا\s*$|ما بعد بدي|ما بدي")
CANCEL = rx(r"\b(l8[iy]|lag?h[iy]|cancel|il8[iy])\b|لغي|إلغاء")

MEDIA = rx(r"^\s*\[(audio|image|video|document|sticker)\s*message\]\s*$")
HUMAN_REQ = rx(r"kell?[ie]mn[iy] 3arab[iy]|كلمني عربي|speak arabic|complaint|شكوى|مدير")

BUSINESS_CONFIRM = rx(r"^\s*(done|confirmed|تم|تمام)\s*[.!]?\s*$")

RUNG = {"NEW": 0, "ENQUIRY": 1, "QUALIFIED": 2, "INTENT": 3, "COMMITTED": 4}


def classify(messages):
    """Walk a thread in order and return (state, evidence, needs_human).

    `messages` is a list of dicts with `direction` ('in' | 'out' | 'out_app') and
    `body`. Walking forward rather than taking a maximum is not a stylistic choice:
    a max over rungs calls the commit-then-cancel thread COMMITTED and a max over
    terminals calls it LOST. Only the walk gets it right.
    """
    # Two evidence slots, not one. The span that justifies a commitment and the span
    # that justifies a walk-away are different quotes, and a thread can contain both.
    # Keeping one slot meant the commit-then-cancel-then-recommit thread ended up
    # COMMITTED while quoting "la2 shukran" as its reason — the exact opposite of what
    # happened, and worse than no evidence at all for anyone auditing a fired event.
    reached, state, needs_human = "NEW", "NEW", False
    rung_evidence = lost_evidence = None
    asked_location = False

    for m in messages:
        body = (m.get("body") or "").strip()
        inbound = m.get("direction") == "in"

        if not inbound:
            if ASK_LOCATION.search(body):
                asked_location = True
            continue

        if MEDIA.match(body) or HUMAN_REQ.search(body):
            needs_human = True
            continue
        if PREFILL.search(body):
            continue                                    # a button press, not a message

        hit = None
        # COMMITTED, strongest first. Each of these is something a person only types
        # when they expect a delivery.
        if LOCATION_PIN.search(body) or NAME_FIELD.search(body) or ADDR.search(body):
            hit = "COMMITTED"
        elif asked_location and (PLACES.search(body) or PHONE.search(body)):
            hit = "COMMITTED"
        elif ORDER_INTENT.search(body):
            hit = "INTENT"
        elif QTY.search(body):
            hit = "QUALIFIED"

        if CANCEL.search(body) or NO.search(body):
            state = "LOST"
            lost_evidence = body[:160]
            continue

        if hit:
            if RUNG[hit] > RUNG[reached]:
                reached = hit
                rung_evidence = body[:160]
            elif state == "LOST":
                # Re-committing after a walk-away. The rung does not move, but this
                # message is now the reason the conversation is live again.
                rung_evidence = body[:160]
            state = reached                             # a commitment un-does a walk-away

    evidence = lost_evidence if state == "LOST" else rung_evidence
    return state, evidence, needs_human


def classify_wa(wa_id, db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT direction, body FROM wa_messages WHERE wa_id = ? ORDER BY id",
            (wa_id,)).fetchall()
    finally:
        conn.close()
    return classify([dict(r) for r in rows])


# ---------------------------------------------------------------- the trigger

def on_conversation_update(wa_id):
    """Called after each inbound message. Queues or fires conversion events.

    LeadSubmitted goes immediately — a qualified lead is qualified the moment they
    name a quantity, and there is nothing to withdraw. Purchase is queued behind the
    settle window instead, and re-checked when the window closes, because the corpus
    says commitments get withdrawn inside minutes.
    """
    from . import agent, capi_bm
    try:
        state, evidence, needs_human = classify_wa(wa_id, agent.DB_PATH)
    except Exception as e:
        print(f"[fgc-intent] classify failed for {wa_id}: {e}")
        return None

    try:
        if RUNG.get(state, 0) >= RUNG["QUALIFIED"] and state != "LOST":
            capi_bm.send(wa_id, "LeadSubmitted", state=state)
        if state == "COMMITTED":
            capi_bm.queue(wa_id, "Purchase", state=state, evidence=evidence)
    except Exception as e:
        print(f"[fgc-intent] event dispatch failed for {wa_id}: {e}")
    return state
