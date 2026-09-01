/**
 * ISO EE Plan Tracker — ที่เก็บข้อมูลกลางบน Google Sheets
 * ------------------------------------------------------------------
 * วิธีใช้ (ทำครั้งเดียว)
 *  1. วางโค้ดนี้ในตัวแก้ไข Apps Script แล้วกด Ctrl+S บันทึก
 *  2. เลือกฟังก์ชัน setupTest ในแถบบน แล้วกด "เรียกใช้ (Run)" หนึ่งครั้ง
 *     - จะขออนุญาตสิทธิ์ครั้งแรก → อนุญาต
 *     - โค้ดจะสร้างชีตเก็บข้อมูลให้เอง และพิมพ์ลิงก์ชีตในบันทึกการทำงาน
 *  3. กด  การทำให้ใช้งานได้ (Deploy) → การทำให้ใช้งานได้รายการใหม่
 *       ประเภท (Type)            = แอปพลิเคชันบนเว็บ (Web app)
 *       ดำเนินการในฐานะ (Execute as) = ฉัน (Me)
 *       ผู้ที่มีสิทธิ์เข้าถึง (Who has access) = ทุกคน (Anyone)
 *  4. กด Deploy → ก๊อป URL ของเว็บแอป (ลงท้าย /exec) ส่งกลับมา
 * ------------------------------------------------------------------
 */

var SHEET_NAME = 'iso_ee';

/** กุญแจสำหรับเขียนข้อมูล ต้องตรงกับที่ตั้งไว้ในหน้าเว็บ
 *  กันการยิงมั่วได้ระดับหนึ่ง แต่ไม่ใช่ระบบความปลอดภัยเต็มรูปแบบ */
var WRITE_KEY = 'ITH-ISOEE-2569';

var HEADERS = ['id','cycle','status','progress','owner','checker',
               'doc','reason','reasonNote','note','ack','at','by'];

/** หาไฟล์ Spreadsheet ที่จะใช้ — ใช้ได้ทั้งโปรเจกต์แบบผูกชีตและแบบเดี่ยว
 *  แบบเดี่ยว: จะสร้างไฟล์ชีตให้เองครั้งแรก แล้วจำ id ไว้ใน Script Properties */
function ss_() {
  var bound = SpreadsheetApp.getActiveSpreadsheet();
  if (bound) return bound;                        // เปิดจาก Sheet → ใช้อันนั้น

  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SS_ID');
  if (id) {
    try { return SpreadsheetApp.openById(id); } catch (e) { /* ถูกลบไปแล้ว สร้างใหม่ */ }
  }
  var created = SpreadsheetApp.create('ISO EE Data (ข้อมูลแดชบอร์ด)');
  props.setProperty('SS_ID', created.getId());
  return created;
}

function sheet_() {
  var ss = ss_();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    // บังคับทั้งคอลัมน์เป็นข้อความ ไม่งั้น Sheets แปลง "2026-09" เป็นวันที่
    sh.getRange(1, 1, sh.getMaxRows(), HEADERS.length).setNumberFormat('@');
    // ลบชีตเปล่า "ชีต1 / Sheet1" ที่ติดมาตอนสร้างไฟล์ใหม่ ถ้ามี
    var all = ss.getSheets();
    for (var i = 0; i < all.length; i++) {
      var nm = all[i].getName();
      if (all[i].getSheetId() !== sh.getSheetId() &&
          (nm === 'Sheet1' || nm === 'ชีต1') && all[i].getLastRow() === 0) {
        ss.deleteSheet(all[i]);
      }
    }
  }
  if (sh.getLastRow() === 0) sh.appendRow(HEADERS);
  return sh;
}

/** เขียนแถวโดยตั้งรูปแบบเป็นข้อความก่อน กัน Sheets แปลงค่าอัตโนมัติ */
function writeRow_(sh, rowNum, values) {
  var rng = sh.getRange(rowNum, 1, 1, HEADERS.length);
  rng.setNumberFormat('@');
  rng.setValues([values]);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** อ่านข้อมูลทั้งหมด — หน้าเว็บเรียกตอนเปิดและตอนรีเฟรช */
function doGet(e) {
  try {
    var sh = sheet_();
    var last = sh.getLastRow();
    if (last < 2) return json_({ ok: true, records: [], count: 0 });

    var rows = sh.getRange(2, 1, last - 1, HEADERS.length).getDisplayValues();
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      if (!rows[i][0]) continue;
      var o = {};
      for (var j = 0; j < HEADERS.length; j++) o[HEADERS[j]] = rows[i][j];
      o.progress = Number(o.progress) || 0;
      out.push(o);
    }
    return json_({ ok: true, records: out, count: out.length });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/** บันทึกข้อมูล — หน้าเว็บส่งมาทีละรายการตอนกดปุ่ม "บันทึก"
 *  ส่งเป็น text/plain เพื่อเลี่ยง CORS preflight ที่ Apps Script ไม่รองรับ */
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);

    var body = JSON.parse(e.postData.contents);
    if (body.key !== WRITE_KEY) return json_({ ok: false, error: 'bad key' });

    var recs = body.records || [];
    if (!recs.length) return json_({ ok: true, saved: 0 });

    var sh = sheet_();
    var last = sh.getLastRow();

    var index = {};
    if (last >= 2) {
      var keys = sh.getRange(2, 1, last - 1, 2).getValues();
      for (var i = 0; i < keys.length; i++) index[keys[i][0] + '||' + keys[i][1]] = i + 2;
    }

    var saved = 0;
    for (var r = 0; r < recs.length; r++) {
      var rec = recs[r];
      if (!rec.id || !rec.cycle) continue;

      var row = [];
      for (var h = 0; h < HEADERS.length; h++) {
        var v = rec[HEADERS[h]];
        row.push(v === undefined || v === null ? '' : v);
      }

      var k = rec.id + '||' + rec.cycle;
      if (index[k]) {
        writeRow_(sh, index[k], row);
      } else {
        writeRow_(sh, sh.getLastRow() + 1, row);
        index[k] = sh.getLastRow();
      }
      saved++;
    }
    return json_({ ok: true, saved: saved });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
  }
}

/** กดรันอันนี้ครั้งแรก เพื่อสร้างชีตและขออนุญาตสิทธิ์
 *  เปิดบันทึกการทำงาน (Ctrl+Enter) จะเห็นลิงก์ชีตที่สร้างให้ */
function setupTest() {
  var sh = sheet_();
  var url = ss_().getUrl();
  Logger.log('OK — ชีต "' + sh.getName() + '" พร้อมใช้งาน มี ' +
             Math.max(0, sh.getLastRow() - 1) + ' รายการ');
  Logger.log('เปิดชีตข้อมูลได้ที่: ' + url);
}
