#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ส่ง "ภาพแผนภาพพร้อมค่าอุณหภูมิ" เข้า Telegram ทุกรอบอัปเดต (ทุก ~5 นาที)
---------------------------------------------------------------------
วาดค่าจาก temps.json ลงบนรูปแผนภาพเดียวกับที่ใช้บนหน้าเว็บ แล้วส่งเข้าบอท

ตำแหน่งของทุกช่องอ่านมาจากไฟล์ HTML โดยตรง (แท็ก <span class="tv" ...>)
จึงไม่มีพิกัดซ้ำซ้อนสองที่ — แก้ที่หน้าเว็บที่เดียว รูปที่ส่งเข้า Telegram ก็ขยับตาม

โหมดการส่ง (ตั้งใน telegram_config.json ช่อง snapshot_mode):
  "edit"  = ส่งครั้งแรกครั้งเดียว จากนั้น "แก้รูปเดิม" ทุก 5 นาที  <- ค่าเริ่มต้น
            แชทไม่รก ภาพในแชทเป็นค่าล่าสุดเสมอ
  "send"  = ส่งรูปใหม่ทุก 5 นาที (แชทจะยาวมาก ~288 รูป/วัน/หน้า)

ใช้งาน:
  python telegram_snapshot.py --now      สร้างรูปแล้วส่งเข้า Telegram เดี๋ยวนี้
  python telegram_snapshot.py --save     สร้างรูปเก็บไว้ดูเฉยๆ ไม่ส่ง
"""
import json, sys, re, io, time, pathlib, datetime, argparse, uuid
import urllib.request, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE       = pathlib.Path(__file__).resolve().parent
REPO_DIR   = HERE.parent
TEMPS_JSON = REPO_DIR / "temps.json"
STATE      = HERE / ".telegram_snapshot_state.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))

WARN, ALARM = 70, 80
STALE_MIN = 20                      # ไม่มีค่าใหม่เกินเท่านี้ (นาที) = ถือว่าเป็นค่าเก่า
# หาฟอนต์ให้เจอทั้งบน Windows (เครื่องนี้) และ Linux (GitHub Actions)
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _font(size):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

# ชื่อหน้า -> (ไฟล์รูป, ไฟล์ HTML ที่เก็บพิกัดช่อง, ชื่อเต็มไว้ขึ้นหัวข้อความ)
PAGES = {
    "SPD":         ("spreader.png", "spreader.html", "Spreader"),
    "Tripper car": ("tripper.png",  "tripper.html",  "Tripper car"),
    "BWE1":        ("BWE1.PNG",     "BWE1.html",     "Bucket Wheel Excavator 1"),
    "BWE2":        ("BWE2.PNG",     "BWE2.html",     "Bucket Wheel Excavator 2"),
    "CR1":         ("CR1.PNG",      "CR1.html",      "Crusher 1"),
    "CR2":         ("CR2.PNG",      "CR2.html",      "Crusher 2"),
}
DEFAULT_PAGES = ["SPD", "Tripper car", "BWE2"]

COL_OK, COL_WARN, COL_ALARM, COL_STALE = (10, 143, 60), (224, 125, 0), (209, 0, 0), (150, 155, 160)
SPAN_RE = re.compile(r'<span class="tv"\s+id="([A-Za-z0-9_]+)"\s+style="left:([\d.]+)%;top:([\d.]+)%"')

try:
    from line_alert import label
except Exception:                                   # pragma: no cover
    def label(tag):
        return tag.replace("_", " ")


# ------------------------------------------------------------------ ข้อมูล
def load_temps():
    data = json.loads(TEMPS_JSON.read_text(encoding="utf-8"))
    updated = data.get("updated", "")
    items = {}
    for cards in (data.get("groups") or {}).values():
        for c in cards:
            if isinstance(c.get("value"), (int, float)):
                items[c["tag"]] = (float(c["value"]), c.get("seen") or updated)
    return items, updated


def spans_of(html_name):
    """อ่านตำแหน่งช่องค่าจากหน้าเว็บ -> [(tag, left%, top%)]"""
    html = (REPO_DIR / html_name).read_text(encoding="utf-8")
    return [(m[0], float(m[1]), float(m[2])) for m in SPAN_RE.findall(html)]


def age_minutes(seen_iso, now=None):
    try:
        seen = datetime.datetime.fromisoformat(seen_iso)
    except Exception:
        return 0.0
    now = now or datetime.datetime.now(TZ)
    return (now - seen).total_seconds() / 60.0


# ------------------------------------------------------------------ วาดรูป
def render(page, items, updated):
    from PIL import Image, ImageDraw, ImageFont

    img_name, html_name, _full = PAGES[page]
    im = Image.open(REPO_DIR / img_name).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    font = _font(max(12, round(W * 0.0140)))
    small = _font(max(10, round(W * 0.0105)))

    hot, shown = [], 0
    for tag, lx, ty in spans_of(html_name):
        x, y = lx / 100 * W, ty / 100 * H
        rec = items.get(tag)
        if rec is None:
            txt, col = "-", COL_STALE
        else:
            v, seen = rec
            txt = f"{v:.1f}"
            if age_minutes(seen) > STALE_MIN:
                col = COL_STALE
            elif v >= ALARM:
                col = COL_ALARM
            elif v >= WARN:
                col = COL_WARN
            else:
                col = COL_OK
            if v >= ALARM:
                hot.append((tag, v))
            shown += 1
        bb = d.textbbox((0, 0), txt, font=font)
        d.text((x - (bb[2] - bb[0]) / 2, y - (bb[3] - bb[1]) / 2 - bb[1]), txt, fill=col, font=font)

    # แถบเวลาเล็กๆ มุมล่างขวา เผื่อรูปถูกส่งต่อออกไปจะได้รู้ว่าเป็นค่าเมื่อไหร่
    try:
        stamp = datetime.datetime.fromisoformat(updated).strftime("Updated %d %b %Y  %H:%M")
    except Exception:
        stamp = "Updated -"
    bb = d.textbbox((0, 0), stamp, font=small)
    pad = round(W * 0.006)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x1, y1 = W - pad, H - pad
    d.rectangle([x1 - tw - 2 * pad, y1 - th - 2 * pad, x1, y1], fill=(255, 255, 255))
    d.text((x1 - tw - pad, y1 - th - pad - bb[1]), stamp, fill=(90, 100, 110), font=small)

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue(), hot, shown


def caption(page, items, updated, hot, shown):
    _img, html_name, full = PAGES[page]
    try:
        t = datetime.datetime.fromisoformat(updated).strftime("%H:%M")
    except Exception:
        t = "-"
    head = f"{'🚨' if hot else '📊'} {page} — {full}"
    lines = [head, f"อัปเดต {t} น. · {shown} จุด"]
    if hot:
        lines.append("")
        lines.append(f"เกิน {ALARM}°C:")
        for tag, v in sorted(hot, key=lambda x: -x[1]):
            lines.append(f"• {label(tag)}  {v:.1f}°C")
    else:
        tags = [t2 for t2, _, _ in spans_of(html_name) if t2 in items]
        if tags:
            top = max(tags, key=lambda t2: items[t2][0])
            v, seen = items[top]
            old = "  (ค่าเก่า)" if age_minutes(seen) > STALE_MIN else ""
            lines.append(f"สูงสุด: {label(top)}  {v:.1f}°C{old}")
    return "\n".join(lines)


# ------------------------------------------------------------------ Telegram
def _multipart(fields, files):
    b = "----ITH" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += str(v).encode("utf-8") + b"\r\n"
    for k, (fn, data, ctype) in files.items():
        body += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    return bytes(body), "multipart/form-data; boundary=" + b


def api(cfg, method, fields, files=None, quiet=False):
    url = f"https://api.telegram.org/bot{cfg['token']}/{method}"
    if files:
        data, ctype = _multipart(fields, files)
        headers = {"Content-Type": ctype}
    else:
        data, headers = json.dumps(fields).encode("utf-8"), {"Content-Type": "application/json"}
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=data, headers=headers, method="POST"),
                timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:250]
        if not quiet:
            print(f"(snapshot) {method} HTTP {e.code}: {detail}")
        return {"ok": False, "description": detail}
    except Exception as e:
        if not quiet:
            print(f"(snapshot) {method} ล้มเหลว: {type(e).__name__} {e}")
        return {"ok": False, "description": str(e)}


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    try:
        STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"(snapshot) เขียน state ไม่ได้: {e}")


def deliver(cfg, chat, page, jpeg, cap, state, mode, silent, fresh_every=0, updated=""):
    """ส่งรูป หรือแก้รูปเดิมถ้าเคยส่งไว้แล้ว

    fresh_every : ทุกกี่นาทีให้ส่งรูป "ใหม่" ลงมาในแชท (0 = แก้รูปเดิมอย่างเดียว)
                  <= 5 หมายถึง "ทุกครั้งที่ข้อมูลอัปเดต" ซึ่งเป็นค่าที่ใช้จริง

    การตัดสินใจว่าถึงเวลาส่งรูปใหม่หรือยัง ยึด "เวลาของข้อมูล" ไม่ใช่นาฬิกาผนัง
    เพราะถ้านับเป็นนาที แต่ละแชทจะเดินคนละจังหวะทันทีที่มีการส่งแทรก (เช่นสั่งด้วยมือ)
    แล้วบางแชทจะโดนข้ามรอบไปเงียบๆ  ยึดเวลาข้อมูลแทน = ทุกแชทได้รูปใหม่พร้อมกันเสมอ
    """
    key = str(chat)
    mine = state.setdefault(key, {})
    files = {"photo": (f"{page}.jpg", jpeg, "image/jpeg")}

    stamps = state.setdefault("_sent_at", {})     # นาฬิกาผนัง (ใช้เมื่อตั้งเป็นราย 15/30/60 นาที)
    marks  = state.setdefault("_sent_for", {})    # เวลาของข้อมูลที่ส่งไปแล้ว
    slot = f"{key}|{page}"
    due_fresh = False
    if fresh_every > 0:
        if fresh_every <= 5:                      # ทุกครั้งที่ข้อมูลอัปเดต
            due_fresh = bool(updated) and marks.get(slot) != updated
        else:
            due_fresh = (time.time() - stamps.get(slot, 0)) >= fresh_every * 60

    if mode == "edit" and mine.get(page) and not due_fresh:
        r = api(cfg, "editMessageMedia", {
            "chat_id": chat,
            "message_id": mine[page],
            "media": json.dumps({"type": "photo", "media": "attach://photo", "caption": cap},
                                ensure_ascii=False),
        }, files, quiet=True)
        desc = str(r.get("description") or "")
        # "message is not modified" = ค่าไม่เปลี่ยนจากรอบก่อน รูปในแชทถูกต้องอยู่แล้ว ไม่ต้องทำอะไร
        if r.get("ok") or "is not modified" in desc:
            return True
        # แก้ไม่ได้จริง (ข้อความถูกลบ / เก่าเกิน 48 ชม.) -> ส่งใหม่แล้วจำ id ใหม่แทน
        print(f"(snapshot) แก้รูปเดิม {page} #{mine[page]} ไม่ได้ จึงส่งใหม่: {desc[:140]}")
        mine.pop(page, None)

    r = api(cfg, "sendPhoto", {
        "chat_id": chat,
        "caption": cap,
        "disable_notification": "true" if silent else "false",
    }, files)
    if r.get("ok"):
        stamps[slot] = time.time()
        marks[slot] = updated
        if mode == "edit":
            mine[page] = r["result"]["message_id"]
        return True
    return False


def post_snapshots(cfg=None):
    """สร้างรูปทุกหน้าแล้วส่งเข้า Telegram — เรียกจาก update_temps.py ได้เลย
       ออกแบบให้ไม่ทำให้ตัวเรียกพังไม่ว่าเกิดอะไรขึ้น"""
    try:
        if cfg is None:
            import telegram_alert
            cfg = telegram_alert.load_config()
        if not cfg or not cfg.get("enabled"):
            return
        if not cfg.get("snapshot_enabled", True):
            return
        chats = cfg.get("chat_ids") or []
        if not chats:
            return

        pages = [p for p in cfg.get("snapshot_pages", DEFAULT_PAGES) if p in PAGES]
        mode = cfg.get("snapshot_mode", "edit")
        silent = bool(cfg.get("snapshot_silent", True))
        fresh_every = float(cfg.get("snapshot_new_message_minutes", 30))
        items, updated = load_temps()
        state = load_state()

        for page in pages:
            try:
                jpeg, hot, shown = render(page, items, updated)
            except Exception as e:
                print(f"(snapshot) วาดรูป {page} ไม่ได้: {type(e).__name__} {e}")
                continue
            cap = caption(page, items, updated, hot, shown)
            for chat in chats:
                deliver(cfg, chat, page, jpeg, cap, state, mode, silent, fresh_every, updated)
        save_state(state)
        print(f"(snapshot) ส่งภาพ {len(pages)} หน้า x {len(chats)} ปลายทาง "
              f"(mode={mode}, รูปใหม่ทุก {fresh_every:g} นาที)")
    except Exception as e:
        print(f"(snapshot) ข้าม: {type(e).__name__} {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="สร้างรูปแล้วส่งเข้า Telegram เดี๋ยวนี้")
    ap.add_argument("--save", action="store_true", help="สร้างรูปเก็บไว้ดู ไม่ส่ง")
    ap.add_argument("--out", default=".", help="โฟลเดอร์ปลายทางของ --save")
    args = ap.parse_args()

    if args.save:
        items, updated = load_temps()
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for page in PAGES:
            jpeg, hot, shown = render(page, items, updated)
            f = out / f"snapshot_{page.replace(' ', '_')}.jpg"
            f.write_bytes(jpeg)
            print(f"  {f}  ({len(jpeg)//1024} KB, {shown} จุด, เกินเกณฑ์ {len(hot)})")
        return

    if args.now:
        post_snapshots()
        return

    ap.print_help()


if __name__ == "__main__":
    main()
