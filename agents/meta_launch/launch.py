#!/usr/bin/env python3
"""
Meta Marketing API launcher — creates a campaign + ad set from a JSON config.

Companion to ../meta_audit/pull.py, which only reads. This one writes, so it is
deliberately hard to fire by accident:

  * dry run by default — nothing is created until you pass --go
  * everything is created PAUSED unless you pass --activate
  * a preflight check confirms the token, account, currency and funding first

Setup:
    cp .env.example .env                 # ads_management token + act_<id>
    cp campaign.example.json campaign.json
    python3 launch.py                    # dry run: validate + show the plan
    python3 launch.py --go               # actually create, PAUSED
    python3 launch.py --go --activate    # create and set live (spends money)

Creates no ads — just the campaign shell and the ad set (targeting + budget).
Attach creative in Ads Manager, or extend this script later.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError

HERE = Path(__file__).parent

# ODAX objectives. The older CONVERSIONS/LINK_CLICKS style objectives are retired.
OBJECTIVES = {
    "OUTCOME_AWARENESS", "OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT",
    "OUTCOME_LEADS", "OUTCOME_APP_PROMOTION", "OUTCOME_SALES",
}

BILLING_EVENTS = {"IMPRESSIONS", "LINK_CLICKS", "THRUPLAY", "PAGE_LIKES", "POST_ENGAGEMENT"}

BID_STRATEGIES = {
    "LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS",
}

# Currencies with no minor unit — budgets are whole numbers, not cents.
ZERO_DECIMAL = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA",
    "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}

# Optimization goals that require a promoted_object, and what it must contain.
NEEDS_PIXEL = {"OFFSITE_CONVERSIONS", "VALUE"}
NEEDS_PAGE = {"LEAD_GENERATION", "PAGE_LIKES", "EVENT_RESPONSES", "CONVERSATIONS"}


def load_env():
    """Same contract as meta_audit/pull.py — .env file, overridden by the real environment."""
    env = {}
    envfile = HERE / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for k in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "GRAPH_API_VERSION"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    token = env.get("META_ACCESS_TOKEN", "")
    acct = env.get("META_AD_ACCOUNT_ID", "")
    ver = env.get("GRAPH_API_VERSION", "v23.0")
    if not token or "PASTE" in token or not acct or "XXXX" in acct:
        sys.exit("Missing token or ad account id. Copy .env.example to .env and fill it in.")
    if not acct.startswith("act_"):
        acct = "act_" + acct
    return token, acct, ver


def _api_error(path, e):
    """Meta puts the useful part in error.error_user_msg; surface it instead of a bare 400."""
    body = e.read().decode(errors="replace")
    try:
        err = json.loads(body).get("error", {})
    except json.JSONDecodeError:
        err = {}
    msg = err.get("error_user_msg") or err.get("message") or body
    detail = f"\nMeta API error on {path}:\n  HTTP {e.code}: {msg}"
    if err.get("error_user_title"):
        detail += f"\n  ({err['error_user_title']})"
    if err.get("code"):
        detail += f"\n  code {err['code']}"
        if err.get("error_subcode"):
            detail += f" / subcode {err['error_subcode']}"
    if err.get("code") == 190:
        detail += "\n  -> Token is invalid or expired. Reissue it in Business Settings."
    if err.get("code") == 200:
        detail += "\n  -> Token lacks ads_management scope, or the user can't write to this account."
    return SystemExit(detail)


def get(version, token, path, params=None):
    params = dict(params or {})
    params["access_token"] = token
    url = f"https://graph.facebook.com/{version}/{path}?" + urlencode(params)
    try:
        with urlopen(Request(url), timeout=60) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        raise _api_error(path, e)


def post(version, token, path, params):
    """POST a node. Dicts/lists are JSON-encoded, as the Graph API expects for form fields."""
    body = {k: v for k, v in params.items() if v is not None}
    body["access_token"] = token
    data = urlencode({
        k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in body.items()
    }).encode()
    url = f"https://graph.facebook.com/{version}/{path}"
    try:
        with urlopen(Request(url, data=data, method="POST"), timeout=60) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        raise _api_error(path, e)


def to_minor(amount, currency):
    """Meta takes budgets in the account's minor unit — $50 is 5000, ¥50 is 50."""
    if amount is None:
        return None
    if currency in ZERO_DECIMAL:
        return str(int(round(float(amount))))
    return str(int(round(float(amount) * 100)))


def money(amount, currency):
    return f"{amount:,.0f} {currency}" if currency in ZERO_DECIMAL else f"{amount:,.2f} {currency}"


def load_config(path):
    cfg_file = Path(path) if Path(path).is_absolute() else HERE / path
    if not cfg_file.exists():
        sys.exit(f"No config at {cfg_file}. Copy campaign.example.json to campaign.json and edit it.")
    try:
        cfg = json.loads(cfg_file.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{cfg_file} is not valid JSON: {e}")
    for section in ("campaign", "adset"):
        if section not in cfg:
            sys.exit(f"Config is missing the '{section}' section.")
    return cfg


def validate(cfg):
    """Catch the mistakes that would otherwise come back as an opaque HTTP 400."""
    problems = []
    camp, adset = cfg["campaign"], cfg["adset"]

    if not camp.get("name"):
        problems.append("campaign.name is required.")
    if camp.get("objective") not in OBJECTIVES:
        problems.append(f"campaign.objective must be one of: {', '.join(sorted(OBJECTIVES))}")
    if not isinstance(camp.get("special_ad_categories"), list):
        problems.append(
            "campaign.special_ad_categories must be a list — use [] for none. Ads about credit, "
            "employment, housing, social issues, elections or politics MUST declare the category."
        )

    if not adset.get("name"):
        problems.append("adset.name is required.")
    if adset.get("billing_event", "IMPRESSIONS") not in BILLING_EVENTS:
        problems.append(f"adset.billing_event must be one of: {', '.join(sorted(BILLING_EVENTS))}")
    if adset.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP") not in BID_STRATEGIES:
        problems.append(f"adset.bid_strategy must be one of: {', '.join(sorted(BID_STRATEGIES))}")
    if not adset.get("targeting", {}).get("geo_locations"):
        problems.append("adset.targeting.geo_locations is required (countries, regions or cities).")

    # Budget lives on exactly one level: campaign (CBO) or ad set — never both.
    camp_budget = camp.get("daily_budget") or camp.get("lifetime_budget")
    adset_budget = adset.get("daily_budget") or adset.get("lifetime_budget")
    if camp_budget and adset_budget:
        problems.append("Budget is set on both campaign and ad set. Pick one (campaign = CBO).")
    if not camp_budget and not adset_budget:
        problems.append("No budget set. Add daily_budget or lifetime_budget to campaign or ad set.")
    if adset.get("daily_budget") and adset.get("lifetime_budget"):
        problems.append("adset has both daily_budget and lifetime_budget. Pick one.")
    if (camp.get("lifetime_budget") or adset.get("lifetime_budget")) and not adset.get("end_time"):
        problems.append("A lifetime budget requires adset.end_time.")

    # Conversion and lead goals need a promoted_object or the API rejects the ad set.
    goal = adset.get("optimization_goal", "")
    promoted = adset.get("promoted_object") or {}
    if goal in NEEDS_PIXEL and not promoted.get("pixel_id"):
        problems.append(f"optimization_goal {goal} requires promoted_object.pixel_id "
                        "(and usually custom_event_type, e.g. PURCHASE or LEAD).")
    if goal in NEEDS_PAGE and not promoted.get("page_id"):
        problems.append(f"optimization_goal {goal} requires promoted_object.page_id.")

    if problems:
        sys.exit("Config problems:\n" + "\n".join(f"  - {p}" for p in problems))


def preflight(ver, token, acct):
    """Confirm the token works and the account can actually spend before we create anything."""
    acc = get(ver, token, acct, {
        "fields": "name,account_status,currency,timezone_name,disable_reason,funding_source"
    })
    currency = acc.get("currency", "USD")
    status = acc.get("account_status")
    print(f"Account : {acc.get('name')}  [{acct}]")
    print(f"Currency: {currency}   Timezone: {acc.get('timezone_name')}")

    # 1 = ACTIVE. Anything else can't serve ads.
    if status != 1:
        labels = {2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW",
                  8: "PENDING_SETTLEMENT", 9: "IN_GRACE_PERIOD", 100: "PENDING_CLOSURE",
                  101: "CLOSED", 201: "ANY_ACTIVE", 202: "ANY_CLOSED"}
        print(f"  ! Account status is {status} ({labels.get(status, 'unknown')}) — ads may not deliver.")
    if not acc.get("funding_source"):
        print("  ! No funding source on the account. Add a payment method before activating.")
    return currency


def plan(cfg, currency, status):
    camp, adset = cfg["campaign"], cfg["adset"]
    t = adset.get("targeting", {})
    geo = t.get("geo_locations", {})
    where = ", ".join(geo.get("countries", []) or
                      [r.get("key", "?") for r in geo.get("regions", [])] or
                      [c.get("key", "?") for c in geo.get("cities", [])]) or "?"

    print("\n--- Plan " + "-" * 52)
    print(f"Campaign : {camp['name']}")
    print(f"           {camp['objective']}   status={status}")
    cats = camp.get("special_ad_categories") or []
    print(f"           special_ad_categories={cats or 'NONE'}")
    if camp.get("daily_budget"):
        print(f"           daily budget {money(camp['daily_budget'], currency)}  (CBO)")
    if camp.get("lifetime_budget"):
        print(f"           lifetime budget {money(camp['lifetime_budget'], currency)}  (CBO)")

    print(f"Ad set   : {adset['name']}")
    if adset.get("daily_budget"):
        print(f"           daily budget {money(adset['daily_budget'], currency)}")
    if adset.get("lifetime_budget"):
        print(f"           lifetime budget {money(adset['lifetime_budget'], currency)}")
    print(f"           optimize for {adset.get('optimization_goal', '-')}, "
          f"billed on {adset.get('billing_event', 'IMPRESSIONS')}")
    print(f"           bid strategy {adset.get('bid_strategy', 'LOWEST_COST_WITHOUT_CAP')}")
    print(f"           geo {where} | age {t.get('age_min', 18)}-{t.get('age_max', 65)}")
    if t.get("publisher_platforms"):
        print(f"           platforms {', '.join(t['publisher_platforms'])}")
    if adset.get("start_time"):
        print(f"           starts {adset['start_time']}")
    if adset.get("end_time"):
        print(f"           ends   {adset['end_time']}")
    print("-" * 61)


def main():
    ap = argparse.ArgumentParser(description="Create a Meta campaign + ad set from a JSON config.")
    ap.add_argument("--config", default="campaign.json", help="config file (default: campaign.json)")
    ap.add_argument("--go", action="store_true", help="actually create it (default is a dry run)")
    ap.add_argument("--activate", action="store_true",
                    help="create ACTIVE instead of PAUSED — this starts spending")
    args = ap.parse_args()

    token, acct, ver = load_env()
    cfg = load_config(args.config)
    validate(cfg)

    status = "ACTIVE" if args.activate else "PAUSED"
    currency = preflight(ver, token, acct)
    plan(cfg, currency, status)

    if not args.go:
        print("\nDry run — nothing was created. Re-run with --go to create it (PAUSED).")
        return

    if args.activate:
        print("\n!! --activate: this ad set will start spending as soon as it's approved.")
        if input("   Type the campaign name to confirm: ").strip() != cfg["campaign"]["name"]:
            sys.exit("   Names didn't match. Nothing was created.")

    camp, adset = cfg["campaign"], cfg["adset"]

    campaign_id = post(ver, token, f"{acct}/campaigns", {
        "name": camp["name"],
        "objective": camp["objective"],
        "status": status,
        "special_ad_categories": camp.get("special_ad_categories", []),
        "buying_type": camp.get("buying_type", "AUCTION"),
        "daily_budget": to_minor(camp.get("daily_budget"), currency),
        "lifetime_budget": to_minor(camp.get("lifetime_budget"), currency),
        "bid_strategy": camp.get("bid_strategy") if camp.get("daily_budget") or
                        camp.get("lifetime_budget") else None,
    })["id"]
    print(f"\nCampaign created: {campaign_id}")

    try:
        adset_id = post(ver, token, f"{acct}/adsets", {
            "name": adset["name"],
            "campaign_id": campaign_id,
            "status": status,
            "billing_event": adset.get("billing_event", "IMPRESSIONS"),
            "optimization_goal": adset.get("optimization_goal"),
            "bid_strategy": adset.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            "bid_amount": to_minor(adset.get("bid_amount"), currency),
            "daily_budget": to_minor(adset.get("daily_budget"), currency),
            "lifetime_budget": to_minor(adset.get("lifetime_budget"), currency),
            "start_time": adset.get("start_time"),
            "end_time": adset.get("end_time"),
            "targeting": adset.get("targeting"),
            "promoted_object": adset.get("promoted_object"),
            "attribution_spec": adset.get("attribution_spec"),
        })["id"]
    except SystemExit:
        # The campaign exists but is empty. It's PAUSED and spends nothing, but say so plainly.
        print(f"\nAd set failed. Campaign {campaign_id} was created and is now empty ({status}).")
        print(f"Delete it with:  curl -X DELETE "
              f"'https://graph.facebook.com/{ver}/{campaign_id}?access_token=$META_ACCESS_TOKEN'")
        raise

    print(f"Ad set created  : {adset_id}")
    print(f"\nBoth are {status}. Next: add creative and an ad to ad set {adset_id} in Ads Manager:")
    print(f"  https://adsmanager.facebook.com/adsmanager/manage/ads?act={acct.replace('act_', '')}"
          f"&selected_adset_ids={adset_id}")


if __name__ == "__main__":
    main()
