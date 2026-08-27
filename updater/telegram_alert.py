#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
แจ้งเตือนอุณหภูมิ Bearing Pulley เข้า Telegram
-----------------------------------------------
ใช้ Telegram Bot API — ฟรี ไม่จำกัดจำนวนข้อความ ไม่มีโควตารายเดือนแบบ LINE OA
จึงเตือนซ้ำทุก 15 นาทีได้โดยไม่ต้องกลัวค่าใช้จ่าย

ตั้งค่าครั้งแรก (ทำ 4 ขั้น):
  1. เปิด Telegram คุยกับ @BotFather -> /newbot -> ตั้งชื่อ -> ได้ token มา
  2. วาง token ลงใน updater/telegram_config.json ช่อง "token"
  3. ทักบอทของเราสัก 1 ข้อความ (หรือถ้าจะส่งเข้ากลุ่ม: เชิญบอทเข้ากลุ่ม แล้วพิมพ์อะไรก็ได้ในกลุ่ม)
  4. รัน  python telegram_alert.py --setup     <- จะไปหา chat id มาใส่ให้เอง
  แล้วลองส่งจริง:  python telegram_alert.py --test

ไฟล์ telegram_config.json ถูก gitignore ไว้ จะไม่ขึ้น GitHub (repo เป็น public ห้าม commit token)

ใช้งาน:
  python telegram_alert.py --setup    หา chat id จากข้อความที่ทักบอทไว้ แล้วบันทึกลง config
  python telegram_alert.py --test     ส่งข้อความทดสอบ
  python telegram_alert.py --check    ตรวจ temps.json ปัจจุบันแล้วแจ้งถ้าเกิน
                                      (ปกติ update_temps.py เรียกให้เองทุกรอบ)
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
CONFIG     = HERE / "telegram_config.json"
STATE      = HERE / ".telegram_alert_state.json"
TEMPS_JSON = REPO_DIR / "temps.json"
TZ = datetime.timezone(datetime.timedelta(hours=7))

API = "https://api.telegram.org/bot{token}/{method}"
FAULTY = 200          # สูงเกินจริง น่าจะเซนเซอร์ผิดปกติ
HOME_URL = "https://sitthawat65.github.io/ith-hongsa-overhaul-dashboard/home.html"

# ชื่อจุดวัดที่อ่านเข้าใจง่าย — ใช้ชุดเดียวกับ LINE/หน้าเว็บ ถ้าหาไม่เจอค่อยตั้งเอง
try:
    from line_alert import label            # noqa: F401  (ใช้ชื่อจุดชุดเดียวกันทุกช่องทาง)
except Exception:                            # pragma: no cover - เผื่อไฟล์หาย
    def label(tag):
        return tag.replace("_", " ")


# ---------------------------------------------------------------- config/state
def _config_from_env():
    """สร้าง config จาก environment variable — ใช้ตอนรันบนคลาวด์ที่ไม่มีไฟล์ config

    ตั้ง TELEGRAM_TOKEN และ TELEGRAM_CHAT_IDS (คั่นด้วยจุลภาค) เป็น GitHub Secrets
    """
    import os
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        return None
    ids = []
    for part in os.environ.get("TELEGRAM_CHAT_IDS", "").replace(" ", "").split(","):
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                pass
    return {"enabled": True, "token": token, "chat_ids": ids, "to": "",
            "threshold": float(os.environ.get("TEMP_THRESHOLD", 80)),
            "repeat_minutes": 15, "nag_minutes": 2, "notify_recovery": True,
            "snapshot_enabled": True,
            "snapshot_pages": ["SPD", "Tripper car", "BWE2"],
            "snapshot_mode": "edit", "snapshot_silent": True,
            "snapshot_new_message_minutes": 5,
            "dashboard_url": HOME_URL}


def load_config():
    if not CONFIG.exists():
        return _config_from_env()
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"(telegram) อ่าน telegram_config.json ไม่ได้: {e}")
        return None
    if not c.get("token"):
        print("(telegram) ยังไม่ได้ใส่ token ใน telegram_config.json")
        return None
    c.setdefault("enabled", True)
    c.setdefault("chat_ids", [])
    c.setdefault("threshold", 80)
    c.setdefault("repeat_minutes", 15)
    c.setdefault("notify_recovery", True)
    c.setdefault("dashboard_url", HOME_URL)
    return c


def save_config(c):
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    try:
        STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"(telegram) เขียน state ไม่ได้: {e}")


# ---------------------------------------------------------------- Telegram API
def call(cfg, method, payload=None, timeout=20):
    """เรียก Telegram Bot API คืน dict ผลลัพธ์ (หรือ None ถ้าพลาด)"""
    url = API.format(token=cfg["token"], method=method)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"(telegram) {method} ไม่สำเร็จ HTTP {e.code}: {detail}")
    except Exception as e:
        print(f"(telegram) {method} ไม่สำเร็จ: {type(e).__name__} {e}")
    return None


def send(cfg, text):
    """ส่งข้อความหาทุก chat ที่ตั้งไว้ คืน True ถ้าส่งสำเร็จอย่างน้อย 1 ปลายทาง"""
    chats = cfg.get("chat_ids") or []
    if not chats:
        print("(telegram) ยังไม่มี chat_ids — รัน  python telegram_alert.py --setup  ก่อน")
        return False
    ok = 0
    for chat in chats:
        r = call(cfg, "sendMessage", {
            "chat_id": chat,
            "text": text[:4000],
            "disable_web_page_preview": True,
        })
        if r and r.get("ok"):
            ok += 1
    if ok:
        print(f"(telegram) ส่งแล้ว {ok}/{len(chats)} ปลายทาง")
    return ok > 0


def discover_chats(cfg):
    """หา chat id จากข้อความล่าสุดที่มีคนทักบอทไว้ (ต้องทักก่อนอย่างน้อย 1 ข้อความ)"""
    r = call(cfg, "getUpdates", {"limit": 100, "timeout": 0})
    if not r or not r.get("ok"):
        return []
    found = {}
    for upd in r.get("result", []):
        msg = (upd.get("message") or upd.get("channel_post")
               or upd.get("edited_message") or {})
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        name = (chat.get("title")
                or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
                or chat.get("username") or "")
        found[cid] = f"{chat.get('type', '?')} · {name}".strip(" ·")
    return sorted(found.items(), key=lambda kv: kv[0])


# ---------------------------------------------------------------- ตรวจอุณหภูมิ
def read_temps(data=None):
    """คืน ({tag: value}, updated) จาก temps.json หรือจาก data ที่ส่งเข้ามา"""
    if data is None:
        try:
            data = json.loads(TEMPS_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"(telegram) อ่าน temps.json ไม่ได้: {e}")
            return {}, ""
    out = {}
    for cards in (data.get("groups") or {}).values():
        for it in cards:
            v = it.get("value")
            if isinstance(v, (int, float)):
                out[it.get("tag")] = float(v)
    return out, data.get("updated", "")


def build_message(hot, cfg):
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
    """ตรวจค่าปัจจุบัน แล้วแจ้ง Telegram ถ้าจำเป็น — เรียกจาก update_temps.py ได้เลย
       ออกแบบให้ไม่ทำให้ตัวเรียกพังไม่ว่าเกิดอะไรขึ้น"""
    try:
        cfg = load_config()
        if not cfg or not cfg.get("enabled"):
            return
        temps, _updated = read_temps(data)
        if not temps:
            return

        thr = float(cfg["threshold"])
        repeat = float(cfg["repeat_minutes"]) * 60
        now = time.time()
        state = load_state()

        hot = sorted([(t, v) for t, v in temps.items() if v >= thr], key=lambda x: -x[1])
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
            if send(cfg, build_message(due, cfg)):
                for t, _ in due:
                    state[t] = now
        save_state(state)
    except Exception as e:
        # แจ้งเตือนล้มเหลวต้องไม่ทำให้การอัปเดตอุณหภูมิพัง
        print(f"(telegram) ข้ามการแจ้งเตือน: {type(e).__name__} {e}")


# ---------------------------------------------------------------- command line
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true",
                    help="หา chat id จากข้อความที่ทักบอทไว้ แล้วบันทึกลง config")
    ap.add_argument("--test", action="store_true", help="ส่งข้อความทดสอบ")
    ap.add_argument("--check", action="store_true", help="ตรวจ temps.json แล้วแจ้งถ้าเกิน")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg:
        print("!! ยังตั้งค่าไม่ครบ — ใส่ token ใน updater/telegram_config.json ก่อน "
              "(ดูคำอธิบายหัวไฟล์)")
        sys.exit(1)

    if args.setup:
        me = call(cfg, "getMe")
        if me and me.get("ok"):
            print(f">> บอท: @{me['result'].get('username')} ({me['result'].get('first_name')})")
        else:
            print("!! token ใช้ไม่ได้ ตรวจอีกครั้งกับ @BotFather")
            sys.exit(1)
        chats = discover_chats(cfg)
        if not chats:
            print("!! ยังไม่เจอ chat — เปิด Telegram ทักบอทสัก 1 ข้อความ "
                  "(หรือเชิญบอทเข้ากลุ่มแล้วพิมพ์อะไรก็ได้) แล้วรัน --setup ใหม่")
            sys.exit(1)
        print(">> เจอ chat ดังนี้:")
        for cid, desc in chats:
            print(f"     {cid}  {desc}")
        cfg["chat_ids"] = [cid for cid, _ in chats]
        save_config(cfg)
        print(f">> บันทึกลง telegram_config.json แล้ว ({len(chats)} ปลายทาง)")
        print(">> ลองส่งจริง:  python telegram_alert.py --test")
        return

    if args.test:
        temps, updated = read_temps()
        top = sorted(temps.items(), key=lambda kv: -kv[1])[:3]
        detail = "\n".join(f"• {label(t)}  {v:.1f} °C" for t, v in top)
        ok = send(cfg, "🔔 ทดสอบการแจ้งเตือน Bearing Pulley Temp\n"
                       f"เกณฑ์แจ้งเตือน {cfg['threshold']}°C · เตือนซ้ำทุก "
                       f"{cfg['repeat_minutes']} นาที\n\n"
                       f"จุดที่ร้อนที่สุดตอนนี้:\n{detail}\n\n"
                       f"อัปเดตล่าสุด {updated}\n{cfg['dashboard_url']}")
        sys.exit(0 if ok else 1)

    if args.check:
        check_and_notify()
        return

    ap.print_help()


if __name__ == "__main__":
    main()
