#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch A-share market snapshot from Eastmoney public APIs -> live_data.js

Runs on GitHub Actions (scheduled Mon-Fri 09:00-16:00 Beijing time, hourly).
Uses only Python stdlib so no pip install is needed.
"""
import json
import urllib.request
import datetime

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def get(url, timeout=15):
    import time
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == 0:
                time.sleep(2)
    raise last


def safe(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        print("WARN:", repr(e))
        return None


data = {
    "updated_at": "",
    "source": "东方财富公开行情",
    "market_status": "",
    "indices": [],
    "breadth": None,
    "total_amount_yi": None,
    "sectors": {"top": [], "bottom": []},
}

# Beijing time
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
data["updated_at"] = now.strftime("%Y-%m-%d %H:%M")
wd = now.weekday()
mins = now.hour * 60 + now.minute
if wd < 5 and (570 <= mins <= 690 or 780 <= mins <= 900):
    data["market_status"] = "盘中"
elif wd < 5 and mins > 900:
    data["market_status"] = "已收盘"
elif wd < 5:
    data["market_status"] = "未开盘"
else:
    data["market_status"] = "休市"

# 1) indices (5 main + Shenzhen composite for total turnover)
idx = safe(lambda: get(
    "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f3,f4,f6,f12,f14,f18"
    "&secids=1.000001,0.399001,1.000300,0.399006,1.000688,0.399106"
))
if idx and idx.get("data") and idx["data"].get("diff"):
    for it in idx["data"]["diff"]:
        data["indices"].append({
            "code": it.get("f12"),
            "name": it.get("f14"),
            "price": it.get("f2"),
            "pct": it.get("f3"),
            "chg": it.get("f4"),
            "prev": it.get("f18"),
            "amount": it.get("f6"),
        })
    amt = 0.0
    for it in data["indices"]:
        if it["code"] in ("000001", "399106") and it.get("amount"):
            amt += it["amount"]
    if amt > 0:
        data["total_amount_yi"] = round(amt / 1e8, 1)

# 2) market breadth (up / down / flat counts, whole A-share)
br = safe(lambda: get(
    "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&po=1&np=1&fltt=2&invt=2&fid=f3"
    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f104,f105,f106"
))
if br and br.get("data") and br["data"].get("diff"):
    def num(x):
        if x is None:
            return None
        try:
            return int(str(x).replace(",", ""))
        except Exception:  # noqa: BLE001
            return None
    d = br["data"]["diff"][0]
    b = {"up": num(d.get("f104")), "down": num(d.get("f105")), "flat": num(d.get("f106"))}
    if b["up"] is not None:  # only publish when market is open and counts are real
        data["breadth"] = b


def sectors(po, pz=5):
    r = safe(lambda: get(
        "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=%d&po=%d&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:90+t:2+f:!50&fields=f12,f14,f3" % (pz, po)
    ))
    out = []
    if r and r.get("data") and r["data"].get("diff"):
        for it in r["data"]["diff"]:
            out.append({"name": it.get("f14"), "pct": it.get("f3")})
    return out


# 3) industry sector ranking (top gainers / top losers)
data["sectors"]["top"] = sectors(1)
data["sectors"]["bottom"] = sectors(0)

with open("live_data.js", "w", encoding="utf-8") as f:
    f.write("window.CLOUD_DATA=" + json.dumps(data, ensure_ascii=False) + ";\n")

print("written live_data.js |", data["updated_at"], data["market_status"])
print("indices:", len(data["indices"]),
      "| breadth:", data["breadth"],
      "| amount(yi):", data["total_amount_yi"])
print("top:", [s["name"] for s in data["sectors"]["top"]],
      "| bottom:", [s["name"] for s in data["sectors"]["bottom"]])
