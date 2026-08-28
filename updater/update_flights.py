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
STRIP_STEP = 13   # ยิงแถบปฏิทินทุกกี่วัน (1 หน้าครอบ ~14 วัน)
GF_DAYS    = 30   # เติมชื่อสายการบินจาก Google Flights กี่วันแรก (ทั้ง 90 วันจะช้าเกินรอบ)
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
    # Google Flights แสดงชื่อเป็นภาษาไทย
    "แอร์เอเชีย":        ("airasia",    "Thai AirAsia"),
    "ไทยแอร์เอเชีย":     ("airasia",    "Thai AirAsia"),
    "นกแอร์":            ("nokair",     "Nok Air"),
    "ไทยเวียตเจ็ท":      ("vietjet",    "Thai Vietjet"),
    "เวียตเจ็ท":         ("vietjet",    "Thai Vietjet"),
    "ไทยไลอ้อนแอร์":     ("lionair",    "Thai Lion Air"),
    "ไลอ้อนแอร์":        ("lionair",    "Thai Lion Air"),
    "การบินไทย":         ("thai",       "Thai Airways"),
    "บางกอกแอร์เวย์ส":   ("bangkokair", "Bangkok Airways"),
    "บางกอกแอร์เวย์":    ("bangkokair", "Bangkok Airways"),
}
# สนามบินหลักของแต่ละเมือง ใช้กับ Google Flights ที่ต้องระบุสนามบินตรงๆ
GF_AIRPORT = {"nnt": "NNT", "cnx": "CNX", "kop": "KOP", "bkk": "DMK"}

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


TH_MONTHS = {"ม.ค.":1,"ก.พ.":2,"มี.ค.":3,"เม.ย.":4,"พ.ค.":5,"มิ.ย.":6,
             "ก.ค.":7,"ส.ค.":8,"ก.ย.":9,"ต.ค.":10,"พ.ย.":11,"ธ.ค.":12}
STRIP_RE = re.compile(
    r"(?:จ|อ|พ|พฤ|ศ|ส|อา)\.\s*(\d{1,2})\s*"
    r"(ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.)\s*\n\s*฿\s*([\d,]+)")


def parse_strip(txt, anchor_date):
    """อ่าน 'แถบปฏิทินราคา' -> {วันที่: ราคาถูกสุด}

    แถบนี้แสดงราคาต่ำสุดของแต่ละวันรอบๆ วันที่ค้นหา (ครั้งละ ~14 วัน)
    ตัวเลขในแถบไม่มีปี จึงเดาปีจากวันที่ที่ใช้ค้นหา
    """
    out = {}
    a = datetime.date.fromisoformat(anchor_date)
    for day, mon, price in STRIP_RE.findall(txt):
        m = TH_MONTHS[mon]
        for y in (a.year, a.year + 1, a.year - 1):      # เลือกปีที่ใกล้วันค้นหาที่สุด
            try:
                d = datetime.date(y, m, int(day))
            except ValueError:
                continue
            if abs((d - a).days) <= 30:
                out[d.isoformat()] = int(price.replace(",", ""))
                break
    return out


GF_ROW_RE = re.compile(
    r"(\d{1,2}:\d{2})\s*\n\s*[–-]\s*\n\s*(\d{1,2}:\d{2})\s*\n"      # เวลาออก-ถึง
    r"(.{0,60}?)\n"                                                        # ชื่อสายการบิน
    r"(\d+)\s*ชม\.\s*(?:(\d+)\s*นาที)?\s*\n"                            # ระยะเวลา
    r"([A-Z]{3})[–-]([A-Z]{3})\s*\n"                                       # เส้นทาง
    r"(.{0,120}?)฿\s*([\d,]+)", re.S)                                      # ... ราคา


def parse_google(txt, frm, to):
    """อ่านผล Google Flights -> ราคาถูกสุดของแต่ละสายการบิน (โครงเดียวกับ parse_page_text)"""
    ok_from, ok_to = CITY_AIRPORTS.get(frm, set()), CITY_AIRPORTS.get(to, set())
    best = {}
    for m in GF_ROW_RE.finditer(txt):
        dep, arr, raw, hh, mm, dep_ap, arr_ap, mid, price = m.groups()
        if ok_from and dep_ap not in ok_from:  continue
        if ok_to   and arr_ap not in ok_to:    continue
        if int(hh) * 60 + int(mm or 0) > MAX_MINUTES: continue
        if "บินตรง" not in mid and "nonstop" not in mid.lower(): continue   # เอาเฉพาะบินตรง
        air = airline_of(raw)
        if not air: continue
        key, name = air
        try:
            baht = int(price.replace(",", ""))
        except ValueError:
            continue
        cur = best.get(key)
        if cur is None or baht < cur["price"]:
            best[key] = {"airline": key, "name": name, "price": baht,
                         "depart": dep, "arrive": arr,
                         "from": dep_ap, "to": arr_ap, "promos": [],
                         "src": "google"}
    return best


def google_url(frm, to, d):
    a, b = GF_AIRPORT.get(frm, frm.upper()), GF_AIRPORT.get(to, to.upper())
    return ("https://www.google.com/travel/flights?hl=th&gl=TH&curr=THB"
            f"&q=Flights%20from%20{a}%20to%20{b}%20on%20{d}%20oneway")


async def dismiss_consent(page):
    """ปิดแบนเนอร์คุกกี้ของ Trip.com — เลือก "ปฏิเสธทั้งหมด" เพื่อไม่ให้ตามเก็บข้อมูล

    ตั้งแต่ปลายเดือน ส.ค. 2026 Trip.com ขึ้นแบนเนอร์นี้คลุมหน้าไว้
    ถ้าไม่ปิด ผลการค้นหาจะไม่ถูกเรนเดอร์เลย (หน้าเหลือแต่เนื้อหาโฆษณา)
    """
    for sel in ('button:has-text("ปฏิเสธทั้งหมด")',
                'button:has-text("Reject all")',
                '[data-testid="reject-all"]',
                '#onetrust-reject-all-handler'):
        try:
            btn = page.locator(sel).first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=3000)
                await page.wait_for_timeout(600)
                return True
        except Exception:
            pass
    return False


async def _grab(page, route, d):
    """โหลดหน้าค้นหาของ 1 เส้นทาง 1 วัน แล้วคืน 4 อันดับถูกสุด"""
    frm, to = route["from"], route["to"]
    await page.goto(search_url(frm, to, d), wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1200)
    await dismiss_consent(page)               # ไม่ปิดแบนเนอร์ = ไม่มีผลค้นหาให้อ่าน
    for _ in range(14):                       # รอผลค้นหาขึ้น (สูงสุด ~35 วิ)
        await page.wait_for_timeout(2500)
        txt = await page.evaluate("()=>document.body?document.body.innerText:''")
        if parse_page_text(txt, frm, to):
            break
        await dismiss_consent(page)           # เผื่อแบนเนอร์เพิ่งโผล่
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


async def _grab_strip(page, route, anchor):
    """โหลดหน้า Trip.com 1 ครั้ง -> ราคาถูกสุด ~14 วันรอบวันที่ anchor"""
    await page.goto(search_url(route["from"], route["to"], anchor),
                    wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1500)
    await dismiss_consent(page)
    for _ in range(6):
        await page.wait_for_timeout(2000)
        txt = await page.evaluate("()=>document.body?document.body.innerText:''")
        got = parse_strip(txt, anchor)
        if len(got) >= 5:
            return got
    return parse_strip(txt, anchor)


async def _grab_google(page, route, d):
    """โหลด Google Flights 1 วัน -> ราคาถูกสุดของแต่ละสายการบิน"""
    await page.goto(google_url(route["from"], route["to"], d),
                    wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1800)
    await dismiss_consent(page)
    for _ in range(6):
        await page.wait_for_timeout(2200)
        txt = await page.evaluate("()=>document.body?document.body.innerText:''")
        best = parse_google(txt, route["from"], route["to"])
        if best:
            return best
    return {}


def merge_day(strip_price, google_best):
    """รวม 2 แหล่ง -> รายการ 4 อันดับ ถูกสุดอยู่หน้าสุด

    Google ให้ชื่อสายการบิน ส่วนแถบปฏิทินของ Trip.com มักถูกกว่าแต่ไม่บอกสายการบิน
    ถ้าราคาจากแถบถูกกว่าทุกสายการบินที่ Google เห็น ให้ใส่เป็นอันดับ 1 แยกไว้
    """
    fares = sorted(google_best.values(), key=lambda f: f["price"])
    if strip_price:
        cheapest_known = fares[0]["price"] if fares else None
        if cheapest_known is None or strip_price < cheapest_known:
            fares.insert(0, {"airline": "tripcom", "name": "ถูกสุดบน Trip.com",
                             "price": strip_price, "depart": "", "arrive": "",
                             "from": "", "to": "", "promos": [], "src": "trip"})
    return fares[:TOP_N]


async def _scrape_async(days, only, workers, headless=True):
    """2 รอบ: (1) แถบปฏิทิน Trip.com ครอบทุกวัน  (2) Google Flights เติมสายการบิน"""
    from playwright.async_api import async_playwright
    today = datetime.date.today()
    dates = [(today + datetime.timedelta(days=i)).isoformat() for i in range(days)]
    todo  = [r for r in ROUTES if not only or r["key"] in only]
    out = {r["key"]: {"label": r["label"], "from_name": r["from_name"],
                      "to_name": r["to_name"], "days": {}} for r in todo}

    # วันที่ใช้ยิงแถบปฏิทิน: ห่างกัน STRIP_STEP วัน (1 หน้าครอบ ~14 วัน จึงเหลื่อมกันเล็กน้อย)
    anchors = {r["key"]: dates[STRIP_STEP // 2::STRIP_STEP] for r in todo}
    gf_days = min(GF_DAYS, days)

    strip_jobs = asyncio.Queue()
    for r in todo:
        for a in anchors[r["key"]]:
            strip_jobs.put_nowait((r, a))
    gf_jobs = asyncio.Queue()
    for r in todo:
        for d in dates[:gf_days]:
            gf_jobs.put_nowait((r, d))

    strips = {r["key"]: {} for r in todo}     # {route: {date: price}}
    googles = {r["key"]: {} for r in todo}    # {route: {date: {airline: fare}}}
    n_strip, n_gf = strip_jobs.qsize(), gf_jobs.qsize()
    done = [0]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        async def run_queue(q, kind, total):
            ctx = await browser.new_context(locale="th-TH", user_agent=UA,
                                            viewport={"width": 1400, "height": 1100})
            page = await ctx.new_page()
            while True:
                try:
                    route, d = q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    if kind == "strip":
                        got = await _grab_strip(page, route, d)
                        strips[route["key"]].update(got)
                        info = f"{len(got)} days"
                    else:
                        got = await _grab_google(page, route, d)
                        googles[route["key"]][d] = got
                        info = ", ".join(f"{f['name']}={f['price']}" for f in got.values()) or "-"
                except Exception as e:
                    info = f"[warn] {type(e).__name__}"
                done[0] += 1
                print(f"  [{done[0]:>3}/{total}] {kind:<6} {route['key']} {d}: {info}", flush=True)
            await ctx.close()

        print(f">> รอบที่ 1: แถบปฏิทิน Trip.com  ({n_strip} หน้า ครอบ {days} วัน)")
        done[0] = 0
        await asyncio.gather(*[run_queue(strip_jobs, "strip", n_strip)
                               for _ in range(max(1, workers))])

        print(f">> รอบที่ 2: Google Flights เติมสายการบิน  ({n_gf} หน้า = {gf_days} วันแรก)")
        done[0] = 0
        await asyncio.gather(*[run_queue(gf_jobs, "google", n_gf)
                               for _ in range(max(1, workers))])

        await browser.close()

    for r in todo:
        k = r["key"]
        for d in dates:
            out[k]["days"][d] = merge_day(strips[k].get(d), googles[k].get(d, {}))
        out[k]["days"] = {d: out[k]["days"][d] for d in sorted(out[k]["days"])}
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
