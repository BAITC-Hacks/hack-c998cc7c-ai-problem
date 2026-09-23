import {
  state,
  t,
  esc,
  $,
  $$,
  notify,
  api,
  json,
  field,
  input,
  options,
} from "./shared.js";
import { renderEditor } from "./editor.js";
import { meetings, tasks, settings } from "./screens.js";
import { stageName, loading } from "./views.js";

function navigation() {
  document.documentElement.lang = state.locale;
  $("#locale").textContent = state.locale === "kk" ? "RU · Русский" : "KZ · Қазақша";
  $("#brand-caption").textContent = t("Кездесуден — нәтижеге", "От встречи к результату");
  $("#workspace-label").textContent = t("Ортақ жұмыс кеңістігі", "Общее рабочее пространство");
  $("#workspace-caption").textContent = t("Транскрипт · Хаттама · Тапсырмалар", "Транскрипт · Протокол · Поручения");
  $$("[data-nav]").forEach((b) => {
    const span = b.querySelector("span");
    if (span)
      span.textContent = {
        meetings: t("Кездесулер", "Совещания"),
        tasks: t("Тапсырмалар", "Поручения"),
        settings: t("Баптаулар", "Настройки"),
      }[b.dataset.nav];
    const active = b.dataset.nav === state.page || (b.dataset.nav === "meetings" && /^(meeting\/|upload)/.test(state.page));
    b.classList.toggle("active", active);
    if (active) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    b.onclick = () => (location.hash = b.dataset.nav);
  });
}

async function upload() {
  const generation = state.generation;
  const h = await api("/api/health");
  if (generation !== state.generation) return;
  $("#app").innerHTML =
    `<div class="upload"><h1>${t("Жаңа кездесу", "Новое совещание")}</h1><p class="muted">${t("Мерзімдер осы кездесудің күні бойынша есептеледі.", "Сроки рассчитываются относительно даты этого совещания.")}</p><form id="upload-form" class="panel"><div class="grid">
 ${field(t("Атауы", "Название"), input("", 'name="title" required maxlength="200"'))}
 ${field(t("Күні мен уақыты", "Дата и время"), input("", 'name="meeting_at" type="datetime-local" required'))}
 ${field(t("Уақыт белдеуі (IANA)", "Часовой пояс (IANA)"), input("Asia/Almaty", 'name="timezone" required'))}
 ${field(t("Қатысушылар (үтір арқылы)", "Участники (через запятую)"), input("", 'name="participants"'))}
 <div class="wide">${field(t("Жазба — WAV / MP3 / MP4", "Запись — WAV / MP3 / MP4"), '<input type="file" name="file" accept=".wav,.mp3,.mp4" required>')}<small>${t("Ең үлкен көлем", "Максимальный размер")}: ${h.max_upload_mb} MB</small></div>
 ${field(t("Өңдеу режимі", "Режим обработки"), `<select name="mode"><option value="LOCAL">LOCAL — ${t("жергілікті LLM", "локальный LLM")}</option><option value="RULES">RULES — ${t("шектеулі ережелер", "ограниченные правила")}</option><option value="HYBRID">HYBRID — ${t("сыртқы LLM", "внешний LLM")}</option></select>`)}
 ${field(t("Сөйлеуді тану", "Распознавание аудио"), `<select name="asr_mode"><option value="API">${t("API арқылы", "Через API")}</option><option value="LOCAL">${t("Осы компьютерде", "На этом компьютере")} · faster-whisper</option></select>`)}
 </div><p id="mode-info" class="notice"></p><p id="audio-info" class="notice"></p><p id="api-setup" class="notice error" hidden></p><label class="check" id="audio-consent-label" hidden><input type="checkbox" name="audio_consent">${t("Жазбаның аудиосын тану API-іне жіберуге келісемін.", "Разрешаю отправку аудио записи API-провайдеру для распознавания.")}</label><label class="check" id="consent-label" hidden><input type="checkbox" name="consent">${t("Транскрипттің сыртқы талдау API-іне жіберілуіне келісемін.", "Разрешаю отправку транскрипта внешнему API для анализа.")}</label>
 ${!h.ffmpeg_available ? `<p class="notice">${t("FFmpeg табылмады. Баптауларды қараңыз.", "FFmpeg не найден. См. настройки.")}</p>` : ""}
 <div class="toolbar"><button class="primary" type="submit">${t("Жүктеу және өңдеу", "Загрузить и обработать")}</button><a class="button" href="#meetings">${t("Артқа", "Назад")}</a></div></form></div>`;
  const form = $("#upload-form");
  form.elements.mode.value = h.default_mode;
  form.elements.asr_mode.value = h.default_asr_mode;
  const modeInfo = () => {
    const mode = form.elements.mode.value;
    const audioAPI = form.elements.asr_mode.value === 'API';
    $('#audio-consent-label').hidden = !audioAPI;
    form.elements.audio_consent.required = audioAPI;
    $('#audio-info').textContent = audioAPI
      ? t(`Аудио ${h.asr_api_endpoint || 'бапталмаған API'} қызметіне жіберіледі.`, `Аудио отправляется в ${h.asr_api_endpoint || 'не настроенный API'} для распознавания.`)
      : t('Аудио осы компьютерде faster-whisper арқылы танылады.', 'Аудио распознаётся на этом компьютере через faster-whisper.');
    const missing = [];
    if (audioAPI && !h.asr_api_configured) missing.push('ASR_API_URL, ASR_API_MODEL, ASR_API_KEY');
    if (mode === 'HYBRID' && !h.hybrid_configured) missing.push('LLM_HYBRID_URL, LLM_HYBRID_MODEL, LLM_API_KEY');
    if (!audioAPI && !h.model_available) missing.push('WHISPER_MODEL');
    $('#api-setup').hidden = !missing.length;
    $('#api-setup').textContent = t('Алдымен backend/.env файлын баптап, қолданбаны қайта іске қосыңыз: ', 'Сначала заполните backend/.env и перезапустите приложение: ') + missing.join('; ');
    form.querySelector('button[type=submit]').disabled = !!missing.length || !h.ffmpeg_available;
    $("#consent-label").hidden = mode !== "HYBRID";
    form.elements.consent.required = mode === "HYBRID";
    $("#mode-info").textContent =
      mode === "LOCAL"
        ? t(
            "LOCAL: транскрипт осы компьютердегі LLM арқылы талданады.",
            "LOCAL: транскрипт анализируется локальным LLM на этом компьютере.",
          )
        : mode === "RULES"
          ? t(
              "RULES: желісіз жұмыс істейтін шектеулі извлекатель. Барлық нәтижені адам тексереді.",
              "RULES: ограниченный локальный извлекатель. Все результаты требуют проверки человеком.",
            )
          : t(
              `HYBRID: транскрипт ${h.hybrid_endpoint || "бапталмаған API"} қызметіне жіберіледі. Бұл жабық контур емес.`,
              `HYBRID: транскрипт отправляется в ${h.hybrid_endpoint || "не настроенный API"}. Это не закрытый контур.`,
            );
  };
  form.elements.mode.onchange = modeInfo;
  form.elements.asr_mode.onchange = modeInfo;
  modeInfo();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const file = form.elements.file.files[0];
      if (file.size > h.max_upload_mb * 1024 * 1024)
        throw Error(t("Файл тым үлкен", "Файл слишком большой"));
      const fd = new FormData();
      fd.append("file", file);
      fd.append(
        "metadata",
        JSON.stringify({
          title: form.elements.title.value,
          meeting_at: form.elements.meeting_at.value,
          timezone: form.elements.timezone.value,
          participants: form.elements.participants.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          mode: form.elements.mode.value,
          hybrid_consent: form.elements.consent.checked,
          asr_mode: form.elements.asr_mode.value,
          audio_consent: form.elements.audio_consent.checked,
        }),
      );
      const r = await api("/api/upload", { method: "POST", body: fd });
      if (generation === state.generation) location.hash = "meeting/" + r.meeting_id;
    } catch (e) {
      notify(e.message, true);
    } finally {
      button.disabled = false;
    }
  };
}

async function openMeeting(id) {
  const generation = state.generation;
  const m = await api("/api/meetings/" + id);
  if (generation !== state.generation) return;
  if (state.page !== "meeting/" + id) return;
  if (
    m.status === "done" ||
    (m.status === "error" && m.draft.transcript.length)
  ) {
    renderEditor(m);
    return;
  }
  $("#app").innerHTML =
    `<a class="button" href="#meetings">← ${t("Кездесулер", "Совещания")}</a><section class="panel"><h1>${esc(m.metadata.title)}</h1><p>${t("Күйі", "Статус")}: ${esc(m.status)}</p><div class="steps">${["queued", "decode", "transcribe", "diarization_manual", "analyze", "review"].map((s) => `<span class="${m.stage === s ? "current" : ""}">${esc(stageName(s))}</span>`).join("")}</div><p role="status">${esc(stageName(m.stage))}</p>${m.error ? `<p class="notice error">${esc(m.error)}</p><button id="retry">${t("Қайта бастау", "Повторить")}</button>` : `<p class="muted">${t("Бетті жабуға болады: жұмыс күйі сақталады.", "Страницу можно закрыть: состояние задания сохраняется.")}</p>`}<ol class="events">${m.events.map((e) => `<li>${esc(e.ts)} · ${esc(stageName(e.action))}</li>`).join("")}</ol></section>`;
  if ($("#retry"))
    $("#retry").onclick = async () => {
      try {
        await api(
          `/api/meetings/${id}/retry`,
          json("POST", { revision: m.revision }),
        );
        openMeeting(id);
      } catch (e) {
        notify(e.message, true);
      }
    };
  if (["queued", "processing"].includes(m.status))
    state.timer = setTimeout(
      () => openMeeting(id).catch((e) => notify(e.message, true)),
      1500,
    );
}

async function route() {
  clearTimeout(state.timer);
  if (state.dirty || state.busy) {
    notify(
      t(
        "Сақталмаған өзгерістер бар. Алдымен сақтаңыз.",
        "Есть несохранённые изменения или выполняется сохранение. Сохраните правки или отмените их.",
      ),
      true,
    );
    history.replaceState(null, "", "#meeting/" + state.meeting.id);
    return;
  }
  state.generation++;
  state.page = location.hash.slice(1) || "meetings";
  state.draft = null;
  state.meeting = null;
  $("#app").innerHTML = loading();
  navigation();
  notify("");
  const generation = state.generation;
  try {
    if (state.page === "upload") await upload();
    else if (state.page.startsWith("meeting/"))
      await openMeeting(state.page.split("/")[1]);
    else if (state.page === "tasks") await tasks();
    else if (state.page === "settings") await settings();
    else await meetings();
  } catch (e) {
    if (generation !== state.generation) return;
    notify(e.message, true);
    $("#app").innerHTML = `<section class="panel"><h1>${t("Жүктеу мүмкін болмады", "Не удалось загрузить страницу")}</h1><p>${esc(e.message)}</p><button id="reload-page">${t("Қайталау", "Попробовать снова")}</button></section>`;
    $("#reload-page").onclick = route;
  }
}
$("#locale").onclick = () => {
  if (state.busy) return;
  state.locale = state.locale === "kk" ? "ru" : "kk";
  localStorage.setItem("khattama-locale", state.locale);
  navigation();
  if (state.page.startsWith("meeting/") && state.draft) {
    const dirty = state.dirty;
    const draft = state.draft;
    renderEditor(state.meeting, { draft, dirty, contentDirty: state.contentDirty });
  } else route();
};
document.querySelector('.skip-link').onclick = (event) => {
  event.preventDefault();
  $('#app').focus();
};
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => {
  if (state.dirty || state.busy) {
    e.preventDefault();
    e.returnValue = "";
  }
});
route();
