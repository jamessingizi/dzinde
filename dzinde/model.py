"""Genealogy domain operations on top of the RM schema: people, families, facts, names,
places, sources/citations, media, notes, sentences. Pure functions taking a connection."""
import re
import xml.etree.ElementTree as ET
from html import escape

from . import rmdate, templates
from .db import OWNER, insert, row, rows, tx, unique_id, update, utc_now

SEX = {0: 'Male', 1: 'Female', 2: 'Unknown'}
NAME_TYPES = {0: '', 1: 'AKA', 2: 'Birth', 3: 'Immigrant', 4: 'Maiden', 5: 'Married', 6: 'Nickname',
              7: 'Other spelling'}
CHILD_REL = {0: 'Birth', 1: 'Adopted', 2: 'Step', 3: 'Foster', 4: 'Related', 5: 'Guardian', 6: 'Sealed',
             7: 'Unknown'}
PROOF = {0: '', 1: 'Proven', 2: 'Disproven', 3: 'Disputed'}
TASK_STATUS = {0: 'Open', 1: 'In progress', 2: 'Completed', 3: 'Cancelled'}
TASK_TYPE = {0: 'To-do', 1: 'Research log', 2: 'Correspondence'}
PRIORITY = {0: 'None', 1: 'Highest', 2: 'Very high', 3: 'High', 4: 'Medium', 5: 'Low', 6: 'Very low', 7: 'Lowest'}
MEDIA_TYPES = {1: 'Image', 2: 'File', 3: 'Sound', 4: 'Video'}
HEALTH_CONDITIONS = ['Cancer', 'Heart disease', 'Stroke', 'Diabetes', 'High blood pressure', 'High cholesterol',
                     'Asthma', 'Alzheimer\'s / dementia', 'Depression', 'Mental illness', 'Kidney disease',
                     'Liver disease', 'Osteoporosis', 'Arthritis', 'Birth defect', 'Genetic disorder',
                     'Allergy', 'Vision', 'Hearing', 'Other']
DNA_PROVIDERS = {0: '', 1: 'AncestryDNA', 2: '23andMe', 3: 'FamilyTreeDNA', 4: 'MyHeritage', 5: 'LivingDNA',
                 6: 'GEDmatch', 7: 'Other'}


# ------------------------------------------------------------------ settings
def settings(con):
    import json
    from .db import DEFAULT_SETTINGS, DZ_CONFIG
    r = row(con, 'SELECT DataRec FROM ConfigTable WHERE RecType=? AND Title=?', DZ_CONFIG, 'Settings')
    s = dict(DEFAULT_SETTINGS)
    if r and r['DataRec']:
        try:
            data = r['DataRec']
            s.update(json.loads(data.decode() if isinstance(data, bytes) else data))
        except ValueError:
            pass
    return s


def save_settings(con, new):
    import json
    from .db import DZ_CONFIG
    s = settings(con)
    s.update(new)
    blob = json.dumps(s)
    r = row(con, 'SELECT RecID FROM ConfigTable WHERE RecType=? AND Title=?', DZ_CONFIG, 'Settings')
    if r:
        update(con, 'ConfigTable', 'RecID', r['RecID'], {'DataRec': blob})
    else:
        insert(con, 'ConfigTable', {'RecType': DZ_CONFIG, 'Title': 'Settings', 'DataRec': blob})
    return s


# ------------------------------------------------------------------ names
def primary_name(con, pid):
    return row(con, 'SELECT * FROM NameTable WHERE OwnerID=? AND IsPrimary=1', pid) or \
        row(con, 'SELECT * FROM NameTable WHERE OwnerID=? ORDER BY NameID LIMIT 1', pid) or {}


def fmt_name(n, style='given_surname', caps=False):
    if not n:
        return ''
    sur = (n.get('Surname') or '')
    if caps:
        sur = sur.upper()
    given, pre, suf = n.get('Given') or '', n.get('Prefix') or '', n.get('Suffix') or ''
    nick = n.get('Nickname') or ''
    if style == 'surname_given':
        s = ', '.join(x for x in (sur, ' '.join(x for x in (given,) if x)) if x)
        return s + (f', {suf}' if suf else '')
    if style == 'full':
        mid = f' "{nick}"' if nick else ''
        return ' '.join(x for x in (pre, given + mid, sur, suf) if x)
    s = ' '.join(x for x in (given, sur) if x)
    return s + (f' {suf}' if suf else '')


def person_name(con, pid, style='given_surname', caps=False):
    return fmt_name(primary_name(con, pid), style, caps) if pid else ''


def _name_years(con, pid):
    b = first_event(con, pid, (1, 3, 7))
    d = first_event(con, pid, (2, 4, 5))
    return rmdate.year(b['Date']) if b else 0, rmdate.year(d['Date']) if d else 0


def refresh_name_years(con, pid):
    """RM caches birth/death years on NameTable for fast lists."""
    by, dy = _name_years(con, pid)
    con.execute('UPDATE NameTable SET BirthYear=?, DeathYear=? WHERE OwnerID=?', (by, dy, pid))


def soundex(s):
    s = ''.join(c for c in (s or '').upper() if c.isalpha())
    if not s:
        return ''
    codes = {**dict.fromkeys('BFPV', '1'), **dict.fromkeys('CGJKQSXZ', '2'), **dict.fromkeys('DT', '3'),
             'L': '4', **dict.fromkeys('MN', '5'), 'R': '6'}
    out, last = s[0], codes.get(s[0], '')
    for c in s[1:]:
        code = codes.get(c, '')
        if code and code != last:
            out += code
        if c not in 'HW':
            last = code
    return (out + '000')[:4]


def metaphone_key(s):
    """Cheap phonetic key for 'MP' columns (RM uses metaphone; we store a soundex-style key)."""
    return soundex(s)


def save_name(con, data):
    """Insert/update a NameTable row from a dict (NameID optional)."""
    d = {k: data.get(k) for k in ('OwnerID', 'Surname', 'Given', 'Prefix', 'Suffix', 'Nickname', 'NameType',
                                  'IsPrimary', 'IsPrivate', 'Proof', 'Sentence', 'Note', 'Display', 'Language')
         if k in data}
    if 'Date' in data:
        d['Date'] = rmdate.encode(data['Date'])
        d['SortDate'] = rmdate.sort_date(d['Date'])
    for k in ('Surname', 'Given', 'Nickname'):
        if k in d:
            d[k + 'MP'] = metaphone_key(d[k])
    if data.get('NameID'):
        update(con, 'NameTable', 'NameID', data['NameID'], d)
        nid = data['NameID']
    else:
        d.setdefault('NameType', 0)
        d.setdefault('IsPrimary', 0)
        d.setdefault('SortDate', rmdate.EMPTY_SORT)
        nid = insert(con, 'NameTable', d)
    owner = data.get('OwnerID') or row(con, 'SELECT OwnerID FROM NameTable WHERE NameID=?', nid)['OwnerID']
    if d.get('IsPrimary'):
        con.execute('UPDATE NameTable SET IsPrimary=0 WHERE OwnerID=? AND NameID<>?', (owner, nid))
    refresh_name_years(con, owner)
    return nid


# ------------------------------------------------------------------ people
def add_person(con, given='', surname='', sex=2, **kw):
    with tx(con):
        pid = insert(con, 'PersonTable', {'UniqueID': unique_id(), 'Sex': sex, 'ParentID': 0, 'SpouseID': 0,
                                          'Color': 0, 'Relate1': 0, 'Relate2': 0, 'Flags': 0,
                                          'Living': kw.get('living', 0), 'IsPrivate': 0, 'Proof': 0,
                                          'Bookmark': 0, 'Note': kw.get('note', '')})
        save_name(con, {'OwnerID': pid, 'Given': given, 'Surname': surname, 'Prefix': kw.get('prefix', ''),
                        'Suffix': kw.get('suffix', ''), 'Nickname': kw.get('nickname', ''), 'IsPrimary': 1,
                        'NameType': 0})
        for ftype, key in ((1, 'birth'), (2, 'death')):
            if kw.get(key + '_date') or kw.get(key + '_place'):
                add_fact(con, 'person', pid, ftype, date=kw.get(key + '_date', ''), place=kw.get(key + '_place', ''))
    return pid


def delete_person(con, pid):
    with tx(con):
        for f in rows(con, 'SELECT FamilyID, FatherID, MotherID FROM FamilyTable WHERE FatherID=? OR MotherID=?',
                      pid, pid):
            col = 'FatherID' if f['FatherID'] == pid else 'MotherID'
            con.execute(f'UPDATE FamilyTable SET {col}=0 WHERE FamilyID=?', (f['FamilyID'],))
            _prune_family(con, f['FamilyID'])
        for c in rows(con, 'SELECT FamilyID FROM ChildTable WHERE ChildID=?', pid):
            con.execute('DELETE FROM ChildTable WHERE ChildID=? AND FamilyID=?', (pid, c['FamilyID']))
            _prune_family(con, c['FamilyID'])
        for e in rows(con, 'SELECT EventID FROM EventTable WHERE OwnerType=0 AND OwnerID=?', pid):
            _delete_event(con, e['EventID'])
        for n in rows(con, 'SELECT NameID FROM NameTable WHERE OwnerID=?', pid):
            _delete_links(con, OWNER['name'], n['NameID'])
        con.execute('DELETE FROM NameTable WHERE OwnerID=?', (pid,))
        con.execute('DELETE FROM WitnessTable WHERE PersonID=?', (pid,))
        con.execute('DELETE FROM FANTable WHERE ID1=? OR ID2=?', (pid, pid))
        con.execute('DELETE FROM DNATable WHERE ID1=? OR ID2=?', (pid, pid))
        con.execute('DELETE FROM HealthTable WHERE OwnerID=?', (pid,))
        _delete_links(con, OWNER['person'], pid)
        remove_from_all_groups(con, pid)
        con.execute('DELETE FROM PersonTable WHERE PersonID=?', (pid,))


def _delete_links(con, otype, oid):
    for t in ('CitationLinkTable', 'MediaLinkTable', 'TaskLinkTable', 'URLTable', 'AddressLinkTable'):
        con.execute(f'DELETE FROM {t} WHERE OwnerType=? AND OwnerID=?', (otype, oid))


def _prune_family(con, fid):
    f = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid)
    if not f:
        return
    kids = con.execute('SELECT COUNT(*) FROM ChildTable WHERE FamilyID=?', (fid,)).fetchone()[0]
    if not f['FatherID'] and not f['MotherID'] and not kids:
        delete_family(con, fid)
    else:
        _fix_person_family_pointers(con)


def _fix_person_family_pointers(con):
    """Keep PersonTable.ParentID/SpouseID pointing at a valid family (RM uses them for navigation)."""
    con.execute('''UPDATE PersonTable SET ParentID=COALESCE((SELECT FamilyID FROM ChildTable
                     WHERE ChildID=PersonTable.PersonID ORDER BY RecID LIMIT 1),0)
                   WHERE ParentID NOT IN (SELECT FamilyID FROM ChildTable WHERE ChildID=PersonTable.PersonID)''')
    con.execute('''UPDATE PersonTable SET SpouseID=COALESCE((SELECT FamilyID FROM FamilyTable
                     WHERE FatherID=PersonTable.PersonID OR MotherID=PersonTable.PersonID ORDER BY FamilyID LIMIT 1),0)
                   WHERE SpouseID NOT IN (SELECT FamilyID FROM FamilyTable
                     WHERE FatherID=PersonTable.PersonID OR MotherID=PersonTable.PersonID)''')


def person_summary(con, pid, s=None):
    """Compact person record used everywhere in the UI."""
    p = row(con, 'SELECT * FROM PersonTable WHERE PersonID=?', pid)
    if not p:
        return None
    s = s or settings(con)
    n = primary_name(con, pid)
    b = first_event(con, pid, (1, 3, 7))
    d = first_event(con, pid, (2, 4, 5))
    color_col = 'Color' if not s.get('activeColorSet') else f'Color{s["activeColorSet"]}'
    return {
        'id': pid, 'name': fmt_name(n, s.get('nameFormat'), s.get('surnameCaps')),
        'given': n.get('Given', ''), 'surname': n.get('Surname', ''), 'sex': p['Sex'],
        'birth': fact_brief(con, b, s), 'death': fact_brief(con, d, s),
        'birthYear': rmdate.year(b['Date']) if b else 0, 'deathYear': rmdate.year(d['Date']) if d else 0,
        'living': p['Living'], 'private': p['IsPrivate'], 'color': p.get(color_col) or 0,
        'bookmark': p['Bookmark'], 'relate1': p['Relate1'], 'relate2': p['Relate2'],
        'parentFamily': p['ParentID'], 'spouseFamily': p['SpouseID'],
    }


def fact_brief(con, e, s=None):
    if not e:
        return None
    fmt = (s or {}).get('dateFormat', 'dmy')
    return {'id': e['EventID'], 'type': e['EventType'], 'date': rmdate.format(e['Date'], fmt),
            'place': place_name(con, e['PlaceID'])}


def first_event(con, pid, types, owner=0):
    q = ','.join('?' * len(types))
    rs = rows(con, f'''SELECT * FROM EventTable WHERE OwnerType=? AND OwnerID=? AND EventType IN ({q})
                       ORDER BY IsPrimary DESC, SortDate''', owner, pid, *types)
    for t in types:  # honour preference order (e.g. birth before christening)
        for r in rs:
            if r['EventType'] == t:
                return r
    return None


def parents_of(con, pid):
    """List of parent families: [{family, father, mother, relFather, relMother}]"""
    out = []
    for c in rows(con, '''SELECT c.*, f.FatherID, f.MotherID FROM ChildTable c
                         JOIN FamilyTable f ON f.FamilyID=c.FamilyID WHERE c.ChildID=? ORDER BY c.RecID''', pid):
        out.append({'family': c['FamilyID'], 'father': c['FatherID'], 'mother': c['MotherID'],
                    'relFather': c['RelFather'], 'relMother': c['RelMother']})
    return out


def spouse_families(con, pid):
    fams = rows(con, 'SELECT * FROM FamilyTable WHERE FatherID=? OR MotherID=?', pid, pid)
    fams.sort(key=lambda f: (f['HusbOrder'] if f['FatherID'] == pid else f['WifeOrder']) or 0)
    for f in fams:
        f['spouse'] = f['MotherID'] if f['FatherID'] == pid else f['FatherID']
    return fams


def children_of(con, fid):
    return [r['ChildID'] for r in rows(con, 'SELECT ChildID FROM ChildTable WHERE FamilyID=? ORDER BY ChildOrder, RecID', fid)]


def primary_parents(con, pid):
    p = row(con, 'SELECT ParentID FROM PersonTable WHERE PersonID=?', pid)
    fid = p and p['ParentID']
    fam = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid) if fid else None
    if not fam:
        ps = parents_of(con, pid)
        return (ps[0]['father'], ps[0]['mother'], ps[0]['family']) if ps else (0, 0, 0)
    return fam['FatherID'], fam['MotherID'], fid


def siblings_of(con, pid):
    out = []
    for p in parents_of(con, pid):
        for c in children_of(con, p['family']):
            if c != pid and c not in out:
                out.append(c)
    return out


# ------------------------------------------------------------------ families
def add_family(con, father=0, mother=0):
    with tx(con):
        fid = insert(con, 'FamilyTable', {'FatherID': father or 0, 'MotherID': mother or 0, 'ChildID': 0,
                                          'HusbOrder': 0, 'WifeOrder': 0, 'IsPrivate': 0, 'Proof': 0,
                                          'SpouseLabel': 0, 'FatherLabel': 0, 'MotherLabel': 0, 'Note': ''})
        for p, col in ((father, 'HusbOrder'), (mother, 'WifeOrder')):
            if p:
                n = con.execute('SELECT COUNT(*) FROM FamilyTable WHERE FatherID=? OR MotherID=?', (p, p)).fetchone()[0]
                con.execute(f'UPDATE FamilyTable SET {col}=? WHERE FamilyID=?', (n, fid))
                con.execute('UPDATE PersonTable SET SpouseID=? WHERE PersonID=? AND SpouseID=0', (fid, p))
    return fid


def find_family(con, a, b):
    return row(con, '''SELECT * FROM FamilyTable WHERE (FatherID=? AND MotherID=?) OR (FatherID=? AND MotherID=?)''',
               a, b, b, a)


def add_spouse(con, pid, spouse_id):
    """Link spouse_id as a spouse of pid; returns family id (reuses an existing family)."""
    f = find_family(con, pid, spouse_id)
    if f:
        return f['FamilyID']
    sex = row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid)['Sex']
    # a single-parent family of pid can absorb the new spouse
    single = row(con, f"SELECT * FROM FamilyTable WHERE {'FatherID' if sex != 1 else 'MotherID'}=? AND "
                      f"{'MotherID' if sex != 1 else 'FatherID'}=0", pid)
    if single:
        col = 'MotherID' if sex != 1 else 'FatherID'
        con.execute(f'UPDATE FamilyTable SET {col}=? WHERE FamilyID=?', (spouse_id, single['FamilyID']))
        con.execute('UPDATE PersonTable SET SpouseID=? WHERE PersonID=? AND SpouseID=0', (single['FamilyID'], spouse_id))
        return single['FamilyID']
    return add_family(con, pid, spouse_id) if sex != 1 else add_family(con, spouse_id, pid)


def add_child(con, fid, child_id, rel_father=0, rel_mother=0):
    with tx(con):
        if row(con, 'SELECT 1 AS x FROM ChildTable WHERE FamilyID=? AND ChildID=?', fid, child_id):
            return
        order = con.execute('SELECT COALESCE(MAX(ChildOrder),0)+1 FROM ChildTable WHERE FamilyID=?', (fid,)).fetchone()[0]
        insert(con, 'ChildTable', {'ChildID': child_id, 'FamilyID': fid, 'RelFather': rel_father,
                                   'RelMother': rel_mother, 'ChildOrder': order, 'IsPrivate': 0,
                                   'ProofFather': 0, 'ProofMother': 0, 'Note': ''})
        con.execute('UPDATE PersonTable SET ParentID=? WHERE PersonID=? AND ParentID=0', (fid, child_id))
        sort_children_by_birth(con, fid, only_if_unordered=True)


def sort_children_by_birth(con, fid, only_if_unordered=False):
    kids = rows(con, 'SELECT RecID, ChildID, ChildOrder FROM ChildTable WHERE FamilyID=?', fid)
    if only_if_unordered and len(kids) < 2:
        return

    def key(k):
        e = first_event(con, k['ChildID'], (1, 3, 7))
        return e['SortDate'] if e else rmdate.EMPTY_SORT
    for i, k in enumerate(sorted(kids, key=lambda k: (key(k), k['ChildOrder'])), 1):
        con.execute('UPDATE ChildTable SET ChildOrder=? WHERE RecID=?', (i, k['RecID']))


def reorder_children(con, fid, child_ids):
    with tx(con):
        for i, c in enumerate(child_ids, 1):
            con.execute('UPDATE ChildTable SET ChildOrder=? WHERE FamilyID=? AND ChildID=?', (i, fid, c))


def reorder_spouses(con, pid, family_ids):
    with tx(con):
        for i, f in enumerate(family_ids, 1):
            con.execute('UPDATE FamilyTable SET HusbOrder=? WHERE FamilyID=? AND FatherID=?', (i, f, pid))
            con.execute('UPDATE FamilyTable SET WifeOrder=? WHERE FamilyID=? AND MotherID=?', (i, f, pid))
        if family_ids:
            con.execute('UPDATE PersonTable SET SpouseID=? WHERE PersonID=?', (family_ids[0], pid))


def unlink_child(con, fid, child_id):
    with tx(con):
        con.execute('DELETE FROM ChildTable WHERE FamilyID=? AND ChildID=?', (fid, child_id))
        _prune_family(con, fid)
        _fix_person_family_pointers(con)


def unlink_spouse(con, fid, pid):
    with tx(con):
        f = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid)
        col = 'FatherID' if f['FatherID'] == pid else 'MotherID'
        con.execute(f'UPDATE FamilyTable SET {col}=0 WHERE FamilyID=?', (fid,))
        _prune_family(con, fid)
        _fix_person_family_pointers(con)


def unlink_family(con, fid):
    """Unlink all members (parents and children) of a family; keeps the people."""
    delete_family(con, fid)


def delete_family(con, fid):
    with tx(con):
        for e in rows(con, 'SELECT EventID FROM EventTable WHERE OwnerType=1 AND OwnerID=?', fid):
            _delete_event(con, e['EventID'])
        _delete_links(con, OWNER['family'], fid)
        con.execute('DELETE FROM ChildTable WHERE FamilyID=?', (fid,))
        con.execute('DELETE FROM FamilyTable WHERE FamilyID=?', (fid,))
        _fix_person_family_pointers(con)


def swap_couple(con, fid):
    con.execute('UPDATE FamilyTable SET FatherID=MotherID, MotherID=FatherID, HusbOrder=WifeOrder, '
                'WifeOrder=HusbOrder WHERE FamilyID=?', (fid,))


def family_summary(con, fid, s=None):
    f = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid)
    if not f:
        return None
    s = s or settings(con)
    m = first_event(con, fid, (300,), owner=1)
    return {'id': fid, 'father': person_summary(con, f['FatherID'], s) if f['FatherID'] else None,
            'mother': person_summary(con, f['MotherID'], s) if f['MotherID'] else None,
            'marriage': fact_brief(con, m, s), 'private': f['IsPrivate'], 'proof': f['Proof'],
            'note': f['Note'] or '',
            'children': [dict(person_summary(con, c, s), **_child_rel(con, fid, c)) for c in children_of(con, fid)]}


def _child_rel(con, fid, cid):
    r = row(con, 'SELECT RelFather, RelMother, ProofFather, ProofMother FROM ChildTable WHERE FamilyID=? AND ChildID=?', fid, cid)
    return {'relFather': r['RelFather'], 'relMother': r['RelMother']} if r else {}


# ------------------------------------------------------------------ places
def place_name(con, place_id):
    if not place_id:
        return ''
    r = row(con, 'SELECT Name FROM PlaceTable WHERE PlaceID=?', place_id)
    return r['Name'] if r else ''


def reverse_place(name):
    return ', '.join(reversed([p.strip() for p in (name or '').split(',')]))


def get_or_create_place(con, name, place_type=0, master=0):
    name = (name or '').strip()
    if not name:
        return 0
    r = row(con, 'SELECT PlaceID FROM PlaceTable WHERE Name=? AND PlaceType=? AND MasterID=?', name, place_type, master)
    if r:
        return r['PlaceID']
    return insert(con, 'PlaceTable', {'PlaceType': place_type, 'Name': name, 'Abbrev': '', 'Normalized': '',
                                      'Latitude': 0, 'Longitude': 0, 'LatLongExact': 0, 'MasterID': master,
                                      'Note': '', 'Reverse': reverse_place(name), 'fsID': 0, 'anID': 0})


def merge_places(con, keep, drop):
    with tx(con):
        con.execute('UPDATE EventTable SET PlaceID=? WHERE PlaceID=?', (keep, drop))
        con.execute('UPDATE FANTable SET PlaceID=? WHERE PlaceID=?', (keep, drop))
        con.execute('UPDATE PlaceTable SET MasterID=? WHERE MasterID=? AND PlaceType=2', (keep, drop))
        for t, ot in (('MediaLinkTable', 5), ('CitationLinkTable', 5), ('TaskLinkTable', 5)):
            con.execute(f'UPDATE {t} SET OwnerID=? WHERE OwnerType=? AND OwnerID=?', (keep, ot, drop))
        con.execute('DELETE FROM PlaceTable WHERE PlaceID=?', (drop,))


def place_usage(con, place_id):
    return con.execute('SELECT COUNT(*) FROM EventTable WHERE PlaceID=? OR SiteID=?', (place_id, place_id)).fetchone()[0]


# ------------------------------------------------------------------ facts / events
def fact_types(con):
    return rows(con, 'SELECT * FROM FactTypeTable ORDER BY OwnerType, Name')


def fact_type(con, ft):
    return row(con, 'SELECT * FROM FactTypeTable WHERE FactTypeID=?', ft)


def add_fact(con, owner, oid, ftype, date='', place='', place_details='', desc='', note='', **kw):
    otype = OWNER[owner] if isinstance(owner, str) else owner
    place_id = place if isinstance(place, int) else get_or_create_place(con, place)
    site_id = 0
    if place_details and place_id:
        site_id = get_or_create_place(con, place_details, 2, place_id)
    enc = rmdate.encode(date)
    is_primary = kw.get('primary')
    if is_primary is None:
        is_primary = 0 if con.execute('SELECT 1 FROM EventTable WHERE OwnerType=? AND OwnerID=? AND EventType=?',
                                      (otype, oid, ftype)).fetchone() else 1
    eid = insert(con, 'EventTable', {'EventType': ftype, 'OwnerType': otype, 'OwnerID': oid,
                                     'FamilyID': kw.get('family', 0), 'PlaceID': place_id, 'SiteID': site_id,
                                     'Date': enc, 'SortDate': rmdate.sort_date(enc), 'IsPrimary': is_primary,
                                     'IsPrivate': kw.get('private', 0), 'Proof': kw.get('proof', 0), 'Status': 0,
                                     'Sentence': kw.get('sentence', ''), 'Details': desc, 'Note': note})
    if otype == 0:
        refresh_name_years(con, oid)
    return eid


def save_fact(con, data):
    """Update an event from UI data: Date (free text), Place (name), PlaceDetails, Details, Note, flags."""
    eid = data['EventID']
    e = row(con, 'SELECT * FROM EventTable WHERE EventID=?', eid)
    d = {}
    if 'Date' in data:
        d['Date'] = rmdate.encode(data['Date'])
        d['SortDate'] = rmdate.sort_date(d['Date'])
    if 'Place' in data:
        d['PlaceID'] = get_or_create_place(con, data['Place'])
    if 'PlaceDetails' in data:
        master = d.get('PlaceID', e['PlaceID'])
        d['SiteID'] = get_or_create_place(con, data['PlaceDetails'], 2, master) if data['PlaceDetails'] and master else 0
    for k in ('EventType', 'Details', 'Note', 'Sentence', 'IsPrivate', 'Proof', 'IsPrimary', 'Status'):
        if k in data:
            d[k] = data[k]
    with tx(con):
        update(con, 'EventTable', 'EventID', eid, d)
        if d.get('IsPrimary'):
            con.execute('UPDATE EventTable SET IsPrimary=0 WHERE OwnerType=? AND OwnerID=? AND EventType=? AND EventID<>?',
                        (e['OwnerType'], e['OwnerID'], d.get('EventType', e['EventType']), eid))
        if e['OwnerType'] == 0:
            refresh_name_years(con, e['OwnerID'])
    return eid


def _delete_event(con, eid):
    _delete_links(con, OWNER['event'], eid)
    for w in rows(con, 'SELECT WitnessID FROM WitnessTable WHERE EventID=?', eid):
        _delete_links(con, 9, w['WitnessID'])
    con.execute('DELETE FROM WitnessTable WHERE EventID=?', (eid,))
    con.execute('DELETE FROM EventTable WHERE EventID=?', (eid,))


def delete_fact(con, eid):
    e = row(con, 'SELECT OwnerType, OwnerID FROM EventTable WHERE EventID=?', eid)
    with tx(con):
        _delete_event(con, eid)
        if e and e['OwnerType'] == 0:
            refresh_name_years(con, e['OwnerID'])


def facts_for(con, owner, oid, s=None, include_shared=True):
    """Facts owned by a person/family, plus facts shared with the person (witness)."""
    s = s or settings(con)
    otype = OWNER[owner] if isinstance(owner, str) else owner
    ft = {f['FactTypeID']: f for f in fact_types(con)}
    out = []
    for e in rows(con, 'SELECT * FROM EventTable WHERE OwnerType=? AND OwnerID=? ORDER BY SortDate, EventID', otype, oid):
        out.append(_fact_view(con, e, ft, s))
    if otype == 0 and include_shared:
        for w in rows(con, '''SELECT w.*, e.* FROM WitnessTable w JOIN EventTable e ON e.EventID=w.EventID
                              WHERE w.PersonID=? ORDER BY e.SortDate''', oid):
            v = _fact_view(con, w, ft, s)
            v['shared'] = {'witnessId': w['WitnessID'], 'role': role_name(con, w['Role']),
                           'principal': event_owner_name(con, w)}
            out.append(v)
    out.sort(key=lambda f: (f['sortDate'], f['id']))
    return out


def _fact_view(con, e, ft, s):
    t = ft.get(e['EventType'], {})
    cites = con.execute('SELECT COUNT(*) FROM CitationLinkTable WHERE OwnerType=2 AND OwnerID=?', (e['EventID'],)).fetchone()[0]
    media = con.execute('SELECT COUNT(*) FROM MediaLinkTable WHERE OwnerType=2 AND OwnerID=?', (e['EventID'],)).fetchone()[0]
    return {'id': e['EventID'], 'type': e['EventType'], 'typeName': t.get('Name', f'Fact {e["EventType"]}'),
            'date': rmdate.format(e['Date'], s.get('dateFormat', 'dmy')), 'dateRaw': e['Date'],
            'sortDate': e['SortDate'] if e['SortDate'] is not None else rmdate.EMPTY_SORT,
            'place': place_name(con, e['PlaceID']), 'placeId': e['PlaceID'],
            'placeDetails': place_name(con, e['SiteID']), 'description': e['Details'] or '',
            'note': e['Note'] or '', 'sentence': e['Sentence'] or '', 'primary': e['IsPrimary'],
            'private': e['IsPrivate'], 'proof': e['Proof'], 'ownerType': e['OwnerType'], 'ownerId': e['OwnerID'],
            'citations': cites, 'media': media,
            'witnesses': con.execute('SELECT COUNT(*) FROM WitnessTable WHERE EventID=?', (e['EventID'],)).fetchone()[0]}


def role_name(con, role_id):
    if not role_id:
        return 'Principal'
    r = row(con, 'SELECT RoleName FROM RoleTable WHERE RoleID=?', role_id)
    return r['RoleName'] if r else 'Witness'


def event_owner_name(con, e):
    if e['OwnerType'] == 0:
        return person_name(con, e['OwnerID'])
    f = row(con, 'SELECT FatherID, MotherID FROM FamilyTable WHERE FamilyID=?', e['OwnerID'])
    return couple_name(con, f) if f else ''


def couple_name(con, f):
    return ' and '.join(x for x in (person_name(con, f['FatherID']), person_name(con, f['MotherID'])) if x)


def add_witness(con, eid, person_id=0, role=0, given='', surname='', sentence='', note=''):
    order = con.execute('SELECT COALESCE(MAX(WitnessOrder),0)+1 FROM WitnessTable WHERE EventID=?', (eid,)).fetchone()[0]
    return insert(con, 'WitnessTable', {'EventID': eid, 'PersonID': person_id, 'WitnessOrder': order, 'Role': role,
                                        'Sentence': sentence, 'Note': note, 'Given': given, 'Surname': surname,
                                        'Prefix': '', 'Suffix': ''})


# ------------------------------------------------------------------ sentences
PRONOUNS = {  # sex -> (he, him, his, He, His)
    0: ('he', 'him', 'his'), 1: ('she', 'her', 'her'), 2: ('they', 'them', 'their')}


def fact_sentence(con, eid, s=None, subject=None, first_mention=True):
    """Narrative sentence for an event, using the custom sentence or the fact-type template."""
    s = s or settings(con)
    e = row(con, 'SELECT * FROM EventTable WHERE EventID=?', eid)
    if not e:
        return ''
    ft = fact_type(con, e['EventType']) or {}
    tmpl = e['Sentence'] or ft.get('Sentence') or '[person]< [Desc]>< [Date]>< [Place]>.'
    return render_sentence(con, tmpl, e, s, subject, first_mention)


def render_sentence(con, tmpl, e, s, subject=None, first_mention=True, this_person=None):
    fmt = s.get('dateFormat', 'dmy')
    fam = None
    principal = e['OwnerID'] if e['OwnerType'] == 0 else 0
    if e['OwnerType'] == 1:
        fam = row(con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', e['OwnerID'])
    subj = subject or principal or (fam and (fam['FatherID'] or fam['MotherID'])) or 0
    sex = (row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', subj) or {'Sex': 2})['Sex'] if subj else 2

    def person_ref(pid, mod, first):
        if not pid:
            return ''
        mod_l = mod.lower()
        n = primary_name(con, pid)
        psex = (row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid) or {'Sex': 2})['Sex']
        he, him, his = PRONOUNS.get(psex, PRONOUNS[2])
        if mod_l == 'hisher':
            return his
        if mod_l == 'heshe':
            return he
        if mod_l == 'himher':
            return him
        if mod_l == 'given':
            return n.get('Given', '')
        if mod_l == 'surname':
            return n.get('Surname', '')
        if mod_l == 'full':
            return fmt_name(n, 'full')
        if mod_l == 'age':
            b = first_event(con, pid, (1,))
            a = rmdate.age_text(b['Date'], e['Date']) if b else ''
            return f'at the age of {a}' if a else ''
        if not first:
            return he[0].upper() + he[1:]
        return fmt_name(n, 'given_surname')

    def resolve(name, mod):
        nl = name.lower()
        if nl == '#couple':
            return bool(fam and fam['FatherID'] and fam['MotherID'])
        if nl == 'person':
            if fam and not mod:
                return couple_name(con, fam) if first_mention else 'They'
            return person_ref(subj, mod, first_mention)
        if nl == 'couple':
            if not fam:
                return person_ref(subj, mod, first_mention)
            if mod.lower() == 'hisher':
                return 'their'
            return couple_name(con, fam) if first_mention else 'They'
        if nl == 'spouse' and fam:
            return person_ref(fam['MotherID'] if subj == fam['FatherID'] else fam['FatherID'], mod, True)
        if nl == 'thisperson':
            return person_ref(this_person, mod, True)
        if nl == 'date':
            if mod.lower() == 'year':
                y = rmdate.year(e['Date'])
                return str(y) if y else ''
            if mod.lower() == 'plain':
                return rmdate.format(e['Date'], fmt)
            return rmdate.sentence_form(e['Date'], fmt)
        if nl == 'place':
            p = place_name(con, e['PlaceID'])
            if not p:
                return ''
            if mod.lower() == 'short':
                return p.split(',')[0]
            return p if mod.lower() == 'plain' else ('in ' + p)
        if nl == 'placedetails':
            p = place_name(con, e['SiteID'])
            return ('at ' + p) if p and mod.lower() != 'plain' else p
        if nl in ('desc', 'description'):
            return templates.apply_text_mod(e['Details'] or '', mod)
        if nl == 'age':
            b = first_event(con, subj, (1,))
            return rmdate.age_text(b['Date'], e['Date']) if b else ''
        return ''
    return templates.render(tmpl, resolve)


# ------------------------------------------------------------------ sources & citations
def fields_to_xml(fields):
    root = ET.Element('Root')
    fs = ET.SubElement(root, 'Fields')
    for k, v in (fields or {}).items():
        f = ET.SubElement(fs, 'Field')
        ET.SubElement(f, 'Name').text = k
        ET.SubElement(f, 'Value').text = v or ''
    return ET.tostring(root, encoding='unicode')


def xml_to_fields(blob):
    if not blob:
        return {}
    if isinstance(blob, bytes):
        blob = blob.decode('utf-8', 'replace').lstrip('﻿')
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return {}
    return {(f.findtext('Name') or ''): (f.findtext('Value') or '') for f in root.iter('Field') if f.findtext('Name')}


def template_fields(con, template_id):
    """Field definitions of a source template: [{name, display, type, hint, citation}]"""
    if not template_id:
        return [{'name': 'Footnote', 'display': 'Footnote', 'type': 'Text', 'hint': '', 'citation': False},
                {'name': 'ShortFootnote', 'display': 'Short footnote', 'type': 'Text', 'hint': '', 'citation': False},
                {'name': 'Bibliography', 'display': 'Bibliography', 'type': 'Text', 'hint': '', 'citation': False},
                {'name': 'Page', 'display': 'Citation detail', 'type': 'Text', 'hint': '', 'citation': True}]
    t = row(con, 'SELECT FieldDefs FROM SourceTemplateTable WHERE TemplateID=?', template_id)
    if not t or not t['FieldDefs']:
        return []
    blob = t['FieldDefs']
    if isinstance(blob, bytes):
        blob = blob.decode('utf-8', 'replace').lstrip('﻿')
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    return [{'name': f.findtext('FieldName') or f.findtext('Name') or '',
             'display': f.findtext('DisplayName') or f.findtext('Display') or '',
             'type': f.findtext('Type') or 'Text', 'hint': f.findtext('Hint') or '',
             'longHint': f.findtext('LongHint') or '',
             'citation': (f.findtext('CitationField') or f.findtext('Detail') or 'False').lower() == 'true'}
            for f in root.iter('Field')]


def render_citation(con, citation_id, which='Footnote'):
    """Footnote / ShortFootnote / Bibliography for a citation (source + citation fields merged)."""
    c = row(con, 'SELECT * FROM CitationTable WHERE CitationID=?', citation_id)
    if not c:
        return ''
    src = row(con, 'SELECT * FROM SourceTable WHERE SourceID=?', c['SourceID']) or {}
    return render_source_text(con, src, c, which)


def render_source_text(con, src, cit, which='Footnote'):
    """Footnote/ShortFootnote/Bibliography as safe HTML (field values are untrusted)."""
    return safe_html(_source_text(con, src, cit, which))


def _source_text(con, src, cit, which):
    fields = xml_to_fields(src.get('Fields'))
    if cit:
        fields.update(xml_to_fields(cit.get('Fields')))
    tid = src.get('TemplateID') or 0
    if not tid:  # free-form
        base = fields.get(which, '')
        if which == 'Bibliography':
            return base
        page = fields.get('Page', '')
        return base + (', ' + page if page and base else page) + ('' if not base or base.endswith('.') else '.')
    t = row(con, 'SELECT * FROM SourceTemplateTable WHERE TemplateID=?', tid) or {}
    types = {f['name']: f['type'] for f in template_fields(con, tid)}

    def resolve(name, mod):
        v = fields.get(name, '')
        typ = types.get(name, 'Text')
        if typ == 'Name':
            return name_value(v, mod) if '/' in v or mod else templates.apply_text_mod(v, mod)
        if typ == 'Date' and mod.lower() == 'year':
            y = rmdate.year(rmdate.encode(v))
            return str(y) if y else v
        if typ == 'Place' and mod.lower() == 'short':
            return v.split(',')[0]
        return templates.apply_text_mod(v, mod)
    return templates.render(t.get(which) or '', resolve)


name_value = templates.name_value


def source_title(src):
    return src.get('Name') or '(untitled source)'


def add_source(con, name, template_id=0, fields=None, **kw):
    return insert(con, 'SourceTable', {'Name': name, 'RefNumber': kw.get('ref', ''), 'ActualText': kw.get('text', ''),
                                       'Comments': kw.get('comments', ''), 'IsPrivate': 0, 'TemplateID': template_id,
                                       'Fields': fields_to_xml(fields or {})})


def add_citation(con, source_id, owner, oid, fields=None, quality='~~~', **kw):
    otype = OWNER[owner] if isinstance(owner, str) else owner
    with tx(con):
        cid = kw.get('citation_id')
        if not cid:
            cid = insert(con, 'CitationTable', {'SourceID': source_id, 'Comments': kw.get('comments', ''),
                                                'ActualText': kw.get('text', ''), 'RefNumber': kw.get('ref', ''),
                                                'Footnote': '', 'ShortFootnote': '', 'Bibliography': '',
                                                'Fields': fields_to_xml(fields or {}),
                                                'CitationName': kw.get('name', '')})
        if oid or otype in (0, 1, 2, 7):
            order = con.execute('SELECT COALESCE(MAX(SortOrder),0)+1 FROM CitationLinkTable WHERE OwnerType=? AND OwnerID=?',
                                (otype, oid)).fetchone()[0]
            insert(con, 'CitationLinkTable', {'CitationID': cid, 'OwnerType': otype, 'OwnerID': oid,
                                              'SortOrder': order, 'Quality': quality, 'IsPrivate': 0, 'Flags': 0})
    return cid


def citations_for(con, otype, oid):
    out = []
    for l in rows(con, '''SELECT l.LinkID, l.Quality, l.CitationID, c.SourceID, c.CitationName, c.RefNumber,
                          s.Name AS SourceName FROM CitationLinkTable l JOIN CitationTable c ON c.CitationID=l.CitationID
                          LEFT JOIN SourceTable s ON s.SourceID=c.SourceID
                          WHERE l.OwnerType=? AND l.OwnerID=? ORDER BY l.SortOrder''', otype, oid):
        l['footnote'] = render_citation(con, l['CitationID'])
        out.append(l)
    return out


QUALITY = {'source': {'O': 'Original', 'D': 'Derivative', 'A': 'Authored', '~': 'Unknown'},
           'info': {'P': 'Primary', 'S': 'Secondary', 'U': 'Undetermined', '~': 'Unknown'},
           'evidence': {'D': 'Direct', 'I': 'Indirect', 'N': 'Negative', '~': 'Unknown'}}


def citation_owner_label(con, otype, oid):
    if otype == 0:
        return person_name(con, oid)
    if otype == 1:
        f = row(con, 'SELECT FatherID, MotherID FROM FamilyTable WHERE FamilyID=?', oid)
        return couple_name(con, f) if f else ''
    if otype == 2:
        e = row(con, 'SELECT * FROM EventTable WHERE EventID=?', oid)
        if not e:
            return ''
        ft = fact_type(con, e['EventType']) or {}
        return f"{ft.get('Name', 'Fact')}: {event_owner_name(con, e)}"
    if otype == 7:
        n = row(con, 'SELECT * FROM NameTable WHERE NameID=?', oid)
        return 'Name: ' + fmt_name(n) if n else ''
    return ''


# ------------------------------------------------------------------ media
def add_media(con, path, caption='', media_type=1, url='', description='', date=''):
    import os
    enc = rmdate.encode(date)
    return insert(con, 'MultimediaTable', {'MediaType': media_type, 'MediaPath': os.path.dirname(path) + os.sep if path else '',
                                           'MediaFile': os.path.basename(path) if path else '', 'URL': url,
                                           'Caption': caption, 'RefNumber': '', 'Date': enc,
                                           'SortDate': rmdate.sort_date(enc), 'Description': description})


def link_media(con, media_id, otype, oid, primary=0):
    order = con.execute('SELECT COALESCE(MAX(SortOrder),0)+1 FROM MediaLinkTable WHERE OwnerType=? AND OwnerID=?',
                        (otype, oid)).fetchone()[0]
    lid = insert(con, 'MediaLinkTable', {'MediaID': media_id, 'OwnerType': otype, 'OwnerID': oid, 'IsPrimary': primary,
                                         'Include1': 1, 'Include2': 1, 'Include3': 1, 'Include4': 1, 'SortOrder': order,
                                         'RectLeft': 0, 'RectTop': 0, 'RectRight': 0, 'RectBottom': 0, 'Comments': ''})
    if primary:
        con.execute('UPDATE MediaLinkTable SET IsPrimary=0 WHERE OwnerType=? AND OwnerID=? AND LinkID<>?', (otype, oid, lid))
    return lid


def media_path(m):
    import os
    return os.path.join(m.get('MediaPath') or '', m.get('MediaFile') or '')


def primary_photo(con, pid):
    return row(con, '''SELECT m.* FROM MediaLinkTable l JOIN MultimediaTable m ON m.MediaID=l.MediaID
                       WHERE l.OwnerType=0 AND l.OwnerID=? AND m.MediaType=1 ORDER BY l.IsPrimary DESC, l.SortOrder
                       LIMIT 1''', pid)


# ------------------------------------------------------------------ groups (TagTable TagType=0 + GroupTable ranges)
def groups(con):
    return rows(con, 'SELECT TagID, TagValue AS GroupID, TagName AS Name, Description FROM TagTable WHERE TagType=0 ORDER BY TagName')


def create_group(con, name, description=''):
    gid = con.execute('SELECT COALESCE(MAX(TagValue),0)+1 FROM TagTable WHERE TagType=0').fetchone()[0]
    insert(con, 'TagTable', {'TagType': 0, 'TagValue': gid, 'TagName': name, 'Description': description})
    return gid


def group_members(con, gid):
    return [r['PersonID'] for r in rows(con, '''SELECT p.PersonID FROM GroupTable g JOIN PersonTable p
               ON p.PersonID BETWEEN g.StartID AND g.EndID WHERE g.GroupID=? ORDER BY p.PersonID''', gid)]


def set_group_members(con, gid, ids):
    """Store membership as compressed ID ranges, exactly like RM's GroupTable."""
    ids = sorted(set(ids))
    with tx(con):
        con.execute('DELETE FROM GroupTable WHERE GroupID=?', (gid,))
        start = prev = None
        for i in ids + [None]:
            if start is None:
                start = prev = i
            elif i is not None and i == prev + 1:
                prev = i
            else:
                insert(con, 'GroupTable', {'GroupID': gid, 'StartID': start, 'EndID': prev})
                start = prev = i


def delete_group(con, gid):
    with tx(con):
        con.execute('DELETE FROM GroupTable WHERE GroupID=?', (gid,))
        con.execute('DELETE FROM TagTable WHERE TagType=0 AND TagValue=?', (gid,))


def remove_from_all_groups(con, pid):
    for g in groups(con):
        m = group_members(con, g['GroupID'])
        if pid in m:
            m.remove(pid)
            set_group_members(con, g['GroupID'], m)


def person_groups(con, pid):
    return [g for g in groups(con) if con.execute(
        'SELECT 1 FROM GroupTable WHERE GroupID=? AND ? BETWEEN StartID AND EndID', (g['GroupID'], pid)).fetchone()]


# ------------------------------------------------------------------ notes (RM stores lightly formatted text)
def safe_html(s):
    """Escape everything except RM's inline formatting tags (<b>,<i>,<u>,<sup>,<sub>, no attributes).
    Notes and source text come from imported GEDCOMs, i.e. other people, and are shown as HTML."""
    return re.sub(r'&lt;(/?)(b|i|u|sup|sub)&gt;', r'<\1\2>', escape(s or '', quote=False), flags=re.I)


def safe_url(u):
    """Only web links are clickable; javascript:/data: URLs from imported data become '#'."""
    return u if re.match(r'(?i)https?://', u or '') else '#'


def note_to_html(note):
    """RM notes allow <b>,<i>,<u>; everything else escaped. Newlines -> <br>."""
    return safe_html(note).replace('\r\n', '\n').replace('\n', '<br>')


def strip_tags(s):
    return re.sub(r'<[^>]+>', '', s or '')
