/* ============================================================
   แจ้งเตือนอุณหภูมิ Bearing Pulley เกินกำหนด — ใช้ร่วมกันทุกหน้า
   ------------------------------------------------------------
   - เฝ้าดู temps.json ทุก 60 วินาที (ไฟล์เล็ก ~1.5 KB)
   - จุดไหน >= 80 °C จะเด้งป๊อปอัปให้กด "รับทราบ"
   - กดรับทราบแล้ว ถ้ายังร้อนอยู่จะเตือนซ้ำอีกใน 15 นาที
   - ถ้าอุณหภูมิลดต่ำกว่า 80 การรับทราบจะถูกล้าง เริ่มนับใหม่เมื่อร้อนอีก
   - สถานะรับทราบเก็บใน localStorage จึงใช้ร่วมกันทุกหน้าในเว็บนี้
   ============================================================ */
(function () {
  'use strict';

  var ALARM      = 80;                 // °C เกินเท่านี้ = แจ้งเตือน
  var REALERT_MS = 15 * 60 * 1000;     // เตือนซ้ำทุก 15 นาที
  var POLL_MS    = 60 * 1000;          // ตรวจค่าทุก 1 นาที
  var FAULTY     = 200;                // สูงเกินจริง น่าจะเซนเซอร์ผิดปกติ
  var ACK_KEY    = 'ith_temp_ack_v1';
  var SND_KEY    = 'ith_temp_alert_sound';

  // ชื่อจุดวัดที่อ่านเข้าใจง่าย
  var LABELS = {
    RCV_DE_L:'Spreader · RCV DE (ซ้าย)',    RCV_DE_R:'Spreader · RCV DE (ขวา)',
    RCV_NDE_L:'Spreader · RCV NDE (ซ้าย)',  RCV_NDE_R:'Spreader · RCV NDE (ขวา)',
    DCV_DE_L:'Spreader · DCV DE (ซ้าย)',    DCV_DE_R:'Spreader · DCV DE (ขวา)',
    DCV_NDE_L:'Spreader · DCV NDE (ซ้าย)',  DCV_NDE_R:'Spreader · DCV NDE (ขวา)',
    DCV_TC_L:'Tripper car · DCV TC (ซ้าย)', DCV_TC_R:'Tripper car · DCV TC (ขวา)',
    BEND_L:'Tripper car · Bend (ซ้าย)',     BEND_R:'Tripper car · Bend (ขวา)',
    TAKE_UP_L:'Tripper car · Take-up (ซ้าย)', TAKE_UP_R:'Tripper car · Take-up (ขวา)'
  };
  function label(tag){ return LABELS[tag] || tag.replace(/_/g, ' '); }

  // ---------- สถานะการรับทราบ ----------
  function ackRead(){
    try { return JSON.parse(localStorage.getItem(ACK_KEY) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function ackWrite(o){ try { localStorage.setItem(ACK_KEY, JSON.stringify(o)); } catch (e) {} }

  var soundOn = localStorage.getItem(SND_KEY) !== 'off';
  var shown = [];              // จุดที่กำลังแสดงในป๊อปอัปตอนนี้
  var lastHot = [];            // จุดที่ร้อนอยู่ล่าสุด (ใช้กับแถบเตือนและตัวนับ)
  var origTitle = document.title;
  var titleTimer = null;

  // ---------- หน้าตา ----------
  var css = ''
   + '.tal-ov{position:fixed;inset:0;z-index:9998;background:rgba(6,10,16,.72);'
   +   'backdrop-filter:blur(2px);display:none;align-items:center;justify-content:center;padding:16px}'
   + '.tal-ov.on{display:flex}'
   + '.tal-bx{width:100%;max-width:460px;background:#16212e;color:#e7eef6;border:2px solid #e02424;'
   +   'border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,.55);overflow:hidden;'
   +   'font-family:"Segoe UI",Tahoma,Arial,sans-serif;animation:tal-pop .18s ease-out}'
   + '@keyframes tal-pop{from{transform:scale(.94);opacity:0}to{transform:scale(1);opacity:1}}'
   + '.tal-hd{background:#e02424;padding:14px 18px;display:flex;align-items:center;gap:10px}'
   + '.tal-hd .ic{font-size:24px;animation:tal-bl 1s steps(1,end) infinite}'
   + '@keyframes tal-bl{0%,49%{opacity:1}50%,100%{opacity:.25}}'
   + '.tal-hd b{font-size:16px;color:#fff;letter-spacing:.3px}'
   + '.tal-bd{padding:16px 18px}'
   + '.tal-bd .sub{font-size:12.5px;color:#8aa0b6;margin:0 0 12px;line-height:1.7}'
   + '.tal-it{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;'
   +   'background:rgba(224,36,36,.12);border:1px solid rgba(224,36,36,.35);margin-bottom:8px}'
   + '.tal-it .nm{flex:1;min-width:0;font-size:13.5px;font-weight:600}'
   + '.tal-it .nm small{display:block;font-weight:400;color:#ffb4b4;font-size:11px;margin-top:2px}'
   + '.tal-it .vl{font-size:20px;font-weight:800;color:#ff6b6b;font-variant-numeric:tabular-nums;white-space:nowrap}'
   + '.tal-ft{padding:0 18px 18px;display:flex;gap:10px;align-items:center}'
   + '.tal-ack{flex:1;padding:15px;border:0;border-radius:14px;background:#e02424;color:#fff;'
   +   'font-family:inherit;font-size:16px;font-weight:800;cursor:pointer}'
   + '.tal-ack:hover{background:#c81f1f}.tal-ack:active{transform:translateY(1px)}'
   + '.tal-snd{width:48px;height:48px;flex:none;border:1px solid #2a3a4d;border-radius:14px;'
   +   'background:#101a26;color:#cdd9e5;font-size:18px;cursor:pointer}'
   + '.tal-snd:hover{background:#1c2a3a}'
   + '.tal-bar{position:fixed;left:0;right:0;bottom:0;z-index:9997;display:none;'
   +   'align-items:center;gap:10px;padding:10px 16px;background:#7a1414;color:#ffdede;'
   +   'font-family:"Segoe UI",Tahoma,Arial,sans-serif;font-size:13px;font-weight:600;'
   +   'box-shadow:0 -6px 18px rgba(0,0,0,.35)}'
   + '.tal-bar.on{display:flex}'
   + '.tal-bar .dot{width:9px;height:9px;border-radius:50%;background:#ff4d4f;flex:none;'
   +   'animation:tal-bl 1s steps(1,end) infinite}'
   + '.tal-bar .cd{margin-left:auto;font-variant-numeric:tabular-nums;white-space:nowrap;color:#fff}'
   + '.tal-bar button{border:1px solid rgba(255,255,255,.35);background:rgba(255,255,255,.1);'
   +   'color:#fff;border-radius:999px;padding:6px 12px;font-family:inherit;font-size:12px;'
   +   'font-weight:700;cursor:pointer}'
   + '@media(max-width:520px){.tal-bar{font-size:12px;padding:9px 12px}.tal-bar .cd{width:100%;margin:4px 0 0}}';

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var ov = document.createElement('div');
  ov.className = 'tal-ov';
  ov.innerHTML =
      '<div class="tal-bx" role="alertdialog" aria-modal="true" aria-labelledby="talTitle">'
    +   '<div class="tal-hd"><span class="ic">🚨</span><b id="talTitle">อุณหภูมิเกินกำหนด</b></div>'
    +   '<div class="tal-bd"><p class="sub" id="talSub"></p><div id="talList"></div></div>'
    +   '<div class="tal-ft">'
    +     '<button class="tal-ack" id="talAck">รับทราบ (Acknowledge)</button>'
    +     '<button class="tal-snd" id="talSnd" title="เปิด/ปิดเสียงเตือน"></button>'
    +   '</div>'
    + '</div>';

  var bar = document.createElement('div');
  bar.className = 'tal-bar';
  bar.innerHTML = '<span class="dot"></span><span id="talBarTxt"></span>'
                + '<span class="cd" id="talBarCd"></span>'
                + '<button id="talBarShow">ดูรายละเอียด</button>';

  function mount(){
    document.body.appendChild(ov);
    document.body.appendChild(bar);
    document.getElementById('talAck').addEventListener('click', acknowledge);
    document.getElementById('talSnd').addEventListener('click', toggleSound);
    document.getElementById('talBarShow').addEventListener('click', function () {
      if (lastHot.length) popup(lastHot);
    });
    drawSound();
    poll();
    setInterval(poll, POLL_MS);
    setInterval(drawBar, 1000);
  }

  // ---------- เสียงเตือน ----------
  var actx = null;
  var siren = null;                    // ตัวจับเวลาเสียงเตือนวนซ้ำ
  var SIREN_MS = 2200;                 // เว้นระยะระหว่างชุดเสียง

  function startSiren(){
    stopSiren();
    beep();
    siren = setInterval(beep, SIREN_MS);   // ดังไปเรื่อยๆ จนกว่าจะกดรับทราบ
  }
  function stopSiren(){
    if (siren) { clearInterval(siren); siren = null; }
  }
  function beep(){
    if (!soundOn) return;
    try {
      if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
      if (actx.state === 'suspended') actx.resume();
      [0, 0.36, 0.72].forEach(function (t) {
        var o = actx.createOscillator(), g = actx.createGain();
        o.type = 'square'; o.frequency.value = 880;
        g.gain.setValueAtTime(0.0001, actx.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.18, actx.currentTime + t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + t + 0.24);
        o.connect(g); g.connect(actx.destination);
        o.start(actx.currentTime + t); o.stop(actx.currentTime + t + 0.26);
      });
    } catch (e) { /* เบราว์เซอร์อาจบล็อกเสียงจนกว่าจะมีการคลิกครั้งแรก */ }
  }
  function drawSound(){
    document.getElementById('talSnd').textContent = soundOn ? '🔊' : '🔇';
  }
  function toggleSound(){
    soundOn = !soundOn;
    try { localStorage.setItem(SND_KEY, soundOn ? 'on' : 'off'); } catch (e) {}
    drawSound();
    if (!soundOn) { stopSiren(); return; }
    if (ov.classList.contains('on')) startSiren(); else beep();
  }

  // ---------- ป๊อปอัป ----------
  function popup(items){
    shown = items.slice();
    var now = new Date();
    document.getElementById('talSub').innerHTML =
        'ตรวจพบเมื่อ <b>' + now.toLocaleString('th-TH', {hour:'2-digit', minute:'2-digit'})
      + ' น.</b> · เกณฑ์แจ้งเตือน ' + ALARM + ' °C<br>'
      + 'เสียงจะดังต่อเนื่องจนกว่าจะกด “รับทราบ” · ถ้ายังร้อนอยู่จะเตือนซ้ำอีกใน 15 นาที';
    document.getElementById('talList').innerHTML = items.map(function (it) {
      var faulty = it.v >= FAULTY
        ? '<small>ค่าสูงผิดปกติ — ควรตรวจสอบเซนเซอร์ด้วย</small>' : '';
      return '<div class="tal-it"><span class="nm">' + label(it.tag) + faulty + '</span>'
           + '<span class="vl">' + it.v.toFixed(1) + ' °C</span></div>';
    }).join('');
    ov.classList.add('on');
    startSiren();
    flashTitle(true);
  }
  function hidePopup(){
    stopSiren();
    ov.classList.remove('on');
    shown = [];
    flashTitle(false);
  }
  function acknowledge(){
    var acks = ackRead(), now = Date.now();
    shown.forEach(function (it) { acks[it.tag] = now; });
    ackWrite(acks);
    hidePopup();
    drawBar();
  }

  // แถบชื่อแท็บกะพริบ เผื่อผู้ใช้สลับไปแท็บอื่น
  function flashTitle(on){
    if (titleTimer) { clearInterval(titleTimer); titleTimer = null; document.title = origTitle; }
    if (!on) return;
    var flip = false;
    titleTimer = setInterval(function () {
      flip = !flip;
      document.title = flip ? '🚨 อุณหภูมิเกิน ' + ALARM + '°C!' : origTitle;
    }, 900);
  }

  // ---------- แถบสถานะล่าง ----------
  function drawBar(){
    if (!lastHot.length || ov.classList.contains('on')) { bar.classList.remove('on'); return; }
    var acks = ackRead(), soonest = Infinity;
    lastHot.forEach(function (it) {
      var a = acks[it.tag];
      if (a) soonest = Math.min(soonest, a + REALERT_MS - Date.now());
    });
    document.getElementById('talBarTxt').textContent =
      'ยังมีจุดร้อนเกิน ' + ALARM + '°C อยู่ ' + lastHot.length + ' จุด (รับทราบแล้ว)';
    var cd = document.getElementById('talBarCd');
    if (soonest === Infinity || soonest < 0) {
      cd.textContent = '';
    } else {
      var s = Math.floor(soonest / 1000), m = Math.floor(s / 60);
      cd.textContent = 'เตือนซ้ำใน ' + m + ':' + String(s % 60).padStart(2, '0');
    }
    bar.classList.add('on');
  }

  // ---------- ตรวจค่า ----------
  function evaluate(data){
    var map = {};
    var groups = (data && data.groups) || {};
    Object.keys(groups).forEach(function (g) {
      (groups[g] || []).forEach(function (it) { map[it.tag] = it.value; });
    });

    var hot = [];
    Object.keys(map).forEach(function (tag) {
      var v = Number(map[tag]);
      if (!isNaN(v) && v >= ALARM) hot.push({tag: tag, v: v});
    });
    hot.sort(function (a, b) { return b.v - a.v; });
    lastHot = hot;

    // ล้างการรับทราบของจุดที่เย็นลงแล้ว จะได้เตือนใหม่ทันทีถ้ากลับมาร้อนอีก
    var acks = ackRead(), changed = false;
    var hotSet = {};
    hot.forEach(function (it) { hotSet[it.tag] = true; });
    Object.keys(acks).forEach(function (tag) {
      if (!hotSet[tag]) { delete acks[tag]; changed = true; }
    });
    if (changed) ackWrite(acks);

    if (!hot.length) { hidePopup(); bar.classList.remove('on'); return; }

    var now = Date.now();
    var due = hot.filter(function (it) {
      var a = acks[it.tag];
      return !a || (now - a) >= REALERT_MS;
    });

    if (due.length) {
      // ถ้าป๊อปอัปเปิดอยู่แล้วด้วยรายการเดิม ไม่ต้องเด้งซ้ำ
      var same = shown.length === due.length && shown.every(function (s, i) {
        return s.tag === due[i].tag && s.v === due[i].v;
      });
      if (!same) popup(due);
    }
    drawBar();
  }

  function poll(){
    fetch('temps.json?_=' + Date.now(), {cache: 'no-store'})
      .then(function (r) { return r.json(); })
      .then(evaluate)
      .catch(function (e) { console.warn('[temp-alert] อ่าน temps.json ไม่ได้', e); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
