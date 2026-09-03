#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตั้ง/ยกเลิก "โหมดงานซ่อมบำรุง" ที่แชร์ให้ทุกคนเห็นตรงกัน
  - เขียน maintenance.json (flag กลาง) แล้ว push ขึ้น GitHub
  - แจ้ง Telegram ตอนเริ่ม/จบ
  - หน้าเว็บ + Chart + snapshot ใน Telegram จะโชว์ชื่อโหมด (PM Day/Shift/Relocate)
    แทนป้าย "ค่าเก่า/Server Error" จนกว่าจะสั่ง normal

ใช้งาน (บน PC ที่ clone repo ไว้):
    python maintenance.py pm         # เข้าโหมด PM Day
    python maintenance.py shift      # เข้าโหมด Shift Line Day
    python maintenance.py relocate   # เข้าโหมด Relocate Day
    python maintenance.py normal     # กลับสู่ปกติ
    python maintenance.py status     # ดูสถานะปัจจุบัน
(ปกติจะกดผ่านไฟล์ .bat: PM_Day.bat / Shift_Line_Day.bat / Relocate_Day.bat / Back_to_Normal.bat)
"""
import json, os, sys, ssl, subprocess, datetime, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE  = pathlib.Path(__file__).resolve().parent
REPO  = HERE.parent
MFILE = REPO / "maintenance.json"
TZ    = datetime.timezone(datetime.timedelta(hours=7))
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

MODES = {
    "pm":       "PM Day",
    "shift":    "Shift Line Day",
    "relocate": "Relocate Day",
}

# ปิด verify SSL ถ้าอยู่หลัง proxy ของโรงงาน (เหมือน update_temps.py)
if os.environ.get("TELEGRAM_INSECURE_SSL") == "1" or os.environ.get("PYTHONHTTPSVERIFY") == "0":
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass


def _git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          creationflags=CREATE_NO_WINDOW,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def write_state(state):
    MFILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def commit_push(state, msg):
    """เขียน maintenance.json แล้ว push — ทน remote นำหน้า (self-heal เหมือน updater)"""
    try:
        write_state(state)
        _git("add", "maintenance.json")
        _git("commit", "-m", msg)                       # 'nothing to commit' = ไม่เป็นไร
        if _git("push", "origin", "main").returncode != 0:
            if _git("pull", "--rebase", "origin", "main").returncode != 0:
                _git("rebase", "--abort")
                _git("fetch", "origin", "main")
                _git("reset", "--hard", "origin/main")
                write_state(state)                       # เขียนใหม่หลัง reset
                _git("add", "maintenance.json")
                _git("commit", "-m", msg)
            _git("push", "origin", "main")
        print(">> อัปเดต maintenance.json ขึ้น GitHub แล้ว")
    except Exception as e:  # noqa: BLE001
        print("(git) ผิดพลาด:", e)


def notify(text):
    """ส่ง Telegram ผ่าน config เดิม (telegram_config.json) — ล้มเหลวก็ไม่ทำให้ทั้งงานพัง"""
    try:
        sys.path.insert(0, str(HERE))
        import telegram_alert
        cfg = telegram_alert.load_config()
        if cfg:
            telegram_alert.send(cfg, text)
        else:
            print("(telegram) ไม่มี config — ข้ามการแจ้งเตือน")
    except Exception as e:  # noqa: BLE001
        print("(telegram) ข้าม:", e)


def read_state():
    try:
        return json.loads(MFILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False}


def now_iso():
    return datetime.datetime.now(TZ).isoformat(timespec="seconds")


def main():
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()

    if arg == "status":
        s = read_state()
        print(json.dumps(s, ensure_ascii=False))
        return

    if arg in MODES:
        mode = MODES[arg]
        state = {"active": True, "code": arg, "mode": mode, "since": now_iso()}
        since_h = datetime.datetime.fromisoformat(state["since"]).strftime("%d/%m %H:%M")
        notify(f"🔧 เข้าโหมดงานซ่อมบำรุง: {mode}\n"
               f"เริ่ม {since_h} น. — พักแจ้งเตือน Server/ค่าค้างชั่วคราว "
               f"(จุดร้อน ≥80°C ยังเตือนปกติ) จนกว่าจะกด กลับสู่ปกติ")
        commit_push(state, f"maintenance: {mode} ON")
        print(f">> เข้าโหมด: {mode}")
        return

    if arg == "normal":
        prev = read_state()
        state = {"active": False, "since": now_iso()}
        was = prev.get("mode") or "งานซ่อมบำรุง"
        notify(f"✅ กลับสู่ปกติแล้ว (จบ {was}) — ระบบแจ้งเตือนทำงานตามปกติ")
        commit_push(state, "maintenance: OFF (normal)")
        print(">> กลับสู่ปกติ")
        return

    print("ใช้: python maintenance.py  pm | shift | relocate | normal | status")
    sys.exit(2)


if __name__ == "__main__":
    main()
