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

function evidenceList(item, index, type) {
  return `<div>${item.evidence.map((e) => `<button class="evidence" data-seek="${esc(e.segment_id)}">${time(e.start)}–${time(e.end)} · «${esc(e.quote)}»</button>`).join("")}</div><label class="field">${t("Дәйексөзді қосу / жаңарту", "Добавить / обновить доказательство")}<select data-evidence="${type}:${index}"><option value="">${t("Сегментті таңдаңыз", "Выберите сегмент")}</option>${state.draft.transcript.map((s, i) => `<option value="${i}">${esc(time(s.start) + " " + s.text.slice(0, 90))}</option>`).join("")}</select></label>`;
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
        state.draft.assignments[i][k] = el.value || null;
        if (k !== "status") state.draft.assignments[i].review = "needs_review";
        dirty();
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
        dirty();
      }),
  );
  $$("[data-delete-task]").forEach(
    (el) =>
      (el.onclick = () => {
        state.draft.assignments.splice(+el.dataset.deleteTask, 1);
        dirty();
        right();
      }),
  );
  $$("[data-delete-decision]").forEach(
    (el) =>
      (el.onclick = () => {
        state.draft.decisions.splice(+el.dataset.deleteDecision, 1);
        state.draft.reviewed = false;
        dirty();
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
        if (type === "task") a.review = "needs_review";
        dirty();
        right();
      }),
  );
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
      dirty();
      right();
    };
  if ($("#add-decision"))
    $("#add-decision").onclick = () => {
      state.draft.decisions.push({ text: "", kind: "decision", evidence: [] });
      dirty();
      right();
    };
  ["summary", "questions"].forEach((k) => {
    const el = $("#" + k + "-text");
    if (el)
      el.oninput = () => {
        state.draft[k] = el.value.split("\n").filter((x) => x.trim());
        state.draft.reviewed = false;
        dirty();
      };
  });
}

function seek(id) {
  const s = state.draft.transcript.find((s) => s.id === id);
  if (!s) return;
  $("#player").currentTime = s.start;
  $$(".segment").forEach((el) =>
    el.classList.toggle("selected", el.dataset.segment === id),
  );
  const el = $$(".segment").find((el) => el.dataset.segment === id);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function renderEditor(m) {
  state.meeting = m;
  state.draft = structuredClone(m.draft);
  state.dirty = false;
  const d = state.draft;
  $("#app").innerHTML =
    `<div class="toolbar"><button id="back">← ${t("Кездесулер", "Совещания")}</button><span class="badge">${esc(m.metadata.mode)}</span><span class="spacer"></span><span>${t("Жоба", "Черновик")} · r${m.revision}</span></div><h1>${esc(m.metadata.title)}</h1><p class="muted">${esc(m.metadata.meeting_at)} · ${esc(m.metadata.timezone)} · ${esc(m.metadata.participants.join(", "))}</p>
 ${m.error ? `<p class="notice error">${esc(m.error)}</p>` : ""}
 <div class="toolbar version-bar"><label>${t("Экспорт нұсқасы", "Версия для экспорта")} <select id="version"><option value="">${t("Ағымдағы жоба", "Текущий черновик")}</option>${m.versions.map((v) => `<option value="${v.id}">v${v.revision} · ${esc(v.created_at.slice(0, 16))}</option>`).join("")}</select></label><label class="check"><input id="with-transcript" type="checkbox" checked>${t("Транскриптпен", "С транскриптом")}</label><button data-export="docx">DOCX ↓</button><button data-export="pdf">PDF ↓</button><button id="view-version">${t("Нұсқаны көру", "Просмотр версии")}</button></div>
 <div class="notice">${t("Сөйлеушілер автоматты анықталмайды. Әр сегментке атын қолмен беріңіз. Сөйлеуші міндетті түрде орындаушы емес.", "Говорящие автоматически не определяются. Назначьте имена сегментам вручную. Говорящий не обязательно исполнитель.")}</div>
 ${m.candidate ? `<details class="panel"><summary>${t("Қайта талдау нәтижесі дайын", "Новый анализ готов для сравнения")}</summary><div class="grid"><div><h3>${t("Ағымдағы түзетулер", "Текущие правки")}</h3><pre>${esc(JSON.stringify(m.draft, null, 2))}</pre></div><div><h3>${t("Жаңа нәтиже", "Новый результат")}</h3><pre>${esc(JSON.stringify(m.candidate, null, 2))}</pre></div></div><p>${t("Қабылдау ағымдағы жобаны ауыстырады. Алдыңғы мәтін өзгерістер журналында қалады.", "Применение заменит текущий черновик. Предыдущий текст сохранится в журнале изменений.")}</p><button id="apply-candidate">${t("Салыстырдым, жаңа нәтижені қолдану", "Сравнение завершено, применить новый результат")}</button></details>` : ""}
 <div class="workspace"><section class="panel"><h2>${t("Жазба және транскрипт", "Запись и транскрипт")}</h2><audio id="player" controls preload="metadata" src="/api/meetings/${m.id}/audio"></audio><div class="scroll">${d.transcript
   .map(
     (s, i) =>
       `<article class="segment" data-segment="${esc(s.id)}"><div class="segment-top"><button class="time" data-time="${esc(s.id)}">▶ ${time(s.start)}–${time(s.end)}</button>${field(t("Сөйлеуші", "Говорящий"), input(s.speaker, `data-segment-field="${i}:speaker" placeholder="${t("Белгісіз", "Неизвестен")}"`))}${field(
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
       `<button role="tab" aria-selected="${state.tab === k}" data-tab="${k}" class="${state.tab === k ? "active" : ""}">${label}</button>`,
   )
   .join("")}</div><div id="right-content"></div></section></div>
 <div class="savebar"><label class="check"><input type="checkbox" id="reviewed" ${d.reviewed ? "checked" : ""}>${t("Транскрипт, түйін, шешімдер мен сұрақтарды тексердім", "Транскрипт, резюме, решения и вопросы проверены")}</label><div class="toolbar"><button class="primary" id="save">${t("Өзгерістерді сақтау", "Сохранить изменения")}</button><button id="approve">${t("Нұсқаны бекіту", "Утвердить версию")}</button><button id="reanalyze">${t("Қайта талдау", "Повторный анализ")}</button><span id="unsaved" class="muted"></span></div><small>${t("Бекіту — қолданбадағы нұсқаны сақтау; электрондық қолтаңба емес.", "Утверждение сохраняет версию в приложении; это не электронная подпись.")}</small></div>
 <details><summary>${t("Өзгерістер журналы", "Журнал изменений")}</summary><ol class="events">${m.events.map((e) => `<li>${esc(e.ts)} · ${esc(e.action)}</li>`).join("")}</ol><button id="audit-detail">${t("Толық журнал", "Полный журнал")}</button><pre id="audit-json"></pre></details>`;
  right();
  $$("[data-time]").forEach((el) => (el.onclick = () => seek(el.dataset.time)));
  $$("[data-segment-field]").forEach(
    (el) =>
      (el.oninput = () => {
        const [i, k] = el.dataset.segmentField.split(":");
        d.transcript[i][k] = el.value || null;
        d.reviewed = false;
        $("#reviewed").checked = false;
        d.assignments.forEach((a) => (a.review = "needs_review"));
        dirty();
      }),
  );
  $$("[data-tab]").forEach(
    (el) =>
      (el.onclick = () => {
        state.tab = el.dataset.tab;
        $$("[data-tab]").forEach((b) => {
          b.classList.toggle("active", b === el);
          b.setAttribute("aria-selected", b === el);
        });
        right();
      }),
  );
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
  $("#reanalyze").onclick = () =>
    guard(async () => {
      await save();
      await api(
        `/api/meetings/${m.id}/reanalyze`,
        json("POST", { revision: state.meeting.revision }),
      );
      location.hash = "meeting/" + m.id;
      window.dispatchEvent(new Event("hashchange"));
    });
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
      win.innerHTML = `<h2>${t("Бекітілген нұсқа", "Утверждённая версия")} v${s.revision}</h2><pre>${esc(JSON.stringify(s, null, 2))}</pre><button>${t("Жабу", "Закрыть")}</button>`;
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
}

async function save() {
  if (!state.dirty) return;
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
  try {
    await fn();
  } catch (e) {
    notify(e.message, true);
  }
}
