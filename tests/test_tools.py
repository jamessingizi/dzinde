"""Tools checks against the sample family. Run: python3 tests/test_tools.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dzinde import db, gedcom, model as m, tools  # noqa: E402


def load():
    con = db.create(os.path.join(tempfile.mkdtemp(), 't.rmtree'))
    gedcom.import_file(con, os.path.join(ROOT, 'samples', 'hartwell.ged'))
    return con


def pid(con, given):
    return m.row(con, 'SELECT OwnerID FROM NameTable WHERE Given=? AND IsPrimary=1', given)['OwnerID']


def test_relationships():
    con = load()
    thomas, william, charles, harold, grace, louisa, ruth = (pid(con, g) for g in (
        'Thomas', 'William Henry', 'Charles Edward', 'Harold', 'Grace', 'Louisa May', 'Ruth'))
    assert tools.relationships(con, grace, thomas)[0]['name'] == '3rd great-grandfather'
    assert tools.relationships(con, thomas, grace)[0]['name'] == '3rd great-granddaughter'
    assert tools.relationships(con, charles, louisa)[0]['name'] == 'sister'
    assert tools.relationships(con, harold, louisa)[0]['name'] == 'aunt'
    assert tools.relationships(con, william, pid(con, 'Sarah Ann'))[0]['name'] == 'wife'
    anc = tools.ancestors(con, grace)
    assert anc[1] == grace and anc[16] == william and anc[32] == thomas and anc[33] == pid(con, 'Eliza')
    kin = {k['person']['id']: k['relationship'] for k in tools.kinship_list(con, harold)}
    assert kin[thomas] == 'great-grandfather' and kin[ruth] == 'sister'
    tools.set_relationships(con, grace)
    assert tools.relationship_to_root(con, thomas, grace) == '3rd great-grandfather'


def test_trees_living_problems():
    con = load()
    trees = tools.count_trees(con)
    assert trees[0]['size'] == 15 and trees[1]['size'] == 1  # Jacob Werner is unconnected
    tools.set_living(con)
    living = {r['PersonID'] for r in m.rows(con, 'SELECT PersonID FROM PersonTable WHERE Living=1')}
    assert pid(con, 'Grace') in living and pid(con, 'Thomas') not in living
    louisa = pid(con, 'Louisa May')
    con.execute("UPDATE EventTable SET Date='D.+18200000..+00000000..' WHERE OwnerID=? AND EventType=1", (louisa,))
    probs = tools.problem_list(con)
    assert any(p['person']['id'] == louisa and p['rule'] == 'mother_young' for p in probs), probs
    tools.not_a_problem(con, louisa, list(tools.PROBLEM_RULES).index('mother_young'))
    assert not any(p['person']['id'] == louisa and p['rule'] == 'mother_young' for p in tools.problem_list(con))


def test_duplicates_merge():
    con = load()
    dup = m.add_person(con, 'Tom', 'Hartwell', 0, birth_date='1808', birth_place='Leeds, Yorkshire, England')
    thomas = pid(con, 'Thomas')
    found = tools.find_duplicates(con)
    assert any({d['a']['id'], d['b']['id']} == {dup, thomas} for d in found), found[:3]
    tools.merge_people(con, thomas, dup)
    assert not m.row(con, 'SELECT 1 AS x FROM PersonTable WHERE PersonID=?', dup)
    assert m.row(con, "SELECT COUNT(*) AS n FROM NameTable WHERE OwnerID=?", thomas)['n'] == 2
    assert len(m.spouse_families(con, thomas)) == 1


def test_dataclean_search():
    con = load()
    p = m.add_person(con, 'Dr. John "Jack" Q', 'MCDONALD JR', 0)
    fix = next(f for f in tools.name_issues(con) if f['person'] == p)
    assert fix['fix']['Prefix'] == 'Dr.' and fix['fix']['Nickname'] == 'Jack' and fix['fix']['Surname'] == 'McDonald'
    assert fix['fix']['Suffix'] == 'JR'
    m.get_or_create_place(con, 'Leeds ,  Yorkshire,England')
    issues = tools.place_issues(con)
    assert any(i['suggestion'] == 'Leeds, Yorkshire, England' for i in issues)
    ch = tools.search_replace(con, 'Columbus', 'Columbus City', fields=['Place'], preview=False)
    assert ch and m.row(con, "SELECT COUNT(*) AS n FROM PlaceTable WHERE Name LIKE 'Columbus City%'")['n'] >= 1
    hits = tools.find_everywhere(con, 'Liverpool')
    assert hits and hits[0]['where'] == 'Person note'
    st = tools.statistics(con)
    assert st['people'] == 17 and st['earliestYear'] == 1808


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
