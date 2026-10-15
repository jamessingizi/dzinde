// Settings (per-file, stored in ConfigTable) + app data folder.
import { GET, PUT, POST, h, clear, toast, fail, select, checkbox, field, chooseFile, put, fill } from './ui.js';
import { S, applySettings, refreshFile } from './app.js';

export async function render(root, [tab = 'display']) {
  const f = await GET('/api/files');
  const tabs = [['display', 'Display'], ['general', 'General'], ['folders', 'Folders'], ['preparer', 'Preparer'], ['colors', 'Colors'], ['lds', 'LDS'], ['websearch', 'WebSearch']];
  const page = h('div.page-pad', { style: { maxWidth: '820px' } });
  put(root, h('div.toolbar', h('div.tabs', tabs.map(([k, l]) => h('button' + (k === tab ? '.active' : ''), { onclick: () => (location.hash = '#/settings/' + k) }, l)))), page);
  if (!S.file && tab !== 'folders') {
    put(page, h('p.muted', 'Most settings are saved inside each file. Open a file to change them.'));
    tab = 'folders';
  }
  const s = S.settings || {};
  const save = async patch => { try { S.settings = await PUT('/api/settings', patch); applySettings(); toast('Settings saved'); } catch (e) { fail(e); } };

  if (tab === 'display') {
    const theme = select([['light', 'Light'], ['dark', 'Dark']], s.theme);
    const scale = select([['0.9', 'Small'], ['1', 'Normal'], ['1.1', 'Large'], ['1.2', 'Extra large']], String(s.fontScale || 1));
    const df = select(Object.entries(S.meta.dateFormats), s.dateFormat);
    const nf = select([['given_surname', 'Given Surname'], ['surname_given', 'Surname, Given'], ['full', 'Prefix Given "Nickname" Surname Suffix']], s.nameFormat);
    const caps = checkbox('Show surnames in CAPITALS', s.surnameCaps), ids = checkbox('Show record numbers', s.showIds);
    put(page, h('div.form', ...field('Theme', theme), ...field('Text size', scale), ...field('Date format', df), ...field('Name format', nf), ...field('', h('div.col', caps, ids))),
      h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ theme: theme.value, fontScale: Number(scale.value), dateFormat: df.value, nameFormat: nf.value, surnameCaps: caps.input.checked, showIds: ids.input.checked }) }, 'Save'));
  }
  if (tab === 'general') {
    const yrs = h('input', { type: 'number', value: s.livingYears || 110, style: { width: '90px' } });
    put(page, h('div.form', ...field('Living if born within', h('div.row', yrs, 'years')), ...field('Root person', h('span', s.rootPersonId ? `#${s.rootPersonId}` : 'not set', ' — set it in Tools › Set relationships'))),
      h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ livingYears: Number(yrs.value) }) }, 'Save'));
  }
  if (tab === 'folders') {
    const folderRow = (label, key, current, onpick) => {
      const lbl = h('span.mono.small', current || '(default)');
      return field(label, h('div.row', lbl, h('button.btn.sm', { onclick: async () => { const p = await chooseFile({ title: label, folder: true, dir: current }); if (p) { lbl.textContent = p; onpick(p); } } }, 'Choose…')));
    };
    put(page, h('div.form',
      ...folderRow('Data folder (all files)', 'dataDir', f.dataDir, async p => { await POST('/api/settings/dataDir', { dataDir: p }); toast('Saved'); refreshFile(); }),
      ...(S.file ? [...folderRow('Media folder (uploads)', 'mediaFolder', s.mediaFolder, p => save({ mediaFolder: p })),
        ...folderRow('Backup folder', 'backupFolder', s.backupFolder, p => save({ backupFolder: p })),
        ...folderRow('Export folder', 'exportFolder', s.exportFolder, p => save({ exportFolder: p }))] : [])));
  }
  if (tab === 'preparer') {
    const p = s.preparer || {};
    const i = k => h('input', { value: p[k] || '', style: { width: '100%' } });
    const name = i('name'), addr = i('address'), email = i('email'), phone = i('phone');
    put(page, h('p.muted', 'Shown on reports and in exported GEDCOM files.'), h('div.form', ...field('Name', name), ...field('Address', addr), ...field('Email', email), ...field('Phone', phone)),
      h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ preparer: { name: name.value, address: addr.value, email: email.value, phone: phone.value } }) }, 'Save'));
  }
  if (tab === 'colors') {
    const names = [...(s.colorNames || [])], sets = [...(s.colorSetNames || [])];
    const active = select(sets.map((n, i) => [i, n]), s.activeColorSet || 0);
    put(page, h('div.form', ...field('Color set shown', active), ...sets.flatMap((n, i) => field(`Color set ${i + 1} name`, h('input', { value: n, oninput: e => (sets[i] = e.target.value) })))),
      h('h4', 'Color names'), h('div', { style: { columns: 3 } }, names.slice(1).map((n, i) => h('div', { style: { marginBottom: '4px' } }, h('input', { value: n, oninput: e => (names[i + 1] = e.target.value) })))),
      h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ colorNames: names, colorSetNames: sets, activeColorSet: Number(active.value) }) }, 'Save'));
  }
  if (tab === 'lds') {
    const lds = checkbox('Show LDS ordinance facts and the LDS list report', s.showLds);
    put(page, lds, h('div', h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ showLds: lds.input.checked }) }, 'Save')));
  }
  if (tab === 'websearch') {
    const provs = (s.webSearchProviders || []).map(p => ({ ...p }));
    const list = h('div');
    function draw() {
      fill(list, ...provs.map((p, i) => h('div.row', { style: { marginBottom: '6px' } }, h('input', { value: p.name, style: { width: '160px' }, oninput: e => (p.name = e.target.value) }),
        h('input', { value: p.url, style: { flex: 1 }, oninput: e => (p.url = e.target.value) }), h('button.btn.sm', { onclick: () => { provs.splice(i, 1); draw(); } }, '✕'))),
      h('button.btn.sm', { onclick: () => { provs.push({ name: 'New', url: 'https://' }); draw(); } }, '+ Provider'));
    }
    draw();
    put(page, h('p.muted', 'URL placeholders: {given} {surname} {birthyear} {deathyear}'), list, h('button.btn.primary', { style: { marginTop: '12px' }, onclick: () => save({ webSearchProviders: provs }) }, 'Save'));
  }
}
