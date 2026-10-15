"""GEDCOM round-trip checks. Run: python3 tests/test_gedcom.py"""
import html
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dzinde import db, gedcom, model as m, rmdate  # noqa: E402

SAMPLE = os.path.join(ROOT, 'samples', 'hartwell.ged')


def load():
    con = db.create(os.path.join(tempfile.mkdtemp(), 'g.rmtree'))
    res = gedcom.import_file(con, SAMPLE)
    return con, res


def count(con, sql):
    return con.execute(sql).fetchone()[0]


def test_import():
    con, res = load()
    st = res['stats']
    assert st['people'] == 16 and st['families'] == 5 and st['sources'] == 3 and st['repositories'] == 1, st
    thomas = m.row(con, "SELECT OwnerID FROM NameTable WHERE Given='Thomas'")['OwnerID']
    b = m.first_event(con, thomas, (1,))
    assert rmdate.format(b['Date']) == '14 Mar 1808'
    pl = m.row(con, 'SELECT * FROM PlaceTable WHERE PlaceID=?', b['PlaceID'])
    assert pl['Name'] == 'Leeds, Yorkshire, England' and pl['Latitude'] == 538008000 and pl['Longitude'] == -15491000
    assert 'Liverpool,\nwhich survives' in m.row(con, 'SELECT Note FROM PersonTable WHERE PersonID=?', thomas)['Note']
    death = m.first_event(con, thomas, (2,))
    assert death['Details'] == 'of Pneumonia'
    assert m.fact_sentence(con, death['EventID']).startswith('Thomas Hartwell died of Pneumonia on 2 Nov 1871')
    assert '2 CAUS Pneumonia' in gedcom.export(con)
    eliza = m.row(con, "SELECT OwnerID FROM NameTable WHERE Given='Eliza' AND IsPrimary=1")['OwnerID']
    assert m.row(con, 'SELECT NameType FROM NameTable WHERE OwnerID=? AND IsPrimary=0', eliza)['NameType'] == 5
    william = m.row(con, "SELECT OwnerID FROM NameTable WHERE Given='William Henry'")['OwnerID']
    mil = [f for f in m.facts_for(con, 'person', william) if f['typeName'] == 'Military']
    assert mil and mil[0]['description'] == '3rd Ohio Infantry' and mil[0]['date'] == 'from 1861 to 1864', mil
    cits = m.citations_for(con, 2, m.first_event(con, william, (18,))['EventID'])
    assert cits and cits[0]['Quality'] == 'OS~'
    ruth = m.row(con, "SELECT OwnerID FROM NameTable WHERE Given='Ruth'")['OwnerID']
    assert m.row(con, 'SELECT RelFather FROM ChildTable WHERE ChildID=?', ruth)['RelFather'] == 1
    assert count(con, 'SELECT COUNT(*) FROM FANTable') == 1
    assert count(con, "SELECT COUNT(*) FROM AddressLinkTable WHERE OwnerType=3") == 1
    assert m.row(con, 'SELECT ParentID FROM PersonTable WHERE PersonID=?', william)['ParentID'] > 0
    goteborg = m.row(con, "SELECT Name FROM PlaceTable WHERE Name LIKE 'G%borg%'")
    assert goteborg['Name'].startswith('Göteborg')


def test_roundtrip():
    con, _ = load()
    text = gedcom.export(con)
    assert '1 CHAR UTF-8' in text and text.rstrip().endswith('0 TRLR')
    con2 = db.create(os.path.join(tempfile.mkdtemp(), 'g2.rmtree'))
    gedcom.import_text(con2, text)
    for t in ('PersonTable', 'FamilyTable', 'ChildTable', 'EventTable', 'SourceTable', 'CitationLinkTable',
              'NameTable', 'FANTable'):
        a, b = count(con, f'SELECT COUNT(*) FROM {t}'), count(con2, f'SELECT COUNT(*) FROM {t}')
        assert a == b, (t, a, b)
    assert count(con2, 'SELECT COUNT(*) FROM FactTypeTable') == count(con, 'SELECT COUNT(*) FROM FactTypeTable')


def test_privatize():
    con, _ = load()
    grace = m.row(con, "SELECT OwnerID FROM NameTable WHERE Given='Grace'")['OwnerID']
    con.execute('UPDATE PersonTable SET Living=1 WHERE PersonID=?', (grace,))
    text = gedcom.export(con, options={'privatizeLiving': True})
    block = text.split(f'0 @I{grace}@ INDI')[1].split('\n0 ')[0]
    assert 'Living /Hartwell/' in block and 'BIRT' not in block


def test_untrusted_source_text_is_escaped():
    con = db.create(os.path.join(tempfile.mkdtemp(), 'x.rmtree'))
    evil = '<img src=x onerror=alert(1)><i>Parish Register</i> & co<script>x()</script>'
    gedcom.import_text(con, f'0 HEAD\n1 CHAR UTF-8\n0 @S1@ SOUR\n1 TITL T\n1 _FOOT {evil}\n0 TRLR\n')
    src = m.row(con, 'SELECT * FROM SourceTable')
    out = m.render_source_text(con, src, None, 'Footnote')
    assert '<img' not in out and '<script' not in out and '<i>Parish Register</i>' in out and '&amp; co' in out, out
    assert html.unescape(out).rstrip('.') == evil  # what GEDCOM export writes: the original text, no entity build-up
    assert m.safe_url('javascript:alert(1)') == '#' and m.safe_url('HTTPS://x.org') == 'HTTPS://x.org'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
