/**
 * ITH Maintenance Worker (Cloudflare Worker)
 * ------------------------------------------------------------------
 * ตัวกลางเล็กๆ ให้ปุ่มบนหน้าเว็บ (GitHub Pages) สั่งเปิด/ปิดโหมดงานซ่อมบำรุงได้
 * โดยไม่ต้องฝัง GitHub token ในหน้าเว็บ (token เก็บเป็น secret ฝั่ง Worker)
 *
 * รับ POST {mode, pin}:
 *   mode = pm | shift | relocate | normal
 *   pin  = รหัสที่ตั้งไว้ (secret MAINT_PIN)
 * แล้ว:
 *   1) ตรวจ PIN
 *   2) เขียน maintenance.json ลง repo ผ่าน GitHub Contents API
 *   3) แจ้ง Telegram
 *
 * ต้องตั้ง Secrets/Variables ใน Cloudflare:
 *   GITHUB_TOKEN       (secret)  fine-grained PAT: repo นี้ + Contents = Read/Write
 *   MAINT_PIN          (secret)  รหัสสั้นๆ กันคนอื่นกดมั่ว
 *   TELEGRAM_TOKEN     (secret)  token บอท (ตัวเดียวกับที่ใช้อยู่)
 *   TELEGRAM_CHAT_IDS  (secret)  chat id คั่นด้วยจุลภาค เช่น 6929839392,-5287516472
 *   GITHUB_REPO        (var, ไม่บังคับ)  ดีฟอลต์ Sitthawat65/ith-hongsa-overhaul-dashboard
 *   GITHUB_BRANCH      (var, ไม่บังคับ)  ดีฟอลต์ main
 */

const MODES = { pm: "PM Day", shift: "Shift Line Day", relocate: "Relocate Day" };

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "POST") return json({ error: "POST only" }, 405, cors);

    let body;
    try { body = await request.json(); } catch { return json({ error: "bad json" }, 400, cors); }

    const mode = String(body.mode || "").toLowerCase();
    const pin  = String(body.pin || "");

    if (!env.MAINT_PIN || pin !== env.MAINT_PIN)
      return json({ error: "PIN ไม่ถูกต้อง" }, 403, cors);

    let state;
    if (mode === "normal") state = { active: false, since: nowIso() };
    else if (MODES[mode]) state = { active: true, code: mode, mode: MODES[mode], since: nowIso() };
    else return json({ error: "mode ไม่ถูกต้อง" }, 400, cors);

    // ---- เขียน maintenance.json ลง repo ----
    const repo   = env.GITHUB_REPO   || "Sitthawat65/ith-hongsa-overhaul-dashboard";
    const branch = env.GITHUB_BRANCH || "main";
    const api    = `https://api.github.com/repos/${repo}/contents/maintenance.json`;
    const gh = {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "User-Agent": "ith-maint-worker",
      "Accept": "application/vnd.github+json",
    };

    let sha;
    const getRes = await fetch(`${api}?ref=${branch}&_=${Date.now()}`, { headers: gh });
    if (getRes.ok) { const cur = await getRes.json(); sha = cur.sha; }

    const content = JSON.stringify(state, null, 2) + "\n";
    const msg = mode === "normal" ? "maintenance: OFF (normal, web)" : `maintenance: ${state.mode} ON (web)`;
    const putRes = await fetch(api, {
      method: "PUT",
      headers: { ...gh, "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, content: btoa(content), sha, branch }),
    });
    if (!putRes.ok) {
      const detail = (await putRes.text()).slice(0, 300);
      return json({ error: "GitHub write failed", detail }, 502, cors);
    }

    // ---- แจ้ง Telegram (ล้มเหลวก็ไม่ทำให้ทั้ง request พัง) ----
    await notify(env, state).catch(() => {});

    return json({ ok: true, state }, 200, cors);
  },
};

function nowIso() {
  // เวลาไทย +07:00
  const d = new Date(Date.now() + 7 * 3600 * 1000);
  return d.toISOString().replace("Z", "+07:00");
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

async function notify(env, state) {
  const token = env.TELEGRAM_TOKEN;
  const ids = String(env.TELEGRAM_CHAT_IDS || "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  if (!token || !ids.length) return;
  const text = state.active
    ? `🔧 เข้าโหมดงานซ่อมบำรุง: ${state.mode} (สั่งจากเว็บ)\nพักแจ้งเตือน Server/ค่าค้างชั่วคราว (จุดร้อน ≥80°C ยังเตือนปกติ) จนกว่าจะกด กลับสู่ปกติ`
    : `✅ กลับสู่ปกติแล้ว (สั่งจากเว็บ) — ระบบแจ้งเตือนทำงานตามปกติ`;
  for (const id of ids) {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: id, text, disable_web_page_preview: true }),
    }).catch(() => {});
  }
}
