"""Render every report against the sample data. Run: python3 tests/test_reports.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dzinde import db, gedcom, model as m, reports  # noqa: E402

# Report ids recovered from the RootsMagic 11 binary.
RM_REPORTS = '''chartAncestor chartAncestorFan chartDescendant chartHourglass rptAddressLabels rptAddressList rptAhnentafel
rptBirthdayList rptBoxChart rptCalendar rptCountTrees rptCountyCheck rptCustomReport rptDescendantList rptDNATestList
rptDuplicateList rptFactList rptFanList rptFanRelationship rptFGS rptGenericList rptHealthCondition rptHealthHistory
rptIndividualList rptIndividualSummary rptKinshipList rptLDSList rptLeedsReport rptMarriageList rptMissingInfoList
rptMultimediaList rptNarrativeReport rptOnThisDay rptPedigreeChart rptPhotograph rptPhotoTree rptPlaceList rptProblemList
rptRelateCalc rptRelationshipChart rptRepositoryList rptResearchLog rptResearchNotes rptScrapbook rptSourceList
rptStatisticsList rptSurnameStatistics rptTaskList rptTimelineList rptWebTagsList rptWhoWasThereList'''.split()


def test_all_reports_render():
    con = db.create(os.path.join(tempfile.mkdtemp(), 'r.rmtree'))
    gedcom.import_file(con, os.path.join(ROOT, 'samples', 'hartwell.ged'))
    pid = lambda g: m.row(con, 'SELECT OwnerID FROM NameTable WHERE Given=? AND IsPrimary=1', g)['OwnerID']
    thomas, grace = pid('Thomas'), pid('Grace')
    fam = m.spouse_families(con, thomas)[0]['FamilyID']
    mid = m.add_media(con, '/nonexistent/photo.jpg', caption='Portrait')
    m.link_media(con, mid, 0, thomas, primary=1)
    assert sorted(reports.REPORTS) == sorted(RM_REPORTS), set(RM_REPORTS) ^ set(reports.REPORTS)
    base = {'person': thomas, 'person2': grace, 'family': fam, 'media': mid, 'place': 'Columbus', 'from': 1830, 'to': 1880,
            'month': 3, 'day': 14}
    for rid, r in reports.REPORTS.items():
        opts = dict(base)
        for o in r['options']:
            if 'default' in o and o['key'] not in opts:
                opts[o['key']] = o['default']
        if rid in ('rptAhnentafel', 'chartAncestor', 'chartAncestorFan', 'rptPedigreeChart', 'rptPhotoTree', 'rptHealthHistory'):
            opts['person'] = grace
        html = reports.run(con, rid, opts)
        assert html.startswith('<!doctype html>') and len(html) > 600, (rid, html[:300])
    narr = reports.run(con, 'rptNarrativeReport', dict(base, generations=3))
    assert 'Thomas Hartwell was born on 14 Mar 1808 in Leeds' in narr and 'Endnotes' in narr and 'Index' in narr
    anc = reports.run(con, 'rptNarrativeReport', dict(base, person=grace, style='ancestors', generations=6))
    assert '<b>32.</b>' in anc.replace('<b>32. ', '<b>32.</b> ') or '32. ' in anc
    fgs = reports.run(con, 'rptFGS', dict(base))
    assert 'William Henry Hartwell' in fgs and 'Husband' in fgs
    rel = reports.run(con, 'rptRelateCalc', dict(base))
    assert '3rd great-granddaughter' in rel
    priv = reports.run(con, 'rptIndividualList', {'privatizeLiving': True})
    assert 'Grace' in priv  # not marked living yet
    con.execute('UPDATE PersonTable SET Living=1 WHERE PersonID=?', (grace,))
    priv = reports.run(con, 'rptIndividualList', {'privatizeLiving': True})
    assert 'Grace' not in priv and 'Living Hartwell' in priv


if __name__ == '__main__':
    test_all_reports_render()
    print('ok test_all_reports_render')
