#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
แจ้งเตือนอุณหภูมิ Bearing Pulley เข้า LINE
------------------------------------------
ใช้ LINE Messaging API (LINE Official Account)
* LINE Notify แบบเดิมปิดบริการไปแล้วเมื่อ 31 มี.ค. 2568 จึงใช้วิธีนี้แทน

ตั้งค่า: สร้างไฟล์ updater/line_config.json (ไฟล์นี้ถูก gitignore ไว้ ไม่ขึ้น GitHub)
{
  "enabled": true,
  "token": "<Channel access token จาก LINE Developers Console>",
  "to": "",                      // เว้นว่าง = broadcast หาทุกคนที่เพิ่มเพื่อน OA
  "threshold": 80,               // °C เกินเท่านี้ถึงแจ้ง
  "repeat_minutes": 15,          // เตือนซ้ำทุกกี่นาทีถ้ายังร้อนอยู่
  "notify_recovery": true,       // แจ้งเมื่อกลับสู่ปกติด้วย
  "dashboard_url": "https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/spreader.html"
}

ใช้งาน:
  python line_alert.py --test     ส่งข้อความทดสอบ
  python line_alert.py --quota    ดูโควตาข้อความที่เหลือของเดือนนี้
  python line_alert.py --check    ตรวจ temps.json ปัจจุบันแล้วแจ้งถ้าเกิน (ปกติ update_temps.py เรียกให้เอง)
"""
import json, sys, time, pathlib, datetime, argparse
import urllib.request, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE       = pathlib.Path(__file__).resolve().parent
REPO_DIR   = HERE.parent
CONFIG     = HERE / "line_config.json"
STATE      = HERE / ".line_alert_state.json"
TEMPS_JSON = REPO_DIR / "temps.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))

API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"
API_PUSH      = "https://api.line.me/v2/bot/message/push"
API_QUOTA     = "https://api.line.me/v2/bot/message/quota/consumption"

FAULTY = 200          # สูงเกินจริง น่าจะเซนเซอร์ผิดปกติ

# ชื่อจุดวัดที่อ่านเข้าใจง่าย (ให้ตรงกับ temp-alert.js บนหน้าเว็บ)
LABELS = {
    "RCV_DE_L":  "Spreader · RCV DE (ซ้าย)",     "RCV_DE_R":  "Spreader · RCV DE (ขวา)",
    "RCV_NDE_L": "Spreader · RCV NDE (ซ้าย)",    "RCV_NDE_R": "Spreader · RCV NDE (ขวา)",
    "DCV_DE_L":  "Spreader · DCV DE (ซ้าย)",     "DCV_DE_R":  "Spreader · DCV DE (ขวา)",
    "DCV_NDE_L": "Spreader · DCV NDE (ซ้าย)",    "DCV_NDE_R": "Spreader · DCV NDE (ขวา)",
    "DCV_TC_L":  "Tripper car · DCV TC (ซ้าย)",  "DCV_TC_R":  "Tripper car · DCV TC (ขวา)",
    "BEND_L":    "Tripper car · Bend (ซ้าย)",    "BEND_R":    "Tripper car · Bend (ขวา)",
    "TAKE_UP_L": "Tripper car · Take-up (ซ้าย)", "TAKE_UP_R": "Tripper car · Take-up (ขวา)",
}


def label(tag):
    return LABELS.get(tag, tag.replace("_", " "))


def load_config():
    if not CONFIG.exists():
        return None
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"(line) อ่าน line_config.json ไม่ได้: {e}")
        return None
    if not c.get("token"):
        print("(line) ยังไม่ได้ใส่ token ใน line_config.json")
        return None
    c.setdefault("enabled", True)
    c.setdefault("to", "")
    c.setdefault("threshold", 80)
    c.setdefault("repeat_minutes", 15)
    c.setdefault("notify_recovery", True)
    c.setdefault("dashboard_url",
                 "https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/spreader.html")
    return c


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    try:
        STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"(line) เขียน state ไม่ได้: {e}")


def send(cfg, text):
    """ส่งข้อความเข้า LINE คืน True ถ้าสำเร็จ"""
    body = {"messages": [{"type": "text", "text": text[:4900]}]}
    url = API_BROADCAST
    if cfg["to"]:
        url = API_PUSH
        body["to"] = cfg["to"]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["token"]},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"(line) ส่งแล้ว HTTP {r.status}")
            return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"(line) ส่งไม่สำเร็จ HTTP {e.code}: {detail}")
    except Exception as e:
        print(f"(line) ส่งไม่สำเร็จ: {type(e).__name__} {e}")
    return False


def quota(cfg):
    req = urllib.request.Request(
        API_QUOTA, headers={"Authorization": "Bearer " + cfg["token"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("(line) ใช้ไปเดือนนี้:", r.read().decode("utf-8"))
    except Exception as e:
        print(f"(line) ดูโควตาไม่ได้: {e}")


def read_temps(data=None):
    """คืน dict {tag: value} จาก temps.json หรือจาก data ที่ส่งเข้ามา"""
    if data is None:
        try:
            data = json.loads(TEMPS_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"(line) อ่าน temps.json ไม่ได้: {e}")
            return {}, ""
    out = {}
    for arr in (data.get("groups") or {}).values():
        for it in arr or []:
            v = it.get("value")
            if isinstance(v, (int, float)):
                out[it.get("tag")] = float(v)
    return out, data.get("updated", "")


def build_message(hot, cfg, updated):
    now = datetime.datetime.now(TZ).strftime("%H:%M")
    lines = [f"🚨 อุณหภูมิ Bearing Pulley เกิน {cfg['threshold']}°C",
             f"เวลา {now} น. · จุดที่เกิน {len(hot)} จุด", ""]
    for tag, v in hot:
        warn = "  ⚠️ ค่าผิดปกติ ตรวจเซนเซอร์" if v >= FAULTY else ""
        lines.append(f"• {label(tag)}\n   {v:.1f} °C{warn}")
    lines += ["", f"เตือนซ้ำทุก {cfg['repeat_minutes']} นาที จนกว่าจะกลับสู่ปกติ",
              cfg["dashboard_url"]]
    return "\n".join(lines)


def check_and_notify(data=None):
    """ตรวจค่าปัจจุบัน แล้วแจ้ง LINE ถ้าจำเป็น — เรียกจาก update_temps.py ได้เลย
       ออกแบบให้ไม่ทำให้ตัวเรียกพังไม่ว่าเกิดอะไรขึ้น"""
    try:
        cfg = load_config()
        if not cfg or not cfg.get("enabled"):
            return
        temps, updated = read_temps(data)
        if not temps:
            return

        thr = float(cfg["threshold"])
        repeat = float(cfg["repeat_minutes"]) * 60
        now = time.time()
        state = load_state()

        hot = sorted([(t, v) for t, v in temps.items() if v >= thr],
                     key=lambda x: -x[1])
        hot_tags = {t for t, _ in hot}

        # จุดที่เย็นลงแล้ว -> ล้าง state ทิ้ง (ถ้าร้อนอีกจะแจ้งทันที ไม่ต้องรอรอบ)
        cooled = [t for t in list(state.keys()) if t not in hot_tags]
        for t in cooled:
            state.pop(t, None)

        if not hot:
            if cooled and cfg.get("notify_recovery"):
                names = ", ".join(label(t) for t in cooled)
                send(cfg, f"✅ อุณหภูมิกลับสู่ปกติแล้ว (ต่ำกว่า {thr:.0f}°C)\n{names}")
            save_state(state)
            return

        # จุดที่ถึงเวลาแจ้ง = ยังไม่เคยแจ้ง หรือแจ้งครั้งล่าสุดเกิน repeat แล้ว
        due = [(t, v) for t, v in hot if now - state.get(t, 0) >= repeat]
        if due:
            if send(cfg, build_message(due, cfg, updated)):
                for t, _ in due:
                    state[t] = now
        save_state(state)
    except Exception as e:
        # แจ้งเตือนล้มเหลวต้องไม่ทำให้การอัปเดตอุณหภูมิพัง
        print(f"(line) ข้ามการแจ้งเตือน: {type(e).__name__} {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="ส่งข้อความทดสอบ")
    ap.add_argument("--quota", action="store_true", help="ดูโควตาข้อความเดือนนี้")
    ap.add_argument("--check", action="store_true", help="ตรวจ temps.json แล้วแจ้งถ้าเกิน")
    ap.add_argument("--reset", action="store_true", help="ล้างสถานะการแจ้ง (จะแจ้งใหม่ทันที)")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg:
        print("!! ยังตั้งค่าไม่ครบ — สร้าง updater/line_config.json ก่อน (ดูคำอธิบายหัวไฟล์)")
        sys.exit(1)

    if args.reset:
        save_state({}); print("ล้างสถานะแล้ว"); return
    if args.quota:
        quota(cfg); return
    if args.test:
        mode = "push -> " + cfg["to"] if cfg["to"] else "broadcast (ทุกคนที่เป็นเพื่อนกับ OA)"
        print("โหมด:", mode)
        ok = send(cfg, "🔔 ทดสอบการแจ้งเตือนอุณหภูมิ Bearing Pulley\n"
                       "ถ้าเห็นข้อความนี้ในไลน์ แปลว่าตั้งค่าเรียบร้อยแล้ว\n"
                       + cfg["dashboard_url"])
        sys.exit(0 if ok else 1)

    check_and_notify()


if __name__ == "__main__":
    main()
