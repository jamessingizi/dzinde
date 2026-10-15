"""GEDCOM 5.5.1 import and export (with tolerance for 5.5, 7.0 and common vendor tags)."""
import html
import os
import re
from datetime import date

from . import model as m
from . import rmdate
from .db import OWNER, insert, row, rows, tx, unique_id

# ------------------------------------------------------------------ ANSEL
_ANSEL = {0xA1: 'Ł', 0xA2: 'Ø', 0xA3: 'Đ', 0xA4: 'Þ', 0xA5: 'Æ', 0xA6: 'Œ', 0xA7: 'ʹ', 0xA8: '·', 0xA9: '♭',
          0xAA: '®', 0xAB: '±', 0xAC: 'Ơ', 0xAD: 'Ư', 0xAE: 'ʼ', 0xB0: 'ʻ', 0xB1: 'ł', 0xB2: 'ø', 0xB3: 'đ',
          0xB4: 'þ', 0xB5: 'æ', 0xB6: 'œ', 0xB7: 'ʺ', 0xB8: 'ı', 0xB9: '£', 0xBA: 'ð', 0xBC: 'ơ', 0xBD: 'ư',
          0xC0: '°', 0xC1: 'ℓ', 0xC2: '℗', 0xC3: '©', 0xC4: '♯', 0xC5: '¿', 0xC6: '¡', 0xCF: 'ß'}
_ANSEL_COMB = {0xE0: '̉', 0xE1: '̀', 0xE2: '́', 0xE3: '̂', 0xE4: '̃', 0xE5: '̄',
               0xE6: '̆', 0xE7: '̇', 0xE8: '̈', 0xE9: '̌', 0xEA: '̊', 0xEB: '︠',
               0xEC: '︡', 0xED: '̕', 0xEE: '̋', 0xEF: '̐', 0xF0: '̧', 0xF1: '̨',
               0xF2: '̣', 0xF3: '̤', 0xF4: '̥', 0xF5: '̳', 0xF6: '̲', 0xF7: '̦',
               0xF8: '̜', 0xF9: '̮', 0xFE: '̓'}


def decode_ansel(b):
    import unicodedata
    out, pending = [], ''
    for x in b:
        if x in _ANSEL_COMB:
            pending += _ANSEL_COMB[x]  # ANSEL puts combining marks before the base letter
            continue
        ch = _ANSEL.get(x) or (chr(x) if x < 0x80 else '�')
        out.append(ch + pending)
        pending = ''
    return unicodedata.normalize('NFC', ''.join(out))


def decode_bytes(data):
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8', 'replace')
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    head = data[:3000].upper()
    m_ = re.search(rb'1 CHAR\s+(\S+)', head)
    charset = m_.group(1).decode() if m_ else ''
    if charset == 'ANSEL':
        return decode_ansel(data)
    if charset in ('ANSI', 'IBMPC', 'WINDOWS-1252', 'CP1252'):
        return data.decode('cp1252', 'replace')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('cp1252', 'replace')


# ------------------------------------------------------------------ parse tree
class Node:
    __slots__ = ('level', 'xref', 'tag', 'value', 'children')

    def __init__(self, level, xref, tag, value):
        self.level, self.xref, self.tag, self.value, self.children = level, xref, tag, value, []

    def first(self, tag):
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def all(self, tag):
        return [c for c in self.children if c.tag == tag]

    def val(self, tag, default=''):
        c = self.first(tag)
        return c.text() if c else default

    def text(self):
        """Value with CONT/CONC continuation lines folded in."""
        out = self.value or ''
        for c in self.children:
            if c.tag == 'CONT':
                out += '\n' + (c.value or '')
            elif c.tag == 'CONC':
                out += c.value or ''
        return out


LINE = re.compile(r'^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?: (.*))?$')


def parse(text):
    roots, stack = [], []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        mm = LINE.match(raw)
        if not mm:
            if stack:  # some exporters wrap long lines without CONC
                stack[-1].value = (stack[-1].value or '') + raw
            continue
        lvl = int(mm[1])
        n = Node(lvl, mm[2], mm[3].upper(), mm[4] if mm[4] is not None else '')
        while stack and stack[-1].level >= lvl:
            stack.pop()
        (stack[-1].children if stack else roots).append(n)
        stack.append(n)
    return roots


# ------------------------------------------------------------------ dates
_GMON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def gedcom_date_to_text(s):
    """GEDCOM date phrase -> text our parser understands (it already handles ABT/BEF/BET...)."""
    s = (s or '').strip()
    s = re.sub(r'@#D[A-Z ]+@\s*', '', s)  # calendar escapes
    if s.startswith('(') and s.endswith(')'):
        return s[1:-1]
    s = re.sub(r'^INT\s+(.*?)\s*\(.*\)$', r'\1', s, flags=re.I)
    s = re.sub(r'\bCAL\b', 'calc', s, flags=re.I)
    return s


def _gpart(p):
    if p.empty():
        return ''
    out = []
    if p.day:
        out.append(str(p.day))
    if p.month:
        out.append(_GMON[p.month - 1])
    if p.year:
        out.append(f'{p.year}/{(p.year + 1) % 100:02d}' if p.double else str(p.year))
    s = ' '.join(out)
    return s + ' B.C.' if p.bc else s


def to_gedcom_date(enc):
    g = rmdate.decode(enc)
    if g.kind == '':
        return ''
    if g.kind == 'T':
        return f'({g.text})'
    a = _gpart(g.p1)
    qual = {'A': 'ABT', 'C': 'ABT', 'E': 'EST', 'L': 'CAL'}.get(g.p1.qual, '')
    if g.p1.qual in '1234':
        qual = 'BET'
        b = _gpart(rmdate.Part(year=g.p1.year, month=g.p1.month + 2))
        return f'BET {_gpart(rmdate.Part(year=g.p1.year, month=g.p1.month))} AND {b}'
    if g.mod == 'R':
        return f'BET {a} AND {_gpart(g.p2)}'
    if g.mod == 'S':
        return f'FROM {a} TO {_gpart(g.p2)}'
    if g.mod == 'O':
        return f'BET {a} AND {_gpart(g.p2)}'
    if g.mod in ('B', 'U'):
        return f'BEF {a}'
    if g.mod in ('A', 'I'):
        return f'AFT {a}'
    if g.mod == 'F':
        return f'FROM {a}'
    if g.mod == 'T':
        return f'TO {a}'
    return f'{qual} {a}'.strip()


# ------------------------------------------------------------------ import
EVENT_LIKE = {'BIRT', 'CHR', 'DEAT', 'BURI', 'CREM', 'ADOP', 'BAPM', 'BARM', 'BASM', 'BLES', 'CHRA', 'CONF', 'FCOM',
              'ORDN', 'NATU', 'EMIG', 'IMMI', 'CENS', 'PROB', 'WILL', 'GRAD', 'RETI', 'EVEN', 'BAPL', 'CONL', 'ENDL',
              'SLGC', 'WAC', 'MARR', 'ANUL', 'DIV', 'DIVF', 'ENGA', 'MARB', 'MARC', 'MARL', 'MARS', 'SLGS', 'RESI',
              'CAST', 'DSCR', 'EDUC', 'IDNO', 'NATI', 'NCHI', 'NMR', 'OCCU', 'PROP', 'RELI', 'SSN', 'TITL', 'FACT',
              'AFN', 'REFN', 'SEPA', 'DEGR', '_MILT', '_MILITARY', '_MISN', '_DNA', '_ELEC', '_EXCM', '_NAMS',
              '_DEG', '_SEPR', '_ILLN', '_STILL', '_LIVING', '_FA1', '_FA2', '_FA3', '_FA4', '_FA5', '_PHYS',
              '_MDCL', '_HEIG', '_WEIG', 'NATU', '_EMPLOY', '_FUN', '_ORDI', '_CIRC'}
NOT_FACTS_INDI = {'NAME', 'SEX', 'FAMC', 'FAMS', 'NOTE', 'SOUR', 'OBJE', 'ASSO', '_UID', 'RIN', 'CHAN', 'RESN',
                  'SUBM', 'ALIA', 'ANCI', 'DESI', 'RFN', '_COLOR', '_TODO', 'ADDR', 'PHON', 'EMAIL', 'WWW', '_WEBTAG',
                  '_FSFTID', '_AMTID', '_PRIM', 'BIRT_', '_PRIV'}
NAME_TYPE_IN = {'AKA': 1, 'aka': 1, 'birth': 2, 'immigrant': 3, 'maiden': 4, 'married': 5, 'nickname': 6,
                'other spelling': 7}
PEDI_IN = {'birth': 0, 'adopted': 1, 'step': 2, 'foster': 3, 'related': 4, 'guardian': 5, 'sealed': 6, 'unknown': 7}
QUAY_IN = {'0': 'A~~', '1': 'D~~', '2': 'OS~', '3': 'OP~'}


class Importer:
    def __init__(self, con, text, media_base=''):
        self.con, self.roots = con, parse(text)
        self.media_base = media_base
        self.indi, self.fam, self.sour, self.repo, self.notes, self.obje = {}, {}, {}, {}, {}, {}
        self.stats = {k: 0 for k in ('people', 'families', 'events', 'sources', 'citations', 'repositories',
                                     'media', 'notes', 'places', 'associations', 'warnings')}
        self.warnings = []
        self.ftypes = {}
        for f in m.fact_types(con):
            if f['GedcomTag']:
                self.ftypes.setdefault((f['GedcomTag'].upper(), f['OwnerType']), f['FactTypeID'])
            self.ftypes.setdefault(('NAME:' + f['Name'].lower(), f['OwnerType']), f['FactTypeID'])

    def note_text(self, n):
        """NOTE value may be inline text or @xref@."""
        v = n.text()
        if v.startswith('@') and v.endswith('@'):
            rec = self.notes.get(v)
            return rec.text() if rec else ''
        return v

    def notes_of(self, node):
        return '\n\n'.join(t for t in (self.note_text(n) for n in node.all('NOTE')) if t)

    def run(self):
        with tx(self.con):
            for r in self.roots:
                if r.tag == 'NOTE' and r.xref:
                    self.notes[r.xref] = r
            for r in self.roots:
                if r.tag == 'REPO':
                    self.import_repo(r)
                elif r.tag == 'OBJE' and r.xref:
                    self.obje[r.xref] = self.import_media(r)
                elif r.tag in ('_PLAC', 'PLAC') and r.level == 0:
                    self.import_place_record(r)
                elif r.tag == 'SUBM':
                    self.import_subm(r)
            for r in self.roots:
                if r.tag == 'SOUR' and r.xref:
                    self.import_source(r)
            for r in self.roots:
                if r.tag == 'INDI':
                    self.indi[r.xref] = self.import_person_shell(r)
            for r in self.roots:
                if r.tag == 'FAM':
                    self.import_family(r)
            for r in self.roots:
                if r.tag == 'INDI':
                    self.import_person_details(r, self.indi[r.xref])
            m._fix_person_family_pointers(self.con)
            for pid in self.indi.values():
                m.refresh_name_years(self.con, pid)
        self.stats['warnings'] = len(self.warnings)
        return {'stats': self.stats, 'warnings': self.warnings[:200]}

    # -- records
    def import_subm(self, r):
        prep = {'name': r.val('NAME'), 'address': r.val('ADDR'), 'email': r.val('EMAIL'), 'phone': r.val('PHON')}
        if any(prep.values()) and not m.settings(self.con)['preparer'].get('name'):
            m.save_settings(self.con, {'preparer': prep})

    def import_repo(self, r):
        addr = r.first('ADDR')
        aid = insert(self.con, 'AddressTable', {
            'AddressType': 1, 'Name': r.val('NAME'), 'Street1': addr.val('ADR1') or (addr.text() if addr else '') if addr else '',
            'Street2': addr.val('ADR2') if addr else '', 'City': addr.val('CITY') if addr else '',
            'State': addr.val('STAE') if addr else '', 'Zip': addr.val('POST') if addr else '',
            'Country': addr.val('CTRY') if addr else '', 'Phone1': r.val('PHON'), 'Phone2': '', 'Fax': r.val('FAX'),
            'Email': r.val('EMAIL'), 'URL': r.val('WWW'), 'Latitude': 0, 'Longitude': 0, 'Note': self.notes_of(r)})
        self.repo[r.xref] = aid
        self.stats['repositories'] += 1

    def import_media(self, r):
        f = r.first('FILE')
        path = f.value if f else r.val('FILE')
        title = r.val('TITL') or (f.val('TITL') if f else '')
        form = (r.val('FORM') or (f.val('FORM') if f else '') or os.path.splitext(path)[1][1:]).lower()
        mtype = 1 if form in ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif', 'tiff', 'webp', 'heic', 'image') else \
            3 if form in ('mp3', 'wav', 'm4a', 'ogg', 'audio') else 4 if form in ('mp4', 'mov', 'avi', 'mkv', 'video') else 2
        if path and self.media_base and not os.path.isabs(path):
            path = os.path.join(self.media_base, path)
        url = path if path.startswith(('http://', 'https://')) else ''
        mid = m.add_media(self.con, '' if url else path, caption=title, media_type=mtype, url=url,
                          description=self.notes_of(r), date=gedcom_date_to_text(r.val('DATE')))
        self.stats['media'] += 1
        return mid

    def import_place_record(self, r):
        name = r.value
        if not name:
            return
        pid = m.get_or_create_place(self.con, name)
        self._place_extras(pid, r)

    def _place_extras(self, pid, plac):
        mp = plac.first('MAP')
        if mp and pid:
            lat, lon = _coord(mp.val('LATI')), _coord(mp.val('LONG'))
            if lat is not None and lon is not None:
                self.con.execute('UPDATE PlaceTable SET Latitude=?, Longitude=? WHERE PlaceID=? AND Latitude=0',
                                 (int(lat * 1e7), int(lon * 1e7), pid))
        abbr = plac.val('_ABBR') or plac.val('ABBR')
        if abbr:
            self.con.execute('UPDATE PlaceTable SET Abbrev=? WHERE PlaceID=?', (abbr, pid))
        note = self.notes_of(plac)
        if note:
            self.con.execute("UPDATE PlaceTable SET Note=? WHERE PlaceID=? AND COALESCE(Note,'')=''", (note, pid))

    def import_source(self, r):
        fields = {}
        tmpl = r.first('_TMPLT')
        tid = 0
        if tmpl:
            tname = tmpl.val('TNAME') or tmpl.val('TID')
            t = row(self.con, 'SELECT TemplateID FROM SourceTemplateTable WHERE Name=?', tname)
            tid = t['TemplateID'] if t else 0
            for f in tmpl.all('FIELD'):
                fields[f.val('NAME')] = f.val('VALUE')
        if not tid:
            title, auth, publ = r.val('TITL'), r.val('AUTH'), r.val('PUBL')
            foot = r.val('_FOOT') or (', '.join(x for x in (auth, f'<i>{title}</i>' if title else '') if x) + (f' ({publ})' if publ else '')).strip()
            fields = {'Footnote': foot, 'ShortFootnote': r.val('_SHORT') or r.val('ABBR') or title,
                      'Bibliography': r.val('_BIBL') or '. '.join(x for x in (auth, f'<i>{title}</i>' if title else '', publ) if x)}
        name = r.val('ABBR') or r.val('TITL') or r.val('_SUBQ') or 'Untitled source'
        sid = m.add_source(self.con, name, tid, fields, text=r.val('TEXT'), comments=self.notes_of(r),
                           ref=r.val('REFN'))
        self.sour[r.xref] = sid
        for rp in r.all('REPO'):
            aid = self.repo.get(rp.value)
            if aid:
                insert(self.con, 'AddressLinkTable', {'OwnerType': 3, 'AddressID': aid, 'OwnerID': sid,
                                                      'AddressNum': 0, 'Details': rp.val('CALN')})
        for o in r.all('OBJE'):
            self._link_obje(o, OWNER['source'], sid)
        self.stats['sources'] += 1

    def _link_obje(self, o, otype, oid):
        mid = self.obje.get(o.value) if o.value.startswith('@') else self.import_media(o)
        if mid:
            m.link_media(self.con, mid, otype, oid, primary=1 if o.val('_PRIM').upper() in ('Y', 'YES') else 0)

    def _citations(self, node, otype, oid):
        for s in node.all('SOUR'):
            sid = self.sour.get(s.value)
            if not sid:  # embedded source (no xref)
                if not s.value:
                    continue
                sid = m.add_source(self.con, s.value[:120], 0, {'Footnote': s.value, 'ShortFootnote': s.value[:60],
                                                                'Bibliography': s.value})
                self.sour[s.value] = sid
            page = s.val('PAGE')
            data = s.first('DATA')
            text = data.val('TEXT') if data else s.val('TEXT')
            fields = {'Page': page}
            src = row(self.con, 'SELECT TemplateID FROM SourceTable WHERE SourceID=?', sid)
            if src and src['TemplateID']:
                cit_fields = [f['name'] for f in m.template_fields(self.con, src['TemplateID']) if f['citation']]
                tm = s.first('_TMPLT')
                fields = {f.val('NAME'): f.val('VALUE') for f in tm.all('FIELD')} if tm else \
                    ({cit_fields[0]: page} if cit_fields else {'Page': page})
            q = QUAY_IN.get(s.val('QUAY'), '~~~')
            cid = m.add_citation(self.con, sid, otype, oid, fields, quality=q, text=text, comments=self.notes_of(s))
            for o in s.all('OBJE'):
                self._link_obje(o, OWNER['citation'], cid)
            self.stats['citations'] += 1

    def import_person_shell(self, r):
        sex = {'M': 0, 'F': 1}.get(r.val('SEX').upper()[:1], 2)
        uid = r.val('_UID') or unique_id()
        pid = insert(self.con, 'PersonTable', {'UniqueID': uid.replace('-', '')[:36], 'Sex': sex, 'ParentID': 0,
                                               'SpouseID': 0, 'Color': 0, 'Relate1': 0, 'Relate2': 0, 'Flags': 0,
                                               'Living': 0, 'IsPrivate': 1 if r.val('RESN').lower() in ('privacy', 'confidential') else 0,
                                               'Proof': 0, 'Bookmark': 0, 'Note': ''})
        self.stats['people'] += 1
        return pid

    def import_person_details(self, r, pid):
        names = r.all('NAME') or [Node(1, None, 'NAME', '')]
        for i, n in enumerate(names):
            given, surname, suffix = split_gedcom_name(n.value)
            ntype = NAME_TYPE_IN.get(n.val('TYPE').lower(), 0 if i == 0 else 1)
            nid = m.save_name(self.con, {
                'OwnerID': pid, 'Given': n.val('GIVN') or given, 'Surname': n.val('SURN') or surname,
                'Prefix': n.val('NPFX'), 'Suffix': n.val('NSFX') or suffix, 'Nickname': n.val('NICK'),
                'NameType': ntype, 'IsPrimary': 1 if i == 0 else 0, 'IsPrivate': 0, 'Proof': 0,
                'Note': self.notes_of(n), 'Date': gedcom_date_to_text(n.val('DATE'))})
            self._citations(n, OWNER['name'], nid)
        note = self.notes_of(r)
        if note:
            self.con.execute('UPDATE PersonTable SET Note=? WHERE PersonID=?', (note, pid))
        for c in r.children:
            if c.tag in NOT_FACTS_INDI or c.tag in ('CONT', 'CONC'):
                continue
            if c.tag in EVENT_LIKE or c.tag.startswith('_'):
                self.import_fact(c, 0, pid)
        self._citations(r, OWNER['person'], pid)
        for o in r.all('OBJE'):
            self._link_obje(o, OWNER['person'], pid)
        for a in r.all('ASSO'):
            other = self.indi.get(a.value)
            if other:
                rel = a.val('RELA') or a.val('ROLE') or 'Friend'
                ft = row(self.con, 'SELECT FANTypeID FROM FANTypeTable WHERE Name=? OR Role1=? OR Role2=?', rel, rel, rel)
                ftid = ft['FANTypeID'] if ft else insert(self.con, 'FANTypeTable', {'Name': rel, 'Role1': rel, 'Role2': rel,
                                                                                   'Sentence1': '', 'Sentence2': ''})
                insert(self.con, 'FANTable', {'ID1': pid, 'ID2': other, 'FanTypeID': ftid, 'PlaceID': 0, 'SiteID': 0,
                                              'Date': '.', 'SortDate': rmdate.EMPTY_SORT, 'Description': '',
                                              'Note': self.notes_of(a)})
                self.stats['associations'] += 1
        for w in r.all('_WEBTAG') + r.all('WWW'):
            url = w.val('URL') or w.value
            insert(self.con, 'URLTable', {'OwnerType': 0, 'OwnerID': pid, 'LinkType': 0,
                                          'Name': w.val('NAME') or url, 'URL': url, 'Note': ''})
        for t in r.all('_TODO'):
            tid = insert(self.con, 'TaskTable', {'TaskType': 0, 'RefNumber': '', 'Name': t.value or t.val('DESC') or 'To-do',
                                                 'Status': 0, 'Priority': 0, 'Date1': '.', 'Date2': '.', 'Date3': '.',
                                                 'SortDate1': rmdate.EMPTY_SORT, 'SortDate2': rmdate.EMPTY_SORT,
                                                 'SortDate3': rmdate.EMPTY_SORT, 'Filename': '', 'Details': self.notes_of(t),
                                                 'Results': '', 'Exclude': 0})
            insert(self.con, 'TaskLinkTable', {'TaskID': tid, 'OwnerType': 0, 'OwnerID': pid})
        for c in r.all('ADDR'):
            aid = insert(self.con, 'AddressTable', {'AddressType': 0, 'Name': m.person_name(self.con, pid),
                                                    'Street1': c.val('ADR1') or c.value, 'Street2': c.val('ADR2'),
                                                    'City': c.val('CITY'), 'State': c.val('STAE'), 'Zip': c.val('POST'),
                                                    'Country': c.val('CTRY'), 'Phone1': r.val('PHON'), 'Phone2': '',
                                                    'Fax': '', 'Email': r.val('EMAIL'), 'URL': '', 'Latitude': 0,
                                                    'Longitude': 0, 'Note': ''})
            insert(self.con, 'AddressLinkTable', {'OwnerType': 0, 'AddressID': aid, 'OwnerID': pid, 'AddressNum': 0, 'Details': ''})

    def fact_type_for(self, node, owner):
        tag = node.tag
        typ = node.val('TYPE')
        if tag in ('EVEN', 'FACT') and typ:
            ft = self.ftypes.get(('NAME:' + typ.lower(), owner))
            if ft:
                return ft
            return self.create_fact_type(typ, owner, 'EVEN')
        ft = self.ftypes.get((tag, owner)) or self.ftypes.get((tag, 1 - owner))
        if ft:
            return ft
        if tag in ('EVEN', 'FACT'):
            return 999
        return self.create_fact_type(tag.strip('_').title(), owner, tag)

    def create_fact_type(self, name, owner, tag):
        fid = max(1000, self.con.execute('SELECT MAX(FactTypeID) FROM FactTypeTable').fetchone()[0] + 1)
        sent = ('[couple]' if owner else '[person]') + ' ' + name.lower() + '< [Desc]>< [Date]>< [PlaceDetails]>< [Place]>.'
        insert(self.con, 'FactTypeTable', {'FactTypeID': fid, 'OwnerType': owner, 'Name': name, 'Abbrev': name[:15],
                                           'GedcomTag': tag, 'UseValue': 1, 'UseDate': 1, 'UsePlace': 1,
                                           'Sentence': sent, 'Flags': 0})
        self.ftypes[('NAME:' + name.lower(), owner)] = fid
        if tag not in ('EVEN', 'FACT'):
            self.ftypes[(tag, owner)] = fid
        self.warnings.append(f'Created custom fact type "{name}" for tag {tag}')
        return fid

    def import_fact(self, c, owner, oid):
        ft = self.fact_type_for(c, owner)
        plac = c.first('PLAC')
        place_id = 0
        if plac and plac.value:
            place_id = m.get_or_create_place(self.con, plac.value)
            self._place_extras(place_id, plac)
        addr = c.first('ADDR')
        details = (addr.text().replace('\n', ', ') if addr else '') or c.val('_PLACEDETAIL') or c.val('_DETAIL')
        desc = c.value if c.value and c.value.upper() not in ('Y', 'YES') else ''
        if not desc and c.tag not in EVENT_LIKE:
            desc = c.val('TYPE')
        cause = c.val('CAUS')
        if cause and not desc:
            desc = 'of ' + cause  # reads naturally in '[person] died< [Desc]>'
        eid = m.add_fact(self.con, owner, oid, ft, date=gedcom_date_to_text(c.val('DATE')), place=place_id,
                         place_details=details, desc=desc, note=self.notes_of(c),
                         private=1 if c.val('RESN').lower() in ('privacy', 'confidential') else 0,
                         primary=1 if c.val('_PRIM').upper() in ('Y', '') else 0)
        sent = c.val('_SENT') or c.val('_SENTENCE')
        if sent:
            self.con.execute('UPDATE EventTable SET Sentence=? WHERE EventID=?', (sent, eid))
        self._citations(c, OWNER['event'], eid)
        for o in c.all('OBJE'):
            self._link_obje(o, OWNER['event'], eid)
        for w in c.all('_SHAR') + c.all('ASSO'):
            other = self.indi.get(w.value)
            if other:
                role = w.val('ROLE') or w.val('RELA')
                rr = row(self.con, 'SELECT RoleID FROM RoleTable WHERE RoleName=? AND EventType IN (?,0)', role, ft) if role else None
                m.add_witness(self.con, eid, other, rr['RoleID'] if rr else 0)
        self.stats['events'] += 1
        return eid

    def import_family(self, r):
        father = self.indi.get(r.val('HUSB'), 0)
        mother = self.indi.get(r.val('WIFE'), 0)
        fid = insert(self.con, 'FamilyTable', {'FatherID': father, 'MotherID': mother, 'ChildID': 0, 'HusbOrder': 0,
                                               'WifeOrder': 0, 'IsPrivate': 1 if r.val('RESN') else 0, 'Proof': 0,
                                               'SpouseLabel': 0, 'FatherLabel': 0, 'MotherLabel': 0,
                                               'Note': self.notes_of(r)})
        self.fam[r.xref] = fid
        for order, c in enumerate(r.all('CHIL'), 1):
            cid = self.indi.get(c.value)
            if not cid:
                continue
            rf = PEDI_IN.get(c.val('_FREL').lower(), 0)
            rm_ = PEDI_IN.get(c.val('_MREL').lower(), 0)
            insert(self.con, 'ChildTable', {'ChildID': cid, 'FamilyID': fid, 'RelFather': rf, 'RelMother': rm_,
                                            'ChildOrder': order, 'IsPrivate': 0, 'ProofFather': 0, 'ProofMother': 0,
                                            'Note': ''})
        for c in r.children:
            if c.tag in EVENT_LIKE and c.tag not in ('NCHI',):
                self.import_fact(c, 1, fid)
        self._citations(r, OWNER['family'], fid)
        for o in r.all('OBJE'):
            self._link_obje(o, OWNER['family'], fid)
        self.stats['families'] += 1

    def apply_pedigree(self):
        """FAMC.PEDI on the INDI side overrides ChildTable relationship."""
        for r in self.roots:
            if r.tag != 'INDI':
                continue
            pid = self.indi[r.xref]
            for fc in r.all('FAMC'):
                fid = self.fam.get(fc.value)
                pedi = fc.val('PEDI').lower()
                if fid and pedi in PEDI_IN and PEDI_IN[pedi]:
                    self.con.execute('UPDATE ChildTable SET RelFather=?, RelMother=? WHERE FamilyID=? AND ChildID=?',
                                     (PEDI_IN[pedi], PEDI_IN[pedi], fid, pid))
                    if not row(self.con, 'SELECT 1 AS x FROM ChildTable WHERE FamilyID=? AND ChildID=?', fid, pid):
                        m.add_child(self.con, fid, pid, PEDI_IN[pedi], PEDI_IN[pedi])


def _coord(s):
    s = (s or '').strip().upper()
    if not s:
        return None
    sign = -1 if s[0] in 'SW' or s.startswith('-') else 1
    try:
        return sign * float(s.lstrip('NSEW+-'))
    except ValueError:
        return None


def split_gedcom_name(v):
    v = (v or '').strip()
    mm = re.match(r'(.*?)\s*/(.*?)/\s*(.*)', v)
    if mm:
        return mm[1].strip(), mm[2].strip(), mm[3].strip()
    return v, '', ''


def import_file(con, path):
    data = open(path, 'rb').read()
    imp = Importer(con, decode_bytes(data), media_base=os.path.dirname(path))
    res = imp.run()
    with tx(con):
        imp.apply_pedigree()
    return res


def import_text(con, text):
    imp = Importer(con, text)
    res = imp.run()
    with tx(con):
        imp.apply_pedigree()
    return res


# ------------------------------------------------------------------ export
PEDI_OUT = {v: k for k, v in PEDI_IN.items()}
NAME_TYPE_OUT = {1: 'aka', 2: 'birth', 3: 'immigrant', 4: 'maiden', 5: 'married', 6: 'nickname', 7: 'other spelling'}


class Exporter:
    def __init__(self, con, people=None, options=None):
        self.con = con
        o = {'privatizeLiving': False, 'excludePrivate': True, 'includeNotes': True, 'includeSources': True,
             'includeMedia': True, 'includeAddresses': True, 'includeAssociations': True, 'includeWebTags': True,
             'extraTags': True, 'livingName': 'Living'}
        o.update(options or {})
        self.o = o
        all_ids = [r['PersonID'] for r in rows(con, 'SELECT PersonID FROM PersonTable ORDER BY PersonID')]
        self.people = set(people) if people is not None else set(all_ids)
        self.lines = []
        self.used_sources, self.used_repos, self.used_media = set(), set(), set()
        self.ftypes = {f['FactTypeID']: f for f in m.fact_types(con)}

    def w(self, level, tag, value='', xref=''):
        """Emit a line, splitting long values with CONC and newlines with CONT."""
        value = '' if value is None else str(value)
        parts = value.replace('\r\n', '\n').split('\n')
        head = f'{level} {xref + " " if xref else ""}{tag}'
        first = True
        for i, p in enumerate(parts):
            chunks = [p[j:j + 200] for j in range(0, len(p), 200)] or ['']
            for k, ch in enumerate(chunks):
                if first:
                    self.lines.append(f'{head} {ch}'.rstrip() if ch else head)
                    first = False
                else:
                    tag2 = 'CONT' if k == 0 else 'CONC'
                    self.lines.append(f'{level + 1} {tag2} {ch}'.rstrip())

    def is_living_private(self, pid):
        if not self.o['privatizeLiving']:
            return False
        p = row(self.con, 'SELECT Living FROM PersonTable WHERE PersonID=?', pid)
        return bool(p and p['Living'])

    def run(self):
        s = m.settings(self.con)
        prep = s.get('preparer') or {}
        self.w(0, 'HEAD')
        self.w(1, 'SOUR', 'DZINDE')
        self.w(2, 'NAME', 'Dzinde')
        self.w(2, 'VERS', '1.0')
        self.w(1, 'DATE', date.today().strftime('%d %b %Y').upper())
        self.w(1, 'GEDC')
        self.w(2, 'VERS', '5.5.1')
        self.w(2, 'FORM', 'LINEAGE-LINKED')
        self.w(1, 'CHAR', 'UTF-8')
        self.w(1, 'SUBM', '@SUBM1@')
        self.w(0, 'SUBM', xref='@SUBM1@')
        self.w(1, 'NAME', prep.get('name') or 'Unknown')
        if prep.get('address'):
            self.w(1, 'ADDR', prep['address'])
        if prep.get('email'):
            self.w(1, 'EMAIL', prep['email'])
        fams = set()
        for pid in sorted(self.people):
            self.person(pid, fams)
        for fid in sorted(fams):
            self.family(fid)
        if self.o['includeSources']:
            for sid in sorted(self.used_sources):
                self.source(sid)
            for aid in sorted(self.used_repos):
                self.repo(aid)
        if self.o['includeMedia']:
            for mid in sorted(self.used_media):
                self.media(mid)
        self.w(0, 'TRLR')
        return '\n'.join(self.lines) + '\n'

    def person(self, pid, fams):
        p = row(self.con, 'SELECT * FROM PersonTable WHERE PersonID=?', pid)
        if not p or (self.o['excludePrivate'] and p['IsPrivate']):
            return
        priv = self.is_living_private(pid)
        self.w(0, 'INDI', xref=f'@I{pid}@')
        names = rows(self.con, 'SELECT * FROM NameTable WHERE OwnerID=? ORDER BY IsPrimary DESC, NameID', pid)
        for n in names:
            if self.o['excludePrivate'] and n['IsPrivate']:
                continue
            given = self.o['livingName'] if priv else (n['Given'] or '')
            sur = n['Surname'] or ''
            self.w(1, 'NAME', f'{given} /{sur}/' + (f' {n["Suffix"]}' if n['Suffix'] and not priv else ''))
            if given:
                self.w(2, 'GIVN', given)
            if sur:
                self.w(2, 'SURN', sur)
            if not priv:
                if n['Prefix']:
                    self.w(2, 'NPFX', n['Prefix'])
                if n['Suffix']:
                    self.w(2, 'NSFX', n['Suffix'])
                if n['Nickname']:
                    self.w(2, 'NICK', n['Nickname'])
                if n['NameType'] in NAME_TYPE_OUT:
                    self.w(2, 'TYPE', NAME_TYPE_OUT[n['NameType']])
                self.citations(2, OWNER['name'], n['NameID'])
            if priv:
                break
        self.w(1, 'SEX', {0: 'M', 1: 'F'}.get(p['Sex'], 'U'))
        if not priv:
            for e in rows(self.con, 'SELECT * FROM EventTable WHERE OwnerType=0 AND OwnerID=? ORDER BY SortDate', pid):
                self.event(1, e)
            if self.o['includeNotes'] and p['Note']:
                self.w(1, 'NOTE', m.strip_tags(p['Note']))
            self.citations(1, OWNER['person'], pid)
            self.media_links(1, OWNER['person'], pid)
            if self.o['includeAssociations']:
                for a in rows(self.con, 'SELECT f.*, t.Role2 FROM FANTable f LEFT JOIN FANTypeTable t ON t.FANTypeID=f.FanTypeID WHERE ID1=?', pid):
                    if a['ID2'] in self.people:
                        self.w(1, 'ASSO', f'@I{a["ID2"]}@')
                        self.w(2, 'RELA', a['Role2'] or 'Associate')
            if self.o['includeWebTags']:
                for u in rows(self.con, 'SELECT * FROM URLTable WHERE OwnerType=0 AND OwnerID=?', pid):
                    self.w(1, '_WEBTAG')
                    self.w(2, 'NAME', u['Name'])
                    self.w(2, 'URL', u['URL'])
            if self.o['includeAddresses']:
                for a in rows(self.con, '''SELECT a.* FROM AddressLinkTable l JOIN AddressTable a ON a.AddressID=l.AddressID
                                           WHERE l.OwnerType=0 AND l.OwnerID=?''', pid):
                    self.w(1, 'ADDR', a['Street1'] or '')
                    for tag, col in (('ADR2', 'Street2'), ('CITY', 'City'), ('STAE', 'State'), ('POST', 'Zip'), ('CTRY', 'Country')):
                        if a[col]:
                            self.w(2, tag, a[col])
            if self.o['extraTags']:
                self.w(1, '_UID', p['UniqueID'])
        for c in rows(self.con, 'SELECT * FROM ChildTable WHERE ChildID=? ORDER BY RecID', pid):
            f = row(self.con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', c['FamilyID'])
            if f and (f['FatherID'] in self.people or f['MotherID'] in self.people):
                self.w(1, 'FAMC', f'@F{c["FamilyID"]}@')
                if c['RelFather'] and c['RelFather'] == c['RelMother']:
                    self.w(2, 'PEDI', PEDI_OUT.get(c['RelFather'], 'birth'))
                fams.add(c['FamilyID'])
        for f in m.spouse_families(self.con, pid):
            self.w(1, 'FAMS', f'@F{f["FamilyID"]}@')
            fams.add(f['FamilyID'])

    def event(self, level, e):
        if self.o['excludePrivate'] and e['IsPrivate']:
            return
        ft = self.ftypes.get(e['EventType'], {})
        tag = (ft.get('GedcomTag') or 'EVEN').upper()
        custom = tag in ('EVEN', 'FACT') or tag.startswith('_') or not re.fullmatch(r'[A-Z0-9]{3,15}', tag)
        if custom:
            tag = 'EVEN'
        val = e['Details'] or ''
        cause = ''
        if tag in ('DEAT', 'BURI') and val.lower().startswith('of '):
            cause, val = val[3:], ''
        if not val and tag in ('BIRT', 'DEAT', 'MARR', 'CHR', 'BURI') and not e['Date'] and not e['PlaceID']:
            val = 'Y'  # GEDCOM: event known to have happened, no details
        self.w(level, tag, val)
        if custom:
            self.w(level + 1, 'TYPE', ft.get('Name', 'Event'))
        if cause:
            self.w(level + 1, 'CAUS', cause)
        d = to_gedcom_date(e['Date'])
        if d:
            self.w(level + 1, 'DATE', d)
        if e['PlaceID']:
            pl = row(self.con, 'SELECT * FROM PlaceTable WHERE PlaceID=?', e['PlaceID'])
            if pl:
                self.w(level + 1, 'PLAC', pl['Name'])
                if pl['Latitude'] or pl['Longitude']:
                    self.w(level + 2, 'MAP')
                    lat, lon = pl['Latitude'] / 1e7, pl['Longitude'] / 1e7
                    self.w(level + 3, 'LATI', ('N' if lat >= 0 else 'S') + f'{abs(lat):.6f}')
                    self.w(level + 3, 'LONG', ('E' if lon >= 0 else 'W') + f'{abs(lon):.6f}')
        if e['SiteID']:
            self.w(level + 1, 'ADDR', m.place_name(self.con, e['SiteID']))
        if self.o['includeNotes'] and e['Note']:
            self.w(level + 1, 'NOTE', m.strip_tags(e['Note']))
        if self.o['extraTags'] and e['Sentence']:
            self.w(level + 1, '_SENT', e['Sentence'])
        if self.o['extraTags'] and not e['IsPrimary']:
            self.w(level + 1, '_PRIM', 'N')
        if self.o['extraTags']:
            for wt in rows(self.con, 'SELECT * FROM WitnessTable WHERE EventID=? AND PersonID>0', e['EventID']):
                if wt['PersonID'] in self.people:
                    self.w(level + 1, '_SHAR', f'@I{wt["PersonID"]}@')
                    self.w(level + 2, 'ROLE', m.role_name(self.con, wt['Role']))
        self.citations(level + 1, OWNER['event'], e['EventID'])
        self.media_links(level + 1, OWNER['event'], e['EventID'])

    def citations(self, level, otype, oid):
        if not self.o['includeSources']:
            return
        for l in rows(self.con, '''SELECT l.*, c.* FROM CitationLinkTable l JOIN CitationTable c ON c.CitationID=l.CitationID
                                   WHERE l.OwnerType=? AND l.OwnerID=? ORDER BY l.SortOrder''', otype, oid):
            if self.o['excludePrivate'] and l['IsPrivate']:
                continue
            self.used_sources.add(l['SourceID'])
            self.w(level, 'SOUR', f'@S{l["SourceID"]}@')
            fields = m.xml_to_fields(l['Fields'])
            page = fields.get('Page') or '; '.join(f'{k}: {v}' for k, v in fields.items() if v)
            if page:
                self.w(level + 1, 'PAGE', page)
            q = (l['Quality'] or '~~~')
            quay = {'O': 3, 'D': 2, 'A': 1}.get(q[0]) if q else None
            if quay is not None and q[0] != '~':
                self.w(level + 1, 'QUAY', str(quay if q[1:2] != 'S' else min(quay, 2)))
            if l['ActualText']:
                self.w(level + 1, 'DATA')
                self.w(level + 2, 'TEXT', m.strip_tags(l['ActualText']))
            if self.o['includeNotes'] and l['Comments']:
                self.w(level + 1, 'NOTE', m.strip_tags(l['Comments']))
            if self.o['extraTags'] and fields:
                src = row(self.con, 'SELECT TemplateID FROM SourceTable WHERE SourceID=?', l['SourceID'])
                if src and src['TemplateID']:
                    self.w(level + 1, '_TMPLT')
                    for k, v in fields.items():
                        self.w(level + 2, 'FIELD')
                        self.w(level + 3, 'NAME', k)
                        self.w(level + 3, 'VALUE', v)

    def media_links(self, level, otype, oid):
        if not self.o['includeMedia']:
            return
        for l in rows(self.con, 'SELECT * FROM MediaLinkTable WHERE OwnerType=? AND OwnerID=? ORDER BY SortOrder', otype, oid):
            self.used_media.add(l['MediaID'])
            self.w(level, 'OBJE', f'@M{l["MediaID"]}@')
            if l['IsPrimary']:
                self.w(level + 1, '_PRIM', 'Y')

    def family(self, fid):
        f = row(self.con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid)
        if not f or (self.o['excludePrivate'] and f['IsPrivate']):
            return
        self.w(0, 'FAM', xref=f'@F{fid}@')
        if f['FatherID'] in self.people:
            self.w(1, 'HUSB', f'@I{f["FatherID"]}@')
        if f['MotherID'] in self.people:
            self.w(1, 'WIFE', f'@I{f["MotherID"]}@')
        private_couple = self.is_living_private(f['FatherID']) or self.is_living_private(f['MotherID'])
        if not private_couple:
            for e in rows(self.con, 'SELECT * FROM EventTable WHERE OwnerType=1 AND OwnerID=? ORDER BY SortDate', fid):
                self.event(1, e)
        for c in rows(self.con, 'SELECT * FROM ChildTable WHERE FamilyID=? ORDER BY ChildOrder', fid):
            if c['ChildID'] in self.people:
                self.w(1, 'CHIL', f'@I{c["ChildID"]}@')
                if self.o['extraTags'] and (c['RelFather'] or c['RelMother']):
                    self.w(2, '_FREL', PEDI_OUT.get(c['RelFather'], 'birth').title())
                    self.w(2, '_MREL', PEDI_OUT.get(c['RelMother'], 'birth').title())
        if self.o['includeNotes'] and f['Note'] and not private_couple:
            self.w(1, 'NOTE', m.strip_tags(f['Note']))
        self.citations(1, OWNER['family'], fid)
        self.media_links(1, OWNER['family'], fid)

    def source(self, sid):
        s = row(self.con, 'SELECT * FROM SourceTable WHERE SourceID=?', sid)
        if not s:
            return
        self.w(0, 'SOUR', xref=f'@S{sid}@')
        fields = m.xml_to_fields(s['Fields'])
        self.w(1, 'TITL', m.strip_tags(html.unescape(m.render_source_text(self.con, s, None, 'Bibliography'))) or s['Name'])
        self.w(1, 'ABBR', s['Name'])
        if fields.get('Author'):
            self.w(1, 'AUTH', templates_name(fields['Author']))
        if s['ActualText']:
            self.w(1, 'TEXT', m.strip_tags(s['ActualText']))
        if self.o['includeNotes'] and s['Comments']:
            self.w(1, 'NOTE', m.strip_tags(s['Comments']))
        if s['RefNumber']:
            self.w(1, 'REFN', s['RefNumber'])
        if self.o['extraTags']:
            self.w(1, '_FOOT', html.unescape(m.render_source_text(self.con, s, None, 'Footnote')))
            self.w(1, '_SHORT', html.unescape(m.render_source_text(self.con, s, None, 'ShortFootnote')))
            self.w(1, '_BIBL', html.unescape(m.render_source_text(self.con, s, None, 'Bibliography')))
            if s['TemplateID']:
                t = row(self.con, 'SELECT Name FROM SourceTemplateTable WHERE TemplateID=?', s['TemplateID'])
                self.w(1, '_TMPLT')
                self.w(2, 'TNAME', t['Name'] if t else '')
                for k, v in fields.items():
                    self.w(2, 'FIELD')
                    self.w(3, 'NAME', k)
                    self.w(3, 'VALUE', v)
        for l in rows(self.con, 'SELECT * FROM AddressLinkTable WHERE OwnerType=3 AND OwnerID=?', sid):
            self.used_repos.add(l['AddressID'])
            self.w(1, 'REPO', f'@R{l["AddressID"]}@')
            if l['Details']:
                self.w(2, 'CALN', l['Details'])
        self.media_links(1, OWNER['source'], sid)

    def repo(self, aid):
        a = row(self.con, 'SELECT * FROM AddressTable WHERE AddressID=?', aid)
        if not a:
            return
        self.w(0, 'REPO', xref=f'@R{aid}@')
        self.w(1, 'NAME', a['Name'])
        if a['Street1'] or a['City']:
            self.w(1, 'ADDR', a['Street1'] or '')
            for tag, col in (('ADR2', 'Street2'), ('CITY', 'City'), ('STAE', 'State'), ('POST', 'Zip'), ('CTRY', 'Country')):
                if a[col]:
                    self.w(2, tag, a[col])
        for tag, col in (('PHON', 'Phone1'), ('EMAIL', 'Email'), ('WWW', 'URL')):
            if a[col]:
                self.w(1, tag, a[col])

    def media(self, mid):
        mm = row(self.con, 'SELECT * FROM MultimediaTable WHERE MediaID=?', mid)
        if not mm:
            return
        self.w(0, 'OBJE', xref=f'@M{mid}@')
        path = mm['URL'] or m.media_path(mm)
        self.w(1, 'FILE', path)
        ext = os.path.splitext(path)[1][1:].lower()
        if ext:
            self.w(2, 'FORM', ext)
        if mm['Caption']:
            self.w(2, 'TITL', mm['Caption'])
        if mm['Description'] and self.o['includeNotes']:
            self.w(1, 'NOTE', m.strip_tags(mm['Description']))


def templates_name(v):
    return m.name_value(v) if '/' in (v or '') else v


def export(con, people=None, options=None):
    return Exporter(con, people, options).run()


if __name__ == '__main__':
    assert to_gedcom_date(rmdate.encode('abt 12 Jan 1850')) == 'ABT 12 JAN 1850'
    assert to_gedcom_date(rmdate.encode('bet 1850 and 1860')) == 'BET 1850 AND 1860'
    assert to_gedcom_date(rmdate.encode('Christmas 1850')) == '(Christmas 1850)'
    assert rmdate.encode(gedcom_date_to_text('CAL 1850')) == rmdate.encode('calc 1850')
    assert decode_ansel(b'Jos\xe2e') == 'José'
    print('gedcom ok')
