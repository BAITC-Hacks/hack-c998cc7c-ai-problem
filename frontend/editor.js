import {
  state,
  t,
  esc,
  $,
  $$,
  time,
  notify,
  api,
  json,
  field,
  input,
  textarea,
  options,
  dirty,
  reason,
} from "./shared.js";
import { protocolPreview, dateLabel } from "./views.js";

function contentChanged() {
  state.contentDirty = true;
  dirty();
}

function syncReview() {
  if (!state.draft || !$("#reviewed")) return;
  $("#reviewed").checked = state.draft.reviewed;
  $("#reviewed").disabled = state.contentDirty;
  $$("[data-confirm]").forEach(el => {
    el.checked = state.draft.assignments[el.dataset.confirm].review === "confirmed";
    el.disabled = state.contentDirty;
  });
  const confirmed = state.draft.assignments.filter(a => a.review === "confirmed").length;
  const total = state.draft.assignments.length;
  const progress = $("#review-progress");
  if (progress) progress.textContent = t(`Тексерілген тапсырмалар: ${confirmed} / ${total}`, `Проверено поручений: ${confirmed} из ${total}`);
  const bar = $("#review-progress-bar");
  if (bar) bar.style.width = total ? `${(confirmed / total) * 100}%` : "0%";
  const hint = $("#review-hint");
  if (hint) hint.textContent = state.contentDirty ? t("Алдымен өзгерістерді сақтаңыз, содан кейін тексеруді растаңыз.", "Сначала сохраните правки, затем подтвердите проверку.") : t("Дереккөзді және тапсырмаларды тексеріп, нұсқаны бекітіңіз.", "Сверьте источник и поручения, затем утвердите версию.");
  if ($("#save")) $("#save").disabled = !state.dirty;
  if ($("#discard")) $("#discard").disabled = !state.dirty;
  if ($("#approve")) $("#approve").disabled = state.contentDirty || !state.draft.reviewed || confirmed !== total;
}
document.addEventListener("draftchange", syncReview);

function evidenceList(item, index, type) {
  return `<div>${item.evidence.map((e, evidenceIndex) => `<div class="evidence-row"><button class="evidence" data-seek="${esc(e.segment_id)}">${time(e.start)}–${time(e.end)} · «${esc(e.quote)}»</button><button class="compact" data-remove-evidence="${type}:${index}:${evidenceIndex}" aria-label="${t("Дәйексөзді жою", "Удалить доказательство")} ${evidenceIndex + 1}">×</button></div>`).join("")}</div><label class="field">${t("Дәйексөзді қосу / жаңарту", "Добавить / обновить доказательство")}<select data-evidence="${type}:${index}"><option value="">${t("Сегментті таңдаңыз", "Выберите сегмент")}</option>${state.draft.transcript.map((s, i) => `<option value="${i}">${esc(time(s.start) + " " + s.text.slice(0, 90))}</option>`).join("")}</select></label>`;
}

function tasks() {
  return (
    `<button id="add-task">+ ${t("Қолмен тапсырма қосу", "Добавить поручение вручную")}</button>` +
    state.draft.assignments
      .map(
        (a, i) => `<article class="task">
<div class="toolbar"><strong>${i + 1}. ${t("Тапсырма", "Поручение")}</strong><span class="badge">${esc(a.origin)}</span><span class="spacer"></span><button data-delete-task="${i}">${t("Жою", "Удалить")}</button></div>
${field(t("Әрекет", "Действие"), textarea(a.action, `data-task="${i}:action"`))}
${field(t("Күтілетін нәтиже", "Ожидаемый результат"), input(a.expected_result, `data-task="${i}:expected_result"`))}
<div class="grid">${field(t("Орындаушы", "Исполнитель"), input(a.owner, `data-task="${i}:owner"`))}${field(t("Бастапқы мерзім", "Исходный срок"), input(a.deadline_raw, `data-task="${i}:deadline_raw"`))}${field(t("Нақты күн", "Нормализованная дата"), input(a.deadline, `type="date" data-task="${i}:deadline"`))}${field(
          t("Орындалу күйі", "Статус исполнения"),
          `<select data-task="${i}:status">${options(
            [
              ["open", t("Ашық", "Открыто")],
              ["in_progress", t("Орындалуда", "В работе")],
              ["done", t("Орындалды", "Выполнено")],
              ["cancelled", t("Күші жойылды", "Отменено")],
            ],
            a.status,
          )}</select>`,
        )}</div>
${a.uncertainty.length ? `<p class="notice">${t("Тексеру себептері", "Причины проверки")}: ${esc(a.uncertainty.map(reason).join("; "))}</p>` : ""}
${evidenceList(a, i, "task")}
${["owner", "deadline", "expected_result"].map((f) => `<label class="check"><input type="checkbox" data-missing="${i}:${f}" ${a.unspecified.includes(f) ? "checked" : ""}>${t("Жазбада көрсетілмеген", "В записи не указано")}: ${esc({ owner: t("орындаушы", "исполнитель"), deadline: t("мерзім", "срок"), expected_result: t("нәтиже", "результат") }[f])}</label>`).join("")}
<label class="check"><input type="checkbox" data-confirm="${i}" ${a.review === "confirmed" ? "checked" : ""}>${t("Тапсырма мен дәлелдерін тексердім", "Поручение и доказательства проверены")}</label>
</article>`,
      )
      .join("")
  );
}

function decisions() {
  return (
    `<button id="add-decision">+ ${t("Шешім / ұсыныс қосу", "Добавить решение / предложение")}</button>` +
    state.draft.decisions
      .map(
        (a, i) =>
          `<article class="task">${field(t("Мәтін", "Текст"), textarea(a.text, `data-decision="${i}:text"`))}${field(
            t("Түрі", "Тип"),
            `<select data-decision="${i}:kind">${options(
              [
                ["decision", t("Шешім", "Решение")],
                ["proposal", t("Ұсыныс", "Предложение")],
                ["question", t("Сұрақ", "Вопрос")],
              ],
              a.kind,
            )}</select>`,
          )}${evidenceList(a, i, "decision")}<button data-delete-decision="${i}">${t("Жою", "Удалить")}</button></article>`,
      )
      .join("")
  );
}

function right() {
  const body =
    state.tab === "tasks"
      ? tasks()
      : state.tab === "decisions"
        ? decisions()
        : `${field(t("Қысқаша түйін — әр тармақ жеке жолда", "Резюме — каждый пункт с новой строки"), textarea(state.draft.summary.join("\n"), 'id="summary-text" rows="9"'))}${field(t("Ашық сұрақтар — әрқайсысы жеке жолда", "Открытые вопросы — каждый с новой строки"), textarea(state.draft.questions.join("\n"), 'id="questions-text" rows="5"'))}<p class="muted">${t("RULES режимінде түйін тек айқын шешімдерден құралады. Мәтінді тыңдап толықтырыңыз.", "В RULES резюме состоит только из явных решений. Дополните его после прослушивания.")}</p>`;
  $("#right-content").innerHTML = body;
  $$("[data-task]").forEach(
    (el) =>
      (el.oninput = () => {
        const [i, k] = el.dataset.task.split(":");
        state.draft.assignments[i][k] = k === "action" || k === "status" ? el.value : el.value || null;
        if (k !== "status") state.draft.assignments[i].review = "needs_review";
        if (k === "status") dirty(); else contentChanged();
      }),
  );
  $$("[data-missing]").forEach(
    (el) =>
      (el.onchange = () => {
        const [i, k] = el.dataset.missing.split(":");
        const a = state.draft.assignments[i];
        a.unspecified = a.unspecified.filter((x) => x !== k);
        if (el.checked) a.unspecified.push(k);
        dirty();
      }),
  );
  $$("[data-confirm]").forEach(
    (el) =>
      (el.onchange = () => {
        state.draft.assignments[el.dataset.confirm].review = el.checked
          ? "confirmed"
          : "needs_review";
        dirty();
      }),
  );
  $$("[data-decision]").forEach(
    (el) =>
      (el.oninput = () => {
        const [i, k] = el.dataset.decision.split(":");
        state.draft.decisions[i][k] = el.value;
        state.draft.reviewed = false;
        contentChanged();
      }),
  );
  $$("[data-delete-task]").forEach(
    (el) =>
      (el.onclick = () => {
        state.draft.assignments.splice(+el.dataset.deleteTask, 1);
        state.draft.reviewed = false;
        contentChanged();
        right();
      }),
  );
  $$("[data-delete-decision]").forEach(
    (el) =>
      (el.onclick = () => {
        state.draft.decisions.splice(+el.dataset.deleteDecision, 1);
        state.draft.reviewed = false;
        contentChanged();
        right();
      }),
  );
  $$("[data-evidence]").forEach(
    (el) =>
      (el.onchange = () => {
        if (el.value === "") return;
        const [type, i] = el.dataset.evidence.split(":");
        const a =
          type === "task"
            ? state.draft.assignments[i]
            : state.draft.decisions[i];
        const s = state.draft.transcript[+el.value];
        a.evidence = a.evidence.filter((e) => e.segment_id !== s.id);
        a.evidence.push({
          segment_id: s.id,
          quote: s.text,
          start: s.start,
          end: s.end,
        });
        if (type === "task") a.review = "needs_review"; else state.draft.reviewed = false;
        contentChanged();
        right();
      }),
  );
  $$("[data-remove-evidence]").forEach(el => {
    el.onclick = () => {
      const [type, index, evidenceIndex] = el.dataset.removeEvidence.split(":");
      const item = type === "task" ? state.draft.assignments[index] : state.draft.decisions[index];
      item.evidence.splice(Number(evidenceIndex), 1);
      if (type === "task") item.review = "needs_review";
      else state.draft.reviewed = false;
      contentChanged();
      right();
    };
  });
  $$("[data-seek]").forEach((el) => (el.onclick = () => seek(el.dataset.seek)));
  if ($("#add-task"))
    $("#add-task").onclick = () => {
      state.draft.assignments.push({
        id: crypto.randomUUID(),
        action: "",
        expected_result: null,
        owner: null,
        deadline_raw: null,
        deadline: null,
        evidence: [],
        review: "needs_review",
        uncertainty: [],
        unspecified: [],
        status: "open",
        origin: "manual",
      });
      contentChanged();
      right();
    };
  if ($("#add-decision"))
    $("#add-decision").onclick = () => {
      state.draft.decisions.push({ text: "", kind: "decision", evidence: [] });
      state.draft.reviewed = false;
      contentChanged();
      right();
    };
  ["summary", "questions"].forEach((k) => {
    const el = $("#" + k + "-text");
    if (el)
      el.oninput = () => {
        state.draft[k] = el.value.split("\n").filter((x) => x.trim());
        state.draft.reviewed = false;
        contentChanged();
      };
  });
  syncReview();
}

function seek(id) {
  const s = state.draft.transcript.find((s) => s.id === id);
  if (!s) return;
  $("#player").currentTime = s.start;
  $$(".segment").forEach((el) =>
    el.classList.toggle("selected", el.dataset.segment === id),
  );
  const el = $$(".segment").find((el) => el.dataset.segment === id);
  el?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
}

export function renderEditor(m, preserved = {}) {
  state.meeting = m;
  state.draft = structuredClone(preserved.draft || m.draft);
  state.dirty = preserved.dirty || false;
  state.contentDirty = preserved.contentDirty || false;
  const d = state.draft;
  const speakers = [...new Set(d.transcript.map(s => s.speaker).filter(Boolean))];
  const hue = s => {
    if (!s) return "";
    const i = speakers.indexOf(s);
    if (i < 0) return "";
    return `style="--sp:${Math.round((i * 360) / Math.max(speakers.length, 1)) % 360}"`;
  };
  $("#app").innerHTML =
    `<fieldset id="editor-fields"><div class="toolbar"><button id="back">← ${t("Кездесулер", "Совещания")}</button><span class="badge">${esc(m.metadata.mode)}</span><span class="spacer"></span><span>${t("Жоба", "Черновик")} · r${m.revision}</span></div><h1>${esc(m.metadata.title)}</h1><p class="muted">${esc(dateLabel(m.metadata.meeting_at, m.metadata.timezone))} · ${esc(m.metadata.timezone)} · ${esc(m.metadata.participants.join(", "))}</p>
 ${m.error ? `<p class="notice error">${esc(m.error)}</p>` : ""}
 <div class="toolbar version-bar"><label>${t("Экспорт нұсқасы", "Версия для экспорта")} <select id="version"><option value="">${t("Ағымдағы жоба", "Текущий черновик")}</option>${m.versions.map((v) => `<option value="${v.id}">v${v.revision} · ${esc(v.created_at.slice(0, 16))}</option>`).join("")}</select></label><label class="check"><input id="with-transcript" type="checkbox" checked>${t("Транскриптпен", "С транскриптом")}</label><button data-export="docx">DOCX ↓</button><button data-export="pdf">PDF ↓</button><button id="view-version">${t("Нұсқаны көру", "Просмотр версии")}</button></div>
 <div class="notice info">${t("Белгісіз сөйлеушілерді жазбаны тыңдап қолмен белгілеңіз. Сөйлеуші міндетті түрде орындаушы емес.", "Укажите неизвестных говорящих вручную, сверяясь с записью. Говорящий не обязательно является исполнителем.")}</div>
 ${m.candidate ? `<details class="panel candidate-panel"><summary>${t("Жаңа талдауды салыстыру", "Сравнить повторный анализ")}</summary><p class="muted">${t("Жаңа нәтиже ағымдағы черновикті тек сіз қолданған кезде ауыстырады.", "Новый результат заменит текущий черновик только после вашего решения.")}</p><div class="grid comparison"><section><h2>${t("Ағымдағы нұсқа", "Текущая версия")}</h2>${protocolPreview(m.draft)}</section><section><h2>${t("Жаңа талдау", "Новый анализ")}</h2>${protocolPreview(m.candidate)}</section></div><button id="apply-candidate">${t("Салыстырдым, жаңа нәтижені қолдану", "Применить новый результат")}</button></details>` : ""}
 <div class="workspace"><section class="panel"><h2>${t("Жазба және транскрипт", "Запись и транскрипт")}</h2><audio id="player" controls preload="metadata" src="/api/meetings/${m.id}/audio"></audio><div class="scroll">${d.transcript
   .map(
     (s, i) =>
       `<article class="segment" data-segment="${esc(s.id)}" ${hue(s.speaker)}><div class="segment-top"><button class="time" data-time="${esc(s.id)}">${time(s.start)}–${time(s.end)}</button>${field(t("Сөйлеуші", "Говорящий"), input(s.speaker, `data-segment-field="${i}:speaker" placeholder="${t("Белгісіз", "Неизвестен")}"`))}${field(
         t("Тіл", "Язык"),
         `<select data-segment-field="${i}:language">${options(
           [
             ["unknown", "?"],
             ["ru", "RU"],
             ["kk", "KZ"],
             ["mixed", "RU/KZ"],
           ],
           s.language,
         )}</select>`,
       )}</div>${field(t("Реплика", "Реплика"), textarea(s.text, `data-segment-field="${i}:text"`))}</article>`,
   )
   .join("")}</div></section>
 <section class="panel"><div class="tabs" role="tablist">${[
   ["summary", t("Түйін", "Резюме")],
   ["decisions", t("Шешімдер", "Решения")],
   ["tasks", t("Тапсырмалар", "Поручения")],
 ]
   .map(
     ([k, label]) =>
       `<button id="tab-${k}" role="tab" aria-controls="right-content" aria-selected="${state.tab === k}" data-tab="${k}" class="${state.tab === k ? "active" : ""}">${label}</button>`,
   )
   .join("")}</div><div id="right-content" role="tabpanel" aria-labelledby="tab-${state.tab}"></div></section></div>
 <div class="savebar"><div class="review-status"><strong id="review-progress"></strong><p id="review-hint" class="muted"></p></div><span class="review-progress" aria-hidden="true"><i id="review-progress-bar"></i></span><label class="check"><input type="checkbox" id="reviewed" ${d.reviewed ? "checked" : ""}>${t("Транскрипт, түйін, шешімдер мен сұрақтарды тексердім", "Транскрипт, резюме, решения и вопросы проверены")}</label><div class="toolbar"><button class="primary" id="save">${t("Өзгерістерді сақтау", "Сохранить изменения")}</button><button id="discard">${t("Өзгерістерді қайтару", "Отменить правки")}</button><button id="approve">${t("Нұсқаны бекіту", "Утвердить версию")}</button><button id="reanalyze">${t("Қайта талдау", "Повторный анализ")}</button><span id="unsaved" class="muted"></span></div><small>${t("Бекіту — қолданбадағы нұсқаны сақтау; электрондық қолтаңба емес.", "Утверждение сохраняет версию в приложении; это не электронная подпись.")}</small></div>
 <details><summary>${t("Өзгерістер журналы", "Журнал изменений")}</summary><ol class="events">${m.events.map((e) => `<li>${esc(e.ts)} · ${esc(e.action)}</li>`).join("")}</ol><button id="audit-detail">${t("Толық журнал", "Полный журнал")}</button><pre id="audit-json"></pre></details></fieldset>`;
  right();
  $$("[data-time]").forEach((el) => (el.onclick = () => seek(el.dataset.time)));
  $$("[data-segment-field]").forEach(
    (el) =>
      (el.oninput = () => {
        const [i, k] = el.dataset.segmentField.split(":");
        d.transcript[i][k] = k === "speaker" ? el.value || null : el.value;
        d.reviewed = false;
        $("#reviewed").checked = false;
        d.assignments.forEach((a) => (a.review = "needs_review"));
        contentChanged();
      }),
  );
  $$("[data-tab]").forEach(
    (el) =>
      (el.onclick = () => {
        state.tab = el.dataset.tab;
        $("#right-content").setAttribute("aria-labelledby", el.id);
        $$("[data-tab]").forEach((b) => {
          b.classList.toggle("active", b === el);
          b.setAttribute("aria-selected", b === el);
          b.tabIndex = b === el ? 0 : -1;
        });
        right();
      }),
  );
  const tabs = $$("[data-tab]");
  tabs.forEach((el, index) => {
    el.tabIndex = el.dataset.tab === state.tab ? 0 : -1;
    el.onkeydown = (event) => {
      const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
      if (next === null) return;
      event.preventDefault();
      tabs[next].click();
      tabs[next].focus();
    };
  });
  $("#reviewed").onchange = (e) => {
    d.reviewed = e.target.checked;
    dirty();
  };
  $("#save").onclick = () => guard(save);
  $("#approve").onclick = () =>
    guard(async () => {
      await save();
      await api(
        `/api/meetings/${m.id}/approve`,
        json("POST", { revision: state.meeting.revision }),
      );
      renderEditor(await api(`/api/meetings/${m.id}`));
      notify(t("Нұсқа бекітілді", "Версия утверждена"));
    });
  $("#reanalyze").onclick = async () => {
    const succeeded = await guard(async () => {
      await save();
      await api(
        `/api/meetings/${m.id}/reanalyze`,
        json("POST", { revision: state.meeting.revision }),
      );
    });
    if (succeeded) window.dispatchEvent(new Event("hashchange"));
  };
  $("#back").onclick = () => {
    location.hash = "meetings";
  };
  if ($("#apply-candidate"))
    $("#apply-candidate").onclick = () =>
      guard(async () => {
        if (state.dirty)
          throw Error(
            t("Алдымен өзгерістерді сақтаңыз", "Сначала сохраните изменения"),
          );
        renderEditor(
          await api(
            `/api/meetings/${m.id}/candidate/apply`,
            json("POST", { revision: m.revision }),
          ),
        );
      });
  $("#view-version").onclick = () =>
    guard(async () => {
      const v = $("#version").value;
      if (!v) return;
      const s = await api(`/api/meetings/${m.id}/versions/${v}`);
      const win = document.createElement("dialog");
      win.innerHTML = `<h2>${t("Бекітілген нұсқа", "Утверждённая версия")} v${s.revision}</h2>${protocolPreview(s.draft)}<button>${t("Жабу", "Закрыть")}</button>`;
      document.body.append(win);
      win.querySelector("button").onclick = () => win.close();
      win.onclose = () => win.remove();
      win.showModal();
    });
  $$("[data-export]").forEach(
    (el) =>
      (el.onclick = () =>
        guard(async () => {
          if (state.dirty)
            throw Error(
              t(
                "Экспорт алдында сақтаңыз",
                "Сохраните изменения перед экспортом",
              ),
            );
          const v = $("#version").value;
          const r = await fetch(
            `/api/meetings/${m.id}/export?format=${el.dataset.export}&include_transcript=${$("#with-transcript").checked}${v ? "&version_id=" + v : ""}`,
          );
          if (!r.ok) throw Error((await r.json()).detail);
          const u = URL.createObjectURL(await r.blob());
          const a = document.createElement("a");
          a.href = u;
          a.download = `khattama_${m.id}.${el.dataset.export}`;
          a.click();
          setTimeout(() => URL.revokeObjectURL(u), 1000);
        })),
  );
  $("#audit-detail").onclick = () =>
    guard(async () => {
      $("#audit-json").textContent = JSON.stringify(
        await api(`/api/meetings/${m.id}/audit`),
        null,
        2,
      );
    });
  $("#discard").onclick = () => {
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `<h2>${t("Өзгерістерді қайтару?", "Отменить несохранённые правки?")}</h2><p>${t("Соңғы сақталған нұсқа ашылады.", "Будет открыта последняя сохранённая версия.")}</p><div class="toolbar"><button data-keep>${t("Жалғастыру", "Продолжить редактирование")}</button><button data-discard>${t("Қайтару", "Отменить правки")}</button></div>`;
    document.body.append(dialog);
    dialog.querySelector("[data-keep]").onclick = () => dialog.close();
    dialog.querySelector("[data-discard]").onclick = () => { dialog.close(); renderEditor(state.meeting); };
    dialog.onclose = () => dialog.remove();
    dialog.showModal();
  };
  syncReview();
  setBusyUI();
}

async function save() {
  if (!state.dirty) return;
  const emptySegment = state.draft.transcript.findIndex(segment => !segment.text?.trim());
  if (emptySegment !== -1) throw Error(t(`Реплика ${emptySegment + 1}: мәтінді енгізіңіз.`, `Реплика ${emptySegment + 1}: заполните текст.`));
  const emptyTask = state.draft.assignments.findIndex(task => !task.action?.trim());
  if (emptyTask !== -1) throw Error(t(`Тапсырма ${emptyTask + 1}: әрекетті енгізіңіз немесе бос тапсырманы жойыңыз.`, `Поручение ${emptyTask + 1}: заполните действие или удалите пустое поручение.`));
  const emptyDecision = state.draft.decisions.findIndex(decision => !decision.text?.trim());
  if (emptyDecision !== -1) throw Error(t(`Шешім ${emptyDecision + 1}: мәтінді енгізіңіз немесе бос жолды жойыңыз.`, `Решение ${emptyDecision + 1}: заполните текст или удалите пустую запись.`));
  const position = $("#player")?.currentTime || 0;
  const m = await api(
    `/api/meetings/${state.meeting.id}/draft`,
    json("PUT", { revision: state.meeting.revision, draft: state.draft }),
  );
  renderEditor(m);
  $("#player").addEventListener(
    "loadedmetadata",
    () => {
      $("#player").currentTime = position;
    },
    { once: true },
  );
  notify(
    t(
      "Сақталды. Өзгертілген дереккөз бен тапсырмаларды қайта тексеріңіз.",
      "Сохранено. Изменённые источники и поручения требуют повторной проверки.",
    ),
  );
}
async function guard(fn) {
  if (state.busy) return;
  state.busy = true;
  setBusyUI();
  try {
    await fn();
    return true;
  } catch (e) {
    notify(e.message, true);
  } finally {
    state.busy = false;
    setBusyUI();
    syncReview();
  }
}

function setBusyUI() {
  const fields = $("#editor-fields");
  if (fields) fields.disabled = state.busy;
  $("#locale").disabled = state.busy;
  $$("[data-nav]").forEach(el => el.disabled = state.busy);
  if ($("#unsaved")) $("#unsaved").textContent = state.busy ? t("Сақталуда…", "Выполняется…") : state.dirty ? t("Сақталмаған өзгерістер", "Несохранённые изменения") : t("Сақталған", "Все изменения сохранены");
}
