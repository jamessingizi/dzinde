// Home page + File menu operations.
import { GET, POST, h, clear, modal, toast, fail, confirmBox, promptBox, chooseFile, checkbox, select, field, download, readFileAs, fmtSize, personLine, put } from './ui.js';
import { S, emit, goPerson, refreshFile } from './app.js';

export async function render(root) {
  const f = await refreshFile();
  if (!f.current) return welcome(root, f);
  const d = await GET('/api/home');
  const st = d.stats;
  const tile = (label, n, hash) => h('div.card' + (hash ? '.click' : ''), { onclick: hash ? () => (location.hash = hash) : null }, h('div.muted', label), h('div.stat', n ?? '—'));
  put(root, h('div.page-pad', { style: { maxWidth: '1180px' } },
    h('div.row', h('h2', { style: { margin: 0 } }, d.file.name), h('span.muted.small', d.file.path),
      h('div.right.row', h('button.btn', { onclick: backup }, 'Backup'), h('button.btn', { onclick: exportGedcom }, 'Export GEDCOM'),
        h('button.btn', { onclick: importGedcom }, 'Import'), h('button.btn', { onclick: openFile }, 'Open other file…'))),
    h('h2.section', 'Overview'),
    h('div.cards', tile('People', st.people, '#/people'), tile('Families', st.families, '#/people'), tile('Places', st.places, '#/places'),
      tile('Sources', st.sources, '#/sources'), tile('Media', st.media, '#/media'), tile('Open tasks', d.openTasks, '#/tasks'),
      tile('Surnames', st.surnames), tile('Years covered', st.earliestYear ? `${st.earliestYear}–${st.latestYear}` : '—')),
    h('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '6px' } },
      h('div', h('h2.section', 'On this day'),
        d.onThisDay.length ? h('div.list', d.onThisDay.map(e => h('div', h('b', e.year), ' ', e.fact, ': ', e.who, h('span.muted.small.right', e.place)))) : h('p.muted', 'No events in your file on today’s date.')),
      h('div', h('h2.section', 'Recently edited'),
        d.recent.length ? h('div.list', d.recent.map(p => h('div', { style: { cursor: 'pointer' }, onclick: () => goPerson(p.id) }, personLine(p)))) : h('p.muted', 'Nobody yet.'),
        d.root ? h('p', 'Root person: ', h('a', { href: '#', onclick: e => { e.preventDefault(); goPerson(d.root.id); } }, d.root.name)) : null)),
  ));
}

function welcome(root, f) {
  const recent = f.recent.filter(r => r.exists);
  put(root, h('div.welcome.page-pad',
    h('h1', 'Dzinde'),
    h('p.muted', 'Family-tree software for your own computer. Opens and saves RootsMagic-compatible .rmtree files.'),
    h('div.cards', { style: { margin: '20px 0' } },
      h('div.card.click', { onclick: newFile }, h('h3', 'Create a new file'), h('p.muted', 'Start a new family tree from scratch.')),
      h('div.card.click', { onclick: openFile }, h('h3', 'Open a file'), h('p.muted', 'Open a .rmtree file (including ones made by RootsMagic 8–11).')),
      h('div.card.click', { onclick: () => importGedcom(true) }, h('h3', 'Import a GEDCOM'), h('p.muted', 'Bring in data from Ancestry, FamilySearch, Legacy, Family Tree Maker, Gramps…')),
      h('div.card.click', { onclick: restore }, h('h3', 'Restore a backup'), h('p.muted', 'Restore a .rmbackup file.'))),
    recent.length ? h('div', h('h2.section', 'Recent files'), h('div.list', recent.map(r => h('div', { style: { cursor: 'pointer' }, onclick: () => open(r.path) },
      h('b', r.name), h('span.muted.small', r.path), h('span.muted.small.right', fmtSize(r.size)))))) : null,
    f.files.length ? h('div', h('h2.section', `Files in ${f.dataDir}`), h('div.list', f.files.map(r => h('div', { style: { cursor: 'pointer' }, onclick: () => open(r.path) },
      h('b', r.name), h('span.muted.small.right', new Date(r.modified * 1000).toLocaleString()))))) : null));
}

async function open(path) {
  try {
    await POST('/api/files/open', { path });
    emit('file');
    await refreshFile();
    location.hash = '#/people';
    toast('Opened ' + path.split(/[\\/]/).pop());
  } catch (e) { fail(e); }
}

export async function newFile() {
  const name = h('input', { value: 'My Family', style: { width: '100%' }, autofocus: true });
  const prep = h('input', { placeholder: 'Your name (for reports)', style: { width: '100%' } });
  const email = h('input', { placeholder: 'Email (optional)', style: { width: '100%' } });
  const res = await modal({ title: 'New file', body: h('div.form', ...field('File name', name), ...field('Researcher', prep), ...field('Email', email)),
    buttons: [{ label: 'Cancel' }, { label: 'Create', primary: true, click: () => POST('/api/files/new', { name: name.value, preparer: prep.value ? { name: prep.value, email: email.value, address: '', phone: '' } : null }) }] }).done;
  if (res) { emit('file'); await refreshFile(); location.hash = '#/people'; toast('Created ' + name.value); }
}

export async function openFile() {
  const p = await chooseFile({ title: 'Open a .rmtree file', ext: '.rmtree,.rmgc' });
  if (p) open(p);
}

export async function importGedcom(asNew = false) {
  const nameInp = h('input', { placeholder: 'New file name', style: { width: '100%' } });
  const target = select([['current', 'Into the open file'], ['new', 'Into a new file']], S.file && !asNew ? 'current' : 'new');
  if (!S.file) target.disabled = true;
  const living = checkbox('Mark people without death info as living (Set Living)', true);
  const pathLbl = h('div.mono.small');
  let path = null, upload = null;
  const pick = h('button.btn', { onclick: async () => { const p = await chooseFile({ title: 'Choose GEDCOM file', ext: '.ged,.gedcom' }); if (p) { path = p; upload = null; pathLbl.textContent = p; if (!nameInp.value) nameInp.value = p.split(/[\\/]/).pop().replace(/\.ged(com)?$/i, ''); } } }, 'Choose file on this computer…');
  const up = h('input', { type: 'file', accept: '.ged,.gedcom', onchange: async e => { const f = e.target.files[0]; if (f) { upload = await readFileAs(f); path = null; pathLbl.textContent = f.name + ' (uploaded)'; if (!nameInp.value) nameInp.value = f.name.replace(/\.ged(com)?$/i, ''); } } });
  const res = await modal({ title: 'Import GEDCOM', wide: true,
    body: h('div.form', ...field('GEDCOM file', h('div.col', h('div.row', pick, h('span.muted', 'or'), up), pathLbl)),
      ...field('Import', target), ...field('New file name', nameInp), ...field('', living)),
    buttons: [{ label: 'Cancel' }, { label: 'Import', primary: true, click: async () => {
      if (!path && !upload) throw new Error('Choose a GEDCOM file');
      const asNewFile = target.value === 'new' || !S.file;
      const body = { setLiving: living.input.checked, newFile: asNewFile ? (nameInp.value || 'Imported') : null };
      toast('Importing…');
      return path ? POST('/api/import/gedcom', { ...body, path }) : POST('/api/import/gedcomUpload', { ...body, content: upload });
    } }] }).done;
  if (res && res.stats) {
    emit('file'); await refreshFile();
    const s = res.stats;
    modal({ title: 'Import complete', body: h('div.col',
      h('p', `${s.people} people, ${s.families} families, ${s.events} facts, ${s.sources} sources, ${s.citations} citations, ${s.media} media, ${s.repositories} repositories, ${s.associations} associations.`),
      res.warnings.length ? h('details', h('summary', `${res.warnings.length} notes`), h('pre.small', res.warnings.join('\n'))) : null),
      buttons: [{ label: 'Go to People', primary: true, click: () => { location.hash = '#/people'; } }] });
  }
}

export async function exportGedcom() {
  const who = select([['all', 'Everyone'], [`ancestors:${S.person}`, 'Ancestors of current person'], [`descendants:${S.person}`, 'Descendants of current person']], 'all');
  const groups = await GET('/api/groups').catch(() => []);
  for (const g of groups) put(who, h('option', { value: 'group:' + g.GroupID }, 'Group: ' + g.Name));
  const opts = { privatizeLiving: checkbox('Privatize living people', true), excludePrivate: checkbox('Exclude private facts/notes', true),
    includeNotes: checkbox('Include notes', true), includeSources: checkbox('Include sources & citations', true),
    includeMedia: checkbox('Include media links', true), includeAssociations: checkbox('Include associations', true),
    extraTags: checkbox('Include extra tags (_UID, templates, sentences, shared facts)', true) };
  const res = await modal({ title: 'Export GEDCOM', body: h('div.col', h('div.form', ...field('People', who)), ...Object.values(opts)),
    buttons: [{ label: 'Cancel' }, { label: 'Export', primary: true, click: () => POST('/api/export/gedcom', { who: who.value, options: Object.fromEntries(Object.entries(opts).map(([k, c]) => [k, c.input.checked])) }) }] }).done;
  if (res) { download((S.file?.name || 'export').replace(/\.rmtree$/, '') + '.ged', res.content, 'text/plain'); toast(`Exported ${res.people} people`); }
}

export async function backup() {
  const media = checkbox('Include media files', false);
  const res = await modal({ title: 'Backup', body: h('div.col', h('p', 'Creates a compressed .rmbackup of this file in the Backups folder.'), media),
    buttons: [{ label: 'Cancel' }, { label: 'Backup now', primary: true, click: () => POST('/api/files/backup', { includeMedia: media.input.checked }) }] }).done;
  if (res) toast('Backup saved: ' + res.path);
}

export async function restore() {
  const p = await chooseFile({ title: 'Choose backup', ext: '.rmbackup,.zip,.rmgb' });
  if (!p) return;
  try { const r = await POST('/api/files/restore', { path: p }); emit('file'); await refreshFile(); toast('Restored to ' + r.path); location.hash = '#/people'; } catch (e) { fail(e); }
}

export async function copyFile() {
  const n = await promptBox('Copy file', 'Name for the copy', (S.file?.name || '').replace(/\.rmtree$/, '') + ' copy');
  if (n) POST('/api/files/copy', { name: n }).then(r => toast('Copied to ' + r.path), fail);
}
export async function renameFile() {
  const n = await promptBox('Rename file', 'New name', (S.file?.name || '').replace(/\.rmtree$/, ''));
  if (n) POST('/api/files/rename', { name: n }).then(async () => { emit('file'); await refreshFile(); toast('Renamed'); }, fail);
}
export async function deleteFile(path) {
  if (await confirmBox(`Permanently delete ${path}?`, { danger: true, ok: 'Delete' })) POST('/api/files/delete', { path }).then(() => { emit('file'); location.hash = '#/home'; }, fail);
}
export async function properties() {
  const p = await GET('/api/files/properties');
  modal({ title: 'File properties', body: h('table.dt', h('tbody',
    h('tr', h('td', 'File'), h('td.mono', p.file.path)), h('tr', h('td', 'Size'), h('td', fmtSize(p.file.size))),
    h('tr', h('td', 'Modified'), h('td', new Date(p.file.modified * 1000).toLocaleString())),
    Object.entries(p.stats).map(([k, v]) => h('tr', h('td', k), h('td', String(v ?? '')))))),
    buttons: [{ label: 'Delete this file…', danger: true, click: () => { deleteFile(p.file.path); } }, { label: 'Close', primary: true }] });
}
