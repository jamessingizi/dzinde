"""Desktop shell checks (needs pywebview; skipped otherwise). Run: python3 tests/test_desktop.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import webview.util
except ImportError:
    print('skip: pywebview not installed')
    sys.exit(0)
from dzinde import desktop  # noqa: E402


class FakeWindow:
    def create_file_dialog(self, kind, **kw):
        self.kind, self.kw = kind, kw
        return ('/tmp/x.rmtree',)


def test_menu_matches_ui_commands():
    cmds = desktop.commands()
    assert len(cmds) > 80 and ('File', 'Open file') in cmds and ('Help', 'About Dzinde') in cmds, cmds[:5]
    assert {g for g, _ in cmds} <= set(desktop.MENU_ORDER), {g for g, _ in cmds}


def test_api_dialogs_and_guard():
    api = desktop.Api('http://127.0.0.1:1')
    api._window = w = FakeWindow()
    assert api.choose({'ext': '.rmtree,.rmgc', 'title': 'Open a .rmtree file'}) == '/tmp/x.rmtree'
    assert w.kind == webview.FileDialog.OPEN
    for t in w.kw['file_types']:
        webview.util.parse_file_type(t)  # raises on a filter string the native dialogs reject
    api.choose({'folder': True})
    assert w.kind == webview.FileDialog.FOLDER and w.kw['file_types'] == ()
    try:
        api.open_window('/etc/passwd', 'x')
        raise AssertionError('non-report path accepted')
    except ValueError:
        pass


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
