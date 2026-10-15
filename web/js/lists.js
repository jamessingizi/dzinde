// List pages (Places, Sources, Media, Tasks, Addresses/Repositories) and list managers.
import { GET, POST, PUT, DEL, h, clear, modal, toast, fail, confirmBox, promptBox, dataTable, select, checkbox, field, dateInput, chooseFile, personLine, debounce, invalidatePlaces, readFileAs, put, fill, safeUrl } from './ui.js';
import { S, emit, goPerson } from './app.js';
import { citationsPanel, mediaPanel, webtagsPanel, noteEditor } from './edit.js';

const split = (left, right) => h('div.split', h('div.lpane', left), h('div', right));

// ================================================================ places
export async function renderPlaces(root) {
  const detail = h('div.page-pad');
  let rows = await GET('/api/places');
  const table = dataTable([
    { key: 'Name', label: 'Place' }, { key: 'uses', label: 'Uses', width: '50px' },
    { key: 'geo', label: '', width: '20px', render: p => p.Latitude || p.Longitude ? '📍' : '', sort: p => !!(p.Latitude || p.Longitude) },
  ], rows, { onclick: p => showPlace(p.PlaceID), selectable: true });
  const tb = h('div.toolbar', h('b', 'Places'), h('span.grow'),
    h('button.btn.sm', { onclick: async () => { const n = await promptBox('New place', 'Place name (City, County, State, Country)'); if (n) { const r = await POST('/api/place', { Name: n }); reload(r.id); } } }, '+ Add'),
    h('button.btn.sm', { onclick: mergePlaces }, 'Merge…'),
    h('button.btn.sm', { onclick: () => import('./tools.js').then(m => m.run('countyCheck')) }, 'Check places'));
  put(root, split([tb, h('div', { style: { padding: '8px', flex: 1, minHeight: 0, display: 'flex' } }, table)], detail));
  async function reload(sel) { rows = await GET('/api/places'); table.setRows(rows); invalidatePlaces(); if (sel) showPlace(sel); }
  async function showPlace(id) {
    const p = await GET(`/api/place/${id}`);
    const name = h('input', { value: p.Name, style: { width: '100%' } }), abbr = h('input', { value: p.Abbrev || '', style: { width: '100%' } });
    const norm = h('input', { value: p.Normalized || '', style: { width: '100%' } });
    const lat = h('input', { value: p.Latitude ? (p.Latitude / 1e7).toFixed(6) : '', style: { width: '130px' } });
    const lon = h('input', { value: p.Longitude ? (p.Longitude / 1e7).toFixed(6) : '', style: { width: '130px' } });
    const note = h('textarea', { value: p.Note || '' });
    const media = h('div'), cites = h('div'), tags = h('div');
    fill(detail, 
      h('div.row', h('h2', { style: { margin: 0 } }, p.Name), h('span.muted', `#${p.PlaceID}`),
        h('div.right.row', h('button.btn.primary', { onclick: save }, 'Save'), h('button.btn', { onclick: () => geocode(p.Name) }, 'Geocode'),
          h('button.btn', { onclick: splitPlace }, 'Split detail…'),
          h('button.btn.danger', { onclick: async () => { if (await confirmBox(`Delete ${p.Name}? ${p.events.length} facts will lose their place.`, { danger: true })) { await DEL(`/api/place/${id}`); clear(detail); reload(); } } }, 'Delete'))),
      h('div.form', { style: { marginTop: '10px' } }, ...field('Place', name), ...field('Abbreviation', abbr), ...field('Standardized', norm),
        ...field('Latitude / Longitude', h('div.row', lat, lon, (p.Latitude || p.Longitude) ? h('a', { href: `https://www.openstreetmap.org/?mlat=${p.Latitude / 1e7}&mlon=${p.Longitude / 1e7}#map=12/${p.Latitude / 1e7}/${p.Longitude / 1e7}`, target: '_blank', rel: 'noopener' }, 'view map') : '')),
        ...field('Note', note)),
      h('h4', `Place details (${p.details.length})`), h('div.list', p.details.length ? p.details.map(d => h('div', d.Name,
        h('button.btn.sm.right', { onclick: async () => { const n = await promptBox('Rename place detail', 'Name', d.Name); if (n) { await POST('/api/place', { PlaceID: d.PlaceID, Name: n }); showPlace(id); } } }, 'Rename'))) : h('div.muted', 'None')),
      h('h4', `Used by ${p.events.length} facts`), h('div.list', { style: { maxHeight: '240px', overflow: 'auto' } }, p.events.map(e => h('div', { style: { cursor: 'pointer' }, onclick: () => e.person && goPerson(e.person) },
        h('b', e.fact), e.who, h('span.muted.small', e.date), e.detail ? h('span.muted.small.right', e.detail) : ''))),
      h('h4', 'Media'), media, h('h4', 'Citations'), cites, h('h4', 'WebTags'), tags);
    mediaPanel(media, 5, id); citationsPanel(cites, 5, id); webtagsPanel(tags, 5, id);
    async function save() {
      await POST('/api/place', { PlaceID: id, Name: name.value, Abbrev: abbr.value, Normalized: norm.value, Latitude: lat.value, Longitude: lon.value, Note: note.value });
      toast('Place saved'); reload(id);
    }
    async function geocode(q) {
      try {
        const res = await GET('/api/geocode?q=' + encodeURIComponent(q));
        const sel = select(res.map((r, i) => [i, `${r.name}  (${r.lat.toFixed(4)}, ${r.lon.toFixed(4)})`]), 0, { size: Math.min(8, res.length + 1), style: { width: '100%' } });
        const i = await modal({ title: 'Geocode — OpenStreetMap results', wide: true, body: res.length ? h('div.col', sel, h('label.chk', h('input', { type: 'checkbox', id: 'gcstd' }), 'Also use as standardized name')) : h('p', 'No results.'),
          buttons: [{ label: 'Cancel' }, { label: 'Use', primary: true, click: () => res.length ? Number(sel.value) + 1 : false }] }).done;
        if (i) { const r = res[i - 1]; lat.value = r.lat.toFixed(6); lon.value = r.lon.toFixed(6); if (document.getElementById('gcstd')?.checked) norm.value = r.name; }
      } catch (e) { fail(e); }
    }
    async function splitPlace() {
      const parts = p.Name.split(',').map(s => s.trim());
      const det = h('input', { value: parts[0], style: { width: '100%' } }), rest = h('input', { value: parts.slice(1).join(', '), style: { width: '100%' } });
      const ok = await modal({ title: 'Split place into place + place detail', body: h('div.form', ...field('Place detail', det, { hint: 'e.g. cemetery, church, hospital' }), ...field('Place', rest)),
        buttons: [{ label: 'Cancel' }, { label: 'Split', primary: true, click: () => POST(`/api/place/${id}/split`, { detail: det.value, place: rest.value }) }] }).done;
      if (ok) { toast('Split'); reload(ok.place); }
    }
  }
  async function mergePlaces() {
    const sel = select(rows.map(p => [p.PlaceID, p.Name]), '', { size: 14, multiple: true, style: { width: '100%' } });
    const ids = await modal({ title: 'Merge places — select 2 or more (the first selected is kept)', wide: true, body: sel,
      buttons: [{ label: 'Cancel' }, { label: 'Merge', primary: true, click: () => { const v = [...sel.selectedOptions].map(o => Number(o.value)); if (v.length < 2) throw new Error('Select at least two'); return v; } }] }).done;
    if (ids) { await POST('/api/places/merge', { keep: ids[0], drop: ids.slice(1) }); toast('Merged'); reload(ids[0]); }
  }
}

// ================================================================ sources
export async function renderSources(root) {
  const detail = h('div.page-pad');
  let rows = await GET('/api/sources');
  const table = dataTable([
    { key: 'Name', label: 'Source' }, { key: 'citations', label: 'Cit.', width: '40px' }, { key: 'uses', label: 'Uses', width: '40px' },
  ], rows, { onclick: s => show(s.SourceID), selectable: true });
  put(root, split([h('div.toolbar', h('b', 'Sources'), h('span.grow'),
    h('button.btn.sm', { onclick: async () => { const id = await editSource(null); if (id) reload(id); } }, '+ Add'),
    h('button.btn.sm', { onclick: () => templateManager() }, 'Templates…'),
    h('button.btn.sm', { onclick: () => location.hash = '#/addresses/repositories' }, 'Repositories…')),
  h('div', { style: { padding: '8px', flex: 1, minHeight: 0, display: 'flex' } }, table)], detail));
  async function reload(sel) { rows = await GET('/api/sources'); table.setRows(rows); if (sel) show(sel); }
  async function show(id) {
    const s = await GET(`/api/source/${id}`);
    const media = h('div'), tags = h('div');
    fill(detail, 
      h('div.row', h('h2', { style: { margin: 0 } }, s.Name), h('div.right.row',
        h('button.btn.primary', { onclick: async () => { if (await editSource(id)) reload(id); } }, 'Edit source'),
        h('button.btn.danger', { onclick: async () => { if (await confirmBox(`Delete this source and its ${s.citations.length} citations?`, { danger: true })) { await DEL(`/api/source/${id}`); clear(detail); reload(); } } }, 'Delete'))),
      h('h4', 'Footnote'), h('div.sentence', { html: s.footnote || '<span class="muted">(empty)</span>' }),
      h('h4', 'Bibliography'), h('div.sentence', { html: s.bibliography || '<span class="muted">(empty)</span>' }),
      s.ActualText ? [h('h4', 'Source text'), h('div.small', s.ActualText)] : null,
      h('h4', 'Repositories'), h('div.list', s.repositories.length ? s.repositories.map(r => h('div', r.Name, r.Details ? h('span.muted', ' call no. ' + r.Details) : '',
        h('button.btn.sm.right', { onclick: async () => { await POST('/api/addressLink', { delete: r.LinkID }); show(id); } }, 'Unlink'))) : h('div.muted', 'None')),
      h('button.btn.sm', { style: { marginTop: '6px' }, onclick: async () => {
        const repos = await GET('/api/list/addresses?AddressType=1');
        const sel = select(repos.map(r => [r.AddressID, r.Name]), '', { size: 10, style: { width: '100%' } });
        const caln = h('input', { placeholder: 'Call number', style: { width: '100%' } });
        const rid = await modal({ title: 'Link repository', body: h('div.col', sel, caln, h('button.btn.sm', { onclick: async () => { const nid = await editAddress({ AddressType: 1 }); if (nid) { put(sel, h('option', { value: nid, selected: true }, 'New repository')); } } }, '+ New repository')),
          buttons: [{ label: 'Cancel' }, { label: 'Link', primary: true, click: () => Number(sel.value) }] }).done;
        if (rid) { await POST('/api/addressLink', { ownerType: 3, ownerId: id, addressId: rid, details: caln.value }); show(id); }
      } }, '+ Link repository'),
      h('h4', `Citations (${s.citations.length})`),
      h('div.list', s.citations.map(c => h('div', { style: { alignItems: 'flex-start', flexDirection: 'column' } }, h('div', { html: c.footnote }),
        h('div.small.muted', 'Used by: ', c.uses.length ? c.uses.map((u, i) => [i ? '; ' : '', u.label]) : 'nothing (unused)'),
        h('div.row', h('button.btn.sm', { onclick: async () => { const { editCitation } = await import('./edit.js'); if (await editCitation(c.CitationID, c.uses[0]?.linkId, c.uses[0]?.quality)) show(id); } }, 'Edit'),
          h('button.btn.sm.danger', { onclick: async () => { if (await confirmBox('Delete this citation everywhere?', { danger: true })) { await DEL(`/api/citation/${c.CitationID}`); show(id); } } }, 'Delete'))))),
      h('h4', 'Media'), media, h('h4', 'WebTags'), tags);
    mediaPanel(media, 3, id); webtagsPanel(tags, 3, id);
  }
}

export async function editSource(id) {
  const templates = await GET('/api/list/templates');
  let s = id ? await GET(`/api/source/${id}`) : { Name: '', TemplateID: 0, Fields: {}, RefNumber: '', ActualText: '', Comments: '', IsPrivate: 0 };
  if (!id) {
    const q = h('input', { type: 'search', placeholder: 'Search templates (e.g. census, book, website)', style: { width: '100%' }, autofocus: true });
    const all = [[0, 'Free-form (type the footnote yourself)'], ...templates.map(t => [t.TemplateID, `${t.Name} — ${t.Category || ''}`])];
    const sel = select(all, 0, { size: 14, style: { width: '100%' } });
    const desc = h('div.small.muted');
    sel.onchange = () => { const t = templates.find(t => t.TemplateID === Number(sel.value)); desc.textContent = t ? t.Description : 'Free-form footnote, short footnote and bibliography.'; };
    q.oninput = () => { clear(sel); for (const [v, l] of all.filter(([, l]) => l.toLowerCase().includes(q.value.toLowerCase()))) put(sel, h('option', { value: v }, l)); sel.selectedIndex = 0; sel.onchange(); };
    const tid = await modal({ title: 'New source — choose a source type', wide: true, body: h('div.col.no-enter', q, sel, desc,
      h('div.hint', 'Tip: import RootsMagic’s full template library from Lists › Source templates › Import.')),
    buttons: [{ label: 'Cancel' }, { label: 'Next', primary: true, click: () => sel.value === '' ? false : 'T' + sel.value }] }).done;
    if (!tid) return null;
    s.TemplateID = Number(tid.slice(1));
  }
  const defs = s.fieldDefs || (await GET(`/api/template/${s.TemplateID}/fields`).catch(() => []));
  const srcDefs = defs.filter(f => !f.citation);
  const name = h('input', { value: s.Name, style: { width: '100%' }, placeholder: 'Short name used in lists' });
  const inputs = {};
  const flds = srcDefs.flatMap(f => {
    const big = ['Footnote', 'ShortFootnote', 'Bibliography'].includes(f.name);
    inputs[f.name] = big ? h('textarea', { value: s.Fields[f.name] || '', style: { minHeight: '50px' } }) : h('input', { value: s.Fields[f.name] || '', style: { width: '100%' }, placeholder: f.hint });
    return field(f.display || f.name, inputs[f.name], { hint: f.type === 'Name' ? 'Put surnames in slashes: John /Smith/' : f.longHint });
  });
  const ref = h('input', { value: s.RefNumber || '' }), text = h('textarea', { value: s.ActualText || '' }), comm = h('textarea', { value: s.Comments || '' });
  const priv = checkbox('Private', s.IsPrivate);
  const prev = h('div.sentence.small');
  const preview = debounce(async () => {
    const r = await POST('/api/source/preview', { TemplateID: s.TemplateID, Fields: Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])) });
    prev.innerHTML = `<b>Footnote:</b> ${r.Footnote}<br><b>Short:</b> ${r.ShortFootnote}<br><b>Bibliography:</b> ${r.Bibliography}`;
    if (!name.value && !id) name.placeholder = r.ShortFootnote.replace(/<[^>]+>/g, '').slice(0, 80) || 'Short name used in lists';
  }, 250);
  Object.values(inputs).forEach(i => i.addEventListener('input', preview));
  preview();
  const tname = s.TemplateID ? (templates.find(t => t.TemplateID === s.TemplateID)?.Name || 'template') : 'Free-form';
  const r = await modal({ title: (id ? 'Edit source' : 'New source') + ' — ' + tname, wide: true,
    body: h('div.col', h('div.form', ...field('Source name', name), ...flds, ...field('Reference #', ref), ...field('Source text', text), ...field('Comments', comm), ...field('', priv)),
      h('h4', 'Preview'), prev),
    buttons: [{ label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST('/api/source', {
      SourceID: id || undefined, Name: name.value || name.placeholder, TemplateID: s.TemplateID, RefNumber: ref.value, ActualText: text.value, Comments: comm.value,
      IsPrivate: priv.input.checked ? 1 : 0, Fields: Object.assign({}, s.Fields, Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value]))) }) }] }).done;
  return r ? r.id : null;
}

// ================================================================ media
export async function renderMedia(root) {
  let items = await GET('/api/media?tags=1');
  const grid = h('div.thumbs', { style: { padding: '14px' } });
  const q = h('input', { type: 'search', placeholder: 'Filter by caption, file, tag', oninput: draw });
  const missingOnly = checkbox('Missing files only', false, { onchange: draw });
  function draw() {
    clear(grid);
    const t = q.value.toLowerCase();
    for (const m of items.filter(m => (!t || [m.Caption, m.MediaFile, ...m.tags.map(x => x.label)].join(' ').toLowerCase().includes(t)) && (!missingOnly.input.checked || !m.exists))) {
      put(grid, h('div.thumb', { onclick: async () => { if (await editMedia(m.MediaID)) reload(); }, title: m.MediaPath + m.MediaFile },
        m.MediaType === 1 ? h('img', { src: `/api/media/${m.MediaID}/file`, loading: 'lazy' }) : h('div.doc', m.MediaType === 3 ? '🔊' : m.MediaType === 4 ? '🎞' : '📄'),
        h('div.cap', m.exists ? '' : '⚠ ', m.Caption || m.MediaFile), h('div.cap.muted', `${m.uses} tag${m.uses === 1 ? '' : 's'} ${m.dateText || ''}`)));
    }
    if (!grid.children.length) put(grid, h('div.empty', 'No media'));
  }
  async function reload() { items = await GET('/api/media?tags=1'); draw(); }
  put(root, h('div.toolbar', h('b', 'Media'), q, missingOnly, h('span.grow'),
    h('label.btn.sm', 'Upload…', h('input.hidden', { type: 'file', multiple: true, onchange: async e => {
      for (const f of e.target.files) await POST('/api/media', { content: await readFileAs(f, 'url'), filename: f.name });
      reload(); toast('Uploaded');
    } })),
    h('button.btn.sm', { onclick: async () => { const p = await chooseFile({ title: 'Link a local file' }); if (p) { await POST('/api/media', { path: p }); reload(); } } }, 'Link local file…'),
    h('button.btn.sm', { onclick: () => import('./tools.js').then(m => m.run('fixMedia')) }, 'Fix broken links…'),
    h('button.btn.sm', { onclick: () => location.hash = '#/publish' }, 'Scrapbook report')), grid);
  draw();
}

export async function editMedia(mid, linkId) {
  const m = await GET(`/api/media/${mid}`);
  const cap = h('input', { value: m.Caption || '', style: { width: '100%' } }), ref = h('input', { value: m.RefNumber || '' });
  const date = dateInput(m.dateText || ''), desc = h('textarea', { value: m.Description || '' });
  const typ = select(Object.entries(S.meta.mediaTypes), m.MediaType);
  const path = h('input', { value: (m.MediaPath || '') + (m.MediaFile || ''), style: { width: '100%' } });
  const prev = m.MediaType === 1 ? h('img', { src: `/api/media/${mid}/file`, style: { maxWidth: '100%', maxHeight: '320px', display: 'block', margin: '0 auto 10px' } })
    : h('p', h('a', { href: m.URL ? safeUrl(m.URL) : `/api/media/${mid}/file`, target: '_blank' }, 'Open file'));
  const tags = h('div.list', m.tags.length ? m.tags.map(t => h('div', t.isPrimary ? '★ ' : '', t.label || `owner ${t.ownerType}:${t.ownerId}`,
    t.ownerType === 0 ? h('button.btn.sm', { onclick: () => goPerson(t.ownerId) }, 'Go') : '',
    t.ownerType === 0 ? h('button.btn.sm', { onclick: async () => { await POST('/api/mediaLink', { LinkID: t.linkId, IsPrimary: 1 }); toast('Primary photo set'); } }, 'Make primary') : '',
    h('button.btn.sm.right', { onclick: async e => { await POST('/api/mediaLink', { delete: t.linkId }); e.target.closest('div').remove(); } }, 'Untag'))) : h('div.muted', 'Not tagged to anything'));
  const r = await modal({ title: 'Media item', wide: true, body: h('div.col', prev, h('div.form', ...field('Caption', cap), ...field('Type', typ), ...field('File', path, { hint: m.exists ? '' : '⚠ File not found at this path' }),
    ...field('Date', date), ...field('Ref #', ref), ...field('Description', desc)), h('h4', 'Tagged to'), tags,
    h('button.btn.sm', { onclick: async () => { const { choosePerson } = await import('./ui.js'); const p = await choosePerson({ title: 'Tag to person' }); if (p) { await POST('/api/mediaLink', { mediaId: mid, ownerType: 0, ownerId: p }); toast('Tagged'); } } }, '+ Tag to person')),
  buttons: [{ label: 'Delete media item', danger: true, click: async () => { if (await confirmBox('Remove this item from the file (the file on disk is not deleted)?', { danger: true })) { await DEL(`/api/media/${mid}`); return true; } return false; } },
    { label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST('/api/media', { MediaID: mid, Caption: cap.value, RefNumber: ref.value, Date: date.value, Description: desc.value, MediaType: Number(typ.value), path: path.value }) }] }).done;
  return r;
}

// ================================================================ tasks
export async function renderTasks(root, [typeArg]) {
  const type = sessionStorage.getItem('dz_tasktype') || (typeArg ?? 'all');
  const status = sessionStorage.getItem('dz_taskstatus') || 'open';
  const typeSel = select([['all', 'All task types'], ...Object.entries(S.meta.taskType)], typeArg ?? type, { onchange: e => { sessionStorage.setItem('dz_tasktype', e.target.value); load(); } });
  const statSel = select([['all', 'Any status'], ['open', 'Open / in progress'], ['done', 'Completed']], status, { onchange: e => { sessionStorage.setItem('dz_taskstatus', e.target.value); load(); } });
  const wrap = h('div', { style: { padding: '10px', display: 'flex', flexDirection: 'column', height: 'calc(100% - 44px)' } });
  put(root, h('div.toolbar', h('b', 'Tasks'), typeSel, statSel, h('span.grow'), h('button.btn.sm.primary', { onclick: async () => { if (await editTask({ TaskType: typeSel.value === 'all' ? 0 : Number(typeSel.value) })) load(); } }, '+ New task'),
    h('button.btn.sm', { onclick: () => location.hash = '#/publish' }, 'Print task list')), wrap);
  async function load() {
    const rows = await GET(`/api/tasks?type=${typeSel.value}&status=${statSel.value}`);
    fill(wrap, dataTable([
      { key: 'Status', label: '', width: '24px', render: t => t.Status === 2 ? '☑' : '☐' },
      { key: 'Name', label: 'Task' }, { key: 'TaskType', label: 'Type', render: t => S.meta.taskType[t.TaskType] },
      { key: 'Priority', label: 'Priority', render: t => S.meta.priority[t.Priority] }, { key: 'date1Text', label: 'Start' },
      { key: 'links', label: 'For', render: t => t.links.map(l => l.label).join('; '), text: t => t.links.map(l => l.label).join(' ') },
    ], rows, { onclick: async t => { if (await editTask(t)) load(); } }));
  }
  load();
}

export async function editTask(t) {
  const name = h('input', { value: t.Name || '', style: { width: '100%' }, autofocus: true });
  const typ = select(Object.entries(S.meta.taskType), t.TaskType || 0), stat = select(Object.entries(S.meta.taskStatus), t.Status || 0);
  const pri = select(Object.entries(S.meta.priority), t.Priority || 0);
  const d1 = dateInput(t.date1Text || ''), d2 = dateInput(t.date2Text || ''), d3 = dateInput(t.date3Text || '');
  const ref = h('input', { value: t.RefNumber || '' }), file = h('input', { value: t.Filename || '', style: { width: '100%' } });
  const det = h('textarea', { value: t.Details || '' }), res = h('textarea', { value: t.Results || '' });
  const links = h('div.list', (t.links || []).map(l => h('div', l.label, h('button.btn.sm.right', { onclick: async e => { await POST('/api/taskLink', { delete: l.linkId }); e.target.closest('div').remove(); } }, 'Unlink'))));
  const r = await modal({ title: t.TaskID ? 'Edit task' : 'New task', wide: true, body: h('div.col', h('div.form',
    ...field('Task / goal', name), ...field('Type', typ), ...field('Status', stat), ...field('Priority', pri),
    ...field('Start date', d1), ...field('Last edited', d2), ...field('Completed', d3), ...field('Ref #', ref), ...field('File / folder', file),
    ...field('Details', det), ...field('Results', res)), t.TaskID ? [h('h4', 'Linked to'), links] : null),
  buttons: [t.TaskID ? { label: 'Delete', danger: true, click: async () => { if (await confirmBox('Delete this task?', { danger: true })) { await DEL(`/api/task/${t.TaskID}`); return true; } return false; } } : null,
    { label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST('/api/task', { TaskID: t.TaskID, Name: name.value, TaskType: Number(typ.value), Status: Number(stat.value), Priority: Number(pri.value),
      Date1: d1.value, Date2: d2.value, Date3: d3.value, RefNumber: ref.value, Filename: file.value, Details: det.value, Results: res.value,
      ownerType: t.TaskID ? undefined : t.ownerType, ownerId: t.TaskID ? undefined : t.ownerId }) }].filter(Boolean) }).done;
  return r;
}

// ================================================================ addresses & repositories
export async function renderAddresses(root, [kind]) {
  const type = kind === 'repositories' ? 1 : 0;
  const wrap = h('div', { style: { padding: '10px', display: 'flex', flexDirection: 'column', height: 'calc(100% - 44px)' } });
  put(root, h('div.toolbar', h('div.tabs', h('button' + (type === 0 ? '.active' : ''), { onclick: () => location.hash = '#/addresses' }, 'Addresses'),
    h('button' + (type === 1 ? '.active' : ''), { onclick: () => location.hash = '#/addresses/repositories' }, 'Repositories')), h('span.grow'),
  h('button.btn.sm.primary', { onclick: async () => { if (await editAddress({ AddressType: type })) load(); } }, type ? '+ New repository' : '+ New address'),
  h('button.btn.sm', { onclick: () => location.hash = '#/publish' }, 'Print list / labels')), wrap);
  async function load() {
    const rows = await GET(`/api/list/addresses?AddressType=${type}`);
    fill(wrap, dataTable([{ key: 'Name', label: 'Name' }, { key: 'City', label: 'City' }, { key: 'State', label: 'State' }, { key: 'Country', label: 'Country' },
      { key: 'Phone1', label: 'Phone' }, { key: 'Email', label: 'Email' }, { key: 'uses', label: 'Uses' }], rows, { onclick: async a => { if (await editAddress(a)) load(); } }));
  }
  load();
}

export async function editAddress(a) {
  const f = {};
  const keys = [['Name', 'Name'], ['Street1', 'Street'], ['Street2', 'Street 2'], ['City', 'City'], ['State', 'State / province'], ['Zip', 'Postal code'], ['Country', 'Country'],
    ['Phone1', 'Phone'], ['Phone2', 'Phone 2'], ['Fax', 'Fax'], ['Email', 'Email'], ['URL', 'Website']];
  for (const [k] of keys) f[k] = h('input', { value: a[k] || '', style: { width: '100%' } });
  const note = h('textarea', { value: a.Note || '' });
  const r = await modal({ title: (a.AddressID ? 'Edit ' : 'New ') + (a.AddressType ? 'repository' : 'address'), wide: true,
    body: h('div.form', ...keys.flatMap(([k, l]) => field(l, f[k])), ...field('Note', note)),
    buttons: [a.AddressID ? { label: 'Delete', danger: true, click: async () => { if (await confirmBox('Delete?', { danger: true })) { await DEL(`/api/list/addresses/${a.AddressID}`); return { deleted: true }; } return false; } } : null,
      { label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST('/api/list/addresses', Object.assign({ AddressID: a.AddressID, AddressType: a.AddressType || 0, Note: note.value },
        Object.fromEntries(Object.entries(f).map(([k, i]) => [k, i.value])))) }].filter(Boolean) }).done;
  return r ? r.id ?? true : null;
}

// ================================================================ managers
export async function factTypeManager() {
  const body = h('div', { style: { height: '64vh', display: 'flex', flexDirection: 'column' } });
  const m = modal({ title: 'Fact types', xwide: true, body, onclose: async () => { const { refreshFile } = await import('./app.js'); refreshFile(); } });
  async function load() {
    const rows = await GET('/api/list/factTypes');
    fill(body, h('div.row', { style: { marginBottom: '8px' } }, h('button.btn.sm.primary', { onclick: () => edit({ OwnerType: 0, UseDate: 1, UsePlace: 1, UseValue: 0 }) }, '+ New fact type')),
      dataTable([{ key: 'Name', label: 'Fact type' }, { key: 'OwnerType', label: 'For', render: f => f.OwnerType ? 'Family' : 'Person' },
        { key: 'Abbrev', label: 'Abbreviation' }, { key: 'GedcomTag', label: 'GEDCOM' }, { key: 'uses', label: 'Uses' },
        { key: 'FactTypeID', label: 'ID' }], rows, { onclick: edit }));
  }
  async function edit(f) {
    const name = h('input', { value: f.Name || '', style: { width: '100%' } }), abbr = h('input', { value: f.Abbrev || '' }), tag = h('input', { value: f.GedcomTag || 'EVEN' });
    const own = select([[0, 'Individual'], [1, 'Family']], f.OwnerType || 0);
    const ud = checkbox('Date', f.UseDate), up = checkbox('Place', f.UsePlace), uv = checkbox('Description', f.UseValue);
    const sent = h('textarea', { value: f.Sentence || '', style: { minHeight: '70px' } });
    const roles = h('div');
    const r = await modal({ title: f.FactTypeID ? `Edit fact type: ${f.Name}` : 'New fact type', wide: true, body: h('div.col', h('div.form', ...field('Name', name), ...field('Abbreviation', abbr),
      ...field('GEDCOM tag', tag, { hint: 'Use EVEN for custom facts' }), ...field('Fact is for', own), ...field('Uses', h('div.row', ud, up, uv)),
      ...field('Sentence template', sent, { hint: '[person]/[couple], [Date], [Place], [PlaceDetails], [Desc], [person:Age], [person:HisHer]…  <text [Field]> is dropped when Field is empty.' })),
    f.FactTypeID ? [h('h4', 'Roles (for shared facts)'), roles] : null),
    buttons: [f.FactTypeID && !f.uses ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/list/factTypes/${f.FactTypeID}`); return true; } } : null,
      { label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST('/api/list/factTypes', { FactTypeID: f.FactTypeID, Name: name.value, Abbrev: abbr.value || name.value, GedcomTag: tag.value,
        OwnerType: Number(own.value), UseDate: ud.input.checked ? 1 : 0, UsePlace: up.input.checked ? 1 : 0, UseValue: uv.input.checked ? 1 : 0, Sentence: sent.value }) }].filter(Boolean) });
    if (f.FactTypeID) rolePanel(roles, f.FactTypeID);
    if (await r.done) load();
  }
  load();
  return m.done;
}

function rolePanel(el, eventType) {
  async function load() {
    const roles = await GET(`/api/list/roles?EventType=${eventType}`);
    fill(el, h('div.list', roles.length ? roles.map(r => h('div', { style: { cursor: 'pointer' }, onclick: () => edit(r) }, h('b', r.RoleName), h('span.muted.small', r.Sentence))) : h('div.muted', 'Only "Witness"')),
      h('button.btn.sm', { style: { marginTop: '6px' }, onclick: () => edit({ RoleType: 1, EventType: eventType }) }, '+ Add role'));
  }
  async function edit(r) {
    const name = h('input', { value: r.RoleName || '' }), typ = select([[0, 'Principal'], [1, 'Witness']], r.RoleType ?? 1);
    const sent = h('textarea', { value: r.Sentence || '[ThisPerson] witnessed the event of [person]< [Date]>< [Place]>.' });
    const ok = await modal({ title: 'Role', wide: true, body: h('div.form', ...field('Role name', name), ...field('Role type', typ), ...field('Sentence', sent, { hint: '[ThisPerson] = the witness; [person] = the principal' })),
      buttons: [r.RoleID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/list/roles/${r.RoleID}`); return true; } } : null, { label: 'Cancel' },
        { label: 'Save', primary: true, click: () => POST('/api/list/roles', { RoleID: r.RoleID, RoleName: name.value, RoleType: Number(typ.value), EventType: eventType, Sentence: sent.value }) }].filter(Boolean) }).done;
    if (ok) load();
  }
  load();
}
export async function roleManager(eventType) {
  const el = h('div');
  rolePanel(el, eventType);
  return modal({ title: 'Roles', wide: true, body: el }).done;
}

export async function fanTypeManager() {
  const body = h('div');
  const m = modal({ title: 'Association types', wide: true, body });
  async function load() {
    const rows = await GET('/api/list/fanTypes');
    fill(body, h('button.btn.sm.primary', { onclick: () => edit({}) }, '+ New type'),
      h('div.list', { style: { marginTop: '8px' } }, rows.map(t => h('div', { style: { cursor: 'pointer' }, onclick: () => edit(t) }, h('b', t.Name), h('span.muted', `${t.Role1} ↔ ${t.Role2}`)))));
  }
  async function edit(t) {
    const n = h('input', { value: t.Name || '' }), r1 = h('input', { value: t.Role1 || '' }), r2 = h('input', { value: t.Role2 || '' });
    const s1 = h('textarea', { value: t.Sentence1 || '' }), s2 = h('textarea', { value: t.Sentence2 || '' });
    const ok = await modal({ title: 'Association type', wide: true, body: h('div.form', ...field('Name', n), ...field('Role 1', r1), ...field('Role 2', r2), ...field('Sentence (role 1)', s1), ...field('Sentence (role 2)', s2)),
      buttons: [t.FANTypeID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/list/fanTypes/${t.FANTypeID}`); return true; } } : null, { label: 'Cancel' },
        { label: 'Save', primary: true, click: () => POST('/api/list/fanTypes', { FANTypeID: t.FANTypeID, Name: n.value, Role1: r1.value, Role2: r2.value || r1.value, Sentence1: s1.value, Sentence2: s2.value }) }].filter(Boolean) }).done;
    if (ok) load();
  }
  load();
  return m.done;
}

export async function templateManager() {
  const body = h('div', { style: { height: '64vh', display: 'flex', flexDirection: 'column' } });
  const m = modal({ title: 'Source templates', xwide: true, body });
  async function load() {
    const rows = await GET('/api/list/templates');
    fill(body, h('div.row', { style: { marginBottom: '8px' } },
      h('button.btn.sm.primary', { onclick: () => edit({ Name: 'New template' }) }, '+ New template'),
      h('button.btn.sm', { onclick: async () => {
        const p = await chooseFile({ title: 'Choose rootsmagic.st (RootsMagic.app/Contents/MacOS/rootsmagic.st on Mac)', ext: '.st,.xml' });
        if (p) { const r = await POST('/api/templates/importLibrary', { path: p }); toast(`Imported ${r.added} templates`); load(); }
      } }, 'Import RootsMagic template library…'),
      h('span.muted.small', `${rows.length} templates`)),
    dataTable([{ key: 'Name', label: 'Template' }, { key: 'Category', label: 'Category' }, { key: 'uses', label: 'Uses' }, { key: 'Favorite', label: '★', render: t => t.Favorite ? '★' : '' }],
      rows, { onclick: edit }));
  }
  async function edit(t) {
    const fields = t.TemplateID ? await GET(`/api/template/${t.TemplateID}/fields`) : [];
    const name = h('input', { value: t.Name || '', style: { width: '100%' } }), cat = h('input', { value: t.Category || '', style: { width: '100%' } });
    const desc = h('input', { value: t.Description || '', style: { width: '100%' } }), fav = checkbox('Favorite', t.Favorite);
    const fn = h('textarea', { value: t.Footnote || '' }), sfn = h('textarea', { value: t.ShortFootnote || '' }), bib = h('textarea', { value: t.Bibliography || '' });
    const fl = h('div');
    let defs = fields.map(f => ({ ...f }));
    function drawFields() {
      fill(fl, h('table.dt', h('thead', h('tr', ['Field name', 'Display', 'Type', 'Hint', 'Citation?', ''].map(x => h('th', x)))),
        h('tbody', defs.map((f, i) => h('tr', h('td', h('input', { value: f.name, oninput: e => (f.name = e.target.value.replace(/\W/g, '')) })),
          h('td', h('input', { value: f.display, oninput: e => (f.display = e.target.value) })),
          h('td', select(['Text', 'Name', 'Date', 'Place'], f.type, { onchange: e => (f.type = e.target.value) })),
          h('td', h('input', { value: f.hint, oninput: e => (f.hint = e.target.value) })),
          h('td', h('input', { type: 'checkbox', checked: f.citation, onchange: e => (f.citation = e.target.checked) })),
          h('td', h('button.btn.sm', { onclick: () => { defs.splice(i, 1); drawFields(); } }, '✕')))))),
      h('button.btn.sm', { onclick: () => { defs.push({ name: 'Field' + (defs.length + 1), display: '', type: 'Text', hint: '', citation: false }); drawFields(); } }, '+ Field'));
    }
    drawFields();
    const ok = await modal({ title: 'Source template', xwide: true, body: h('div.col', h('div.form', ...field('Name', name), ...field('Category', cat), ...field('Description', desc), ...field('', fav),
      ...field('Footnote', fn), ...field('Short footnote', sfn), ...field('Bibliography', bib)),
    h('div.hint', 'Template language: [Field], [Field:Surname], [Field:Abbrev], <optional text [Field]>, <?[Field]|if present|otherwise>, <i>italic</i>.'),
    h('h4', 'Fields'), fl),
    buttons: [t.TemplateID && !t.uses ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/list/templates/${t.TemplateID}`); return true; } } : null,
      { label: 'Copy as new', click: async () => { const r = await POST('/api/list/templates', { Name: name.value + ' (copy)', Category: cat.value, Description: desc.value, Footnote: fn.value, ShortFootnote: sfn.value, Bibliography: bib.value });
        await POST(`/api/template/${r.id}/fields`, { fields: defs }); return true; } },
      { label: 'Cancel' }, { label: 'Save', primary: true, click: async () => {
        const r = await POST('/api/list/templates', { TemplateID: t.TemplateID, Name: name.value, Category: cat.value, Description: desc.value, Favorite: fav.input.checked ? 1 : 0, Footnote: fn.value, ShortFootnote: sfn.value, Bibliography: bib.value });
        await POST(`/api/template/${r.id}/fields`, { fields: defs });
      } }].filter(Boolean) }).done;
    if (ok) load();
  }
  load();
  return m.done;
}

export async function groupManager() {
  const body = h('div', { style: { minHeight: '50vh' } });
  const m = modal({ title: 'Groups', xwide: true, body });
  async function load(sel) {
    const groups = await GET('/api/groups');
    const right = h('div', { style: { flex: 1, minWidth: 0 } });
    fill(body, h('div.row', { style: { alignItems: 'flex-start', gap: '16px' } },
      h('div', { style: { width: '280px' } }, h('button.btn.sm.primary', { onclick: async () => { const n = await promptBox('New group', 'Name'); if (n) { const r = await POST('/api/group', { Name: n }); load(r.id); } } }, '+ New group'),
        h('div.list', { style: { marginTop: '8px' } }, groups.map(g => h('div', { style: { cursor: 'pointer', background: g.GroupID === sel ? 'var(--sel)' : '' }, onclick: () => load(g.GroupID) }, h('b', g.Name), h('span.muted.right', g.count))))),
      right));
    if (sel) showGroup(right, groups.find(g => g.GroupID === sel));
  }
  async function showGroup(el, g) {
    const members = await GET(`/api/group/${g.GroupID}`);
    put(el, h('div.row', h('h3', { style: { margin: 0 } }, g.Name), h('div.right.row',
      h('button.btn.sm', { onclick: async () => { const n = await promptBox('Rename group', 'Name', g.Name); if (n) { await POST('/api/group', { GroupID: g.GroupID, Name: n }); load(g.GroupID); } } }, 'Rename'),
      h('button.btn.sm', { onclick: async () => { const { choosePerson } = await import('./ui.js'); const p = await choosePerson({ title: 'Add person to group' }); if (p) { await POST('/api/group', { GroupID: g.GroupID, Name: g.Name, add: [p] }); load(g.GroupID); } } }, '+ Person'),
      h('button.btn.sm', { onclick: async () => { const crit = await import('./search.js').then(x => x.criteriaDialog('Mark group members by criteria')); if (crit) { await POST('/api/group', { GroupID: g.GroupID, Name: g.Name, criteria: crit.criteria, match: crit.match, mode: crit.mode }); load(g.GroupID); } } }, 'Mark by criteria…'),
      h('button.btn.sm', { onclick: () => location.hash = '#/publish' }, 'Print'),
      h('button.btn.sm.danger', { onclick: async () => { if (await confirmBox(`Delete group ${g.Name}? (people are not deleted)`)) { await DEL(`/api/group/${g.GroupID}`); load(); } } }, 'Delete'))),
    dataTable([{ key: 'name', label: 'Name' }, { key: 'birthYear', label: 'Born' }, { key: 'deathYear', label: 'Died' },
      { key: 'x', label: '', render: p => h('button.btn.sm', { onclick: async e => { e.stopPropagation(); await POST('/api/group', { GroupID: g.GroupID, Name: g.Name, remove: [p.id] }); load(g.GroupID); } }, 'Remove') }],
    members, { onclick: p => goPerson(p.id), height: '50vh' }));
  }
  load();
  return m.done;
}
