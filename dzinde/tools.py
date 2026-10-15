"""Analysis & maintenance tools (RootsMagic 'Tools' menu equivalents)."""
import datetime
import difflib
import os
import re
import shutil
import sqlite3
import zipfile
from collections import deque

from . import db, model as m, rmdate
from .db import OWNER, insert, row, rows, tx


# ------------------------------------------------------------------ traversal
def parents(con, pid, birth_only=False):
    """[(father, mother, family)] for all parent families (primary first)."""
    out = []
    pf = row(con, 'SELECT ParentID FROM PersonTable WHERE PersonID=?', pid)
    for p in m.parents_of(con, pid):
        if birth_only and (p['relFather'] or p['relMother']):
            continue
        out.append(p)
    out.sort(key=lambda p: p['family'] != (pf and pf['ParentID']))
    return [(p['father'], p['mother'], p['family']) for p in out]


def ancestors(con, pid, gens=99):
    """Ahnentafel dict {number: person_id} following primary parents."""
    out, queue = {1: pid}, deque([(1, pid)])
    while queue:
        n, p = queue.popleft()
        if n >= 2 ** gens:
            continue
        ps = parents(con, p)
        if not ps:
            continue
        f, mo, _ = ps[0]
        for k, x in ((2 * n, f), (2 * n + 1, mo)):
            if x and k not in out:
                out[k] = x
                queue.append((k, x))
    return out


def all_ancestors(con, pid):
    """{ancestor_id: min generations} over all parent links."""
    seen, queue = {pid: 0}, deque([pid])
    while queue:
        p = queue.popleft()
        for f, mo, _ in parents(con, p):
            for x in (f, mo):
                if x and x not in seen:
                    seen[x] = seen[p] + 1
                    queue.append(x)
    return seen


def descendants(con, pid, gens=99):
    """[(person, generation, via_family)] depth-first in child order."""
    out, seen = [], {pid}

    def walk(p, g):
        if g >= gens:
            return
        for f in m.spouse_families(con, p):
            for c in m.children_of(con, f['FamilyID']):
                if c not in seen:
                    seen.add(c)
                    out.append((c, g + 1, f['FamilyID']))
                    walk(c, g + 1)
    walk(pid, 0)
    return out


def all_descendants(con, pid):
    return {c for c, _, _ in descendants(con, pid)}


# ------------------------------------------------------------------ relationship names
ORD = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
       'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth', 'sixteenth', 'seventeenth', 'eighteenth',
       'nineteenth']
TIMES = {1: 'once', 2: 'twice'}


def _ord(n):
    return ORD[n] if n < len(ORD) else f'{n}th'


def _nth(k):
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def _greats(n, word):
    """n=0 -> word, 1 -> grandword, 2 -> great-grandword, 3 -> 2nd great-grandword, ..."""
    if n == 0:
        return word
    if n == 1:
        return 'grand' + word
    if n == 2:
        return 'great-grand' + word
    return f'{_nth(n - 1)} great-grand{word}'


def relationship_name(g1, g2, sex=2, half=False):
    """Name of person B relative to A where the common ancestor is g1 generations above A and g2 above B."""
    male, female = sex == 0, sex == 1
    pick = lambda mw, fw, nw: mw if male else fw if female else nw
    if g1 == 0 and g2 == 0:
        return 'self'
    if g2 == 0:  # B is ancestor of A
        return _greats(g1 - 1, pick('father', 'mother', 'parent'))
    if g1 == 0:  # B is descendant of A
        return _greats(g2 - 1, pick('son', 'daughter', 'child'))
    h = 'half ' if half else ''
    if g1 == 1 and g2 == 1:
        return h + pick('brother', 'sister', 'sibling')
    if g1 == 1:  # B is descendant of A's sibling
        return h + _greats(g2 - 2, pick('nephew', 'niece', 'niece/nephew'))
    if g2 == 1:  # B is sibling of A's ancestor
        return h + _greats(g1 - 2, pick('uncle', 'aunt', 'aunt/uncle'))
    c = min(g1, g2) - 1
    r = abs(g1 - g2)
    s = f'{h}{_ord(c)} cousin'
    if r:
        s += ' ' + (TIMES.get(r) or f'{r} times') + ' removed'
    return s


def common_ancestors(con, a, b):
    """[(ancestor, gens from a, gens from b)] — nearest common ancestors only."""
    aa, bb = all_ancestors(con, a), all_ancestors(con, b)
    common = set(aa) & set(bb)
    nearest = [x for x in common if not any(x in all_ancestors(con, y) and x != y for y in common)]
    return sorted(((x, aa[x], bb[x]) for x in nearest), key=lambda t: t[1] + t[2])


def relationships(con, a, b):
    """All ways B is related to A: blood (via common ancestors), spouse, in-law, step."""
    if a == b:
        return [{'name': 'self', 'ancestors': []}]
    sexb = (row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', b) or {'Sex': 2})['Sex']
    out = []
    ca = common_ancestors(con, a, b)
    # group ancestor couples (father+mother with same distances = full relationship)
    used = set()
    for anc, g1, g2 in ca:
        if anc in used:
            continue
        spouses = {f['spouse'] for f in m.spouse_families(con, anc)}
        partner = next((x for x, h1, h2 in ca if x in spouses and (h1, h2) == (g1, g2)), None)
        used.update({anc, partner})
        half = partner is None and g1 > 0 and g2 > 0
        out.append({'name': relationship_name(g1, g2, sexb, half), 'g1': g1, 'g2': g2,
                    'ancestors': [x for x in (anc, partner) if x]})
    for f in m.spouse_families(con, a):
        if f['spouse'] == b:
            out.append({'name': {0: 'husband', 1: 'wife'}.get(sexb, 'spouse'), 'ancestors': []})
    if not out:  # in-law via spouse
        for f in m.spouse_families(con, a):
            if f['spouse']:
                for r in relationships_blood_only(con, f['spouse'], b, sexb):
                    out.append({'name': r + '-in-law' if r in ('father', 'mother', 'brother', 'sister', 'son', 'daughter', 'parent', 'sibling', 'child') else f"spouse's {r}", 'ancestors': []})
        for f in m.spouse_families(con, b):
            if f['spouse'] and not out:
                for r in relationships_blood_only(con, a, f['spouse'], 2):
                    nm = {'son': 'son-in-law', 'daughter': 'daughter-in-law', 'child': 'child-in-law',
                          'brother': 'brother-in-law', 'sister': 'sister-in-law', 'sibling': 'sibling-in-law'}.get(r)
                    spouse_word = {0: 'husband', 1: 'wife'}.get(sexb, 'spouse')
                    out.append({'name': nm or f"{spouse_word} of {r}", 'ancestors': []})
    return out


def relationships_blood_only(con, a, b, sexb):
    if a == b:
        return []
    return [relationship_name(g1, g2, sexb) for _, g1, g2 in common_ancestors(con, a, b)[:1]]


def kinship_list(con, pid, limit=5000):
    """Everyone blood-related to pid (via ancestors' descendants) with relationship name."""
    anc = all_ancestors(con, pid)
    s = m.settings(con)
    out = {}
    for x, g1 in sorted(anc.items(), key=lambda t: t[1]):
        for c, g2, _ in [(x, 0, 0)] + descendants(con, x):
            if c in out or c == pid:
                continue
            sex = (row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', c) or {'Sex': 2})['Sex']
            out[c] = relationship_name(g1, g2, sex)
            if len(out) >= limit:
                break
    return [{'person': m.person_summary(con, c, s), 'relationship': r} for c, r in out.items()]


def set_relationships(con, root):
    """Fill PersonTable.Relate1/Relate2 = generations from root / from person to nearest common ancestor."""
    with tx(con):
        con.execute('UPDATE PersonTable SET Relate1=0, Relate2=0')
        anc = all_ancestors(con, root)
        n = 0
        for x, g1 in anc.items():
            for c, g2, _ in [(x, 0, 0)] + descendants(con, x):
                r = row(con, 'SELECT Relate1, Relate2 FROM PersonTable WHERE PersonID=?', c)
                if r and (r['Relate1'] == 0 and r['Relate2'] == 0 or g1 + g2 < r['Relate1'] + r['Relate2']):
                    con.execute('UPDATE PersonTable SET Relate1=?, Relate2=? WHERE PersonID=?', (g1, g2, c))
                    n += 1
        con.execute('UPDATE PersonTable SET Relate1=0, Relate2=0 WHERE PersonID=?', (root,))
        m.save_settings(con, {'rootPersonId': root})
    return n


def relationship_to_root(con, pid, root=None):
    root = root or m.settings(con).get('rootPersonId')
    if not root:
        return ''
    r = row(con, 'SELECT Sex, Relate1, Relate2 FROM PersonTable WHERE PersonID=?', pid)
    if not r or pid == root:
        return '' if pid != root else 'Root person'
    if not (r['Relate1'] or r['Relate2']):
        return ''
    return relationship_name(r['Relate1'], r['Relate2'], r['Sex'])


# ------------------------------------------------------------------ count trees / living
def count_trees(con):
    ids = [r['PersonID'] for r in rows(con, 'SELECT PersonID FROM PersonTable')]
    adj = {i: set() for i in ids}
    for f in rows(con, 'SELECT FamilyID, FatherID, MotherID FROM FamilyTable'):
        members = [x for x in (f['FatherID'], f['MotherID']) if x in adj] + \
                  [c for c in m.children_of(con, f['FamilyID']) if c in adj]
        for x in members:
            adj[x].update(y for y in members if y != x)
    seen, trees = set(), []
    for i in ids:
        if i in seen:
            continue
        comp, q = [], deque([i])
        seen.add(i)
        while q:
            x = q.popleft()
            comp.append(x)
            for y in adj[x] - seen:
                seen.add(y)
                q.append(y)
        trees.append(comp)
    trees.sort(key=len, reverse=True)
    s = m.settings(con)
    return [{'size': len(t), 'start': m.person_summary(con, min(t), s), 'members': sorted(t)} for t in trees]


def guess_living(con, pid, years=110):
    """Living unless there is a death/burial fact or any evidence of being born > `years` ago."""
    if m.first_event(con, pid, (2, 4, 5, 1003)):
        return False
    this_year = datetime.date.today().year
    by = 0
    b = m.first_event(con, pid, (1, 3, 7))
    if b:
        by = rmdate.year(b['Date'])
    if not by:
        # infer from children / parents / marriages
        for f in m.spouse_families(con, pid):
            for c in m.children_of(con, f['FamilyID']):
                cb = m.first_event(con, c, (1, 3, 7))
                if cb and rmdate.year(cb['Date']):
                    by = rmdate.year(cb['Date']) - 20
                    break
            mar = m.first_event(con, f['FamilyID'], (300,), owner=1)
            if not by and mar and rmdate.year(mar['Date']):
                by = rmdate.year(mar['Date']) - 20
    if not by:
        e = row(con, "SELECT Date FROM EventTable WHERE OwnerType=0 AND OwnerID=? AND Date LIKE 'D%' ORDER BY SortDate LIMIT 1", pid)
        if e and rmdate.year(e['Date']):
            by = rmdate.year(e['Date']) - 20
    if not by:
        return True
    return this_year - by < years


def set_living(con, years=110, ids=None):
    ids = ids or [r['PersonID'] for r in rows(con, 'SELECT PersonID FROM PersonTable')]
    changed = 0
    with tx(con):
        for pid in ids:
            v = 1 if guess_living(con, pid, years) else 0
            if con.execute('UPDATE PersonTable SET Living=? WHERE PersonID=? AND Living<>?', (v, pid, v)).rowcount:
                changed += 1
    return changed


# ------------------------------------------------------------------ duplicates & merge
def _norm(s):
    return re.sub(r'[^a-z ]', '', (s or '').lower()).strip()


def person_key(con, pid):
    n = m.primary_name(con, pid)
    b = m.first_event(con, pid, (1, 3, 7))
    d = m.first_event(con, pid, (2, 4))
    f, mo, _ = m.primary_parents(con, pid)
    return {'id': pid, 'given': _norm(n.get('Given')), 'surname': _norm(n.get('Surname')),
            'sex': (row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid) or {}).get('Sex', 2),
            'by': rmdate.year(b['Date']) if b else 0, 'dy': rmdate.year(d['Date']) if d else 0,
            'bdate': b['Date'] if b else '', 'bplace': m.place_name(con, b['PlaceID']).lower() if b else '',
            'father': _norm(m.person_name(con, f)), 'mother': _norm(m.person_name(con, mo))}


def dup_score(a, b, use_soundex=True):
    if a['sex'] != b['sex'] and 2 not in (a['sex'], b['sex']):
        return 0
    if use_soundex:
        if m.soundex(a['surname']) != m.soundex(b['surname']):
            return 0
    elif a['surname'] != b['surname']:
        return 0
    g = difflib.SequenceMatcher(None, a['given'], b['given']).ratio()
    if a['given'].split()[:1] and b['given'].split()[:1] and a['given'].split()[0] == b['given'].split()[0]:
        g = max(g, 0.9)
    if g < 0.6:
        return 0
    score = 40 * g + (20 if a['surname'] == b['surname'] else 10)
    for k, w in (('by', 15), ('dy', 10)):
        if a[k] and b[k]:
            diff = abs(a[k] - b[k])
            if diff > 5:
                return 0
            score += w * (1 - diff / 6)
    if a['bdate'] and a['bdate'] == b['bdate']:
        score += 5
    if a['bplace'] and b['bplace']:
        score += 5 if a['bplace'] == b['bplace'] else 0
    for k in ('father', 'mother'):
        if a[k] and b[k]:
            score += 5 if a[k] == b[k] else -5
    return round(min(score, 100))


def find_duplicates(con, min_score=60, use_soundex=True):
    keys = [person_key(con, r['PersonID']) for r in rows(con, 'SELECT PersonID FROM PersonTable')]
    excl = {(r['ID1'], r['ID2']) for r in rows(con, 'SELECT ID1, ID2 FROM ExclusionTable WHERE ExclusionType=1')}
    buckets = {}
    for k in keys:
        buckets.setdefault(m.soundex(k['surname']) if use_soundex else k['surname'], []).append(k)
    out = []
    s = m.settings(con)
    for group in buckets.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if (a['id'], b['id']) in excl or (b['id'], a['id']) in excl:
                    continue
                sc = dup_score(a, b, use_soundex)
                if sc >= min_score:
                    out.append({'score': sc, 'a': m.person_summary(con, a['id'], s), 'b': m.person_summary(con, b['id'], s)})
    out.sort(key=lambda d: -d['score'])
    return out


def not_duplicate(con, a, b):
    con.execute('INSERT OR IGNORE INTO ExclusionTable (ExclusionType, ID1, ID2, UTCModDate) VALUES (1,?,?,?)',
                (min(a, b), max(a, b), db.utc_now()))


def merge_people(con, keep, drop):
    """Move everything from `drop` onto `keep`, then delete `drop`."""
    if keep == drop:
        return
    with tx(con):
        con.execute('UPDATE NameTable SET OwnerID=?, IsPrimary=0 WHERE OwnerID=?', (keep, drop))
        con.execute('UPDATE EventTable SET OwnerID=? WHERE OwnerType=0 AND OwnerID=?', (keep, drop))
        for t in ('CitationLinkTable', 'MediaLinkTable', 'TaskLinkTable', 'URLTable', 'AddressLinkTable'):
            con.execute(f'UPDATE {t} SET OwnerID=? WHERE OwnerType=0 AND OwnerID=?', (keep, drop))
        con.execute('UPDATE WitnessTable SET PersonID=? WHERE PersonID=?', (keep, drop))
        con.execute('UPDATE FANTable SET ID1=? WHERE ID1=?', (keep, drop))
        con.execute('UPDATE FANTable SET ID2=? WHERE ID2=?', (keep, drop))
        con.execute('UPDATE DNATable SET ID1=? WHERE ID1=?', (keep, drop))
        con.execute('UPDATE DNATable SET ID2=? WHERE ID2=?', (keep, drop))
        con.execute('UPDATE HealthTable SET OwnerID=? WHERE OwnerID=?', (keep, drop))
        # families: as spouse
        for f in rows(con, 'SELECT * FROM FamilyTable WHERE FatherID=? OR MotherID=?', drop, drop):
            col = 'FatherID' if f['FatherID'] == drop else 'MotherID'
            other = f['MotherID'] if col == 'FatherID' else f['FatherID']
            existing = m.find_family(con, keep, other) if other else None
            if existing and existing['FamilyID'] != f['FamilyID']:
                _merge_families(con, existing['FamilyID'], f['FamilyID'])
            else:
                con.execute(f'UPDATE FamilyTable SET {col}=? WHERE FamilyID=?', (keep, f['FamilyID']))
        # families: as child
        keep_fams = {r['FamilyID'] for r in rows(con, 'SELECT FamilyID FROM ChildTable WHERE ChildID=?', keep)}
        for c in rows(con, 'SELECT * FROM ChildTable WHERE ChildID=?', drop):
            if c['FamilyID'] in keep_fams:
                con.execute('DELETE FROM ChildTable WHERE RecID=?', (c['RecID'],))
            else:
                con.execute('UPDATE ChildTable SET ChildID=? WHERE RecID=?', (keep, c['RecID']))
        p_keep = row(con, 'SELECT * FROM PersonTable WHERE PersonID=?', keep)
        p_drop = row(con, 'SELECT * FROM PersonTable WHERE PersonID=?', drop)
        note = '\n\n'.join(x for x in (p_keep['Note'], p_drop['Note']) if x)
        sex = p_keep['Sex'] if p_keep['Sex'] != 2 else p_drop['Sex']
        con.execute('UPDATE PersonTable SET Note=?, Sex=? WHERE PersonID=?', (note, sex, keep))
        for g in m.groups(con):
            mem = m.group_members(con, g['GroupID'])
            if drop in mem:
                mem.remove(drop)
                if keep not in mem:
                    mem.append(keep)
                m.set_group_members(con, g['GroupID'], mem)
        con.execute('DELETE FROM PersonTable WHERE PersonID=?', (drop,))
        con.execute('DELETE FROM ExclusionTable WHERE ID1=? OR ID2=?', (drop, drop))
        _dedupe_facts(con, keep)
        m._fix_person_family_pointers(con)
        m.refresh_name_years(con, keep)


def _merge_families(con, keep, drop):
    con.execute('UPDATE EventTable SET OwnerID=? WHERE OwnerType=1 AND OwnerID=?', (keep, drop))
    for t in ('CitationLinkTable', 'MediaLinkTable', 'TaskLinkTable'):
        con.execute(f'UPDATE {t} SET OwnerID=? WHERE OwnerType=1 AND OwnerID=?', (keep, drop))
    kids = set(m.children_of(con, keep))
    for c in rows(con, 'SELECT * FROM ChildTable WHERE FamilyID=?', drop):
        if c['ChildID'] in kids:
            con.execute('DELETE FROM ChildTable WHERE RecID=?', (c['RecID'],))
        else:
            con.execute('UPDATE ChildTable SET FamilyID=? WHERE RecID=?', (keep, c['RecID']))
    con.execute('DELETE FROM FamilyTable WHERE FamilyID=?', (drop,))


def _dedupe_facts(con, pid):
    """After a merge, drop exact duplicate facts (same type/date/place/desc), keeping citations."""
    seen = {}
    for e in rows(con, 'SELECT * FROM EventTable WHERE OwnerType=0 AND OwnerID=? ORDER BY EventID', pid):
        k = (e['EventType'], e['Date'], e['PlaceID'], e['SiteID'], e['Details'] or '')
        if k in seen:
            con.execute('UPDATE CitationLinkTable SET OwnerID=? WHERE OwnerType=2 AND OwnerID=?', (seen[k], e['EventID']))
            con.execute('UPDATE MediaLinkTable SET OwnerID=? WHERE OwnerType=2 AND OwnerID=?', (seen[k], e['EventID']))
            con.execute('DELETE FROM EventTable WHERE EventID=?', (e['EventID'],))
        else:
            seen[k] = e['EventID']
    dup_names = {}
    for n in rows(con, 'SELECT * FROM NameTable WHERE OwnerID=? ORDER BY IsPrimary DESC, NameID', pid):
        k = (n['Given'] or '', n['Surname'] or '', n['Suffix'] or '')
        if k in dup_names:
            con.execute('UPDATE CitationLinkTable SET OwnerID=? WHERE OwnerType=7 AND OwnerID=?', (dup_names[k], n['NameID']))
            con.execute('DELETE FROM NameTable WHERE NameID=?', (n['NameID'],))
        else:
            dup_names[k] = n['NameID']


def auto_merge(con):
    """Merge exact duplicates: same name, sex, birth date (full), and same parents' names."""
    groups = {}
    for r in rows(con, 'SELECT PersonID FROM PersonTable'):
        k = person_key(con, r['PersonID'])
        if not (k['given'] and k['surname'] and k['bdate'] and rmdate.ymd(k['bdate']) and rmdate.ymd(k['bdate'])[2]):
            continue
        groups.setdefault((k['given'], k['surname'], k['sex'], k['bdate'], k['father'], k['mother']), []).append(k['id'])
    merged = 0
    for ids in groups.values():
        for d in ids[1:]:
            merge_people(con, ids[0], d)
            merged += 1
    return merged


# ------------------------------------------------------------------ problem list
PROBLEM_RULES = {
    'birth_after_death': 'Born after death',
    'burial_before_death': 'Buried before death',
    'too_old': 'Age at death over {maxAge}',
    'married_young': 'Married before age {minMarriageAge}',
    'married_old': 'Married after age {maxMarriageAge}',
    'mother_young': 'Mother younger than {minMotherAge} at birth of child',
    'mother_old': 'Mother older than {maxMotherAge} at birth of child',
    'father_young': 'Father younger than {minFatherAge} at birth of child',
    'father_old': 'Father older than {maxFatherAge} at birth of child',
    'born_after_mother_death': 'Born after mother died',
    'born_long_after_father_death': 'Born more than 1 year after father died',
    'married_after_death': 'Married after death',
    'child_before_marriage': 'Child born before parents married',
    'children_too_close': 'Siblings born less than {minChildGapMonths} months apart',
    'same_sex_parents': 'Both parents have the same sex',
    'missing_sex': 'Sex unknown',
    'missing_name': 'Missing surname or given name',
    'facts_after_death': 'Fact dated more than a year after death (other than burial/probate)',
}
PROBLEM_DEFAULTS = {'maxAge': 110, 'minMarriageAge': 13, 'maxMarriageAge': 80, 'minMotherAge': 13,
                    'maxMotherAge': 50, 'minFatherAge': 13, 'maxFatherAge': 80, 'minChildGapMonths': 9}


def _years(d1, d2):
    """Signed years from d1 to d2 (negative when d2 precedes d1); None if either is undated."""
    a, b = rmdate.ymd(d1), rmdate.ymd(d2)
    if not a or not b:
        return None
    return (b[0] - a[0]) + ((b[1] or 1) - (a[1] or 1)) / 12


def problem_list(con, options=None, rules=None):
    o = dict(PROBLEM_DEFAULTS, **(options or {}))
    rules = set(rules or PROBLEM_RULES)
    excl = {(r['ID1'], r['ID2']) for r in rows(con, 'SELECT ID1, ID2 FROM ExclusionTable WHERE ExclusionType=2')}
    out = []
    s = m.settings(con)

    def add(pid, rule, detail=''):
        rid = list(PROBLEM_RULES).index(rule)
        if (pid, rid) in excl:
            return
        out.append({'person': m.person_summary(con, pid, s), 'rule': rule, 'ruleId': rid,
                    'problem': PROBLEM_RULES[rule].format(**o) + (f' ({detail})' if detail else '')})

    for p in rows(con, 'SELECT PersonID, Sex FROM PersonTable'):
        pid = p['PersonID']
        b = m.first_event(con, pid, (1, 3, 7))
        d = m.first_event(con, pid, (2,))
        bu = m.first_event(con, pid, (4, 5))
        bd, dd = (b or {}).get('Date'), (d or {}).get('Date')
        if 'birth_after_death' in rules and bd and dd and b['SortDate'] > d['SortDate'] and rmdate.year(dd):
            add(pid, 'birth_after_death')
        if 'burial_before_death' in rules and bu and d and bu['SortDate'] < d['SortDate'] and rmdate.year(bu['Date']):
            add(pid, 'burial_before_death')
        if 'too_old' in rules and bd and dd:
            y = _years(bd, dd)
            if y and y > o['maxAge']:
                add(pid, 'too_old', f'{int(y)}')
        if 'missing_sex' in rules and p['Sex'] == 2:
            add(pid, 'missing_sex')
        n = m.primary_name(con, pid)
        if 'missing_name' in rules and (not n.get('Surname') or not n.get('Given')):
            add(pid, 'missing_name')
        if 'facts_after_death' in rules and dd and rmdate.year(dd):
            for e in rows(con, 'SELECT * FROM EventTable WHERE OwnerType=0 AND OwnerID=? AND EventType NOT IN (2,4,5,19,20)', pid):
                if e['SortDate'] != rmdate.EMPTY_SORT and rmdate.year(e['Date']) > rmdate.year(dd) + 1:
                    add(pid, 'facts_after_death', m.fact_type(con, e['EventType'])['Name'])
                    break
        for f in m.spouse_families(con, pid):
            mar = m.first_event(con, f['FamilyID'], (300,), owner=1)
            if mar and bd:
                y = _years(bd, mar['Date'])
                if y is not None and 'married_young' in rules and y < o['minMarriageAge']:
                    add(pid, 'married_young', f'{int(y)}')
                if y is not None and 'married_old' in rules and y > o['maxMarriageAge']:
                    add(pid, 'married_old', f'{int(y)}')
            if mar and dd and 'married_after_death' in rules and rmdate.year(mar['Date']) and mar['SortDate'] > d['SortDate']:
                add(pid, 'married_after_death')
    for f in rows(con, 'SELECT * FROM FamilyTable'):
        fa, mo = f['FatherID'], f['MotherID']
        if 'same_sex_parents' in rules and fa and mo:
            sx = [row(con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', x)['Sex'] for x in (fa, mo)]
            if sx[0] == sx[1] and sx[0] != 2:
                add(fa, 'same_sex_parents')
        mar = m.first_event(con, f['FamilyID'], (300,), owner=1)
        fb, fd = m.first_event(con, fa, (1, 3, 7)) if fa else None, m.first_event(con, fa, (2,)) if fa else None
        mb, md = m.first_event(con, mo, (1, 3, 7)) if mo else None, m.first_event(con, mo, (2,)) if mo else None
        births = []
        for c in m.children_of(con, f['FamilyID']):
            rel = row(con, 'SELECT RelFather, RelMother FROM ChildTable WHERE FamilyID=? AND ChildID=?', f['FamilyID'], c)
            cb = m.first_event(con, c, (1, 3, 7))
            if not cb or not rmdate.year(cb['Date']):
                continue
            births.append(cb)
            if rel and (rel['RelFather'] or rel['RelMother']):
                continue
            if mb:
                y = _years(mb['Date'], cb['Date'])
                if y is not None and 'mother_young' in rules and y < o['minMotherAge']:
                    add(c, 'mother_young', f'{int(y)}')
                if y is not None and 'mother_old' in rules and y > o['maxMotherAge']:
                    add(c, 'mother_old', f'{int(y)}')
            if fb:
                y = _years(fb['Date'], cb['Date'])
                if y is not None and 'father_young' in rules and y < o['minFatherAge']:
                    add(c, 'father_young', f'{int(y)}')
                if y is not None and 'father_old' in rules and y > o['maxFatherAge']:
                    add(c, 'father_old', f'{int(y)}')
            if 'born_after_mother_death' in rules and md and rmdate.ymd(md['Date']) and rmdate.ymd(md['Date'])[1] \
                    and cb['SortDate'] > md['SortDate']:
                add(c, 'born_after_mother_death')
            if 'born_long_after_father_death' in rules and fd and rmdate.year(fd['Date']):
                y = _years(fd['Date'], cb['Date'])
                if y is not None and y > 1:
                    add(c, 'born_long_after_father_death')
            if 'child_before_marriage' in rules and mar and rmdate.year(mar['Date']) and cb['SortDate'] < mar['SortDate'] \
                    and rmdate.year(cb['Date']) < rmdate.year(mar['Date']):
                add(c, 'child_before_marriage')
        if 'children_too_close' in rules:
            full = sorted((b for b in births if (rmdate.ymd(b['Date']) or (0, 0, 0))[2]), key=lambda b: b['SortDate'])
            for a, b in zip(full, full[1:]):
                gap = rmdate.age_between(a['Date'], b['Date'])
                if gap and gap[0] == 0 and 0 < gap[1] < o['minChildGapMonths'] and a['Date'] != b['Date']:
                    add(b['OwnerID'], 'children_too_close')
    return out


def not_a_problem(con, pid, rule_id):
    con.execute('INSERT OR IGNORE INTO ExclusionTable (ExclusionType, ID1, ID2, UTCModDate) VALUES (2,?,?,?)',
                (pid, rule_id, db.utc_now()))


# ------------------------------------------------------------------ DataClean
def place_issues(con):
    """Places that look malformed, with a suggested fix."""
    out = []
    for p in rows(con, 'SELECT PlaceID, Name FROM PlaceTable WHERE PlaceType=0'):
        name = p['Name'] or ''
        fixed = re.sub(r'\s+', ' ', name).strip()
        fixed = re.sub(r'\s*,\s*', ', ', fixed)
        fixed = re.sub(r'(,\s*)+', ', ', fixed).strip(', ')
        if fixed.isupper() and len(fixed) > 3:
            fixed = fixed.title()
        if fixed != name:
            out.append({'id': p['PlaceID'], 'name': name, 'suggestion': fixed,
                        'issue': 'all caps' if name.isupper() else 'spacing / commas'})
    names = {}
    for p in rows(con, 'SELECT PlaceID, Name FROM PlaceTable WHERE PlaceType=0'):
        names.setdefault(re.sub(r'[\s,]+', ' ', (p['Name'] or '').lower()).strip(), []).append(p)
    for k, ps in names.items():
        if len(ps) > 1:
            out.append({'id': ps[1]['PlaceID'], 'name': ps[1]['Name'], 'suggestion': ps[0]['Name'],
                        'mergeInto': ps[0]['PlaceID'], 'issue': 'duplicate place'})
    return out


PREFIXES = {'dr', 'dr.', 'rev', 'rev.', 'capt', 'capt.', 'col', 'col.', 'sir', 'lord', 'lady', 'mr', 'mr.', 'mrs', 'mrs.',
            'miss', 'ms', 'ms.', 'gen', 'gen.', 'lt', 'lt.', 'sgt', 'sgt.', 'prof', 'prof.', 'hon', 'hon.'}
SUFFIXES = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v', 'esq', 'esq.', 'md', 'm.d.', 'phd', 'ph.d.'}


def name_issues(con):
    out = []
    for n in rows(con, 'SELECT * FROM NameTable'):
        g, s = n['Given'] or '', n['Surname'] or ''
        fix = dict(Given=g, Surname=s, Prefix=n['Prefix'] or '', Suffix=n['Suffix'] or '', Nickname=n['Nickname'] or '')
        issues = []
        mm = re.search(r'\s*["(]([^")]+)[")]\s*', fix['Given'])
        if mm and not fix['Nickname']:
            fix['Nickname'] = mm[1]
            fix['Given'] = (fix['Given'][:mm.start()] + ' ' + fix['Given'][mm.end():]).strip()
            issues.append('nickname in given name')
        words = fix['Given'].split()
        if words and words[0].lower() in PREFIXES and not fix['Prefix']:
            fix['Prefix'] = words.pop(0)
            issues.append('prefix in given name')
        if words and words[-1].lower().strip(',') in SUFFIXES and not fix['Suffix']:
            fix['Suffix'] = words.pop().strip(',')
            issues.append('suffix in given name')
        sw = fix['Surname'].split()
        if sw and sw[-1].lower().strip(',') in SUFFIXES and not fix['Suffix']:
            fix['Suffix'] = sw.pop().strip(',')
            fix['Surname'] = ' '.join(sw)
            issues.append('suffix in surname')
        fix['Given'] = ' '.join(words)
        if fix['Surname'].isupper() and len(fix['Surname']) > 1:
            fix['Surname'] = _title_surname(fix['Surname'])
            issues.append('all caps surname')
        if fix['Given'].isupper() and len(fix['Given']) > 2:
            fix['Given'] = fix['Given'].title()
            issues.append('all caps given name')
        for k in ('Given', 'Surname'):
            fix[k] = re.sub(r'\s+', ' ', fix[k]).strip()
        if fix['Given'] != g.strip() and not issues:
            issues.append('extra spaces')
        if issues:
            out.append({'id': n['NameID'], 'person': n['OwnerID'], 'issues': issues,
                        'before': m.fmt_name(n, 'full'), 'after': m.fmt_name(fix, 'full'), 'fix': fix})
    return out


def _title_surname(s):
    t = s.title()
    t = re.sub(r"\bMc(\w)", lambda x: 'Mc' + x[1].upper(), t)
    t = re.sub(r"\bO'(\w)", lambda x: "O'" + x[1].upper(), t)
    for p in ('Van ', 'Von ', 'De ', 'Del ', 'Der ', 'Du ', 'La ', 'Le '):
        if t.startswith(p) and len(t) > len(p):
            t = p.lower() + t[len(p):]
    return t


def apply_name_fixes(con, fixes):
    with tx(con):
        for f in fixes:
            m.save_name(con, dict(f['fix'], NameID=f['id']))
    return len(fixes)


def apply_place_fixes(con, fixes):
    with tx(con):
        for f in fixes:
            if f.get('mergeInto'):
                m.merge_places(con, f['mergeInto'], f['id'])
            else:
                con.execute('UPDATE PlaceTable SET Name=?, Reverse=? WHERE PlaceID=?',
                            (f['suggestion'], m.reverse_place(f['suggestion']), f['id']))
    return len(fixes)


# ------------------------------------------------------------------ search & replace / find everywhere
SEARCHABLE = [  # (table, pk, column, label, owner kind)
    ('NameTable', 'NameID', 'Given', 'Given name', 'name'), ('NameTable', 'NameID', 'Surname', 'Surname', 'name'),
    ('NameTable', 'NameID', 'Nickname', 'Nickname', 'name'), ('NameTable', 'NameID', 'Note', 'Name note', 'name'),
    ('PersonTable', 'PersonID', 'Note', 'Person note', 'person'),
    ('FamilyTable', 'FamilyID', 'Note', 'Family note', 'family'),
    ('EventTable', 'EventID', 'Details', 'Fact description', 'event'),
    ('EventTable', 'EventID', 'Note', 'Fact note', 'event'),
    ('EventTable', 'EventID', 'Sentence', 'Fact sentence', 'event'),
    ('PlaceTable', 'PlaceID', 'Name', 'Place', 'place'), ('PlaceTable', 'PlaceID', 'Note', 'Place note', 'place'),
    ('SourceTable', 'SourceID', 'Name', 'Source name', 'source'),
    ('SourceTable', 'SourceID', 'Fields', 'Source fields', 'source'),
    ('SourceTable', 'SourceID', 'ActualText', 'Source text', 'source'),
    ('SourceTable', 'SourceID', 'Comments', 'Source comments', 'source'),
    ('CitationTable', 'CitationID', 'Fields', 'Citation fields', 'citation'),
    ('CitationTable', 'CitationID', 'ActualText', 'Citation text', 'citation'),
    ('CitationTable', 'CitationID', 'Comments', 'Citation comments', 'citation'),
    ('MultimediaTable', 'MediaID', 'Caption', 'Media caption', 'media'),
    ('MultimediaTable', 'MediaID', 'Description', 'Media description', 'media'),
    ('TaskTable', 'TaskID', 'Name', 'Task', 'task'), ('TaskTable', 'TaskID', 'Details', 'Task details', 'task'),
    ('AddressTable', 'AddressID', 'Name', 'Address name', 'address'),
    ('URLTable', 'LinkID', 'URL', 'WebTag', 'webtag'),
]


def _owner_label(con, kind, rec):
    if kind == 'name':
        return m.person_name(con, rec['OwnerID']), ('person', rec['OwnerID'])
    if kind == 'person':
        return m.person_name(con, rec['PersonID']), ('person', rec['PersonID'])
    if kind == 'family':
        return m.couple_name(con, rec), ('family', rec['FamilyID'])
    if kind == 'event':
        ft = m.fact_type(con, rec['EventType']) or {}
        label = f"{ft.get('Name', 'Fact')}: {m.event_owner_name(con, rec)}"
        if rec['OwnerType'] == 0:
            return label, ('person', rec['OwnerID'])
        f = row(con, 'SELECT FatherID, MotherID FROM FamilyTable WHERE FamilyID=?', rec['OwnerID']) or {}
        return label, ('person', f.get('FatherID') or f.get('MotherID') or 0)
    if kind == 'place':
        return rec['Name'], ('place', rec['PlaceID'])
    if kind == 'source':
        return rec['Name'], ('source', rec['SourceID'])
    if kind == 'citation':
        src = row(con, 'SELECT Name FROM SourceTable WHERE SourceID=?', rec['SourceID']) or {}
        return f"Citation of {src.get('Name', '')}", ('source', rec['SourceID'])
    if kind == 'media':
        return rec['Caption'] or rec['MediaFile'], ('media', rec['MediaID'])
    if kind == 'task':
        return rec['Name'], ('task', rec['TaskID'])
    if kind == 'address':
        return rec['Name'], ('address', rec['AddressID'])
    if kind == 'webtag':
        return rec['Name'], ('person', rec['OwnerID'] if rec['OwnerType'] == 0 else 0)
    return '', ('', 0)


def find_everywhere(con, text, limit=500):
    out = []
    if not text:
        return out
    like = f'%{text}%'
    for table, pk, col, label, kind in SEARCHABLE:
        for r in rows(con, f'SELECT * FROM {table} WHERE CAST({col} AS TEXT) LIKE ? LIMIT ?', like, limit):
            val = r[col]
            if isinstance(val, bytes):
                val = val.decode('utf-8', 'replace')
            if kind in ('source', 'citation') and col == 'Fields':
                val = ' | '.join(v for v in m.xml_to_fields(val).values() if text.lower() in v.lower())
                if not val:
                    continue
            owner, link = _owner_label(con, kind, r)
            i = (val or '').lower().find(text.lower())
            snippet = (val or '')[max(0, i - 40):i + len(text) + 60]
            out.append({'where': label, 'owner': owner, 'link': link, 'snippet': snippet})
            if len(out) >= limit:
                return out
    return out


def search_replace(con, find, replace, fields=None, whole_word=False, case_sensitive=False, preview=True):
    """Replace text in chosen searchable fields. Returns list of changes (applied unless preview)."""
    if not find:
        return []
    flags = 0 if case_sensitive else re.I
    pat = re.compile((r'\b%s\b' if whole_word else '%s') % re.escape(find), flags)
    fields = set(fields or [s[3] for s in SEARCHABLE])
    changes = []
    with tx(con):
        for table, pk, col, label, kind in SEARCHABLE:
            if label not in fields:
                continue
            for r in rows(con, f'SELECT * FROM {table} WHERE CAST({col} AS TEXT) LIKE ?', f'%{find}%'):
                val = r[col]
                if isinstance(val, bytes):
                    val = val.decode('utf-8', 'replace')
                new = pat.sub(replace, val or '')
                if new == val:
                    continue
                owner, link = _owner_label(con, kind, r)
                changes.append({'where': label, 'owner': owner, 'before': val[:200], 'after': new[:200], 'link': link})
                if not preview:
                    con.execute(f'UPDATE {table} SET {col}=? WHERE {pk}=?', (new, r[pk]))
                    if table == 'PlaceTable' and col == 'Name':
                        con.execute('UPDATE PlaceTable SET Reverse=? WHERE PlaceID=?', (m.reverse_place(new), r[pk]))
                    if table == 'NameTable' and col in ('Surname', 'Given', 'Nickname'):
                        con.execute(f'UPDATE NameTable SET {col}MP=? WHERE NameID=?', (m.metaphone_key(new), r[pk]))
    return changes


# ------------------------------------------------------------------ database tools
def db_tools(con, action):
    if action == 'integrity':
        return {'result': [r[0] for r in con.execute('PRAGMA integrity_check')]}
    if action == 'compact':
        con.execute('VACUUM')
        return {'result': ['Database compacted']}
    if action == 'reindex':
        con.execute('REINDEX')
        return {'result': ['Indexes rebuilt']}
    if action == 'phantoms':
        stmts = [
            'DELETE FROM ChildTable WHERE ChildID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM ChildTable WHERE FamilyID NOT IN (SELECT FamilyID FROM FamilyTable)',
            'UPDATE FamilyTable SET FatherID=0 WHERE FatherID<>0 AND FatherID NOT IN (SELECT PersonID FROM PersonTable)',
            'UPDATE FamilyTable SET MotherID=0 WHERE MotherID<>0 AND MotherID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM NameTable WHERE OwnerID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM EventTable WHERE OwnerType=0 AND OwnerID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM EventTable WHERE OwnerType=1 AND OwnerID NOT IN (SELECT FamilyID FROM FamilyTable)',
            'DELETE FROM CitationLinkTable WHERE CitationID NOT IN (SELECT CitationID FROM CitationTable)',
            'DELETE FROM CitationLinkTable WHERE OwnerType=2 AND OwnerID NOT IN (SELECT EventID FROM EventTable)',
            'DELETE FROM CitationLinkTable WHERE OwnerType=0 AND OwnerID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM MediaLinkTable WHERE MediaID NOT IN (SELECT MediaID FROM MultimediaTable)',
            'DELETE FROM WitnessTable WHERE EventID NOT IN (SELECT EventID FROM EventTable)',
            'DELETE FROM TaskLinkTable WHERE TaskID NOT IN (SELECT TaskID FROM TaskTable)',
            'DELETE FROM URLTable WHERE OwnerType=0 AND OwnerID NOT IN (SELECT PersonID FROM PersonTable)',
            'DELETE FROM FANTable WHERE ID1 NOT IN (SELECT PersonID FROM PersonTable) OR ID2 NOT IN (SELECT PersonID FROM PersonTable)',
        ]
        out = []
        with tx(con):
            for sql in stmts:
                n = con.execute(sql).rowcount
                if n:
                    out.append(f'{n} rows: {sql}')
            m._fix_person_family_pointers(con)
        return {'result': out or ['No phantom records found']}
    if action == 'unusedPlaces':
        n = con.execute('''DELETE FROM PlaceTable WHERE PlaceType IN (0,2) AND PlaceID NOT IN (SELECT PlaceID FROM EventTable)
                           AND PlaceID NOT IN (SELECT SiteID FROM EventTable) AND PlaceID NOT IN (SELECT PlaceID FROM FANTable)
                           AND PlaceID NOT IN (SELECT MasterID FROM PlaceTable)''').rowcount
        return {'result': [f'{n} unused places deleted']}
    if action == 'unusedSources':
        n = con.execute('DELETE FROM SourceTable WHERE SourceID NOT IN (SELECT SourceID FROM CitationTable)').rowcount
        return {'result': [f'{n} unused sources deleted']}
    raise ValueError(action)


# ------------------------------------------------------------------ backup / restore / file ops
def backup(path, dest_dir, include_media=False):
    con = db.connect(path)
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
    base = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(dest_dir, f'{base}_{stamp}.rmbackup')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(path, os.path.basename(path))
        if include_media:
            for mm in rows(con, 'SELECT MediaPath, MediaFile FROM MultimediaTable'):
                p = m.media_path(mm)
                if p and os.path.isfile(p):
                    z.write(p, 'media/' + os.path.basename(p))
    con.close()
    return out


def restore(backup_path, dest_dir):
    with zipfile.ZipFile(backup_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(('.rmtree', '.rmgc', '.db', '.sqlite'))]
        if not names:
            raise ValueError('No database in backup')
        target = os.path.join(dest_dir, os.path.basename(names[0]))
        if os.path.exists(target):
            stem, ext = os.path.splitext(target)
            target = f'{stem}_restored_{datetime.datetime.now():%Y%m%d%H%M%S}{ext}'
        with z.open(names[0]) as src, open(target, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        media = [n for n in z.namelist() if n.startswith('media/') and not n.endswith('/')]
        if media:
            mdir = os.path.join(dest_dir, 'media')
            os.makedirs(mdir, exist_ok=True)
            for n in media:
                safe = os.path.basename(n)
                with z.open(n) as src, open(os.path.join(mdir, safe), 'wb') as dst:
                    shutil.copyfileobj(src, dst)
    return target


def compare_files(con_a, path_b):
    """People matched by surname+given+birth year; report only-in-A, only-in-B, and differing facts."""
    con_b = db.connect(path_b)

    def index(con):
        out = {}
        for r in rows(con, 'SELECT PersonID FROM PersonTable'):
            k = person_key(con, r['PersonID'])
            out.setdefault((k['surname'], k['given'], k['by']), []).append(r['PersonID'])
        return out
    ia, ib = index(con_a), index(con_b)
    sa, sb = m.settings(con_a), m.settings(con_b)
    only_a = [m.person_summary(con_a, i, sa) for k in ia.keys() - ib.keys() for i in ia[k]]
    only_b = [m.person_summary(con_b, i, sb) for k in ib.keys() - ia.keys() for i in ib[k]]
    diffs = []
    for k in ia.keys() & ib.keys():
        a, b = ia[k][0], ib[k][0]
        fa = {(f['typeName'], f['date'], f['place']) for f in m.facts_for(con_a, 'person', a, sa, False)}
        fb = {(f['typeName'], f['date'], f['place']) for f in m.facts_for(con_b, 'person', b, sb, False)}
        if fa != fb:
            diffs.append({'a': m.person_summary(con_a, a, sa), 'b': m.person_summary(con_b, b, sb),
                          'onlyA': sorted(fa - fb), 'onlyB': sorted(fb - fa)})
    con_b.close()
    return {'onlyA': only_a, 'onlyB': only_b, 'different': diffs, 'matched': len(ia.keys() & ib.keys())}


def import_lists(con, path_b, what):
    """Copy list items (fact types, templates, places, sources+repos, FAN types, roles) from another file."""
    src = db.connect(path_b)
    added = {}
    with tx(con):
        if 'factTypes' in what:
            n = 0
            for f in rows(src, 'SELECT * FROM FactTypeTable'):
                if not row(con, 'SELECT 1 AS x FROM FactTypeTable WHERE Name=? AND OwnerType=?', f['Name'], f['OwnerType']):
                    f['FactTypeID'] = max(1000, con.execute('SELECT MAX(FactTypeID) FROM FactTypeTable').fetchone()[0] + 1)
                    insert(con, 'FactTypeTable', f)
                    n += 1
            added['factTypes'] = n
        if 'templates' in what:
            n = 0
            for t in rows(src, 'SELECT * FROM SourceTemplateTable'):
                if not row(con, 'SELECT 1 AS x FROM SourceTemplateTable WHERE Name=?', t['Name']):
                    t.pop('TemplateID')
                    insert(con, 'SourceTemplateTable', t)
                    n += 1
            added['templates'] = n
        if 'places' in what:
            n = 0
            for p in rows(src, 'SELECT * FROM PlaceTable WHERE PlaceType<>2'):
                if not row(con, 'SELECT 1 AS x FROM PlaceTable WHERE Name=? AND PlaceType=?', p['Name'], p['PlaceType']):
                    p.pop('PlaceID')
                    p['MasterID'] = 0
                    insert(con, 'PlaceTable', p)
                    n += 1
            added['places'] = n
        if 'sources' in what:
            n = 0
            tmap = {}
            for s in rows(src, 'SELECT * FROM SourceTable'):
                if row(con, 'SELECT 1 AS x FROM SourceTable WHERE Name=?', s['Name']):
                    continue
                if s['TemplateID'] and s['TemplateID'] not in tmap:
                    t = row(src, 'SELECT * FROM SourceTemplateTable WHERE TemplateID=?', s['TemplateID'])
                    mine = t and row(con, 'SELECT TemplateID FROM SourceTemplateTable WHERE Name=?', t['Name'])
                    if t and not mine:
                        t.pop('TemplateID')
                        tmap[s['TemplateID']] = insert(con, 'SourceTemplateTable', t)
                    else:
                        tmap[s['TemplateID']] = mine['TemplateID'] if mine else 0
                s.pop('SourceID')
                s['TemplateID'] = tmap.get(s['TemplateID'], 0)
                insert(con, 'SourceTable', s)
                n += 1
            added['sources'] = n
            n = 0
            for a in rows(src, 'SELECT * FROM AddressTable WHERE AddressType=1'):
                if not row(con, 'SELECT 1 AS x FROM AddressTable WHERE Name=? AND AddressType=1', a['Name']):
                    a.pop('AddressID')
                    insert(con, 'AddressTable', a)
                    n += 1
            added['repositories'] = n
        if 'fanTypes' in what:
            n = 0
            for f in rows(src, 'SELECT * FROM FANTypeTable'):
                if not row(con, 'SELECT 1 AS x FROM FANTypeTable WHERE Name=?', f['Name']):
                    f.pop('FANTypeID')
                    insert(con, 'FANTypeTable', f)
                    n += 1
            added['fanTypes'] = n
        if 'roles' in what:
            n = 0
            for r in rows(src, 'SELECT * FROM RoleTable'):
                if not row(con, 'SELECT 1 AS x FROM RoleTable WHERE RoleName=? AND EventType=?', r['RoleName'], r['EventType']):
                    r.pop('RoleID')
                    insert(con, 'RoleTable', r)
                    n += 1
            added['roles'] = n
    src.close()
    return added


def import_template_library(con, path):
    """Load RootsMagic's master template file (rootsmagic.st XML) into SourceTemplateTable."""
    import xml.etree.ElementTree as ET
    data = open(path, 'rb').read().decode('utf-8-sig')
    root = ET.fromstring(data)
    n = 0
    with tx(con):
        for t in root.iter('Template'):
            name = t.findtext('Name') or ''
            if row(con, 'SELECT 1 AS x FROM SourceTemplateTable WHERE Name=?', name):
                continue
            fields = [(f.findtext('Type') or 'Text', f.findtext('Name') or '', f.findtext('Display') or '',
                       f.findtext('Hint') or '', f.findtext('Detail') or 'False') for f in t.iter('Field')]
            insert(con, 'SourceTemplateTable', {'Name': name, 'Description': t.findtext('Description') or '',
                                                'Favorite': 0, 'Category': t.findtext('Category') or '',
                                                'Footnote': t.findtext('Footnote') or '',
                                                'ShortFootnote': t.findtext('ShortFootnote') or '',
                                                'Bibliography': t.findtext('Bibliography') or '',
                                                'FieldDefs': db._tf(*fields)})
            n += 1
    return n


# ------------------------------------------------------------------ misc lists
def on_this_day(con, month, day, types=None):
    out = []
    s = m.settings(con)
    pat = f'D_+____{month:02d}{day:02d}%'
    for e in rows(con, 'SELECT * FROM EventTable WHERE Date LIKE ? ORDER BY SortDate', pat):
        if types and e['EventType'] not in types:
            continue
        ft = m.fact_type(con, e['EventType']) or {}
        out.append({'year': rmdate.year(e['Date']), 'fact': ft.get('Name', ''), 'who': m.event_owner_name(con, e),
                    'date': rmdate.format(e['Date'], s['dateFormat']), 'place': m.place_name(con, e['PlaceID']),
                    'ownerType': e['OwnerType'], 'ownerId': e['OwnerID']})
    return out


def who_was_there(con, place_text, year_from, year_to):
    """People with a fact in a matching place, alive during the period (by birth/death years)."""
    s = m.settings(con)
    out = []
    pids = {r['OwnerID'] for r in rows(con, '''SELECT e.OwnerID FROM EventTable e JOIN PlaceTable p ON p.PlaceID=e.PlaceID
                                              WHERE e.OwnerType=0 AND p.Name LIKE ?''', f'%{place_text}%')}
    for f in rows(con, '''SELECT f.FatherID, f.MotherID FROM EventTable e JOIN PlaceTable p ON p.PlaceID=e.PlaceID
                          JOIN FamilyTable f ON f.FamilyID=e.OwnerID WHERE e.OwnerType=1 AND p.Name LIKE ?''', f'%{place_text}%'):
        pids.update(x for x in (f['FatherID'], f['MotherID']) if x)
    for pid in pids:
        p = m.person_summary(con, pid, s)
        by, dy = p['birthYear'] or (p['deathYear'] - 80 if p['deathYear'] else 0), p['deathYear'] or (p['birthYear'] + 80 if p['birthYear'] else 0)
        if by and by <= year_to and dy >= year_from:
            out.append(p)
    return sorted(out, key=lambda p: (p['surname'], p['given']))


def statistics(con):
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]
    s = {
        'people': q('SELECT COUNT(*) FROM PersonTable'), 'males': q('SELECT COUNT(*) FROM PersonTable WHERE Sex=0'),
        'females': q('SELECT COUNT(*) FROM PersonTable WHERE Sex=1'), 'unknownSex': q('SELECT COUNT(*) FROM PersonTable WHERE Sex=2'),
        'living': q('SELECT COUNT(*) FROM PersonTable WHERE Living=1'), 'families': q('SELECT COUNT(*) FROM FamilyTable'),
        'events': q('SELECT COUNT(*) FROM EventTable'), 'places': q('SELECT COUNT(*) FROM PlaceTable WHERE PlaceType=0'),
        'sources': q('SELECT COUNT(*) FROM SourceTable'), 'citations': q('SELECT COUNT(*) FROM CitationTable'),
        'media': q('SELECT COUNT(*) FROM MultimediaTable'), 'tasks': q('SELECT COUNT(*) FROM TaskTable'),
        'surnames': q("SELECT COUNT(DISTINCT Surname) FROM NameTable WHERE IsPrimary=1 AND Surname<>''"),
        'repositories': q('SELECT COUNT(*) FROM AddressTable WHERE AddressType=1'),
        'addresses': q('SELECT COUNT(*) FROM AddressTable WHERE AddressType=0'),
        'associations': q('SELECT COUNT(*) FROM FANTable'),
    }
    ages = []
    for r in rows(con, 'SELECT PersonID FROM PersonTable'):
        b, d = m.first_event(con, r['PersonID'], (1,)), m.first_event(con, r['PersonID'], (2,))
        if b and d:
            a = rmdate.age_between(b['Date'], d['Date'])
            if a:
                ages.append(a[0])
    s['averageLifespan'] = round(sum(ages) / len(ages), 1) if ages else None
    s['oldestAge'] = max(ages) if ages else None
    yrs = [r['y'] for r in rows(con, "SELECT CAST(substr(Date,4,4) AS INT) AS y FROM EventTable WHERE Date LIKE 'D%' AND substr(Date,4,4)<>'0000'")]
    s['earliestYear'], s['latestYear'] = (min(yrs), max(yrs)) if yrs else (None, None)
    return s


def surname_statistics(con):
    out = []
    for r in rows(con, '''SELECT n.Surname AS surname, COUNT(*) AS total, SUM(p.Sex=0) AS male, SUM(p.Sex=1) AS female,
                          MIN(NULLIF(n.BirthYear,0)) AS first, MAX(MAX(n.BirthYear), MAX(n.DeathYear)) AS last
                          FROM NameTable n JOIN PersonTable p ON p.PersonID=n.OwnerID
                          WHERE n.IsPrimary=1 GROUP BY n.Surname COLLATE RMNOCASE ORDER BY total DESC, n.Surname'''):
        out.append(r)
    return out


def ai_prompt(con, pid, goal='Suggest next research steps'):
    """Build a plain-text research prompt about a person (no network call is made)."""
    s = m.settings(con)
    p = m.person_summary(con, pid, s)
    lines = [f'I am researching my ancestor {p["name"]}.', '', 'Known facts:']
    for f in m.facts_for(con, 'person', pid, s, False):
        lines.append(f"- {f['typeName']}: {' '.join(x for x in (f['date'], f['place'], f['description']) if x)}")
    fa, mo, _ = m.primary_parents(con, pid)
    if fa or mo:
        lines.append(f"- Parents: {m.person_name(con, fa) or 'unknown'} and {m.person_name(con, mo) or 'unknown'}")
    for f in m.spouse_families(con, pid):
        if f['spouse']:
            kids = ', '.join(m.person_name(con, c) for c in m.children_of(con, f['FamilyID']))
            lines.append(f"- Spouse: {m.person_name(con, f['spouse'])}" + (f'; children: {kids}' if kids else ''))
    srcs = {c['SourceName'] for c in m.citations_for(con, 0, pid)}
    for f in m.facts_for(con, 'person', pid, s, False):
        srcs.update(c['SourceName'] for c in m.citations_for(con, 2, f['id']))
    if srcs - {None}:
        lines += ['', 'Sources already consulted:'] + [f'- {x}' for x in sorted(srcs - {None})]
    lines += ['', f'Task: {goal}. Please be specific about record types, repositories, and date ranges, '
                  'and flag anything in the facts above that looks inconsistent.']
    return '\n'.join(lines)


def web_search_urls(con, pid):
    s = m.settings(con)
    p = m.person_summary(con, pid, s)
    from urllib.parse import quote_plus
    vals = {'given': quote_plus(p['given'] or ''), 'surname': quote_plus(p['surname'] or ''),
            'birthyear': p['birthYear'] or '', 'deathyear': p['deathYear'] or ''}
    out = []
    for prov in s.get('webSearchProviders', []):
        url = prov['url']
        for k, v in vals.items():
            url = url.replace('{' + k + '}', str(v))
        out.append({'name': prov['name'], 'url': url})
    return out


def color_people(con, ids, color, color_set=0):
    col = 'Color' if not color_set else f'Color{color_set}'
    with tx(con):
        for i in ids:
            con.execute(f'UPDATE PersonTable SET {col}=? WHERE PersonID=?', (color, i))
    return len(ids)


if __name__ == '__main__':
    assert relationship_name(1, 1, 0) == 'brother'
    assert relationship_name(2, 2, 1) == 'first cousin'
    assert relationship_name(3, 2, 2) == 'first cousin once removed'
    assert relationship_name(2, 0, 0) == 'grandfather'
    assert relationship_name(3, 0, 1) == 'great-grandmother'
    assert relationship_name(4, 0, 1) == '2nd great-grandmother'
    assert relationship_name(0, 2, 0) == 'grandson'
    assert relationship_name(2, 1, 0) == 'uncle'
    assert relationship_name(3, 1, 1) == 'grandaunt'
    assert relationship_name(7, 0, 0) == '5th great-grandfather'
    assert relationship_name(1, 2, 0) == 'nephew'
    assert relationship_name(1, 3, 1) == 'grandniece'
    assert relationship_name(4, 4, 0) == 'third cousin'
    assert m.soundex('Robert') == 'R163' and m.soundex('Rupert') == 'R163' and m.soundex('Tymczak') == 'T522'
    print('tools ok')
