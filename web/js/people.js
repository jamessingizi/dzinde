// People workspace: name index, navigation views, side panel, family operations.
import { GET, POST, PUT, DEL, h, clear, modal, toast, fail, confirmBox, dataTable, select, icon, sexClass, lifeOf, personLine, debounce, yrs, put, fill } from './ui.js';
import { S, on, setPerson, goPerson, factTypeName } from './app.js';

const COLORS = ['transparent', '#e53935', '#7cb342', '#1e88e5', '#d81b60', '#fdd835', '#00acc1', '#bdbdbd', '#8d2b2b', '#2e7d32',
  '#1a237e', '#6a1b9a', '#795548', '#00897b', '#757575', '#fb8c00', '#f48fb1', '#c0ca33', '#81d4fa', '#b39ddb', '#fff3c4',
  '#ffc107', '#d7b98e', '#808000', '#ffffff', '#000000', '#8e24aa', '#ff7043'];
export const colorOf = c => COLORS[c] || 'transparent';

let root, viewEl, sideEl, idx;
let cache = {};

export async function render(el) {
  root = el;
  const views = [['pedigree', 'Pedigree'], ['family', 'Family'], ['descendants', 'Descendants'], ['list', 'People'], ['couples', 'Couples'], ['fans', 'Associations'], ['map', 'Map']];
  const tabs = h('div.tabs', views.map(([k, l]) => h('button' + (S.view === k ? '.active' : ''), { onclick: () => switchView(k) }, l)));
  const genSel = select([['4', '4 gen'], ['5', '5 gen'], ['6', '6 gen']], localStorage.getItem('dz_pedgens') || '5', { onchange: e => { localStorage.setItem('dz_pedgens', e.target.value); draw(); }, title: 'Generations' });
  const dGen = select([['2', '2 gen'], ['3', '3 gen'], ['4', '4 gen'], ['5', '5 gen'], ['6', '6 gen'], ['7', '7 gen']], localStorage.getItem('dz_descgens') || '3', { onchange: e => { localStorage.setItem('dz_descgens', e.target.value); draw(); }, title: 'Generations' });
  const sideBtn = h('button.icon-btn', { title: 'Toggle side panel', onclick: () => { ws.classList.toggle('no-side'); localStorage.setItem('dz_noside', ws.classList.contains('no-side') ? '1' : ''); } }, icon('edit'));
  const tb = h('div.toolbar', tabs, h('span.grow'), genSel, dGen,
    h('button.btn', { onclick: () => import('./edit.js').then(m => m.addPerson({})) }, '+ Person'),
    h('button.btn', { onclick: () => import('./edit.js').then(m => m.editPerson(S.person)) }, 'Edit'),
    h('button.btn', { title: 'Print a report for this person', onclick: () => (location.hash = '#/publish') }, icon('print', 16)), sideBtn);
  viewEl = h('div.view');
  sideEl = h('aside.side');
  idx = indexPanel();
  const ws = h('div.people' + (localStorage.getItem('dz_noside') ? '.no-side' : ''), idx.el, h('div.viewwrap', tb, viewEl), sideEl);
  put(root, ws);
  function switchView(k) {
    S.view = k; localStorage.setItem('dz_view', k);
    tabs.querySelectorAll('button').forEach((b, i) => b.classList.toggle('active', views[i][0] === k));
    syncTools(); draw();
  }
  function syncTools() { genSel.classList.toggle('hidden', S.view !== 'pedigree'); dGen.classList.toggle('hidden', S.view !== 'descendants'); }
  syncTools();
  if (!S.person) {
    const r = await GET('/api/people?limit=1');
    if (r.rows.length) S.person = (S.settings?.rootPersonId) || r.rows[0][0];
  }
  if (!S.hist.length && S.person) { S.hist = [S.person]; S.histPos = 0; }
  await draw();
}

on('person', () => { if (root?.isConnected) draw(); });
on('changed', () => { cache = {}; if (root?.isConnected) { idx.reload(); draw(); } });

async function draw() {
  if (!viewEl) return;
  idx.highlight(S.person);
  if (!S.person) {
    fill(viewEl, h('div.empty', h('p', 'This file has no people yet.'),
      h('button.btn.primary', { onclick: () => import('./edit.js').then(m => m.addPerson({})) }, '+ Add the first person')));
    clear(sideEl);
    return;
  }
  const v = S.view;
  try {
    const p = { pedigree: pedigreeView, family: familyView, descendants: descendantView, list: listView, couples: couplesView, fans: fansView, map: mapView }[v] || pedigreeView;
    await Promise.all([p(), sidePanel()]);
  } catch (e) {
    if (e.status === 404) { S.person = 0; localStorage.removeItem('dz_person'); return draw(); }
    fail(e);
  }
}

// ---------------------------------------------------------------- name index (virtual list)
function indexPanel() {
  let rows = [], filtered = [], selId = 0;
  const RH = 26;
  const q = h('input', { type: 'search', placeholder: 'Surname, given…', style: { width: '100%' } });
  const alt = h('input', { type: 'checkbox', checked: localStorage.getItem('dz_alt') === '1' });
  const count = h('span.muted.small');
  const inner = h('div', { style: { position: 'relative' } });
  const list = h('div.ilist', inner);
  const el = h('aside.index', h('div.ihead', q, h('div.row', h('label.chk', alt, 'Alternate names'), h('span.right', count))), list);
  async function load() {
    const r = await GET('/api/people' + (alt.checked ? '?alt=1' : ''));
    rows = r.rows; filter();
  }
  function filter() {
    const t = q.value.trim().toLowerCase();
    if (!t) filtered = rows;
    else if (t.includes(',')) {
      const [s, g] = t.split(',').map(x => x.trim());
      filtered = rows.filter(r => r[1].toLowerCase().startsWith(s) && r[2].toLowerCase().startsWith(g));
    } else if (/^\d+$/.test(t)) filtered = rows.filter(r => String(r[0]) === t);
    else filtered = rows.filter(r => r[1].toLowerCase().startsWith(t) || (r[2] + ' ' + r[1]).toLowerCase().includes(t));
    count.textContent = filtered.length.toLocaleString();
    inner.style.height = filtered.length * RH + 'px';
    paint();
  }
  function paint() {
    const top = list.scrollTop, hgt = list.clientHeight || 600;
    const a = Math.max(0, Math.floor(top / RH) - 10), b = Math.min(filtered.length, Math.ceil((top + hgt) / RH) + 10);
    clear(inner);
    for (let i = a; i < b; i++) {
      const r = filtered[i];
      put(inner, h('div.irow' + (r[0] === selId ? '.sel' : '') + (r[7] ? '' : '.alt'), {
        style: { top: i * RH + 'px' }, title: `#${r[0]}`, onclick: () => setPerson(r[0]),
        ondblclick: () => import('./edit.js').then(m => m.editPerson(r[0])),
      }, h('span.colordot', { style: { background: colorOf(r[8]) } }),
        h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, (r[1] ? r[1].toUpperCase() === r[1] ? r[1] : r[1] : '—') + ', ' + r[2] + (r[3] ? ' ' + r[3] : '')),
        r[9] ? h('span', { title: 'Bookmarked' }, '★') : '',
        h('span.yrs', yrs(r[4], r[5]))));
    }
  }
  list.addEventListener('scroll', paint);
  q.addEventListener('input', debounce(filter, 120));
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && filtered[0]) setPerson(filtered[0][0]); });
  alt.addEventListener('change', () => { localStorage.setItem('dz_alt', alt.checked ? '1' : ''); load(); });
  new ResizeObserver(paint).observe(list);
  load();
  return {
    el, reload: load,
    highlight(id) {
      selId = id;
      const i = filtered.findIndex(r => r[0] === id);
      if (i >= 0 && (i * RH < list.scrollTop || i * RH > list.scrollTop + list.clientHeight - RH)) list.scrollTop = Math.max(0, i * RH - list.clientHeight / 2);
      paint();
    },
  };
}

// ---------------------------------------------------------------- pedigree
function boxEl(p, x, y, w, hgt, num, { focus = false, onclick } = {}) {
  if (!p) return h('div.pbox.empty', { style: { left: x + 'px', top: y + 'px', width: w + 'px', height: hgt + 'px' }, onclick }, '+ add');
  const b = h('div.pbox.' + (sexClass(p.sex) || 'u') + (focus ? '.focus' : ''), {
    style: { left: x + 'px', top: y + 'px', width: w + 'px', height: hgt + 'px' },
    onclick: () => setPerson(p.id), ondblclick: () => import('./edit.js').then(m => m.editPerson(p.id)), title: `${p.name} [${p.id}]`,
  }, h('div.nm', p.color ? h('span.colordot', { style: { background: colorOf(p.color), marginRight: '4px' } }) : '', p.name || '(no name)'),
    hgt > 34 && p.birth ? h('div.dt', 'b. ', [p.birth.date, p.birth.place].filter(Boolean).join(', ')) : null,
    hgt > 50 && p.death ? h('div.dt', 'd. ', [p.death.date, p.death.place].filter(Boolean).join(', ')) : null,
    hgt <= 34 ? h('div.dt', lifeOf(p)) : null,
    num ? h('span.num', num) : null,
    p.hasParents === true && num ? h('span.more', '▶') : null);
  return b;
}

async function pedigreeView() {
  const gens = Number(localStorage.getItem('dz_pedgens') || 5);
  const d = await GET(`/api/pedigree/${S.person}?gens=${gens}`);
  // fit the chart to the visible area; scroll only when the window is too small
  const W = viewEl.clientWidth || 1000, VH = (viewEl.clientHeight || 700) - 30;
  const left = 170;
  const colW = Math.max(140, Math.min(260, (W - left - 30) / gens - 30));
  const leaves = 2 ** (gens - 1);
  const H = Math.max(leaves * (gens >= 6 ? 26 : 34) + 20, VH, 420);
  const boxH = Math.max(24, Math.min(62, H / leaves - 6));
  const canvas = h('div', { style: { position: 'relative', width: left + gens * (colW + 30) + 'px', height: H + 'px', margin: '10px' } });
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'lines'); svg.setAttribute('width', left + gens * (colW + 30)); svg.setAttribute('height', H);
  const P = d.people;
  for (let g = 0; g < gens; g++) {
    const n = 2 ** g;
    for (let i = 0; i < n; i++) {
      const num = n + i, span = H / n;
      const x = left + g * (colW + 30), y = span * i + span / 2 - boxH / 2;
      const p = P[num];
      if (g < gens - 1) {
        for (const c of [2 * num, 2 * num + 1]) {
          const j = c - 2 * n, cs = H / (2 * n), cy = cs * j + cs / 2;
          if (!P[c] && !p) continue;
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', `M${x + colW} ${y + boxH / 2} H${x + colW + 15} V${cy} H${x + colW + 30}`);
          put(svg, path);
        }
      }
      if (!p && num > 1 && !P[Math.floor(num / 2)]) continue;
      const child = P[Math.floor(num / 2)];
      put(canvas, boxEl(p, x, y, colW, boxH, num, {
        focus: num === 1,
        onclick: !p && child ? () => import('./edit.js').then(m => m.addPerson({ rel: num % 2 ? 'mother' : 'father', of: child.id, sex: num % 2 ? 1 : 0 })) : null,
      }));
    }
  }
  canvas.prepend(svg);
  // children & spouses column (to go "back down")
  const kids = h('div', { style: { position: 'absolute', left: '0', top: '10px', width: left - 20 + 'px' } },
    d.spouses.length ? h('div.muted.small', 'Spouses') : null,
    d.spouses.map(s => h('div', { style: { cursor: 'pointer', padding: '2px 0' }, onclick: () => setPerson(s.id) }, '⚭ ', s.name)),
    h('div.muted.small', { style: { marginTop: '8px' } }, 'Children'),
    d.children.length ? d.children.map(c => h('div', { style: { cursor: 'pointer', padding: '2px 0' }, onclick: () => setPerson(c.id) }, '◀ ', c.name, ' ', h('span.muted.small', lifeOf(c)))) : h('div.muted.small', 'none'),
    h('button.btn.sm', { style: { marginTop: '6px' }, onclick: () => import('./edit.js').then(m => m.addPerson({ rel: 'child', of: S.person })) }, '+ child'));
  put(canvas, kids);
  fill(viewEl, canvas);
}

// ---------------------------------------------------------------- family view
async function familyView() {
  const pd = await GET(`/api/person/${S.person}`);
  const me = pd.summary;
  let famIdx = Number(sessionStorage.getItem('dz_famidx_' + S.person) || 0);
  if (famIdx >= pd.spouses.length) famIdx = 0;
  const fam = pd.spouses[famIdx];
  const isMale = me.sex !== 1;
  const left = isMale ? me : fam?.spouse, right = isMale ? fam?.spouse : me;
  const leftParents = isMale ? pd.parents[0] : null, rightParents = isMale ? null : pd.parents[0];
  async function parentsOf(p) {
    if (!p) return null;
    if (p.id === me.id) return pd.parents[0] || null;
    return (await GET(`/api/person/${p.id}`)).parents[0] || null;
  }
  const [lp, rp] = await Promise.all([leftParents ? leftParents : parentsOf(left), rightParents ? rightParents : parentsOf(right)]);
  function card(p, role, parents, sex) {
    if (!p) {
      return h('div.fcard', h('div.muted', role), h('button.btn', {
        onclick: () => import('./edit.js').then(m => m.addPerson({ rel: 'spouse', of: me.id, sex })),
      }, '+ Add ' + role.toLowerCase()));
    }
    return h('div.fcard.' + (sexClass(p.sex) || 'u'),
      h('div.gp', h('div', { onclick: () => parents?.father ? setPerson(parents.father.id) : import('./edit.js').then(m => m.addPerson({ rel: 'father', of: p.id, sex: 0 })) },
        h('div.muted', 'Father'), parents?.father ? personLine(parents.father, { ids: false }) : h('span.muted', '+ add')),
        h('div', { onclick: () => parents?.mother ? setPerson(parents.mother.id) : import('./edit.js').then(m => m.addPerson({ rel: 'mother', of: p.id, sex: 1 })) },
          h('div.muted', 'Mother'), parents?.mother ? personLine(parents.mother, { ids: false }) : h('span.muted', '+ add'))),
      h('div.muted.small', role),
      h('h3', { onclick: () => setPerson(p.id), ondblclick: () => import('./edit.js').then(m => m.editPerson(p.id)) }, p.name, ' ', h('span.muted.small', `[${p.id}]`)),
      p.birth ? h('div', h('span.muted', 'Born '), [p.birth.date, p.birth.place].filter(Boolean).join(', ')) : null,
      p.death ? h('div', h('span.muted', 'Died '), [p.death.date, p.death.place].filter(Boolean).join(', ')) : null,
      h('div.row', { style: { marginTop: '6px' } }, h('button.btn.sm', { onclick: () => import('./edit.js').then(m => m.editPerson(p.id)) }, 'Edit')));
  }
  const famTabs = pd.spouses.length > 1 ? h('div.row', { style: { gridColumn: '1 / -1' } }, h('span.muted', 'Spouses:'),
    pd.spouses.map((f, i) => h('button.btn.sm' + (i === famIdx ? '.primary' : ''), { onclick: () => { sessionStorage.setItem('dz_famidx_' + S.person, i); familyView(); } }, f.spouse?.name || 'Unknown'))) : null;
  const kids = fam ? fam.children : [];
  const view = h('div.famview',
    famTabs,
    card(left, 'Husband / Father', lp, 0), card(right, 'Wife / Mother', rp, 1),
    fam ? h('div.fcard.famfacts', h('div.row', h('b', 'Family'), h('span.muted.small', `#${fam.id}`),
      h('div.right.row', h('button.btn.sm', { onclick: () => import('./edit.js').then(m => m.editFamily(fam.id)) }, 'Edit family'))),
    fam.facts.length ? fam.facts.map(f => h('div', h('span.muted', f.typeName, ' '), [f.date, f.place, f.description].filter(Boolean).join(', '))) : h('div.muted', 'No marriage information')) : null,
    h('div.fcard.kids', h('div.row', h('b', 'Children'), h('span.muted', `(${kids.length})`),
      h('div.right.row', fam ? h('button.btn.sm', { onclick: () => rearrangeChildren(fam.id) }, 'Rearrange') : null,
        h('button.btn.sm', { onclick: () => import('./edit.js').then(m => m.addPerson({ rel: 'child', of: me.id, family: fam?.id })) }, '+ Add child'))),
    kids.map((c, i) => h('div.kid', { onclick: () => setPerson(c.id), ondblclick: () => import('./edit.js').then(m => m.editPerson(c.id)) },
      h('span.muted', i + 1), h('span', h('span.colordot', { style: { background: c.sex === 0 ? 'var(--maleLine)' : c.sex === 1 ? 'var(--femaleLine)' : 'var(--line)', marginRight: '6px' } }),
        c.name, c.relFather || c.relMother ? h('span.badge', { style: { marginLeft: '6px' } }, S.meta.childRel[c.relFather || c.relMother]) : ''),
      h('span.small', c.birth ? 'b. ' + [c.birth.date, c.birth.place?.split(',')[0]].filter(Boolean).join(' ') : ''),
      h('span.small', c.death ? 'd. ' + [c.death.date, c.death.place?.split(',')[0]].filter(Boolean).join(' ') : ''),
      h('span.small.muted', c.spouses ? `⚭${c.spouses}` : ''))),
    !kids.length ? h('div.muted', 'No children') : null));
  fill(viewEl, view);
}

// ---------------------------------------------------------------- descendants
async function descendantView() {
  const gens = Number(localStorage.getItem('dz_descgens') || 3);
  const d = await GET(`/api/descendants/${S.person}?gens=${gens}`);
  function node(p, depth) {
    const line = h('div.dline', h('span.muted.small', depth), h('span.who', { onclick: () => setPerson(p.id), ondblclick: () => import('./edit.js').then(m => m.editPerson(p.id)) }, p.name),
      h('span.muted.small', lifeOf(p)));
    const fams = p.families.map(f => h('div',
      h('div.dline', h('span.sp', { onclick: () => f.spouse && setPerson(f.spouse.id) }, '+ ', f.spouse ? f.spouse.name : 'unknown spouse', ' ', h('span.small', lifeOf(f.spouse))),
        f.marriage ? h('span.muted.small', 'm. ' + f.marriage.date) : ''),
      f.more ? h('div.dnode.muted.small', `… ${f.more} more children (go deeper)`) : null,
      h('div.dnode', f.children.map(c => node(c, depth + 1)))));
    return h('div', line, h('div', fams));
  }
  fill(viewEl, h('div.dtree', node(d, 1)));
}

// ---------------------------------------------------------------- list views
let listCols = null;
async function listView() {
  const r = await GET('/api/people');
  const rows = r.rows.map(x => ({ id: x[0], surname: x[1], given: x[2], suffix: x[3], by: x[4], dy: x[5], sex: x[6], color: x[8], bookmark: x[9], living: x[10] }));
  const t = dataTable([
    { key: 'id', label: '#', width: '60px' },
    { key: 'color', label: '', width: '18px', render: x => h('span.colordot', { style: { background: colorOf(x.color) } }) },
    { key: 'surname', label: 'Surname' }, { key: 'given', label: 'Given' }, { key: 'suffix', label: 'Suffix' },
    { key: 'sex', label: 'Sex', render: x => S.meta.sex[x.sex] || '' },
    { key: 'by', label: 'Born', render: x => x.by || '' }, { key: 'dy', label: 'Died', render: x => x.dy || '' },
    { key: 'living', label: 'Living', render: x => x.living ? '✓' : '' },
  ], rows, { onclick: x => setPerson(x.id), selectable: true });
  fill(viewEl, h('div', { style: { padding: '10px', height: '100%', display: 'flex', flexDirection: 'column' } }, t));
}

async function couplesView() {
  const rows = await GET('/api/couples');
  const t = dataTable([
    { key: 'id', label: '#', width: '60px' }, { key: 'fatherName', label: 'Husband' }, { key: 'motherName', label: 'Wife' },
    { key: 'marriage', label: 'Marriage' }, { key: 'place', label: 'Place' }, { key: 'children', label: 'Children' },
  ], rows, { onclick: x => setPerson(x.father || x.mother), selectable: true });
  fill(viewEl, h('div', { style: { padding: '10px', height: '100%', display: 'flex', flexDirection: 'column' } }, t));
}

async function fansView() {
  const rows = await GET('/api/fans');
  const t = dataTable([
    { key: 'p1', label: 'Person 1' }, { key: 'Role1', label: 'Role' }, { key: 'p2', label: 'Person 2' }, { key: 'Role2', label: 'Role' },
    { key: 'TypeName', label: 'Type' }, { key: 'dateText', label: 'Date' }, { key: 'Description', label: 'Description' },
  ], rows, { onclick: x => setPerson(x.ID1), empty: 'No associations. Add them from Edit Person › Associations.' });
  fill(viewEl, h('div', { style: { padding: '10px', height: '100%', display: 'flex', flexDirection: 'column' } }, t));
}

// ---------------------------------------------------------------- map (Leaflet from CDN; list fallback offline)
let leafletLoading = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  leafletLoading = leafletLoading || new Promise((res, rej) => {
    put(document.head, h('link', { rel: 'stylesheet', href: 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' }));
    const s = h('script', { src: 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' });
    s.onload = res; s.onerror = () => { leafletLoading = null; rej(new Error('Map library could not be loaded (offline?)')); };
    put(document.head, s);
  });
  return leafletLoading;
}
async function mapView() {
  const mode = sessionStorage.getItem('dz_mapmode') || 'person';
  const pts = await GET('/api/places/map' + (mode === 'person' ? `?person=${S.person}` : ''));
  const modeSel = select([['person', 'This person'], ['all', 'Everyone']], mode, { onchange: e => { sessionStorage.setItem('dz_mapmode', e.target.value); mapView(); } });
  const mapDiv = h('div.map');
  const info = h('div.small.muted', `${pts.length} geocoded places. Places without coordinates are not shown — add them in Places (Geocode).`);
  fill(viewEl, h('div.col', { style: { height: '100%', padding: '8px' } }, h('div.row', modeSel, info), mapDiv));
  try {
    await loadLeaflet();
    const map = L.map(mapDiv).setView([30, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors', maxZoom: 18 }).addTo(map);
    const bounds = [];
    for (const p of pts) {
      const evs = p.events.map(e => `${e.date || ''} ${e.fact}: ${e.who}`).join('<br>');
      L.marker([p.lat, p.lon]).addTo(map).bindPopup(`<b>${p.name.replace(/</g, '&lt;')}</b><br>${evs.replace(/<(?!br>)/g, '&lt;')}`);
      bounds.push([p.lat, p.lon]);
    }
    if (mode === 'person' && pts.length > 1) {
      const ordered = pts.map(p => ({ p, s: Math.min(...p.events.map(e => e.sort)) })).sort((a, b) => a.s - b.s).map(x => [x.p.lat, x.p.lon]);
      L.polyline(ordered, { color: '#2f6f4f', dashArray: '4 6' }).addTo(map);
    }
    if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 9 });
  } catch (e) {
    mapDiv.replaceWith(dataTable([{ key: 'name', label: 'Place' }, { key: 'lat', label: 'Lat' }, { key: 'lon', label: 'Lon' },
      { key: 'ev', label: 'Events', render: p => p.events.map(e => `${e.date} ${e.fact}: ${e.who}`).join('; ') }], pts));
    info.textContent = e.message;
  }
}

// ---------------------------------------------------------------- side panel
async function sidePanel() {
  const d = await GET(`/api/person/${S.person}`);
  const p = d.summary;
  const edit = tab => import('./edit.js').then(m => m.editPerson(p.id, tab));
  const fact = f => h('div.fact', { onclick: () => import('./edit.js').then(m => m.editPerson(p.id, 'facts', f.id)) },
    h('span.ft', f.typeName), h('span', [f.date, f.placeDetails, f.place].filter(Boolean).join(', '), f.description ? h('div.small', f.description) : '',
      h('div.flags', f.citations ? `📎${f.citations} ` : '', f.media ? `🖼${f.media} ` : '', f.shared ? `shared (${f.shared.role} for ${f.shared.principal})` : '', f.private ? 'private ' : '')));
  fill(sideEl, 
    h('div.shead', h('div.row', h('h2', p.name || '(no name)'), h('span.muted.small', `#${p.id}`)),
      h('div.muted', [S.meta.sex[p.sex], lifeOf(p), p.living ? 'living' : ''].filter(Boolean).join(' · ')),
      d.relationship ? h('div.small', { style: { color: 'var(--accent)' } }, d.relationship + ' of root person') : null,
      h('div.row.wrap', { style: { marginTop: '8px' } },
        h('button.btn.primary', { onclick: () => edit() }, 'Edit person'),
        h('button.btn', { onclick: toggleBookmark, title: 'Bookmark' }, p.bookmark ? '★' : '☆'),
        h('button.btn', { onclick: () => import('./edit.js').then(m => m.addPerson({ rel: 'spouse', of: p.id })) }, '+ Spouse'),
        h('button.btn', { onclick: () => import('./edit.js').then(m => m.addParents(p.id)) }, '+ Parents'),
        h('button.btn', { onclick: () => import('./edit.js').then(m => m.addPerson({ rel: 'child', of: p.id })) }, '+ Child'))),
    h('section', h('h4', 'Facts', h('button.btn.sm.right', { onclick: () => edit('facts') }, '+ fact')), d.facts.length ? d.facts.map(fact) : h('div.muted', 'No facts')),
    h('section', h('h4', 'Parents'), d.parents.length ? d.parents.map(pf => h('div',
      pf.father ? h('div.fact', { onclick: () => setPerson(pf.father.id) }, h('span.ft', 'Father'), personLine(pf.father, { ids: false })) : null,
      pf.mother ? h('div.fact', { onclick: () => setPerson(pf.mother.id) }, h('span.ft', 'Mother'), personLine(pf.mother, { ids: false })) : null,
      pf.relFather || pf.relMother ? h('div.small.muted', 'Relationship: ' + S.meta.childRel[pf.relFather] + ' / ' + S.meta.childRel[pf.relMother]) : null)) : h('div.muted', 'None')),
    h('section', h('h4', 'Spouses & children'), d.spouses.length ? d.spouses.map(f => h('div',
      h('div.fact', { onclick: () => f.spouse && setPerson(f.spouse.id) }, h('span.ft', 'Spouse'), f.spouse ? personLine(f.spouse, { ids: false }) : h('span.muted', 'unknown')),
      f.marriage ? h('div.small.muted', { style: { marginLeft: '102px' } }, 'm. ', [f.marriage.date, f.marriage.place].filter(Boolean).join(', ')) : null,
      f.children.map(c => h('div.fact', { onclick: () => setPerson(c.id) }, h('span.ft', 'Child'), personLine(c, { ids: false }))))) : h('div.muted', 'None')),
    d.siblings.length ? h('section', h('h4', 'Siblings'), d.siblings.map(c => h('div.fact', { onclick: () => setPerson(c.id) }, h('span.ft', S.meta.sex[c.sex] === 'Male' ? 'Brother' : S.meta.sex[c.sex] === 'Female' ? 'Sister' : 'Sibling'), personLine(c, { ids: false })))) : null,
    d.person.Note ? h('section', h('h4', 'Notes', h('button.btn.sm.right', { onclick: () => edit('notes') }, 'edit')), h('div.small', { html: d.noteHtml.slice(0, 1500) })) : null,
    d.media.length ? h('section', h('h4', 'Media'), h('div.thumbs', d.media.slice(0, 6).map(m => h('div.thumb', { onclick: () => edit('media') },
      m.MediaType === 1 ? h('img', { src: `/api/media/${m.MediaID}/file`, loading: 'lazy' }) : h('div.doc', '📄'), h('div.cap', m.Caption || m.MediaFile))))) : null,
    d.fans.length ? h('section', h('h4', 'Associations'), d.fans.map(a => h('div.fact', { onclick: () => setPerson(a.other.id) }, h('span.ft', a.theirRole || a.TypeName), personLine(a.other, { ids: false })))) : null,
    d.groups.length ? h('section', h('h4', 'Groups'), h('div.chips', d.groups.map(g => h('span.chip', g.Name)))) : null,
    d.tasks.length ? h('section', h('h4', 'Tasks'), d.tasks.map(t => h('div.small', '☐ ', t.Name))) : null,
  );
}

// ---------------------------------------------------------------- family operations (Edit menu)
async function currentFamily() {
  const d = await GET(`/api/person/${S.person}`);
  const idx = Number(sessionStorage.getItem('dz_famidx_' + S.person) || 0);
  return { d, fam: d.spouses[idx] || d.spouses[0] };
}
export async function swapCouple() {
  const { fam } = await currentFamily();
  if (!fam) return toast('This person has no family');
  await POST(`/api/family/${fam.id}/swap`); emitChanged(); toast('Swapped');
}
export async function rearrangeChildren(fid) {
  if (!fid) fid = (await currentFamily()).fam?.id;
  if (!fid) return toast('No family selected');
  const f = await GET(`/api/family/${fid}`);
  let order = f.children.map(c => c);
  const list = h('div.list');
  function draw() {
    clear(list);
    order.forEach((c, i) => put(list, h('div', h('span.muted', i + 1), c.name, h('span.muted.small', lifeOf(c)),
      h('span.right.row', h('button.btn.sm', { disabled: !i, onclick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); } }, '↑'),
        h('button.btn.sm', { disabled: i === order.length - 1, onclick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); } }, '↓')))));
  }
  draw();
  const r = await modal({ title: 'Rearrange children', body: list, buttons: [
    { label: 'Sort by birth date', click: async () => { await POST(`/api/family/${fid}/children`, { sortByBirth: true }); return true; } },
    { label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST(`/api/family/${fid}/children`, { order: order.map(c => c.id) }) }] }).done;
  if (r) emitChanged();
}
export async function rearrangeSpouses() {
  const d = await GET(`/api/person/${S.person}`);
  let order = [...d.spouses];
  if (order.length < 2) return toast('Only one spouse');
  const list = h('div.list');
  function draw() {
    clear(list);
    order.forEach((f, i) => put(list, h('div', f.spouse?.name || 'Unknown spouse', h('span.right.row',
      h('button.btn.sm', { disabled: !i, onclick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); } }, '↑'),
      h('button.btn.sm', { disabled: i === order.length - 1, onclick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); } }, '↓')))));
  }
  draw();
  const r = await modal({ title: 'Rearrange spouses', body: list, buttons: [{ label: 'Cancel' }, { label: 'Save', primary: true, click: () => POST(`/api/person/${S.person}/spouseOrder`, { order: order.map(f => f.id) }) }] }).done;
  if (r) emitChanged();
}
export async function unlinkParents() {
  const d = await GET(`/api/person/${S.person}`);
  if (!d.parents.length) return toast('No parents linked');
  const pf = d.parents[0];
  if (await confirmBox(`Unlink ${d.summary.name} from parents ${[pf.father?.name, pf.mother?.name].filter(Boolean).join(' and ')}? No one is deleted.`))
    POST(`/api/family/${pf.family}/unlinkChild`, { child: S.person }).then(emitChanged, fail);
}
export async function unlinkSpouse() {
  const { d, fam } = await currentFamily();
  if (!fam) return toast('No spouse');
  if (await confirmBox(`Unlink ${d.summary.name} from ${fam.spouse?.name || 'spouse'}? No one is deleted.`))
    POST(`/api/family/${fam.id}/unlinkSpouse`, { person: S.person }).then(emitChanged, fail);
}
export async function deleteFamily() {
  const { fam } = await currentFamily();
  if (!fam) return toast('No family');
  if (await confirmBox('Delete this family? The people stay; their family links and family facts are removed.', { danger: true, ok: 'Delete family' }))
    DEL(`/api/family/${fam.id}`).then(emitChanged, fail);
}
export async function toggleBookmark() {
  const d = await GET(`/api/person/${S.person}`);
  await PUT(`/api/person/${S.person}`, { Bookmark: d.person.Bookmark ? 0 : 1 });
  toast(d.person.Bookmark ? 'Bookmark removed' : 'Bookmarked');
  emitChanged();
}
export async function bookmarks() {
  const b = await GET('/api/bookmarks');
  modal({ title: 'Bookmarks', body: b.length ? h('div.list', b.map(p => h('div', { style: { cursor: 'pointer' }, onclick: () => { goPerson(p.id); document.querySelector('.backdrop')?.remove(); } }, personLine(p),
    h('button.btn.sm.right', { onclick: async e => { e.stopPropagation(); await PUT(`/api/person/${p.id}`, { Bookmark: 0 }); e.target.closest('div').remove(); } }, 'Remove')))) : h('p.muted', 'No bookmarks yet.') });
}
export async function historyList() {
  const ids = [...new Set([...S.hist].reverse())].slice(0, 40);
  const ppl = await Promise.all(ids.map(id => GET(`/api/person/${id}`).then(d => d.summary).catch(() => null)));
  const m = modal({ title: 'History', body: h('div.list', ppl.filter(Boolean).map(p => h('div', { style: { cursor: 'pointer' }, onclick: () => { m.close(); goPerson(p.id); } }, personLine(p)))) });
}
export async function immediateFamily() {
  const d = await GET(`/api/person/${S.person}`);
  const line = (label, p) => p ? h('div', { style: { cursor: 'pointer' }, onclick: () => { m.close(); goPerson(p.id); } }, h('span.muted', label + ': '), personLine(p)) : null;
  const m = modal({ title: 'Immediate family of ' + d.summary.name, body: h('div.list',
    d.parents.flatMap(pf => [line('Father', pf.father), line('Mother', pf.mother)]),
    d.siblings.map(s => line('Sibling', s)),
    d.spouses.flatMap(f => [line('Spouse', f.spouse), ...f.children.map(c => line('Child', c))])) });
}
export function emitChanged() { import('./app.js').then(a => a.emit('changed')); }
