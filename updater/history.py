#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
เก็บประวัติอุณหภูมิย้อนหลังลง temps_history.json ให้หน้า chart.html พล็อตกราฟ
---------------------------------------------------------------------------
update_temps.py เขียน temps.json (ค่าล่าสุด) อยู่แล้วทุก ~5 นาที โมดูลนี้ถูก
เรียกต่อท้ายเพื่อ "ต่อแถว" ค่ารอบนั้นเข้าไฟล์ประวัติ แล้วตัดข้อมูลที่เก่ากว่า
KEEP_DAYS วันทิ้ง

รูปแบบไฟล์ (ออกแบบให้ git เก็บ diff ได้เล็ก: ต่อแถวท้ายไฟล์ ตัดหัวทิ้ง):
{
  "updated": "<iso ล่าสุด>",
  "step_min": 5,
  "keep_days": 30,
  "series": {
    "SPD": {
      "tags":   ["DCV_TC_L", ...],          # ลำดับจุดวัด (โตได้เมื่อมี tag ใหม่)
      "colors": ["#008000", ...],           # สีของแต่ละจุด (ดัชนีตรงกับ tags)
      "rows":   [["<iso>", 31.4, 35.7, ...], ...]   # เรียงเก่า -> ใหม่
    },
    ...
  }
}
แถวใหม่จะยาวเท่าจำนวน tags ปัจจุบันเสมอ ส่วนแถวเก่าที่สั้นกว่า (เพราะมี tag
เพิ่มภายหลัง) ให้ฝั่งหน้าเว็บอ่านค่าที่ขาดเป็น null
"""
import json, pathlib, datetime

HERE      = pathlib.Path(__file__).resolve().parent
REPO_DIR  = HERE.parent
HIST_JSON = REPO_DIR / "temps_history.json"
KEEP_DAYS = 30
STEP_MIN  = 5
TZ = datetime.timezone(datetime.timedelta(hours=7))


def _round(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _load():
    try:
        d = json.loads(HIST_JSON.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("series"), dict):
            return d
    except Exception:
        pass
    return {"updated": "", "step_min": STEP_MIN, "keep_days": KEEP_DAYS, "series": {}}


def _trim(rows, cutoff_iso):
    """ตัดแถวที่เก่ากว่า cutoff ทิ้ง (rows เรียงเก่า->ใหม่)"""
    out = []
    started = False
    for r in rows:
        if not started and (not r or r[0] < cutoff_iso):
            continue
        started = True
        out.append(r)
    return out


def append(data):
    """เพิ่มค่าจาก temps.json (dict) หนึ่งรอบเข้าไฟล์ประวัติ"""
    now_iso = data.get("updated") or datetime.datetime.now(TZ).isoformat(timespec="seconds")
    hist = _load()
    hist["step_min"] = STEP_MIN
    hist["keep_days"] = KEEP_DAYS
    series = hist["series"]

    for group, cards in (data.get("groups") or {}).items():
        s = series.setdefault(group, {"tags": [], "colors": [], "rows": []})
        tags, colors, rows = s["tags"], s["colors"], s["rows"]
        idx = {t: i for i, t in enumerate(tags)}

        # ค่าล่าสุดของรอบนี้ ต่อ tag
        vals = {}
        for c in cards:
            tag = c.get("tag")
            if not tag:
                continue
            vals[tag] = _round(c.get("value"))
            if tag not in idx:                       # tag ใหม่ -> เพิ่มเข้า schema
                idx[tag] = len(tags)
                tags.append(tag)
                colors.append(c.get("color") or "#8aa0b6")
            elif c.get("color"):
                colors[idx[tag]] = c.get("color")

        row = [now_iso] + [vals.get(t) for t in tags]

        # กันซ้ำ: ถ้ารอบนี้เวลาเท่าแถวสุดท้าย ให้ทับแทนต่อ (idempotent)
        if rows and rows[-1] and rows[-1][0] == now_iso:
            rows[-1] = row
        else:
            rows.append(row)

        cutoff = (datetime.datetime.now(TZ) - datetime.timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
        s["rows"] = _trim(rows, cutoff)

    hist["updated"] = now_iso
    HIST_JSON.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(s["rows"]) for s in series.values())
    return n
