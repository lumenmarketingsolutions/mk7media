#!/usr/bin/env python3
"""Rebuild the raw material for product_map.json: every ad on the FGC account with its
ad set, campaign and creative, plus frame thumbnails for every video and the image for
every static ad, laid out on contact sheets so a human (or Claude) can look at each
creative and record what product it actually sells.

Run from the repo root with the Lumen system token in the environment, e.g.
    railway run --service mk7media -- python3 agents/whatsapp_agent/profiles/fgc_agent_v1_00/tools/fgc_ad_map.py --out /tmp/fgc-ads
Then:
    1. look at sheet_*.jpg, write video_id -> product into classify.json
       ({"<video_id>": "Teeth Whitening Strips", ...}; static ads use "img_<ad_id>")
    2. python3 .../tools/fgc_ad_map.py --out /tmp/fgc-ads --build classify.json
       -> writes product_map.json next to agent.py (ads / videos / adsets / campaigns)
    3. commit + deploy, then hit /fgc-wa/backfill-products and check /fgc-wa/ad-map

Rate limits: the account has ~200 ads; this keeps to ~10 Graph calls by using the
/advideos edge for thumbnails and per-creative lookups only where needed. If Meta
returns (#4) "Application request limit reached" the script waits and retries.
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request

ACCOUNT = os.environ.get("FGC_AD_ACCOUNT", "act_1337494034720023")
TOKEN = os.environ.get("LUMEN_META_CAPI_TOKEN") or os.environ.get("FGC_ADS_TOKEN") or ""
GRAPH = "https://graph.facebook.com/v21.0/"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS = ["Teeth Whitening Strips", "Nasal Strips", "Migraine Relief Cap",
            "Pimple Patches", "Whitening Toothpaste", "Posture Corrector"]
TITLE_RULES = (("nose", "Nasal Strips"), ("nasal", "Nasal Strips"),
               ("toothpaste", "Whitening Toothpaste"),
               ("migraine", "Migraine Relief Cap"), ("cap", "Migraine Relief Cap"),
               ("acne", "Pimple Patches"), ("pimple", "Pimple Patches"), ("patch", "Pimple Patches"),
               ("posture", "Posture Corrector"),
               ("whitening", "Teeth Whitening Strips"), ("teeth", "Teeth Whitening Strips"),
               ("strip", "Teeth Whitening Strips"))


def g(url, **p):
    p["access_token"] = TOKEN
    full = url if url.startswith("http") else GRAPH + url
    sep = "&" if "?" in full else "?"
    for attempt in range(30):
        try:
            with urllib.request.urlopen(full + sep + urllib.parse.urlencode(p), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if '"code":4' in body or '"code":17' in body or e.code in (403, 429):
                print(f"  rate limited, waiting 5 min ({attempt+1})", file=sys.stderr)
                time.sleep(300)
                continue
            raise RuntimeError(f"{e.code} {body}")
    raise RuntimeError("gave up on rate limit")


def product_from_title(*names):
    t = " ".join(n or "" for n in names).lower()
    for needle, product in TITLE_RULES:
        if needle in t:
            return product
    return None


def pull(out):
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    ads = []
    d = g(f"{ACCOUNT}/ads", fields="id,name,effective_status,adset{id,name},campaign{id,name},creative{id}", limit=50)
    while True:
        ads += d.get("data", [])
        nxt = (d.get("paging") or {}).get("next")
        if not nxt:
            break
        d = g(nxt)
    print("ads", len(ads))
    cr = {}
    for a in ads:
        cid = (a.get("creative") or {}).get("id")
        if cid and cid not in cr:
            try:
                cr[cid] = g(cid, fields="id,thumbnail_url,image_url,image_hash,video_id,object_story_spec")
            except Exception as e:
                cr[cid] = {"error": str(e)[:100]}
            time.sleep(0.3)
        a["creative"] = cr.get(cid, {})
    recs = []
    for a in ads:
        c = a["creative"]; oss = c.get("object_story_spec") or {}
        vd = oss.get("video_data") or {}; ld = oss.get("link_data") or {}
        recs.append(dict(ad_id=a["id"], ad_name=a.get("name"), status=a.get("effective_status"),
                         adset_id=a["adset"]["id"], adset_name=a["adset"]["name"],
                         campaign_id=a["campaign"]["id"], campaign_name=a["campaign"]["name"],
                         creative_id=c.get("id"), video_id=c.get("video_id") or vd.get("video_id"),
                         image_url=c.get("image_url") or ld.get("picture"), image_hash=c.get("image_hash"),
                         body=(vd.get("message") or ld.get("message") or "")[:200]))
    json.dump(recs, open(os.path.join(out, "ads.json"), "w"), ensure_ascii=False, indent=1)
    # videos via the account edge (few calls), missing ones individually
    wanted = {r["video_id"] for r in recs if r["video_id"]}
    vids = {}
    d = g(f"{ACCOUNT}/advideos", fields="id,title,length,thumbnails{uri,width,height}", limit=50)
    while True:
        for v in d.get("data", []):
            vids[v["id"]] = v
        nxt = (d.get("paging") or {}).get("next")
        if not nxt:
            break
        time.sleep(1); d = g(nxt)
    for v in sorted(wanted - set(vids)):
        try:
            vids[v] = g(v, fields="id,title,length,thumbnails{uri,width,height}"); time.sleep(1)
        except Exception as e:
            vids[v] = {"id": v, "error": str(e)[:100]}
    frames = {}
    for v in sorted(wanted):
        th = ((vids.get(v) or {}).get("thumbnails") or {}).get("data") or []
        fl = []
        n = min(6, len(th))
        for k, i in enumerate(sorted(set(round(i * (len(th) - 1) / max(1, n - 1)) for i in range(n)))):
            fn = os.path.join(out, "frames", f"{v}_{k}.jpg")
            try:
                urllib.request.urlretrieve(th[i]["uri"], fn); fl.append(fn)
            except Exception:
                pass
        frames[v] = {"frames": fl, "length": (vids.get(v) or {}).get("length")}
    for r in recs:
        if not r["video_id"] and r.get("image_url"):
            fn = os.path.join(out, "frames", f"img_{r['ad_id']}.jpg")
            try:
                urllib.request.urlretrieve(r["image_url"], fn); frames[f"img_{r['ad_id']}"] = {"frames": [fn]}
            except Exception:
                pass
    json.dump(frames, open(os.path.join(out, "frames.json"), "w"), indent=1)
    print("videos with frames", sum(1 for f in frames.values() if f["frames"]), "of", len(frames))
    sheets(out)


def sheets(out):
    from PIL import Image, ImageDraw, ImageFont
    recs = json.load(open(os.path.join(out, "ads.json")))
    frames = json.load(open(os.path.join(out, "frames.json")))
    byv = {}
    for r in recs:
        key = r["video_id"] or f"img_{r['ad_id']}"
        byv.setdefault(key, []).append(r)
    rank = lambda k: 0 if any(a["status"] == "ACTIVE" for a in byv[k]) else 1 if any(a["status"] == "PAUSED" for a in byv[k]) else 2
    keys = sorted([k for k in byv if frames.get(k, {}).get("frames")], key=lambda k: (rank(k), byv[k][0]["adset_name"]))
    W, H, PER, NF = 180, 320, 6, 4
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except Exception:
        font = ImageFont.load_default()
    for si in range(0, len(keys), PER):
        chunk = keys[si:si + PER]
        img = Image.new("RGB", (NF * W + 10, len(chunk) * (H + 46) + 10), "white"); dr = ImageDraw.Draw(img)
        for row, k in enumerate(chunk):
            y = row * (H + 46) + 5; a = byv[k][0]
            dr.text((5, y), f"#{si+row+1} {k} | {a['adset_name'][:40]} | {a['ad_name'][:38]} | {len(byv[k])} ads", fill="black", font=font)
            fl = frames[k]["frames"]; step = max(1, len(fl) // NF)
            for col, f in enumerate(fl[::step][:NF]):
                try:
                    im = Image.open(f); im.thumbnail((W, H)); img.paste(im, (5 + col * W, y + 22))
                except Exception:
                    pass
        img.save(os.path.join(out, f"sheet_{si//PER+1:02d}.jpg"), quality=80)
    json.dump({"order": keys}, open(os.path.join(out, "sheet_order.json"), "w"))
    print("sheets", (len(keys) + PER - 1) // PER, "creatives", len(keys))


def build(out, classify_path):
    """classify.json: {video_id or img_<ad_id>: product}. Everything else from titles."""
    recs = json.load(open(os.path.join(out, "ads.json")))
    cls = json.load(open(classify_path))
    for k, v in cls.items():
        assert v in PRODUCTS, f"unknown product {v!r} for {k}"
    m = {"generated": time.strftime("%Y-%m-%d"), "account": ACCOUNT, "products": PRODUCTS,
         "ads": {}, "videos": {}, "adsets": {}, "campaigns": {}}
    for k, v in cls.items():
        if not k.startswith("img_"):
            m["videos"][k] = {"product": v, "how": "frames"}
    for r in recs:
        key = r["video_id"] or f"img_{r['ad_id']}"
        if key in cls:
            product, how = cls[key], "frames"
        else:
            product, how = product_from_title(r["adset_name"], r["campaign_name"], r["ad_name"]), "title"
        if r.get("image_hash") and key in cls:
            m["videos"][r["image_hash"]] = {"product": cls[key], "how": "frames"}
        m["ads"][r["ad_id"]] = {"product": product, "how": how, "ad_name": r["ad_name"],
                                "adset_id": r["adset_id"], "adset_name": r["adset_name"],
                                "campaign_id": r["campaign_id"], "campaign_name": r["campaign_name"],
                                "video_id": r["video_id"], "status": r["status"]}
        tp = product_from_title(r["adset_name"])
        if tp:
            m["adsets"].setdefault(r["adset_id"], {"product": tp, "name": r["adset_name"], "how": "title"})
        tp = product_from_title(r["campaign_name"])
        if tp:
            m["campaigns"].setdefault(r["campaign_id"], {"product": tp, "name": r["campaign_name"], "how": "title"})
    # an ad set whose ads disagree with its own title gets flagged, never silently trusted
    for sid, v in m["adsets"].items():
        seen = {a["product"] for a in m["ads"].values() if a["adset_id"] == sid and a["how"] == "frames" and a["product"]}
        if seen and (len(seen) > 1 or v["product"] not in seen):
            v["mixed"] = sorted(seen)
    path = os.path.join(HERE, "product_map.json")
    json.dump(m, open(path, "w"), ensure_ascii=False, indent=1)
    unverified = [a for a in m["ads"].values() if a["how"] != "frames"]
    print(f"wrote {path}: {len(m['ads'])} ads ({len(unverified)} by title only), {len(m['videos'])} creatives, "
          f"{len(m['adsets'])} ad sets, {len(m['campaigns'])} campaigns")
    mixed = {k: v for k, v in m["adsets"].items() if v.get("mixed")}
    if mixed:
        print("AD SETS WHOSE CREATIVES DO NOT MATCH THEIR TITLE:")
        for k, v in mixed.items():
            print(f"  {k} {v['name']!r} title says {v['product']} but frames say {v['mixed']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--build", help="classify.json to turn into product_map.json")
    ap.add_argument("--sheets-only", action="store_true")
    a = ap.parse_args()
    if a.build:
        build(a.out, a.build)
    elif a.sheets_only:
        sheets(a.out)
    else:
        if not TOKEN:
            sys.exit("no LUMEN_META_CAPI_TOKEN / FGC_ADS_TOKEN in env")
        pull(a.out)
