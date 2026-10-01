const API = (window.API_BASE || "").replace(/\/$/, "");
const $ = s => document.getElementById(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const STEPS = ["Submitted", "Assigned", "In Progress", "Resolved"];
const MY = "civicai_mine";
let PIN = "", authed = false, timer;
const mine = () => { try { return JSON.parse(localStorage.getItem(MY)) || [] } catch { return [] } };
const fmt = d => new Date(d).toLocaleString("en-IN", {day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit"});
const cls = s => s.replace(" ", "-");

async function api(path, opt = {}) {
  const r = await fetch(API + path, {...opt, headers: {"Content-Type": "application/json", "X-Officer-Pin": PIN, ...(opt.headers || {})}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Request failed");
  return j;
}
function toast(m) { const t = $("toast"); t.textContent = m; t.className = "show"; setTimeout(() => t.className = "", 2600) }
function toggleTheme() { const r = document.documentElement; r.dataset.theme = (r.dataset.theme || (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light")) === "dark" ? "light" : "dark" }
function page(p) {
  document.querySelectorAll("section").forEach(s => s.classList.toggle("on", s.id === p));
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.p === p));
  if (p === "ana") analytics(); if (p === "mine") loadMine(); if (p === "dash" && authed) dash(); window.scrollTo(0, 0);
}
$("nav").onclick = e => { if (e.target.dataset.p) page(e.target.dataset.p) };

async function health() {
  const el = document.querySelector("header span[style]");
  try { await api("/api/health"); el.textContent = "● Backend connected"; el.style.color = "#69db7c" }
  catch { el.textContent = "● Backend offline"; el.style.color = "#ff8787" }
}
health();

$("d").oninput = () => {
  clearTimeout(timer); const t = $("d").value;
  if (t.length < 5) { $("live").innerHTML = "🤖 AI preview will appear as you type…"; return }
  timer = setTimeout(async () => { try {
    const a = await api("/api/analyze", {method: "POST", body: JSON.stringify({text: t + " " + $("loc").value})});
    $("live").innerHTML = `🤖 <b>${a.category}</b> → ${a.department} · <span class="chip ${a.priority}">${a.priority} priority</span> · confidence ${a.confidence}%`;
  } catch {} }, 350);
};

$("f").onsubmit = async e => {
  e.preventDefault(); const btn = e.target.querySelector("button"); btn.disabled = true; btn.textContent = "AI is analysing…";
  try {
    const {complaint: c} = await api("/api/complaints", {method: "POST", body: JSON.stringify({
      name: $("n").value, contact: $("c").value,
      location: $("loc").value + ($("spot").value ? " – " + $("spot").value : ""), description: $("d").value})});
    localStorage.setItem(MY, JSON.stringify([c.id, ...mine()]));
    e.target.reset(); $("live").textContent = "🤖 AI preview will appear as you type…";
    $("res").innerHTML = `<div class="card" style="border-color:var(--ok);margin-top:16px"><h3 style="margin-top:0">✅ Complaint submitted</h3><h2 style="color:var(--pri)">${c.id}</h2><p><span class="chip">${esc(c.category)}</span> <span class="chip ${c.priority}">${c.priority}</span> <span class="chip">SLA ${c.sla}</span></p><p><b>Routed to:</b> ${esc(c.department)}<br><b>Suggested action:</b> ${esc(c.action)}</p>${c.dup_of ? `<p class="mut">🔁 A similar issue is already reported (${c.dup_of}). Your report is grouped with it so the department sees one issue.</p>` : ""}<button class="btn s" onclick="openTrack('${c.id}')">Track now</button> <button class="btn s g" onclick="navigator.clipboard&&navigator.clipboard.writeText('${c.id}');toast('ID copied')">Copy ID</button></div>`;
    toast("Saved: " + c.id);
  } catch (x) { $("res").innerHTML = `<p style="color:var(--bad)">${esc(x.message)}</p>` }
  btn.disabled = false; btn.textContent = "Submit with AI Analysis →";
};

function view(c) {
  const i = STEPS.indexOf(c.status);
  return `<div style="margin-top:16px"><h3 style="margin:0">${c.id} <span class="chip st-${cls(c.status)}">${c.status}</span></h3><div class="bar"><i style="width:${(i+1)*25}%"></i></div>${c.escalated ? '<p><span class="chip esc">⚠ SLA breached – auto-escalated to senior officer</span></p>' : ""}${c.dup_of ? `<p class="mut">🔁 Grouped with ${c.dup_of} (duplicate detection)</p>` : ""}${c.reports > 1 ? `<p class="mut">👥 ${c.reports} citizens reported this issue</p>` : ""}<p>${esc(c.description)}</p><p class="mut">📍 ${esc(c.location)} · ${esc(c.category)} · ${esc(c.department)} · <span class="chip ${c.priority}">${c.priority}</span> · SLA ${c.sla}</p><div class="tl">${STEPS.map((s, k) => { const l = c.log.filter(x => x.s === s).pop(); return `<div class="${k <= i ? "" : "pend"}"><b>${s}</b>${l ? `<small>${fmt(l.t)} – ${esc(l.note)}</small>` : "<small>Pending</small>"}</div>` }).join("")}</div></div>`;
}
async function track() {
  const id = $("tid").value.trim().toUpperCase(); if (!id) return; $("tout").innerHTML = "Searching…";
  try { $("tout").innerHTML = view((await api("/api/complaints/" + encodeURIComponent(id))).complaint) }
  catch (x) { $("tout").innerHTML = `<p style="color:var(--bad)">${esc(x.message)}</p>` }
}
function openTrack(id) { $("tid").value = id; page("track"); track() }
$("tid").onkeydown = e => { if (e.key === "Enter") track() };

async function loadMine() {
  const ids = mine(); if (!ids.length) { $("mlist").innerHTML = '<p class="mut">No complaints yet.</p>'; return }
  try { const {complaints: a} = await api("/api/complaints/lookup?ids=" + ids.join(","));
    $("mlist").innerHTML = a.map(c => `<div class="mine" onclick="openTrack('${c.id}')"><span><b>${c.id}</b> · ${esc(c.description.slice(0, 60))}</span><span class="chip st-${cls(c.status)}">${c.status}</span></div>`).join("") || '<p class="mut">No complaints yet.</p>';
  } catch (x) { $("mlist").innerHTML = `<p style="color:var(--bad)">${esc(x.message)}</p>` }
}

let ALL = [];
async function login() {
  PIN = $("pin").value;
  try { await api("/api/complaints"); authed = true; $("lock").style.display = "none"; $("dbox").style.display = "block"; dash() }
  catch (x) { PIN = ""; toast(x.message) }
}
async function dash() {
  try { ALL = (await api("/api/complaints")).complaints } catch (x) { return toast(x.message) }
  const a = ALL, n = s => a.filter(x => x.status === s).length;
  $("stats").innerHTML = [["Total", a.length], ["Submitted", n("Submitted")], ["Assigned", n("Assigned")], ["In Progress", n("In Progress")], ["Resolved", n("Resolved")], ["High priority open", a.filter(x => x.priority === "High" && x.status !== "Resolved").length]].map(x => `<div class="stat"><b>${x[1]}</b><small>${x[0]}</small></div>`).join("");
  const q = $("q").value.toLowerCase(), fs = $("fs").value, fp = $("fp").value;
  const r = a.filter(x => (!fs || x.status === fs) && (!fp || x.priority === fp) && (!q || (x.id + x.name + x.description + x.category).toLowerCase().includes(q)));
  $("tbl").innerHTML = r.length ? `<table><tr><th>ID</th><th>Issue</th><th>Dept</th><th>Priority</th><th>Status</th></tr>${r.map(c => `<tr><td><b>${c.id}</b><br><small class="mut">${fmt(c.created)}</small></td><td>${c.escalated ? '<span class="chip esc">⚠ Escalated</span> ' : ""}${c.reports > 1 ? `<span class="chip dup">×${c.reports} reports</span> ` : ""}${c.dup_of ? `<span class="chip dup">Duplicate of ${c.dup_of}</span> ` : ""}${esc(c.description.slice(0, 90))}<br><small class="mut">${esc(c.name)} · ${esc(c.location)}</small></td><td>${esc(c.department)}</td><td><span class="chip ${c.priority}">${c.priority}</span></td><td><select onchange="setSt('${c.id}',this.value)" style="margin:0;min-width:120px">${STEPS.map(s => `<option ${s === c.status ? "selected" : ""}>${s}</option>`).join("")}</select></td></tr>`).join("")}</table>` : '<p class="mut">No complaints match.</p>';
}
async function setSt(id, s) { try { await api(`/api/complaints/${id}/status`, {method: "PATCH", body: JSON.stringify({status: s})}); toast(id + " → " + s); dash() } catch (x) { toast(x.message) } }
async function demo() { try { await api("/api/demo", {method: "POST"}); toast("Demo data loaded"); dash() } catch (x) { toast(x.message) } }
function csv() {
  const h = ["id","name","contact","location","category","department","priority","status","description"];
  const b = [h.join(",")].concat(ALL.map(c => h.map(k => '"' + String(c[k]).replace(/"/g, '""') + '"').join(","))).join("\n");
  const l = document.createElement("a"); l.href = URL.createObjectURL(new Blob([b], {type: "text/csv"})); l.download = "complaints.csv"; l.click();
}

function voice() {
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!R) return toast("Voice input needs Chrome/Edge");
  const r = new R(); r.lang = $("lang").value; r.interimResults = false; $("mic").textContent = "🎙 Listening…";
  r.onresult = e => { $("d").value += ($("d").value ? " " : "") + e.results[0][0].transcript; $("d").dispatchEvent(new Event("input")) };
  r.onend = () => $("mic").textContent = "🎤 Speak your complaint"; r.onerror = () => toast("Could not hear you, try again"); r.start();
}
function bars(el, rows) {
  const m = Math.max(1, ...rows.map(r => r[1]));
  $(el).innerHTML = rows.length ? rows.map(r => `<div class="arow"><span>${esc(r[0])}</span><div class="bar"><i style="width:${r[1] / m * 100}%"></i></div><b>${r[1]}</b></div>`).join("") : '<p class="mut">No data yet.</p>';
}
async function analytics() {
  try { const a = await api("/api/analytics");
    $("astats").innerHTML = [["Total complaints", a.total], ["Resolved", a.resolved], ["Resolution rate", a.resolution_rate + "%"], ["Avg. resolution", a.avg_hours + " h"], ["SLA compliance", a.sla_compliance + "%"], ["Auto-escalated", a.escalated], ["Duplicates merged", a.duplicates_merged]].map(x => `<div class="stat"><b>${x[1]}</b><small>${x[0]}</small></div>`).join("");
    bars("acat", a.by_category); bars("aloc", a.hotspots);
  } catch (x) { toast(x.message) }
}
