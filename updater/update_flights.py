#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ITH Flight Price Watch - auto updater (Nan / Chiang Mai <-> Bangkok)
--------------------------------------------------------------------
ดึงราคาตั๋วเครื่องบินถูกสุดของ "ทุกสายการบิน" ที่บินเส้นทาง
น่าน (NNT) / เชียงใหม่ (CNX) / นครพนม (KOP) <-> กรุงเทพ (DMK/BKK)
ล่วงหน้า 90 วัน (3 เดือน) จาก Trip.com เก็บ 4 อันดับที่ถูกที่สุดของแต่ละวัน
(อันดับละ 1 สายการบิน) แล้วเขียน flights.json + push ขึ้น GitHub Pages

รัน:  python update_flights.py                          (ปกติ - Task Scheduler ทุก 12 ชม.)
      python update_flights.py --days 2                 (ทดสอบเร็ว)
      python update_flights.py --routes CNX_BKK,BKK_CNX (อัปเดตเฉพาะบางเส้นทาง - เส้นทางอื่นคงข้อมูลเดิม)
"""
import json, os, re, sys, time, asyncio, subprocess, datetime, pathlib, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_DIR     = pathlib.Path(__file__).resolve().parent.parent
FLIGHTS_JSON = REPO_DIR / "flights.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TOP_N = 4          # เก็บกี่อันดับต่อวัน (1 สายการบิน = 1 อันดับ)
WORKERS = 5        # เปิดกี่หน้าพร้อมกัน (540 หน้าแบบเรียงทีละหน้าใช้ ~2.5 ชม. ซึ่งนานเกิน
                   # กว่ารอบอัปเดตทุก 2 ชม. จะไล่ทัน)
LOCK = pathlib.Path(__file__).resolve().parent / ".update_flights.lock"
LOCK_STALE_SEC = 3 * 3600      # ล็อกเก่ากว่านี้ถือว่าค้าง ให้รันทับได้

# เส้นทางที่ติดตาม
ROUTES = [
    {"key": "NNT_BKK", "from": "nnt", "to": "bkk", "label": "น่าน → กรุงเทพ",      "from_name": "น่าน (NNT)",        "to_name": "กรุงเทพ (DMK/BKK)"},
    {"key": "BKK_NNT", "from": "bkk", "to": "nnt", "label": "กรุงเทพ → น่าน",      "from_name": "กรุงเทพ (DMK/BKK)", "to_name": "น่าน (NNT)"},
    {"key": "CNX_BKK", "from": "cnx", "to": "bkk", "label": "เชียงใหม่ → กรุงเทพ", "from_name": "เชียงใหม่ (CNX)",   "to_name": "กรุงเทพ (DMK/BKK)"},
    {"key": "BKK_CNX", "from": "bkk", "to": "cnx", "label": "กรุงเทพ → เชียงใหม่", "from_name": "กรุงเทพ (DMK/BKK)", "to_name": "เชียงใหม่ (CNX)"},
    {"key": "KOP_BKK", "from": "kop", "to": "bkk", "label": "นครพนม → กรุงเทพ",   "from_name": "นครพนม (KOP)",      "to_name": "กรุงเทพ (DMK/BKK)"},
    {"key": "BKK_KOP", "from": "bkk", "to": "kop", "label": "กรุงเทพ → นครพนม",   "from_name": "กรุงเทพ (DMK/BKK)", "to_name": "นครพนม (KOP)"},
]

# รหัสเมืองบน Trip.com -> สนามบินที่ยอมรับ (กรุงเทพมี 2 สนามบิน)
CITY_AIRPORTS = {"nnt": {"NNT"}, "cnx": {"CNX"}, "kop": {"KOP"}, "bkk": {"BKK", "DMK"}}

# ชื่อสายการบินบนหน้าเว็บ (ตัวพิมพ์เล็ก) -> (คีย์สำหรับโลโก้, ชื่อที่แสดง)
AIRLINES = {
    "thai airasia":     ("airasia",    "Thai AirAsia"),
    "thai airasia x":   ("airasia",    "Thai AirAsia X"),
    "airasia":          ("airasia",    "AirAsia"),
    "nokair":           ("nokair",     "Nok Air"),
    "nok air":          ("nokair",     "Nok Air"),
    "thai vietjet air": ("vietjet",    "Thai Vietjet"),
    "vietjet air":      ("vietjet",    "Vietjet Air"),
    "thai lion air":    ("lionair",    "Thai Lion Air"),
    "lion air":         ("lionair",    "Lion Air"),
    "thai airways":     ("thai",       "Thai Airways"),
    "thai smile":       ("thai",       "Thai Smile"),
    "bangkok airways":  ("bangkokair", "Bangkok Airways"),
}

# เที่ยวบินตรงในเส้นทางพวกนี้ใช้เวลา ~1 ชม. 10-35 นาที ถ้ายาวกว่านี้มากแปลว่าเป็น
# เที่ยวบินต่อเครื่องที่บังเอิญต้นทาง-ปลายทางตรงกัน (เช่น กทม.->ย่างกุ้ง->เชียงใหม่ 15 ชม.)
MAX_MINUTES = 240

# ตัวแทนออกตั๋ว ไม่ใช่สายการบินที่ทำการบินเอง - ไม่เอามาแสดง
SKIP_AIRLINES = {"hahn air systems", "hahn air", "trip.com"}

# ป้ายโปรโมชั่นที่หน้าเว็บใช้
PROMO_WORDS = ["ราคาพิเศษ", "สุดคุ้ม", "บินตรงราคาถูกสุด", "ดีลพิเศษ"]

# โครงสร้างการ์ดเที่ยวบินบนหน้า Trip.com:
#   ชื่อสายการบิน / เวลาออก / สนามบินต้นทาง / ... / เวลาถึง / สนามบินปลายทาง / ... / ราคา
FLIGHT_RE = re.compile(
    r"^([A-Z][A-Za-z0-9.'&/-]*(?: [A-Za-z0-9.'&/-]+){0,4})\n"   # สายการบิน (ขึ้นต้นบรรทัด)
    r"(\d{1,2}:\d{2})\n"                                        # เวลาออก
    r"([A-Z]{3})\n"                                             # สนามบินต้นทาง
    r"[\s\S]{0,140}?"                                           # ระยะเวลา / เที่ยวบินตรง
    r"(\d{1,2}:\d{2})\n"                                        # เวลาถึง
    r"([A-Z]{3})\n"                                             # สนามบินปลายทาง
    r"[\s\S]{0,80}?"                                            # terminal / +1 ฯลฯ
    r"฿\s?([\d,]+)",                                            # ราคา
    re.M)


def search_url(frm, to, date_iso):
    return (f"https://th.trip.com/flights/showfarefirst?dcity={frm}&acity={to}"
            f"&ddate={date_iso}&triptype=ow&class=y&quantity=1&locale=th-TH&curr=THB")


def leg_minutes(dep, arr):
    """ระยะเวลาบินเป็นนาที (เผื่อกรณีถึงหลังเที่ยงคืน)"""
    dh, dm = (int(x) for x in dep.split(":"))
    ah, am = (int(x) for x in arr.split(":"))
    return ((ah * 60 + am) - (dh * 60 + dm)) % 1440


def airline_of(raw):
    """ชื่อบนหน้าเว็บ -> (คีย์, ชื่อที่แสดง) ; None ถ้าไม่ใช่สายการบินที่ทำการบิน"""
    name = raw.strip()
    low = name.lower()
    if low in SKIP_AIRLINES:
        return None
    if low in AIRLINES:
        return AIRLINES[low]
    # สายการบินที่ยังไม่รู้จัก - ใช้ชื่อตามหน้าเว็บ ทำคีย์จากชื่อ
    key = re.sub(r"[^a-z0-9]+", "", low)
    return (key, name) if key else None


def parse_page_text(txt, frm, to):
    """อ่านเที่ยวบินทั้งหน้า -> ราคาถูกสุดของแต่ละสายการบิน"""
    ok_from = CITY_AIRPORTS.get(frm, set())
    ok_to   = CITY_AIRPORTS.get(to, set())
    best = {}
    for m in FLIGHT_RE.finditer(txt):
        raw, dep, dep_ap, arr, arr_ap, price = m.groups()
        # กันเที่ยวบินต่อเครื่อง / การ์ดอื่นบนหน้า: ต้นทาง-ปลายทางต้องตรงเส้นทางนี้
        if ok_from and dep_ap not in ok_from:
            continue
        if ok_to and arr_ap not in ok_to:
            continue
        if leg_minutes(dep, arr) > MAX_MINUTES:      # เที่ยวบินต่อเครื่อง ไม่ใช่บินตรง
            continue
        air = airline_of(raw)
        if not air:
            continue
        key, name = air
        try:
            baht = int(price.replace(",", ""))
        except ValueError:
            continue
        # ป้ายโปรฯ = ข้อความ 160 ตัวก่อนชื่อสายการบิน + 60 ตัวหลังราคา
        around = txt[max(0, m.start() - 160): m.end() + 60]
        promos = sorted({w for w in PROMO_WORDS if w in around})
        cur = best.get(key)
        if cur is None or baht < cur["price"]:
            best[key] = {"airline": key, "name": name, "price": baht,
                         "depart": dep, "arrive": arr,
                         "from": dep_ap, "to": arr_ap, "promos": promos}
    return best


def top_fares(best, n=TOP_N):
    """เรียงถูก -> แพง เอา n อันดับแรก (สายการบินละ 1)"""
    return sorted(best.values(), key=lambda f: f["price"])[:n]


async def _grab(page, route, d):
    """โหลดหน้าค้นหาของ 1 เส้นทาง 1 วัน แล้วคืน 4 อันดับถูกสุด"""
    frm, to = route["from"], route["to"]
    await page.goto(search_url(frm, to, d), wait_until="domcontentloaded", timeout=60000)
    for _ in range(14):                       # รอผลค้นหาขึ้น (สูงสุด ~35 วิ)
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("()=>document.body?document.body.innerText:''")
        if parse_page_text(txt, frm, to):
            break
    # เลื่อนหน้าลงจนสุดเพื่อโหลดเที่ยวบินให้ครบ เส้นทางที่มีสายการบินเยอะ
    # อย่าง CNX-BKK ต้องเลื่อนหลายรอบกว่าเที่ยวบินราคาถูกจะโผล่ครบ
    best = await _scroll_and_parse(page, frm, to)
    if len(best) < 3:                         # ยังเห็นน้อย -> เลื่อนต่ออีกชุด
        more = await _scroll_and_parse(page, frm, to, rounds=12)
        for k, v in more.items():
            if k not in best or v["price"] < best[k]["price"]:
                best[k] = v
    return top_fares(best)


async def _scroll_and_parse(page, frm, to, rounds=20, settle=2):
    """เลื่อนหน้าลงจนความสูงไม่เพิ่มแล้ว (หรือครบ rounds) แล้วอ่านผลทั้งหน้า"""
    last_h, stable = -1, 0
    for _ in range(rounds):
        await page.evaluate("()=>window.scrollTo(0,document.body.scrollHeight)")
        await page.wait_for_timeout(1100)
        h = await page.evaluate("()=>document.body?document.body.scrollHeight:0")
        stable = stable + 1 if h == last_h else 0
        last_h = h
        if stable >= settle:                  # ความสูงนิ่งแล้ว = โหลดครบ
            break
    txt = await page.evaluate("()=>document.body?document.body.innerText:''")
    return parse_page_text(txt, frm, to)


async def _scrape_async(days, only, workers, headless=True):
    from playwright.async_api import async_playwright
    today = datetime.date.today()
    dates = [(today + datetime.timedelta(days=i)).isoformat() for i in range(days)]
    todo  = [r for r in ROUTES if not only or r["key"] in only]
    out = {r["key"]: {"label": r["label"], "from_name": r["from_name"],
                      "to_name": r["to_name"], "days": {}} for r in todo}

    jobs = asyncio.Queue()
    for route in todo:
        for d in dates:
            jobs.put_nowait((route, d))
    total = jobs.qsize()
    done = [0]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        async def worker(n):
            # แต่ละ worker ใช้ context ของตัวเอง จะได้ไม่แย่ง cookie/สถานะกัน
            ctx = await browser.new_context(locale="th-TH", user_agent=UA,
                                            viewport={"width": 1400, "height": 1000})
            page = await ctx.new_page()
            while True:
                try:
                    route, d = jobs.get_nowait()
                except asyncio.QueueEmpty:
                    break
                fares = []
                try:
                    fares = await _grab(page, route, d)
                except Exception as e:
                    print(f"   [warn] {route['key']} {d}: {type(e).__name__}")
                out[route["key"]]["days"][d] = fares
                done[0] += 1
                got = ", ".join(f"{f['name']}={f['price']}" for f in fares) or "-"
                print(f"  [{done[0]:>3}/{total}] {route['key']} {d}: {got}", flush=True)
            await ctx.close()

        await asyncio.gather(*[worker(i) for i in range(max(1, workers))])
        await browser.close()

    for r in out.values():                    # ให้วันเรียงตามลำดับเสมอ
        r["days"] = {d: r["days"][d] for d in sorted(r["days"])}
    return out


def scrape(days=90, headless=True, only=None, workers=WORKERS):
    return asyncio.run(_scrape_async(days, only, workers, headless))


def acquire_lock():
    """กันไม่ให้รอบใหม่เริ่มทับรอบเดิมที่ยังทำงานอยู่ (รอบเต็มนานกว่าช่วงตั้งเวลา)"""
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < LOCK_STALE_SEC:
            print(f"!! another run started {int(age/60)} min ago - skipping this one")
            return False
        print(f"(warn) stale lock ({int(age/60)} min old) - taking over")
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock():
    try:
        LOCK.unlink()
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--routes", default="",
                    help="อัปเดตเฉพาะเส้นทางนี้ คั่นด้วย , เช่น CNX_BKK,BKK_CNX (ว่าง = ทุกเส้นทาง)")
    ap.add_argument("--workers", type=int, default=WORKERS,
                    help=f"เปิดกี่หน้าพร้อมกัน (ค่าเริ่มต้น {WORKERS})")
    ap.add_argument("--no-lock", action="store_true", help="ข้ามการเช็คล็อกกันรันซ้อน")
    args = ap.parse_args()

    only = [k.strip() for k in args.routes.split(",") if k.strip()] or None
    if only:
        valid = {r["key"] for r in ROUTES}
        bad = [k for k in only if k not in valid]
        if bad:
            print(f"!! unknown route key(s): {', '.join(bad)} (valid: {', '.join(sorted(valid))})")
            sys.exit(2)

    if not args.no_lock and not acquire_lock():
        sys.exit(0)
    t0 = time.time()
    try:
        fresh = scrape(days=args.days, only=only, workers=args.workers)
    finally:
        if not args.no_lock:
            release_lock()
    print(f">> scraped in {int(time.time()-t0)//60} min {int(time.time()-t0)%60} s "
          f"({args.workers} workers)")
    total = sum(1 for r in fresh.values() for d in r["days"].values() if d)
    print(f">> got fares for {total} route-days")
    if total == 0:
        print("!! no fares found - Trip.com may have blocked this run")
        sys.exit(1)

    # ถ้าอัปเดตแค่บางเส้นทาง ให้คงข้อมูลเดิมของเส้นทางที่ไม่ได้ดึงไว้
    prev = {}
    if FLIGHTS_JSON.exists():
        try:
            prev = json.loads(FLIGHTS_JSON.read_text(encoding="utf-8")).get("routes", {})
        except Exception as e:
            print(f"(warn) cannot read existing flights.json: {type(e).__name__}")

    routes = {}
    for r in ROUTES:                       # เรียงตามลำดับ ROUTES เสมอ
        k = r["key"]
        if k in fresh:
            routes[k] = fresh[k]
        elif k in prev:
            routes[k] = prev[k]

    data = {
        "updated": datetime.datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "Trip.com (th)",
        "top_n": TOP_N,
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
