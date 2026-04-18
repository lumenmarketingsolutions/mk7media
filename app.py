import os
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ── Config ──
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "marykatezarehghazarian@gmail.com")

@app.route("/")
def home():
    return render_template("index.html")

def _build_inquiry_email(name, email, business, website, service_type, budget, worked_with_agency, goals):
    dash = "\u2014"
    goals_block = ""
    if goals:
        goals_block = (
            '<div style="margin-top: 24px; padding: 16px; background: #f9f9f9; border-radius: 8px;">'
            '<p style="margin: 0 0 4px; color: #888; font-size: 13px;">Goals</p>'
            f'<p style="margin: 0; color: #111;">{goals}</p>'
            '</div>'
        )
    return (
        '<div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px;">'
        '<h2 style="margin: 0 0 24px; color: #111;">New Inquiry from MK7 Media</h2>'
        '<table style="width: 100%; border-collapse: collapse;">'
        f'<tr><td style="padding: 8px 0; color: #888; width: 140px;">Name</td><td style="padding: 8px 0; color: #111; font-weight: 600;">{name}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Email</td><td style="padding: 8px 0; color: #111;">{email}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Business</td><td style="padding: 8px 0; color: #111;">{business or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Website</td><td style="padding: 8px 0; color: #111;">{website or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Service</td><td style="padding: 8px 0; color: #111;">{service_type or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Monthly Budget</td><td style="padding: 8px 0; color: #111;">{budget or dash}</td></tr>'
        f'<tr><td style="padding: 8px 0; color: #888;">Worked w/ Agency</td><td style="padding: 8px 0; color: #111;">{worked_with_agency or dash}</td></tr>'
        '</table>'
        f'{goals_block}'
        '</div>'
    )

@app.route("/api/inquiry", methods=["POST"])
def inquiry():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    business = data.get("business", "").strip()
    website = data.get("website", "").strip()
    service_type = data.get("service_type", "").strip()
    budget = data.get("budget", "").strip()
    worked_with_agency = data.get("worked_with_agency", "").strip()
    goals = data.get("goals", "").strip()

    if not name or not email:
        return jsonify({"error": "Name and email are required"}), 400

    # Send notification email
    if RESEND_API_KEY:
        try:
            import resend
            resend.api_key = RESEND_API_KEY
            resend.Emails.send({
                "from": "MK7 Media <notifications@lumenmarketing.co>",
                "to": [NOTIFY_EMAIL, "kendall@lumenmarketing.co"],
                "subject": f"New Inquiry: {name} — {service_type}",
                "html": _build_inquiry_email(name, email, business, website, service_type, budget, worked_with_agency, goals)
            })
        except Exception as e:
            print(f"[email] Failed to send notification: {e}")

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

    if not whatsapp:
        return jsonify({"error": "WhatsApp number is required"}), 400

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
            for email in [NOTIFY_EMAIL, "kendall@lumenmarketing.co"]:
                req.post("https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={"from": "MK7 Media <notifications@lumenmarketing.co>", "to": [email], "subject": subject, "html": body})
        except Exception as e:
            print(f"[email] Failed: {e}")

    return jsonify({"ok": True})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5050)
