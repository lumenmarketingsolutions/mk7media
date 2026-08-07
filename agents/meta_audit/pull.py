#!/usr/bin/env python3
"""
Meta Marketing API puller — read-only audit snapshot of an ad account.

Pulls account / campaign / ad set / ad structure plus insights (last 30 & 90 days)
and writes them to ./out as JSON + flattened CSVs. Prints a quick top-line summary.

Setup:
    cp .env.example .env   # then put the client's ads_read token + act_<id> in .env
    python3 pull.py

Only reads. Never mutates the ad account.
"""
import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError

HERE = Path(__file__).parent
OUT = HERE / "out"
DATE_PRESETS = ["last_30d", "last_90d"]

INSIGHT_FIELDS = [
    "campaign_name", "adset_name", "ad_name", "objective",
    "spend", "impressions", "reach", "frequency", "clicks",
    "ctr", "cpc", "cpm", "actions", "action_values",
    "purchase_roas", "cost_per_action_type",
]


def load_env():
    env = {}
    envfile = HERE / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # real environment overrides the file
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


def get(version, token, path, params=None):
    """GET a Graph API node, following pagination, returning the combined `data` list
    (or the raw object for single nodes)."""
    params = dict(params or {})
    params["access_token"] = token
    base = f"https://graph.facebook.com/{version}/{path}"
    url = base + "?" + urlencode(params)
    rows = []
    while url:
        try:
            with urlopen(Request(url), timeout=60) as r:
                payload = json.loads(r.read().decode())
        except HTTPError as e:
            body = e.read().decode(errors="replace")
            raise SystemExit(f"\nMeta API error on {path}:\n  HTTP {e.code}\n  {body}\n"
                             "If it mentions an unsupported version, bump GRAPH_API_VERSION in .env.")
        if "data" in payload:
            rows.extend(payload["data"])
            url = payload.get("paging", {}).get("next")
            time.sleep(0.2)  # be gentle on rate limits
        else:
            return payload  # single object
    return rows


def _action_val(items, *types):
    """Sum the 'value' of matching action types from an actions/action_values list."""
    if not isinstance(items, list):
        return 0.0
    total = 0.0
    for it in items:
        if it.get("action_type") in types:
            try:
                total += float(it.get("value", 0))
            except (TypeError, ValueError):
                pass
    return total


def summarize_row(row):
    spend = float(row.get("spend", 0) or 0)
    purchases = _action_val(row.get("actions"), "purchase", "omni_purchase",
                            "offsite_conversion.fb_pixel_purchase")
    revenue = _action_val(row.get("action_values"), "purchase", "omni_purchase",
                          "offsite_conversion.fb_pixel_purchase")
    roas = (revenue / spend) if spend else 0.0
    cpa = (spend / purchases) if purchases else 0.0
    return {
        "campaign": row.get("campaign_name", ""),
        "adset": row.get("adset_name", ""),
        "ad": row.get("ad_name", ""),
        "spend": round(spend, 2),
        "impressions": int(float(row.get("impressions", 0) or 0)),
        "reach": int(float(row.get("reach", 0) or 0)),
        "frequency": round(float(row.get("frequency", 0) or 0), 2),
        "clicks": int(float(row.get("clicks", 0) or 0)),
        "ctr": round(float(row.get("ctr", 0) or 0), 2),
        "cpc": round(float(row.get("cpc", 0) or 0), 2),
        "cpm": round(float(row.get("cpm", 0) or 0), 2),
        "purchases": int(purchases),
        "revenue": round(revenue, 2),
        "roas": round(roas, 2),
        "cpa": round(cpa, 2),
    }


def write_csv(path, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    token, acct, ver = load_env()
    OUT.mkdir(exist_ok=True)
    print(f"Pulling {acct} via Graph {ver} (read-only)\n")

    # ---- Structure ----
    account = get(ver, token, acct, {"fields": "name,account_status,currency,timezone_name,amount_spent,balance"})
    (OUT / "account.json").write_text(json.dumps(account, indent=2))
    print(f"Account: {account.get('name')}  ({account.get('currency')}, {account.get('timezone_name')})")

    campaigns = get(ver, token, f"{acct}/campaigns",
                    {"fields": "id,name,status,effective_status,objective,daily_budget,lifetime_budget,bid_strategy,buying_type",
                     "limit": 200})
    (OUT / "campaigns.json").write_text(json.dumps(campaigns, indent=2))

    adsets = get(ver, token, f"{acct}/adsets",
                 {"fields": "id,name,status,effective_status,campaign_id,daily_budget,lifetime_budget,optimization_goal,billing_event,targeting",
                  "limit": 500})
    (OUT / "adsets.json").write_text(json.dumps(adsets, indent=2))

    ads = get(ver, token, f"{acct}/ads",
              {"fields": "id,name,status,effective_status,adset_id,campaign_id,creative",
               "limit": 500})
    (OUT / "ads.json").write_text(json.dumps(ads, indent=2))

    active_c = sum(1 for c in campaigns if c.get("effective_status") == "ACTIVE")
    print(f"Campaigns: {len(campaigns)} ({active_c} active) | Ad sets: {len(adsets)} | Ads: {len(ads)}\n")

    # ---- Insights per level per window ----
    for preset in DATE_PRESETS:
        for level in ("campaign", "adset", "ad"):
            raw = get(ver, token, f"{acct}/insights",
                      {"level": level, "date_preset": preset,
                       "fields": ",".join(INSIGHT_FIELDS), "limit": 500})
            (OUT / f"insights_{level}_{preset}.json").write_text(json.dumps(raw, indent=2))
            rows = [summarize_row(r) for r in raw]
            rows.sort(key=lambda x: x["spend"], reverse=True)
            write_csv(OUT / f"insights_{level}_{preset}.csv", rows)

        # top-line summary for the window, at campaign level
        camp_rows = [summarize_row(r) for r in
                     json.loads((OUT / f"insights_campaign_{preset}.json").read_text())]
        tot_spend = round(sum(r["spend"] for r in camp_rows), 2)
        tot_rev = round(sum(r["revenue"] for r in camp_rows), 2)
        blended = round(tot_rev / tot_spend, 2) if tot_spend else 0
        print(f"== {preset} ==  spend ${tot_spend:,.2f} | revenue ${tot_rev:,.2f} | blended ROAS {blended}")
        for r in sorted(camp_rows, key=lambda x: x["roas"], reverse=True)[:5]:
            print(f"   {r['roas']:>5}x ROAS | ${r['spend']:>9,.2f} | CPA ${r['cpa']:>7,.2f} | {r['campaign'][:48]}")
        print()

    print(f"Wrote JSON + CSV to {OUT}")


if __name__ == "__main__":
    main()
