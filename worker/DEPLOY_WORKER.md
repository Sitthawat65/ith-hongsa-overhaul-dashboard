# วิธี Deploy Maintenance Worker (Cloudflare) — ทำครั้งเดียว

ให้ปุ่มโหมดซ่อมบำรุงบน **หน้าเว็บ** สั่งเปิด/ปิดได้ทั้งระบบ (แทนการสั่งที่ PC)
ใช้เวลา ~10–15 นาที ทำครั้งเดียวจบ

---

## ขั้นที่ 1 — สร้าง GitHub Token (ให้ Worker เขียนไฟล์ได้)

1. เปิด https://github.com/settings/personal-access-tokens/new  (Fine-grained token)
2. **Token name:** `ith-maint-worker`
3. **Expiration:** 1 ปี (หรือตามต้องการ)
4. **Repository access** → *Only select repositories* → เลือก **`ith-hongsa-overhaul-dashboard`**
5. **Permissions** → *Repository permissions* → **Contents** = **Read and write**
6. กด **Generate token** → **คัดลอกค่า token เก็บไว้** (ขึ้นครั้งเดียว)

> ⚠️ อย่าเอา token ไปวางในหน้าเว็บ/แชท/สกรีนช็อต — ใช้เฉพาะวางใน Cloudflare (ขั้นที่ 4)

---

## ขั้นที่ 2 — สมัคร Cloudflare (ฟรี)

1. ไป https://dash.cloudflare.com/sign-up สมัครด้วยอีเมล (ฟรี ไม่ต้องผูกบัตร)
2. ยืนยันอีเมลให้เรียบร้อย

---

## ขั้นที่ 3 — สร้าง Worker แล้ววางโค้ด

1. เมนูซ้าย → **Workers & Pages** → **Create** → **Create Worker**
2. ตั้งชื่อ เช่น `ith-maint` → **Deploy** (มันจะสร้าง Worker เปล่าๆ ก่อน)
3. กด **Edit code** (หรือ **</> Edit**)
4. **ลบโค้ดเดิมทั้งหมด** แล้ววางเนื้อหาจากไฟล์ **`worker/maintenance-worker.js`** ลงไปทั้งหมด
5. กด **Deploy** (มุมขวาบน)

---

## ขั้นที่ 4 — ใส่ Secrets (ค่าลับ)

ที่หน้า Worker → **Settings** → **Variables and Secrets** → **Add**
เพิ่มทีละตัว (เลือกชนิด **Secret** สำหรับ 4 ตัวแรก) แล้วกด **Deploy/Save** :

| ชื่อ (Name) | ชนิด | ค่า |
|-------------|------|-----|
| `GITHUB_TOKEN` | Secret | token จากขั้นที่ 1 |
| `MAINT_PIN` | Secret | รหัสสั้นๆ ที่จะใช้กดปุ่ม เช่น `2580` |
| `TELEGRAM_TOKEN` | Secret | token บอท (ตัวเดียวกับที่ใช้อยู่ ดูใน `updater/telegram_config.json` ช่อง token) |
| `TELEGRAM_CHAT_IDS` | Secret | chat id คั่นจุลภาค เช่น `6929839392,-5287516472` |

*(ไม่ต้องใส่ GITHUB_REPO/GITHUB_BRANCH — Worker ใช้ค่าดีฟอลต์ให้แล้ว)*

---

## ขั้นที่ 5 — คัดลอก URL ของ Worker

ที่หน้า Worker จะเห็น URL แบบ:
```
https://ith-maint.<ชื่อบัญชีคุณ>.workers.dev
```
**คัดลอก URL นี้** แล้วส่งให้ผม (Claude) — ผมจะเอาไปใส่ในหน้าเว็บให้ (หรือถ้าจะใส่เอง: เปิดไฟล์ `Bearing-Pulley-Temp-Monitoring-ITH-CV.html` หาบรรทัด `const MAINT_WORKER_URL = '';` แล้ววาง URL ในเครื่องหมายคำพูด)

---

## ขั้นที่ 6 — ทดสอบ

1. เปิด Dashboard → กดปุ่ม **PM Day** → ใส่ **PIN** ที่ตั้งไว้
2. ควรเห็น: แบนเนอร์ "🔧 โหมดงานซ่อมบำรุง: PM Day" + **Telegram เด้ง**
3. กด **กลับสู่ปกติ** → ใส่ PIN → แบนเนอร์หาย + Telegram "✅ กลับสู่ปกติ"

เสร็จ! ตั้งแต่นี้กดจากเว็บได้ทุกที่ (มือถือ/แล็ปท็อป) โดยใส่ PIN

---

## หมายเหตุ
- **PIN** ใส่ครั้งเดียวต่อการเปิดเว็บ (จำไว้จนปิดแท็บ) — กันคนอื่นกดมั่ว
- ถ้า PIN ผิด ระบบจะไม่ทำอะไรและให้ใส่ใหม่
- ตัว **PC (`Back_to_Normal.bat` ฯลฯ) ยังใช้ได้อยู่** — คุมได้ทั้งจากเว็บและจาก PC (flag กลางตัวเดียวกัน)
- Cloudflare ฟรีให้ 100,000 request/วัน — เกินพอ (เรากดวันละไม่กี่ครั้ง)
