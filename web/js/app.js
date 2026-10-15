// Application shell: state, router, rail navigation, history, shortcuts, command palette.
import { GET, POST, h, clear, icon, modal, toast, fail, debounce, yrs, put } from './ui.js';

export const S = {
  file: null, meta: null, settings: null,
  person: Number(localStorage.getItem('dz_person')) || 0,
  hist: [], histPos: -1,
  view: localStorage.getItem('dz_view') || 'pedigree',
};
export const bus = new EventTarget();
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));
export const on = (name, fn) => bus.addEventListener(name, e => fn(e.detail));

const PAGES = [
  ['home', 'Home', 'home', () => import('./home.js')],
  ['people', 'People', 'people', () => import('./people.js')],
  ['places', 'Places', 'place', () => import('./lists.js').then(m => ({ render: m.renderPlaces }))],
  ['sources', 'Sources', 'source', () => import('./lists.js').then(m => ({ render: m.renderSources }))],
  ['media', 'Media', 'media', () => import('./lists.js').then(m => ({ render: m.renderMedia }))],
  ['tasks', 'Tasks', 'task', () => import('./lists.js').then(m => ({ render: m.renderTasks }))],
  ['addresses', 'Addresses', 'address', () => import('./lists.js').then(m => ({ render: m.renderAddresses }))],
  ['search', 'Search', 'search', () => import('./search.js')],
  ['publish', 'Publish', 'publish', () => import('./publish.js')],
  ['tools', 'Tools', 'tools', () => import('./tools.js')],
  ['settings', 'Settings', 'settings', () => import('./settings.js')],
];

// ---------------------------------------------------------------- person navigation
export function setPerson(id, { push = true } = {}) {
  id = Number(id);
  if (!id) return;
  if (push && S.person !== id) {
    S.hist = S.hist.slice(0, S.histPos + 1);
    S.hist.push(id);
    if (S.hist.length > 200) S.hist.shift();
    S.histPos = S.hist.length - 1;
  }
  S.person = id;
  localStorage.setItem('dz_person', id);
  emit('person', id);
}
export function goPerson(id, view) {
  if (view) { S.view = view; localStorage.setItem('dz_view', view); }
  setPerson(id);
  if (!location.hash.startsWith('#/people')) location.hash = '#/people';
}
function back() { if (S.histPos > 0) { S.histPos--; setPerson(S.hist[S.histPos], { push: false }); } }
function fwd() { if (S.histPos < S.hist.length - 1) { S.histPos++; setPerson(S.hist[S.histPos], { push: false }); } }

export async function refreshFile() {
  const f = await GET('/api/files');
  S.file = f.current;
  document.getElementById('fileName').textContent = f.current ? f.current.name : 'No file open';
  if (f.current) {
    S.settings = await GET('/api/settings');
    applySettings();
  }
  S.meta = await GET('/api/meta');
  return f;
}
export function applySettings() {
  const s = S.settings || {};
  document.documentElement.dataset.theme = s.theme === 'dark' ? 'dark' : 'light';
  document.documentElement.style.setProperty('--scale', s.fontScale || 1);
}
export const factTypeName = id => (S.meta?.factTypes || []).find(f => f.FactTypeID === id)?.Name || `Fact ${id}`;

// ---------------------------------------------------------------- router
let current = null;
async function route() {
  const [, page = 'home', ...rest] = (location.hash || '#/home').slice(1).split('/');
  const def = PAGES.find(p => p[0] === page) || PAGES[0];
  document.querySelectorAll('#rail button').forEach(b => b.classList.toggle('active', b.dataset.page === def[0]));
  document.getElementById('pageTitle').textContent = def[1];
  const root = clear(document.getElementById('page'));
  if (!S.file && def[0] !== 'home' && def[0] !== 'settings') {
    location.hash = '#/home';
    return;
  }
  try {
    const mod = await def[3]();
    current = def[0];
    await mod.render(root, rest);
  } catch (e) { fail(e); put(root, h('div.empty', 'Error: ' + e.message)); }
}
export function rerender() { route(); }

function buildRail() {
  const rail = document.getElementById('rail');
  for (const [key, label, ic] of PAGES) {
    if (key === 'settings') put(rail, h('div.spacer'));
    put(rail, h('button', { 'data-page': key, title: label, onclick: () => (location.hash = '#/' + key) }, icon(ic), label));
  }
}

// ---------------------------------------------------------------- quick search
function setupQuickSearch() {
  const inp = document.getElementById('quickSearch');
  const box = document.getElementById('quickResults');
  let rows = [], sel = 0;
  const run = debounce(async () => {
    if (!S.file || !inp.value.trim()) { box.classList.add('hidden'); return; }
    const r = await GET('/api/people?limit=40&q=' + encodeURIComponent(inp.value));
    rows = r.rows; sel = 0; draw();
  }, 160);
  function draw() {
    clear(box);
    rows.forEach((r, i) => put(box, h('div.pi' + (i === sel ? '.sel' : ''), { onmousedown: () => pick(r[0]) },
      h('span', `${r[1]}, ${r[2]}`), h('span.muted.small.right', `${yrs(r[4], r[5])} [${r[0]}]`))));
    if (!rows.length) put(box, h('div.pi.muted', 'No matches'));
    box.classList.remove('hidden');
  }
  function pick(id) { box.classList.add('hidden'); inp.value = ''; goPerson(id); }
  inp.addEventListener('input', run);
  inp.addEventListener('blur', () => setTimeout(() => box.classList.add('hidden'), 150));
  inp.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { sel = Math.min(rows.length - 1, sel + 1); draw(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    else if (e.key === 'Enter' && rows[sel]) pick(rows[sel][0]);
    else if (e.key === 'Escape') { box.classList.add('hidden'); inp.blur(); }
  });
}

// ---------------------------------------------------------------- commands & shortcuts
// Mirrors RootsMagic's action list (File/Edit/Add/View/Lists/Search/Tools/Reports).
export function commands() {
  const P = () => import('./people.js');
  const E = () => import('./edit.js');
  const T = () => import('./tools.js');
  const L = () => import('./lists.js');
  const nav = h => () => (location.hash = h);
  return [
    ['File: New file', 'file', () => import('./home.js').then(m => m.newFile())],
    ['File: Open file', 'file', () => import('./home.js').then(m => m.openFile())],
    ['File: Import data (GEDCOM)', 'file', () => import('./home.js').then(m => m.importGedcom())],
    ['File: Export GEDCOM', 'file', () => import('./home.js').then(m => m.exportGedcom())],
    ['File: Backup', 'file', () => import('./home.js').then(m => m.backup())],
    ['File: Restore backup', 'file', () => import('./home.js').then(m => m.restore())],
    ['File: Copy file', 'file', () => import('./home.js').then(m => m.copyFile())],
    ['File: Rename file', 'file', () => import('./home.js').then(m => m.renameFile())],
    ['File: Properties', 'file', () => import('./home.js').then(m => m.properties())],
    ['File: Database tools', 'file', nav('#/tools/database')],
    ['File: Compare files', 'file', nav('#/tools/compare')],
    ['File: Import lists from another file', 'file', nav('#/tools/importlists')],
    ['Edit: Edit person', 'edit', () => E().then(m => m.editPerson(S.person)), 'Ctrl+Shift+E'],
    ['Edit: Delete person', 'edit', () => E().then(m => m.deletePerson(S.person))],
    ['Edit: Swap couple', 'edit', () => P().then(m => m.swapCouple())],
    ['Edit: Rearrange children', 'edit', () => P().then(m => m.rearrangeChildren())],
    ['Edit: Rearrange spouses', 'edit', () => P().then(m => m.rearrangeSpouses())],
    ['Edit: Unlink from parents', 'edit', () => P().then(m => m.unlinkParents())],
    ['Edit: Unlink from spouse', 'edit', () => P().then(m => m.unlinkSpouse())],
    ['Edit: Delete family', 'edit', () => P().then(m => m.deleteFamily())],
    ['Edit: Groups for this person', 'edit', () => E().then(m => m.editPerson(S.person, 'groups'))],
    ['Add: Add individual', 'add', () => E().then(m => m.addPerson({})), 'Ctrl+Shift+I'],
    ['Add: Add spouse', 'add', () => E().then(m => m.addPerson({ rel: 'spouse', of: S.person })), 'Ctrl+Shift+S'],
    ['Add: Add parents', 'add', () => E().then(m => m.addParents(S.person)), 'Ctrl+Shift+P'],
    ['Add: Add child', 'add', () => E().then(m => m.addPerson({ rel: 'child', of: S.person })), 'Ctrl+Shift+C'],
    ['Add: Add association', 'add', () => E().then(m => m.editPerson(S.person, 'fans'))],
    ['View: Pedigree', 'view', () => goPerson(S.person, 'pedigree'), 'Ctrl+1'],
    ['View: Family', 'view', () => goPerson(S.person, 'family'), 'Ctrl+2'],
    ['View: Descendants', 'view', () => goPerson(S.person, 'descendants'), 'Ctrl+3'],
    ['View: Person list', 'view', () => goPerson(S.person, 'list'), 'Ctrl+4'],
    ['View: Couple list', 'view', () => goPerson(S.person, 'couples'), 'Ctrl+Shift+F'],
    ['View: Association list', 'view', () => goPerson(S.person, 'fans'), 'Ctrl+5'],
    ['View: Map', 'view', () => goPerson(S.person, 'map'), 'Ctrl+6'],
    ['Lists: Places', 'list', nav('#/places')],
    ['Lists: Sources', 'list', nav('#/sources')],
    ['Lists: Media', 'list', nav('#/media')],
    ['Lists: Tasks', 'list', nav('#/tasks')],
    ['Lists: Research logs', 'list', nav('#/tasks/1')],
    ['Lists: Correspondence log', 'list', nav('#/tasks/2')],
    ['Lists: Addresses', 'list', nav('#/addresses')],
    ['Lists: Repositories', 'list', nav('#/addresses/repositories')],
    ['Lists: Fact types', 'list', () => L().then(m => m.factTypeManager())],
    ['Lists: Source templates', 'list', () => L().then(m => m.templateManager())],
    ['Lists: Association types', 'list', () => L().then(m => m.fanTypeManager())],
    ['Lists: Groups', 'list', () => L().then(m => m.groupManager())],
    ['Search: Person search', 'search', () => document.getElementById('quickSearch').focus(), 'Ctrl+S'],
    ['Search: Person search (advanced)', 'search', nav('#/search/advanced')],
    ['Search: Find everywhere', 'search', nav('#/search/everywhere')],
    ['Search: Search and replace', 'search', nav('#/search/replace')],
    ['Search: WebSearch for this person', 'search', nav('#/search/web')],
    ['Search: Go to root person', 'search', () => S.settings?.rootPersonId ? goPerson(S.settings.rootPersonId) : toast('No root person set (Tools > Set relationships)'), 'Ctrl+H'],
    ['Search: Bookmark person', 'search', () => P().then(m => m.toggleBookmark())],
    ['Search: Manage bookmarks', 'search', () => P().then(m => m.bookmarks())],
    ['Search: History', 'search', () => P().then(m => m.historyList())],
    ['Search: View immediate family', 'search', () => P().then(m => m.immediateFamily())],
    ['Search: Back', 'search', back, 'Ctrl+Shift+←'],
    ['Search: Forward', 'search', fwd, 'Ctrl+Shift+→'],
    ['Tools: Count trees', 'tool', () => T().then(m => m.run('countTrees'))],
    ['Tools: DataClean', 'tool', () => T().then(m => m.run('dataClean'))],
    ['Tools: Date calculator', 'tool', () => T().then(m => m.run('dateCalc'))],
    ['Tools: Relationship calculator', 'tool', () => T().then(m => m.run('relCalc'))],
    ['Tools: Soundex calculator', 'tool', () => T().then(m => m.run('soundex'))],
    ['Tools: Calendar', 'tool', () => T().then(m => m.run('calendar'))],
    ['Tools: Duplicate search and merge', 'tool', () => T().then(m => m.run('duplicates'))],
    ['Tools: AutoMerge', 'tool', () => T().then(m => m.run('autoMerge'))],
    ['Tools: Manual merge', 'tool', () => T().then(m => m.run('manualMerge'))],
    ['Tools: Not a duplicate list', 'tool', () => T().then(m => m.run('notDup'))],
    ['Tools: Problem list', 'tool', () => T().then(m => m.run('problems'))],
    ['Tools: Not a problem list', 'tool', () => T().then(m => m.run('notProblem'))],
    ['Tools: Mapping', 'tool', () => goPerson(S.person, 'map')],
    ['Tools: Place checker (CountyCheck)', 'tool', () => T().then(m => m.run('countyCheck'))],
    ['Tools: Color code people', 'tool', () => T().then(m => m.run('colorCode'))],
    ['Tools: Set living', 'tool', () => T().then(m => m.run('setLiving'))],
    ['Tools: Set relationships', 'tool', () => T().then(m => m.run('setRelationships'))],
    ['Tools: Gazetteer (place lookup)', 'tool', () => T().then(m => m.run('gazetteer'))],
    ['Tools: AI prompt builder', 'tool', () => T().then(m => m.run('aiPrompt'))],
    ['Tools: Fix broken media links', 'tool', () => T().then(m => m.run('fixMedia'))],
    ['Reports: Print a report or chart', 'report', nav('#/publish'), 'Ctrl+P'],
    ['Reports: Publisher (books)', 'report', nav('#/publish/books')],
    ['Reports: HTML website', 'report', nav('#/publish/website')],
    ['Tools: Settings', 'tool', nav('#/settings')],
    ['Help: Keyboard shortcuts', 'help', showShortcuts, 'F1'],
    ['Help: About Dzinde', 'help', about],
  ];
}

function showShortcuts() {
  const rows = commands().filter(c => c[3]).map(c => h('tr', h('td', h('kbd', c[3])), h('td', c[0])));
  modal({ title: 'Keyboard shortcuts', body: h('table.dt', h('tbody', rows, h('tr', h('td', h('kbd', 'F2')), h('td', 'Command palette')))) });
}
function about() {
  modal({ title: 'About Dzinde', body: h('div.col',
    h('p', h('b', 'Dzinde '), S.meta?.version || ''),
    h('p', 'A local genealogy application that reads and writes RootsMagic-compatible .rmtree database files.'),
    h('p.muted', 'Runs entirely on this computer. Data never leaves your machine except when you use web search, geocoding, or open links.')) });
}

export function palette() {
  const cmds = commands();
  let list = cmds, sel = 0;
  const inp = h('input', { placeholder: 'Type a command…', style: { width: '100%' }, autofocus: true });
  const box = h('div.palette', { style: { maxHeight: '60vh', overflow: 'auto', marginTop: '8px' } });
  function draw() {
    clear(box);
    list.forEach((c, i) => put(box, h('div.pi' + (i === sel ? '.sel' : ''), { onclick: () => runCmd(c) }, c[0], c[3] ? h('span.k', c[3]) : '')));
  }
  function runCmd(c) { m.close(); setTimeout(() => Promise.resolve(c[2]()).catch(fail), 10); }
  inp.addEventListener('input', () => {
    const words = inp.value.toLowerCase().split(/\s+/).filter(Boolean);
    list = cmds.filter(c => words.every(w => c[0].toLowerCase().includes(w)));
    sel = 0; draw();
  });
  inp.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { sel = Math.min(list.length - 1, sel + 1); draw(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    if (e.key === 'Enter' && list[sel]) { e.preventDefault(); e.stopPropagation(); runCmd(list[sel]); }
  });
  const m = modal({ title: 'Command palette', body: h('div.no-enter', inp, box) });
  draw();
}

// Native menu bar (desktop build) runs commands by their palette label.
window.dzRun = label => {
  const c = commands().find(c => c[0] === label);
  if (!c) return;
  if (!S.file && !/^(File: (New|Open|Import|Restore)|Help:|Tools: Settings)/.test(label)) return toast('Open or create a file first');
  Promise.resolve(c[2]()).catch(fail);
};

function setupShortcuts() {
  const map = {};
  for (const c of commands()) if (c[3]) map[c[3].toLowerCase()] = c[2];
  document.addEventListener('keydown', e => {
    if (document.querySelector('.backdrop') && e.key !== 'F2') return;
    const typing = /INPUT|TEXTAREA|SELECT/.test(e.target.tagName);
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'F2') { e.preventDefault(); return palette(); }
    if (e.key === 'F1') { e.preventDefault(); return showShortcuts(); }
    if (!mod) return;
    const key = e.key === 'ArrowLeft' ? '←' : e.key === 'ArrowRight' ? '→' : e.key.length === 1 ? e.key.toUpperCase() : e.key;
    const combo = ('ctrl+' + (e.shiftKey ? 'shift+' : '') + key).toLowerCase();
    const fn = map[combo];
    if (fn && (!typing || combo.includes('shift') || key === 'S' || key === 'P')) {
      e.preventDefault();
      if (!S.file) return toast('Open or create a file first');
      Promise.resolve(fn()).catch(fail);
    }
  });
}

// ---------------------------------------------------------------- boot
async function boot() {
  buildRail();
  document.getElementById('btnBack').append(icon('back'));
  document.getElementById('btnFwd').append(icon('fwd'));
  document.getElementById('btnBack').onclick = back;
  document.getElementById('btnFwd').onclick = fwd;
  document.getElementById('btnPalette').onclick = palette;
  setupQuickSearch();
  setupShortcuts();
  try { await refreshFile(); } catch (e) { fail(e); }
  window.addEventListener('hashchange', route);
  if (S.file && !location.hash) location.hash = '#/people'; // hashchange routes it; a second route() here would race it
  else route();
}
on('file', async () => { await refreshFile(); S.hist = []; S.histPos = -1; });
boot();
