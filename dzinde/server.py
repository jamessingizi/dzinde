"""Local HTTP server: JSON API + static web UI. Binds to 127.0.0.1 only."""
import json
import mimetypes
import os
import re
import shutil
import threading
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db, gedcom, model as m, reports, rmdate, tools, website
from .db import OWNER, insert, row, rows, tx, update

# Windows' registry often maps .js to text/plain, and browsers refuse ES modules served with that type
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/css', '.css')
WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')
CONF_DIR = os.path.expanduser('~/.dzinde')
CONF = os.path.join(CONF_DIR, 'config.json')


class App:
    """Holds the open database. One file open at a time (like RootsMagic)."""
    def __init__(self):
        self.lock = threading.RLock()
        self.con = None
        self.path = None
        self.conf = {'recent': [], 'dataDir': os.path.expanduser('~/Dzinde')}
        try:
            self.conf.update(json.load(open(CONF)))
        except (OSError, ValueError):
            pass

    def save_conf(self):
        os.makedirs(CONF_DIR, exist_ok=True)
        json.dump(self.conf, open(CONF, 'w'), indent=1)

    def open(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(path):
            raise ApiError(f'File not found: {path}', 404)
        with self.lock:
            self.close()
            con = db.connect(path)
            try:
                con.execute('SELECT 1 FROM PersonTable LIMIT 1')
            except Exception:
                con.close()
                raise ApiError('Not a RootsMagic/Dzinde database')
            db.upgrade(con)
            self.con, self.path = con, path
            rec = [p for p in self.conf['recent'] if p != path]
            self.conf['recent'] = [path] + rec[:9]
            self.conf['lastFile'] = path
            self.save_conf()

    def close(self):
        with self.lock:
            if self.con:
                self.con.close()
            self.con = self.path = None

    def need(self):
        if not self.con:
            raise ApiError('No file is open', 409)
        return self.con


class ApiError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


APP = App()
ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile('^' + pattern + '$'), fn))
        return fn
    return deco


def ival(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


# ================================================================== files
def _file_info(p):
    try:
        st = os.stat(p)
        return {'path': p, 'name': os.path.basename(p), 'size': st.st_size, 'modified': st.st_mtime, 'exists': True}
    except OSError:
        return {'path': p, 'name': os.path.basename(p), 'exists': False}


@route('GET', '/api/files')
def files_state(q, b):
    d = APP.conf['dataDir']
    found = []
    if os.path.isdir(d):
        found = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(('.rmtree', '.rmgc'))]
    return {'current': _file_info(APP.path) if APP.path else None, 'recent': [_file_info(p) for p in APP.conf['recent']],
            'dataDir': d, 'files': [_file_info(p) for p in found], 'home': os.path.expanduser('~')}


@route('POST', '/api/files/open')
def files_open(q, b):
    APP.open(b['path'])
    return files_state(q, b)


@route('POST', '/api/files/new')
def files_new(q, b):
    name = re.sub(r'[\\/:*?"<>|]', '', (b.get('name') or '').strip()) or 'My Family'
    folder = os.path.expanduser(b.get('folder') or APP.conf['dataDir'])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name if name.lower().endswith('.rmtree') else name + '.rmtree')
    if os.path.exists(path):
        raise ApiError('A file with that name already exists')
    db.create(path).close()
    APP.open(path)
    if b.get('preparer'):
        m.save_settings(APP.con, {'preparer': b['preparer']})
    return files_state(q, b)


@route('POST', '/api/files/close')
def files_close(q, b):
    APP.close()
    return files_state(q, b)


@route('POST', '/api/files/copy')
def files_copy(q, b):
    con = APP.need()
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    dest = os.path.join(os.path.dirname(APP.path), (b.get('name') or 'Copy') + '.rmtree')
    if os.path.exists(dest):
        raise ApiError('Destination exists')
    shutil.copy2(APP.path, dest)
    return {'path': dest}


@route('POST', '/api/files/rename')
def files_rename(q, b):
    APP.need()
    old = APP.path
    dest = os.path.join(os.path.dirname(old), b['name'] + '.rmtree')
    if os.path.exists(dest):
        raise ApiError('Destination exists')
    APP.close()
    os.rename(old, dest)
    for ext in ('-wal', '-shm'):
        if os.path.exists(old + ext):
            os.rename(old + ext, dest + ext)
    APP.conf['recent'] = [p for p in APP.conf['recent'] if p != old]
    APP.open(dest)
    return files_state(q, b)


@route('POST', '/api/files/delete')
def files_delete(q, b):
    p = os.path.abspath(b['path'])
    if not p.lower().endswith(('.rmtree', '.rmgc')):
        raise ApiError('Only database files can be deleted here')
    if p == APP.path:
        APP.close()
    for ext in ('', '-wal', '-shm'):
        if os.path.exists(p + ext):
            os.remove(p + ext)
    APP.conf['recent'] = [x for x in APP.conf['recent'] if x != p]
    APP.save_conf()
    return files_state(q, b)


@route('GET', '/api/files/properties')
def files_props(q, b):
    con = APP.need()
    st = tools.statistics(con)
    return {'file': _file_info(APP.path), 'stats': st,
            'sqlite': con.execute('select sqlite_version()').fetchone()[0],
            'userVersion': con.execute('PRAGMA user_version').fetchone()[0]}


@route('POST', '/api/files/backup')
def files_backup(q, b):
    APP.need()
    dest = os.path.expanduser(b.get('folder') or m.settings(APP.con).get('backupFolder') or os.path.join(APP.conf['dataDir'], 'Backups'))
    os.makedirs(dest, exist_ok=True)
    return {'path': tools.backup(APP.path, dest, bool(b.get('includeMedia')))}


@route('POST', '/api/files/restore')
def files_restore(q, b):
    dest = os.path.expanduser(b.get('folder') or APP.conf['dataDir'])
    os.makedirs(dest, exist_ok=True)
    path = tools.restore(b['path'], dest)
    APP.open(path)
    return {'path': path}


@route('POST', '/api/files/compare')
def files_compare(q, b):
    return tools.compare_files(APP.need(), b['path'])


@route('POST', '/api/files/importLists')
def files_import_lists(q, b):
    return tools.import_lists(APP.need(), b['path'], b.get('what') or [])


@route('POST', '/api/settings/dataDir')
def set_data_dir(q, b):
    APP.conf['dataDir'] = os.path.expanduser(b['dataDir'])
    APP.save_conf()
    return files_state(q, b)


@route('GET', '/api/browse')
def browse(q, b):
    """Local file chooser (the browser can't reveal absolute paths)."""
    d = os.path.expanduser(q.get('dir') or APP.conf['dataDir'])
    d = os.path.abspath(d if os.path.isdir(d) else os.path.expanduser('~'))
    exts = tuple(x for x in (q.get('ext') or '').lower().split(',') if x)
    entries = []
    try:
        for name in sorted(os.listdir(d), key=str.lower):
            if name.startswith('.'):
                continue
            p = os.path.join(d, name)
            if os.path.isdir(p):
                entries.append({'name': name, 'path': p, 'dir': True})
            elif not exts or name.lower().endswith(exts):
                entries.append({'name': name, 'path': p, 'dir': False, 'size': os.path.getsize(p)})
    except PermissionError:
        raise ApiError(f'Permission denied: {d}', 403)
    return {'dir': d, 'parent': os.path.dirname(d), 'entries': entries, 'home': os.path.expanduser('~')}


# ================================================================== import / export
@route('POST', '/api/import/gedcom')
def import_gedcom(q, b):
    if b.get('newFile'):
        files_new(q, {'name': b['newFile']})
    con = APP.need()
    res = gedcom.import_file(con, os.path.expanduser(b['path']))
    if b.get('setLiving', True):
        tools.set_living(con)
    return res


@route('POST', '/api/import/gedcomUpload')
def import_gedcom_upload(q, b):
    """Body: {name, content(text), newFile?}"""
    if b.get('newFile'):
        files_new(q, {'name': b['newFile']})
    con = APP.need()
    res = gedcom.import_text(con, b['content'])
    if b.get('setLiving', True):
        tools.set_living(con)
    return res


@route('POST', '/api/export/gedcom')
def export_gedcom(q, b):
    con = APP.need()
    people = _people_for(con, b.get('who', 'all'))
    text = gedcom.export(con, people, b.get('options') or {})
    if b.get('path'):
        path = os.path.expanduser(b['path'])
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return {'path': path, 'people': len(people)}
    return {'content': text, 'people': len(people)}


def _people_for(con, who):
    ctx = reports.Ctx(con, {'who': who})
    return ctx.people()


# ================================================================== settings
@route('GET', '/api/settings')
def get_settings(q, b):
    return m.settings(APP.need())


@route('PUT', '/api/settings')
def put_settings(q, b):
    return m.save_settings(APP.need(), b)


# ================================================================== people
@route('GET', '/api/people')
def people_index(q, b):
    """Name index (all names incl. alternates when ?alt=1), sorted surname/given."""
    con = APP.need()
    s = m.settings(con)
    alt = q.get('alt') == '1'
    where = '' if alt else 'WHERE n.IsPrimary=1'
    text = (q.get('q') or '').strip()
    args = []
    if text:
        if ',' in text:
            sur, giv = [x.strip() for x in text.split(',', 1)]
            where += (' AND ' if where else 'WHERE ') + 'n.Surname LIKE ? AND n.Given LIKE ?'
            args += [sur + '%', giv + '%']
        elif text.isdigit():
            where += (' AND ' if where else 'WHERE ') + 'n.OwnerID=?'
            args.append(int(text))
        else:
            parts = text.split()
            for part in parts:
                where += (' AND ' if where else 'WHERE ') + '(n.Surname LIKE ? OR n.Given LIKE ? OR n.Nickname LIKE ?)'
                args += [part + '%', '%' + part + '%', part + '%']
    lim = min(ival(q.get('limit'), 50000), 50000)
    out = []
    color_col = 'Color' if not s.get('activeColorSet') else f'Color{s["activeColorSet"]}'
    for r in rows(con, f'''SELECT n.OwnerID AS id, n.Surname, n.Given, n.Suffix, n.Prefix, n.Nickname, n.BirthYear, n.DeathYear,
                         n.IsPrimary, n.NameType, p.Sex, p.Living, p.{color_col} AS Color, p.Bookmark
                         FROM NameTable n JOIN PersonTable p ON p.PersonID=n.OwnerID {where}
                         ORDER BY n.Surname COLLATE RMNOCASE, n.Given COLLATE RMNOCASE, n.BirthYear LIMIT ?''', *args, lim):
        out.append([r['id'], r['Surname'] or '', r['Given'] or '', r['Suffix'] or '', r['BirthYear'] or 0, r['DeathYear'] or 0,
                    r['Sex'], r['IsPrimary'], r['Color'] or 0, r['Bookmark'] or 0, r['Living'] or 0])
    return {'columns': ['id', 'surname', 'given', 'suffix', 'by', 'dy', 'sex', 'primary', 'color', 'bookmark', 'living'], 'rows': out}


@route('GET', r'/api/person/(\d+)')
def person_get(q, b, pid):
    con = APP.need()
    pid = int(pid)
    s = m.settings(con)
    p = row(con, 'SELECT * FROM PersonTable WHERE PersonID=?', pid)
    if not p:
        raise ApiError('Person not found', 404)
    summary = m.person_summary(con, pid, s)
    parents = []
    for pf in m.parents_of(con, pid):
        parents.append({'family': pf['family'], 'father': m.person_summary(con, pf['father'], s) if pf['father'] else None,
                        'mother': m.person_summary(con, pf['mother'], s) if pf['mother'] else None,
                        'relFather': pf['relFather'], 'relMother': pf['relMother'],
                        'primary': pf['family'] == p['ParentID']})
    spouses = []
    for f in m.spouse_families(con, pid):
        fs = m.family_summary(con, f['FamilyID'], s)
        fs['spouse'] = m.person_summary(con, f['spouse'], s) if f['spouse'] else None
        fs['facts'] = m.facts_for(con, 'family', f['FamilyID'], s)
        spouses.append(fs)
    return {
        'person': p, 'summary': summary,
        'names': rows(con, 'SELECT * FROM NameTable WHERE OwnerID=? ORDER BY IsPrimary DESC, NameID', pid),
        'facts': m.facts_for(con, 'person', pid, s),
        'parents': parents, 'spouses': spouses,
        'siblings': [m.person_summary(con, x, s) for x in m.siblings_of(con, pid)],
        'citations': m.citations_for(con, 0, pid),
        'media': _media_links(con, 0, pid),
        'tasks': _task_links(con, 0, pid),
        'webtags': rows(con, 'SELECT * FROM URLTable WHERE OwnerType=0 AND OwnerID=?', pid),
        'groups': m.person_groups(con, pid),
        'fans': _fans(con, pid, s),
        'dna': _dna(con, pid, s),
        'health': rows(con, 'SELECT * FROM HealthTable WHERE OwnerID=? ORDER BY Date', pid),
        'addresses': rows(con, '''SELECT a.*, l.LinkID FROM AddressLinkTable l JOIN AddressTable a ON a.AddressID=l.AddressID
                                  WHERE l.OwnerType=0 AND l.OwnerID=?''', pid),
        'relationship': tools.relationship_to_root(con, pid),
        'noteHtml': m.note_to_html(p['Note']),
    }


def _fans(con, pid, s):
    out = []
    for a in rows(con, '''SELECT f.*, t.Name AS TypeName, t.Role1, t.Role2 FROM FANTable f LEFT JOIN FANTypeTable t
                          ON t.FANTypeID=f.FanTypeID WHERE f.ID1=? OR f.ID2=?''', pid, pid):
        other = a['ID2'] if a['ID1'] == pid else a['ID1']
        a['other'] = m.person_summary(con, other, s)
        a['myRole'] = a['Role1'] if a['ID1'] == pid else a['Role2']
        a['theirRole'] = a['Role2'] if a['ID1'] == pid else a['Role1']
        a['dateText'] = rmdate.format(a['Date'], s['dateFormat'])
        a['place'] = m.place_name(con, a['PlaceID'])
        out.append(a)
    return out


def _dna(con, pid, s):
    out = []
    for d in rows(con, 'SELECT * FROM DNATable WHERE ID1=? OR ID2=? ORDER BY SharedCM DESC', pid, pid):
        other = d['ID2'] if d['ID1'] == pid else d['ID1']
        d['other'] = m.person_summary(con, other, s)
        rel = tools.relationships(con, pid, other)
        d['relationship'] = rel[0]['name'] if rel else ''
        d['predicted'] = reports.predict_relationship(d['SharedCM'] or 0)
        out.append(d)
    return out


def _media_links(con, otype, oid):
    return rows(con, '''SELECT l.*, mm.MediaType, mm.MediaPath, mm.MediaFile, mm.URL, mm.Caption, mm.Date, mm.Description
                        FROM MediaLinkTable l JOIN MultimediaTable mm ON mm.MediaID=l.MediaID
                        WHERE l.OwnerType=? AND l.OwnerID=? ORDER BY l.IsPrimary DESC, l.SortOrder''', otype, oid)


def _task_links(con, otype, oid):
    return rows(con, '''SELECT l.LinkID, t.* FROM TaskLinkTable l JOIN TaskTable t ON t.TaskID=l.TaskID
                        WHERE l.OwnerType=? AND l.OwnerID=?''', otype, oid)


@route('POST', '/api/person')
def person_add(q, b):
    """Add a person, optionally linked: rel = spouse|child|parent|father|mother with 'of' (person) or 'family'."""
    con = APP.need()
    with tx(con):
        if b.get('existing'):
            pid = int(b['existing'])
        else:
            pid = m.add_person(con, b.get('given', ''), b.get('surname', ''), ival(b.get('sex'), 2),
                               prefix=b.get('prefix', ''), suffix=b.get('suffix', ''), nickname=b.get('nickname', ''),
                               birth_date=b.get('birthDate', ''), birth_place=b.get('birthPlace', ''),
                               death_date=b.get('deathDate', ''), death_place=b.get('deathPlace', ''),
                               living=1 if b.get('living') else 0)
            for f in b.get('facts') or []:
                m.add_fact(con, 'person', pid, int(f['type']), date=f.get('date', ''), place=f.get('place', ''),
                           desc=f.get('description', ''))
        rel, of = b.get('rel'), ival(b.get('of'))
        fid = ival(b.get('family'))
        if rel == 'spouse' and of:
            fid = m.add_spouse(con, of, pid)
        elif rel == 'child':
            if not fid and of:
                fams = m.spouse_families(con, of)
                fid = fams[0]['FamilyID'] if fams else 0
                if not fid:
                    sex = row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', of)['Sex']
                    fid = m.add_family(con, of if sex != 1 else 0, of if sex == 1 else 0)
            m.add_child(con, fid, pid, ival(b.get('relFather')), ival(b.get('relMother')))
        elif rel in ('parent', 'father', 'mother') and of:
            fa, mo, fam = m.primary_parents(con, of)
            sex = row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid)['Sex']
            as_father = rel == 'father' or (rel == 'parent' and sex != 1)
            if fam:
                col = 'FatherID' if as_father else 'MotherID'
                if row(con, f'SELECT {col} AS x FROM FamilyTable WHERE FamilyID=?', fam)['x']:
                    fam = 0  # slot taken -> new parent family
                else:
                    con.execute(f'UPDATE FamilyTable SET {col}=? WHERE FamilyID=?', (pid, fam))
                    con.execute('UPDATE PersonTable SET SpouseID=? WHERE PersonID=? AND SpouseID=0', (fam, pid))
            if not fam:
                fam = m.add_family(con, pid if as_father else 0, 0 if as_father else pid)
                m.add_child(con, fam, of)
            fid = fam
    return {'id': pid, 'family': fid}


@route('POST', '/api/family/parents')
def family_set_parents(q, b):
    """Link an existing couple/family as parents of child."""
    con = APP.need()
    child = int(b['child'])
    fid = ival(b.get('family'))
    if not fid:
        fa, mo = ival(b.get('father')), ival(b.get('mother'))
        f = m.find_family(con, fa, mo) if fa and mo else None
        fid = f['FamilyID'] if f else m.add_family(con, fa, mo)
    m.add_child(con, fid, child, ival(b.get('relFather')), ival(b.get('relMother')))
    return {'family': fid}


@route('PUT', r'/api/person/(\d+)')
def person_put(q, b, pid):
    con = APP.need()
    allowed = {k: v for k, v in b.items() if k in ('Sex', 'Living', 'IsPrivate', 'Proof', 'Note', 'Bookmark', 'Color', 'Color1',
                                                   'Color2', 'Color3', 'Color4', 'Color5', 'Color6', 'Color7', 'Color8', 'Color9',
                                                   'ParentID', 'SpouseID')}
    update(con, 'PersonTable', 'PersonID', int(pid), allowed)
    return {'ok': True}


@route('DELETE', r'/api/person/(\d+)')
def person_delete(q, b, pid):
    m.delete_person(APP.need(), int(pid))
    return {'ok': True}


@route('POST', '/api/name')
def name_save(q, b):
    return {'id': m.save_name(APP.need(), b)}


@route('DELETE', r'/api/name/(\d+)')
def name_delete(q, b, nid):
    con = APP.need()
    n = row(con, 'SELECT * FROM NameTable WHERE NameID=?', int(nid))
    if n and n['IsPrimary']:
        raise ApiError('Cannot delete the primary name; make another name primary first')
    con.execute('DELETE FROM NameTable WHERE NameID=?', (int(nid),))
    m._delete_links(con, OWNER['name'], int(nid))
    return {'ok': True}


# ================================================================== facts
@route('POST', '/api/fact')
def fact_add(q, b):
    con = APP.need()
    eid = m.add_fact(con, ival(b.get('ownerType')), int(b['ownerId']), int(b['type']), date=b.get('date', ''),
                     place=b.get('place', ''), place_details=b.get('placeDetails', ''), desc=b.get('description', ''),
                     note=b.get('note', ''), private=ival(b.get('private')), proof=ival(b.get('proof')),
                     sentence=b.get('sentence', ''))
    return {'id': eid}


@route('GET', r'/api/fact/(\d+)')
def fact_get(q, b, eid):
    con = APP.need()
    e = row(con, 'SELECT * FROM EventTable WHERE EventID=?', int(eid))
    if not e:
        raise ApiError('Not found', 404)
    s = m.settings(con)
    ft = m.fact_type(con, e['EventType']) or {}
    witnesses = []
    for w in rows(con, 'SELECT * FROM WitnessTable WHERE EventID=? ORDER BY WitnessOrder', int(eid)):
        w['name'] = m.person_name(con, w['PersonID']) if w['PersonID'] else f"{w['Given'] or ''} {w['Surname'] or ''}".strip()
        w['roleName'] = m.role_name(con, w['Role'])
        w['sentencePreview'] = m.render_sentence(con, w['Sentence'] or (row(con, 'SELECT Sentence FROM RoleTable WHERE RoleID=?', w['Role']) or {}).get('Sentence') or '[ThisPerson] witnessed the event of [person]< [Date]>< [Place]>.', e, s, this_person=w['PersonID'])
        witnesses.append(w)
    return {'fact': e, 'type': ft, 'dateText': rmdate.format(e['Date'], s['dateFormat']),
            'place': m.place_name(con, e['PlaceID']), 'placeDetails': m.place_name(con, e['SiteID']),
            'sentence': m.fact_sentence(con, e['EventID'], s), 'templateSentence': ft.get('Sentence', ''),
            'citations': m.citations_for(con, 2, e['EventID']), 'media': _media_links(con, 2, e['EventID']),
            'tasks': _task_links(con, 2, e['EventID']), 'witnesses': witnesses,
            'roles': rows(con, 'SELECT * FROM RoleTable WHERE EventType=? ORDER BY RoleName', e['EventType'])}


@route('PUT', r'/api/fact/(\d+)')
def fact_put(q, b, eid):
    b['EventID'] = int(eid)
    m.save_fact(APP.need(), b)
    return fact_get(q, {}, eid)


@route('DELETE', r'/api/fact/(\d+)')
def fact_delete(q, b, eid):
    m.delete_fact(APP.need(), int(eid))
    return {'ok': True}


@route('POST', '/api/sentence/preview')
def sentence_preview(q, b):
    con = APP.need()
    e = row(con, 'SELECT * FROM EventTable WHERE EventID=?', int(b['eventId']))
    return {'text': m.render_sentence(con, b.get('template') or '', e, m.settings(con), this_person=ival(b.get('thisPerson')))}


@route('POST', '/api/witness')
def witness_add(q, b):
    con = APP.need()
    wid = m.add_witness(con, int(b['eventId']), ival(b.get('personId')), ival(b.get('role')), b.get('given', ''),
                        b.get('surname', ''), b.get('sentence', ''), b.get('note', ''))
    return {'id': wid}


@route('PUT', r'/api/witness/(\d+)')
def witness_put(q, b, wid):
    update(APP.need(), 'WitnessTable', 'WitnessID', int(wid), b)
    return {'ok': True}


@route('DELETE', r'/api/witness/(\d+)')
def witness_delete(q, b, wid):
    APP.need().execute('DELETE FROM WitnessTable WHERE WitnessID=?', (int(wid),))
    return {'ok': True}


@route('GET', '/api/date/parse')
def date_parse(q, b):
    enc = rmdate.encode(q.get('text', ''))
    con = APP.con
    fmt = m.settings(con)['dateFormat'] if con else 'dmy'
    g = rmdate.decode(enc)
    return {'encoded': enc, 'display': rmdate.format(enc, fmt), 'isText': g.kind == 'T', 'sortDate': rmdate.sort_date(enc)}


# ================================================================== families / navigation views
@route('GET', r'/api/family/(\d+)')
def family_get(q, b, fid):
    con = APP.need()
    s = m.settings(con)
    fs = m.family_summary(con, int(fid), s)
    if not fs:
        raise ApiError('Family not found', 404)
    fs['facts'] = m.facts_for(con, 'family', int(fid), s)
    fs['citations'] = m.citations_for(con, 1, int(fid))
    fs['media'] = _media_links(con, 1, int(fid))
    f = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', int(fid))
    fs['raw'] = f
    for who in ('father', 'mother'):
        p = fs[who]
        if p:
            fa, mo, _ = m.primary_parents(con, p['id'])
            p['parents'] = [m.person_summary(con, x, s) if x else None for x in (fa, mo)]
            p['otherSpouses'] = len(m.spouse_families(con, p['id'])) - 1
    for c in fs['children']:
        c['spouses'] = len(m.spouse_families(con, c['id']))
        c['hasChildren'] = any(m.children_of(con, f2['FamilyID']) for f2 in m.spouse_families(con, c['id']))
    return fs


@route('PUT', r'/api/family/(\d+)')
def family_put(q, b, fid):
    con = APP.need()
    allowed = {k: v for k, v in b.items() if k in ('IsPrivate', 'Proof', 'Note', 'SpouseLabel', 'FatherLabel', 'MotherLabel',
                                                   'SpouseLabelStr', 'FatherLabelStr', 'MotherLabelStr', 'FatherID', 'MotherID')}
    update(con, 'FamilyTable', 'FamilyID', int(fid), allowed)
    return {'ok': True}


@route('DELETE', r'/api/family/(\d+)')
def family_delete(q, b, fid):
    m.delete_family(APP.need(), int(fid))
    return {'ok': True}


@route('POST', r'/api/family/(\d+)/swap')
def family_swap(q, b, fid):
    m.swap_couple(APP.need(), int(fid))
    return {'ok': True}


@route('POST', r'/api/family/(\d+)/children')
def family_children(q, b, fid):
    con = APP.need()
    if b.get('sortByBirth'):
        m.sort_children_by_birth(con, int(fid))
    else:
        m.reorder_children(con, int(fid), [int(x) for x in b['order']])
    return {'ok': True}


@route('POST', r'/api/family/(\d+)/unlinkChild')
def family_unlink_child(q, b, fid):
    m.unlink_child(APP.need(), int(fid), int(b['child']))
    return {'ok': True}


@route('POST', r'/api/family/(\d+)/unlinkSpouse')
def family_unlink_spouse(q, b, fid):
    m.unlink_spouse(APP.need(), int(fid), int(b['person']))
    return {'ok': True}


@route('POST', r'/api/family/(\d+)/childRel')
def family_child_rel(q, b, fid):
    APP.need().execute('UPDATE ChildTable SET RelFather=?, RelMother=?, ProofFather=?, ProofMother=? WHERE FamilyID=? AND ChildID=?',
                       (ival(b.get('relFather')), ival(b.get('relMother')), ival(b.get('proofFather')), ival(b.get('proofMother')),
                        int(fid), int(b['child'])))
    return {'ok': True}


@route('POST', r'/api/person/(\d+)/spouseOrder')
def person_spouse_order(q, b, pid):
    m.reorder_spouses(APP.need(), int(pid), [int(x) for x in b['order']])
    return {'ok': True}


@route('POST', r'/api/person/(\d+)/primaryParents')
def person_primary_parents(q, b, pid):
    APP.need().execute('UPDATE PersonTable SET ParentID=? WHERE PersonID=?', (int(b['family']), int(pid)))
    return {'ok': True}


@route('GET', r'/api/pedigree/(\d+)')
def pedigree(q, b, pid):
    con = APP.need()
    s = m.settings(con)
    gens = min(ival(q.get('gens'), 5), 8)
    anc = tools.ancestors(con, int(pid), gens)
    out = {str(k): m.person_summary(con, v, s) for k, v in anc.items()}
    for k, v in anc.items():
        out[str(k)]['hasParents'] = bool(m.parents_of(con, v))
    kids = []
    for f in m.spouse_families(con, int(pid)):
        kids += [m.person_summary(con, c, s) for c in m.children_of(con, f['FamilyID'])]
    return {'people': out, 'children': kids, 'gens': gens,
            'spouses': [m.person_summary(con, f['spouse'], s) for f in m.spouse_families(con, int(pid)) if f['spouse']]}


@route('GET', r'/api/descendants/(\d+)')
def descendants_view(q, b, pid):
    con = APP.need()
    s = m.settings(con)
    gens = min(ival(q.get('gens'), 3), 10)

    def node(p, g):
        n = m.person_summary(con, p, s)
        n['families'] = []
        for f in m.spouse_families(con, p):
            fam = {'id': f['FamilyID'], 'spouse': m.person_summary(con, f['spouse'], s) if f['spouse'] else None,
                   'marriage': m.fact_brief(con, m.first_event(con, f['FamilyID'], (300,), owner=1), s), 'children': []}
            if g < gens:
                fam['children'] = [node(c, g + 1) for c in m.children_of(con, f['FamilyID'])]
            else:
                fam['more'] = len(m.children_of(con, f['FamilyID']))
            n['families'].append(fam)
        return n
    return node(int(pid), 1)


@route('GET', '/api/couples')
def couples(q, b):
    con = APP.need()
    s = m.settings(con)
    out = []
    for f in rows(con, 'SELECT FamilyID, FatherID, MotherID FROM FamilyTable'):
        mar = m.first_event(con, f['FamilyID'], (300,), owner=1)
        fn = m.primary_name(con, f['FatherID']) if f['FatherID'] else {}
        mn = m.primary_name(con, f['MotherID']) if f['MotherID'] else {}
        out.append({'id': f['FamilyID'], 'father': f['FatherID'], 'mother': f['MotherID'],
                    'fatherName': m.fmt_name(fn, 'surname_given') if fn else '', 'motherName': m.fmt_name(mn, 'surname_given') if mn else '',
                    'marriage': rmdate.format(mar['Date'], s['dateFormat']) if mar else '',
                    'place': m.place_name(con, mar['PlaceID']) if mar else '',
                    'children': con.execute('SELECT COUNT(*) FROM ChildTable WHERE FamilyID=?', (f['FamilyID'],)).fetchone()[0]})
    out.sort(key=lambda x: (x['fatherName'].lower(), x['motherName'].lower()))
    return out


@route('GET', '/api/fans')
def fans_list(q, b):
    con = APP.need()
    s = m.settings(con)
    out = []
    for a in rows(con, '''SELECT f.*, t.Name AS TypeName, t.Role1, t.Role2 FROM FANTable f
                          LEFT JOIN FANTypeTable t ON t.FANTypeID=f.FanTypeID'''):
        a['p1'] = m.person_name(con, a['ID1'])
        a['p2'] = m.person_name(con, a['ID2'])
        a['dateText'] = rmdate.format(a['Date'], s['dateFormat'])
        out.append(a)
    return out


@route('POST', '/api/fan')
def fan_save(q, b):
    con = APP.need()
    data = {'ID1': int(b['ID1']), 'ID2': int(b['ID2']), 'FanTypeID': ival(b.get('FanTypeID')), 'Description': b.get('Description', ''),
            'Note': b.get('Note', ''), 'PlaceID': m.get_or_create_place(con, b.get('place', '')), 'SiteID': 0}
    enc = rmdate.encode(b.get('date', ''))
    data.update(Date=enc, SortDate=rmdate.sort_date(enc))
    if b.get('FanID'):
        update(con, 'FANTable', 'FanID', int(b['FanID']), data)
        return {'id': int(b['FanID'])}
    return {'id': insert(con, 'FANTable', data)}


@route('DELETE', r'/api/fan/(\d+)')
def fan_delete(q, b, fid):
    con = APP.need()
    con.execute('DELETE FROM FANTable WHERE FanID=?', (int(fid),))
    m._delete_links(con, OWNER['fan'], int(fid))
    return {'ok': True}


# ================================================================== DNA / health
@route('POST', '/api/dna')
def dna_save(q, b):
    con = APP.need()
    data = {k: b.get(k) for k in ('ID1', 'ID2', 'Label1', 'Label2', 'DNAProvider', 'SharedCM', 'SharedPercent', 'LargeSeg',
                                  'SharedSegs', 'Date', 'Relate1', 'Relate2', 'CommonAnc', 'CommonAncType', 'Verified', 'Note') if k in b}
    if b.get('RecID'):
        update(con, 'DNATable', 'RecID', int(b['RecID']), data)
        return {'id': int(b['RecID'])}
    return {'id': insert(con, 'DNATable', data)}


@route('DELETE', r'/api/dna/(\d+)')
def dna_delete(q, b, rid):
    APP.need().execute('DELETE FROM DNATable WHERE RecID=?', (int(rid),))
    return {'ok': True}


@route('POST', '/api/health')
def health_save(q, b):
    con = APP.need()
    data = {k: b.get(k) for k in ('OwnerID', 'Condition', 'SubCondition', 'Date', 'Note') if k in b}
    if b.get('RecID'):
        update(con, 'HealthTable', 'RecID', int(b['RecID']), data)
        return {'id': int(b['RecID'])}
    return {'id': insert(con, 'HealthTable', data)}


@route('DELETE', r'/api/health/(\d+)')
def health_delete(q, b, rid):
    APP.need().execute('DELETE FROM HealthTable WHERE RecID=?', (int(rid),))
    return {'ok': True}


# ================================================================== generic list tables
TABLES = {  # name: (table, pk, order, default insert values)
    'factTypes': ('FactTypeTable', 'FactTypeID', 'OwnerType, Name COLLATE RMNOCASE',
                  {'OwnerType': 0, 'Abbrev': '', 'GedcomTag': 'EVEN', 'UseValue': 1, 'UseDate': 1, 'UsePlace': 1, 'Sentence': '', 'Flags': 0}),
    'roles': ('RoleTable', 'RoleID', 'EventType, RoleName COLLATE RMNOCASE', {'RoleType': 1, 'Sentence': ''}),
    'fanTypes': ('FANTypeTable', 'FANTypeID', 'Name COLLATE RMNOCASE', {'Role1': '', 'Role2': '', 'Sentence1': '', 'Sentence2': ''}),
    'templates': ('SourceTemplateTable', 'TemplateID', 'Name COLLATE RMNOCASE',
                  {'Description': '', 'Favorite': 0, 'Category': '', 'Footnote': '', 'ShortFootnote': '', 'Bibliography': '',
                   'FieldDefs': '<Root><Fields></Fields></Root>'}),
    'addresses': ('AddressTable', 'AddressID', 'Name COLLATE RMNOCASE',
                  {'AddressType': 0, 'Street1': '', 'Street2': '', 'City': '', 'State': '', 'Zip': '', 'Country': '', 'Phone1': '',
                   'Phone2': '', 'Fax': '', 'Email': '', 'URL': '', 'Latitude': 0, 'Longitude': 0, 'Note': ''}),
    'webtags': ('URLTable', 'LinkID', 'Name', {'LinkType': 0, 'Note': ''}),
    'tags': ('TagTable', 'TagID', 'TagType, TagName COLLATE RMNOCASE', {'TagValue': 0, 'Description': ''}),
}


@route('GET', r'/api/list/(\w+)')
def list_get(q, b, name):
    con = APP.need()
    if name not in TABLES:
        raise ApiError('Unknown list', 404)
    table, pk, order, _ = TABLES[name]
    where, args = [], []
    for k, v in q.items():
        if k in db.table_columns(con, table):
            where.append(f'{k}=?')
            args.append(v)
    out = rows(con, f'SELECT * FROM {table} {"WHERE " + " AND ".join(where) if where else ""} ORDER BY {order}', *args)
    for r in out:
        for k, v in list(r.items()):
            if isinstance(v, bytes):
                r[k] = v.decode('utf-8', 'replace')
    if name == 'factTypes':
        counts = dict(con.execute('SELECT EventType, COUNT(*) FROM EventTable GROUP BY EventType').fetchall())
        for r in out:
            r['uses'] = counts.get(r['FactTypeID'], 0)
    if name == 'templates':
        counts = dict(con.execute('SELECT TemplateID, COUNT(*) FROM SourceTable GROUP BY TemplateID').fetchall())
        for r in out:
            r['uses'] = counts.get(r['TemplateID'], 0)
    if name == 'addresses':
        for r in out:
            r['uses'] = con.execute('SELECT COUNT(*) FROM AddressLinkTable WHERE AddressID=?', (r['AddressID'],)).fetchone()[0]
    return out


@route('POST', r'/api/list/(\w+)')
def list_save(q, b, name):
    con = APP.need()
    table, pk, _, defaults = TABLES[name]
    if b.get(pk):
        update(con, table, pk, int(b[pk]), b)
        return {'id': int(b[pk])}
    data = dict(defaults, **b)
    if name == 'factTypes':
        data['FactTypeID'] = max(1000, con.execute('SELECT MAX(FactTypeID) FROM FactTypeTable').fetchone()[0] + 1)
        if not data.get('Sentence'):
            data['Sentence'] = ('[couple]' if ival(data.get('OwnerType')) else '[person]') + \
                f" {(data.get('Name') or '').lower()}< [Desc]>< [Date]>< [PlaceDetails]>< [Place]>."
    return {'id': insert(con, table, data)}


@route('DELETE', r'/api/list/(\w+)/(\d+)')
def list_delete(q, b, name, rid):
    con = APP.need()
    table, pk, _, _ = TABLES[name]
    rid = int(rid)
    if name == 'factTypes':
        n = con.execute('SELECT COUNT(*) FROM EventTable WHERE EventType=?', (rid,)).fetchone()[0]
        if n:
            raise ApiError(f'This fact type is used by {n} facts and cannot be deleted')
    if name == 'templates' and con.execute('SELECT COUNT(*) FROM SourceTable WHERE TemplateID=?', (rid,)).fetchone()[0]:
        raise ApiError('This template is used by sources and cannot be deleted')
    if name == 'addresses':
        con.execute('DELETE FROM AddressLinkTable WHERE AddressID=?', (rid,))
    con.execute(f'DELETE FROM {table} WHERE {pk}=?', (rid,))
    return {'ok': True}


@route('POST', '/api/addressLink')
def address_link(q, b):
    con = APP.need()
    if b.get('delete'):
        con.execute('DELETE FROM AddressLinkTable WHERE LinkID=?', (int(b['delete']),))
        return {'ok': True}
    return {'id': insert(con, 'AddressLinkTable', {'OwnerType': ival(b.get('ownerType')), 'AddressID': int(b['addressId']),
                                                   'OwnerID': int(b['ownerId']), 'AddressNum': 0, 'Details': b.get('details', '')})}


@route('GET', r'/api/template/(\d+)/fields')
def template_fields(q, b, tid):
    return m.template_fields(APP.need(), int(tid))


@route('POST', r'/api/template/(\d+)/fields')
def template_fields_save(q, b, tid):
    con = APP.need()
    defs = db._tf(*[(f.get('type', 'Text'), f['name'], f.get('display', f['name']), f.get('hint', ''),
                     'True' if f.get('citation') else 'False') for f in b['fields']])
    update(con, 'SourceTemplateTable', 'TemplateID', int(tid), {'FieldDefs': defs})
    return {'ok': True}


@route('POST', '/api/templates/importLibrary')
def templates_import_library(q, b):
    return {'added': tools.import_template_library(APP.need(), os.path.expanduser(b['path']))}


# ================================================================== places
@route('GET', '/api/places')
def places_list(q, b):
    con = APP.need()
    out = rows(con, '''SELECT p.PlaceID, p.PlaceType, p.Name, p.Abbrev, p.Normalized, p.Latitude, p.Longitude, p.MasterID, p.Reverse,
                       (SELECT COUNT(*) FROM EventTable e WHERE e.PlaceID=p.PlaceID OR e.SiteID=p.PlaceID) AS uses
                       FROM PlaceTable p WHERE p.PlaceType IN (0,1) ORDER BY p.Name COLLATE RMNOCASE''')
    return out


@route('GET', r'/api/place/(\d+)')
def place_get(q, b, pid):
    con = APP.need()
    s = m.settings(con)
    p = row(con, 'SELECT * FROM PlaceTable WHERE PlaceID=?', int(pid))
    if not p:
        raise ApiError('Not found', 404)
    evs = []
    for e in rows(con, 'SELECT * FROM EventTable WHERE PlaceID=? OR SiteID=? ORDER BY SortDate', int(pid), int(pid)):
        ft = m.fact_type(con, e['EventType']) or {}
        person = e['OwnerID'] if e['OwnerType'] == 0 else (row(con, 'SELECT FatherID, MotherID FROM FamilyTable WHERE FamilyID=?', e['OwnerID']) or {}).get('FatherID')
        evs.append({'id': e['EventID'], 'fact': ft.get('Name', ''), 'who': m.event_owner_name(con, e), 'person': person,
                    'date': rmdate.format(e['Date'], s['dateFormat']), 'detail': m.place_name(con, e['SiteID'])})
    p['events'] = evs
    p['details'] = rows(con, 'SELECT * FROM PlaceTable WHERE PlaceType=2 AND MasterID=? ORDER BY Name', int(pid))
    p['media'] = _media_links(con, 5, int(pid))
    p['citations'] = m.citations_for(con, 5, int(pid))
    p['webtags'] = rows(con, 'SELECT * FROM URLTable WHERE OwnerType=5 AND OwnerID=?', int(pid))
    return p


@route('POST', '/api/place')
def place_save(q, b):
    con = APP.need()
    data = {k: b[k] for k in ('Name', 'Abbrev', 'Normalized', 'Note', 'PlaceType', 'MasterID') if k in b}
    for k in ('Latitude', 'Longitude'):
        if k in b and b[k] not in (None, ''):
            data[k] = int(round(float(b[k]) * 1e7))
    if 'Name' in data:
        data['Reverse'] = m.reverse_place(data['Name'])
    if b.get('PlaceID'):
        update(con, 'PlaceTable', 'PlaceID', int(b['PlaceID']), data)
        return {'id': int(b['PlaceID'])}
    data.setdefault('PlaceType', 0)
    data.setdefault('MasterID', 0)
    return {'id': insert(con, 'PlaceTable', dict({'Abbrev': '', 'Normalized': '', 'Latitude': 0, 'Longitude': 0, 'LatLongExact': 0,
                                                  'Note': '', 'fsID': 0, 'anID': 0}, **data))}


@route('DELETE', r'/api/place/(\d+)')
def place_delete(q, b, pid):
    con = APP.need()
    with tx(con):
        con.execute('UPDATE EventTable SET PlaceID=0, SiteID=0 WHERE PlaceID=?', (int(pid),))
        con.execute('UPDATE EventTable SET SiteID=0 WHERE SiteID=?', (int(pid),))
        con.execute('DELETE FROM PlaceTable WHERE PlaceID=? OR (PlaceType=2 AND MasterID=?)', (int(pid), int(pid)))
    return {'ok': True}


@route('POST', '/api/places/merge')
def places_merge(q, b):
    con = APP.need()
    for d in b['drop']:
        m.merge_places(con, int(b['keep']), int(d))
    return {'ok': True}


@route('POST', r'/api/place/(\d+)/split')
def place_split(q, b, pid):
    """Move part of a place name into a new place detail (e.g. cemetery name)."""
    con = APP.need()
    p = row(con, 'SELECT * FROM PlaceTable WHERE PlaceID=?', int(pid))
    detail, rest = b['detail'].strip(), b['place'].strip()
    master = m.get_or_create_place(con, rest)
    site = m.get_or_create_place(con, detail, 2, master)
    with tx(con):
        con.execute('UPDATE EventTable SET PlaceID=?, SiteID=? WHERE PlaceID=?', (master, site, p['PlaceID']))
        if master != p['PlaceID']:
            con.execute('DELETE FROM PlaceTable WHERE PlaceID=?', (p['PlaceID'],))
    return {'place': master, 'detail': site}


@route('GET', '/api/geocode')
def geocode(q, b):
    """Look a place up on OpenStreetMap Nominatim (only when the user asks)."""
    text = q.get('q', '')
    url = 'https://nominatim.openstreetmap.org/search?format=json&limit=8&q=' + urllib.parse.quote(text)
    req = urllib.request.Request(url, headers={'User-Agent': 'Dzinde-genealogy/1.0 (local desktop app)'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        raise ApiError(f'Geocoding failed: {e}', 502)
    return [{'name': d.get('display_name'), 'lat': float(d['lat']), 'lon': float(d['lon']), 'type': d.get('type')} for d in data]


@route('GET', '/api/places/map')
def places_map(q, b):
    """Geocoded places with events, optionally for one person."""
    con = APP.need()
    pid = ival(q.get('person'))
    s = m.settings(con)
    if pid:
        evs = rows(con, 'SELECT * FROM EventTable WHERE OwnerType=0 AND OwnerID=? ORDER BY SortDate', pid)
        evs += [e for f in m.spouse_families(con, pid) for e in rows(con, 'SELECT * FROM EventTable WHERE OwnerType=1 AND OwnerID=?', f['FamilyID'])]
    else:
        evs = rows(con, 'SELECT * FROM EventTable WHERE PlaceID>0')
    out = {}
    for e in evs:
        p = row(con, 'SELECT * FROM PlaceTable WHERE PlaceID=?', e['PlaceID'])
        if not p or not (p['Latitude'] or p['Longitude']):
            continue
        d = out.setdefault(p['PlaceID'], {'id': p['PlaceID'], 'name': p['Name'], 'lat': p['Latitude'] / 1e7, 'lon': p['Longitude'] / 1e7, 'events': []})
        ft = m.fact_type(con, e['EventType']) or {}
        d['events'].append({'fact': ft.get('Name', ''), 'who': m.event_owner_name(con, e), 'date': rmdate.format(e['Date'], s['dateFormat']),
                            'sort': e['SortDate']})
    return list(out.values())


# ================================================================== sources / citations
@route('GET', '/api/sources')
def sources_list(q, b):
    con = APP.need()
    return rows(con, '''SELECT s.SourceID, s.Name, s.RefNumber, s.TemplateID, s.IsPrivate, t.Name AS TemplateName,
                        (SELECT COUNT(*) FROM CitationTable c WHERE c.SourceID=s.SourceID) AS citations,
                        (SELECT COUNT(*) FROM CitationLinkTable l JOIN CitationTable c ON c.CitationID=l.CitationID WHERE c.SourceID=s.SourceID) AS uses
                        FROM SourceTable s LEFT JOIN SourceTemplateTable t ON t.TemplateID=s.TemplateID
                        ORDER BY s.Name COLLATE RMNOCASE''')


@route('GET', r'/api/source/(\d+)')
def source_get(q, b, sid):
    con = APP.need()
    s = row(con, 'SELECT * FROM SourceTable WHERE SourceID=?', int(sid))
    if not s:
        raise ApiError('Not found', 404)
    s['Fields'] = m.xml_to_fields(s['Fields'])
    s['fieldDefs'] = m.template_fields(con, s['TemplateID'])
    s['footnote'] = m.render_source_text(con, row(con, 'SELECT * FROM SourceTable WHERE SourceID=?', int(sid)), None, 'Footnote')
    s['bibliography'] = m.render_source_text(con, row(con, 'SELECT * FROM SourceTable WHERE SourceID=?', int(sid)), None, 'Bibliography')
    cits = []
    for c in rows(con, 'SELECT * FROM CitationTable WHERE SourceID=? ORDER BY CitationName, CitationID', int(sid)):
        c['Fields'] = m.xml_to_fields(c['Fields'])
        c['footnote'] = m.render_citation(con, c['CitationID'])
        c['uses'] = [{'linkId': l['LinkID'], 'label': m.citation_owner_label(con, l['OwnerType'], l['OwnerID']), 'ownerType': l['OwnerType'],
                      'ownerId': l['OwnerID'], 'quality': l['Quality']}
                     for l in rows(con, 'SELECT * FROM CitationLinkTable WHERE CitationID=?', c['CitationID'])]
        cits.append(c)
    s['citations'] = cits
    s['repositories'] = rows(con, '''SELECT a.AddressID, a.Name, l.LinkID, l.Details FROM AddressLinkTable l
                                     JOIN AddressTable a ON a.AddressID=l.AddressID WHERE l.OwnerType=3 AND l.OwnerID=?''', int(sid))
    s['media'] = _media_links(con, 3, int(sid))
    s['webtags'] = rows(con, 'SELECT * FROM URLTable WHERE OwnerType=3 AND OwnerID=?', int(sid))
    return s


@route('POST', '/api/source')
def source_save(q, b):
    con = APP.need()
    data = {k: b[k] for k in ('Name', 'RefNumber', 'ActualText', 'Comments', 'IsPrivate', 'TemplateID') if k in b}
    if 'Fields' in b:
        data['Fields'] = m.fields_to_xml(b['Fields'])
    if b.get('SourceID'):
        update(con, 'SourceTable', 'SourceID', int(b['SourceID']), data)
        return {'id': int(b['SourceID'])}
    return {'id': m.add_source(con, data.get('Name', 'New source'), ival(data.get('TemplateID')), b.get('Fields') or {},
                               ref=data.get('RefNumber', ''), text=data.get('ActualText', ''), comments=data.get('Comments', ''))}


@route('DELETE', r'/api/source/(\d+)')
def source_delete(q, b, sid):
    con = APP.need()
    with tx(con):
        for c in rows(con, 'SELECT CitationID FROM CitationTable WHERE SourceID=?', int(sid)):
            con.execute('DELETE FROM CitationLinkTable WHERE CitationID=?', (c['CitationID'],))
            m._delete_links(con, OWNER['citation'], c['CitationID'])
        con.execute('DELETE FROM CitationTable WHERE SourceID=?', (int(sid),))
        m._delete_links(con, OWNER['source'], int(sid))
        con.execute('DELETE FROM SourceTable WHERE SourceID=?', (int(sid),))
    return {'ok': True}


@route('POST', '/api/source/preview')
def source_preview(q, b):
    con = APP.need()
    src = {'TemplateID': ival(b.get('TemplateID')), 'Fields': m.fields_to_xml(b.get('Fields') or {})}
    cit = {'Fields': m.fields_to_xml(b.get('CitationFields') or {})}
    return {k: m.render_source_text(con, src, cit, k) for k in ('Footnote', 'ShortFootnote', 'Bibliography')}


@route('POST', '/api/citation')
def citation_save(q, b):
    """Create a citation (and link), reuse one (citationId), or update fields."""
    con = APP.need()
    if b.get('CitationID') and not b.get('link'):
        data = {k: b[k] for k in ('Comments', 'ActualText', 'RefNumber', 'CitationName') if k in b}
        if 'Fields' in b:
            data['Fields'] = m.fields_to_xml(b['Fields'])
        update(con, 'CitationTable', 'CitationID', int(b['CitationID']), data)
        if 'Quality' in b and b.get('LinkID'):
            con.execute('UPDATE CitationLinkTable SET Quality=? WHERE LinkID=?', (b['Quality'], int(b['LinkID'])))
        return {'id': int(b['CitationID'])}
    cid = m.add_citation(con, ival(b.get('SourceID')), ival(b.get('ownerType')), ival(b.get('ownerId')), b.get('Fields') or {},
                         quality=b.get('Quality', '~~~'), citation_id=ival(b.get('CitationID')) or None,
                         comments=b.get('Comments', ''), text=b.get('ActualText', ''), name=b.get('CitationName', ''))
    return {'id': cid}


@route('GET', r'/api/citation/(\d+)')
def citation_get(q, b, cid):
    con = APP.need()
    c = row(con, 'SELECT * FROM CitationTable WHERE CitationID=?', int(cid))
    if not c:
        raise ApiError('Not found', 404)
    src = row(con, 'SELECT * FROM SourceTable WHERE SourceID=?', c['SourceID']) or {}
    c['Fields'] = m.xml_to_fields(c['Fields'])
    c['source'] = {'SourceID': src.get('SourceID'), 'Name': src.get('Name'), 'TemplateID': src.get('TemplateID')}
    c['fieldDefs'] = [f for f in m.template_fields(con, src.get('TemplateID') or 0) if f['citation']]
    c['footnote'] = m.render_citation(con, int(cid))
    c['shortFootnote'] = m.render_citation(con, int(cid), 'ShortFootnote')
    c['bibliography'] = m.render_citation(con, int(cid), 'Bibliography')
    c['media'] = _media_links(con, 4, int(cid))
    return c


@route('GET', '/api/citations')
def citations_get(q, b):
    return m.citations_for(APP.need(), ival(q.get('ownerType')), ival(q.get('ownerId')))


@route('DELETE', r'/api/citationLink/(\d+)')
def citation_link_delete(q, b, lid):
    con = APP.need()
    l = row(con, 'SELECT * FROM CitationLinkTable WHERE LinkID=?', int(lid))
    con.execute('DELETE FROM CitationLinkTable WHERE LinkID=?', (int(lid),))
    if l and b.get('deleteCitation') and not con.execute('SELECT 1 FROM CitationLinkTable WHERE CitationID=?', (l['CitationID'],)).fetchone():
        con.execute('DELETE FROM CitationTable WHERE CitationID=?', (l['CitationID'],))
    return {'ok': True}


@route('DELETE', r'/api/citation/(\d+)')
def citation_delete(q, b, cid):
    con = APP.need()
    con.execute('DELETE FROM CitationLinkTable WHERE CitationID=?', (int(cid),))
    con.execute('DELETE FROM CitationTable WHERE CitationID=?', (int(cid),))
    return {'ok': True}


@route('POST', '/api/citations/memorize')
def citations_paste(q, b):
    """Paste memorized citations onto an owner (link existing citations)."""
    con = APP.need()
    for cid in b['citations']:
        m.add_citation(con, 0, ival(b['ownerType']), int(b['ownerId']), citation_id=int(cid))
    return {'ok': True}


# ================================================================== media
@route('GET', '/api/media')
def media_list(q, b):
    con = APP.need()
    out = rows(con, '''SELECT MediaID, MediaType, MediaPath, MediaFile, URL, Caption, RefNumber, Date, Description,
                       (SELECT COUNT(*) FROM MediaLinkTable l WHERE l.MediaID=m.MediaID) AS uses
                       FROM MultimediaTable m ORDER BY Caption COLLATE RMNOCASE, MediaFile''')
    s = m.settings(con)
    for r in out:
        r['dateText'] = rmdate.format(r['Date'], s['dateFormat'])
        r['exists'] = bool(r['URL']) or os.path.isfile(m.media_path(r))
        r['tags'] = [{'linkId': l['LinkID'], 'ownerType': l['OwnerType'], 'ownerId': l['OwnerID'],
                      'label': m.citation_owner_label(con, l['OwnerType'], l['OwnerID']) or reports._owner_misc(con, l['OwnerType'], l['OwnerID'])}
                     for l in rows(con, 'SELECT * FROM MediaLinkTable WHERE MediaID=?', r['MediaID'])] if q.get('tags') else []
    return out


@route('GET', r'/api/media/(\d+)')
def media_get(q, b, mid):
    con = APP.need()
    r = row(con, 'SELECT MediaID, MediaType, MediaPath, MediaFile, URL, Caption, RefNumber, Date, Description FROM MultimediaTable WHERE MediaID=?', int(mid))
    if not r:
        raise ApiError('Not found', 404)
    r['dateText'] = rmdate.format(r['Date'], m.settings(con)['dateFormat'])
    r['exists'] = bool(r['URL']) or os.path.isfile(m.media_path(r))
    r['tags'] = [{'linkId': l['LinkID'], 'ownerType': l['OwnerType'], 'ownerId': l['OwnerID'], 'isPrimary': l['IsPrimary'],
                  'label': m.citation_owner_label(con, l['OwnerType'], l['OwnerID']) or reports._owner_misc(con, l['OwnerType'], l['OwnerID'])}
                 for l in rows(con, 'SELECT * FROM MediaLinkTable WHERE MediaID=?', int(mid))]
    return r


@route('POST', '/api/media')
def media_save(q, b):
    """Add (by local path, or upload base64 content into the media folder) or update a media item."""
    con = APP.need()
    if b.get('MediaID'):
        data = {k: b[k] for k in ('Caption', 'RefNumber', 'Description', 'MediaType', 'URL') if k in b}
        if 'Date' in b:
            data['Date'] = rmdate.encode(b['Date'])
            data['SortDate'] = rmdate.sort_date(data['Date'])
        if 'path' in b:
            data['MediaPath'] = os.path.dirname(b['path']) + os.sep
            data['MediaFile'] = os.path.basename(b['path'])
        update(con, 'MultimediaTable', 'MediaID', int(b['MediaID']), data)
        return {'id': int(b['MediaID'])}
    path = os.path.expanduser(b.get('path') or '')
    if b.get('content'):
        import base64
        folder = os.path.expanduser(m.settings(con).get('mediaFolder') or os.path.join(os.path.dirname(APP.path), 'Media'))
        os.makedirs(folder, exist_ok=True)
        name = os.path.basename(b.get('filename') or 'upload.bin')
        path = os.path.join(folder, name)
        stem, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(path):
            path = f'{stem}_{i}{ext}'
            i += 1
        with open(path, 'wb') as f:
            f.write(base64.b64decode(b['content'].split(',', 1)[-1]))
    ext = os.path.splitext(path)[1].lower()
    mtype = ival(b.get('MediaType')) or (1 if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.heic') else
                                         3 if ext in ('.mp3', '.wav', '.m4a', '.ogg') else 4 if ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm') else 2)
    mid = m.add_media(con, path, caption=b.get('Caption') or os.path.splitext(os.path.basename(path))[0], media_type=mtype,
                      url=b.get('URL', ''), description=b.get('Description', ''), date=b.get('Date', ''))
    if b.get('ownerId') is not None and b.get('ownerType') is not None:
        m.link_media(con, mid, ival(b['ownerType']), ival(b['ownerId']), ival(b.get('primary')))
    return {'id': mid}


@route('DELETE', r'/api/media/(\d+)')
def media_delete(q, b, mid):
    con = APP.need()
    con.execute('DELETE FROM MediaLinkTable WHERE MediaID=?', (int(mid),))
    con.execute('DELETE FROM MultimediaTable WHERE MediaID=?', (int(mid),))
    return {'ok': True}


@route('POST', '/api/mediaLink')
def media_link(q, b):
    con = APP.need()
    if b.get('delete'):
        con.execute('DELETE FROM MediaLinkTable WHERE LinkID=?', (int(b['delete']),))
        return {'ok': True}
    if b.get('LinkID'):
        update(con, 'MediaLinkTable', 'LinkID', int(b['LinkID']), b)
        if b.get('IsPrimary'):
            l = row(con, 'SELECT * FROM MediaLinkTable WHERE LinkID=?', int(b['LinkID']))
            con.execute('UPDATE MediaLinkTable SET IsPrimary=0 WHERE OwnerType=? AND OwnerID=? AND LinkID<>?', (l['OwnerType'], l['OwnerID'], l['LinkID']))
        return {'ok': True}
    return {'id': m.link_media(con, int(b['mediaId']), ival(b['ownerType']), int(b['ownerId']), ival(b.get('primary')))}


@route('POST', '/api/media/fix')
def media_fix(q, b):
    """Fix broken media links: search a folder tree for missing files by name and repoint them."""
    con = APP.need()
    folder = os.path.expanduser(b['folder'])
    index = {}
    for root, _, fs in os.walk(folder):
        for f in fs:
            index.setdefault(f.lower(), os.path.join(root, f))
    fixed, missing = 0, []
    for mm in rows(con, "SELECT MediaID, MediaPath, MediaFile FROM MultimediaTable WHERE COALESCE(URL,'')=''"):
        if os.path.isfile(m.media_path(mm)):
            continue
        hit = index.get((mm['MediaFile'] or '').lower())
        if hit:
            if not b.get('preview'):
                con.execute('UPDATE MultimediaTable SET MediaPath=? WHERE MediaID=?', (os.path.dirname(hit) + os.sep, mm['MediaID']))
            fixed += 1
        else:
            missing.append(mm['MediaFile'])
    return {'fixed': fixed, 'missing': missing}


# ================================================================== tasks
@route('GET', '/api/tasks')
def tasks_list(q, b):
    con = APP.need()
    s = m.settings(con)
    where = []
    args = []
    if q.get('type') not in (None, '', 'all'):
        where.append('TaskType=?')
        args.append(ival(q['type']))
    if q.get('status') == 'open':
        where.append('Status IN (0,1)')
    elif q.get('status') == 'done':
        where.append('Status=2')
    out = rows(con, f'SELECT * FROM TaskTable {"WHERE " + " AND ".join(where) if where else ""} ORDER BY Priority, Name COLLATE RMNOCASE', *args)
    for t in out:
        t['date1Text'] = rmdate.format(t['Date1'], s['dateFormat'])
        t['date2Text'] = rmdate.format(t['Date2'], s['dateFormat'])
        t['date3Text'] = rmdate.format(t['Date3'], s['dateFormat'])
        t['links'] = [{'linkId': l['LinkID'], 'ownerType': l['OwnerType'], 'ownerId': l['OwnerID'],
                       'label': m.citation_owner_label(con, l['OwnerType'], l['OwnerID']) or reports._owner_misc(con, l['OwnerType'], l['OwnerID'])}
                      for l in rows(con, 'SELECT * FROM TaskLinkTable WHERE TaskID=?', t['TaskID'])]
    return out


@route('POST', '/api/task')
def task_save(q, b):
    con = APP.need()
    data = {k: b[k] for k in ('TaskType', 'RefNumber', 'Name', 'Status', 'Priority', 'Filename', 'Details', 'Results', 'Exclude') if k in b}
    for i in (1, 2, 3):
        if f'Date{i}' in b:
            data[f'Date{i}'] = rmdate.encode(b[f'Date{i}'])
            data[f'SortDate{i}'] = rmdate.sort_date(data[f'Date{i}'])
    if b.get('TaskID'):
        update(con, 'TaskTable', 'TaskID', int(b['TaskID']), data)
        tid = int(b['TaskID'])
    else:
        base = {'TaskType': 0, 'RefNumber': '', 'Name': 'New task', 'Status': 0, 'Priority': 0, 'Date1': '.', 'Date2': '.', 'Date3': '.',
                'SortDate1': rmdate.EMPTY_SORT, 'SortDate2': rmdate.EMPTY_SORT, 'SortDate3': rmdate.EMPTY_SORT, 'Filename': '',
                'Details': '', 'Results': '', 'Exclude': 0}
        tid = insert(con, 'TaskTable', dict(base, **data))
    if b.get('ownerId') is not None and b.get('ownerType') is not None:
        insert(con, 'TaskLinkTable', {'TaskID': tid, 'OwnerType': ival(b['ownerType']), 'OwnerID': ival(b['ownerId'])})
    return {'id': tid}


@route('DELETE', r'/api/task/(\d+)')
def task_delete(q, b, tid):
    con = APP.need()
    con.execute('DELETE FROM TaskLinkTable WHERE TaskID=?', (int(tid),))
    con.execute('DELETE FROM TaskTable WHERE TaskID=?', (int(tid),))
    return {'ok': True}


@route('POST', '/api/taskLink')
def task_link(q, b):
    con = APP.need()
    if b.get('delete'):
        con.execute('DELETE FROM TaskLinkTable WHERE LinkID=?', (int(b['delete']),))
        return {'ok': True}
    return {'id': insert(con, 'TaskLinkTable', {'TaskID': int(b['taskId']), 'OwnerType': ival(b['ownerType']), 'OwnerID': int(b['ownerId'])})}


# ================================================================== groups & search
@route('GET', '/api/groups')
def groups_list(q, b):
    con = APP.need()
    out = m.groups(con)
    for g in out:
        g['count'] = len(m.group_members(con, g['GroupID']))
    return out


@route('POST', '/api/group')
def group_save(q, b):
    con = APP.need()
    if b.get('GroupID'):
        con.execute('UPDATE TagTable SET TagName=?, Description=? WHERE TagType=0 AND TagValue=?',
                    (b.get('Name', ''), b.get('Description', ''), int(b['GroupID'])))
        gid = int(b['GroupID'])
    else:
        gid = m.create_group(con, b.get('Name') or 'New group', b.get('Description', ''))
    if 'members' in b:
        m.set_group_members(con, gid, [int(x) for x in b['members']])
    if b.get('criteria'):
        ids = [p['id'] for p in run_search(con, b['criteria'], b.get('match', 'all'))]
        if b.get('mode') == 'add':
            ids += m.group_members(con, gid)
        elif b.get('mode') == 'remove':
            ids = [x for x in m.group_members(con, gid) if x not in set(ids)]
        m.set_group_members(con, gid, ids)
    if b.get('add'):
        m.set_group_members(con, gid, m.group_members(con, gid) + [int(x) for x in b['add']])
    if b.get('remove'):
        rem = {int(x) for x in b['remove']}
        m.set_group_members(con, gid, [x for x in m.group_members(con, gid) if x not in rem])
    return {'id': gid, 'count': len(m.group_members(con, gid))}


@route('GET', r'/api/group/(\d+)')
def group_members(q, b, gid):
    con = APP.need()
    s = m.settings(con)
    return [m.person_summary(con, p, s) for p in m.group_members(con, int(gid))]


@route('DELETE', r'/api/group/(\d+)')
def group_delete(q, b, gid):
    m.delete_group(APP.need(), int(gid))
    return {'ok': True}


SEARCH_FIELDS = ['name', 'given', 'surname', 'nickname', 'anyName', 'sex', 'id', 'living', 'private', 'bookmark', 'color',
                 'note', 'hasParents', 'hasSpouse', 'hasChildren', 'spouseCount', 'childCount', 'ancestorOf', 'descendantOf',
                 'relatedTo', 'inGroup', 'factType', 'factDate', 'factPlace', 'factDesc', 'anyPlace', 'hasSource',
                 'hasMedia', 'proof', 'soundex']


def run_search(con, criteria, match='all'):
    """Criteria: [{field, op, value, factType}] ops: contains, equals, startsWith, notContains, before, after, between, exists, missing, is, not"""
    s = m.settings(con)
    ids = [r['PersonID'] for r in rows(con, 'SELECT PersonID FROM PersonTable')]
    cache = {}

    def test(pid, c):
        f, op, v = c.get('field'), c.get('op', 'contains'), str(c.get('value') or '')
        vl = v.lower()

        def text_op(txt):
            t = (txt or '').lower()
            return {'contains': vl in t, 'equals': t == vl, 'startsWith': t.startswith(vl), 'notContains': vl not in t,
                    'exists': bool(t), 'missing': not t, 'is': t == vl, 'not': t != vl}.get(op, vl in t)
        if f in ('name', 'given', 'surname', 'nickname', 'anyName'):
            names = rows(con, 'SELECT * FROM NameTable WHERE OwnerID=?' + ('' if f == 'anyName' else ' AND IsPrimary=1'), pid)
            for n in names:
                val = {'name': m.fmt_name(n), 'given': n['Given'], 'surname': n['Surname'], 'nickname': n['Nickname'],
                       'anyName': m.fmt_name(n, 'full')}[f]
                if text_op(val):
                    return op != 'notContains' or len(names) == 1
            return op in ('notContains', 'missing') and not names
        if f == 'soundex':
            return m.soundex(m.primary_name(con, pid).get('Surname')) == m.soundex(v)
        if f in ('sex', 'living', 'private', 'bookmark', 'color', 'proof'):
            p = cache.setdefault(pid, row(con, 'SELECT * FROM PersonTable WHERE PersonID=?', pid))
            col = {'sex': 'Sex', 'living': 'Living', 'private': 'IsPrivate', 'bookmark': 'Bookmark', 'color': 'Color', 'proof': 'Proof'}[f]
            if f == 'color' and s.get('activeColorSet'):
                col = f'Color{s["activeColorSet"]}'
            ok = str(p[col] or 0) == (v or '1')
            return ok if op != 'not' else not ok
        if f == 'id':
            nums = [int(x) for x in v.replace('-', ' ').split() if x.isdigit()]
            return (nums[0] <= pid <= nums[-1]) if op == 'between' and nums else pid in nums
        if f == 'note':
            return text_op(row(con, 'SELECT Note FROM PersonTable WHERE PersonID=?', pid)['Note'])
        if f == 'hasParents':
            return bool(m.parents_of(con, pid)) == (op != 'not')
        if f == 'hasSpouse':
            return any(x['spouse'] for x in m.spouse_families(con, pid)) == (op != 'not')
        if f == 'hasChildren':
            return any(m.children_of(con, x['FamilyID']) for x in m.spouse_families(con, pid)) == (op != 'not')
        if f in ('spouseCount', 'childCount'):
            n = len([x for x in m.spouse_families(con, pid) if x['spouse']]) if f == 'spouseCount' else \
                sum(len(m.children_of(con, x['FamilyID'])) for x in m.spouse_families(con, pid))
            k = int(v or 0)
            return {'equals': n == k, 'is': n == k, 'after': n > k, 'before': n < k, 'not': n != k}.get(op, n == k)
        if f in ('ancestorOf', 'descendantOf', 'relatedTo'):
            key = (f, v)
            if key not in cache:
                t = int(v)
                cache[key] = set(tools.all_ancestors(con, t)) if f == 'ancestorOf' else \
                    tools.all_descendants(con, t) if f == 'descendantOf' else {k['person']['id'] for k in tools.kinship_list(con, t)}
            return (pid in cache[key]) == (op != 'not')
        if f == 'inGroup':
            key = ('g', v)
            if key not in cache:
                cache[key] = set(m.group_members(con, int(v)))
            return (pid in cache[key]) == (op != 'not')
        if f in ('factType', 'factDate', 'factPlace', 'factDesc'):
            ft = ival(c.get('factType'))
            evs = rows(con, 'SELECT * FROM EventTable WHERE OwnerType=0 AND OwnerID=?' + (' AND EventType=?' if ft else ''), pid, *([ft] if ft else []))
            for fam in m.spouse_families(con, pid):
                evs += rows(con, 'SELECT * FROM EventTable WHERE OwnerType=1 AND OwnerID=?' + (' AND EventType=?' if ft else ''), fam['FamilyID'], *([ft] if ft else []))
            if f == 'factType':
                return bool(evs) == (op != 'missing' and op != 'not')
            if op == 'missing':
                return not any((e['Date'] not in ('', '.')) if f == 'factDate' else e['PlaceID'] if f == 'factPlace' else e['Details'] for e in evs)
            for e in evs:
                if f == 'factDate':
                    y = rmdate.year(e['Date'])
                    nums = [int(x) for x in v.replace('-', ' ').split() if x.lstrip('-').isdigit()]
                    if op == 'exists' and e['Date'] not in ('', '.'):
                        return True
                    if not y or not nums:
                        continue
                    if (op == 'before' and y < nums[0]) or (op == 'after' and y > nums[0]) or \
                            (op == 'between' and nums[0] <= y <= nums[-1]) or (op in ('equals', 'is', 'contains') and y == nums[0]):
                        return True
                elif f == 'factPlace':
                    if text_op(m.place_name(con, e['PlaceID']) + ' ' + m.place_name(con, e['SiteID'])):
                        return True
                elif text_op(e['Details']):
                    return True
            return False
        if f == 'anyPlace':
            return any(text_op(m.place_name(con, e['PlaceID'])) for e in rows(con, 'SELECT PlaceID FROM EventTable WHERE OwnerType=0 AND OwnerID=?', pid))
        if f == 'hasSource':
            has = bool(row(con, '''SELECT 1 AS x FROM CitationLinkTable WHERE (OwnerType=0 AND OwnerID=?) OR (OwnerType=2 AND OwnerID IN
                                  (SELECT EventID FROM EventTable WHERE OwnerType=0 AND OwnerID=?))''', pid, pid))
            return has == (op != 'not')
        if f == 'hasMedia':
            return bool(row(con, 'SELECT 1 AS x FROM MediaLinkTable WHERE OwnerType=0 AND OwnerID=?', pid)) == (op != 'not')
        return False
    out = []
    for pid in ids:
        results = (test(pid, c) for c in criteria)
        if (all(results) if match == 'all' else any(results)):
            out.append(m.person_summary(con, pid, s))
    out.sort(key=lambda p: (p['surname'].lower(), p['given'].lower()))
    return out


@route('POST', '/api/search')
def search(q, b):
    con = APP.need()
    res = run_search(con, b.get('criteria') or [], b.get('match', 'all'))
    if b.get('saveAs'):
        insert(con, 'PayloadTable', {'RecType': 1, 'OwnerType': 0, 'OwnerID': 0, 'Title': b['saveAs'],
                                     'DataRec': json.dumps({'criteria': b['criteria'], 'match': b.get('match', 'all')})})
    return res


@route('GET', '/api/savedSearches')
def saved_searches(q, b):
    return [{'id': r['RecID'], 'title': r['Title'], 'data': json.loads(r['DataRec'])}
            for r in rows(APP.need(), 'SELECT * FROM PayloadTable WHERE RecType=1 ORDER BY Title')
            if isinstance(r['DataRec'], (str, bytes)) and _is_json(r['DataRec'])]


def _is_json(s):
    try:
        json.loads(s)
        return True
    except ValueError:
        return False


@route('DELETE', r'/api/savedSearch/(\d+)')
def saved_search_delete(q, b, rid):
    APP.need().execute('DELETE FROM PayloadTable WHERE RecID=? AND RecType=1', (int(rid),))
    return {'ok': True}


@route('GET', '/api/find')
def find(q, b):
    return tools.find_everywhere(APP.need(), q.get('q', ''))


@route('POST', '/api/replace')
def replace(q, b):
    return tools.search_replace(APP.need(), b['find'], b.get('replace', ''), b.get('fields'), bool(b.get('wholeWord')),
                                bool(b.get('caseSensitive')), bool(b.get('preview', True)))


# ================================================================== tools
@route('POST', r'/api/tools/(\w+)')
def tool(q, b, name):
    con = APP.need()
    s = m.settings(con)
    if name == 'countTrees':
        return [{k: v for k, v in t.items() if k != 'members'} | {'members': t['members'][:5000]} for t in tools.count_trees(con)]
    if name == 'setLiving':
        return {'changed': tools.set_living(con, ival(b.get('years'), 110))}
    if name == 'setRelationships':
        return {'set': tools.set_relationships(con, int(b['root']))}
    if name == 'clearRelationships':
        con.execute('UPDATE PersonTable SET Relate1=0, Relate2=0')
        return {'ok': True}
    if name == 'relationship':
        a, c = int(b['a']), int(b['b'])
        rel = tools.relationships(con, a, c)
        for r in rel:
            r['ancestors'] = [m.person_summary(con, x, s) for x in r['ancestors']]
        return {'a': m.person_summary(con, a, s), 'b': m.person_summary(con, c, s), 'relationships': rel}
    if name == 'kinship':
        return tools.kinship_list(con, int(b['person']))
    if name == 'duplicates':
        return tools.find_duplicates(con, ival(b.get('minScore'), 60), b.get('soundex', True))
    if name == 'merge':
        tools.merge_people(con, int(b['keep']), int(b['drop']))
        return {'ok': True}
    if name == 'notDuplicate':
        tools.not_duplicate(con, int(b['a']), int(b['b']))
        return {'ok': True}
    if name == 'clearNotDuplicates':
        con.execute('DELETE FROM ExclusionTable WHERE ExclusionType=1')
        return {'ok': True}
    if name == 'notDuplicateList':
        return [{'id': r['RecID'], 'a': m.person_summary(con, r['ID1'], s), 'b': m.person_summary(con, r['ID2'], s)}
                for r in rows(con, 'SELECT * FROM ExclusionTable WHERE ExclusionType=1')
                if row(con, 'SELECT 1 AS x FROM PersonTable WHERE PersonID=?', r['ID1']) and row(con, 'SELECT 1 AS x FROM PersonTable WHERE PersonID=?', r['ID2'])]
    if name == 'deleteExclusion':
        con.execute('DELETE FROM ExclusionTable WHERE RecID=?', (int(b['id']),))
        return {'ok': True}
    if name == 'autoMerge':
        return {'merged': tools.auto_merge(con)}
    if name == 'problems':
        return {'rules': tools.PROBLEM_RULES, 'defaults': tools.PROBLEM_DEFAULTS,
                'problems': tools.problem_list(con, b.get('options'), b.get('rules'))}
    if name == 'notProblem':
        tools.not_a_problem(con, int(b['person']), int(b['ruleId']))
        return {'ok': True}
    if name == 'notProblemList':
        rules = list(tools.PROBLEM_RULES.values())
        return [{'id': r['RecID'], 'person': m.person_summary(con, r['ID1'], s), 'rule': rules[r['ID2']] if r['ID2'] < len(rules) else ''}
                for r in rows(con, 'SELECT * FROM ExclusionTable WHERE ExclusionType=2') if row(con, 'SELECT 1 AS x FROM PersonTable WHERE PersonID=?', r['ID1'])]
    if name == 'nameClean':
        return tools.name_issues(con)
    if name == 'nameCleanApply':
        return {'fixed': tools.apply_name_fixes(con, b['fixes'])}
    if name == 'placeClean':
        return tools.place_issues(con)
    if name == 'placeCleanApply':
        return {'fixed': tools.apply_place_fixes(con, b['fixes'])}
    if name == 'db':
        return tools.db_tools(con, b['action'])
    if name == 'colorCode':
        ids = [int(x) for x in b.get('ids') or []]
        if b.get('who'):
            ids = _people_for(con, b['who'])
        if b.get('criteria'):
            ids = [p['id'] for p in run_search(con, b['criteria'], b.get('match', 'all'))]
        return {'colored': tools.color_people(con, ids, ival(b.get('color')), ival(b.get('colorSet')))}
    if name == 'clearColors':
        col = 'Color' if not ival(b.get('colorSet')) else f'Color{ival(b.get("colorSet"))}'
        con.execute(f'UPDATE PersonTable SET {col}=0')
        return {'ok': True}
    if name == 'onThisDay':
        return tools.on_this_day(con, int(b['month']), int(b['day']))
    if name == 'whoWasThere':
        return tools.who_was_there(con, b.get('place', ''), int(b['from']), int(b['to']))
    if name == 'statistics':
        return tools.statistics(con)
    if name == 'aiPrompt':
        return {'prompt': tools.ai_prompt(con, int(b['person']), b.get('goal') or 'Suggest next research steps')}
    if name == 'webSearch':
        return tools.web_search_urls(con, int(b['person']))
    if name == 'dateCalc':
        return date_calc(b)
    if name == 'soundex':
        return {'code': m.soundex(b.get('name', '')), 'matches': [r for r in rows(con, '''SELECT DISTINCT Surname FROM NameTable
                 WHERE Surname<>'' ORDER BY Surname''') if m.soundex(r['Surname']) == m.soundex(b.get('name', ''))][:200]}
    if name == 'website':
        out = os.path.expanduser(b.get('folder') or os.path.join(os.path.dirname(APP.path), 'Website'))
        return {'path': website.generate(con, out, _people_for(con, b.get('who', 'all')), b.get('options') or {})}
    raise ApiError('Unknown tool', 404)


def date_calc(b):
    import datetime as dt
    mode = b.get('mode')
    if mode == 'between':
        a = rmdate.age_between(rmdate.encode(b['date1']), rmdate.encode(b['date2']))
        if not a:
            a2 = rmdate.age_between(rmdate.encode(b['date2']), rmdate.encode(b['date1']))
            a = a2
        return {'years': a[0], 'months': a[1], 'days': a[2]} if a else {'error': 'Enter two complete dates'}
    if mode in ('add', 'birthFromAge'):
        y = rmdate.ymd(rmdate.encode(b['date1']))
        if not y:
            return {'error': 'Enter a date'}
        sign = -1 if mode == 'birthFromAge' or b.get('subtract') else 1
        yrs, mos, dys = (ival(b.get(k)) for k in ('years', 'months', 'days'))
        base = dt.date(y[0], y[1] or 1, y[2] or 1)
        total_months = base.year * 12 + base.month - 1 + sign * (yrs * 12 + mos)
        yy, mm = divmod(total_months, 12)
        day = min(base.day, calendar_days(yy, mm + 1))
        res = dt.date(yy, mm + 1, day) + dt.timedelta(days=sign * dys)
        return {'result': rmdate.format(rmdate.encode(res.isoformat()), 'dmy'), 'weekday': res.strftime('%A')}
    if mode == 'weekday':
        y = rmdate.ymd(rmdate.encode(b['date1']))
        if not y or not y[2]:
            return {'error': 'Enter a full date'}
        return {'weekday': dt.date(*y).strftime('%A')}
    raise ApiError('Unknown date calc mode')


def calendar_days(y, mo):
    import calendar
    return calendar.monthrange(y, mo)[1]


# ================================================================== reports & books
@route('GET', '/api/reports')
def reports_catalog(q, b):
    return reports.catalog()


@route('POST', '/api/reports/run')
def reports_run(q, b):
    return {'html': reports.run(APP.need(), b['id'], b.get('options') or {})}


@route('GET', '/api/books')
def books_list(q, b):
    return [{'id': r['RecID'], 'title': r['Title'], 'data': json.loads(r['DataRec'])}
            for r in rows(APP.need(), 'SELECT * FROM PayloadTable WHERE RecType=2 ORDER BY Title') if _is_json(r['DataRec'])]


@route('POST', '/api/book')
def book_save(q, b):
    con = APP.need()
    data = json.dumps({'items': b.get('items', []), 'subtitle': b.get('subtitle', ''), 'author': b.get('author', '')})
    if b.get('id'):
        update(con, 'PayloadTable', 'RecID', int(b['id']), {'Title': b.get('title', 'Book'), 'DataRec': data})
        return {'id': int(b['id'])}
    return {'id': insert(con, 'PayloadTable', {'RecType': 2, 'OwnerType': 0, 'OwnerID': 0, 'Title': b.get('title', 'Book'), 'DataRec': data})}


@route('DELETE', r'/api/book/(\d+)')
def book_delete(q, b, bid):
    APP.need().execute('DELETE FROM PayloadTable WHERE RecID=? AND RecType=2', (int(bid),))
    return {'ok': True}


@route('POST', r'/api/book/(\d+)/build')
def book_build(q, b, bid):
    """Concatenate title page, table of contents, text chapters and report chapters into one printable document."""
    from html import escape as E
    con = APP.need()
    r = row(con, 'SELECT * FROM PayloadTable WHERE RecID=?', int(bid))
    data = json.loads(r['DataRec'])
    body, toc = [], []
    for i, it in enumerate(data.get('items', []), 1):
        title = it.get('title') or (reports.REPORTS.get(it.get('report'), {}).get('title') if it.get('report') else 'Chapter')
        toc.append(f'<li><a href="#ch{i}">{E(title)}</a></li>')
        if it.get('report'):
            html = reports.run(con, it['report'], it.get('options') or {})
            inner = html.split('<body>', 1)[1].rsplit('</body>', 1)[0]
            inner = inner.split('</h1>', 1)[1] if '</h1>' in inner else inner
        else:
            inner = m.note_to_html(it.get('text', ''))
        body.append(f'<section id="ch{i}" style="break-before:page"><h1>{E(title)}</h1>{inner}</section>')
    s = m.settings(con)
    author = data.get('author') or (s.get('preparer') or {}).get('name', '')
    html = (f'<!doctype html><html><head><meta charset="utf-8"><title>{E(r["Title"])}</title><style>{reports.PAGE_CSS}'
            f'.title{{text-align:center;margin-top:30vh}}.title h1{{font-size:32pt}}</style></head><body>'
            f'<div class="title"><h1>{E(r["Title"])}</h1><p>{E(data.get("subtitle", ""))}</p><p>{E(author)}</p></div>'
            f'<section style="break-before:page"><h2>Contents</h2><ol>{"".join(toc)}</ol></section>{"".join(body)}</body></html>')
    return {'html': html}


# ================================================================== bookmarks / misc
@route('GET', '/api/bookmarks')
def bookmarks(q, b):
    con = APP.need()
    s = m.settings(con)
    return [m.person_summary(con, r['PersonID'], s) for r in rows(con, 'SELECT PersonID FROM PersonTable WHERE Bookmark=1')]


@route('GET', '/api/home')
def home(q, b):
    con = APP.need()
    s = m.settings(con)
    import datetime as dt
    today = dt.date.today()
    st = tools.statistics(con)
    recent = [m.person_summary(con, r['PersonID'], s) for r in rows(con, 'SELECT PersonID FROM PersonTable ORDER BY UTCModDate DESC LIMIT 8')]
    return {'stats': st, 'onThisDay': tools.on_this_day(con, today.month, today.day)[:20], 'recent': recent,
            'root': m.person_summary(con, s.get('rootPersonId'), s) if s.get('rootPersonId') else None,
            'openTasks': con.execute('SELECT COUNT(*) FROM TaskTable WHERE Status IN (0,1)').fetchone()[0],
            'file': _file_info(APP.path)}


@route('GET', '/api/meta')
def meta(q, b):
    """Static enumerations for the UI."""
    con = APP.con
    return {'sex': m.SEX, 'nameTypes': m.NAME_TYPES, 'childRel': m.CHILD_REL, 'proof': m.PROOF, 'taskStatus': m.TASK_STATUS,
            'taskType': m.TASK_TYPE, 'priority': m.PRIORITY, 'mediaTypes': m.MEDIA_TYPES, 'health': m.HEALTH_CONDITIONS,
            'dnaProviders': m.DNA_PROVIDERS, 'quality': m.QUALITY, 'dateFormats': {k: v[0] for k, v in rmdate.FORMATS.items()},
            'searchFields': SEARCH_FIELDS, 'problemRules': tools.PROBLEM_RULES, 'searchable': [x[3] for x in tools.SEARCHABLE],
            'factTypes': m.fact_types(con) if con else [], 'version': __import__('dzinde').__version__}


# ================================================================== HTTP plumbing
class Handler(BaseHTTPRequestHandler):
    server_version = 'Dzinde'

    def log_message(self, fmt, *args):
        if os.environ.get('DZINDE_DEBUG'):
            super().log_message(fmt, *args)

    def _host_ok(self):
        host = (self.headers.get('Host') or '').split(':')[0]
        return host in ('127.0.0.1', 'localhost')

    def _send(self, status, body, ctype='application/json; charset=utf-8', extra=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _dispatch(self, method):
        if not self._host_ok():
            return self._send(403, '{"error":"bad host"}')
        url = urllib.parse.urlparse(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        path = url.path
        if method == 'GET' and (m_ := re.match(r'^/api/media/(\d+)/file$', path)):
            return self._media_file(int(m_[1]))
        if method == 'GET' and path == '/report':
            return self._report_page(q)
        if path.startswith('/api/'):
            if self.headers.get('X-Dzinde') != '1':  # forces CORS preflight -> blocks cross-site requests
                return self._send(403, '{"error":"missing X-Dzinde header"}')
            body = {}
            n = int(self.headers.get('Content-Length') or 0)
            if n:
                try:
                    body = json.loads(self.rfile.read(n).decode('utf-8'))
                except ValueError:
                    return self._send(400, '{"error":"bad json"}')
            for meth, rx, fn in ROUTES:
                if meth == method and (mm := rx.match(path)):
                    try:
                        with APP.lock:
                            res = fn(q, body, *mm.groups())
                        return self._send(200, json.dumps(res, default=_json_default))
                    except ApiError as e:
                        return self._send(e.status, json.dumps({'error': str(e)}))
                    except Exception as e:  # report, keep serving
                        traceback.print_exc()
                        return self._send(500, json.dumps({'error': f'{type(e).__name__}: {e}'}))
            return self._send(404, '{"error":"not found"}')
        return self._static(path)

    def _media_file(self, mid):
        con = APP.con
        r = row(con, 'SELECT MediaPath, MediaFile, URL FROM MultimediaTable WHERE MediaID=?', mid) if con else None
        p = m.media_path(r) if r else ''
        if not r or not os.path.isfile(p):
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#eee"/>'
                   '<text x="60" y="64" font-size="12" text-anchor="middle" fill="#999" font-family="sans-serif">missing</text></svg>')
            return self._send(200, svg, 'image/svg+xml')
        with open(p, 'rb') as f:
            data = f.read()
        self._send(200, data, mimetypes.guess_type(p)[0] or 'application/octet-stream')

    def _report_page(self, q):
        try:
            html = reports.run(APP.need(), q['id'], json.loads(q.get('opts') or '{}'))
        except Exception as e:
            html = f'<p>Report error: {e}</p>'
        self._send(200, html, 'text/html; charset=utf-8')

    def _static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
        if not full.startswith(WEB) or not os.path.isfile(full):
            full = os.path.join(WEB, 'index.html')
        with open(full, 'rb') as f:
            data = f.read()
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype.endswith('javascript'):
            ctype += '; charset=utf-8'
        self._send(200, data, ctype)

    def do_GET(self):
        self._dispatch('GET')

    def do_HEAD(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def do_PUT(self):
        self._dispatch('PUT')

    def do_DELETE(self):
        self._dispatch('DELETE')


def _json_default(o):
    if isinstance(o, bytes):
        return o.decode('utf-8', 'replace')
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def start(port=8642, open_file=None):
    """Open the requested (or last) file and bind the server; port 0 picks a free one."""
    if open_file:
        APP.open(open_file)
    elif APP.conf.get('lastFile') and os.path.isfile(APP.conf['lastFile']):
        try:
            APP.open(APP.conf['lastFile'])
        except Exception:
            pass
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(port=8642, open_file=None, open_browser=True):
    httpd = start(port, open_file)
    url = f'http://127.0.0.1:{port}/'
    print(f'Dzinde running at {url}  (Ctrl+C to quit)')
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        APP.close()
