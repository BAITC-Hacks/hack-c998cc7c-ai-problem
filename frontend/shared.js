export const state = {
  locale: localStorage.getItem("khattama-locale") || "kk",
  page: "meetings",
  meeting: null,
  draft: null,
  tab: "summary",
  dirty: false,
  busy: false,
  contentDirty: false,
  generation: 0,
  timer: null,
};
export const t = (kk, ru) => (state.locale === "kk" ? kk : ru);
export const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const $ = (s) => document.querySelector(s);
export const $$ = (s) => [...document.querySelectorAll(s)];
export const time = (n) =>
  `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(Math.floor(n % 60)).padStart(2, "0")}`;
export function notify(message, error = false) {
  $("#message").textContent = message;
  $("#message").className = error ? "error" : "";
}
export async function api(url, options = {}) {
  const r = await fetch(url, options);
  if (!r.ok) {
    let j;
    try {
      j = await r.json();
    } catch {
      j = { detail: r.statusText };
    }
    throw Error(
      typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail),
    );
  }
  return r.json();
}
export const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const icon = (name) =>
  ({
    library: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M9 7h7M9 11h7M9 15h4"/></svg>',
    bulb: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 1 3.5 10.9c-.8.6-1.2 1.2-1.3 2.1h-4.4c-.1-.9-.5-1.5-1.3-2.1A6 6 0 0 1 12 3z"/></svg>',
    tasks: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l3 3 6-7"/><path d="M4 4h2M4 12h2M4 20h2"/></svg>',
    mic: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8.5 12.2l2.3 2.3 4.7-5"/></svg>',
    upload: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7 9m5-5c5 0 9 4 9 9a7 7 0 0 1-7 7c-1.3 0-2.5-.3-3.5-.9"/></svg>',
  })[name] || "";
export const field = (label, control) =>
  `<label class="field">${esc(label)}${control}</label>`;
export const input = (value, attrs = "") =>
  `<input value="${esc(value)}" ${attrs}>`;
export const textarea = (value, attrs = "") =>
  `<textarea ${attrs}>${esc(value)}</textarea>`;
export const options = (values, selected) =>
  values
    .map(
      ([v, label]) =>
        `<option value="${esc(v)}" ${selected === v ? "selected" : ""}>${esc(label)}</option>`,
    )
    .join("");
export function dirty() {
  state.dirty = true;
  const x = $("#unsaved");
  if (x) x.textContent = t("Сақталмаған өзгерістер", "Несохранённые изменения");
  document.dispatchEvent(new Event("draftchange"));
}
export function reason(code) {
  return (
    {
      rules_limited: t(
        "Ережелер шектеулі: нәтижені тыңдап тексеріңіз",
        "Ограниченные правила: сверьте результат с записью",
      ),
      owner_not_stated: t("Орындаушы көрсетілмеген", "Исполнитель не указан"),
      deadline_unclear_or_not_stated: t(
        "Мерзім анық емес немесе айтылмаған",
        "Срок неясен или не указан",
      ),
      changed_deadline_requires_review: t(
        "Мерзім өзгертілген: соңғы нұсқаны тексеріңіз",
        "Срок изменён: проверьте последнее решение",
      ),
      source_changed: t(
        "Дереккөз өзгерген: дәлелдерді қайта тексеріңіз",
        "Источник изменён: перепроверьте доказательства",
      ),
      owner_not_in_evidence: t(
        "Орындаушы дәйексөзде жоқ",
        "Исполнителя нет в цитате",
      ),
      deadline_not_in_evidence: t(
        "Мерзім дәйексөзде жоқ",
        "Срока нет в цитате",
      ),
      result_not_in_evidence: t(
        "Нәтиже дәйексөзде жоқ",
        "Результата нет в цитате",
      ),
    }[code] || code
  );
}
