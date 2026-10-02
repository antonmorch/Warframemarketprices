#!/usr/bin/env python3
"""Fetch warframe.market prime set prices, build data + static HTML page.
Designed for GitHub Actions (or any cron). No cache files needed.
"""
import json, urllib.request, time, datetime, re, os

HDRS = {"Platform": "pc", "User-Agent": "wf-prices-action/1.0"}
BASE = "https://api.warframe.market/v2"

def fetch(path):
    req = urllib.request.Request(BASE + path, headers=HDRS)
    return json.load(urllib.request.urlopen(req, timeout=30))["data"]

def main():
    items = fetch("/items")
    id2slug = {it["id"]: it["slug"] for it in items}
    sets = {}
    for it in items:
        if it.get("slug", "").endswith("_set") and "prime" in (it.get("tags") or []):
            sets[it["slug"]] = it
    print(f"{len(sets)} prime sets")
    orders = {}
    all_slugs = list(sets)
    # part slugs come from each set's detail; batch politely
    for slug in all_slugs:
        for attempt in range(3):
            try:
                detail = fetch(f"/items/{slug}")
                # setParts are item ids (incl. the set itself) -> map to slugs
                sets[slug]["parts"] = [id2slug[i] for i in detail.get("setParts", [])
                                       if id2slug.get(i) and id2slug[i] != slug]
                break
            except Exception as e:
                print("retry", slug, e); time.sleep(2)
        time.sleep(0.3)
    part_slugs = sorted({p for i in sets.values() for p in i["parts"]})
    print(f"{len(part_slugs)} parts")
    for slug in all_slugs + part_slugs:
        for attempt in range(3):
            try:
                data = fetch(f"/orders/item/{slug}")
                orders[slug] = [[o["platinum"], o["user"]["status"]] for o in data if o["type"] == "sell"]
                break
            except Exception as e:
                print("retry", slug, e); time.sleep(2)
        time.sleep(0.3)
        if len(orders) % 100 == 0:
            print(len(orders), "fetched", flush=True)

    def lowest(sells, pred):
        ps = [p for p, st in sells if pred(st)]
        return min(ps) if ps else None
    def cat(info):
        t = info.get("tags", [])
        return "warframe" if "warframe" in t else ("weapon" if "weapon" in t else "companion")

    rows = []
    for slug, info in sorted(sets.items()):
        sells = orders.get(slug, [])
        ing, onl = lowest(sells, lambda s: s == "ingame"), lowest(sells, lambda s: s != "offline")
        part_ing, part_onl = [], []
        for ps in info["parts"]:
            psells = orders.get(ps, [])
            part_ing.append(lowest(psells, lambda s: s == "ingame"))
            part_onl.append(lowest(psells, lambda s: s != "offline"))
        si = sum(p for p in part_ing if p is not None)
        so = sum(p for p in part_onl if p is not None)
        m = sum(1 for p in part_ing if p is None)
        di = si - ing if ing is not None and m == 0 else None
        do = so - onl if onl is not None and m == 0 else None
        rows.append({"set": info["i18n"]["en"]["name"], "slug": slug, "category": cat(info),
                     "set_price_ingame": ing, "set_price_online": onl,
                     "parts_sum_ingame": si, "parts_sum_online": so, "missing_parts": m,
                     "difference_ingame": di, "difference_online": do,
                     "pct_ingame": round(100*di/ing, 1) if di is not None and ing else None,
                     "pct_online": round(100*do/onl, 1) if do is not None and onl else None,
                     "parts": [{"slug": p, "ingame": part_ing[i], "online": part_onl[i]}
                               for i, p in enumerate(info["parts"])]})
    snap_time = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    json.dump({"time": snap_time, "rows": rows}, open("Price Snapshot.json", "w"), indent=1)
    data = [{"n": r["set"], "s": r["slug"], "c": r["category"],
             "ing": r["set_price_ingame"], "onl": r["set_price_online"],
             "pi": r["parts_sum_ingame"], "po": r["parts_sum_online"], "m": r["missing_parts"],
             "parts": [{"s": p["slug"].replace("_", " "), "id": p["slug"], "i": p["ingame"], "o": p["online"]}
                       for p in r["parts"]]} for r in rows]
    html = open("Prime Set Prices.html").read()  # template with placeholder data
    html = re.sub(r'const DATA = (\[.*?\]);\n', lambda m: "const DATA = " + json.dumps(data) + ";\n", html, count=1, flags=re.S)
    html = re.sub(r'const META = ".*?";', 'const META = "' + snap_time + '";', html)
    open("Prime Set Prices.html", "w").write(html)
    print("written", len(html))

if __name__ == "__main__":
    main()
