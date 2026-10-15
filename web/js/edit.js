// Edit Person / Add Person / Edit Family / citations / media / tasks / witnesses.
import { GET, POST, PUT, DEL, h, clear, modal, toast, fail, confirmBox, select, checkbox, field, dateInput, placeInput, choosePerson, chooseFile, personLine, lifeOf, readFileAs, debounce, invalidatePlaces, promptBox, put, fill, safeUrl } from './ui.js';
import { S, emit, setPerson, goPerson } from './app.js';

const changed = () => emit('changed');
const OT = { person: 0, family: 1, event: 2, source: 3, citation: 4, place: 5, task: 6, name: 7 };

// ================================================================ add person
export async function addPerson({ rel = '', of = 0, sex = null, family = 0 } = {}) {
  let ofName = '';
  if (of) ofName = (await GET(`/api/person/${of}`)).summary.name;
  const relLabel = { spouse: 'Add spouse to', child: 'Add child to', father: 'Add father of', mother: 'Add mother of', parent: 'Add parent of' }[rel];
  const given = h('input', { style: { width: '100%' }, autofocus: true });
  let defaultSurname = '';
  if (of && (rel === 'child' || rel === 'father')) defaultSurname = (await GET(`/api/person/${of}`)).summary.surname;
  const surname = h('input', { value: defaultSurname, style: { width: '100%' } });
  const prefix = h('input', { style: { width: '90px' }, placeholder: 'Prefix' });
  const suffix = h('input', { style: { width: '90px' }, placeholder: 'Suffix' });
  const sexSel = select([[0, 'Male'], [1, 'Female'], [2, 'Unknown']], sex ?? (rel === 'father' ? 0 : rel === 'mother' ? 1 : 2));
  const bd = dateInput(), bp = placeInput(), dd = dateInput(), dp = placeInput();
  const living = checkbox('Living', false);
  const rf = select(Object.entries(S.meta.childRel), 0), rm = select(Object.entries(S.meta.childRel), 0);
  const dupBox = h('div.small');
  const checkDup = debounce(async () => {
    if (!surname.value || !given.value) { clear(dupBox); return; }
    const r = await GET('/api/people?limit=8&q=' + encodeURIComponent(surname.value + ', ' + given.value.split(' ')[0]));
    clear(dupBox);
    if (r.rows.length) put(dupBox, h('div', { style: { color: 'var(--warn)' } }, '⚠ Possible existing match — click to use instead:'),
      r.rows.map(x => h('div', h('a', { href: '#', onclick: e => { e.preventDefault(); m.close({ existing: x[0] }); } }, `${x[2]} ${x[1]} (${x[4] || '?'}–${x[5] || ''}) [${x[0]}]`))));
  }, 400);
  given.addEventListener('input', checkDup); surname.addEventListener('input', checkDup);
  const m = modal({
    title: relLabel ? `${relLabel} ${ofName}` : 'Add person', wide: true,
    body: h('div.form',
      ...field('Given name(s)', given), ...field('Surname', surname), ...field('Prefix / suffix', h('div.row', prefix, suffix)),
      ...field('Sex', sexSel), ...field('Birth date', bd), ...field('Birth place', bp), ...field('Death date', dd), ...field('Death place', dp),
      ...field('', living),
      rel === 'child' ? field('Relationship to father', rf) : [], rel === 'child' ? field('Relationship to mother', rm) : [],
      h('div.full', dupBox)),
    buttons: [
      of ? { label: 'Select existing person…', click: async () => { const id = await choosePerson({ title: 'Select existing person', exclude: [of] }); return id ? { existing: id } : false; } } : null,
      { label: 'Cancel' },
      { label: 'Add', primary: true, click: () => ({ given: given.value.trim(), surname: surname.value.trim(), prefix: prefix.value, suffix: suffix.value, sex: Number(sexSel.value),
        birthDate: bd.value, birthPlace: bp.value, deathDate: dd.value, deathPlace: dp.value, living: living.input.checked }) },
    ].filter(Boolean),
  });
  const v = await m.done;
  if (!v) return null;
  try {
    const r = await POST('/api/person', { ...v, rel, of, family, relFather: Number(rf.value), relMother: Number(rm.value) });
    invalidatePlaces();
    changed();
    setPerson(r.id);
    toast(v.existing ? 'Linked' : 'Person added');
    return r.id;
  } catch (e) { fail(e); }
}

export async function addParents(pid) {
  const d = await GET(`/api/person/${pid}`);
  const choice = await modal({ title: `Add parents for ${d.summary.name}`, body: h('div.col',
    h('p.muted', 'Add a new father and/or mother, or link an existing couple.')),
  buttons: [{ label: 'Cancel' }, { label: 'Link existing couple…', value: 'couple' }, { label: 'Add mother', value: 'mother' }, { label: 'Add father', primary: true, value: 'father' }] }).done;
  if (choice === 'father' || choice === 'mother') return addPerson({ rel: choice, of: pid, sex: choice === 'father' ? 0 : 1 });
  if (choice === 'couple') {
    const fa = await choosePerson({ title: 'Choose the father (Esc to skip)' });
    const mo = await choosePerson({ title: 'Choose the mother (Esc to skip)' });
    if (!fa && !mo) return;
    await POST('/api/family/parents', { child: pid, father: fa || 0, mother: mo || 0 }).catch(fail);
    changed();
  }
}

export async function deletePerson(pid) {
  const d = await GET(`/api/person/${pid}`);
  if (!await confirmBox(`Delete ${d.summary.name} [${pid}] and all of their facts, names, and links? This cannot be undone.`, { danger: true, ok: 'Delete person' })) return;
  await DEL(`/api/person/${pid}`);
  const next = d.parents[0]?.father?.id || d.parents[0]?.mother?.id || d.spouses[0]?.spouse?.id || d.siblings[0]?.id;
  changed();
  if (next) setPerson(next);
  toast('Deleted');
}

// ================================================================ edit person
export async function editPerson(pid, tab = 'facts', focusFact = null) {
  if (!pid) return toast('No person selected');
  let d;
  const tabs = [['facts', 'Facts'], ['names', 'Names'], ['notes', 'Notes'], ['sources', 'Sources'], ['media', 'Media'], ['tasks', 'Tasks'],
    ['fans', 'Associations'], ['dna', 'DNA'], ['health', 'Health'], ['webtags', 'WebTags'], ['groups', 'Groups'], ['addresses', 'Addresses'], ['flags', 'Person']];
  const tabBar = h('div.tabs', { style: { flexWrap: 'wrap' } });
  const body = h('div', { style: { height: '100%', minHeight: 0 } });
  const m = modal({ title: 'Edit person', xwide: true, body: h('div.col', { style: { height: '100%', gap: 0 } }, tabBar, h('div', { style: { flex: 1, minHeight: 0, borderTop: '1px solid var(--line)' } }, body)),
    buttons: [{ label: 'Delete person…', danger: true, click: async () => { await deletePerson(pid); } }, { label: 'Close', primary: true }], onclose: () => changed() });
  m.body.style.padding = '0';
  async function load() { d = await GET(`/api/person/${pid}`); m.title.textContent = `Edit person — ${d.summary.name} [${pid}]`; }
  async function show(t, focus) {
    tab = t;
    tabBar.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.t === t));
    await load();
    clear(body);
    try { await ({ facts: factsTab, names: namesTab, notes: notesTab, sources: sourcesTab, media: mediaTab, tasks: tasksTab, fans: fansTab, dna: dnaTab, health: healthTab, webtags: webtagsTab, groups: groupsTab, addresses: addressesTab, flags: flagsTab }[t])(body, focus); }
    catch (e) { fail(e); }
  }
  for (const [k, l] of tabs) put(tabBar, h('button', { 'data-t': k, onclick: () => show(k) }, l));

  // ---- facts tab
  async function factsTab(el, focus) {
    const list = h('div.flist');
    const detail = h('div.fdetail');
    put(el, h('div.editp', { style: { height: 'calc(90vh - 150px)' } }, list, detail));
    const primary = d.names.find(n => n.IsPrimary) || d.names[0] || {};
    function drawList(sel) {
      clear(list);
      put(list, h('div.toolbar', h('b', 'Facts'), h('span.grow'), h('button.btn.sm.primary', { onclick: addFact }, '+ Add fact'),
        h('button.btn.sm', { onclick: shareFact, title: 'Share an existing fact from another person (witness)' }, 'Share…')));
      put(list, h('div.fitem' + (sel === 'name' ? '.sel' : ''), { onclick: () => { drawList('name'); nameEditor(detail, primary); } },
        h('span.t', 'Name'), h('span.badges'), h('span.d', `${primary.Given || ''} ${primary.Surname || ''} ${primary.Suffix || ''}`)));
      put(list, h('div.fitem' + (sel === 'sex' ? '.sel' : ''), { onclick: () => { drawList('sex'); sexEditor(detail); } }, h('span.t', 'Sex'), h('span'), h('span.d', S.meta.sex[d.person.Sex])));
      for (const f of d.facts) {
        put(list, h('div.fitem' + (sel === f.id ? '.sel' : ''), { onclick: () => { drawList(f.id); f.shared ? sharedEditor(detail, f) : factEditor(detail, f.id); } },
          h('span.t', f.typeName, f.shared ? h('span.muted.small', ` (${f.shared.role})`) : ''),
          h('span.badges', f.citations ? h('span.badge', `S${f.citations}`) : '', f.media ? h('span.badge', `M${f.media}`) : '', f.witnesses ? h('span.badge', `W${f.witnesses}`) : '',
            f.private ? h('span.badge.warn', 'P') : '', f.note ? h('span.badge', 'N') : ''),
          h('span.d', [f.date, f.placeDetails, f.place, f.description].filter(Boolean).join(' · ') || '—')));
      }
    }
    async function addFact() {
      const types = S.meta.factTypes.filter(t => t.OwnerType === 0);
      const sel = select(types.map(t => [t.FactTypeID, t.Name]), 26, { size: 14, style: { width: '100%' } });
      const q = h('input', { type: 'search', placeholder: 'Filter fact types', style: { width: '100%' }, autofocus: true,
        oninput: e => { clear(sel); for (const t of types.filter(t => t.Name.toLowerCase().includes(e.target.value.toLowerCase()))) put(sel, h('option', { value: t.FactTypeID }, t.Name)); sel.selectedIndex = 0; } });
      sel.addEventListener('dblclick', () => mm.el.querySelector('footer .btn.primary').click());
      const mm = modal({ title: 'Add fact', body: h('div.col', q, sel, h('button.btn.sm', { onclick: () => { mm.close(); import('./lists.js').then(x => x.factTypeManager()); } }, 'Manage fact types…')),
        buttons: [{ label: 'Cancel' }, { label: 'Add', primary: true, click: () => Number(sel.value) }] });
      const ft = await mm.done;
      if (!ft) return;
      const r = await POST('/api/fact', { ownerType: 0, ownerId: pid, type: ft });
      await load(); drawList(r.id); factEditor(detail, r.id);
    }
    async function shareFact() {
      const other = await choosePerson({ title: 'Whose fact is being shared?', exclude: [pid] });
      if (!other) return;
      const od = await GET(`/api/person/${other}`);
      const own = [...od.facts.filter(f => !f.shared), ...od.spouses.flatMap(f => f.facts)];
      const fsel = select(own.map(f => [f.id, `${f.typeName} ${f.date} ${f.place}`]), own[0]?.id, { size: 10, style: { width: '100%' } });
      const fid = await modal({ title: `Share a fact of ${od.summary.name}`, body: fsel, buttons: [{ label: 'Cancel' }, { label: 'Next', primary: true, click: () => Number(fsel.value) }] }).done;
      if (!fid) return;
      const fd = await GET(`/api/fact/${fid}`);
      const role = select([[0, 'Witness'], ...fd.roles.map(r => [r.RoleID, r.RoleName])], 0);
      const ok = await modal({ title: 'Role', body: h('div.form', ...field('Role of ' + d.summary.name, role)), buttons: [{ label: 'Cancel' }, { label: 'Share', primary: true, value: true }] }).done;
      if (!ok) return;
      await POST('/api/witness', { eventId: fid, personId: pid, role: Number(role.value) });
      await load(); drawList();
    }
    function sexEditor(el) {
      const s = select([[0, 'Male'], [1, 'Female'], [2, 'Unknown']], d.person.Sex);
      fill(el, h('h3', 'Sex'), h('div.form', ...field('Sex', s)), h('div.row', { style: { marginTop: '10px' } },
        h('button.btn.primary', { onclick: async () => { await PUT(`/api/person/${pid}`, { Sex: Number(s.value) }); await load(); drawList('sex'); toast('Saved'); } }, 'Save')));
    }
    async function sharedEditor(el, f) {
      const fd = await GET(`/api/fact/${f.id}`);
      const w = fd.witnesses.find(x => x.WitnessID === f.shared.witnessId);
      const role = select([[0, 'Witness'], ...fd.roles.map(r => [r.RoleID, r.RoleName])], w.Role);
      const sent = h('textarea', { value: w.Sentence || '', placeholder: 'Leave blank to use the role sentence' });
      const note = h('textarea', { value: w.Note || '' });
      fill(el, h('h3', `${f.typeName} of ${f.shared.principal}`), h('p.muted', [f.date, f.place].filter(Boolean).join(', ')),
        h('div.form', ...field('Role', role), ...field('Sentence', sent, { hint: w.sentencePreview }), ...field('Note', note)),
        h('div.row', { style: { marginTop: '10px' } },
          h('button.btn.primary', { onclick: async () => { await PUT(`/api/witness/${w.WitnessID}`, { Role: Number(role.value), Sentence: sent.value, Note: note.value }); toast('Saved'); } }, 'Save'),
          h('button.btn', { onclick: () => { m.close(); goPerson(fd.fact.OwnerType === 0 ? fd.fact.OwnerID : pid); } }, 'Go to principal'),
          h('button.btn.danger.right', { onclick: async () => { await DEL(`/api/witness/${w.WitnessID}`); await load(); drawList(); clear(el); } }, 'Remove sharing')));
    }
    drawList(focus || null);
    if (focus) {
      const f = d.facts.find(x => x.id === focus);
      if (f) f.shared ? sharedEditor(detail, f) : factEditor(detail, focus);
    } else nameEditor(detail, primary), drawList('name');
    async function factEditor(el, eid) { await editFactPanel(el, eid, { onChange: async () => { await load(); drawList(eid); }, onDelete: async () => { await load(); drawList(); clear(el); } }); }
  }

  function nameEditor(el, n) {
    const given = h('input', { value: n.Given || '', style: { width: '100%' } });
    const sur = h('input', { value: n.Surname || '', style: { width: '100%' } });
    const pre = h('input', { value: n.Prefix || '' }), suf = h('input', { value: n.Suffix || '' }), nick = h('input', { value: n.Nickname || '' });
    const typ = select(Object.entries(S.meta.nameTypes).map(([k, v]) => [k, v || '(none)']), n.NameType || 0);
    const date = dateInput(n.Date && n.Date !== '.' ? '' : '');
    if (n.Date && n.Date !== '.') GET('/api/date/parse?text=' + encodeURIComponent(n.Date)).then(r => (date.value = r.display));
    const note = h('textarea', { value: n.Note || '' });
    const priv = checkbox('Private', n.IsPrivate), prim = checkbox('Primary name', n.IsPrimary);
    const proof = select(Object.entries(S.meta.proof).map(([k, v]) => [k, v || '(none)']), n.Proof || 0);
    const cites = h('div');
    fill(el, h('h3', n.IsPrimary ? 'Primary name' : 'Alternate name'),
      h('div.form', ...field('Given', given), ...field('Surname', sur), ...field('Prefix', pre), ...field('Suffix', suf), ...field('Nickname', nick),
        ...field('Name type', typ), ...field('Date', date), ...field('Proof', proof), ...field('', h('div.row', prim, priv)), ...field('Note', note)),
      h('div.row', { style: { margin: '10px 0' } }, h('button.btn.primary', { onclick: async () => {
        await POST('/api/name', { NameID: n.NameID, OwnerID: pid, Given: given.value, Surname: sur.value, Prefix: pre.value, Suffix: suf.value, Nickname: nick.value,
          NameType: Number(typ.value), Date: date.value, Note: note.value, IsPrivate: priv.input.checked ? 1 : 0, IsPrimary: prim.input.checked ? 1 : 0, Proof: Number(proof.value) });
        toast('Saved'); show(tab);
      } }, 'Save name')), n.NameID ? cites : null);
    if (n.NameID) citationsPanel(cites, OT.name, n.NameID);
  }

  // ---- names tab
  async function namesTab(el) {
    el.style.padding = '14px';
    const detail = h('div', { style: { marginTop: '14px' } });
    put(el, h('div.row', h('b', 'All names'), h('button.btn.sm.right', { onclick: () => nameEditor(detail, { OwnerID: pid, NameType: 1, IsPrimary: 0 }) }, '+ Add alternate name')),
      h('div.list', { style: { marginTop: '8px' } }, d.names.map(n => h('div', { style: { cursor: 'pointer' }, onclick: () => nameEditor(detail, n) },
        n.IsPrimary ? h('b', 'Primary') : h('span.muted', S.meta.nameTypes[n.NameType] || 'Alternate'),
        `${n.Prefix || ''} ${n.Given || ''} ${n.Surname || ''} ${n.Suffix || ''}`, n.Nickname ? h('span.muted', ` "${n.Nickname}"`) : '',
        !n.IsPrimary ? h('button.btn.sm.danger.right', { onclick: async e => { e.stopPropagation(); if (await confirmBox('Delete this name?')) { await DEL(`/api/name/${n.NameID}`); show('names'); } } }, 'Delete') : ''))),
      detail);
  }

  // ---- notes
  async function notesTab(el) {
    el.style.padding = '14px';
    put(el, noteEditor(d.person.Note || '', async v => { await PUT(`/api/person/${pid}`, { Note: v }); toast('Note saved'); }, 'General note for this person'));
  }
  // ---- sources (person-level)
  async function sourcesTab(el) {
    el.style.padding = '14px';
    put(el, h('p.muted', 'Citations attached to the person as a whole. Fact citations are on each fact (Facts tab).'));
    const c = h('div'); put(el, c); citationsPanel(c, OT.person, pid);
    const fc = d.facts.filter(f => f.citations);
    if (fc.length) put(el, h('h4', 'Facts with citations'), h('div.list', fc.map(f => h('div', f.typeName, ' ', h('span.muted', f.date), h('span.badge.right', f.citations)))));
  }
  async function mediaTab(el) { el.style.padding = '14px'; mediaPanel(el, OT.person, pid); }
  async function tasksTab(el) { el.style.padding = '14px'; tasksPanel(el, OT.person, pid); }
  async function webtagsTab(el) { el.style.padding = '14px'; webtagsPanel(el, OT.person, pid); }

  // ---- associations
  async function fansTab(el) {
    el.style.padding = '14px';
    const types = await GET('/api/list/fanTypes');
    put(el, h('div.row', h('b', 'Associations (friends, associates, neighbors)'), h('button.btn.sm.right', { onclick: () => edit({}) }, '+ Add association')),
      h('div.list', { style: { marginTop: '8px' } }, d.fans.length ? d.fans.map(a => h('div', { style: { cursor: 'pointer' }, onclick: () => edit(a) },
        h('b', a.theirRole || a.TypeName), personLine(a.other), h('span.muted.small', a.dateText), h('span.muted.small.right', a.Description || ''))) : h('div.muted', 'None')));
    async function edit(a) {
      let other = a.other?.id || 0;
      const who = h('span', a.other ? a.other.name : h('span.muted', 'nobody selected'));
      const pick = h('button.btn.sm', { onclick: async () => { const x = await choosePerson({ title: 'Associated person', exclude: [pid] }); if (x) { other = x; who.textContent = (await GET(`/api/person/${x}`)).summary.name; } } }, 'Choose…');
      const typeSel = select(types.flatMap(t => [[`${t.FANTypeID}:1`, `${t.Name}: ${d.summary.name} is ${t.Role1}`], ...(t.Role1 !== t.Role2 ? [[`${t.FANTypeID}:2`, `${t.Name}: ${d.summary.name} is ${t.Role2}`]] : [])]),
        a.FanID ? `${a.FanTypeID}:${a.ID1 === pid ? 1 : 2}` : '');
      const date = dateInput(a.dateText || ''), place = placeInput(a.place || '');
      const desc = h('input', { value: a.Description || '', style: { width: '100%' } }), note = h('textarea', { value: a.Note || '' });
      const r = await modal({ title: a.FanID ? 'Edit association' : 'Add association', wide: true, body: h('div.form',
        ...field('Person', h('div.row', who, pick)), ...field('Type', typeSel), ...field('Date', date), ...field('Place', place), ...field('Description', desc), ...field('Note', note),
        ...field('', h('button.btn.sm', { onclick: () => import('./lists.js').then(x => x.fanTypeManager()) }, 'Manage association types…'))),
      buttons: [a.FanID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/fan/${a.FanID}`); return 'deleted'; } } : null, { label: 'Cancel' },
        { label: 'Save', primary: true, click: async () => {
          if (!other) throw new Error('Choose a person');
          const [tid, side] = typeSel.value.split(':').map(Number);
          await POST('/api/fan', { FanID: a.FanID, ID1: side === 1 ? pid : other, ID2: side === 1 ? other : pid, FanTypeID: tid, date: date.value, place: place.value, Description: desc.value, Note: note.value });
        } }].filter(Boolean) }).done;
      if (r) show('fans');
    }
  }

  // ---- DNA
  async function dnaTab(el) {
    el.style.padding = '14px';
    put(el, h('div.row', h('b', 'DNA matches'), h('button.btn.sm.right', { onclick: () => edit({}) }, '+ Add DNA match')),
      d.dna.length ? h('table.dt', { style: { marginTop: '8px' } }, h('thead', h('tr', ['Match', 'Shared cM', '%', 'Segs', 'Largest', 'Known relationship', 'Predicted', 'Company'].map(x => h('th', x)))),
        h('tbody', d.dna.map(x => h('tr.click', { onclick: () => edit(x) }, h('td', x.other?.name || x.Label2), h('td', x.SharedCM), h('td', x.SharedPercent), h('td', x.SharedSegs), h('td', x.LargeSeg),
          h('td', x.relationship), h('td', x.predicted), h('td', S.meta.dnaProviders[x.DNAProvider] || ''))))) : h('p.muted', 'No DNA matches recorded.'));
    async function edit(x) {
      let other = x.other?.id || 0;
      const who = h('span', x.other ? x.other.name : h('span.muted', 'nobody selected'));
      const pick = h('button.btn.sm', { onclick: async () => { const y = await choosePerson({ title: 'DNA match (person in your file)', exclude: [pid], allowNew: false }); if (y) { other = y; who.textContent = (await GET(`/api/person/${y}`)).summary.name; } } }, 'Choose…');
      const num = (v, step = '0.1') => h('input', { type: 'number', step, value: v ?? '', style: { width: '120px' } });
      const cm = num(x.SharedCM), pct = num(x.SharedPercent, '0.01'), segs = num(x.SharedSegs, '1'), large = num(x.LargeSeg);
      const prov = select(Object.entries(S.meta.dnaProviders), x.DNAProvider || 0), date = h('input', { value: x.Date || '' });
      const note = h('textarea', { value: x.Note || '' }), verified = checkbox('Verified', x.Verified);
      let anc = x.CommonAnc || 0;
      const ancLbl = h('span', anc ? '#' + anc : h('span.muted', 'none'));
      const r = await modal({ title: 'DNA match', wide: true, body: h('div.form', ...field('Match', h('div.row', who, pick)), ...field('Company', prov), ...field('Test date', date),
        ...field('Shared cM', cm), ...field('Shared %', pct), ...field('Segments', segs), ...field('Largest segment (cM)', large),
        ...field('Common ancestor', h('div.row', ancLbl, h('button.btn.sm', { onclick: async () => { const y = await choosePerson({ title: 'Common ancestor' }); if (y) { anc = y; ancLbl.textContent = '#' + y; } } }, 'Choose…'))),
        ...field('', verified), ...field('Note', note)),
      buttons: [x.RecID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/dna/${x.RecID}`); return 'x'; } } : null, { label: 'Cancel' },
        { label: 'Save', primary: true, click: async () => {
          if (!other) throw new Error('Choose the matching person (add them to your file first if needed)');
          await POST('/api/dna', { RecID: x.RecID, ID1: pid, ID2: other, Label1: '', Label2: '', DNAProvider: Number(prov.value), SharedCM: Number(cm.value) || 0, SharedPercent: Number(pct.value) || 0,
            SharedSegs: Number(segs.value) || 0, LargeSeg: Number(large.value) || 0, Date: date.value, CommonAnc: anc, CommonAncType: 0, Verified: verified.input.checked ? 1 : 0, Note: note.value, Relate1: 0, Relate2: 0 });
        } }].filter(Boolean) }).done;
      if (r) show('dna');
    }
  }

  // ---- health
  async function healthTab(el) {
    el.style.padding = '14px';
    put(el, h('div.row', h('b', 'Health conditions'), h('button.btn.sm.right', { onclick: () => edit({}) }, '+ Add condition')),
      h('div.list', { style: { marginTop: '8px' } }, d.health.length ? d.health.map(x => h('div', { style: { cursor: 'pointer' }, onclick: () => edit(x) },
        h('b', S.meta.health[x.Condition] || 'Other'), x.SubCondition || '', h('span.muted.small.right', x.Note || ''))) : h('div.muted', 'None recorded')));
    async function edit(x) {
      const cond = select(S.meta.health.map((c, i) => [i, c]), x.Condition ?? 0), sub = h('input', { value: x.SubCondition || '', style: { width: '100%' } });
      const note = h('textarea', { value: x.Note || '' });
      const r = await modal({ title: 'Health condition', body: h('div.form', ...field('Condition', cond), ...field('Detail', sub), ...field('Note', note)),
        buttons: [x.RecID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/health/${x.RecID}`); return 'x'; } } : null, { label: 'Cancel' },
          { label: 'Save', primary: true, click: () => POST('/api/health', { RecID: x.RecID, OwnerID: pid, Condition: Number(cond.value), SubCondition: sub.value, Note: note.value, Date: 0 }) }].filter(Boolean) }).done;
      if (r) show('health');
    }
  }

  // ---- groups
  async function groupsTab(el) {
    el.style.padding = '14px';
    const all = await GET('/api/groups');
    const mine = new Set(d.groups.map(g => g.GroupID));
    put(el, h('div.row', h('b', 'Groups this person belongs to'), h('button.btn.sm.right', { onclick: async () => {
      const n = await promptBox('New group', 'Group name');
      if (n) { await POST('/api/group', { Name: n, add: [pid] }); show('groups'); }
    } }, '+ New group with this person')),
    h('div.list', { style: { marginTop: '8px' } }, all.length ? all.map(g => { const c = checkbox(`${g.Name} (${g.count})`, mine.has(g.GroupID), { onchange: async e => {
      await POST('/api/group', { GroupID: g.GroupID, Name: g.Name, Description: g.Description || '', [e.target.checked ? 'add' : 'remove']: [pid] }); toast('Updated');
    } }); return h('div', c); }) : h('div.muted', 'No groups yet')));
  }

  // ---- addresses
  async function addressesTab(el) {
    el.style.padding = '14px';
    put(el, h('div.row', h('b', 'Addresses'), h('button.btn.sm.right', { onclick: async () => {
      const id = await import('./lists.js').then(x => x.editAddress({ AddressType: 0, Name: d.summary.name }));
      if (id) { await POST('/api/addressLink', { ownerType: 0, ownerId: pid, addressId: id }); show('addresses'); }
    } }, '+ Add address'), h('button.btn.sm', { onclick: async () => {
      const all = await GET('/api/list/addresses?AddressType=0');
      const sel = select(all.map(a => [a.AddressID, a.Name + ' — ' + [a.City, a.State].filter(Boolean).join(', ')]), '', { size: 10, style: { width: '100%' } });
      const id = await modal({ title: 'Link existing address', body: sel, buttons: [{ label: 'Cancel' }, { label: 'Link', primary: true, click: () => Number(sel.value) }] }).done;
      if (id) { await POST('/api/addressLink', { ownerType: 0, ownerId: pid, addressId: id }); show('addresses'); }
    } }, 'Link existing…')),
    h('div.list', { style: { marginTop: '8px' } }, d.addresses.length ? d.addresses.map(a => h('div', h('b', a.Name), [a.Street1, a.City, a.State, a.Country].filter(Boolean).join(', '),
      h('span.muted.small', [a.Phone1, a.Email].filter(Boolean).join(' · ')),
      h('button.btn.sm.right', { onclick: async () => { await POST('/api/addressLink', { delete: a.LinkID }); show('addresses'); } }, 'Unlink'))) : h('div.muted', 'None')));
  }

  // ---- person flags, colors, living, proof
  async function flagsTab(el) {
    el.style.padding = '14px';
    const p = d.person;
    const living = checkbox('Living', p.Living), priv = checkbox('Private (exclude from reports/exports when chosen)', p.IsPrivate), bm = checkbox('Bookmarked', p.Bookmark);
    const proof = select(Object.entries(S.meta.proof).map(([k, v]) => [k, v || '(none)']), p.Proof || 0);
    const names = S.settings.colorNames || [];
    const colorSels = [];
    for (let i = 0; i < 10; i++) {
      const col = i ? `Color${i}` : 'Color';
      colorSels.push([col, select(names.map((n, j) => [j, n || '(none)']), p[col] || 0)]);
    }
    put(el, h('div.form', ...field('', h('div.col', living, priv, bm)), ...field('Proof', proof),
      ...colorSels.flatMap(([col, s], i) => field((S.settings.colorSetNames || [])[i] || `Color set ${i + 1}`, s)),
      ...field('Unique ID', h('span.mono.small', p.UniqueID || '')), ...field('Record number', String(p.PersonID))),
    h('div.row', { style: { marginTop: '12px' } }, h('button.btn.primary', { onclick: async () => {
      await PUT(`/api/person/${pid}`, Object.assign({ Living: living.input.checked ? 1 : 0, IsPrivate: priv.input.checked ? 1 : 0, Bookmark: bm.input.checked ? 1 : 0, Proof: Number(proof.value) },
        Object.fromEntries(colorSels.map(([c, s]) => [c, Number(s.value)]))));
      toast('Saved');
    } }, 'Save')));
  }

  show(tab, focusFact);
  return m.done;
}

// ================================================================ fact editor (also used by family edit)
export async function editFactPanel(el, eid, { onChange, onDelete } = {}) {
  const d = await GET(`/api/fact/${eid}`);
  const f = d.fact, t = d.type;
  const types = S.meta.factTypes.filter(x => x.OwnerType === t.OwnerType);
  const typeSel = select(types.map(x => [x.FactTypeID, x.Name]), f.EventType);
  const date = dateInput(d.dateText), place = placeInput(d.place), details = h('input', { value: d.placeDetails, style: { width: '100%' }, placeholder: 'Cemetery, church, hospital, street address…' });
  const desc = h('input', { value: f.Details || '', style: { width: '100%' } });
  const note = h('textarea', { value: f.Note || '' });
  const prim = checkbox('Primary', f.IsPrimary), priv = checkbox('Private', f.IsPrivate);
  const proof = select(Object.entries(S.meta.proof).map(([k, v]) => [k, v || '(none)']), f.Proof || 0);
  const sentPrev = h('div.sentence', d.sentence);
  const custom = h('textarea', { value: f.Sentence || '', placeholder: 'Custom sentence (leave blank for the fact type sentence)', style: { minHeight: '50px' } });
  const previewCustom = debounce(async () => {
    const r = await POST('/api/sentence/preview', { eventId: eid, template: custom.value || d.templateSentence });
    sentPrev.textContent = r.text;
  }, 300);
  custom.addEventListener('input', previewCustom);
  const cites = h('div'), media = h('div'), wit = h('div'), tasks = h('div');
  const save = async () => {
    await PUT(`/api/fact/${eid}`, { EventType: Number(typeSel.value), Date: date.value, Place: place.value, PlaceDetails: details.value, Details: desc.value, Note: note.value,
      Sentence: custom.value, IsPrimary: prim.input.checked ? 1 : 0, IsPrivate: priv.input.checked ? 1 : 0, Proof: Number(proof.value) });
    invalidatePlaces();
    toast('Fact saved');
    const nd = await GET(`/api/fact/${eid}`);
    sentPrev.textContent = nd.sentence;
    onChange && onChange();
  };
  fill(el, 
    h('div.row', h('h3', { style: { margin: '0' } }, t.Name), h('span.muted.small', `#${eid}`), h('div.right.row',
      h('button.btn.primary', { onclick: save }, 'Save'),
      h('button.btn.danger', { onclick: async () => { if (await confirmBox('Delete this fact?', { danger: true, ok: 'Delete' })) { await DEL(`/api/fact/${eid}`); onDelete && onDelete(); } } }, 'Delete'))),
    h('div.form', { style: { marginTop: '10px' } },
      ...field('Fact type', typeSel), ...(t.UseDate !== 0 ? field('Date', date) : []), ...(t.UsePlace !== 0 ? field('Place', place) : []),
      ...(t.UsePlace !== 0 ? field('Place details', details) : []), ...field(t.UseValue ? 'Description' : 'Description', desc),
      ...field('Flags', h('div.row', prim, priv, h('span.muted', 'Proof'), proof)), ...field('Note', note),
      ...field('Sentence', h('div.col', sentPrev, h('details', h('summary.small.muted', 'Customize sentence'), custom,
        h('div.hint', 'Fields: [person] [couple] [Date] [Place] [PlaceDetails] [Desc] [Age]; modifiers like [person:HeShe], [Desc:A]; <…> drops when empty.'))))),
    h('h4', 'Citations'), cites, h('h4', 'Media'), media, h('h4', 'Shared with (witnesses)'), wit, h('h4', 'Tasks'), tasks);
  citationsPanel(cites, OT.event, eid, onChange);
  mediaPanel(media, OT.event, eid, onChange);
  tasksPanel(tasks, OT.event, eid);
  witnessPanel(wit, d, onChange);
}

function witnessPanel(el, d, onChange) {
  fill(el, h('div.list', d.witnesses.length ? d.witnesses.map(w => h('div', h('b', w.name || '(unnamed)'), h('span.muted', w.roleName),
    h('span.small.muted', w.sentencePreview), h('button.btn.sm.right', { onclick: async () => { await DEL(`/api/witness/${w.WitnessID}`); reload(); } }, 'Remove'))) : h('div.muted', 'Not shared')),
  h('div.row', { style: { marginTop: '6px' } }, h('button.btn.sm', { onclick: async () => {
    const pid = await choosePerson({ title: 'Share this fact with…' });
    if (!pid) return;
    const role = select([[0, 'Witness'], ...d.roles.map(r => [r.RoleID, r.RoleName])], 0);
    const ok = await modal({ title: 'Role', body: h('div.form', ...field('Role', role), ...field('', h('button.btn.sm', { onclick: () => import('./lists.js').then(x => x.roleManager(d.fact.EventType)) }, 'Manage roles…'))),
      buttons: [{ label: 'Cancel' }, { label: 'Share', primary: true, value: true }] }).done;
    if (ok) { await POST('/api/witness', { eventId: d.fact.EventID, personId: pid, role: Number(role.value) }); reload(); }
  } }, '+ Share with person'), h('button.btn.sm', { onclick: async () => {
    const g = h('input'), s = h('input');
    const ok = await modal({ title: 'Witness not in this file', body: h('div.form', ...field('Given', g), ...field('Surname', s)), buttons: [{ label: 'Cancel' }, { label: 'Add', primary: true, value: true }] }).done;
    if (ok) { await POST('/api/witness', { eventId: d.fact.EventID, personId: 0, given: g.value, surname: s.value }); reload(); }
  } }, '+ Unlinked witness')));
  async function reload() { const nd = await GET(`/api/fact/${d.fact.EventID}`); witnessPanel(el, nd, onChange); onChange && onChange(); }
}

// ================================================================ notes
export function noteEditor(value, onSave, label = 'Note') {
  const ta = h('textarea', { value, style: { minHeight: '46vh', fontFamily: 'Georgia, serif', fontSize: '15px' }, spellcheck: true });
  const wrap = (tag) => { const s = ta.selectionStart, e = ta.selectionEnd; ta.setRangeText(`<${tag}>${ta.value.slice(s, e)}</${tag}>`, s, e, 'end'); ta.focus(); };
  return h('div.col', h('div.row', h('b', label), h('span.grow'),
    h('button.btn.sm', { onclick: () => wrap('b'), title: 'Bold' }, h('b', 'B')), h('button.btn.sm', { onclick: () => wrap('i'), title: 'Italic' }, h('i', 'I')),
    h('button.btn.sm', { onclick: () => wrap('u'), title: 'Underline' }, h('u', 'U')),
    h('button.btn.sm', { onclick: () => import('./tools.js').then(x => x.run('charMap', c => ta.setRangeText(c, ta.selectionStart, ta.selectionEnd, 'end'))) }, 'Ω'),
    h('button.btn.primary', { onclick: () => onSave(ta.value) }, 'Save note')), ta,
  h('div.hint', 'Spell checking is provided by your browser. Formatting: <b>bold</b>, <i>italic</i>, <u>underline</u>.'));
}

// ================================================================ citations
export function citationsPanel(el, ownerType, ownerId, onChange) {
  async function load() {
    const list = await GET(`/api/citations?ownerType=${ownerType}&ownerId=${ownerId}`);
    fill(el, h('div.list', list.length ? list.map(c => h('div', { style: { alignItems: 'flex-start' } },
      h('div.grow', h('div', { html: c.footnote || '' }), h('div.small.muted', c.SourceName, ' · quality ', qualityText(c.Quality))),
      h('button.btn.sm', { onclick: async () => { if (await editCitation(c.CitationID, c.LinkID, c.Quality)) { load(); onChange && onChange(); } } }, 'Edit'),
      h('button.btn.sm', { onclick: async () => { if (await confirmBox('Remove this citation from here?')) { await DEL(`/api/citationLink/${c.LinkID}`, { deleteCitation: true }); load(); onChange && onChange(); } } }, 'Remove'))) : h('div.muted', 'No citations')),
    h('div.row', { style: { marginTop: '6px' } }, h('button.btn.sm', { onclick: async () => { if (await addCitation(ownerType, ownerId)) { load(); onChange && onChange(); } } }, '+ Add citation'),
      memo.length ? h('button.btn.sm', { onclick: async () => { await POST('/api/citations/memorize', { citations: memo, ownerType, ownerId }); load(); onChange && onChange(); toast(`Pasted ${memo.length}`); } }, `Paste ${memo.length} memorized`) : null,
      list.length ? h('button.btn.sm', { onclick: () => { memo = list.map(c => c.CitationID); toast(`Memorized ${memo.length} citation(s)`); load(); } }, 'Memorize') : null));
  }
  load();
}
let memo = [];
const qualityText = q => {
  q = q || '~~~';
  return [S.meta.quality.source[q[0]], S.meta.quality.info[q[1]], S.meta.quality.evidence[q[2]]].map(x => x || 'Unknown').join(' / ');
};

export async function addCitation(ownerType, ownerId) {
  const sources = await GET('/api/sources');
  const q = h('input', { type: 'search', placeholder: 'Search sources', style: { width: '100%' }, autofocus: true });
  const sel = select(sources.map(s => [s.SourceID, s.Name]), sources[0]?.SourceID, { size: 14, style: { width: '100%' } });
  q.addEventListener('input', () => { clear(sel); for (const s of sources.filter(s => s.Name.toLowerCase().includes(q.value.toLowerCase()))) put(sel, h('option', { value: s.SourceID }, s.Name)); sel.selectedIndex = 0; });
  const choice = await modal({ title: 'Add citation — choose source', wide: true, body: h('div.col', q, sel),
    buttons: [{ label: 'Cancel' }, { label: '+ New source…', value: 'new' }, { label: 'Use selected source', primary: true, click: () => sel.value ? Number(sel.value) : false }] }).done;
  let sid = choice;
  if (choice === 'new') sid = await import('./lists.js').then(x => x.editSource(null));
  if (!sid) return false;
  const sd = await GET(`/api/source/${sid}`);
  if (sd.citations.length) {
    const reuse = select([['', '— create a new citation —'], ...sd.citations.map(c => [c.CitationID, (c.CitationName || c.footnote.replace(/<[^>]+>/g, '')).slice(0, 120)])], '');
    const r = await modal({ title: 'Existing citations of this source', wide: true, body: h('div.form', ...field('Reuse citation', reuse)),
      buttons: [{ label: 'Cancel' }, { label: 'Continue', primary: true, click: () => reuse.value || 'new' }] }).done;
    if (!r) return false;
    if (r !== 'new') { await POST('/api/citation', { CitationID: Number(r), link: true, ownerType, ownerId }); return true; }
  }
  return citationForm({ source: sd, ownerType, ownerId });
}

export async function editCitation(cid, linkId, quality = '~~~') {
  const c = await GET(`/api/citation/${cid}`);
  const sd = await GET(`/api/source/${c.source.SourceID}`);
  return citationForm({ source: sd, citation: c, linkId, quality });
}

async function citationForm({ source, citation = null, ownerType, ownerId, linkId, quality = '~~~' }) {
  const defs = source.fieldDefs.filter(f => f.citation);
  const vals = citation?.Fields || {};
  const inputs = {};
  const fields = defs.map(f => { inputs[f.name] = h('input', { value: vals[f.name] || '', style: { width: '100%' }, placeholder: f.hint }); return field(f.display || f.name, inputs[f.name], { hint: f.longHint }); }).flat();
  const curQ = (quality || '~~~').padEnd(3, '~');
  const qs = select(Object.entries(S.meta.quality.source), curQ[0]), qi = select(Object.entries(S.meta.quality.info), curQ[1]), qe = select(Object.entries(S.meta.quality.evidence), curQ[2]);
  const name = h('input', { value: citation?.CitationName || '', style: { width: '100%' } });
  const text = h('textarea', { value: citation?.ActualText || '' }), comments = h('textarea', { value: citation?.Comments || '' });
  const prev = h('div.sentence.small');
  const preview = debounce(async () => {
    const r = await POST('/api/source/preview', { TemplateID: source.TemplateID, Fields: source.Fields, CitationFields: Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])) });
    prev.innerHTML = `<b>Footnote:</b> ${r.Footnote}<br><b>Short:</b> ${r.ShortFootnote}<br><b>Bibliography:</b> ${r.Bibliography}`;
  }, 250);
  Object.values(inputs).forEach(i => i.addEventListener('input', preview));
  preview();
  const media = h('div');
  const res = await modal({ title: (citation ? 'Edit citation' : 'New citation') + ' — ' + source.Name, wide: true,
    body: h('div.col', h('div.form', ...fields, ...field('Citation name', name, { hint: 'Optional label to find this citation again' }),
      ...field('Quality', h('div.row.wrap', qs, qi, qe)), ...field('Research note', comments), ...field('Detail text (transcription)', text)),
    h('h4', 'Preview'), prev, citation ? h('h4', 'Media for this citation') : null, citation ? media : null),
    buttons: [{ label: 'Cancel' }, { label: 'Save', primary: true, click: () => {
      const Fields = Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value]));
      const Quality = qs.value + qi.value + qe.value;
      if (citation) return POST('/api/citation', { CitationID: citation.CitationID, LinkID: linkId, Fields, Quality, CitationName: name.value, ActualText: text.value, Comments: comments.value });
      return POST('/api/citation', { SourceID: source.SourceID, ownerType, ownerId, Fields, Quality, CitationName: name.value, ActualText: text.value, Comments: comments.value });
    } }] });
  if (citation) mediaPanel(media, OT.citation, citation.CitationID);
  return res.done;
}
// ================================================================ media
export function mediaPanel(el, ownerType, ownerId, onChange) {
  async function load() {
    const items = ownerType === OT.person ? (await GET(`/api/person/${ownerId}`)).media
      : ownerType === OT.event ? (await GET(`/api/fact/${ownerId}`)).media
        : ownerType === OT.family ? (await GET(`/api/family/${ownerId}`)).media
          : ownerType === OT.source ? (await GET(`/api/source/${ownerId}`)).media
            : ownerType === OT.place ? (await GET(`/api/place/${ownerId}`)).media
              : ownerType === OT.citation ? (await GET(`/api/citation/${ownerId}`)).media : [];
    fill(el, h('div.thumbs', items.map(m => h('div.thumb', { onclick: () => import('./lists.js').then(x => x.editMedia(m.MediaID, m.LinkID)).then(r => r && load()) },
      m.MediaType === 1 ? h('img', { src: `/api/media/${m.MediaID}/file`, loading: 'lazy' }) : h('div.doc', m.MediaType === 3 ? '🔊' : m.MediaType === 4 ? '🎞' : '📄'),
      h('div.cap', m.IsPrimary ? '★ ' : '', m.Caption || m.MediaFile || m.URL)))),
    h('div.row', { style: { marginTop: '6px' } },
      h('label.btn.sm', 'Upload file…', h('input.hidden', { type: 'file', multiple: true, onchange: async e => {
        for (const f of e.target.files) await POST('/api/media', { content: await readFileAs(f, 'url'), filename: f.name, ownerType, ownerId, primary: items.length ? 0 : 1 });
        load(); onChange && onChange(); toast('Media added');
      } })),
      h('button.btn.sm', { onclick: async () => {
        const p = await chooseFile({ title: 'Link a file on this computer' });
        if (p) { await POST('/api/media', { path: p, ownerType, ownerId, primary: items.length ? 0 : 1 }); load(); onChange && onChange(); }
      } }, 'Link local file…'),
      h('button.btn.sm', { onclick: async () => {
        const all = await GET('/api/media');
        const sel = select(all.map(m => [m.MediaID, m.Caption || m.MediaFile]), '', { size: 12, style: { width: '100%' } });
        const id = await modal({ title: 'Tag existing media', body: sel, buttons: [{ label: 'Cancel' }, { label: 'Tag', primary: true, click: () => Number(sel.value) }] }).done;
        if (id) { await POST('/api/mediaLink', { mediaId: id, ownerType, ownerId }); load(); onChange && onChange(); }
      } }, 'Existing media…'),
      h('button.btn.sm', { onclick: async () => {
        const url = await promptBox('Link a URL', 'Web address of the image/document');
        if (url) { await POST('/api/media', { URL: url, path: '', Caption: url, MediaType: 2, ownerType, ownerId }); load(); }
      } }, 'URL…')));
  }
  load();
}

// ================================================================ tasks
export function tasksPanel(el, ownerType, ownerId) {
  async function load() {
    const all = await GET('/api/tasks');
    const mine = all.filter(t => t.links.some(l => l.ownerType === ownerType && l.ownerId === ownerId));
    fill(el, h('div.list', mine.length ? mine.map(t => h('div', { style: { cursor: 'pointer' }, onclick: () => import('./lists.js').then(x => x.editTask(t)).then(r => r && load()) },
      t.Status === 2 ? '☑' : '☐', h('b', t.Name), h('span.muted.small', S.meta.taskStatus[t.Status]), h('span.muted.small.right', S.meta.taskType[t.TaskType]))) : h('div.muted', 'No tasks')),
    h('div.row', { style: { marginTop: '6px' } }, h('button.btn.sm', { onclick: async () => { const r = await import('./lists.js').then(x => x.editTask({ ownerType, ownerId })); if (r) load(); } }, '+ New task'),
      h('button.btn.sm', { onclick: async () => {
        const sel = select(all.map(t => [t.TaskID, t.Name]), '', { size: 12, style: { width: '100%' } });
        const id = await modal({ title: 'Link existing task', body: sel, buttons: [{ label: 'Cancel' }, { label: 'Link', primary: true, click: () => Number(sel.value) }] }).done;
        if (id) { await POST('/api/taskLink', { taskId: id, ownerType, ownerId }); load(); }
      } }, 'Link existing…')));
  }
  load();
}

// ================================================================ web tags
export function webtagsPanel(el, ownerType, ownerId) {
  async function load() {
    const tags = await GET(`/api/list/webtags?OwnerType=${ownerType}&OwnerID=${ownerId}`);
    fill(el, h('div.list', tags.length ? tags.map(t => h('div', h('a', { href: safeUrl(t.URL), target: '_blank', rel: 'noopener noreferrer' }, t.Name || t.URL), h('span.muted.small', t.URL),
      h('button.btn.sm.right', { onclick: () => edit(t) }, 'Edit'))) : h('div.muted', 'No WebTags')),
    h('button.btn.sm', { style: { marginTop: '6px' }, onclick: () => edit({}) }, '+ Add WebTag'));
  }
  async function edit(t) {
    const name = h('input', { value: t.Name || '', style: { width: '100%' } }), url = h('input', { value: t.URL || 'https://', style: { width: '100%' } }), note = h('textarea', { value: t.Note || '' });
    const r = await modal({ title: 'WebTag', body: h('div.form', ...field('Name', name), ...field('URL', url), ...field('Note', note)),
      buttons: [t.LinkID ? { label: 'Delete', danger: true, click: async () => { await DEL(`/api/list/webtags/${t.LinkID}`); return 'x'; } } : null, { label: 'Cancel' },
        { label: 'Save', primary: true, click: () => POST('/api/list/webtags', { LinkID: t.LinkID, OwnerType: ownerType, OwnerID: ownerId, Name: name.value, URL: url.value, Note: note.value }) }].filter(Boolean) }).done;
    if (r) load();
  }
  load();
}

// ================================================================ family edit
export async function editFamily(fid) {
  let f = await GET(`/api/family/${fid}`);
  const body = h('div');
  const m = modal({ title: 'Edit family', xwide: true, body, buttons: [{ label: 'Delete family…', danger: true, click: async () => {
    if (await confirmBox('Delete this family? People are kept.', { danger: true })) { await DEL(`/api/family/${fid}`); return true; } return false;
  } }, { label: 'Close', primary: true }], onclose: () => changed() });
  async function draw(sel) {
    f = await GET(`/api/family/${fid}`);
    m.title.textContent = `Edit family — ${[f.father?.name, f.mother?.name].filter(Boolean).join(' & ')}`;
    const list = h('div.flist'), detail = h('div.fdetail');
    put(list, h('div.toolbar', h('b', 'Family facts'), h('span.grow'), h('button.btn.sm.primary', { onclick: addFact }, '+ Add fact')));
    put(list, h('div.fitem' + (!sel ? '.sel' : ''), { onclick: () => draw() }, h('span.t', 'Family'), h('span'), h('span.d', 'Spouses, children, notes, sources')));
    for (const x of f.facts) put(list, h('div.fitem' + (sel === x.id ? '.sel' : ''), { onclick: () => draw(x.id) }, h('span.t', x.typeName),
      h('span.badges', x.citations ? h('span.badge', `S${x.citations}`) : ''), h('span.d', [x.date, x.place, x.description].filter(Boolean).join(' · ') || '—')));
    fill(body, h('div.editp', { style: { height: 'calc(90vh - 150px)' } }, list, detail));
    if (sel) return editFactPanel(detail, sel, { onChange: () => {}, onDelete: () => draw() });
    const priv = checkbox('Private', f.private);
    const proof = select(Object.entries(S.meta.proof).map(([k, v]) => [k, v || '(none)']), f.proof || 0);
    const cites = h('div'), media = h('div');
    put(detail, 
      h('div.row', h('b', 'Husband:'), f.father ? personLine(f.father) : h('span.muted', 'none'), h('b', { style: { marginLeft: '16px' } }, 'Wife:'), f.mother ? personLine(f.mother) : h('span.muted', 'none'),
        h('button.btn.sm.right', { onclick: async () => { await POST(`/api/family/${fid}/swap`); draw(); } }, 'Swap')),
      h('div.row', { style: { margin: '8px 0' } }, priv, h('span.muted', 'Proof'), proof, h('button.btn.sm', { onclick: async () => { await PUT(`/api/family/${fid}`, { IsPrivate: priv.input.checked ? 1 : 0, Proof: Number(proof.value) }); toast('Saved'); } }, 'Save flags')),
      h('h4', 'Children'), h('table.dt', h('tbody', f.children.map(c => {
        const rf = select(Object.entries(S.meta.childRel), c.relFather || 0), rm = select(Object.entries(S.meta.childRel), c.relMother || 0);
        const upd = () => POST(`/api/family/${fid}/childRel`, { child: c.id, relFather: Number(rf.value), relMother: Number(rm.value) }).then(() => toast('Saved'));
        rf.onchange = upd; rm.onchange = upd;
        return h('tr', h('td', personLine(c)), h('td', 'to father ', rf), h('td', 'to mother ', rm),
          h('td', h('button.btn.sm', { onclick: async () => { if (await confirmBox(`Unlink ${c.name} from this family?`)) { await POST(`/api/family/${fid}/unlinkChild`, { child: c.id }); draw(); } } }, 'Unlink')));
      }))),
      h('h4', 'Family note'), noteEditor(f.note || '', async v => { await PUT(`/api/family/${fid}`, { Note: v }); toast('Saved'); }, ''),
      h('h4', 'Family citations'), cites, h('h4', 'Family media'), media);
    citationsPanel(cites, OT.family, fid);
    mediaPanel(media, OT.family, fid);
  }
  async function addFact() {
    const types = S.meta.factTypes.filter(t => t.OwnerType === 1);
    const sel = select(types.map(t => [t.FactTypeID, t.Name]), 300, { size: 12, style: { width: '100%' } });
    const ft = await modal({ title: 'Add family fact', body: sel, buttons: [{ label: 'Cancel' }, { label: 'Add', primary: true, click: () => Number(sel.value) }] }).done;
    if (!ft) return;
    const r = await POST('/api/fact', { ownerType: 1, ownerId: fid, type: ft });
    draw(r.id);
  }
  draw();
  return m.done;
}
