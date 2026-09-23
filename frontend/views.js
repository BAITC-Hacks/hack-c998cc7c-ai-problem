import { t, esc } from './shared.js';

export function dateLabel(value, timezone) {
  return new Intl.DateTimeFormat(document.documentElement.lang === 'kk' ? 'kk-KZ' : 'ru-RU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: timezone,
  }).format(new Date(value));
}

export function statusLabel(status) {
  return ({ queued: t('Кезекте', 'В очереди'), processing: t('Өңделуде', 'Обрабатывается'), done: t('Тексеруге дайын', 'Готово к проверке'), error: t('Назар аударыңыз', 'Требует внимания'), open: t('Ашық', 'Открыто'), in_progress: t('Орындалуда', 'В работе'), cancelled: t('Жойылды', 'Отменено'), confirmed: t('Тексерілген', 'Проверено'), needs_review: t('Тексеру қажет', 'Нужна проверка') })[status] || status;
}

export function statusBadge(status, label) {
  return `<span class="status status-${esc(status)}"><span aria-hidden="true" class="status-mark"></span>${esc(label || statusLabel(status))}</span>`;
}

export function stageName(stage) {
  const audio = /^transcribe_chunk_(\d+)_of_(\d+)$/.exec(stage);
  if (audio) return t(`Сөйлеуді тану: ${audio[1]} / ${audio[2]} бөлік`, `Распознавание: фрагмент ${audio[1]} из ${audio[2]}`);
  const chunk = /^analysis_chunk_(\d+)_of_(\d+)$/.exec(stage);
  if (chunk) return t(`Талдау: ${chunk[1]} / ${chunk[2]} бөлік`, `Анализ: фрагмент ${chunk[1]} из ${chunk[2]}`);
  return ({ queued: t('Кезекте', 'В очереди'), recovered: t('Жалғастыру', 'Возобновление'), decode: t('Аудионы дайындау', 'Подготовка аудио'), transcribe: t('Сөйлеуді тану', 'Распознавание речи'), diarization_manual: t('Транскрипт дайын', 'Транскрипт готов'), analyze: t('Мазмұнды талдау', 'Анализ содержания'), review: t('Адамның тексеруі', 'Проверка человеком') })[stage] || stage;
}

export function errorNotice(message) {
  const code = message?.split(':')[0];
  const hint = ({
    ASR_MODEL_MISSING: t('Сөйлеуді тану моделі орнатылмаған. Баптаулар бөлімін қараңыз.', 'Модель распознавания не установлена. Откройте настройки.'),
    NO_SPEECH: t('Сөйлеу табылмады. Жазбадағы дыбысты тексеріңіз.', 'Речь не найдена. Проверьте, слышны ли голоса в записи.'),
    LLM_UNAVAILABLE: t('Талдау қызметі қолжетімсіз. Транскрипт сақталды.', 'Сервис анализа недоступен. Готовый транскрипт сохранён.'),
    AUDIO_DECODE_FAILED: t('Аудионы оқу мүмкін болмады. Басқа файлды жүктеңіз.', 'Не удалось прочитать аудио. Попробуйте другой файл.'),
  })[code];
  return `<div class="notice error">${esc(hint || message)}${hint ? `<details><summary>${t('Техникалық мәлімет', 'Технические подробности')}</summary><small>${esc(message)}</small></details>` : ''}</div>`;
}

export function protocolPreview(draft) {
  const list = values => values.length ? `<ul>${values.map(value => `<li>${esc(value)}</li>`).join('')}</ul>` : `<p class="muted">${t('Әзірге жоқ', 'Пока нет')}</p>`;
  return `<div class="protocol-preview"><h3>${t('Резюме', 'Резюме')}</h3>${list(draft.summary)}<h3>${t('Шешімдер', 'Решения')}</h3>${list(draft.decisions.map(item => item.text))}<h3>${t('Тапсырмалар', 'Поручения')} · ${draft.assignments.length}</h3>${draft.assignments.map(item => `<article><strong>${esc(item.action)}</strong><p>${esc(item.owner || t('Орындаушы жоқ', 'Исполнитель не указан'))} · ${esc(item.deadline || item.deadline_raw || t('Мерзім жоқ', 'Без срока'))}</p>${item.expected_result ? `<p>${esc(item.expected_result)}</p>` : ''}<small>${esc(item.status === 'done' ? t('Орындалды', 'Выполнено') : statusLabel(item.status))}</small></article>`).join('')}<h3>${t('Ашық сұрақтар', 'Открытые вопросы')}</h3>${list(draft.questions)}</div>`;
}

export function loading() {
  return `<div class="loading-state" role="status"><span class="loader" aria-hidden="true"></span>${t('Жүктелуде…', 'Загружаем…')}</div>`;
}
