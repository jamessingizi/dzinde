// Tools page and tool dialogs.
import { GET, POST, DEL, h, clear, modal, toast, fail, confirmBox, dataTable, select, checkbox, field, choosePerson, chooseFile, personLine, lifeOf, dateInput, put, fill } from './ui.js';
import { S, goPerson, emit } from './app.js';

const changed = () => emit('changed');
const TOOLS = [
  ['Data quality', [['problems', 'Problem list', 'Find impossible or unlikely dates and relationships'], ['dataClean', 'DataClean', 'Fix name capitalization, nicknames/prefixes in names, and malformed places'],
    ['countyCheck', 'Place checker', 'Find duplicate and badly formatted place names'], ['duplicates', 'Duplicate search & merge', 'Find people who may be entered twice'],
    ['autoMerge', 'AutoMerge', 'Automatically merge exact duplicates'], ['manualMerge', 'Manual merge', 'Merge any two people'],
    ['notDup', 'Not-a-duplicate list', 'People you marked as not duplicates'], ['notProblem', 'Not-a-problem list', 'Problems you dismissed']]],
  ['People', [['setRelationships', 'Set relationships', 'Compute everyone’s relationship to a root person'], ['setLiving', 'Set living', 'Mark people living or deceased automatically'],
    ['colorCode', 'Color coding', 'Color people by ancestors, descendants, groups or criteria'], ['countTrees', 'Count trees', 'Find separate, unconnected trees in your file'],
    ['relCalc', 'Relationship calculator', 'How are two people related?'], ['kinship', 'Kinship list', 'Everyone related to a person'], ['aiPrompt', 'AI prompt builder', 'Build a research prompt to paste into an AI assistant']]],
  ['Calculators', [['dateCalc', 'Date calculator', 'Ages, date differences, birth year from age'], ['soundex', 'Soundex calculator', 'Soundex code of a surname'],
    ['calendar', 'Perpetual calendar', 'Any month of any year'], ['gazetteer', 'Gazetteer', 'Look up places worldwide (OpenStreetMap)'], ['onThisDay', 'On this day', 'Events on a given day'],
    ['whoWasThere', 'Who was there', 'People present at a place in a period'], ['statistics', 'Statistics', 'Counts and lifespans for your file']]],
  ['File', [['database', 'Database tools', 'Integrity check, compact, rebuild indexes, clean phantom records'], ['compare', 'Compare files', 'Compare this file with another file'],
    ['importlists', 'Import lists', 'Copy fact types, templates, places, sources from another file'], ['fixMedia', 'Fix broken media links', 'Find moved media files']]],
];

export async function render(root, [tool]) {
  put(root, h('div.page-pad', TOOLS.map(([sec, items]) => [h('h2.section', sec),
    h('div.cards', items.map(([k, t, dsc]) => h('div.card.click', { onclick: () => run(k) }, h('h3', t), h('div.small.muted', dsc))))])));
  if (tool) run(tool);
}

export async function run(name, cb, ids) {
  try { await (T[name] || (() => toast('Unknown tool ' + name)))(cb, ids); } catch (e) { fail(e); }
}

const pick = async (title, def = S.person) => {
  let pid = def;
  const lbl = h('span', '…');
  const set = async () => { lbl.textContent = pid ? (await GET(`/api/person/${pid}`)).summary.name + ` [${pid}]` : 'choose…'; };
  set();
  const el = h('div.row', lbl, h('button.btn.sm', { onclick: async () => { const x = await choosePerson({ title }); if (x) { pid = x; set(); } } }, 'Change…'));
  return { el, get: () => pid };
};
const resultModal = (title, body, wide = true) => modal({ title, wide, xwide: wide === 'x', body });

const T = {
  async countTrees() {
    const r = await POST('/api/tools/countTrees');
    resultModal('Count trees', h('div.col', h('p', `${r.length} separate trees.`), dataTable([{ key: 'n', label: '#', render: (t) => r.indexOf(t) + 1 }, { key: 'size', label: 'People' },
      { key: 'start', label: 'Starting person', render: t => personLine(t.start) }], r, { onclick: t => goPerson(t.start.id) })));
  },
  async setLiving() {
    const yrs = h('input', { type: 'number', value: S.settings.livingYears || 110, style: { width: '90px' } });
    const ok = await modal({ title: 'Set living', body: h('div.col', h('p', 'Marks each person living unless they have a death/burial fact or were (or probably were) born more than this many years ago:'), yrs),
      buttons: [{ label: 'Cancel' }, { label: 'Set living flags', primary: true, click: () => POST('/api/tools/setLiving', { years: Number(yrs.value) }) }] }).done;
    if (ok) { toast(`${ok.changed} people changed`); changed(); }
  },
  async setRelationships() {
    const p = await pick('Root person', S.settings.rootPersonId || S.person);
    const ok = await modal({ title: 'Set relationships', body: h('div.col', h('p', 'Calculates each blood relative’s relationship to the root person (shown in the side panel and usable in reports).'), p.el),
      buttons: [{ label: 'Clear all', click: () => POST('/api/tools/clearRelationships') }, { label: 'Cancel' }, { label: 'Set relationships', primary: true, click: () => POST('/api/tools/setRelationships', { root: p.get() }) }] }).done;
    if (ok) { toast(ok.set != null ? `${ok.set} relationships set` : 'Cleared'); const a = await import('./app.js'); await a.refreshFile(); changed(); }
  },
  async relCalc() {
    const a = await pick('First person'), b = await pick('Second person', 0);
    const out = h('div');
    modal({ title: 'Relationship calculator', wide: true, body: h('div.col', h('div.form', ...field('Person 1', a.el), ...field('Person 2', b.el)),
      h('button.btn.primary', { onclick: async () => {
        if (!b.get()) return toast('Choose the second person');
        const r = await POST('/api/tools/relationship', { a: a.get(), b: b.get() });
        fill(out, r.relationships.length ? h('div.list', r.relationships.map(x => h('div', { style: { flexDirection: 'column', alignItems: 'flex-start' } },
          h('div', h('b', r.b.name), ' is the ', h('b', x.name), ' of ', h('b', r.a.name)),
          x.ancestors.length ? h('div.small.muted', 'Common ancestor(s): ', x.ancestors.map(p => p.name).join(' & ')) : null))) : h('p', `${r.b.name} is not related to ${r.a.name}.`),
        h('button.btn.sm', { style: { marginTop: '8px' }, onclick: () => import('./publish.js').then(m => m.runReport('rptRelationshipChart', { person: a.get(), person2: b.get(), title: '' })) }, 'Print relationship chart'));
      } }, 'Calculate'), out) });
  },
  async kinship() {
    const p = await pick('Person');
    const ok = await modal({ title: 'Kinship list', body: p.el, buttons: [{ label: 'Cancel' }, { label: 'Show', primary: true, value: true }] }).done;
    if (!ok) return;
    const r = await POST('/api/tools/kinship', { person: p.get() });
    resultModal('Kinship list', dataTable([{ key: 'n', label: 'Name', render: x => x.person.name, text: x => x.person.name }, { key: 'l', label: 'Life', render: x => lifeOf(x.person) },
      { key: 'relationship', label: 'Relationship' }], r, { onclick: x => goPerson(x.person.id), height: '60vh' }));
  },
  async duplicates() {
    const score = h('input', { type: 'number', value: 60, style: { width: '80px' } }), sx = checkbox('Match surnames by Soundex', true);
    const out = h('div', { style: { display: 'flex', flexDirection: 'column', height: '58vh' } });
    async function go() {
      const r = await POST('/api/tools/duplicates', { minScore: Number(score.value), soundex: sx.input.checked });
      fill(out, dataTable([{ key: 'score', label: 'Score', width: '60px' }, { key: 'a', label: 'Person 1', render: d => personLine(d.a), text: d => d.a.name },
        { key: 'b', label: 'Person 2', render: d => personLine(d.b), text: d => d.b.name },
        { key: 'x', label: '', render: d => h('div.row', h('button.btn.sm', { onclick: async e => { e.stopPropagation(); if (await compareMerge(d.a.id, d.b.id)) go(); } }, 'Compare / merge'),
          h('button.btn.sm', { onclick: async e => { e.stopPropagation(); await POST('/api/tools/notDuplicate', { a: d.a.id, b: d.b.id }); go(); } }, 'Not a duplicate')) }],
      r, { empty: 'No likely duplicates found' }));
    }
    resultModal('Duplicate search', h('div.col', h('div.row', 'Minimum score', score, sx, h('button.btn.primary', { onclick: go }, 'Search')), out), 'x');
    go();
  },
  async autoMerge() {
    if (!await confirmBox('AutoMerge merges people with the same full name, sex, exact birth date and parents. Make a backup first. Continue?', { ok: 'AutoMerge' })) return;
    const r = await POST('/api/tools/autoMerge');
    toast(`${r.merged} people merged`); changed();
  },
  async manualMerge() {
    const a = await choosePerson({ title: 'First person (to keep)' });
    if (!a) return;
    const b = await choosePerson({ title: 'Second person (to merge into the first)', exclude: [a] });
    if (b && await compareMerge(a, b)) changed();
  },
  async notDup() {
    const r = await POST('/api/tools/notDuplicateList');
    resultModal('Not-a-duplicate list', h('div.col', h('button.btn.sm', { onclick: async () => { if (await confirmBox('Clear the whole list?')) { await POST('/api/tools/clearNotDuplicates'); toast('Cleared'); } } }, 'Clear list'),
      dataTable([{ key: 'a', label: 'Person 1', render: x => personLine(x.a) }, { key: 'b', label: 'Person 2', render: x => personLine(x.b) },
        { key: 'x', label: '', render: x => h('button.btn.sm', { onclick: async e => { await POST('/api/tools/deleteExclusion', { id: x.id }); e.target.closest('tr').remove(); } }, 'Remove') }], r)));
  },
  async problems() {
    const meta = await POST('/api/tools/problems', { rules: [] });
    const opts = Object.fromEntries(Object.entries(meta.defaults).map(([k, v]) => [k, h('input', { type: 'number', value: v, style: { width: '70px' } })]));
    const rules = Object.entries(meta.rules).map(([k, l]) => { const c = checkbox(l.replace(/\{(\w+)\}/g, (_, x) => opts[x] ? `(${meta.defaults[x]})` : x), true); c.key = k; return c; });
    const out = h('div', { style: { display: 'flex', flexDirection: 'column', height: '46vh' } });
    async function go() {
      const r = await POST('/api/tools/problems', { rules: rules.filter(c => c.input.checked).map(c => c.key), options: Object.fromEntries(Object.entries(opts).map(([k, i]) => [k, Number(i.value)])) });
      fill(out, dataTable([{ key: 'p', label: 'Person', render: x => personLine(x.person), text: x => x.person.name }, { key: 'problem', label: 'Problem' },
        { key: 'x', label: '', render: x => h('button.btn.sm', { onclick: async e => { e.stopPropagation(); await POST('/api/tools/notProblem', { person: x.person.id, ruleId: x.ruleId }); e.target.closest('tr').remove(); } }, 'Not a problem') }],
      r.problems, { onclick: x => goPerson(x.person.id), empty: 'No problems found 🎉' }));
    }
    resultModal('Problem list', h('div.col', h('details', h('summary', 'Rules and thresholds'), h('div', { style: { columns: 2 } }, rules.map(c => h('div', c))),
      h('div.row.wrap', Object.entries(opts).map(([k, i]) => h('label.small', k, ' ', i)))), h('div.row', h('button.btn.primary', { onclick: go }, 'Find problems'),
      h('button.btn', { onclick: () => import('./publish.js').then(m => m.runReport('rptProblemList', {})) }, 'Print')), out), 'x');
    go();
  },
  async notProblem() {
    const r = await POST('/api/tools/notProblemList');
    resultModal('Not-a-problem list', dataTable([{ key: 'p', label: 'Person', render: x => personLine(x.person) }, { key: 'rule', label: 'Problem' },
      { key: 'x', label: '', render: x => h('button.btn.sm', { onclick: async e => { await POST('/api/tools/deleteExclusion', { id: x.id }); e.target.closest('tr').remove(); } }, 'Restore') }], r));
  },
  async dataClean() {
    const out = h('div', { style: { display: 'flex', flexDirection: 'column', height: '56vh' } });
    let current = [], kind = 'names';
    async function load(k) {
      kind = k;
      current = await POST('/api/tools/' + (k === 'names' ? 'nameClean' : 'placeClean'));
      current.forEach(x => (x.apply = true));
      fill(out, h('div.row', h('b', `${current.length} suggestions`), h('span.grow'), h('button.btn.primary', { onclick: apply }, 'Apply checked fixes')),
        dataTable(k === 'names' ? [{ key: 'ok', label: '✓', render: x => h('input', { type: 'checkbox', checked: x.apply, onchange: e => (x.apply = e.target.checked) }) },
          { key: 'before', label: 'Before' }, { key: 'after', label: 'After' }, { key: 'issues', label: 'Issue', render: x => x.issues.join(', ') }]
          : [{ key: 'ok', label: '✓', render: x => h('input', { type: 'checkbox', checked: x.apply, onchange: e => (x.apply = e.target.checked) }) },
            { key: 'name', label: 'Place' }, { key: 'suggestion', label: 'Suggestion' }, { key: 'issue', label: 'Issue' }], current, { empty: 'Nothing to clean 🎉' }));
    }
    async function apply() {
      const fixes = current.filter(x => x.apply);
      if (!fixes.length) return;
      const r = await POST('/api/tools/' + (kind === 'names' ? 'nameCleanApply' : 'placeCleanApply'), { fixes });
      toast(`${r.fixed} fixed`); changed(); load(kind);
    }
    resultModal('DataClean', h('div.col', h('div.row', h('button.btn', { onclick: () => load('names') }, 'Names'), h('button.btn', { onclick: () => load('places') }, 'Places')), out), 'x');
    load('names');
  },
  async countyCheck() {
    const r = await POST('/api/tools/placeClean');
    resultModal('Place checker', h('div.col', h('p.muted', 'Duplicate and malformed places. Use DataClean › Places to fix them in bulk, or Places to edit individually.'),
      dataTable([{ key: 'name', label: 'Place' }, { key: 'issue', label: 'Issue' }, { key: 'suggestion', label: 'Suggestion' }], r, { empty: 'No issues found' }),
      h('button.btn.sm', { onclick: () => import('./publish.js').then(m => m.runReport('rptCountyCheck', {})) }, 'Print place check report')));
  },
  async colorCode(cb, ids) {
    const setSel = select((S.settings.colorSetNames || []).map((n, i) => [i, n]), S.settings.activeColorSet || 0);
    const colSel = select((S.settings.colorNames || []).map((n, i) => [i, n || 'Clear color']), 1);
    const p = await pick('Person');
    const who = select(ids ? [['ids', `${ids.length} people from search results`]] : [['ancestors', 'Ancestors of'], ['descendants', 'Descendants of'], ['person', 'Just this person'], ['group', 'Group'], ['all', 'Everyone']], ids ? 'ids' : 'ancestors');
    const gs = select((await GET('/api/groups')).map(g => [g.GroupID, g.Name]), '');
    const ok = await modal({ title: 'Color coding', wide: true, body: h('div.form', ...field('Color set', setSel), ...field('Color', colSel), ...field('Who', who), ...field('Person', p.el), ...field('Group', gs)),
      buttons: [{ label: 'Clear this color set', click: () => POST('/api/tools/clearColors', { colorSet: Number(setSel.value) }) }, { label: 'Cancel' },
        { label: 'Apply', primary: true, click: () => {
          const w = who.value;
          const body = { color: Number(colSel.value), colorSet: Number(setSel.value) };
          if (w === 'ids') body.ids = ids;
          else if (w === 'group') body.who = 'group:' + gs.value;
          else if (w === 'all') body.who = 'all';
          else if (w === 'person') body.ids = [p.get()];
          else body.who = `${w}:${p.get()}`;
          return POST('/api/tools/colorCode', body);
        } }] }).done;
    if (ok) { toast(ok.colored != null ? `${ok.colored} people colored` : 'Cleared'); changed(); }
  },
  async dateCalc() {
    const d1 = dateInput(''), d2 = dateInput(''), y = h('input', { type: 'number', value: 0, style: { width: '70px' } }), mo = h('input', { type: 'number', value: 0, style: { width: '70px' } }), dd = h('input', { type: 'number', value: 0, style: { width: '70px' } });
    const out = h('div.sentence', { style: { marginTop: '10px' } }, 'Result appears here');
    const show = r => { out.textContent = r.error ? r.error : r.years != null ? `${r.years} years, ${r.months} months, ${r.days} days` : r.result ? `${r.result} (${r.weekday})` : r.weekday; };
    modal({ title: 'Date calculator', wide: true, body: h('div.col', h('div.form', ...field('Date 1', d1), ...field('Date 2', d2), ...field('Years / months / days', h('div.row', y, mo, dd))),
      h('div.row.wrap', h('button.btn', { onclick: async () => show(await POST('/api/tools/dateCalc', { mode: 'between', date1: d1.value, date2: d2.value })) }, 'Difference between dates'),
        h('button.btn', { onclick: async () => show(await POST('/api/tools/dateCalc', { mode: 'add', date1: d1.value, years: y.value, months: mo.value, days: dd.value })) }, 'Date 1 + Y/M/D'),
        h('button.btn', { onclick: async () => show(await POST('/api/tools/dateCalc', { mode: 'birthFromAge', date1: d1.value, years: y.value, months: mo.value, days: dd.value })) }, 'Birth date from age at Date 1'),
        h('button.btn', { onclick: async () => show(await POST('/api/tools/dateCalc', { mode: 'weekday', date1: d1.value })) }, 'Day of week of Date 1')), out) });
  },
  async soundex() {
    const n = h('input', { placeholder: 'Surname', autofocus: true }), out = h('div', { style: { marginTop: '10px' } });
    const go = async () => { const r = await POST('/api/tools/soundex', { name: n.value }); fill(out, h('div.stat', r.code), h('div.small.muted', 'Surnames in your file with this code:'), h('div.chips', r.matches.map(m => h('span.chip', m.Surname)))); };
    n.addEventListener('input', go);
    modal({ title: 'Soundex calculator', body: h('div.no-enter', n, out) });
  },
  async calendar() {
    const now = new Date();
    let y = now.getFullYear(), m = now.getMonth();
    const yIn = h('input', { type: 'number', value: y, style: { width: '90px' } }), mSel = select(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'].map((n, i) => [i, n]), m);
    const grid = h('div');
    function draw() {
      y = Number(yIn.value); m = Number(mSel.value);
      const first = new Date(y, m, 1); first.setFullYear(y);
      const days = new Date(y, m + 1, 0); days.setFullYear(y, m + 1, 0);
      const start = first.getDay(), n = days.getDate();
      const cells = [...Array(start).fill(''), ...Array.from({ length: n }, (_, i) => i + 1)];
      const rows = [];
      for (let i = 0; i < cells.length; i += 7) rows.push(h('tr', cells.slice(i, i + 7).map(c => h('td', { style: { textAlign: 'center', padding: '8px' } }, c))));
      fill(grid, h('table.dt', h('thead', h('tr', ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => h('th', d)))), h('tbody', rows)),
        h('p.small.muted', 'Gregorian calendar (proleptic before 1582; Britain and colonies switched in 1752).'));
    }
    yIn.oninput = draw; mSel.onchange = draw;
    modal({ title: 'Perpetual calendar', body: h('div.col', h('div.row', h('button.btn.sm', { onclick: () => { mSel.value = (Number(mSel.value) + 11) % 12; if (mSel.value === '11') yIn.value--; draw(); } }, '◀'), mSel, yIn,
      h('button.btn.sm', { onclick: () => { mSel.value = (Number(mSel.value) + 1) % 12; if (mSel.value === '0') yIn.value++; draw(); } }, '▶')), grid) });
    draw();
  },
  async gazetteer() {
    const q = h('input', { placeholder: 'Place name', style: { width: '100%' }, autofocus: true }), out = h('div', { style: { marginTop: '10px' } });
    const go = async () => {
      try {
        const r = await GET('/api/geocode?q=' + encodeURIComponent(q.value));
        fill(out, dataTable([{ key: 'name', label: 'Place' }, { key: 'type', label: 'Type' }, { key: 'lat', label: 'Lat', render: x => x.lat.toFixed(4) }, { key: 'lon', label: 'Lon', render: x => x.lon.toFixed(4) },
          { key: 'x', label: '', render: x => h('a', { href: `https://www.openstreetmap.org/?mlat=${x.lat}&mlon=${x.lon}#map=11/${x.lat}/${x.lon}`, target: '_blank', rel: 'noopener' }, 'map') }], r, { filter: false }));
      } catch (e) { fail(e); }
    };
    q.addEventListener('keydown', e => e.key === 'Enter' && go());
    modal({ title: 'Gazetteer (OpenStreetMap)', wide: true, body: h('div.col.no-enter', h('div.row', q, h('button.btn.primary', { onclick: go }, 'Search')), h('p.small.muted', 'Searches OpenStreetMap Nominatim over the internet.'), out) });
  },
  async onThisDay() {
    const now = new Date();
    const mo = h('input', { type: 'number', value: now.getMonth() + 1, min: 1, max: 12, style: { width: '70px' } }), d = h('input', { type: 'number', value: now.getDate(), min: 1, max: 31, style: { width: '70px' } });
    const out = h('div');
    const go = async () => { const r = await POST('/api/tools/onThisDay', { month: Number(mo.value), day: Number(d.value) }); fill(out, dataTable([{ key: 'year', label: 'Year' }, { key: 'fact', label: 'Event' }, { key: 'who', label: 'Who' }, { key: 'place', label: 'Place' }], r, { empty: 'Nothing on this day' })); };
    modal({ title: 'On this day', wide: true, body: h('div.col', h('div.row', 'Month', mo, 'Day', d, h('button.btn.primary', { onclick: go }, 'Show')), out) });
    go();
  },
  async whoWasThere() {
    const place = h('input', { placeholder: 'Place contains…' }), f = h('input', { type: 'number', value: 1850, style: { width: '90px' } }), t = h('input', { type: 'number', value: 1900, style: { width: '90px' } });
    const out = h('div');
    const go = async () => { const r = await POST('/api/tools/whoWasThere', { place: place.value, from: Number(f.value), to: Number(t.value) }); fill(out, dataTable([{ key: 'name', label: 'Name' }, { key: 'l', label: 'Life', render: p => lifeOf(p) }], r, { onclick: p => goPerson(p.id) })); };
    modal({ title: 'Who was there', wide: true, body: h('div.col', h('div.row', place, 'from', f, 'to', t, h('button.btn.primary', { onclick: go }, 'Search')), out) });
  },
  async statistics() {
    const s = await POST('/api/tools/statistics');
    resultModal('Statistics', h('table.dt', h('tbody', Object.entries(s).map(([k, v]) => h('tr', h('td', k.replace(/([A-Z])/g, ' $1').toLowerCase()), h('td', String(v ?? '—')))))), false);
  },
  async aiPrompt() {
    const p = await pick('Person');
    const goal = h('input', { value: 'Suggest next research steps', style: { width: '100%' } });
    const ta = h('textarea', { style: { minHeight: '40vh' }, readOnly: true });
    modal({ title: 'AI prompt builder', wide: true, body: h('div.col', h('div.form', ...field('Person', p.el), ...field('Goal', goal)),
      h('div.row', h('button.btn', { onclick: async () => { ta.value = (await POST('/api/tools/aiPrompt', { person: p.get(), goal: goal.value })).prompt; } }, 'Build prompt'),
        h('button.btn', { onclick: () => { navigator.clipboard.writeText(ta.value); toast('Copied to clipboard'); } }, 'Copy')),
      ta, h('p.small.muted', 'Nothing is sent anywhere — paste the prompt into the AI assistant of your choice.')) });
  },
  async fixMedia() {
    const f = await chooseFile({ title: 'Folder to search for missing media files', folder: true });
    if (!f) return;
    const pre = await POST('/api/media/fix', { folder: f, preview: true });
    if (await confirmBox(`${pre.fixed} missing files were found in that folder. ${pre.missing.length} are still missing. Update the links?`, { ok: 'Fix links' })) {
      const r = await POST('/api/media/fix', { folder: f });
      toast(`${r.fixed} media links fixed`);
    }
  },
  async charMap(cb) {
    const chars = 'ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿĀāĂăĄąĆćČčĎďĐđĒēĘęĚěĞğĪīİıŁłŃńŇňŌōŐőŒœŘřŚśŞşŠšŢţŤťŪūŮůŰűŸŹźŻżŽž†‡§¶©°±×÷½¼¾…–—‘’“”«»€£¥';
    modal({ title: 'Character map', body: h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(16, 1fr)', gap: '3px' } },
      [...chars].map(c => h('button.btn.sm', { onclick: () => { cb ? cb(c) : navigator.clipboard.writeText(c); toast(cb ? 'Inserted ' + c : 'Copied ' + c); } }, c))) });
  },
  async database() {
    const out = h('pre.small', { style: { whiteSpace: 'pre-wrap' } });
    const run = async a => { out.textContent = 'Working…'; const r = await POST('/api/tools/db', { action: a }); out.textContent = r.result.join('\n'); changed(); };
    modal({ title: 'Database tools', wide: true, body: h('div.col', h('div.row.wrap',
      h('button.btn', { onclick: () => run('integrity') }, 'Test integrity'), h('button.btn', { onclick: () => run('compact') }, 'Compact'),
      h('button.btn', { onclick: () => run('reindex') }, 'Rebuild indexes'), h('button.btn', { onclick: () => run('phantoms') }, 'Clean phantom records'),
      h('button.btn', { onclick: async () => { if (await confirmBox('Delete all places not used by any fact?')) run('unusedPlaces'); } }, 'Delete unused places'),
      h('button.btn', { onclick: async () => { if (await confirmBox('Delete all sources that have no citations?')) run('unusedSources'); } }, 'Delete unused sources')), out) });
  },
  async compare() {
    const p = await chooseFile({ title: 'Compare with which file?', ext: '.rmtree,.rmgc' });
    if (!p) return;
    const r = await POST('/api/files/compare', { path: p });
    const sec = (title, rows) => [h('h4', `${title} (${rows.length})`), h('div.list', { style: { maxHeight: '22vh', overflow: 'auto' } }, rows.map(x => h('div', personLine(x))))];
    resultModal('Compare files', h('div.col', h('p', `${r.matched} people matched by name and birth year.`), sec('Only in this file', r.onlyA), sec('Only in the other file', r.onlyB),
      h('h4', `Matched but different (${r.different.length})`), h('div.list', { style: { maxHeight: '30vh', overflow: 'auto' } }, r.different.map(x => h('div', { style: { flexDirection: 'column', alignItems: 'flex-start' } },
        h('b', x.a.name), x.onlyA.map(f => h('div.small', '− here only: ', f.filter(Boolean).join(' '))), x.onlyB.map(f => h('div.small', '+ other only: ', f.filter(Boolean).join(' ')))))), 'x'));
  },
  async importlists() {
    const p = await chooseFile({ title: 'Import lists from which file?', ext: '.rmtree,.rmgc' });
    if (!p) return;
    const opts = { factTypes: checkbox('Fact types', true), templates: checkbox('Source templates', true), places: checkbox('Places', false), sources: checkbox('Sources and repositories', false), fanTypes: checkbox('Association types', true), roles: checkbox('Roles', true) };
    const r = await modal({ title: 'Import lists', body: h('div.col', h('p.mono.small', p), ...Object.values(opts)),
      buttons: [{ label: 'Cancel' }, { label: 'Import', primary: true, click: () => POST('/api/files/importLists', { path: p, what: Object.entries(opts).filter(([, c]) => c.input.checked).map(([k]) => k) }) }] }).done;
    if (r) { toast('Imported: ' + Object.entries(r).map(([k, v]) => `${v} ${k}`).join(', ')); const a = await import('./app.js'); a.refreshFile(); }
  },
};

// Side-by-side compare + merge (used by duplicate search and manual merge)
async function compareMerge(a, b) {
  const [pa, pb] = await Promise.all([GET(`/api/person/${a}`), GET(`/api/person/${b}`)]);
  const col = d => h('div', { style: { flex: 1, minWidth: 0 } }, h('h3', d.summary.name, ' ', h('span.muted.small', `#${d.summary.id}`)),
    h('div.small.muted', S.meta.sex[d.summary.sex]), d.facts.map(f => h('div.fact', h('span.ft', f.typeName), h('span', [f.date, f.place, f.description].filter(Boolean).join(', ')))),
    d.parents.map(p => h('div.small', 'Parents: ', [p.father?.name, p.mother?.name].filter(Boolean).join(' & '))),
    d.spouses.map(s => h('div.small', 'Spouse: ', s.spouse?.name || '?', ` (${s.children.length} children)`)));
  const keep = select([[a, `Keep #${a} (${pa.summary.name}) as primary`], [b, `Keep #${b} (${pb.summary.name}) as primary`]], a);
  const r = await modal({ title: 'Compare and merge', xwide: true, body: h('div.col', h('div.row', { style: { alignItems: 'flex-start', gap: '20px' } }, col(pa), col(pb)), keep,
    h('p.small.muted', 'Merging moves all names, facts, families, citations and media of the other person onto the kept person. Exact duplicate facts are combined.')),
  buttons: [{ label: 'Not a duplicate', click: () => POST('/api/tools/notDuplicate', { a, b }) }, { label: 'Cancel' },
    { label: 'Merge', primary: true, click: () => POST('/api/tools/merge', { keep: Number(keep.value), drop: Number(keep.value) === a ? b : a }) }] }).done;
  if (r) { toast('Done'); changed(); }
  return r;
}
