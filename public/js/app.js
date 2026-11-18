const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const md = s => esc(s).replace(/```([\s\S]*?)```/g,'<pre>$1</pre>').replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>');
async function api(u, o = {}) {
  const r = await fetch(u, {headers:{'Content-Type':'application/json'}, ...o});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const post = (u, b) => api(u, {method:'POST', body: JSON.stringify(b)});
const pct = s => Math.max(0, Math.round(s * 100));
const getK = () => +(localStorage.getItem('k') || 5);

/* ---------- navigation ---------- */
const loaders = {overview: loadOverview, knowledge: loadDocs, analytics: loadAnalytics, history: loadHistory, settings: loadSettings};
function show(v) {
  $$('.view').forEach(e => e.classList.toggle('active', e.id === 'v-' + v));
  $$('#nav button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  location.hash = v; window.scrollTo(0, 0); if (typeof setMenu === 'function') setMenu(false);
  loaders[v]?.();
}
$$('#nav button').forEach(b => b.onclick = () => show(b.dataset.view));
$$('[data-go]').forEach(b => b.onclick = () => show(b.dataset.go));

/* ---------- overview / analytics ---------- */
const recentHTML = r => r.length ? r.map(x => `<div class="item recent"><span class="q"><i class="bi bi-search"></i> ${esc(x.query)}</span><span class="tag">${x.results} results · ${pct(x.top_score)}%</span></div>`).join('') : '<div class="empty">No searches yet. Try the Search page.</div>';
async function loadOverview() {
  const s = await api('/api/stats');
  $('#s-docs').textContent = s.documents; $('#s-chats').textContent = s.conversations;
  $('#s-searches').textContent = s.searches; $('#s-avg').textContent = s.avg_results;
  $('#recent').innerHTML = recentHTML(s.recent);
}
async function loadAnalytics() {
  const s = await api('/api/stats');
  $('#a-total').textContent = s.searches; $('#a-score').textContent = pct(s.avg_score) + '%';
  $('#a-emb').textContent = `${s.embedded}/${s.documents}`; $('#a-cats').textContent = s.categories.length;
  const max = Math.max(1, ...s.categories.map(c => c.n));
  $('#a-bars').innerHTML = s.categories.map(c => `<div class="brow"><span>${esc(c.category)}</span><div class="bar"><i style="width:${c.n / max * 100}%"></i></div><span>${c.n}</span></div>`).join('');
  $('#a-recent').innerHTML = recentHTML(s.recent);
}

/* ---------- semantic search ---------- */
const resultHTML = r => `<div class="res"><div class="top"><span class="tag">${esc(r.category)}</span><span class="score">${pct(r.score)}% similarity</span></div>
  <div>${esc(r.text)}</div><div class="bar"><i style="width:${Math.min(100, pct(r.score))}%"></i></div></div>`;
async function doSearch(query) {
  const q = (query || $('#q').value).trim(); if (!q) return;
  $('#q').value = q; $('#go').disabled = true; $('#results').innerHTML = '<div class="empty">Searching by meaning...</div>';
  try {
    const {results} = await post('/api/search', {query: q, k: getK()});
    $('#results').innerHTML = results.length ? results.map(resultHTML).join('') + '<div class="note">Scores show relative similarity between meanings. They are not an accuracy percentage.</div>'
      : '<div class="empty">No results. Add documents in Knowledge Base and generate embeddings.</div>';
  } catch (e) { $('#results').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  $('#go').disabled = false;
}
$('#go').onclick = () => doSearch();
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
$$('#suggest button').forEach(b => b.onclick = () => doSearch(b.textContent));

/* ---------- knowledge base ---------- */
async function loadDocs() {
  embedStatus();
  const docs = await api('/api/docs');
  $('#k-count').textContent = docs.length + ' documents';
  $('#cats').innerHTML = [...new Set(docs.map(d => d.category))].map(c => `<option value="${esc(c)}">`).join('');
  $('#k-list').innerHTML = docs.length ? docs.map(d => `<div class="item"><div><div>${esc(d.text)}</div><span class="tag">${esc(d.category)}</span> ${d.embedded ? '' : '<span class="muted" style="font-size:.75rem">not embedded</span>'}</div>
    <button class="x" data-id="${d.id}" aria-label="Delete"><i class="bi bi-trash3"></i></button></div>`).join('') : '<div class="empty">Your knowledge base is empty. Add your first document above.</div>';
  $$('#k-list .x').forEach(b => b.onclick = async () => { await api('/api/docs/' + b.dataset.id, {method:'DELETE'}); loadDocs(); });
}
const kmsg = t => $('#k-msg').textContent = t;
const safe = fn => async () => { try { await fn(); } catch (e) { kmsg(e.message); } };
let wasRunning = false, pollT = null;
async function embedStatus() {
  clearTimeout(pollT);
  const s = await api('/api/embed/status'), el = $('#k-status');
  if (s.running) { wasRunning = true; el.textContent = `Generating embeddings: ${s.done}/${s.total}...`; pollT = setTimeout(embedStatus, 1500); return; }
  el.textContent = s.error ? `Embedding stopped: ${s.error}` : s.pending ? `${s.pending} document(s) not embedded yet. Press "Embed missing".` : 'All documents are embedded and ready to search.';
  if (wasRunning) { wasRunning = false; loadDocs(); }
}
const watchEmbed = () => { wasRunning = true; setTimeout(embedStatus, 700); };
async function addDocs(docs) {
  kmsg('Saving...');
  const r = await post('/api/docs', {docs});
  kmsg(`Added ${r.added} document(s). Embeddings are generated in the background.`);
  await loadDocs(); watchEmbed();
}
$('#k-add').onclick = safe(async () => {
  const text = $('#k-text').value.trim(); if (!text) return kmsg('Write some text first.');
  await addDocs([{text, category: $('#k-cat').value || 'General'}]); $('#k-text').value = '';
});
const clean = t => String(t || '').replace(/\s+/g, ' ').trim().slice(0, 600);
$('#k-file').onchange = safe(async () => {
  const inp = $('#k-file'), f = inp.files[0]; inp.value = ''; if (!f) return;
  if (!/\.(txt|json|md)$/i.test(f.name)) return kmsg('Only .txt, .json or .md files are supported. PowerPoint, Word and PDF files cannot be read.');
  const t = await f.text();
  if (/[\u0000\uFFFD]/.test(t.slice(0, 3000))) return kmsg('This looks like a binary file, not text. Nothing was added.');
  const cat = $('#k-cat').value || 'General';
  let docs;
  try {
    if (/\.json$/i.test(f.name)) {
      let j = JSON.parse(t); if (!Array.isArray(j)) j = j.documents || j.docs || [];
      docs = j.map(x => typeof x === 'string' ? {text: x, category: cat} : {text: x.text, category: x.category || cat});
    } else docs = t.split(/\n+/).map(x => ({text: x, category: cat}));
  } catch { return kmsg('Could not read the JSON. Use a list like [{"text": "...", "category": "..."}].'); }
  docs = docs.map(d => ({text: clean(d.text), category: d.category})).filter(d => d.text.length >= 15).slice(0, 200);
  if (!docs.length) return kmsg('No usable text found. Each line needs at least 15 characters.');
  await addDocs(docs);
});
$('#k-re').onclick = safe(async () => { kmsg('Re-generating all embeddings...'); await post('/api/docs/reembed', {}); await loadDocs(); watchEmbed(); });
$('#k-pend').onclick = safe(async () => { kmsg('Embedding missing documents...'); await post('/api/embed', {}); watchEmbed(); });
$('#k-reset').onclick = safe(async () => {
  if (!confirm('Delete ALL documents and restore the sample documents?')) return;
  await post('/api/docs/reset', {sample: true}); kmsg('Sample documents restored.'); await loadDocs(); watchEmbed();
});
$('#k-clear').onclick = safe(async () => {
  if (!confirm('Delete ALL documents?')) return;
  await post('/api/docs/reset', {sample: false}); kmsg('All documents deleted.'); loadDocs();
});

/* ---------- history / settings ---------- */
async function loadHistory() {
  const c = await api('/api/chats');
  $('#h-list').innerHTML = c.length ? c.map(x => `<div class="card-x item" style="margin-bottom:.6rem"><div style="cursor:pointer;flex:1" data-open="${x.id}"><b>${esc(x.title)}</b><div class="muted" style="font-size:.78rem">${x.n} messages · ${esc(x.created)}</div></div>
    <button class="x" data-del="${x.id}" aria-label="Delete"><i class="bi bi-trash3"></i></button></div>`).join('') : '<div class="empty">No conversations yet. Start one in the Workspace.</div>';
  $$('[data-open]').forEach(b => b.onclick = () => openChat(+b.dataset.open, b.querySelector('b').textContent));
  $$('[data-del]').forEach(b => b.onclick = async () => { await api('/api/chats/' + b.dataset.del, {method:'DELETE'}); loadHistory(); });
}
async function loadSettings() {
  const s = await api('/api/settings');
  $('#st-chat').textContent = s.chat_model; $('#st-emb').textContent = s.embed_model;
  $('#st-key').textContent = s.api_key ? 'Configured' : 'Missing'; $('#st-k').value = getK();
}
$('#st-k').onchange = e => localStorage.setItem('k', e.target.value);

/* ---------- AI workspace ---------- */
let chatId = null, busy = false;
const box = $('#messages');
const TOOL_LABEL = {calculator:'Calculator', get_weather:'Live weather', convert_currency:'Currency conversion', calculate_age:'Age calculator', search_knowledge:'Semantic search'};
function welcome() {
  box.innerHTML = `<div class="empty" style="margin:auto"><i class="bi bi-stars" style="font-size:1.6rem;color:var(--coral)"></i><p>Just type. The assistant decides whether to chat, search your knowledge or run a tool.</p>
  <div class="chips" style="justify-content:center">${['How can I learn programming?','What is 25 × 8?','Weather in Karachi','Convert 100 USD to PKR'].map(t => `<button>${t}</button>`).join('')}</div></div>`;
  box.querySelectorAll('.chips button').forEach(b => b.onclick = () => send(b.textContent));
}
function bubble(role, html = '') {
  if (box.querySelector('.empty')) box.innerHTML = '';
  const d = document.createElement('div'); d.className = 'm ' + role; d.innerHTML = html; box.appendChild(d);
  box.scrollTop = box.scrollHeight; return d;
}
function finishAI(d, text) {
  d.querySelector('.body').innerHTML = md(text);
  if (!d.querySelector('.copy')) { const c = document.createElement('button'); c.className = 'copy'; c.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
    c.onclick = () => { navigator.clipboard.writeText(text); c.textContent = 'Copied'; }; d.appendChild(c); }
}
async function send(text) {
  text = (text ?? $('#msg').value).trim(); if (!text || busy) return;
  busy = true; $('#msg').value = ''; $('#msg').style.height = 'auto';
  bubble('user', esc(text));
  const ai = bubble('ai', '<div class="tools"></div><div class="body"><span class="dots"><span></span><span></span><span></span></span></div><div class="srcs"></div>');
  let full = '';
  try {
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message: text, chat_id: chatId})});
    if (!r.ok) throw new Error((await r.json()).error || 'Request failed');
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
    while (true) {
      const {done, value} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream: true}); const lines = buf.split('\n'); buf = lines.pop();
      for (const l of lines.filter(Boolean)) {
        const ev = JSON.parse(l);
        if (ev.type === 'chat') { chatId = ev.id; $('#chat-title').textContent = text.slice(0, 40); }
        else if (ev.type === 'tool') ai.querySelector('.tools').innerHTML += `<span class="tool"><i class="bi bi-lightning-charge-fill"></i>${TOOL_LABEL[ev.name] || ev.name}</span>`;
        else if (ev.type === 'sources') ai.querySelector('.srcs').innerHTML = ev.items.map(s => `<div class="src">${esc(s.text)} <span class="tag">${esc(s.category)} · ${pct(s.score)}%</span></div>`).join('');
        else if (ev.type === 'text') { full += ev.text; ai.querySelector('.body').innerHTML = md(full); }
        else if (ev.type === 'error') throw new Error(ev.message);
        box.scrollTop = box.scrollHeight;
      }
    }
    finishAI(ai, full || 'No response received.');
  } catch (e) { ai.querySelector('.body').innerHTML = `<span style="color:var(--coral)">${esc(e.message)}</span>`; }
  busy = false;
}
async function openChat(id, title) {
  const msgs = await api('/api/chats/' + id); chatId = id; $('#chat-title').textContent = title; show('workspace'); box.innerHTML = '';
  msgs.forEach(m => { if (m.role === 'user') bubble('user', esc(m.content)); else finishAI(bubble('ai', '<div class="body"></div>'), m.content); });
}
$('#send').onclick = () => send();
$('#msg').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
$('#msg').oninput = e => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; };
$('#new-chat').onclick = () => { chatId = null; $('#chat-title').textContent = 'New chat'; welcome(); };
$('#clear-chat').onclick = async () => { if (chatId) await api('/api/chats/' + chatId, {method:'DELETE'}); $('#new-chat').click(); };

const burger = $('#burger'), nav = $('#nav');
function setMenu(o) { nav.classList.toggle('open', o); burger.classList.toggle('open', o); burger.setAttribute('aria-expanded', o); }
burger.onclick = e => { e.stopPropagation(); setMenu(!nav.classList.contains('open')); };
document.addEventListener('click', e => { if (!nav.contains(e.target)) setMenu(false); });
document.addEventListener('keydown', e => e.key === 'Escape' && setMenu(false));
addEventListener('resize', () => innerWidth > 820 && setMenu(false));
welcome();
show(location.hash.slice(1) && $('#v-' + location.hash.slice(1)) ? location.hash.slice(1) : 'overview');
