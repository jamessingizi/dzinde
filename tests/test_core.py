"""Core model checks. Run: python3 tests/test_core.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dzinde import db, model as m  # noqa: E402


def fresh():
    return db.create(os.path.join(tempfile.mkdtemp(), 'test.rmtree'))


def test_people_families_sentences():
    con = fresh()
    john = m.add_person(con, 'John', 'Smith', 0, birth_date='12 Jan 1850', birth_place='Columbus, Franklin, Ohio, USA')
    mary = m.add_person(con, 'Mary', 'Jones', 1, birth_date='abt 1852')
    fid = m.add_spouse(con, john, mary)
    assert m.add_spouse(con, mary, john) == fid  # reuses family
    kid = m.add_person(con, 'Tom', 'Smith', 0, birth_date='1875')
    kid2 = m.add_person(con, 'Ann', 'Smith', 1, birth_date='1872')
    m.add_child(con, fid, kid)
    m.add_child(con, fid, kid2)
    assert m.children_of(con, fid) == [kid2, kid]  # sorted by birth
    assert m.primary_parents(con, kid)[:2] == (john, mary)
    assert m.siblings_of(con, kid) == [kid2]
    m.add_fact(con, 'family', fid, 300, date='5 May 1870', place='Columbus, Franklin, Ohio, USA')
    birth = m.first_event(con, john, (1,))
    assert m.fact_sentence(con, birth['EventID']) == 'John Smith was born on 12 Jan 1850 in Columbus, Franklin, Ohio, USA.'
    marr = m.first_event(con, fid, (300,), owner=1)
    assert m.fact_sentence(con, marr['EventID']) == 'John Smith and Mary Jones were married on 5 May 1870 in Columbus, Franklin, Ohio, USA.'
    occ = m.add_fact(con, 'person', john, 26, date='1880', desc='farmer')
    assert m.fact_sentence(con, occ) == 'John Smith worked as a farmer in 1880.'
    death = m.add_fact(con, 'person', john, 2, date='1 Feb 1920')
    assert 'at the age of 70' in m.fact_sentence(con, death)
    s = m.person_summary(con, john)
    assert s['name'] == 'John Smith' and s['birthYear'] == 1850 and s['deathYear'] == 1920
    assert m.primary_name(con, john)['BirthYear'] == 1850
    m.unlink_child(con, fid, kid)
    assert m.children_of(con, fid) == [kid2]
    m.delete_person(con, mary)
    assert m.row(con, 'SELECT MotherID FROM FamilyTable WHERE FamilyID=?', fid)['MotherID'] == 0
    w = m.add_witness(con, occ, person_id=kid2)
    assert any(f.get('shared') for f in m.facts_for(con, 'person', kid2)) and w


def test_sources_groups():
    con = fresh()
    p = m.add_person(con, 'Ann', 'Lee', 1)
    sid = m.add_source(con, 'Lee Family Bible', 10008, {'Family': 'Lee', 'BibleTitle': 'Holy Bible',
                                                        'PubPlace': 'New York', 'Publisher': 'ABS', 'PubDate': '1850'})
    cid = m.add_citation(con, sid, 'person', p, {'Page': 'Births page'})
    fn = m.render_citation(con, cid)
    assert fn.startswith('Lee Family Bible, <i>Holy Bible</i> (New York: ABS, 1850), "Births page"'), fn
    assert m.render_citation(con, cid, 'Bibliography') == 'Lee Family Bible. <i>Holy Bible</i>. New York: ABS, 1850.'
    free = m.add_source(con, 'Notes', 0, {'Footnote': 'Smith notes', 'Bibliography': 'Smith notes.'})
    c2 = m.add_citation(con, free, 'person', p, {'Page': 'p. 4'})
    assert m.render_citation(con, c2) == 'Smith notes, p. 4.'
    g = m.create_group(con, 'Test')
    m.set_group_members(con, g, [1, 2, 3, 7, 9, 10])
    assert m.rows(con, 'SELECT StartID, EndID FROM GroupTable WHERE GroupID=? ORDER BY StartID', g) == \
        [{'StartID': 1, 'EndID': 3}, {'StartID': 7, 'EndID': 7}, {'StartID': 9, 'EndID': 10}]
    assert m.person_groups(con, p) and m.person_groups(con, p)[0]['Name'] == 'Test'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
