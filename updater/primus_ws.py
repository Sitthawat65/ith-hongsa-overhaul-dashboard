#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
อ่านค่าอุณหภูมิจาก Primus ผ่าน WebSocket ตรงๆ — ไม่ต้องเปิดเบราว์เซอร์
---------------------------------------------------------------------
เดิมทีต้องเปิด Chromium ซ่อนไว้นอกจอ โหลดหน้าเว็บ Primus แล้วดักเฟรม socket.io
ซึ่งใช้เวลาราวนาทีต่อรอบ กินซีพียู และพังง่ายเวลาเบราว์เซอร์มีปัญหา

ตัวนี้ต่อ WebSocket ตรงไปที่เซิร์ฟเวอร์เลย ใช้เวลาไม่กี่วินาที

  endpoint จริงคือ  wss://primus.ith.co.th/socket/primus/v1/prisoft/?EIO=3&transport=websocket
  (ไม่ใช่ /socket.io/ ซึ่งเป็นตัวที่หน้าเว็บเรียกวนเปล่าๆ แล้วได้ HTML กลับมาตลอด)

ใช้ cookie ของ session ที่ล็อกอินไว้แล้ว (connect.sid + cf_clearance) เก็บใน
primus_session.json ซึ่ง gitignore ไว้ — เบราว์เซอร์จะถูกเรียกใช้ก็ต่อเมื่อ cookie หมดอายุ

โปรโตคอล engine.io v3 บน WebSocket:
    "0{...}"   handshake (บอก sid + pingInterval)
    "42[...]"  event    -> ["update_tag_value", "<json string>"]
    ส่ง "2" เป็น ping ทุก pingInterval มิฉะนั้นเซิร์ฟเวอร์จะตัดสาย
"""
import json, sys, time, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE    = pathlib.Path(__file__).resolve().parent
SESSION = HERE / "primus_session.json"
HOST    = "primus.ith.co.th"
WS_URL  = f"wss://{HOST}/socket/primus/v1/prisoft/?EIO=3&transport=websocket"


# ------------------------------------------------------------------ session
def save_session(cookies, ua):
    """เก็บ cookie + user-agent ไว้ใช้ต่อ (cf_clearance ผูกกับ user-agent จึงต้องเก็บคู่กัน)"""
    keep = [{"name": c["name"], "value": c["value"], "domain": c["domain"],
             "expires": c.get("expires", -1)}
            for c in cookies if c["domain"].lstrip(".").endswith("ith.co.th")]
    SESSION.write_text(json.dumps({"cookies": keep, "ua": ua, "saved": time.time()},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return len(keep)


def load_session():
    try:
        blob = json.loads(SESSION.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    jar = "; ".join(f"{c['name']}={c['value']}" for c in blob.get("cookies", []))
    return (jar or None), blob.get("ua")


def session_age_days():
    try:
        return (time.time() - json.loads(SESSION.read_text(encoding="utf-8"))["saved"]) / 86400
    except Exception:
        return None


# ------------------------------------------------------------------ อ่านค่า
def collect(wanted, enough=None, max_secs=20, quiet=False):
    """ต่อ WebSocket แล้วเก็บค่าจนกว่าจะพอ หรือหมดเวลา

    wanted : set ของชื่อ tag ที่สนใจ
    enough : ฟังก์ชัน(dict) -> True เมื่อได้ครบพอแล้ว (ไม่ใส่ = รอจนหมดเวลา)
    คืน {tag: {"value": float, "read_ms": int}} หรือ {} ถ้าต่อไม่ได้
    """
    try:
        import websocket                      # websocket-client
    except ImportError:
        if not quiet:
            print("(ws) ไม่มีไลบรารี websocket-client — ข้ามไปใช้เบราว์เซอร์")
        return {}

    # endpoint นี้ไม่ตรวจสอบตัวตนเลย ไม่มี cookie ก็อ่านค่าได้ (ทดสอบแล้ว 2026-08-27)
    # ยังส่ง cookie ไปด้วยถ้ามี เผื่อวันหลังฝั่ง Primus เปิดการตรวจสอบขึ้นมา
    jar, ua = load_session()
    hdr = [f"Origin: https://{HOST}"]
    if jar:
        hdr.append(f"Cookie: {jar}")
    hdr.append(f"User-Agent: {ua or 'ITH-BearingTemp/1.0'}")

    try:
        ws = websocket.create_connection(WS_URL, timeout=20, header=hdr, suppress_origin=True)
    except Exception as e:
        if not quiet:
            print(f"(ws) ต่อไม่ได้: {type(e).__name__} {e}")
        return {}

    latest, t0, ping_every, last_ping = {}, time.time(), 20.0, time.time()
    try:
        while time.time() - t0 < max_secs:
            try:
                ws.settimeout(3)
                msg = ws.recv()
            except Exception as e:
                if type(e).__name__ == "WebSocketTimeoutException":
                    msg = ""
                else:
                    if not quiet:
                        print(f"(ws) สายหลุด: {type(e).__name__} {e}")
                    break
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", "replace")

            if msg[:1] == "0":
                try:
                    ping_every = json.loads(msg[1:]).get("pingInterval", 25000) / 1000 * 0.8
                except Exception:
                    pass
            elif msg[:2] == "42":
                try:
                    name, raw = json.loads(msg[2:])
                    if name != "update_tag_value":
                        continue
                    payload = json.loads(raw)
                except Exception:
                    continue
                ts = payload.get("ts", 0)
                for dev in payload.get("table", []):
                    if str(dev.get("port")) == "999":      # ตัวจำลอง ไม่ใช่ค่าจริง
                        continue
                    try:
                        read_ms = int(dev.get("time") or ts)
                    except (TypeError, ValueError):
                        read_ms = ts
                    for d in dev.get("data", []):
                        n, v = d.get("name"), d.get("value")
                        if n not in wanted or v in (None, ""):
                            continue
                        try:
                            fv = float(v)
                        except (TypeError, ValueError):
                            continue
                        if n not in latest or read_ms >= latest[n][0]:
                            latest[n] = (read_ms, fv)
                if enough and enough({k: {"value": v, "read_ms": r}
                                      for k, (r, v) in latest.items()}):
                    break

            if time.time() - last_ping > ping_every:
                try:
                    ws.send("2")
                except Exception:
                    break
                last_ping = time.time()
    finally:
        try:
            ws.close()
        except Exception:
            pass

    if not quiet:
        print(f"(ws) อ่านได้ {len(latest)} tag ใน {time.time()-t0:.1f} วินาที")
    return {k: {"value": v, "read_ms": r} for k, (r, v) in latest.items()}


if __name__ == "__main__":
    import update_temps as U
    age = session_age_days()
    print(f"session อายุ {age:.1f} วัน" if age is not None else "ยังไม่มี session")
    vals = collect(U.WANTED_TAGS, enough=U.enough, max_secs=20)
    for g, tags in U.GROUP_TAGS.items():
        got = [t for t in tags if t in vals]
        print(f"  {g:5s} {len(got)}/{len(tags)}")
    for t in sorted(vals):
        print(f"     {t:20s} {vals[t]['value']:6.1f}")
