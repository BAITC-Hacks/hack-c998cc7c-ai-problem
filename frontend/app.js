/* Хаттама AI — frontend */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtT = (sec) => { sec = Math.max(0, Math.floor(sec || 0)); return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`; };

const STAGES = [
  ["upload", "Загрузка"],
  ["transcribe", "Распознавание речи"],
  ["diarize", "Диаризация"],
  ["extract", "Поручения"],
  ["summarize", "Саммари"],
  ["export", "Экспорт"],
];
const SPEAKER_COLORS = ["#2f9bff", "#20c997", "#ffb454", "#ff5c7a", "#b48bff", "#4dd0e1", "#ffd54f", "#ff8a65", "#a5d6a7", "#f8bbd0"];
const spColor = (n) => { let h = 0; for (const c of n) h = (h + c.charCodeAt(0)) % 997; return SPEAKER_COLORS[h % SPEAKER_COLORS.length]; };
const langBadge = (l) => l ? `<span class="chip">${esc(l.toUpperCase())}</span>` : "";

const state = { meeting: null, timer: null };

/* ---------------- tab switching (top level + inline) ---------------- */
$$(".tab").forEach((b) => b.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.remove("active")); b.classList.add("active");
  $$(".tab-pane").forEach((x) => x.classList.toggle("active", x.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "dash") loadDash();
}));
$$(".itab").forEach((b) => b.addEventListener("click", () => {
  $$(".itab").forEach((x) => x.classList.remove("active")); b.classList.add("active");
  $$(".itab-pane").forEach((x) => x.classList.toggle("active", x.id === "i-" + b.dataset.itab));
}));

/* ---------------- llm badge ---------------- */
async function loadHealth() {
  try {
    const r = await fetch("/api/health"); const h = await r.json();
    const on = h.llm && h.llm.available;
    const b = $("#llm-badge");
    b.className = "llm-badge " + (on ? "on" : "off");
    b.textContent = on ? `LLM: ${h.llm.provider}` : "Офлайн-режим (без LLM)";
    b.title = h.llm ? h.llm.detail : "";
  } catch { $("#llm-badge").textContent = "—"; }
}

/* ---------------- upload ---------------- */
const dz = $("#dropzone"), fi = $("#file-input");
dz.addEventListener("click", () => fi.click());
["dragover", "dragenter"].forEach((e) => dz.addEventListener(e, (ev) => { ev.preventDefault(); dz.classList.add("dragover"); }));
["dragleave", "drop"].forEach((e) => dz.addEventListener(e, (ev) => { ev.preventDefault(); dz.classList.remove("dragover"); }));
dz.addEventListener("drop", (ev) => { if (ev.dataTransfer.files[0]) pick(ev.dataTransfer.files[0]); });
fi.addEventListener("change", () => { if (fi.files[0]) pick(fi.files[0]); });

function pick(f) {
  $("#file-name").textContent = f.name; $("#upload-error").classList.add("hidden");
  $("#dropzone").classList.add("hidden"); $("#file-choosen").classList.remove("hidden");
  state.file = f;
}
$("#btn-reset").addEventListener("click", () => { state.file = null; fi.value = ""; $("#file-choosen").classList.add("hidden"); $("#dropzone").classList.remove("hidden"); });
$("#btn-upload").addEventListener("click", async () => {
  if (!state.file) return;
  const btn = $("#btn-upload"); btn.disabled = true;
  const fd = new FormData(); fd.append("file", state.file);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "Ошибка загрузки");
    beginProgress(j.meeting_id);
  } catch (e) { $("#upload-error").textContent = e.message; $("#upload-error").classList.remove("hidden"); }
  btn.disabled = false;
});

/* ---------------- progress ---------------- */
function beginProgress(id) {
  $("#upload-card").classList.add("hidden");
  $("#progress-card").classList.remove("hidden");
  $("#result-card").classList.add("hidden");
  $("#progress-steps").innerHTML = STAGES.map(([k, n]) =>
    `<div class="step" data-st="${k}"><span class="spinner"></span><div class="st-name">${n}</div><div class="st-state">ожидание</div></div>`).join("");
  $("#event-log").innerHTML = "";
  poll(id);
}
function poll(id) {
  clearInterval(state.timer);
  state.timer = setInterval(async () => {
    try {
      const r = await fetch("/api/meetings/" + id); const m = await r.json();
      if (!r.ok) throw new Error(m.detail);
      renderProgress(m);
      if (m.status === "done") { clearInterval(state.timer); renderResult(m); }
      if (m.status === "error") { clearInterval(state.timer); $("#event-log").insertAdjacentHTML("beforeend", `<div style="color:var(--danger)">Ошибка: ${esc(m.error)}</div>`); }
    } catch (e) { $("#event-log").insertAdjacentHTML("beforeend", `<div style="color:var(--danger)">${esc(e.message)}</div>`); }
  }, 1500);
}
function renderProgress(m) {
  const doneIdxs = new Set(m.events.map((e) => e.stage));
  const cur = m.stage;
  STAGES.forEach(([k], i) => {
    const el = document.querySelector(`.step[data-st="${k}"]`);
    if (!el) return;
    el.classList.remove("run", "done", "err");
    if (doneIdxs.has(k) || (m.status === "done" && i < STAGES.indexOf([m.stage || "export"]) )) el.classList.add("done");
    if (cur === k || (cur === "extract" && k === "transcribe" && m.status === "processing")) {}
    if (el.classList.contains("done")) {
      el.querySelector(".st-state").textContent = "готово";
      el.querySelector(".spinner").style.display = "none";
    }
  });
  // подсветка текущего этапа
  const curEl = document.querySelector(`.step[data-st="${cur}"]`);
  if (curEl) { curEl.classList.add("run"); curEl.querySelector(".st-state").textContent = "выполняется"; }
  (m.events || []).slice(-30).forEach((e) => {
    if (!document.querySelector(`#event-log [data-e="${e.ts}"]`)) {
      $("#event-log").insertAdjacentHTML("beforeend", `<div data-e="${e.ts}"><b>${esc(e.stage || "")}</b> · ${esc(e.message)}</div>`);
      $("#event-log").scrollTop = 9999;
    }
  });
}

/* ---------------- result ---------------- */
function renderResult(m) {
  state.meeting = m;
  $("#progress-card").classList.add("hidden");
  $("#result-card").classList.remove("hidden");
  const res = m.result || {};
  $("#result-meta").textContent = `${m.filename} · дата: ${m.created_at} · поручения: ${res.assignments ? res.assignments.length : 0} (${m.extract_mode || "?"}) · саммари: ${m.summary_mode || "?"}`;

  // поручения (актуальные из БД)
  const assigns = (m.assignments && m.assignments.length ? m.assignments : res.assignments) || [];
  $("#assign-empty").classList.toggle("hidden", assigns.length > 0);
  $("#assign-list").innerHTML = assigns.map((a, i) => {
    const st = a.status || "в работе";
    const overdue = a.overdue && st === "в работе";
    const badge = overdue ? `<span class="status-badge overdue">просрочено</span>`
      : `<span class="status-badge ${st === "выполнено" ? "done" : st === "в работе" ? "work" : "pause"}">${esc(st)}</span>`;
    return `<div class="assign" data-id="${a.id}">
      <div class="prio ${esc(a.priority || "medium")}"></div>
      <div style="flex:1">
        <div class="task">${esc(a.task)}</div>
        <div class="meta">
          <span class="chip">👤 ${esc(a.owner || a.speaker_label || "не указан")}</span>
          <span class="chip">⏱ ${esc(a.deadline || a.deadline_raw || "не указан")}</span>
          <span class="chip">🎤 ${esc(a.speaker_label || "—")}</span>
        </div>
        <div class="statusbar">${badge}
          <select data-aid="${a.id}">
            <option ${st === "в работе" ? "selected" : ""}>в работе</option>
            <option ${st === "выполнено" ? "selected" : ""}>выполнено</option>
          </select>
        </div>
      </div></div>`;
  }).join("");

  // саммари
  $("#summary-list").innerHTML = (res.summary || []).map((s) => `<li>${esc(s)}</li>`).join("");

  // транскрипт
  $("#transcript-list").innerHTML = (res.transcript || []).map((b) =>
    `<div class="turn">
       <span class="t-time">${fmtT(b.start)}–${fmtT(b.end)}</span>
       <span class="t-speaker" style="color:${spColor(b.speaker)}">${esc(b.speaker)}</span>
       <span class="t-text">${esc(b.text)}</span>
     </div>`).join("");

  $$(".statusbar select").forEach((sel) => sel.addEventListener("change", async (e) => {
    const aid = e.target.dataset.aid;
    await fetch(`/api/meetings/${m.id}/assignments/${aid}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: e.target.value }),
    });
    const mm = await (await fetch("/api/meetings/" + m.id)).json(); renderResult(mm);
  }));
}

/* ---------------- exports ---------------- */
$$("[data-export]").forEach((b) => b.addEventListener("click", async () => {
  const m = state.meeting; if (!m) return;
  const fmt = b.dataset.export;
  const url = fmt === "txt" ? `/api/meetings/${m.id}/protocol.txt` : `/api/meetings/${m.id}/export?format=${fmt}`;
  try {
    const r = await fetch(url); if (!r.ok) throw new Error((await r.json()).detail);
    const blob = await r.blob(); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `protocol_${m.id}.${fmt}`; a.click(); URL.revokeObjectURL(a.href);
  } catch (e) { alert("Ошибка экспорта: " + e.message); }
}));

/* ---------------- dashboard ---------------- */
async function loadDash() {
  try {
    const r = await fetch("/api/meetings"); const { meetings } = await r.json();
    const counts = { done: 0, work: 0, overdue: 0, all: meetings.length };
    meetings.forEach((me) => { if (me.status === "done") counts.done++; else if (me.status === "processing") counts.work++; });
    $("#dash-stats").innerHTML = `
      <div class="stat"><div class="n">${counts.all}</div><div class="l">совещаний</div></div>
      <div class="stat"><div class="n">${counts.done}</div><div class="l">готово</div></div>
      <div class="stat"><div class="n">${counts.work}</div><div class="l">в обработке</div></div>`;
    $("#dash-list").innerHTML = meetings.map((m) => {
      const badge = m.status === "done" ? `<span class="status-badge done">готово</span>`
        : m.status === "error" ? `<span class="status-badge overdue">ошибка</span>`
        : `<span class="status-badge work">${esc(m.status)}</span>`;
      const tasks = m.extract_mode ? "· поручения: LLM/rules" : "";
      return `<div class="ditem" data-mi="${m.id}">
        <div class="dhead">
          <span class="fname">${esc(m.filename)}</span> ${badge}
          <span class="stat" style="display:none"></span>
          <button class="btn ghost" data-open="${m.id}" style="padding:4px 10px; font-size:12px">открыть</button>
        </div>
        <div class="dsub">${esc(m.created_at)} · этап: ${esc(m.stage || "—")} ${tasks} ${m.error ? "· ошибка: " + esc(m.error) : ""}</div>
        <div class="atasks" id="tasks-${m.id}"></div>
      </div>`;
    }).join("");
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === "new"));
      $$(".tab-pane").forEach((x) => x.classList.toggle("active", x.id === "tab-new"));
      if (state.meeting && state.meeting.id === +b.dataset.open) { $("#result-card").classList.remove("hidden"); $("#progress-card").classList.add("hidden"); $("#upload-card").classList.add("hidden"); }
    }));
    // подгрузка заданий для готовых
    for (const m of meetings) {
      if (m.status !== "done") continue;
      const mm = await (await fetch("/api/meetings/" + m.id)).json();
      const el = $("#tasks-" + m.id); if (!el) continue;
      const assigns = (mm.assignments && mm.assignments.length ? mm.assignments : (mm.result || {}).assignments) || [];
      if (!assigns.length) { el.innerHTML = `<div class="atask"><span class="muted">поручений нет</span></div>`; continue; }
      el.innerHTML = assigns.map((a) => {
        const st = a.status || "в работе";
        const badge = a.overdue ? `<span class="status-badge overdue">просрочено</span>` : `<span class="status-badge ${st === "выполнено" ? "done" : "work"}">${esc(st)}</span>`;
        return `<div class="atask"><span class="t">${esc(a.task)}</span> ${badge}
          <select data-daid="${a.id}"><option ${st === "в работе" ? "selected" : ""}>в работе</option><option ${st === "выполнено" ? "selected" : ""}>выполнено</option></select></div>`;
      }).join("");
      el.querySelectorAll("select").forEach((sel) => sel.addEventListener("change", async (e) => {
        await fetch(`/api/meetings/${m.id}/assignments/${e.target.dataset.daid}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: e.target.value }) });
        loadDash();
      }));
    }
  } catch (e) { $("#dash-list").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

loadHealth();