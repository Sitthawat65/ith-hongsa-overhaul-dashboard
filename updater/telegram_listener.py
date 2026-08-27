#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตัวรับปุ่ม "รับทราบ" จาก Telegram แบบทันที
------------------------------------------
เปิดค้างไว้เบาๆ (long polling) เพื่อให้:
  * กดปุ่มรับทราบแล้วเสียงเตือนหยุดทันที ไม่ต้องรอรอบอัปเดต 5 นาที
  * เตือนซ้ำได้ถี่กว่ารอบอัปเดต (ทุก nag_minutes นาที)
  * พิมพ์ /status ในแชทเพื่อขอดูอุณหภูมิล่าสุดได้ตลอดเวลา

ไม่เปิดตัวนี้ก็ยังใช้งานได้ ตัวอัปเดตทุก 5 นาทีจะเช็คปุ่มให้เอง แค่ตอบสนองช้ากว่า

รันเอง:      python telegram_listener.py
รันแบบซ่อน:  pythonw telegram_listener.py      (ไม่มีหน้าต่าง)
ให้เปิดเองตอนเข้า Windows: ดับเบิลคลิก INSTALL_Telegram_Listener.bat

หมายเหตุ: ห้ามเปิดพร้อมกันสองตัว และห้ามรัน telegram_alert.py --setup ระหว่างที่ตัวนี้ทำงาน
(Telegram ยอมให้ดึงอัปเดตได้ทีละที่เดียว จะขึ้น error 409)
"""
import sys, time, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import telegram_alert as TA
import telegram_alarm as AL

POLL_TIMEOUT = 45          # วินาที ต่อการรอ 1 รอบ (long polling ไม่กินเน็ต/ซีพียู)


def main():
    cfg = TA.load_config()
    if not cfg:
        print("!! ยังไม่ได้ตั้งค่า token — ดู updater/telegram_config.json")
        sys.exit(1)
    me = TA.call(cfg, "getMe")
    if not (me and me.get("ok")):
        print("!! token ใช้ไม่ได้")
        sys.exit(1)
    print(f">> listening as @{me['result']['username']} — กด Ctrl+C เพื่อหยุด")

    while True:
        try:
            cfg = TA.load_config() or cfg            # อ่าน config ใหม่ทุกรอบ แก้แล้วมีผลทันที
            AL.touch(listener_seen=time.time())      # บอกตัวอัปเดตว่าเราดูแลเรื่องปุ่มอยู่

            AL.poll_updates(cfg, timeout=POLL_TIMEOUT)

            # เตือนซ้ำได้ถี่กว่ารอบอัปเดต 5 นาที โดยใช้ค่าที่ตัวอัปเดตบันทึกไว้ล่าสุด
            # (อ่านสถานะสดหลัง long-poll เสมอ ตัวอัปเดตอาจเพิ่งเขียนทับไประหว่างนั้น)
            st = AL.touch(listener_seen=time.time())
            if st.get("active") and not st.get("acked"):
                hot = [(t, v) for t, v in st.get("points", [])]
                if hot:
                    AL.pump(cfg, st, hot)
                    AL.save(st)
        except KeyboardInterrupt:
            print("\n>> หยุดแล้ว")
            return
        except Exception as e:
            print(f"(listener) {type(e).__name__} {e} — ลองใหม่ใน 15 วินาที")
            time.sleep(15)


if __name__ == "__main__":
    main()
