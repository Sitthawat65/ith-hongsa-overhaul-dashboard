# ITH Hongsa — Overhaul Monitoring Dashboard

แดชบอร์ดติดตามความคืบหน้างาน **Overhaul มอเตอร์** ของสายพานลำเลียงและเครื่องจักร
(Progress Plan of Overhaul — Motor Line Conveyor & Machines) สำหรับ **Italian Thai Hongsa Co.,Ltd**

> ข้อมูล ณ วันที่ **20 มิถุนายน 2026** · สรุปจากชีต `MASTER` ของไฟล์ `MASTER OH# STP 20.06.2026.xlsx`

## เปิดใช้งาน

เปิดไฟล์ [`Dashboard.html`](Dashboard.html) ด้วยเว็บเบราว์เซอร์ได้ทันที (ดับเบิลคลิก)
— เป็นไฟล์ **self-contained** ฝังข้อมูลไว้ในตัว ไม่ต้องต่ออินเทอร์เน็ตและไม่ต้องติดตั้งอะไรเพิ่ม

## ภายในแดชบอร์ด

- **KPI การ์ด** — จำนวนมอเตอร์ทั้งหมด, Running, PRE OH, Finished, Stand by, เกินกำหนด OH, ใกล้ครบกำหนด, กำลังรวม (MW)
- **กราฟสถานะ** (donut) และ **กราฟยี่ห้อ** (ELIN / SIEMENS / WEG / WattDrive / MENZEL / ABB)
- **แถบความเร่งด่วนรอบ OH#2** — Overdue / Due soon / OK
- **กราฟตามจุดติดตั้ง** — SPD, BWE, CR, Belt, สถานีสายพาน ฯลฯ
- **Watchlist** รายการใกล้/เกินกำหนด พร้อมแถบ Life used %
- **ตารางทะเบียนมอเตอร์ 89 รายการ** — ค้นหา / กรอง (สถานะ, ยี่ห้อ, จุดติดตั้ง) / จัดเรียง / ไฮไลต์ตามความเร่งด่วน

## สรุปข้อมูล

| ตัวชี้วัด | ค่า |
|---|---|
| มอเตอร์ทั้งหมด | 89 |
| Running | 76 |
| PRE OH | 2 |
| Finished | 6 |
| Stand by | 5 |
| **เกินกำหนด OH#2 (Overdue)** | **6** (ทั้งหมดอยู่ที่ Spreader / SPD) |
| ใกล้ครบกำหนด (< 5,000 ชม.) | 7 |

## ไฟล์ในโปรเจกต์

| ไฟล์ | คำอธิบาย |
|---|---|
| `Dashboard.html` | แดชบอร์ดหลัก (เปิดใช้งานได้เลย) |
| `master_data.json` | ข้อมูลดิบ 89 รายการที่ดึงจากชีต MASTER |
| `README.md` | เอกสารนี้ |

---
จัดทำด้วย Claude Code
