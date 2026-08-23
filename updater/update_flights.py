#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ITH Flight Price Watch - auto updater (Nan <-> Bangkok)
--------------------------------------------------------
ดึงราคาตั๋วเครื่องบินถูกสุดของ Thai AirAsia และ Nok Air
เส้นทาง น่าน (NNT) <-> กรุงเทพ (DMK/BKK) ล่วงหน้า 15 วัน จาก Trip.com
แล้วเขียน flights.json + push ขึ้น GitHub Pages

รัน:  python update_flights.py            (ปกติ - ใช้กับ Task Scheduler ทุก 12 ชม.)
      python update_flights.py --days 2   (ทดสอบเร็ว)
"""
import json, os, re, sys, subprocess, datetime, pathlib, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_DIR    = pathlib.Path(__file__).resolve().parent.parent
FLIGHTS_JSON = REPO_DIR / "flights.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# เส้นทางที่ติดตาม
ROUTES = [
    {"key": "NNT_BKK", "from": "nnt", "to": "bkk", "label": "น่าน → กรุงเทพ",  "from_name": "น่าน (NNT)",   "to_name": "กรุงเทพ (DMK)"},
    {"key": "BKK_NNT", "from": "bkk", "to": "nnt", "label": "กรุงเทพ → น่าน",  "from_name": "กรุงเทพ (DMK)", "to_name": "น่าน (NNT)"},
]

# สายการบินที่สนใจ (ข้อความบนหน้าเว็บ -> คีย์ของเรา)
AIRLINES = {
    "Thai AirAsia": "airasia",
    "AirAsia":      "airasia",
    "Nokair":       "nokair",
    "Nok Air":      "nokair",
}

# ป้ายโปรโมชั่นที่หน้าเว็บใช้
PROMO_WORDS = ["ราคาพิเศษ", "สุดคุ้ม", "บินตรงราคาถูกสุด", "ดีลพิเศษ"]

FLIGHT_RE = re.compile(
    r"(Thai AirAsia|AirAsia|Nokair|Nok Air)\s*\n"      # สายการบิน
    r"(\d{1,2}:\d{2})\s*\n"                            # เวลาออก
    r"([A-Z]{3})\s*\n"                                 # สนามบินต้นทาง
    r"[\s\S]{0,120}?"                                  # ระยะเวลา/เที่ยวบินตรง
    r"(\d{1,2}:\d{2})\s*\n"                            # เวลาถึง
    r"([A-Z]{3})\s*\n"                                 # สนามบินปลายทาง
    r"[\s\S]{0,60}?"                                   # terminal ฯลฯ
    r"฿\s?([\d,]+)"                                    # ราคา
)


def search_url(frm, to, date_iso):
    return (f"https://th.trip.com/flights/showfarefirst?dcity={frm}&acity={to}"
            f"&ddate={date_iso}&triptype=ow&class=y&quantity=1&locale=th-TH&curr=THB")


def parse_page_text(txt):
    """ดึงเที่ยวบินของ AirAsia/NokAir จากข้อความบนหน้า -> ราคาถูกสุดต่อสายการบิน"""
    best = {}
    for m in FLIGHT_RE.finditer(txt):
        name, dep, dep_ap, arr, arr_ap, price = m.groups()
        key = AIRLINES.get(name.strip())
        if not key:
            continue
        try:
            baht = int(price.replace(",", ""))
        except ValueError:
            continue
        # ป้ายโปรฯ = ข้อความ 160 ตัวก่อนหน้าชื่อสายการบิน + 60 ตัวหลังราคา
        around = txt[max(0, m.start() - 160): m.end() + 60]
        promos = sorted({w for w in PROMO_WORDS if w in around})
        cur = best.get(key)
        if cur is None or baht < cur["price"]:
            best[key] = {"price": baht, "depart": dep, "arrive": arr,
                         "from": dep_ap, "to": arr_ap, "promos": promos}
    return best


def scrape(days=15, headless=True):
    from playwright.sync_api import sync_playwright
    today = datetime.date.today()
    dates = [(today + datetime.timedelta(days=i)).isoformat() for i in range(days)]
    out = {r["key"]: {"label": r["label"], "from_name": r["from_name"],
                      "to_name": r["to_name"], "days": {}} for r in ROUTES}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="th-TH", user_agent=UA,
                                  viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        for route in ROUTES:
            for d in dates:
                url = search_url(route["from"], route["to"], d)
                found = {}
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    for _ in range(14):                 # รอผลค้นหาขึ้น (สูงสุด ~35 วิ)
                        page.wait_for_timeout(2500)
                        txt = page.evaluate("()=>document.body?document.body.innerText:''")
                        if parse_page_text(txt):
                            break
                    # เลื่อนหน้าลงเพื่อโหลดเที่ยวบินให้ครบ (ไม่งั้นจะเห็นแค่ 2-3 เที่ยวแรก
                    # ทำให้พลาดสายการบินที่ถูกกว่า เช่น Nok Air)
                    for _ in range(6):
                        page.evaluate("()=>window.scrollTo(0,document.body.scrollHeight)")
                        page.wait_for_timeout(1200)
                    txt = page.evaluate("()=>document.body?document.body.innerText:''")
                    found = parse_page_text(txt)
                except Exception as e:
                    print(f"   [warn] {route['key']} {d}: {type(e).__name__}")
                out[route["key"]]["days"][d] = found
                got = ", ".join(f"{k}={v['price']}" for k, v in found.items()) or "-"
                print(f"  {route['key']} {d}: {got}")
        browser.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=15)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    routes = scrape(days=args.days)
    total = sum(1 for r in routes.values() for d in r["days"].values() if d)
    print(f">> got fares for {total} route-days")
    if total == 0:
        print("!! no fares found - Trip.com may have blocked this run")
        sys.exit(1)

    data = {
        "updated": datetime.datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "Trip.com (th)",
        "routes": routes,
    }
    FLIGHTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> wrote {FLIGHTS_JSON.name} @ {data['updated']}")

    if args.no_push:
        return
    try:
        subprocess.run(["git", "-C", str(REPO_DIR), "add", "flights.json"], check=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["git", "-C", str(REPO_DIR), "commit", "-m",
                        f"Update flight prices {data['updated']}"], check=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["git", "-C", str(REPO_DIR), "push", "origin", "main"], check=True, creationflags=CREATE_NO_WINDOW)
        print(">> pushed to GitHub Pages.")
    except subprocess.CalledProcessError as e:
        print(f"(git) {e}")


if __name__ == "__main__":
    main()
