// Shared UI toolkit: API client, DOM builder, dialogs, pickers, tables.

export async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: { 'X-Dzinde': '1', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return data;
}
export const GET = p => api('GET', p);
export const POST = (p, b) => api('POST', p, b || {});
export const PUT = (p, b) => api('PUT', p, b || {});
export const DEL = (p, b) => api('DELETE', p, b);

// h('div.cls#id', {attrs, onclick}, ...children)
export function h(sel, attrs, ...kids) {
  if (attrs == null || typeof attrs !== 'object' || attrs instanceof Node || Array.isArray(attrs)) { kids.unshift(attrs); attrs = {}; }
  const [tag, ...rest] = sel.split(/(?=[.#])/);
  const el = document.createElement(tag || 'div');
  for (const r of rest) r[0] === '.' ? el.classList.add(r.slice(1)) : (el.id = r.slice(1));
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k in el && k !== 'list' && k !== 'form') { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? '' : v);
  }
  add(el, kids);
  return el;
}
function add(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
export const clear = el => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
// Like Element.append but skips null/false and flattens arrays (native append would print "null").
export const put = (el, ...kids) => { add(el, kids); return el; };
export const fill = (el, ...kids) => put(clear(el), ...kids);
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---------------------------------------------------------------- icons (simple line icons)
const ICONS = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  people: 'M9 11a4 4 0 100-8 4 4 0 000 8zM2 21v-1a6 6 0 0112 0v1M17 11a3 3 0 100-6M22 21v-1a5 5 0 00-4-4.9',
  place: 'M12 21s-7-6.2-7-12a7 7 0 1114 0c0 5.8-7 12-7 12zM12 11a2 2 0 100-4 2 2 0 000 4z',
  source: 'M4 4h12a4 4 0 014 4v12H8a4 4 0 01-4-4zM8 8h8M8 12h8M8 16h5',
  media: 'M3 5h18v14H3zM3 15l5-5 4 4 3-3 6 6M15 9a1 1 0 100-2 1 1 0 000 2z',
  task: 'M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2h9',
  address: 'M4 4h16v16H4zM8 9h8M8 13h8M8 17h4',
  search: 'M11 18a7 7 0 100-14 7 7 0 000 14zM21 21l-5-5',
  publish: 'M6 9V3h12v6M6 18H4v-6a2 2 0 012-2h12a2 2 0 012 2v6h-2M7 14h10v7H7z',
  tools: 'M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z',
  settings: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-2.9 1.2V21a2 2 0 11-4 0v-.1A1.7 1.7 0 006 19.4l-.1.1a2 2 0 11-2.8-2.8l.1-.1A1.7 1.7 0 003 13.7H3a2 2 0 110-4h.1A1.7 1.7 0 004.6 6l-.1-.1a2 2 0 112.8-2.8l.1.1A1.7 1.7 0 009.3 3V3a2 2 0 114 0v.1a1.7 1.7 0 002.9 1.2l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 001.2 2.9H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z',
  back: 'M15 18l-6-6 6-6', fwd: 'M9 18l6-6-6-6', plus: 'M12 5v14M5 12h14', edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3', star: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
  link: 'M10 14a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 10a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1', print: 'M6 9V3h12v6M6 18H4v-6h16v6h-2M7 14h10v7H7z',
  folder: 'M3 6h6l2 2h10v11H3z', file: 'M6 3h9l4 4v14H6zM14 3v5h5', up: 'M12 19V5M5 12l7-7 7 7',
};
export function icon(name, size) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor');
  s.setAttribute('stroke-width', '1.8'); s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  if (size) { s.setAttribute('width', size); s.setAttribute('height', size); }
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', ICONS[name] || ''); s.append(p);
  return s;
}

// ---------------------------------------------------------------- toasts & dialogs
export function toast(msg, kind = '') {
  const t = h('div.toast' + (kind ? '.' + kind : ''), msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 6000 : 3000);
}
export function fail(e) { console.error(e); toast(e.message || String(e), 'err'); }

const stack = [];
export function modal({ title, body, buttons = [], wide = false, xwide = false, onclose } = {}) {
  let resolve;
  const done = new Promise(r => (resolve = r));
  const footer = h('footer');
  const box = h('div.modal' + (wide ? '.wide' : '') + (xwide ? '.xwide' : ''), { role: 'dialog', 'aria-modal': 'true' },
    h('header', h('h2', title || ''), h('button.icon-btn', { onclick: () => close(null), 'aria-label': 'Close', title: 'Close (Esc)' }, '✕')),
    h('div.mbody', body), footer);
  const back = h('div.backdrop', { onmousedown: e => { if (e.target === back) close(null); } }, box);
  function close(v) {
    if (!back.isConnected) return;
    back.remove(); stack.splice(stack.indexOf(api_), 1); onclose && onclose(v); resolve(v);
  }
  for (const b of buttons) {
    footer.append(h('button.btn' + (b.primary ? '.primary' : '') + (b.danger ? '.danger' : ''), {
      onclick: async () => {
        if (!b.click) return close(b.value ?? null);
        try { const v = await b.click(); if (v !== false) close(v ?? b.value ?? true); } catch (e) { fail(e); }
      },
    }, b.label));
  }
  if (!buttons.length) footer.remove();
  document.body.append(back);
  const api_ = { el: box, body: box.querySelector('.mbody'), close, done, title: box.querySelector('h2') };
  stack.push(api_);
  setTimeout(() => { const f = box.querySelector('[autofocus], input, select, textarea'); f && f.focus(); }, 30);
  return api_;
}
export function topModal() { return stack[stack.length - 1]; }
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && stack.length) { e.preventDefault(); stack[stack.length - 1].close(null); }
  if (e.key === 'Enter' && stack.length && e.target.tagName === 'INPUT' && !e.target.closest('.no-enter')) {
    const btn = stack[stack.length - 1].el.querySelector('footer .btn.primary');
    if (btn) { e.preventDefault(); btn.click(); }
  }
});
export function confirmBox(msg, { ok = 'OK', danger = false, title = 'Confirm' } = {}) {
  return modal({ title, body: h('p', msg), buttons: [{ label: 'Cancel', value: false }, { label: ok, primary: !danger, danger, value: true }] }).done.then(Boolean);
}
export function promptBox(title, label, value = '') {
  const inp = h('input', { value, style: { width: '100%' } });
  return modal({ title, body: h('div.col', h('label', label), inp), buttons: [{ label: 'Cancel' }, { label: 'OK', primary: true, click: () => inp.value }] }).done;
}
export function alertBox(title, body) {
  return modal({ title, body: typeof body === 'string' ? h('p', body) : body, buttons: [{ label: 'Close', primary: true }] }).done;
}

// ---------------------------------------------------------------- tables
// columns: [{key, label, render(row)->node|string, sort(row)->value, width}]
export function dataTable(columns, rows, { onclick, selectable = false, filter = true, empty = 'Nothing to show', height } = {}) {
  let sortKey = null, asc = true, sel = null, text = '';
  const tbody = h('tbody');
  const thead = h('thead', h('tr', columns.map(c => h('th', { style: c.width ? { width: c.width } : null, onclick: () => { asc = sortKey === c.key ? !asc : true; sortKey = c.key; draw(); } }, c.label))));
  const tbl = h('table.dt', thead, tbody);
  const wrap = h('div.dt-wrap', { style: height ? { maxHeight: height } : null }, tbl);
  const fbox = h('input', { type: 'search', placeholder: 'Filter…', oninput: e => { text = e.target.value.toLowerCase(); draw(); } });
  const count = h('span.muted.small');
  function val(c, r) { return c.sort ? c.sort(r) : (r[c.key] ?? ''); }
  function draw() {
    clear(tbody);
    let list = rows;
    if (text) list = list.filter(r => columns.some(c => String(c.text ? c.text(r) : val(c, r)).toLowerCase().includes(text)));
    if (sortKey) {
      const c = columns.find(c => c.key === sortKey);
      list = [...list].sort((a, b) => { const x = val(c, a), y = val(c, b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
    }
    for (const r of list) {
      const tr = h('tr' + (onclick ? '.click' : ''), { onclick: () => { if (selectable) { tbody.querySelectorAll('tr.sel').forEach(t => t.classList.remove('sel')); tr.classList.add('sel'); sel = r; } onclick && onclick(r, tr); } },
        columns.map(c => h('td', c.render ? c.render(r) : String(r[c.key] ?? ''))));
      tbody.append(tr);
    }
    if (!list.length) tbody.append(h('tr', h('td.muted', { colSpan: columns.length }, empty)));
    count.textContent = `${list.length} of ${rows.length}`;
  }
  draw();
  const el = h('div.col', { style: { gap: '6px', minHeight: 0, flex: 1 } }, filter ? h('div.row', fbox, count) : null, wrap);
  el.setRows = r => { rows = r; draw(); };
  el.selected = () => sel;
  return el;
}

// ---------------------------------------------------------------- form helpers
export function field(label, input, { full = false, hint } = {}) {
  return [h('label', label), h('div' + (full ? '.full' : ''), input, hint ? h('div.hint', hint) : null)];
}
export function select(options, value, attrs = {}) {
  const s = h('select', attrs);
  for (const o of options) {
    const [v, l] = Array.isArray(o) ? o : [o, o];
    s.append(h('option', { value: v, selected: String(v) === String(value) }, l));
  }
  return s;
}
export function checkbox(label, checked, attrs = {}) {
  const c = h('input', Object.assign({ type: 'checkbox', checked: !!checked }, attrs));
  const l = h('label.chk', c, label);
  l.input = c;
  return l;
}

// Date input with live parse feedback (shows how the date will be stored/displayed)
export function dateInput(value = '', attrs = {}) {
  const inp = h('input', Object.assign({ value, placeholder: 'e.g. 12 Jan 1850, abt 1850, bet 1840 and 1850' }, attrs));
  const hint = h('div.datehint');
  const check = debounce(async () => {
    if (!inp.value.trim()) { hint.textContent = ''; return; }
    try {
      const r = await GET('/api/date/parse?text=' + encodeURIComponent(inp.value));
      hint.textContent = r.isText ? 'Text date (not sortable)' : '→ ' + r.display;
      hint.classList.toggle('text', r.isText);
    } catch { /* offline */ }
  }, 300);
  inp.addEventListener('input', check);
  if (value) check();
  const w = h('div', inp, hint);
  w.input = inp;
  Object.defineProperty(w, 'value', { get: () => inp.value, set: v => { inp.value = v; check(); } });
  inp.style.width = '100%';
  return w;
}

let placeCache = null;
export function invalidatePlaces() { placeCache = null; }
export function placeInput(value = '', attrs = {}) {
  const id = 'dl' + Math.random().toString(36).slice(2);
  const inp = h('input', Object.assign({ value, list: id, style: { width: '100%' }, placeholder: 'City, County, State, Country' }, attrs));
  inp.setAttribute('list', id);
  const dl = h('datalist', { id });
  (async () => {
    placeCache = placeCache || await GET('/api/places').catch(() => []);
    for (const p of placeCache) dl.append(h('option', { value: p.Name }));
  })();
  const w = h('div', inp, dl);
  w.input = inp;
  Object.defineProperty(w, 'value', { get: () => inp.value, set: v => (inp.value = v) });
  return w;
}

// ---------------------------------------------------------------- person helpers
export const yrs = (b, d) => (b || d) ? `${b || '?'}–${d || ''}` : '';
export function lifeOf(p) {
  if (!p) return '';
  return yrs(p.birthYear, p.deathYear);
}
export function personLine(p, { ids = true } = {}) {
  if (!p) return h('span.muted', '—');
  return h('span', p.name || '(no name)', ' ', h('span.muted.small', lifeOf(p) + (ids ? ` [${p.id}]` : '')));
}
export function sexClass(sex) { return sex === 0 ? 'm' : sex === 1 ? 'f' : ''; }

// Person picker: search the index, choose existing person; optional "add new" form
export function choosePerson({ title = 'Select person', allowNew = false, exclude = [] } = {}) {
  let rows = [], selIdx = 0;
  const q = h('input', { type: 'search', placeholder: 'Surname, given  — or ID', style: { width: '100%' }, autofocus: true });
  const list = h('div.list', { style: { maxHeight: '50vh', overflow: 'auto', marginTop: '8px' } });
  const load = debounce(async () => {
    const r = await GET('/api/people?alt=1&limit=300&q=' + encodeURIComponent(q.value));
    rows = r.rows.filter(x => !exclude.includes(x[0]));
    selIdx = 0;
    draw();
  }, 180);
  function draw() {
    clear(list);
    rows.forEach((r, i) => list.append(h('div', {
      style: { cursor: 'pointer', background: i === selIdx ? 'var(--sel)' : '' },
      onclick: () => m.close(r[0]),
    }, h('span', `${r[1]}${r[1] && r[2] ? ', ' : ''}${r[2]}${r[3] ? ' ' + r[3] : ''}`, r[7] ? '' : h('span.muted', ' (alt name)')),
      h('span.muted.small.right', `${yrs(r[4], r[5])} [${r[0]}]`))));
    if (!rows.length) list.append(h('div.muted', 'No matches'));
  }
  q.addEventListener('input', load);
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { selIdx = Math.min(rows.length - 1, selIdx + 1); draw(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { selIdx = Math.max(0, selIdx - 1); draw(); e.preventDefault(); }
    if (e.key === 'Enter' && rows[selIdx]) { e.preventDefault(); e.stopPropagation(); m.close(rows[selIdx][0]); }
  });
  const buttons = [{ label: 'Cancel' }];
  if (allowNew) buttons.unshift({ label: '+ Add new person', value: 'new' });
  const m = modal({ title, body: h('div.no-enter', q, list), buttons });
  load();
  return m.done;
}

// ---------------------------------------------------------------- local file browser
// Desktop build (pywebview): native dialogs, file saving and windows. Undefined in a normal browser.
export const desktop = () => window.pywebview?.api;

export function chooseFile({ title = 'Choose file', ext = '', dir = '', folder = false, save = false, defaultName = '' } = {}) {
  if (desktop()) return desktop().choose({ title, ext, dir, folder, save, defaultName });
  let cur = dir;
  const pathLbl = h('div.mono.small.muted');
  const list = h('div.list', { style: { height: '46vh', overflow: 'auto' } });
  const nameInp = h('input', { value: defaultName, style: { width: '100%' }, placeholder: 'File name' });
  async function load(d) {
    try {
      const r = await GET(`/api/browse?ext=${encodeURIComponent(ext)}&dir=${encodeURIComponent(d || '')}`);
      cur = r.dir; pathLbl.textContent = r.dir; clear(list);
      list.append(h('div', { style: { cursor: 'pointer' }, onclick: () => load(r.parent) }, icon('up', 16), '..'));
      list.append(h('div', { style: { cursor: 'pointer' }, onclick: () => load(r.home) }, icon('home', 16), 'Home'));
      for (const e of r.entries) {
        if (folder && !e.dir) continue;
        list.append(h('div', {
          style: { cursor: 'pointer' },
          onclick: () => e.dir ? load(e.path) : (save ? (nameInp.value = e.name) : m.close(e.path)),
        }, icon(e.dir ? 'folder' : 'file', 16), e.name, e.dir ? '' : h('span.muted.small.right', fmtSize(e.size))));
      }
    } catch (e) { fail(e); }
  }
  const buttons = [{ label: 'Cancel' }];
  if (folder) buttons.push({ label: 'Choose this folder', primary: true, click: () => cur });
  if (save) buttons.push({ label: 'Save', primary: true, click: () => nameInp.value ? cur.replace(/\/$/, '') + '/' + nameInp.value : false });
  const m = modal({ title, wide: true, body: h('div.col.no-enter', pathLbl, list, save ? nameInp : null), buttons });
  load(dir);
  return m.done;
}
export const fmtSize = n => n > 1e6 ? (n / 1e6).toFixed(1) + ' MB' : n > 1e3 ? Math.round(n / 1e3) + ' KB' : n + ' B';

// Build a form from a schema [{key,type,label,default,choices,min,max}] -> {el, values()}
export function schemaForm(schema, values = {}, extraTypes = {}) {
  const getters = {};
  const el = h('div.form');
  for (const o of schema) {
    const v = values[o.key] ?? o.default ?? '';
    let input, get;
    if (extraTypes[o.type]) { [input, get] = extraTypes[o.type](o, v); }
    else if (o.type === 'bool') { const c = checkbox('', v); input = c; get = () => c.input.checked; }
    else if (o.type === 'int') { input = h('input', { type: 'number', value: v, min: o.min, max: o.max, style: { width: '110px' } }); get = () => Number(input.value); }
    else if (o.type === 'select') { input = select(o.choices, v); get = () => input.value; }
    else { input = h('input', { value: v, style: { width: '100%' } }); get = () => input.value; }
    getters[o.key] = get;
    el.append(...field(o.label, input));
  }
  return { el, values: () => Object.fromEntries(Object.entries(getters).map(([k, g]) => [k, g()])) };
}

export function download(name, text, type = 'text/plain') {
  if (desktop()) return desktop().save_text(name, text).then(p => p && toast('Saved ' + p), fail);
  const a = h('a', { href: URL.createObjectURL(new Blob([text], { type })), download: name });
  document.body.append(a); a.click(); a.remove();
}
export function readFileAs(file, how = 'text') {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result); r.onerror = rej;
    how === 'text' ? r.readAsText(file) : r.readAsDataURL(file);
  });
}
