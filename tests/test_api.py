"""HTTP API smoke test. Run: python3 tests/test_api.py"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['HOME'] = tempfile.mkdtemp()  # isolate ~/.dzinde config
from dzinde import server  # noqa: E402

server.CONF_DIR = os.path.join(os.environ['HOME'], '.dzinde')
server.CONF = os.path.join(server.CONF_DIR, 'config.json')
server.APP.conf['dataDir'] = os.path.join(os.environ['HOME'], 'trees')
httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def call(method, path, body=None, headers=None):
    h = {'X-Dzinde': '1', 'Content-Type': 'application/json'}
    h.update(headers or {})
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', method=method, headers=h,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'null')


def ok(method, path, body=None):
    st, res = call(method, path, body)
    assert st == 200, (method, path, st, res)
    return res


def test_api():
    assert call('GET', '/api/files', headers={'X-Dzinde': ''})[0] == 403          # CSRF guard
    assert call('GET', '/api/files', headers={'Host': 'evil.example'})[0] == 403    # DNS-rebinding guard
    assert call('GET', '/api/people')[0] == 409                                     # no file open
    ok('POST', '/api/files/new', {'name': 'Api Test'})
    res = ok('POST', '/api/import/gedcom', {'path': os.path.join(ROOT, 'samples', 'hartwell.ged')})
    assert res['stats']['people'] == 16
    idx = ok('GET', '/api/people')
    assert len(idx['rows']) == 16 and idx['rows'][0][1] == 'Brook'
    thomas = next(r[0] for r in idx['rows'] if r[2] == 'Thomas')
    p = ok('GET', f'/api/person/{thomas}')
    assert p['summary']['name'] == 'Thomas Hartwell' and p['spouses'][0]['children']
    kid = ok('POST', '/api/person', {'given': 'New', 'surname': 'Child', 'sex': 0, 'rel': 'child', 'of': thomas, 'birthDate': '1845'})
    assert any(c['id'] == kid['id'] for c in ok('GET', f'/api/person/{thomas}')['spouses'][0]['children'])
    par = ok('POST', '/api/person', {'given': 'Old', 'surname': 'Hartwell', 'sex': 0, 'rel': 'parent', 'of': thomas})
    assert ok('GET', f'/api/person/{thomas}')['parents'][0]['father']['id'] == par['id']
    fact = ok('POST', '/api/fact', {'ownerType': 0, 'ownerId': thomas, 'type': 26, 'date': 'abt 1840', 'description': 'Cooper'})
    f = ok('PUT', f"/api/fact/{fact['id']}", {'Date': 'bet 1840 and 1845', 'Place': 'Leeds, Yorkshire, England'})
    assert f['dateText'] == 'bet 1840 and 1845' and f['place'].startswith('Leeds')
    ped = ok('GET', f'/api/pedigree/{thomas}?gens=4')
    assert ped['people']['2']['id'] == par['id']
    assert ok('GET', f'/api/descendants/{thomas}?gens=3')['families']
    assert len(ok('GET', '/api/couples')) == 6
    src = ok('GET', '/api/sources')
    assert len(src) == 3
    sd = ok('GET', f"/api/source/{src[0]['SourceID']}")
    assert sd['citations']
    assert ok('GET', '/api/places') and ok('GET', '/api/list/factTypes')
    res = ok('POST', '/api/search', {'criteria': [{'field': 'surname', 'op': 'equals', 'value': 'Hartwell'},
                                                  {'field': 'factDate', 'factType': 1, 'op': 'before', 'value': '1900'}]})
    assert len(res) == 7, [r['name'] for r in res]
    g = ok('POST', '/api/group', {'Name': 'Born before 1900', 'criteria': [{'field': 'factDate', 'factType': 1, 'op': 'before', 'value': '1900'}]})
    assert g['count'] == 13, g  # 7 Hartwells + Eliza, Sarah Ann, Jacob, Ida Rose, Dorothy, and 'New Child' (1845)
    assert ok('POST', '/api/tools/relationship', {'a': thomas, 'b': par['id']})['relationships'][0]['name'] == 'father'
    assert ok('POST', '/api/tools/problems', {})['rules']
    assert ok('POST', '/api/tools/dateCalc', {'mode': 'between', 'date1': '1 Jan 1900', 'date2': '15 Mar 1950'})['years'] == 50
    assert ok('POST', '/api/tools/db', {'action': 'integrity'})['result'] == ['ok']
    html = ok('POST', '/api/reports/run', {'id': 'rptFGS', 'options': {'family': p['spouses'][0]['id']}})['html']
    assert 'Family Group Sheet' in html
    ged = ok('POST', '/api/export/gedcom', {'who': 'all', 'options': {}})
    assert ged['people'] == 18 and '0 TRLR' in ged['content']
    site = ok('POST', '/api/tools/website', {'folder': os.path.join(os.environ['HOME'], 'site')})
    assert os.path.isfile(os.path.join(site['path'], 'surnames.html'))
    bk = ok('POST', '/api/files/backup', {})
    assert os.path.isfile(bk['path'])
    ok('DELETE', f"/api/person/{kid['id']}")
    assert call('GET', f"/api/person/{kid['id']}")[0] == 404
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/') as r:
        assert b'<html' in r.read().lower()


if __name__ == '__main__':
    test_api()
    print('ok test_api')
