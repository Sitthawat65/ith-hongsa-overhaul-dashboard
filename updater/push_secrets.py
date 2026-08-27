#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ส่งค่าจาก telegram_config.json ขึ้นไปเป็น GitHub Secrets ให้ workflow บนคลาวด์ใช้
-------------------------------------------------------------------------------
อ่าน token กับ chat_ids จากไฟล์ในเครื่อง แล้วส่งให้ `gh secret set` ทาง stdin
ค่าจริงไม่เคยถูกพิมพ์ออกจอ ไม่เคยอยู่ใน command line (จึงไม่ติดใน history)

รันเมื่อ: ตั้งค่าครั้งแรก หรือทุกครั้งที่ chat_ids เปลี่ยน (เช่นเพิ่มกลุ่มใหม่ด้วย /join)
    python push_secrets.py
"""
import json, pathlib, subprocess, sys, shutil

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE / "telegram_config.json"
REPO = "Sitthawat65/ith-hongsa-overhaul-dashboard"

GH = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"


def set_secret(name, value):
    """ส่งค่าทาง stdin — ไม่ผ่าน argument จึงไม่โผล่ใน process list หรือ shell history"""
    p = subprocess.run([GH, "secret", "set", name, "--repo", REPO],
                       input=value.encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ok = p.returncode == 0
    print(f"  {name:20s} {'ตั้งค่าแล้ว' if ok else 'ล้มเหลว: ' + p.stdout.decode('utf-8', 'replace')[:200]}")
    return ok


def main():
    if not CONFIG.exists():
        sys.exit("!! ไม่พบ telegram_config.json")
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    token = (c.get("token") or "").strip()
    ids = [str(x) for x in (c.get("chat_ids") or [])]
    if not token:
        sys.exit("!! ยังไม่ได้ใส่ token ใน telegram_config.json")
    if not ids:
        sys.exit("!! ยังไม่มี chat_ids — ทักบอทแล้วรัน telegram_alert.py --setup ก่อน")

    print(f"repo: {REPO}")
    print(f"token: ...{token[-4:]} (ความยาว {len(token)})")
    print(f"chat_ids: {len(ids)} แชท -> {', '.join(ids)}")
    print()
    ok = set_secret("TELEGRAM_TOKEN", token)
    ok = set_secret("TELEGRAM_CHAT_IDS", ",".join(ids)) and ok
    print()
    print(">> เรียบร้อย" if ok else "!! มีบางตัวตั้งไม่สำเร็จ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
