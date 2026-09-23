import { state, t, esc, $, api, field, input, icon } from './shared.js';
import { dateLabel, statusBadge, statusLabel, stageName } from './views.js';

export const pageHeading = (heading, subtitle, action = '', eyebrow = t('Жұмыс кеңістігі', 'Рабочее пространство')) =>
  `<div class="page-heading"><div><p class="eyebrow">${esc(eyebrow)}</p><h1>${heading}</h1><p class="muted">${subtitle}</p></div>${action}</div>`;

const empty = (heading, body, action = '', glyph = 'library') =>
  `<div class="empty"><span class="empty-symbol" aria-hidden="true">${icon(glyph)}</span><h2>${heading}</h2><p>${body}</p>${action}</div>`;

const metric = (label, count) => `<div><span>${label}</span><strong>${count}</strong></div>`;

const svgAction = (href, label, glyph, primary = false) =>
  `<a href="${href}" class="button ${primary ? 'primary' : ''}">${icon(glyph)}${label}</a>`;

export async function meetings() {
  const generation = state.generation;
  const { meetings } = await api('/api/meetings');
  if (state.generation !== generation) return;
  const processing = meetings.filter(m => ['queued', 'processing'].includes(m.status)).length;
  $('#app').innerHTML =
    pageHeading(
      t('Кездесулер', 'Совещания'),
      t('Жазбалар, шешімдер және тапсырмалар — бір жерде.', 'Записи, решения и поручения вашей команды — в одном месте.'),
      svgAction('#upload', t('Жазбаны жүктеу', 'Загрузить запись'), 'upload', true),
      t('Кездесулерден — нәтижеге', 'От встреч к результату'),
    ) +
    `<div class="metrics">${metric(t('Барлық кездесулер', 'Всего совещаний'), meetings.length)}${metric(t('Тексеруге дайын', 'Готово к проверке'), meetings.filter(m => m.status === 'done').length)}${metric(t('Өңделуде', 'Обрабатываются'), processing)}</div>
    <section class="panel"><div class="section-heading"><h2>${t('Жазбалар кітапханасы', 'Библиотека записей')}</h2><small>${t('Кездесу күні бойынша', 'Дата и время встречи')}</small></div><div class="filter-bar">${field(t('Іздеу', 'Поиск'), input('', `id="meeting-search" type="search" placeholder="${t('Атау немесе файл', 'Название или файл')}"`))}${field(t('Күйі', 'Статус'), `<select id="meeting-filter"><option value="all">${t('Барлығы', 'Все статусы')}</option><option value="done">${t('Тексеруге дайын', 'Готово к проверке')}</option><option value="processing">${t('Өңделуде', 'В обработке')}</option><option value="error">${t('Қателер', 'Требует внимания')}</option></select>`)}</div><div id="meeting-list"></div></section>`;
  const render = () => {
    const query = $('#meeting-search').value.trim().toLocaleLowerCase();
    const filter = $('#meeting-filter').value;
    const rows = meetings.filter(m => `${m.metadata.title} ${m.filename}`.toLocaleLowerCase().includes(query) && (filter === 'all' || m.status === filter || (filter === 'processing' && m.status === 'queued')));
    $('#meeting-list').innerHTML = rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>${t('Кездесу', 'Совещание')}</th><th>${t('Күні', 'Дата встречи')}</th><th>${t('Өңдеу', 'Обработка')}</th><th><span class="sr-only">${t('Әрекеттер', 'Действия')}</span></th></tr></thead><tbody>${rows.map(m => `<tr><td><a class="record-title" href="#meeting/${m.id}">${esc(m.metadata.title)}</a><small class="block">${esc(m.filename)} · ${esc(m.metadata.mode)}</small></td><td>${esc(dateLabel(m.metadata.meeting_at, m.metadata.timezone))}<small class="block">${esc(m.metadata.timezone)}</small></td><td>${statusBadge(m.status)}${m.status === 'processing' ? `<small class="block">${esc(stageName(m.stage))}</small>` : ''}</td><td><a class="button compact" href="#meeting/${m.id}">${t('Ашу', 'Открыть')} <span aria-hidden="true">↗</span></a></td></tr>`).join('')}</tbody></table></div>`
      : empty(
          meetings.length ? t('Ештеңе табылмады', 'Ничего не найдено') : t('Алғашқы кездесуден бастаңыз', 'Начните с первой встречи'),
          meetings.length ? t('Іздеуді немесе сүзгіні өзгертіңіз.', 'Измените запрос или фильтр.') : t('Аудионы жүктеңіз — транскрипт пен хаттаманы бірге тексереміз.', 'Загрузите аудио, чтобы получить транскрипт и проверить протокол.'),
          meetings.length ? '' : svgAction('#upload', t('Жазбаны таңдау', 'Выбрать запись'), 'upload'),
          'upload',
        );
  };
  $('#meeting-search').oninput = render;
  $('#meeting-filter').onchange = render;
  render();
  const poll = async () => {
    if (state.generation !== generation) return;
    try {
      const result = await api('/api/meetings');
      if (state.generation !== generation) return;
      meetings.splice(0, meetings.length, ...result.meetings);
      const counts = [meetings.length, meetings.filter(m => m.status === 'done').length, meetings.filter(m => ['queued', 'processing'].includes(m.status)).length];
      document.querySelectorAll('.metrics strong').forEach((el, i) => { el.textContent = counts[i]; });
      render();
    } catch { /* Keep current rows while the connection recovers. */ }
    if (state.generation === generation && meetings.some(m => ['queued', 'processing'].includes(m.status))) state.timer = setTimeout(poll, 5000);
  };
  if (processing) state.timer = setTimeout(poll, 5000);
}

export async function tasks() {
  const generation = state.generation;
  const { assignments } = await api('/api/assignments');
  if (state.generation !== generation) return;
  $('#app').innerHTML =
    pageHeading(
      t('Тапсырмалар', 'Поручения'),
      t('Кім, не және қашан орындауы керек.', 'Кто, что и к какому сроку должен сделать.'),
      '',
      t('Жауапкершілік', 'Ответственность'),
    ) +
    `<div class="metrics">${metric(t('Барлығы', 'Всего поручений'), assignments.length)}${metric(t('Тексеру қажет', 'Нужна проверка'), assignments.filter(a => a.review !== 'confirmed').length)}${metric(t('Мерзімі өткен', 'Просрочены'), assignments.filter(a => a.overdue).length)}</div><section class="panel"><div class="filter-bar">${field(t('Іздеу', 'Поиск'), input('', `type="search" id="task-search" placeholder="${t('Тапсырма немесе орындаушы', 'Поручение или исполнитель')}"`))}${field(t('Сүзгі', 'Фильтр'), `<select id="filter"><option value="all">${t('Барлығы', 'Все поручения')}</option><option value="overdue">${t('Мерзімі өткен', 'Просрочены')}</option><option value="needs_review">${t('Тексеру қажет', 'Нужна проверка')}</option>${['open', 'in_progress', 'done', 'cancelled'].map(s => `<option value="${s}">${s === 'done' ? t('Орындалды', 'Выполнены') : statusLabel(s)}</option>`).join('')}</select>`)}</div><div id="register"></div></section>`;
  const render = () => {
    const filter = $('#filter').value;
    const query = $('#task-search').value.trim().toLocaleLowerCase();
    const rows = assignments.filter(a => `${a.action} ${a.owner || ''} ${a.title}`.toLocaleLowerCase().includes(query) && (filter === 'all' || (filter === 'overdue' ? a.overdue : filter === 'needs_review' ? a.review !== 'confirmed' : a.status === filter)));
    $('#register').innerHTML = rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>${t('Тапсырма', 'Поручение')}</th><th>${t('Орындаушы', 'Исполнитель')}</th><th>${t('Мерзімі', 'Срок')}</th><th>${t('Күйі', 'Статус')}</th></tr></thead><tbody>${rows.map(a => `<tr><td><a class="record-title" href="#meeting/${a.meeting_id}">${esc(a.action)}</a><small class="block">${esc(a.title)}</small></td><td>${esc(a.owner || t('Көрсетілмеген', 'Не указан'))}</td><td>${esc(a.deadline || a.deadline_raw || t('Мерзімсіз', 'Без срока'))}${a.overdue ? `<small class="overdue block">${t('Мерзімі өткен', 'Просрочено')}</small>` : ''}</td><td>${statusBadge(a.status, a.status === 'done' ? t('Орындалды', 'Выполнено') : undefined)}<small class="block">${esc(statusLabel(a.review))}</small></td></tr>`).join('')}</tbody></table></div>`
      : empty(
          t('Тапсырмалар табылмады', 'Поручений пока нет'),
          t('Олар жазбаны өңдегеннен кейін пайда болады. Сүзгілерді де тексеріңіз.', 'Они появятся после обработки записей. Если включены фильтры, попробуйте их изменить.'),
          '',
          'tasks',
        );
  };
  $('#filter').onchange = render;
  $('#task-search').oninput = render;
  render();
}

export async function settings() {
  const generation = state.generation;
  const h = await api('/api/health');
  if (state.generation !== generation) return;
  const badge = ready => statusBadge(ready ? 'confirmed' : 'error', ready ? t('Бапталған', 'Настроено') : t('Баптау қажет', 'Нужно настроить'));
  const provider = (title, host, model, ready, variables) => `<section class="panel provider-card"><div class="section-heading"><h2>${title}</h2>${badge(ready)}</div><p>${esc(host || t('Провайдер таңдалмаған', 'Провайдер не выбран'))}</p><p>${t('Модель', 'Модель')}: <strong>${esc(model || '—')}</strong></p><p class="muted"><code>${variables}</code></p></section>`;
  $('#app').innerHTML =
    pageHeading(t('Баптаулар', 'Настройки'), t('Қолданба жергілікті жұмыс істейді, AI — API арқылы.', 'Приложение работает локально, ИИ — через API.'), '', t('Жүйе', 'Система')) +
    `<section class="panel"><h2>${t('Жұмыс кеңістігі', 'Рабочее пространство')}</h2><p>${t('Жазбалар, хаттамалар мен нұсқалар осы компьютерде сақталады.', 'Записи, протоколы и версии хранятся на этом компьютере.')}</p><p>${t('Аудио мен транскрипт тек таңдалған API қызметтеріне келісіммен жіберіледі.', 'Аудио и транскрипт передаются выбранным API-провайдерам с согласия при загрузке.')}</p><div class="toolbar">${statusBadge(h.worker_running ? 'confirmed' : 'error', t('Өңдеу кезегі', 'Очередь обработки'))}${statusBadge(h.ffmpeg_available ? 'confirmed' : 'error', 'FFmpeg')}<span class="badge">${h.max_upload_mb} MB</span></div></section>` +
    `<div class="grid">${provider(t('Аудионы тану API', 'API распознавания аудио'), h.asr_api_endpoint, h.asr_api_model, h.asr_api_configured, 'ASR_API_URL · ASR_API_MODEL · ASR_API_KEY')}${provider(t('Мәтінді талдау API', 'API анализа текста'), h.hybrid_endpoint, h.hybrid_model, h.hybrid_configured, 'LLM_HYBRID_URL · LLM_HYBRID_MODEL · LLM_API_KEY')}</div>` +
    `<section class="panel"><h2>${t('Қосылымды баптау', 'Настройка подключения')}</h2><p>${t('Провайдер мекенжайларын, модельдер мен кілттерді backend/.env файлына енгізіп, қолданбаны қайта іске қосыңыз.', 'Укажите адреса провайдеров, модели и ключи в backend/.env, затем перезапустите приложение.')}</p><p>${t('Кілттер браузерге берілмейді. Екі кезеңге әртүрлі провайдер қолдануға болады.', 'Ключи не передаются браузеру. Для двух этапов можно использовать разных провайдеров.')}</p><p class="muted">${t('«Бапталған» — өрістер толтырылған; желілік қосылым мен квота өңдеу кезінде тексеріледі.', '«Настроено» означает, что поля заполнены. Доступ к модели и квота проверяются при обработке.')}</p></section>` +
    `<details class="panel"><summary>${t('Жергілікті баламалар', 'Локальные альтернативы')}</summary><p>faster-whisper: ${h.model_available ? t('модель орнатылған', 'модель установлена') : t('модель жоқ', 'модель не установлена')}.</p><p>LOCAL — ${t('жергілікті LLM', 'локальный LLM')}. RULES — ${t('LLM-сіз шектеулі ережелер', 'ограниченные правила без LLM')}.</p><p>${t('Автоматты ауысу жоқ. Әр кездесу режимі жүктеу кезінде таңдалады.', 'Автоматического переключения нет. Режимы выбираются при загрузке каждой записи.')}</p></details>`;
}