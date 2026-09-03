#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watchdog — เตือน Telegram ถ้า temps.json "ค้าง" (updater บน PC ออฟฟิศหยุดทำงาน)

รันบนเครื่องของ GitHub Actions (นอกโรงงาน) จึงจับได้แม้ PC 192.168.101.9
ดับ / ไฟดับ / เน็ตหลุด — ต่างจาก updater ที่รันในโรงงาน
อ่านแค่ temps.json ในรีโป (ไม่ยุ่งกับ Primus) จึงไม่ติด Cloudflare

ค่าที่ปรับได้ผ่าน env:
  STALE_MIN         ค้างกี่นาทีถึงเตือน (ดีฟอลต์ 20 — updater เขียนทุก 5 นาที = พลาด ~4 รอบ)
  TELEGRAM_TOKEN    token บอท (secret)
  TELEGRAM_CHAT_IDS chat id ปลายทาง คั่นด้วยจุลภาค (secret)
"""
import json, os, sys, urllib.request, urllib.parse, datetime, pathlib

STALE_MIN = int(os.environ.get("STALE_MIN", "20"))
REPO      = pathlib.Path(__file__).resolve().parents[2]
TEMPS     = REPO / "temps.json"
DASH_URL  = ("https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/"
             "Bearing-Pulley-Temp-Monitoring-ITH-CV.html")


def telegram(text):
    """ส่งข้อความเข้าทุก chat id — ล้มเหลวก็แค่พิมพ์ log ไม่ทำให้ job พัง"""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    ids   = os.environ.get("TELEGRAM_CHAT_IDS", "")
    chat_ids = [c.strip() for c in ids.replace(";", ",").split(",") if c.strip()]
    if not token or not chat_ids:
        print("watchdog: ไม่มี TELEGRAM_TOKEN/CHAT_IDS — ข้ามการเตือน")
        return
    for cid in chat_ids:
        body = urllib.parse.urlencode({
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=body)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
            print("watchdog: ส่งเตือนไปยัง", cid)
        except Exception as e:  # noqa: BLE001
            print("watchdog: ส่งไม่สำเร็จ", cid, e)


def main():
    # 1) อ่านไฟล์
    try:
        data = json.loads(TEMPS.read_text(encoding="utf-8"))
        updated = data.get("updated")
    except Exception as e:  # noqa: BLE001
        telegram("⚠️ <b>ITH Bearing Temp Watchdog</b>\n"
                 f"อ่าน temps.json ไม่ได้: {e}")
        print("watchdog: อ่าน temps.json ไม่ได้:", e)
        return

    # 2) แปลงเวลา updated (เช่น 2026-09-03T16:17:41+07:00)
    try:
        t = datetime.datetime.fromisoformat(str(updated))
    except Exception:  # noqa: BLE001
        telegram("⚠️ <b>ITH Bearing Temp Watchdog</b>\n"
                 f"รูปแบบเวลา updated ผิดปกติ: {updated}")
        print("watchdog: parse updated ไม่ได้:", updated)
        return

    now = datetime.datetime.now(t.tzinfo) if t.tzinfo else datetime.datetime.now()
    age_min = (now - t).total_seconds() / 60.0
    print(f"watchdog: updated={updated} age={age_min:.1f} min threshold={STALE_MIN} min")

    # 3) ตัดสิน
    if age_min > STALE_MIN:
        hhmm = t.strftime("%d/%m %H:%M")
        telegram(
            "⚠️ <b>ITH Dashboard — ระบบดึงอุณหภูมิหยุดอัปเดต</b>\n"
            f"ค่าล่าสุดเมื่อ <b>{hhmm}</b> น. (ค้างมาแล้ว ~{int(age_min)} นาที)\n"
            "โปรดตรวจสอบ PC <code>192.168.101.9</code> / updater / เน็ต\n"
            f'<a href="{DASH_URL}">เปิด Dashboard</a>'
        )
        print("watchdog: STALE — ส่งเตือนแล้ว")
    else:
        print("watchdog: OK — ค่าสดปกติ")


if __name__ == "__main__":
    main()
