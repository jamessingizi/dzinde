// Search: advanced person search (criteria), find everywhere, search & replace, WebSearch.
import { GET, POST, DEL, h, clear, modal, toast, fail, confirmBox, promptBox, dataTable, select, checkbox, field, choosePerson, put, fill } from './ui.js';
import { S, goPerson, emit } from './app.js';

const FIELDS = [
  ['name', 'Name (primary)'], ['given', 'Given name'], ['surname', 'Surname'], ['nickname', 'Nickname'], ['anyName', 'Any name (incl. alternate)'],
  ['soundex', 'Surname sounds like (Soundex)'], ['sex', 'Sex'], ['id', 'Record number'], ['living', 'Living flag'], ['private', 'Private flag'],
  ['bookmark', 'Bookmarked'], ['color', 'Color code'], ['proof', 'Proof'], ['note', 'Person note'],
  ['factType', 'Has fact of type'], ['factDate', 'Fact date (year)'], ['factPlace', 'Fact place'], ['factDesc', 'Fact description'], ['anyPlace', 'Any place'],
  ['hasParents', 'Has parents'], ['hasSpouse', 'Has spouse'], ['hasChildren', 'Has children'], ['spouseCount', 'Number of spouses'], ['childCount', 'Number of children'],
  ['ancestorOf', 'Is an ancestor of'], ['descendantOf', 'Is a descendant of'], ['relatedTo', 'Is blood relative of'], ['inGroup', 'Is in group'],
  ['hasSource', 'Has any source'], ['hasMedia', 'Has media'],
];
const OPS = {
  text: [['contains', 'contains'], ['equals', 'equals'], ['startsWith', 'starts with'], ['notContains', 'does not contain'], ['exists', 'exists'], ['missing', 'is missing']],
  bool: [['is', 'is'], ['not', 'is not']],
  num: [['equals', '='], ['after', '>'], ['before', '<'], ['not', '≠']],
  year: [['before', 'before'], ['after', 'after'], ['between', 'between'], ['equals', 'in'], ['exists', 'has a date'], ['missing', 'has no date']],
  rel: [['is', 'is'], ['not', 'is not']],
};
const kind = f => ['name', 'given', 'surname', 'nickname', 'anyName', 'note', 'factPlace', 'factDesc', 'anyPlace'].includes(f) ? 'text'
  : ['spouseCount', 'childCount'].includes(f) ? 'num' : f === 'factDate' ? 'year' : ['ancestorOf', 'descendantOf', 'relatedTo', 'inGroup'].includes(f) ? 'rel' : f === 'id' || f === 'soundex' ? 'id' : 'bool';

export function criteriaBuilder(initial = [{ field: 'surname', op: 'contains', value: '' }]) {
  const rows = h('div');
  const groupsP = GET('/api/groups').catch(() => []);
  function addRow(c) {
    const fsel = select(FIELDS, c.field), opSel = h('select'), valWrap = h('div'), ftSel = select([[0, '(any fact)'], ...S.meta.factTypes.map(f => [f.FactTypeID, f.Name])], c.factType || 0);
    let valGet = () => '';
    const row = h('div.crit', fsel, opSel, valWrap, ftSel, h('button.btn.sm', { onclick: () => row.remove(), title: 'Remove' }, '✕'));
    async function sync(v = c.value, op = c.op) {
      const k = kind(fsel.value);
      clear(opSel);
      for (const [a, b] of (OPS[k] || [['is', 'is'], ['between', 'between']])) put(opSel, h('option', { value: a, selected: a === op }, b));
      ftSel.style.visibility = fsel.value.startsWith('fact') ? 'visible' : 'hidden';
      clear(valWrap);
      if (k === 'rel' && fsel.value !== 'inGroup') {
        let pid = Number(v) || 0;
        const lbl = h('span', pid ? `#${pid}` : 'choose…');
        put(valWrap, h('button.btn.sm', { onclick: async () => { const x = await choosePerson(); if (x) { pid = x; lbl.textContent = (await GET(`/api/person/${x}`)).summary.name; } } }, lbl));
        if (pid) GET(`/api/person/${pid}`).then(d => (lbl.textContent = d.summary.name)).catch(() => {});
        valGet = () => pid;
      } else if (fsel.value === 'inGroup') {
        const gs = select((await groupsP).map(g => [g.GroupID, g.Name]), v); put(valWrap, gs); valGet = () => gs.value;
      } else if (fsel.value === 'sex') {
        const s = select([[0, 'Male'], [1, 'Female'], [2, 'Unknown']], v || 0); put(valWrap, s); valGet = () => s.value;
      } else if (fsel.value === 'color') {
        const s = select((S.settings.colorNames || []).map((n, i) => [i, n || '(none)']), v || 1); put(valWrap, s); valGet = () => s.value;
      } else if (fsel.value === 'proof') {
        const s = select(Object.entries(S.meta.proof).map(([a, b]) => [a, b || '(none)']), v || 1); put(valWrap, s); valGet = () => s.value;
      } else if (k === 'bool') {
        valGet = () => '1';
      } else {
        const i = h('input', { value: v ?? '', style: { width: '100%' }, placeholder: k === 'year' ? 'e.g. 1850  or  1840 1860' : fsel.value === 'id' ? 'e.g. 12  or  10-20' : '' });
        put(valWrap, i); valGet = () => i.value;
      }
    }
    fsel.onchange = () => sync('', '');
    sync();
    row.get = () => ({ field: fsel.value, op: opSel.value, value: valGet(), factType: Number(ftSel.value) });
    put(rows, row);
  }
  for (const c of initial) addRow(c);
  const match = select([['all', 'Match ALL of these'], ['any', 'Match ANY of these']], 'all');
  const el = h('div.col', rows, h('div.row', h('button.btn.sm', { onclick: () => addRow({ field: 'surname', op: 'contains', value: '' }) }, '+ Criterion'), match));
  el.get = () => ({ criteria: [...rows.children].map(r => r.get()), match: match.value });
  el.setMatch = v => (match.value = v);
  return el;
}

export async function criteriaDialog(title = 'Criteria') {
  const b = criteriaBuilder();
  const mode = select([['set', 'Replace members with matches'], ['add', 'Add matches to group'], ['remove', 'Remove matches from group']], 'set');
  return modal({ title, xwide: false, wide: true, body: h('div.col', b, h('div.row', mode)), buttons: [{ label: 'Cancel' }, { label: 'OK', primary: true, click: () => ({ ...b.get(), mode: mode.value }) }] }).done;
}

export async function render(root, [tab = 'advanced']) {
  const tabs = [['advanced', 'Person search'], ['everywhere', 'Find everywhere'], ['replace', 'Search & replace'], ['web', 'WebSearch']];
  const page = h('div.page-pad');
  put(root, h('div.toolbar', h('div.tabs', tabs.map(([k, l]) => h('button' + (k === tab ? '.active' : ''), { onclick: () => (location.hash = '#/search/' + k) }, l)))), page);
  await ({ advanced, everywhere, replace, web }[tab] || advanced)(page);
}

async function advanced(el) {
  let builder = criteriaBuilder();
  const holder = h('div', builder);
  const results = h('div', { style: { marginTop: '14px', display: 'flex', flexDirection: 'column', height: '52vh' } });
  let last = [];
  const saved = await GET('/api/savedSearches').catch(() => []);
  const savedSel = select([['', 'Saved searches…'], ...saved.map(s => [s.id, s.title])], '', { onchange: () => {
    const s = saved.find(x => String(x.id) === savedSel.value);
    if (s) { builder = criteriaBuilder(s.data.criteria); builder.setMatch(s.data.match); fill(holder, builder); }
  } });
  async function run(saveAs) {
    const q = builder.get();
    try {
      last = await POST('/api/search', { ...q, saveAs });
      fill(results, h('div.row', h('b', `${last.length} people found`), h('span.grow'),
        h('button.btn.sm', { onclick: async () => { const n = await promptBox('Create group from results', 'Group name', 'Search results'); if (n) { await POST('/api/group', { Name: n, members: last.map(p => p.id) }); toast('Group created'); emit('changed'); } } }, 'Save as group'),
        h('button.btn.sm', { onclick: async () => { const { run: runTool } = await import('./tools.js'); runTool('colorCode', null, last.map(p => p.id)); } }, 'Color code these…')),
      dataTable([{ key: 'id', label: '#', width: '60px' }, { key: 'name', label: 'Name' }, { key: 'b', label: 'Birth', render: p => p.birth ? [p.birth.date, p.birth.place].filter(Boolean).join(', ') : '' },
        { key: 'd', label: 'Death', render: p => p.death ? [p.death.date, p.death.place].filter(Boolean).join(', ') : '' }], last, { onclick: p => goPerson(p.id) }));
    } catch (e) { fail(e); }
  }
  put(el, h('div.row', h('h3', { style: { margin: 0 } }, 'Find people matching'), h('span.grow'), savedSel,
    savedSel.value ? null : h('button.btn.sm', { onclick: async () => { const s = saved.find(x => String(x.id) === savedSel.value); if (s && await confirmBox('Delete saved search?')) { await DEL(`/api/savedSearch/${s.id}`); toast('Deleted'); } } }, 'Delete saved')),
  h('div', { style: { marginTop: '10px' } }, holder),
  h('div.row', { style: { marginTop: '10px' } }, h('button.btn.primary', { onclick: () => run() }, 'Search'),
    h('button.btn', { onclick: async () => { const n = await promptBox('Save search', 'Name'); if (n) run(n); } }, 'Search & save criteria')), results);
}

async function everywhere(el) {
  const q = h('input', { type: 'search', placeholder: 'Text to find anywhere (names, notes, places, sources, media, tasks…)', style: { width: '480px' }, autofocus: true });
  const out = h('div', { style: { marginTop: '12px', display: 'flex', flexDirection: 'column', height: '64vh' } });
  async function go() {
    const r = await GET('/api/find?q=' + encodeURIComponent(q.value));
    fill(out, dataTable([{ key: 'where', label: 'Found in' }, { key: 'owner', label: 'Record' }, { key: 'snippet', label: 'Text' }], r,
      { onclick: x => openLink(x.link), empty: 'No matches' }));
  }
  q.addEventListener('keydown', e => e.key === 'Enter' && go());
  put(el, h('div.row', q, h('button.btn.primary', { onclick: go }, 'Find')), out);
}
function openLink([kind, id]) {
  if (kind === 'person' && id) goPerson(id);
  else if (kind === 'place') location.hash = '#/places';
  else if (kind === 'source') location.hash = '#/sources';
  else if (kind === 'media') location.hash = '#/media';
  else if (kind === 'task') location.hash = '#/tasks';
  else if (kind === 'address') location.hash = '#/addresses';
}

async function replace(el) {
  const find = h('input', { style: { width: '100%' } }), rep = h('input', { style: { width: '100%' } });
  const whole = checkbox('Whole words only', false), cs = checkbox('Match case', false);
  const fieldBoxes = S.meta.searchable.map(f => checkbox(f, ['Place', 'Given name', 'Surname', 'Fact description'].includes(f)));
  const out = h('div', { style: { marginTop: '12px', display: 'flex', flexDirection: 'column', height: '40vh' } });
  const params = () => ({ find: find.value, replace: rep.value, wholeWord: whole.input.checked, caseSensitive: cs.input.checked,
    fields: fieldBoxes.filter(b => b.input.checked).map(b => b.textContent) });
  put(el, h('div.form', { style: { maxWidth: '760px' } }, ...field('Find', find), ...field('Replace with', rep), ...field('', h('div.row', whole, cs)),
    ...field('Look in', h('div', { style: { columns: 3 } }, fieldBoxes.map(b => h('div', b))))),
  h('div.row', { style: { marginTop: '10px' } }, h('button.btn', { onclick: async () => {
    const r = await POST('/api/replace', { ...params(), preview: true });
    fill(out, h('b', `${r.length} changes will be made`), dataTable([{ key: 'where', label: 'Field' }, { key: 'owner', label: 'Record' }, { key: 'before', label: 'Before' }, { key: 'after', label: 'After' }], r));
  } }, 'Preview'), h('button.btn.primary', { onclick: async () => {
    if (!await confirmBox('Replace all matches? Make a backup first if unsure.', { ok: 'Replace all' })) return;
    const r = await POST('/api/replace', { ...params(), preview: false });
    toast(`${r.length} replacements made`); emit('changed'); clear(out);
  } }, 'Replace all')), out);
}

async function web(el) {
  if (!S.person) return put(el, h('p', 'Select a person first.'));
  const urls = await POST('/api/tools/webSearch', { person: S.person });
  const d = await GET(`/api/person/${S.person}`);
  put(el, h('h3', `WebSearch for ${d.summary.name}`), h('p.muted', 'Opens a search in your browser using this person’s name and years. Edit providers in Settings › WebSearch.'),
    h('div.cards', urls.map(u => h('a.card.click', { href: u.url, target: '_blank', rel: 'noopener noreferrer', style: { textDecoration: 'none', color: 'inherit' } }, h('h3', u.name), h('div.small.muted', { style: { wordBreak: 'break-all' } }, u.url)))));
}
