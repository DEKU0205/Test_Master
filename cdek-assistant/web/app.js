'use strict';
let me = null, sources = [], csrf = '';
const $ = id => document.getElementById(id);
function node(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function notify(text, error = false) { const box = $('global-message'); box.replaceChildren(); if (text) box.append(node('p', text, error ? 'notice error' : 'notice')); }
async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path === '/api/answer' ? 75000 : 12000);
  const opts = {credentials: 'same-origin', headers: {}, signal: controller.signal};
  if (body !== undefined) { opts.method = 'POST'; opts.headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}; opts.body = JSON.stringify(body); }
  try {
    let res;
    try { res = await fetch(path, opts); }
    catch (err) { throw new Error(err.name === 'AbortError' ? 'Сервер не ответил вовремя. Проверьте соединение и повторите вход.' : 'Нет соединения с сервером приложения. Проверьте адрес сайта.'); }
    if (!(res.headers.get('content-type') || '').includes('application/json')) throw new Error('По этому адресу сервер приложения недоступен. Открытая HTML-страница сама по себе не поддерживает вход.');
    const data = await res.json();
    if (!res.ok) { if (res.status === 401 && path !== '/api/login') showLogin(); const error = new Error(data.error || 'Ошибка запроса'); error.status = res.status; throw error; }
    return data;
  } finally { clearTimeout(timer); }
}
function showLogin() { me = null; csrf = ''; $('workspace').hidden = true; $('login-view').hidden = false; $('logout').hidden = true; $('identity').textContent = ''; }
async function enter() {
  me = await api('/api/me'); csrf = me.csrf;
  $('login-view').hidden = true; $('workspace').hidden = false; $('logout').hidden = false;
  $('identity').textContent = me.name;
  for (const id of ['sources-tab', 'queue-tab', 'audit-tab']) $(id).hidden = me.role !== 'admin';
  $('model-status').textContent = me.model_configured ? '● OpenAI настроен' : '○ Модель не подключена';
  await refreshCoverage(); await selectTab('assistant');
}
async function refreshCoverage() {
  const c = await api('/api/coverage');
  $('approved-count').textContent = c.approved_sources; $('source-count').textContent = c.total_sources; $('queue-count').textContent = c.queue_count;
  $('coverage-notice').textContent = c.approved_sources ? 'Рабочий поиск использует только допущенные источники. Полнота Вики не подтверждена.' : 'База не допущена к консультациям. Доступны подготовка и проверка материалов.';
}
$('login-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.currentTarget.querySelector('button'); button.disabled = true; button.textContent = 'Выполняется вход…'; $('login-error').textContent = '';
  try { await api('/api/login', {username: $('username').value, password: $('password').value}); $('password').value = ''; await enter(); }
  catch (err) { $('login-error').textContent = err.message; } finally { button.disabled = false; button.textContent = 'Войти в рабочую среду →'; }
});
$('logout').onclick = async () => { try { await api('/api/logout', {}); } finally { showLogin(); } };
for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => selectTab(button.dataset.tab).catch(e => notify(e.message, true));
async function selectTab(tab) {
  notify('');
  for (const p of document.querySelectorAll('.tab-panel')) p.hidden = p.id !== tab + '-panel';
  for (const b of document.querySelectorAll('[data-tab]')) b.classList.toggle('active', b.dataset.tab === tab);
  if (tab === 'sources') { sources = (await api('/api/admin/sources')).sources; renderSources(); }
  if (tab === 'queue') await renderQueue();
  if (tab === 'audit') {
    const events = (await api('/api/admin/audit')).events; $('audit-list').replaceChildren();
    for (const event of events) { const row = node('div', undefined, 'audit-row'); row.append(node('strong', `${event.at} · ${event.actor} · ${event.action}`), node('p', event.source_id), node('pre', event.details)); $('audit-list').append(row); }
  }
}
function citation(c) {
  const box = node('div', undefined, 'citation');
  box.append(node('strong', c.title), node('small', `${c.locator} · ${c.revision}`));
  if (c.quote) box.append(node('blockquote', c.quote));
  if (c.body) box.append(node('pre', c.body));
  const url = new URL(c.url);
  if (url.protocol === 'https:' && url.hostname === 'base.cdek.ru') { const a = node('a', 'Открыть первоисточник ↗'); a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; box.append(a); }
  box.append(node('small', 'SHA256: ' + c.hash)); return box;
}
const titles = {summary: 'Краткий итог', acceptance: 'Условия приёма', restrictions: 'Ограничения', packaging: 'Упаковка', marking: 'Маркировка', documents: 'Документы', coordination: 'Согласования', client_phrase: 'Формулировка для клиента'};
$('question-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = $('ask-button'); button.disabled = true; button.textContent = 'Проверяем источники…';
  const context = Object.fromEntries(new FormData(e.currentTarget));
  $('answer').replaceChildren(node('h2', 'Ответ для оператора'), node('p', 'Выполняется поиск по допущенным материалам…', 'muted'));
  try {
    const result = await api('/api/answer', {query: $('question').value, context});
    $('answer').replaceChildren(node('h2', result.status === 'no_approved_sources' ? 'Нужна проверка источников' : 'Ответ для оператора'));
    if (result.notice) $('answer').append(node('p', result.notice, 'notice'));
    if (result.status === 'needs_review') $('answer').append(node('p', 'Есть противоречия или условия, требующие проверки. Не сообщайте клиенту безусловное разрешение.', 'notice'));
    if (result.questions.length) {
      const block = node('section', undefined, 'answer-section'); block.append(node('h3', 'Уточните у клиента')); const list = node('ul');
      for (const q of result.questions) { const li = node('li'); const b = node('button', q, 'quiet'); b.onclick = () => { $('question').value += '\n' + q + ' '; $('question').focus(); }; li.append(b); list.append(li); }
      block.append(list, node('p', 'Добавьте ответы в описание или поля слева и отправьте уточнённый запрос.', 'fine')); $('answer').append(block);
    }
    for (const key of Object.keys(titles)) {
      if (!result.sections[key]?.length) continue;
      const block = node('section', undefined, 'answer-section'); block.append(node('h3', titles[key]));
      for (const claim of result.sections[key]) { const item = node('div', undefined, 'claim'); item.append(node('p', claim.text)); for (const c of claim.citations) item.append(citation(c)); block.append(item); }
      if (key === 'client_phrase') { const copy = node('button', 'Копировать формулировку', 'quiet'); copy.onclick = async () => { try { await navigator.clipboard.writeText(result.sections[key].map(c => c.text).join('\n')); copy.textContent = 'Скопировано'; } catch { notify('Копирование недоступно. Выделите текст вручную.'); } }; block.append(copy); }
      $('answer').append(block);
    }
  } catch (err) { $('answer').replaceChildren(node('h2', 'Ответ не сформирован'), node('p', err.message, 'notice')); }
  finally { button.disabled = false; button.textContent = 'Получить ответ с источниками →'; }
});
const statuses = {not_confirmed:'Не проверен',latest_explicit:'Есть отметка последней редакции',retired_explicit:'Отменён',current_verified:'Допущен после проверки',superseded:'Заменён',unavailable:'Недоступен'};
function renderSources() {
  const filter = $('source-filter').value.toLowerCase(); $('source-list').replaceChildren();
  for (const s of sources.filter(s => (s.title + ' ' + s.id).toLowerCase().includes(filter))) {
    const row = node('div', undefined, 'source-row'); const info = node('div'); info.append(node('strong', `${s.id} · ${s.title}`), node('small', s.revision));
    const active = s.approved && s.expires_at && new Date(s.expires_at) > new Date();
    info.append(node('span', active ? 'Допущен до ' + s.expires_at : (s.approved ? 'Срок допуска истёк' : statuses[s.status] || s.status), 'tag' + (active ? '' : ' warn')));
    const button = node('button', 'Проверить', 'quiet'); button.onclick = () => openSource(s.id).catch(e => notify(e.message, true)); row.append(info, button); $('source-list').append(row);
  }
}
$('source-filter').oninput = renderSources;
$('review-search').onsubmit = async e => {
  e.preventDefault(); try { const data = await api('/api/search', {query: $('review-query').value, review: true}); $('review-results').replaceChildren(node('p', `Найдено фрагментов: ${data.results.length}. Только для проверки, не для консультаций.`, 'notice'));
    for (const r of data.results) { const box = citation(r); const b = node('button', 'Проверить источник', 'quiet'); b.onclick = () => openSource(r.source_id).catch(e => notify(e.message, true)); box.append(b); $('review-results').append(box); }
  } catch (err) { notify(err.message, true); }
};
async function openSource(id) {
  const {source:s, chunks} = await api('/api/source?id=' + encodeURIComponent(id)); const box = $('source-detail'); box.hidden = false; box.replaceChildren();
  box.append(node('span', 'РЕЖИМ ПРОВЕРКИ · НЕ РЕКОМЕНДАЦИЯ', 'eyebrow'), node('h2', s.title), node('p', `Статус: ${statuses[s.status] || s.status}`), node('pre', JSON.stringify({revision:s.revision, hash:s.hash, metadata:JSON.parse(s.metadata), evidence:s.evidence && JSON.parse(s.evidence)}, null, 2)));
  const original = node('a', 'Открыть оригинал на сервере (скачать)'); original.href = '/api/admin/original?id=' + encodeURIComponent(id); box.append(original);
  const history = node('details'); history.append(node('summary', 'История версий источника'));
  const versions = (await api('/api/admin/versions?id=' + encodeURIComponent(id))).versions;
  for (const version of versions) { const snap = JSON.parse(version.snapshot); const d = node('details'); d.append(node('summary', `${version.archived_at} · ${snap.revision} · ${snap.hash}`), node('pre', JSON.stringify(snap, null, 2))); history.append(d); }
  if (!versions.length) history.append(node('p', 'Предыдущих версий нет.', 'fine'));
  box.append(history);
  const form = node('form'); const grid = node('div', undefined, 'evidence-grid');
  const labels = {currency:'Доказательство актуальности',completeness:'Проверка полноты',attachments:'Изображения и приложения',scope:'Область применения',conflicts:'Противоречия и приоритеты',reference:'Ссылка на запись проверки / первоисточник'};
  for (const [key, label] of Object.entries(labels)) { const l = node('label', label); const t = node('textarea'); t.name = key; t.required = true; t.minLength = 12; t.maxLength = 4000; l.append(t); grid.append(l); }
  const expiryLabel = node('label', 'Повторная проверка не позднее (до 90 дней)'); const expiry = node('input'); expiry.type = 'datetime-local'; expiry.required = true; expiryLabel.append(expiry);
  const toolbar = node('div', undefined, 'toolbar'); const approve = node('button', 'Подтвердить допуск', 'primary'); approve.type = 'submit'; const revoke = node('button', 'Снять допуск', 'danger'); revoke.type = 'button';
  toolbar.append(approve, revoke); form.append(node('p', 'Допуск означает вашу явную проверку актуальности и полноты конкретной версии. Наличие текста или отметки «последняя редакция» недостаточно.', 'notice'), grid, expiryLabel, toolbar); box.append(form);
  const decide = async approveFlag => { const evidence = Object.fromEntries(new FormData(form)); await api('/api/admin/decision', {source_id:id, hash:s.hash, approve:approveFlag, evidence, expires_at:approveFlag ? new Date(expiry.value).toISOString() : null}); await refreshCoverage(); sources = (await api('/api/admin/sources')).sources; renderSources(); await openSource(id); notify(approveFlag ? 'Решение о допуске сохранено в журнале.' : 'Допуск снят.'); };
  form.onsubmit = async e => { e.preventDefault(); try { await decide(true); } catch (err) { notify(err.message, true); } }; revoke.onclick = () => decide(false).catch(err => notify(err.message, true));
  const texts = node('details'); texts.append(node('summary', `Локальные фрагменты (${chunks.length})`));
  for (const c of chunks) { const d = node('details'); d.append(node('summary', c.locator), node('pre', c.body)); texts.append(d); } box.append(texts); box.scrollIntoView({behavior:'smooth',block:'start'});
}
async function renderQueue() {
  const queue = (await api('/api/admin/queue')).queue; $('queue-list').replaceChildren();
  for (const item of queue) { const row = node('div', undefined, 'queue-row'); row.append(node('strong', `${item.id} · приоритет ${item.priority} · ${item.status}`), node('pre', item.details));
    const form = node('form'); const select = node('select'); for (const [v,t] of [['requires_review','Требует проверки'],['in_scope','Релевантен'],['out_of_scope','Вне области'],['blocked','Проверка заблокирована'],['reviewed','Проверен']]) { const opt = node('option', t); opt.value = v; select.append(opt); } select.value = ['requires_review','in_scope','out_of_scope','blocked','reviewed'].includes(item.status) ? item.status : 'requires_review';
    const note = node('input'); note.placeholder = 'Обоснование решения (не менее 12 символов)'; note.required = true; note.minLength = 12; note.maxLength = 4000; const save = node('button','Сохранить оценку','quiet'); form.append(select,note,save); form.onsubmit = async e => { e.preventDefault(); try { await api('/api/admin/queue',{id:item.id,status:select.value,note:note.value}); await renderQueue(); notify('Оценка ссылки сохранена. Допуск источника не изменён.'); } catch(err){notify(err.message,true);} }; row.append(form); $('queue-list').append(row);
  }
}
async function initialize() {
  const button = $('login-form').querySelector('button');
  try {
    const health = await api('/health');
    if (health.status !== 'ok') throw new Error('Сервер приложения не готов. Повторите позже.');
    $('connection-status').hidden = true; button.disabled = false;
    try { await enter(); }
    catch (err) { showLogin(); if (err.status !== 401) $('login-error').textContent = err.message; }
  } catch (err) {
    showLogin(); $('connection-status').textContent = err.message;
    $('connection-status').hidden = false;
    button.disabled = true;
  }
}
initialize();
