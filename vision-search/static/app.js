/* ============================================================
   Vision Search — логика интерфейса.
   Общается с бэкендом по /api/*, рисует чат и результаты.
   История и избранное хранятся локально в браузере (localStorage).
   ============================================================ */

const $ = (id) => document.getElementById(id);
const chat = $('chat');
const form = $('composer');
const queryInput = $('query');
const fileInput = $('file');
const sendBtn = $('send');
const statusEl = $('status');
const minScore = $('minScore');
const minScoreVal = $('minScoreVal');
const historyEl = $('history');

// Настройки, которые переживают перезагрузку страницы.
const store = {
  get(key, def){ try { return JSON.parse(localStorage.getItem('vs_' + key)) ?? def; } catch { return def; } },
  set(key, val){ localStorage.setItem('vs_' + key, JSON.stringify(val)); },
};

// ---- тема (тёмная/светлая) ----
function applyTheme(theme){
  document.body.setAttribute('data-theme', theme);
  store.set('theme', theme);
  $('btnTheme').textContent = theme === 'dark' ? '☾' : '☀';
}
applyTheme(store.get('theme', 'dark'));
$('btnTheme').addEventListener('click', () => {
  applyTheme(document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

// ---- порог схожести ----
minScore.value = store.get('minScore', 0);
minScoreVal.textContent = minScore.value + '%';
minScore.addEventListener('input', () => {
  minScoreVal.textContent = minScore.value + '%';
  store.set('minScore', Number(minScore.value));
});
const getMinScore = () => Number(minScore.value) / 100;  // бэкенд ждёт долю 0..1

// ---- лайтбокс ----
const lb = $('lightbox');
lb.addEventListener('click', () => lb.classList.remove('open'));
function openLightbox(src){ lb.querySelector('img').src = src; lb.classList.add('open'); }

function scrollDown(){ chat.scrollTop = chat.scrollHeight; }

// ---- сообщения чата ----
function addUser(text, imgSrc){
  const m = document.createElement('div'); m.className = 'msg user';
  const b = document.createElement('div'); b.className = 'bubble';
  if (imgSrc){ const im = document.createElement('img'); im.src = imgSrc; b.appendChild(im); }
  if (text){ const t = document.createElement('div'); t.textContent = text; b.appendChild(t); }
  m.appendChild(b); chat.appendChild(m); scrollDown();
}
function addBot(html){
  const m = document.createElement('div'); m.className = 'msg bot';
  const b = document.createElement('div'); b.className = 'bubble'; b.innerHTML = html;
  m.appendChild(b); chat.appendChild(m); scrollDown();
  return b;
}

// ---- избранное ----
function favs(){ return new Set(store.get('favs', [])); }
function toggleFav(name){
  const set = favs();
  if (set.has(name)) set.delete(name); else set.add(name);
  store.set('favs', [...set]);
  return set.has(name);
}

// ---- рендер карточек результатов ----
function renderResults(bubble, results, headline){
  if (!results || !results.length){
    bubble.innerHTML = 'Ничего не нашлось 😕 Попробуй другое описание или опусти порог схожести.';
    return;
  }
  const favSet = favs();
  bubble.innerHTML = headline || `Нашёл <b>${results.length}</b> похожих (по убыванию схожести):`;
  const grid = document.createElement('div'); grid.className = 'results';
  results.forEach(r => {
    const url = '/images/' + encodeURIComponent(r.file);
    const pct = Math.round((r.score ?? 0) * 100);
    const card = document.createElement('div'); card.className = 'card';
    const tags = (r.tags || []).map(t => `<span class="tag">${t}</span>`).join('');
    card.innerHTML = `
      ${r.ocr ? '<span class="badge-ocr">текст</span>' : ''}
      <button class="fav ${favSet.has(r.file) ? 'on' : ''}" title="В избранное">★</button>
      <img class="thumb" loading="lazy" src="${url}">
      <div class="meta"><span class="name" title="${r.file}">${r.file}</span><span class="score">${pct}%</span></div>
      ${tags ? `<div class="tags">${tags}</div>` : ''}
      <div class="actions">
        <button data-act="similar">похожие</button>
        <button data-act="open">в папке</button>
        <button data-act="copy">путь</button>
      </div>`;
    card.querySelector('.thumb').addEventListener('click', () => openLightbox(url));
    card.querySelector('.fav').addEventListener('click', (e) => {
      e.target.classList.toggle('on', toggleFav(r.file));
    });
    card.querySelector('[data-act="similar"]').addEventListener('click', () => searchSimilar(r.file));
    card.querySelector('[data-act="open"]').addEventListener('click', () => openInFolder(r.file));
    card.querySelector('[data-act="copy"]').addEventListener('click', () => copyPath(r.file));
    grid.appendChild(card);
  });
  bubble.appendChild(grid);
  scrollDown();
}

// ---- статус и прогресс индексации ----
async function refreshStatus(){
  try{
    const s = await (await fetch('/api/status')).json();
    if ($('folder') !== document.activeElement && s.folder) $('folder').value = s.folder;
    if (s.ready){
      statusEl.textContent = `Готово · ${s.count} фото`;
      statusEl.className = 'status ready';
      sendBtn.disabled = false;
    } else if (s.status === 'error'){
      statusEl.textContent = 'Ошибка';
      statusEl.className = 'status busy';
      sendBtn.disabled = true;
    } else {
      statusEl.innerHTML = `<span class="spinner"></span>Индексация ${s.done}/${s.total}`
        + `<div class="progress"><i style="width:${s.percent}%"></i></div>`;
      statusEl.className = 'status busy';
      sendBtn.disabled = true;
      setTimeout(refreshStatus, 1000);
      return;
    }
  }catch(e){
    statusEl.textContent = 'Нет связи'; setTimeout(refreshStatus, 2000);
  }
}

// ---- поиск по тексту ----
async function searchText(q){
  addUser(q, null);
  pushHistory(q);
  const bubble = addBot('<span class="spinner"></span>Ищу…');
  try{
    const data = await (await fetch('/api/search/text', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ query:q, top_k:30, min_score:getMinScore() }),
    })).json();
    renderResults(bubble, data.results);
  }catch(e){ bubble.textContent = 'Ошибка: ' + e.message; }
}

// ---- поиск по фото (и гибрид с текстом) ----
async function searchImage(file, text){
  const localUrl = URL.createObjectURL(file);
  addUser(text || '', localUrl);
  const bubble = addBot('<span class="spinner"></span>Анализирую фото…');
  try{
    const fd = new FormData();
    fd.append('image', file);
    fd.append('top_k', '30');
    fd.append('min_score', String(getMinScore()));
    if (text){ fd.append('query', text); fd.append('text_weight', '0.5'); }
    const data = await (await fetch('/api/search/image', { method:'POST', body: fd })).json();
    renderResults(bubble, data.results);
  }catch(e){ bubble.textContent = 'Ошибка: ' + e.message; }
}

// ---- «похожие на это» ----
async function searchSimilar(file){
  const bubble = addBot(`<span class="spinner"></span>Ищу похожие на <b>${file}</b>…`);
  try{
    const data = await (await fetch('/api/similar', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ file, top_k:24 }),
    })).json();
    renderResults(bubble, data.results, `Похожие на <b>${file}</b>:`);
  }catch(e){ bubble.textContent = 'Ошибка: ' + e.message; }
}

// ---- действия над файлом ----
async function openInFolder(file){
  try{ await fetch('/api/open', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ file }) }); }
  catch(e){ /* молча — на сервере могло не быть GUI */ }
}
async function copyPath(file){
  try{
    const data = await (await fetch('/api/path', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ file }) })).json();
    if (data.path){ await navigator.clipboard.writeText(data.path); toast('Путь скопирован'); }
  }catch(e){ toast('Не удалось скопировать'); }
}

// ---- поиск дубликатов ----
$('btnDuplicates').addEventListener('click', async () => {
  const bubble = addBot('<span class="spinner"></span>Ищу дубликаты…');
  try{
    const data = await (await fetch('/api/duplicates', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ distance:5 }),
    })).json();
    if (!data.groups || !data.groups.length){ bubble.textContent = 'Дубликатов не нашлось — всё чисто ✨'; return; }
    bubble.innerHTML = `Нашёл <b>${data.groups.length}</b> групп похожих картинок:`;
    data.groups.forEach((group, gi) => {
      const box = document.createElement('div'); box.className = 'dupgroup';
      box.innerHTML = `<h4>Группа ${gi + 1} · ${group.length} шт.</h4>`;
      const grid = document.createElement('div'); grid.className = 'results';
      group.forEach(name => {
        const url = '/images/' + encodeURIComponent(name);
        const card = document.createElement('div'); card.className = 'card';
        card.innerHTML = `<img class="thumb" loading="lazy" src="${url}"><div class="meta"><span class="name">${name}</span></div>`;
        card.querySelector('.thumb').addEventListener('click', () => openLightbox(url));
        grid.appendChild(card);
      });
      box.appendChild(grid); bubble.appendChild(box);
    });
    scrollDown();
  }catch(e){ bubble.textContent = 'Ошибка: ' + e.message; }
});

// ---- переиндексация и смена папки ----
$('btnReindex').addEventListener('click', async () => {
  await fetch('/api/reindex', { method:'POST' });
  refreshStatus();
});
$('btnFolder').addEventListener('click', async () => {
  const folder = $('folder').value.trim();
  if (!folder) return;
  const r = await fetch('/api/folder', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ folder }) });
  const data = await r.json();
  if (!r.ok){ toast(data.error || 'Не удалось'); return; }
  toast('Папка подключена, индексирую…');
  refreshStatus();
});

// ---- история запросов ----
function pushHistory(q){
  let h = store.get('history', []);
  h = [q, ...h.filter(x => x !== q)].slice(0, 8);
  store.set('history', h);
  renderHistory();
}
function renderHistory(){
  const h = store.get('history', []);
  historyEl.innerHTML = '';
  h.forEach(q => {
    const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = q;
    chip.addEventListener('click', () => searchText(q));
    historyEl.appendChild(chip);
  });
}

// ---- маленькое всплывающее уведомление ----
let toastTimer = null;
function toast(text){
  let t = $('toast');
  if (!t){
    t = document.createElement('div'); t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--panel);'
      + 'border:1px solid var(--line);color:var(--text);padding:10px 18px;border-radius:10px;z-index:99;box-shadow:0 8px 24px var(--shadow)';
    document.body.appendChild(t);
  }
  t.textContent = text; t.style.opacity = '1';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.opacity = '0'; }, 1800);
}

// ---- отправка формы ----
form.addEventListener('submit', (e) => {
  e.preventDefault();
  const q = queryInput.value.trim();
  const f = fileInput.files && fileInput.files[0];
  if (f){ searchImage(f, q); fileInput.value = ''; queryInput.value = ''; return; }
  if (!q) return;
  queryInput.value = '';
  searchText(q);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files && fileInput.files[0]){
    searchImage(fileInput.files[0], queryInput.value.trim());
    fileInput.value = ''; queryInput.value = '';
  }
});

// ---- drag & drop куда угодно ----
let dragDepth = 0;
window.addEventListener('dragenter', (e) => { e.preventDefault(); dragDepth++; document.body.classList.add('dragging'); });
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('dragleave', () => { if (--dragDepth <= 0){ document.body.classList.remove('dragging'); dragDepth = 0; } });
window.addEventListener('drop', (e) => {
  e.preventDefault(); dragDepth = 0; document.body.classList.remove('dragging');
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (f && f.type.startsWith('image/')) searchImage(f, queryInput.value.trim());
});

// ---- вставка фото из буфера (Ctrl+V) ----
window.addEventListener('paste', (e) => {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const it of items){ if (it.type.startsWith('image/')){ const f = it.getAsFile(); if (f) searchImage(f, queryInput.value.trim()); } }
});

// ---- подсказки-чипсы в первом сообщении ----
const firstBubble = document.querySelector('.msg.bot .bubble');
const chips = ['кот', 'собака', 'красная машина', 'пицца', 'закат', 'цветок', 'ракета', 'гитара'];
const wrap = document.createElement('div'); wrap.className = 'chips';
chips.forEach(c => {
  const el = document.createElement('span'); el.className = 'chip'; el.textContent = c;
  el.addEventListener('click', () => searchText(c)); wrap.appendChild(el);
});
firstBubble.appendChild(wrap);

renderHistory();
refreshStatus();
