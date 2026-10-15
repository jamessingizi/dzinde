// Publish: report catalog & viewer, Publisher (books), HTML website.
import { GET, POST, DEL, h, clear, modal, toast, fail, confirmBox, promptBox, select, checkbox, field, choosePerson, schemaForm, download, chooseFile, put, desktop } from './ui.js';
import { S } from './app.js';

let catalog = null;
const RECENT_KEY = 'dz_recent_reports';

export async function render(root, [tab = 'reports']) {
  catalog = catalog || await GET('/api/reports');
  const page = h('div', { style: { height: 'calc(100% - 44px)', overflow: 'auto' } });
  put(root, h('div.toolbar', h('div.tabs', [['reports', 'Reports and charts'], ['books', 'Books (Publisher)'], ['website', 'HTML website']].map(([k, l]) =>
    h('button' + (k === tab ? '.active' : ''), { onclick: () => (location.hash = '#/publish/' + k) }, l)))), page);
  await ({ reports, books, website }[tab] || reports)(page);
}

async function reports(el) {
  const recent = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').map(id => catalog.find(r => r.id === id)).filter(Boolean);
  const q = h('input', { type: 'search', placeholder: 'Filter reports…', oninput: draw, style: { width: '320px' } });
  const body = h('div');
  const cats = ['Charts (Large format)', 'Charts (Reports)', 'Forms', 'Narratives', 'Lists', 'Labels', 'Reports'];
  function draw() {
    clear(body);
    const t = q.value.toLowerCase();
    if (recent.length && !t) put(body, h('h2.section', 'Recent'), h('div.cards', recent.map(card)));
    for (const c of cats) {
      const items = catalog.filter(r => r.category === c && (!t || (r.title + r.description).toLowerCase().includes(t)));
      if (items.length) put(body, h('h2.section', c), h('div.cards', items.map(card)));
    }
  }
  const card = r => h('div.card.click', { onclick: () => runReport(r.id) }, h('h3', r.title), h('div.small.muted', r.description));
  put(el, h('div.page-pad', h('div.row', q, h('span.muted', `${catalog.length} reports`)), body));
  draw();
}

export async function reportOptions(r, values = {}) {
  const d = S.person ? await GET(`/api/person/${S.person}`).catch(() => null) : null;
  const groups = await GET('/api/groups').catch(() => []);
  const types = {
    person: (o, v) => {
      let pid = Number(v) || S.person;
      const lbl = h('span', '…');
      const setLbl = async () => { lbl.textContent = pid ? (await GET(`/api/person/${pid}`)).summary.name + ` [${pid}]` : 'choose…'; };
      setLbl();
      return [h('div.row', lbl, h('button.btn.sm', { onclick: async () => { const x = await choosePerson(); if (x) { pid = x; setLbl(); } } }, 'Change…')), () => pid];
    },
    family: (o, v) => {
      const fams = d ? d.spouses : [];
      const s = select(fams.map(f => [f.id, `${d.summary.name} & ${f.spouse?.name || 'unknown'}`]), v || fams[0]?.id);
      if (d) for (const p of d.parents) put(s, h('option', { value: p.family }, `Parents: ${[p.father?.name, p.mother?.name].filter(Boolean).join(' & ')}`));
      return [s, () => Number(s.value)];
    },
    who: (o, v) => {
      const s = select([['all', 'Everyone in the file'], [`ancestors:${S.person}`, `Ancestors of ${d?.summary.name || 'current person'}`],
        [`descendants:${S.person}`, `Descendants of ${d?.summary.name || 'current person'}`], [`person:${S.person}`, `Just ${d?.summary.name || 'current person'}`],
        ...groups.map(g => [`group:${g.GroupID}`, `Group: ${g.Name} (${g.count})`])], v || 'all');
      return [s, () => s.value];
    },
    facttypes: (o, v) => {
      const s = select(S.meta.factTypes.map(f => [f.FactTypeID, f.Name]), '', { multiple: true, size: 8 });
      const sel = String(v || '').split(',');
      [...s.options].forEach(op => (op.selected = sel.includes(op.value)));
      return [s, () => [...s.selectedOptions].map(op => op.value).join(',')];
    },
    media: (o, v) => {
      const s = h('select');
      GET('/api/media').then(ms => ms.filter(m => m.MediaType === 1).forEach(m => put(s, h('option', { value: m.MediaID, selected: String(m.MediaID) === String(v) }, m.Caption || m.MediaFile))));
      return [s, () => Number(s.value)];
    },
  };
  const saved = JSON.parse(localStorage.getItem('dz_ropts_' + r.id) || '{}');
  const form = schemaForm(r.options, Object.assign({}, saved, values), types);
  return modal({ title: r.title, wide: true, body: h('div.col', h('p.muted', r.description), form.el),
    buttons: [{ label: 'Cancel' }, { label: 'Generate report', primary: true, click: () => form.values() }] }).done;
}

export async function runReport(id, values) {
  catalog = catalog || await GET('/api/reports');
  const r = catalog.find(x => x.id === id);
  const opts = values || await reportOptions(r);
  if (!opts) return;
  const keep = Object.fromEntries(Object.entries(opts).filter(([k]) => !['person', 'person2', 'family', 'media'].includes(k)));
  localStorage.setItem('dz_ropts_' + id, JSON.stringify(keep));
  const rec = [id, ...JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').filter(x => x !== id)].slice(0, 4);
  localStorage.setItem(RECENT_KEY, JSON.stringify(rec));
  toast('Generating ' + r.title + '…');
  try {
    const { html } = await POST('/api/reports/run', { id, options: opts });
    viewer(r.title, html, () => runReport(id), `/report?id=${encodeURIComponent(id)}&opts=${encodeURIComponent(JSON.stringify(opts))}`);
  } catch (e) { fail(e); }
}

export function viewer(title, html, again, url) {
  const frame = h('iframe.report', { srcdoc: html });
  const m = modal({ title, xwide: true, body: frame, buttons: [
    again ? { label: 'Change options…', click: () => { setTimeout(again, 50); return true; } } : null,
    { label: 'Save as HTML', click: () => { download(title.replace(/[^\w ]+/g, '') + '.html', html, 'text/html'); return false; } },
    url ? { label: desktop() ? 'Open in new window' : 'Open in browser tab', click: () => { desktop() ? desktop().open_window(url, title).catch(fail) : window.open(url, '_blank'); return false; } } : null,
    { label: 'Print / Save PDF', primary: true, click: () => {
      if (desktop() && url) desktop().open_window(url, title, true).catch(fail); // WKWebView can't print an iframe
      else { frame.contentWindow.focus(); frame.contentWindow.print(); }
      return false;
    } },
  ].filter(Boolean) });
  m.body.style.padding = '0';
  return m;
}

// ---------------------------------------------------------------- books
async function books(el) {
  const list = await GET('/api/books');
  put(el, h('div.page-pad', h('div.row', h('h2', { style: { margin: 0 } }, 'Books'), h('button.btn.primary.right', { onclick: async () => { const n = await promptBox('New book', 'Title', 'Family History'); if (n) { const r = await POST('/api/book', { title: n, items: [] }); editBook(r.id); } } }, '+ New book')),
    h('p.muted', 'Combine reports, charts and text chapters into one book with a title page and table of contents.'),
    list.length ? h('div.cards', list.map(b => h('div.card.click', { onclick: () => editBook(b.id) }, h('h3', b.title), h('div.muted', `${b.data.items.length} chapters`)))) : h('p.muted', 'No books yet.')));
}

async function editBook(id) {
  const all = await GET('/api/books');
  const b = all.find(x => x.id === id);
  let items = [...b.data.items];
  const title = h('input', { value: b.title, style: { width: '100%' } }), sub = h('input', { value: b.data.subtitle || '', style: { width: '100%' } }), author = h('input', { value: b.data.author || '', style: { width: '100%' } });
  const list = h('div.list');
  function draw() {
    clear(list);
    items.forEach((it, i) => put(list, h('div', h('span.muted', i + 1), h('b', it.title || catalog.find(r => r.id === it.report)?.title || 'Text'), h('span.muted.small', it.report ? 'report' : 'text'),
      h('span.right.row', h('button.btn.sm', { disabled: !i, onclick: () => { [items[i - 1], items[i]] = [items[i], items[i - 1]]; draw(); } }, '↑'),
        h('button.btn.sm', { disabled: i === items.length - 1, onclick: () => { [items[i + 1], items[i]] = [items[i], items[i + 1]]; draw(); } }, '↓'),
        h('button.btn.sm', { onclick: async () => { if (it.report) { const o = await reportOptions(catalog.find(r => r.id === it.report), it.options); if (o) { it.options = o; it.title = o.title || it.title; } } else { await textChapter(it); } draw(); } }, 'Edit'),
        h('button.btn.sm', { onclick: () => { items.splice(i, 1); draw(); } }, '✕')))));
    if (!items.length) put(list, h('div.muted', 'No chapters yet'));
  }
  async function textChapter(it) {
    const t = h('input', { value: it.title || '', style: { width: '100%' } }), x = h('textarea', { value: it.text || '', style: { minHeight: '40vh' } });
    const ok = await modal({ title: 'Text chapter', wide: true, body: h('div.col', t, x), buttons: [{ label: 'Cancel' }, { label: 'OK', primary: true, value: true }] }).done;
    if (ok) { it.title = t.value; it.text = x.value; }
    return ok;
  }
  draw();
  const save = () => POST('/api/book', { id, title: title.value, subtitle: sub.value, author: author.value, items });
  const res = await modal({ title: 'Edit book', xwide: true, body: h('div.col', h('div.form', ...field('Title', title), ...field('Subtitle', sub), ...field('Author', author)),
    h('div.row', h('h4', 'Chapters'), h('span.grow'),
      h('button.btn.sm', { onclick: async () => {
        const sel = select(catalog.map(r => [r.id, `${r.category}: ${r.title}`]), '', { size: 14, style: { width: '100%' } });
        const rid = await modal({ title: 'Add report chapter', wide: true, body: sel, buttons: [{ label: 'Cancel' }, { label: 'Next', primary: true, click: () => sel.value || false }] }).done;
        if (!rid) return;
        const o = await reportOptions(catalog.find(r => r.id === rid));
        if (o) { items.push({ report: rid, options: o, title: o.title || catalog.find(r => r.id === rid).title }); draw(); }
      } }, '+ Report'),
      h('button.btn.sm', { onclick: async () => { const it = { title: 'Introduction', text: '' }; if (await textChapter(it)) { items.push(it); draw(); } } }, '+ Text chapter')), list),
  buttons: [{ label: 'Delete book', danger: true, click: async () => { if (await confirmBox('Delete this book?')) { await DEL(`/api/book/${id}`); return 'deleted'; } return false; } },
    { label: 'Save', click: async () => { await save(); toast('Saved'); return false; } },
    { label: 'Build & preview', primary: true, click: async () => { await save(); const { html } = await POST(`/api/book/${id}/build`); viewer(title.value, html); return false; } }] }).done;
  if (res) location.hash = '#/publish/books';
}

// ---------------------------------------------------------------- website
async function website(el) {
  const groups = await GET('/api/groups').catch(() => []);
  const who = select([['all', 'Everyone'], [`ancestors:${S.person}`, 'Ancestors of current person'], [`descendants:${S.person}`, 'Descendants of current person'], ...groups.map(g => [`group:${g.GroupID}`, 'Group: ' + g.Name])], 'all');
  const title = h('input', { value: 'Our Family History', style: { width: '100%' } });
  let folder = '';
  const folderLbl = h('span.mono.small', '(next to the database, in “Website”)');
  const o = { privatizeLiving: checkbox('Privatize living people', true), includeNotes: checkbox('Include notes', true), includeSources: checkbox('Include sources', true), includePhotos: checkbox('Include primary photos', true) };
  put(el, h('div.page-pad', { style: { maxWidth: '760px' } }, h('h2', 'HTML website'), h('p.muted', 'Creates a static website (index, surname index, one page per person) you can upload anywhere or open locally.'),
    h('div.form', ...field('Title', title), ...field('People', who), ...field('Folder', h('div.row', folderLbl, h('button.btn.sm', { onclick: async () => { const f = await chooseFile({ title: 'Output folder', folder: true }); if (f) { folder = f; folderLbl.textContent = f; } } }, 'Choose…'))),
      ...field('', h('div.col', ...Object.values(o)))),
    h('button.btn.primary', { style: { marginTop: '12px' }, onclick: async () => {
      try {
        const r = await POST('/api/tools/website', { folder, who: who.value, options: { title: title.value, ...Object.fromEntries(Object.entries(o).map(([k, c]) => [k, c.input.checked])) } });
        modal({ title: 'Website created', body: h('div.col', h('p', 'Your website was written to:'), h('p.mono', r.path), h('p.muted', 'Open index.html in that folder with your browser, or upload the folder to a web host.')) });
      } catch (e) { fail(e); }
    } }, 'Create website')));
}
