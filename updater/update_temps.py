#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ITH Bearing Pulley Temp — auto updater  (socket.io first)
---------------------------------------------------------
ดึงค่าอุณหภูมิกลุ่ม SPD จากระบบ Primus แล้วเขียนทับ temps.json + push ขึ้น GitHub
ให้หน้า dashboard ออนไลน์อัปเดตเอง

วิธีทำงาน (ใหม่):
  - เปิด Chromium แบบจำ session (persistent profile) แบบซ่อนนอกจอ
  - **อ่านค่าจาก socket.io โดยตรง** (event `update_tag_value`, port=1 = ค่าจริง)
    → ทำงานได้แม้หน้าเว็บจะขึ้น 403 / session หมดอายุ ซึ่งทนทานกว่าการ scrape DOM มาก
  - ถ้า socket ไม่มีค่า ค่อย fallback ไปอ่าน DOM (วิธีเดิม)
  - เขียนทับ temps.json แล้ว git push -> GitHub Pages

โหมด:
  python update_temps.py            # รันปกติ (สำหรับ Task Scheduler)
  python update_temps.py --login    # เปิดหน้าจอให้ล็อกอินใหม่ (เมื่อ session ตายจริง)
"""

import json, os, sys, subprocess, datetime, pathlib

# บังคับ stdout/stderr เป็น UTF-8 กัน UnicodeEncodeError บน Windows console
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---- ตั้งค่า ----
BASE_URL = "https://primus.ith.co.th/"
SPD_URL = ("https://primus.ith.co.th/home?factory_id=68c1024abea6aa0b8ca1c61e"
           "&line_id=6a7e7140c6b59a2f0084246a&dashboard_name=SPD")
REPO_DIR   = pathlib.Path(__file__).resolve().parent.parent   # โฟลเดอร์ repo (มี temps.json)
TEMPS_JSON = REPO_DIR / "temps.json"
# เก็บ session ไว้ที่ path ภาษาอังกฤษล้วน (Chromium บน Windows เปิด user-data-dir ที่มีอักษรไทยไม่ได้)
PROFILE_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home()))) / "ith_primus_profile"
CREDS_FILE  = pathlib.Path(__file__).resolve().parent / "credentials.txt"  # เก็บ user/pass (gitignored)
TZ = datetime.timezone(datetime.timedelta(hours=7))  # เวลาไทย
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # กันหน้าต่าง console เด้งตอน git ทำงาน

# ลำดับการ์ด + สี (ยึดตาม Primus SPD dashboard: 7 คู่ bearing = 14 การ์ด)
SPD_TAGS = [
    "DCV_TC_L", "DCV_TC_R",
    "BEND_L", "BEND_R",
    "TAKE_UP_L", "TAKE_UP_R",
    "RCV_DE_L", "RCV_DE_R",
    "RCV_NDE_L", "RCV_NDE_R",
    "DCV_DE_L", "DCV_DE_R",
    "DCV_NDE_L", "DCV_NDE_R",
]
SPD_TAG_SET = set(SPD_TAGS)

# BWE1 / BWE2 -- ชื่อ tag ในระบบ Primus มี prefix กลุ่มติดมาแล้ว (BWE1_*, BWE2_*) จึงไม่ชนกับ SPD
# หมายเหตุ: กล่อง "CVW" บนแผนภาพ = tag "WCV" ในระบบ Primus (จุดวัดเดียวกัน สลับตัวอักษร)
BWE_BASES = ["DE_WCV", "NDE_WCV", "DE_DCV", "NDE_DCV"]


def _bwe_tags(group):
    return [f"{group}_{base}_{side}" for base in BWE_BASES for side in ("L", "R")]


BWE1_TAGS = _bwe_tags("BWE1")
BWE2_TAGS = _bwe_tags("BWE2")

# ลำดับกลุ่มที่จะเขียนลง temps.json (หน้าเว็บอ่านตามนี้)
GROUP_TAGS = {"SPD": SPD_TAGS, "BWE1": BWE1_TAGS, "BWE2": BWE2_TAGS}
WANTED_TAGS = set(SPD_TAGS) | set(BWE1_TAGS) | set(BWE2_TAGS)

TAG_COLORS = {
    "DCV_TC_L": "#008000",  "DCV_TC_R": "#008000",   # เขียวเข้ม
    "BEND_L":   "#f8e71c",  "BEND_R":   "#f8e71c",   # เหลือง
    "TAKE_UP_L":"#7ed321",  "TAKE_UP_R":"#7ed321",   # เขียวอ่อน
    "RCV_DE_L": "#f5a623",  "RCV_DE_R": "#f5a623",   # ส้ม
    "RCV_NDE_L":"#4a90e2",  "RCV_NDE_R":"#4a90e2",   # น้ำเงิน
    "DCV_DE_L": "#50e3c2",  "DCV_DE_R": "#50e3c2",   # เขียวมิ้นต์
    "DCV_NDE_L":"#9b9b9b",  "DCV_NDE_R":"#9b9b9b",   # เทา
}
# สีหัวการ์ดของ BWE บน Primus (ใช้เป็นจุดสีในหน้าตาราง)
for _side in ("L", "R"):
    TAG_COLORS[f"BWE1_DE_WCV_{_side}"]  = "#c00000"   # แดงเลือดหมู
    TAG_COLORS[f"BWE1_NDE_WCV_{_side}"] = "#4a90e2"   # น้ำเงิน
    TAG_COLORS[f"BWE1_DE_DCV_{_side}"]  = "#404040"   # เทาเข้ม
    TAG_COLORS[f"BWE1_NDE_DCV_{_side}"] = "#8cc63e"   # เขียวมะนาว
    TAG_COLORS[f"BWE2_DE_WCV_{_side}"]  = "#2e7d32"   # เขียวเข้ม
    TAG_COLORS[f"BWE2_NDE_WCV_{_side}"] = "#e6d800"   # เหลือง
    TAG_COLORS[f"BWE2_DE_DCV_{_side}"]  = "#cc00cc"   # ม่วงบานเย็น
    TAG_COLORS[f"BWE2_NDE_DCV_{_side}"] = "#8b5a2b"   # น้ำตาล

# JS ติดตั้งตอนโหลดหน้า: หลอกว่าหน้า visible + ดักเฟรม socket.io (update_tag_value)
INIT_JS = r"""
Object.defineProperty(document,'hidden',{get:()=>false,configurable:true});
Object.defineProperty(document,'visibilityState',{get:()=>'visible',configurable:true});
Object.defineProperty(document,'webkitVisibilityState',{get:()=>'visible',configurable:true});
document.hasFocus=()=>true;
window.__frames = [];
(function(){
  const keep = (s)=>{ try{ if(typeof s==='string' && /update_tag_value/.test(s)){ if(window.__frames.length<300) window.__frames.push(s.slice(0,200000)); } }catch(e){} };
  const OW = window.WebSocket;
  function W(u,p){ const ws = (p!==undefined)? new OW(u,p) : new OW(u); try{ws.addEventListener('message', e=>keep(typeof e.data==='string'?e.data:''));}catch(e){} return ws; }
  W.prototype = OW.prototype; try{['CONNECTING','OPEN','CLOSING','CLOSED'].forEach(k=>W[k]=OW[k]);}catch(e){}
  window.WebSocket = W;
  const OX = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(){ try{ this.addEventListener('load', ()=>{ try{keep(this.responseText);}catch(e){} }); }catch(e){} return OX.apply(this, arguments); };
})();
"""

# JS อ่านชื่อ tag + ค่า + สี จากการ์ดบน dashboard (วิธี fallback เดิม)
SCRAPE_JS = r"""
() => {
  const out = [];
  const all = [...document.querySelectorAll('*')].filter(e=>e.children.length===0 && e.textContent);
  const items = all.map(e=>({el:e, t:e.textContent.trim(), r:e.getBoundingClientRect()}))
                   .filter(x=>x.t.length>0 && x.r.width>0);
  const names = items.filter(x=>/^[A-Z][A-Z0-9_]{2,}$/.test(x.t));
  const vals  = items.filter(x=>/^-?\d{1,4}(\.\d+)?$/.test(x.t));
  const rgb2hex = (s)=>{ const m=(s||'').match(/\d+/g); if(!m) return null;
    return '#'+m.slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join(''); };
  for (const n of names){
    let best=null, bd=1e9;
    for (const v of vals){
      const dx=Math.abs((v.r.left+v.r.right)/2-(n.r.left+n.r.right)/2);
      const dy=(v.r.top - n.r.top);
      if (dy>0 && dy<220 && dx<180){ const d=dy+dx; if(d<bd){bd=d;best=v;} }
    }
    if (best){
      let color=null, node=n.el;
      for (let i=0;i<4 && node;i++){ const bg=getComputedStyle(node).backgroundColor;
        const hx=rgb2hex(bg); if(hx && bg!=='rgba(0, 0, 0, 0)' && hx!=='#ffffff'){ color=hx; break; }
        node=node.parentElement; }
      out.push({tag:n.t, value:parseFloat(best.t), color});
    }
  }
  return out;
}
"""


def load_credentials():
    """อ่าน user/password จาก credentials.txt (รูปแบบ key=value)"""
    if not CREDS_FILE.exists():
        return None
    creds = {}
    for line in CREDS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        creds[k.strip().lower()] = v.strip()
    if creds.get("username") and creds.get("password"):
        return creds
    return None


def parse_socket_frames(frames):
    """แปลงเฟรม socket.io -> {tag: value} เอาเฉพาะค่าจริงของทุกกลุ่ม (SPD/BWE1/BWE2), ค่าใหม่สุดชนะ

    เฟรมเดียวมีครบทุกเครื่อง แยกด้วย port: 1=SPD, 3=BWE1, 5=BWE2, 999=ตัวจำลอง (_sim) ที่ต้องข้าม
    ชื่อ tag ของ BWE มี prefix กลุ่มอยู่แล้ว จึงกรองด้วยชื่อ tag ได้ตรงๆ ไม่ต้องยึด port
    """
    latest = {}  # tag -> (ts, value)
    for fr in frames:
        i = fr.find('["update_tag_value",')
        if i < 0:
            continue
        try:
            arr = json.loads(fr[i:])
            payload = json.loads(arr[1])
        except Exception:
            continue
        ts = payload.get("ts", 0)
        for dev in payload.get("table", []):
            if str(dev.get("port")) == "999":    # 999 = ตัวจำลอง (_sim) ไม่ใช่ค่าจริง
                continue
            for d in dev.get("data", []):
                name = d.get("name")
                val = d.get("value")
                if name in WANTED_TAGS and val not in (None, ""):
                    try:
                        fval = float(val)
                    except (TypeError, ValueError):
                        continue
                    if name not in latest or ts >= latest[name][0]:
                        latest[name] = (ts, fval)
    return {k: v for k, (t, v) in latest.items()}


def groups_from_socket(vals):
    """จัดค่าที่อ่านได้เข้ากลุ่ม ตามลำดับ+สีมาตรฐานของแต่ละหน้า (กลุ่มที่ไม่มีค่าเลยจะถูกข้าม)"""
    out = {}
    for group, tags in GROUP_TAGS.items():
        cards = [{"tag": t, "value": vals[t], "color": TAG_COLORS[t]}
                 for t in tags if t in vals]
        if cards:
            out[group] = cards
    return out


def enough(vals):
    """ได้ครบพอจะเขียนไฟล์หรือยัง -- SPD ต้องมาเกือบครบ ส่วน BWE ขอทั้งสองเครื่องอย่างน้อยเครื่องละ 6 จุด"""
    have = lambda tags: sum(1 for t in tags if t in vals)
    return have(SPD_TAGS) >= 12 and have(BWE1_TAGS) >= 6 and have(BWE2_TAGS) >= 6


def poll_socket(page, tries=20, interval=2000):
    """รอ+อ่านค่าจาก socket.io จนครบทุกกลุ่ม หรือหมดจำนวนรอบ (เก็บรอบที่ได้มากที่สุดไว้)"""
    best = {}
    for _ in range(tries):
        page.wait_for_timeout(interval)
        try:
            frames = page.evaluate("() => window.__frames || []")
        except Exception:
            frames = []
        vals = parse_socket_frames(frames)
        if len(vals) > len(best):
            best = vals
        if enough(best):
            break
    # ถ้า BWE ยังไม่มา แต่ SPD ครบแล้ว ก็ยังเขียนไฟล์ได้ (ดีกว่าไม่อัปเดตเลย)
    if sum(1 for t in SPD_TAGS if t in best) >= 12:
        return groups_from_socket(best)
    return {}


def poll_cards(page, tries=15, interval=2000):
    """รอ+อ่านการ์ดจาก DOM (fallback) จนได้ >=10 ตัว หรือหมดจำนวนรอบ"""
    for _ in range(tries):
        page.wait_for_timeout(interval)
        try:
            c = page.evaluate(SCRAPE_JS)
            numeric = [x for x in c if isinstance(x.get("value"), (int, float))]
            if len(numeric) >= 10:
                return {"SPD": c}          # วิธีสำรองอ่านได้เฉพาะการ์ดบนหน้า SPD
        except Exception:
            pass
    return {}


def do_login(page, creds):
    """ล็อกอินอัตโนมัติเมื่อเจอหน้า login (หาช่อง user/password เอง)"""
    try:
        pw = page.query_selector('input[type="password"]')
        if not pw:
            return False
        user_el = None
        for sel in ['input[type="text"]', 'input[type="email"]',
                    'input[name*="user" i]', 'input[id*="user" i]',
                    'input[placeholder*="user" i]', 'input[name*="name" i]']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    user_el = el
                    break
            except Exception:
                pass
        if user_el:
            user_el.fill(creds["username"])
        pw.fill(creds["password"])
        clicked = False
        for sel in ['button[type="submit"]', 'input[type="submit"]',
                    'button:has-text("Login")', 'button:has-text("LOGIN")',
                    'button:has-text("Log in")', 'button:has-text("Sign in")',
                    'button:has-text("เข้าสู่ระบบ")']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            try:
                pw.press("Enter")
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"   [login error] {e}")
        return False


def kill_stale_browsers():
    """ฆ่า Chromium ของ Playwright ที่ค้างจากรอบก่อน (ไม่แตะ Chrome ปกติของผู้ใช้)"""
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process chrome,chrome_proxy -ErrorAction SilentlyContinue | "
             "Where-Object { $_.Path -like '*ms-playwright*' } | "
             "Stop-Process -Force -ErrorAction SilentlyContinue"],
            creationflags=CREATE_NO_WINDOW, timeout=20,
        )
    except Exception:
        pass
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        try:
            (PROFILE_DIR / name).unlink()
        except Exception:
            pass


def scrape(login_mode=False):
    from playwright.sync_api import sync_playwright
    kill_stale_browsers()
    with sync_playwright() as p:
        # headed แต่ซ่อนนอกจอ + ปิด occlusion กัน Chrome freeze หน้าที่ถูกบัง (โหมด --login = เปิดให้เห็น)
        norm_args = ["--window-position=-32000,-32000",
                     "--disable-features=CalculateNativeWinOcclusion"]
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=([] if login_mode else norm_args),
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            ctx.add_init_script(INIT_JS)
        except Exception:
            pass

        # ---------- โหมดล็อกอินด้วยมือ ----------
        if login_mode:
            print(">> Opening Primus login page. Please LOG IN by hand if a form appears.")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            creds = load_credentials()
            if creds:
                page.wait_for_timeout(2500)
                if do_login(page, creds):
                    print(">> Tried auto-login with saved credentials...")
                    page.wait_for_timeout(4000)
            page.goto(SPD_URL, wait_until="domcontentloaded", timeout=60000)
            print(">> Waiting up to 5 minutes for live data to appear...")
            ok = False
            for _ in range(150):
                page.wait_for_timeout(2000)
                try:
                    frames = page.evaluate("() => window.__frames || []")
                    vals = parse_socket_frames(frames)
                    if sum(1 for t in SPD_TAGS if t in vals) >= 12:
                        ok = True
                        break
                    cards = page.evaluate(SCRAPE_JS)
                    if len([c for c in cards if isinstance(c.get("value"), (int, float))]) >= 10:
                        ok = True
                        break
                except Exception:
                    pass
            ctx.close()
            print(">> Session saved successfully." if ok else "!! Timeout - data not found. Try again.")
            return ok

        # ---------- โหมดรันปกติ ----------
        page.goto(SPD_URL, wait_until="domcontentloaded", timeout=60000)

        # 1) PRIMARY: อ่านค่าจาก socket.io (ทำงานได้แม้หน้าจะ 403)
        cards = poll_socket(page, tries=20)
        if cards:
            ctx.close()
            return cards

        # 2) FALLBACK: อ่านจาก DOM (ต้องให้หน้า render ได้)
        cards = poll_cards(page, tries=20)

        # 3) ยังไม่ได้ + มี credentials + อยู่หน้า login -> ลอง auto-login แล้วอ่านใหม่ (socket ก่อน)
        if not cards:
            creds = load_credentials()
            has_login = page.query_selector('input[type="password"]') is not None
            if creds and has_login:
                print(">> Session expired - attempting auto-login...")
                if do_login(page, creds):
                    page.wait_for_timeout(3000)
                    cards = poll_socket(page, tries=15) or poll_cards(page, tries=15)
                    print(">> Auto-login OK." if cards else "!! Auto-login failed (check credentials).")
            elif not creds:
                print("!! No credentials.txt found - cannot auto-login.")

        # 4) debug เมื่ออ่านไม่ได้เลย
        if not cards:
            try:
                print(f"   [debug] url: {page.url}")
                print(f"   [debug] title: {page.title()}")
                fc = page.evaluate("() => (window.__frames||[]).length")
                print(f"   [debug] socketFrames={fc}")
            except Exception as e:
                print(f"   [debug err] {e}")
        ctx.close()
        return cards


def main():
    login_mode = "--login" in sys.argv
    result = scrape(login_mode=login_mode)
    if login_mode:
        print(">> Login step done." if result else ">> Login step finished (data not confirmed).")
        return

    groups = result
    if not groups:
        print("!! Could not read values - session may be dead. Run RESET_Dashboard.bat (login step).")
        sys.exit(1)

    groups = {g: [c for c in cards if isinstance(c.get("value"), (int, float))]
              for g, cards in groups.items()}
    groups = {g: cards for g, cards in groups.items() if cards}
    spd_n = len(groups.get("SPD", []))
    if spd_n < 10:
        print(f"!! Only got {spd_n} SPD cards (expected 14) - session may have a problem")
        sys.exit(1)

    data = {
        "updated": datetime.datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "Primus dashboards (socket.io): SPD + BWE1 + BWE2",
        "groups": groups,
    }
    TEMPS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = ", ".join(f"{g}={len(c)}" for g, c in groups.items())
    print(f">> Updated temps.json: {summary} @ {data['updated']}")

    # แจ้งเตือนเข้า LINE ถ้ามีจุดไหนเกินเกณฑ์ (ทำก่อน push เผื่อ git มีปัญหา จะได้ยังแจ้งทัน)
    # ไม่ตั้งค่า line_config.json ไว้ = ข้ามไปเงียบๆ ไม่กระทบการอัปเดต
    try:
        import line_alert
        line_alert.check_and_notify(data)
    except Exception as e:
        print(f"(line) ข้ามการแจ้งเตือน: {type(e).__name__} {e}")

    # push ขึ้น GitHub
    try:
        subprocess.run(["git", "-C", str(REPO_DIR), "add", "temps.json"], check=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["git", "-C", str(REPO_DIR), "commit", "-m",
                        f"Update temps {data['updated']}"], check=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["git", "-C", str(REPO_DIR), "push", "origin", "main"], check=True, creationflags=CREATE_NO_WINDOW)
        print(">> Pushed to GitHub Pages.")
    except subprocess.CalledProcessError as e:
        print(f"(git) {e}")


if __name__ == "__main__":
    main()
