#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
แจ้งเตือนอุณหภูมิเข้า Telegram แบบเดียวกับหน้า Dashboard
--------------------------------------------------------
เลียนแบบพฤติกรรมของ temp-alert.js บนหน้าเว็บให้มากที่สุดเท่าที่ Telegram ทำได้:

  * มีจุด >= 80 C  -> ส่งข้อความพร้อมปุ่ม "รับทราบ (Acknowledge)"
  * ยังไม่กดรับทราบ -> ส่งซ้ำทุก nag_minutes นาที (แทนเสียงที่ดังไม่หยุดบนหน้าเว็บ
                       เพราะบอทสั่งให้มือถือส่งเสียงยาวไม่ได้ ได้แค่ 1 เสียงต่อ 1 ข้อความ)
  * กดรับทราบแล้ว   -> เงียบ แล้วถ้ายังร้อนอยู่จะเตือนใหม่อีกครั้งใน repeat_minutes นาที
  * เย็นลงต่ำกว่าเกณฑ์ -> ส่งข้อความ "กลับสู่ปกติ" แล้วล้างสถานะ (ร้อนอีกจะเตือนทันที)

ใครกดรับทราบ ระบบจะแก้ข้อความเดิมให้เห็นว่าใครกดตอนกี่โมง — เหมือนหน้าเว็บที่กดแล้วป๊อปอัปหาย

การรับ "ปุ่มถูกกด" ทำได้ 2 ทาง:
  1. ตัวอัปเดตทุก 5 นาทีจะเช็คให้เอง  (ไม่ต้องติดตั้งอะไรเพิ่ม แต่กดแล้วรอถึง 5 นาที)
  2. เปิด telegram_listener.py ค้างไว้ -> กดแล้วตอบสนองทันที (แนะนำ)

สถานะเก็บใน .telegram_alarm_state.json (gitignore ไว้)
"""
import json, sys, time, pathlib, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE  = pathlib.Path(__file__).resolve().parent
STATE = HERE / ".telegram_alarm_state.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))

import telegram_alert as TA          # ใช้ config / label / read_temps / call ร่วมกัน

FAULTY = TA.FAULTY
LISTENER_FRESH = 120                 # ถ้า listener หายใจภายในกี่วินาที ให้ถือว่ายังทำงานอยู่


# ------------------------------------------------------------------ สถานะ
def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(st):
    try:
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"(alarm) เขียนสถานะไม่ได้: {e}")


def listener_alive(st):
    return (time.time() - st.get("listener_seen", 0)) < LISTENER_FRESH


# ------------------------------------------------------------------ ข้อความ
def hhmm(ts=None):
    return datetime.datetime.fromtimestamp(ts or time.time(), TZ).strftime("%H:%M")


def alarm_text(cfg, hot, st, nag_no):
    thr = cfg["threshold"]
    lines = [f"🚨 อุณหภูมิเกิน {thr}°C — ต้องกดรับทราบ",
             f"เวลา {hhmm()} น. · จุดที่เกิน {len(hot)} จุด"]
    if nag_no > 1:
        since = hhmm(st.get("started"))
        lines.append(f"⏰ เตือนครั้งที่ {nag_no} · ค้างมาตั้งแต่ {since} น.")
    lines.append("")
    for tag, v in sorted(hot, key=lambda x: -x[1]):
        warn = "  ⚠️ ค่าผิดปกติ ตรวจเซนเซอร์" if v >= FAULTY else ""
        lines.append(f"• {TA.label(tag)}\n   {v:.1f} °C{warn}")
    lines += ["", f"จะเตือนซ้ำทุก {cfg.get('nag_minutes', 2)} นาที จนกว่าจะกดปุ่มรับทราบข้างล่าง",
              cfg["dashboard_url"]]
    return "\n".join(lines)


ACK_MARKUP = {"inline_keyboard": [[{"text": "✅ รับทราบ (Acknowledge)", "callback_data": "ack"}]]}


def send_msg(cfg, chat, text, markup=None):
    body = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
    if markup:
        body["reply_markup"] = markup
    r = TA.call(cfg, "sendMessage", body)
    if r and r.get("ok"):
        return r["result"]["message_id"]
    return None


def broadcast(cfg, text, markup=None):
    out = {}
    for chat in cfg.get("chat_ids") or []:
        mid = send_msg(cfg, chat, text, markup)
        if mid:
            out[str(chat)] = mid
    return out


# ------------------------------------------------------------------ ตรรกะหลัก
def pump(cfg, st, hot, now=None):
    """ตัดสินใจว่าถึงเวลาส่ง/ส่งซ้ำหรือยัง — เรียกได้ทั้งจากตัวอัปเดตและจาก listener"""
    now = now or time.time()
    nag = float(cfg.get("nag_minutes", 2)) * 60
    repeat = float(cfg.get("repeat_minutes", 15)) * 60

    if not hot:
        if st.get("active"):
            names = ", ".join(TA.label(t) for t, _ in st.get("points", []))
            broadcast(cfg, f"✅ อุณหภูมิกลับสู่ปกติแล้ว (ต่ำกว่า {cfg['threshold']:.0f}°C)\n{names}\n"
                           f"เวลา {hhmm(now)} น.")
            st.clear()
        return st

    st["points"] = [[t, v] for t, v in hot]

    if not st.get("active"):                       # เพิ่งข้ามเกณฑ์ -> เตือนครั้งแรก
        st.update(active=True, acked=False, started=now, nag_no=0, acked_at=0, acked_by="")

    if st.get("acked"):
        # รับทราบแล้ว: เงียบไว้ก่อน ครบ repeat_minutes แล้วยังร้อนอยู่ค่อยปลุกใหม่
        if now - st.get("acked_at", 0) < repeat:
            return st
        st.update(acked=False, nag_no=0, acked_by="")

    if st.get("last_sent") and now - st["last_sent"] < nag:
        return st                                   # ยังไม่ถึงรอบเตือนซ้ำ

    st["nag_no"] = st.get("nag_no", 0) + 1
    msgs = broadcast(cfg, alarm_text(cfg, hot, st, st["nag_no"]), ACK_MARKUP)
    if msgs:
        st["messages"] = msgs                       # จำไว้เพื่อแก้ข้อความตอนกดรับทราบ
        st["last_sent"] = now
    return st


def acknowledge(cfg, st, who, now=None):
    """มีคนกดปุ่มรับทราบ — เงียบเสียง แล้วแก้ข้อความเดิมให้เห็นว่าใครกด"""
    now = now or time.time()
    if not st.get("active"):
        # ไม่มีเหตุการณ์จริงค้างอยู่ — ถ้าเป็นข้อความตัวอย่าง ก็แก้ให้เห็นว่ากดแล้ว
        nag = cfg.get("nag_minutes", 2)
        rpt = int(float(cfg.get("repeat_minutes", 15)))
        for chat, mid in (st.pop("demo_messages", None) or {}).items():
            TA.call(cfg, "editMessageText", {
                "chat_id": int(chat), "message_id": mid,
                "text": ("🧪 ตัวอย่างการแจ้งเตือน — ทดสอบสำเร็จ\n\n"
                         f"✅ รับทราบแล้วโดย {who}\nเวลา {hhmm(now)} น.\n\n"
                         f"ของจริงจะทำงานแบบนี้: เตือนซ้ำทุก {nag} นาทีจนกว่าจะกดปุ่มนี้ "
                         f"แล้วเงียบไป {rpt} นาที ก่อนเตือนอีกครั้งถ้ายังร้อนอยู่"),
                "disable_web_page_preview": True})
        return st
    st.update(acked=True, acked_at=now, acked_by=who)
    repeat = int(float(cfg.get("repeat_minutes", 15)))
    note = (f"\n\n✅ รับทราบแล้วโดย {who}\n"
            f"เวลา {hhmm(now)} น. · ถ้ายังร้อนอยู่จะเตือนอีกครั้งใน {repeat} นาที")
    for chat, mid in (st.get("messages") or {}).items():
        base = alarm_text(cfg, [(t, v) for t, v in st.get("points", [])], st, st.get("nag_no", 1))
        TA.call(cfg, "editMessageText", {
            "chat_id": int(chat), "message_id": mid,
            "text": (base + note)[:4000], "disable_web_page_preview": True,
        })
    return st


def status_text(cfg):
    temps, updated = TA.read_temps()
    if not temps:
        return "ยังไม่มีข้อมูลอุณหภูมิ"
    thr = float(cfg["threshold"])
    hot = sorted([(t, v) for t, v in temps.items() if v >= thr], key=lambda x: -x[1])
    top = sorted(temps.items(), key=lambda kv: -kv[1])[:5]
    try:
        t = datetime.datetime.fromisoformat(updated).strftime("%d/%m/%Y %H:%M")
    except Exception:
        t = updated
    lines = [("🚨 มีจุดเกินเกณฑ์" if hot else "✅ ทุกจุดปกติ") + f" · เกณฑ์ {thr:.0f}°C",
             f"ข้อมูล ณ {t} น. · {len(temps)} จุด", ""]
    lines += [f"{'🔴' if v >= thr else '•'} {TA.label(tg)}  {v:.1f}°C" for tg, v in top]
    lines += ["", cfg["dashboard_url"]]
    return "\n".join(lines)


def handle_update(cfg, st, upd):
    """ประมวลผล 1 อัปเดตจาก Telegram (ปุ่มถูกกด หรือคำสั่ง /status)"""
    cq = upd.get("callback_query")
    if cq:
        who = (cq.get("from") or {}).get("first_name") or "ไม่ทราบชื่อ"
        if (cq.get("data") or "") == "ack":
            acknowledge(cfg, st, who)
            TA.call(cfg, "answerCallbackQuery",
                    {"callback_query_id": cq["id"], "text": "รับทราบแล้ว ✅"})
        else:
            TA.call(cfg, "answerCallbackQuery", {"callback_query_id": cq["id"]})
        return True

    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip().lower()
    chat = (msg.get("chat") or {}).get("id")
    if chat and text.startswith("/status"):
        send_msg(cfg, chat, status_text(cfg))
        return True
    if chat and text.startswith("/help"):
        send_msg(cfg, chat,
                 "คำสั่งที่ใช้ได้\n"
                 "/status — ดูอุณหภูมิล่าสุดเดี๋ยวนี้\n\n"
                 f"ระบบจะเตือนเองเมื่อมีจุดใดเกิน {cfg['threshold']}°C "
                 f"และเตือนซ้ำทุก {cfg.get('nag_minutes', 2)} นาที จนกว่าจะกดปุ่มรับทราบ")
        return True
    return False


def touch(**kw):
    """อ่านสถานะสดๆ แก้เฉพาะคีย์ที่ส่งมา แล้วเขียนกลับทันที

    ตัวอัปเดต (ทุก 5 นาที) กับ listener (ค้างไว้) เขียนไฟล์เดียวกัน ถ้าใครถือสถานะเก่า
    ไว้นานแล้วค่อยเขียนทับ ข้อมูลของอีกฝั่งจะหาย จึงต้องอ่าน-แก้-เขียน ให้สั้นที่สุดเสมอ
    """
    st = load()
    st.update(kw)
    save(st)
    return st


def poll_updates(cfg, timeout=0):
    """ดึงอัปเดตค้างท่อมาประมวลผล — โหลดสถานะใหม่ทุกครั้งกันเขียนทับกัน"""
    body = {"timeout": timeout, "limit": 50, "allowed_updates": ["callback_query", "message"]}
    off = load().get("offset")
    if off:
        body["offset"] = off
    r = TA.call(cfg, "getUpdates", body, timeout=timeout + 20)
    if not r or not r.get("ok"):
        return 0
    n = 0
    for upd in r.get("result", []):
        st = load()                       # สดเสมอ เผื่อตัวอัปเดตเพิ่งเขียนอะไรไว้
        st["offset"] = upd["update_id"] + 1
        try:
            if handle_update(cfg, st, upd):
                n += 1
        except Exception as e:
            print(f"(alarm) จัดการอัปเดตไม่ได้: {type(e).__name__} {e}")
        save(st)
    return n


def check_and_notify(data=None):
    """เรียกจาก update_temps.py ทุกรอบ — ออกแบบให้ไม่ทำให้ตัวเรียกพังไม่ว่าเกิดอะไรขึ้น"""
    try:
        cfg = TA.load_config()
        if not cfg or not cfg.get("enabled"):
            return
        temps, _updated = TA.read_temps(data)
        if not temps:
            return
        # ถ้าไม่ได้เปิด listener ไว้ ให้เช็คปุ่มที่ถูกกดเองตรงนี้ (เปิดไว้ = ปล่อยให้ listener ทำ)
        if not listener_alive(load()):
            poll_updates(cfg)

        thr = float(cfg["threshold"])
        hot = sorted([(t, v) for t, v in temps.items() if v >= thr], key=lambda x: -x[1])
        st = load()                       # โหลดใหม่ เผื่อเพิ่งมีคนกดรับทราบระหว่างนี้
        st = pump(cfg, st, hot)
        save(st)
    except Exception as e:
        print(f"(alarm) ข้ามการแจ้งเตือน: {type(e).__name__} {e}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="ตรวจ temps.json แล้วแจ้งถ้าเกิน")
    ap.add_argument("--status", action="store_true", help="พิมพ์สรุปสถานะออกจอ")
    ap.add_argument("--demo", action="store_true",
                    help="ส่งการแจ้งเตือนตัวอย่างพร้อมปุ่มรับทราบ (ไม่แตะสถานะจริง)")
    a = ap.parse_args()
    cfg = TA.load_config()
    if not cfg:
        sys.exit(1)
    if a.status:
        print(status_text(cfg))
    elif a.demo:
        temps, _ = TA.read_temps()
        top = sorted(temps.items(), key=lambda kv: -kv[1])[:2]
        fake = [(t, max(v, 81.0)) for t, v in top]
        demo_st = {"started": time.time(), "points": [[t, v] for t, v in fake]}
        send = broadcast(cfg, "🧪 ตัวอย่างการแจ้งเตือน (ไม่ใช่ของจริง)\n\n"
                         + alarm_text(cfg, fake, demo_st, 1), ACK_MARKUP)
        live = load()
        live["demo_messages"] = send          # ให้ปุ่มในข้อความตัวอย่างกดได้จริง
        save(live)
        print("ส่งตัวอย่างแล้ว:", send)
    else:
        check_and_notify()
