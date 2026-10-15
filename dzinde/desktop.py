"""Native desktop shell: the same local server and UI inside an OS webview window (pywebview).

macOS uses WKWebView, Windows uses Edge WebView2, Linux uses Qt WebEngine (or WebKitGTK).
"""
import json
import os
import re
import sys
import threading
import webbrowser
from functools import partial

import webview
from webview.menu import Menu, MenuAction

from . import server

PORT = 8643  # fixed so the webview's origin-scoped localStorage survives restarts; 8642 stays free for run.py
MENU_ORDER = ['File', 'Edit', 'Add', 'View', 'Lists', 'Search', 'Tools', 'Reports', 'Help']


def commands():
    """[(menu, label)] parsed from the UI's command list (web/js/app.js) so the menu bar never drifts from it."""
    text = open(os.path.join(server.WEB, 'js', 'app.js'), encoding='utf-8').read()
    body = text[text.index('export function commands()'):text.index('function showShortcuts')]
    return re.findall(r"\['(\w+): ([^']+)'", body)


class Api:
    """Exposed to the page as window.pywebview.api (underscored attributes stay private)."""

    def __init__(self, base):
        self._base = base
        self._window = None

    def choose(self, o):
        """Native open/save/folder dialog. o = chooseFile() options from ui.js. Returns a path or None."""
        fd = webview.FileDialog
        kind = fd.FOLDER if o.get('folder') else fd.SAVE if o.get('save') else fd.OPEN
        exts = [e.strip().lstrip('.') for e in (o.get('ext') or '').split(',') if e.strip()]
        types = (f"Supported files ({';'.join('*.' + e for e in exts)})", 'All files (*.*)') if exts and kind == fd.OPEN else ()
        r = self._window.create_file_dialog(kind, directory=o.get('dir') or '', save_filename=o.get('defaultName') or '',
                                            file_types=types)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def save_text(self, name, text):
        """Save-as dialog, then write text there. Returns the path or None if cancelled."""
        p = self.choose({'save': True, 'defaultName': name})
        if p:
            with open(p, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
        return p

    def open_window(self, path, title, print_it=False):
        """Show one of our own report pages in a new native window, optionally opening the print dialog."""
        if not path.startswith('/report?'):
            raise ValueError('only report pages can be opened')
        url = self._base + path
        if print_it and webview.renderer.startswith('qt'):
            return webbrowser.open(url)  # ponytail: QtWebEngine ignores window.print(); hook page.printRequested if Linux users need it native
        w = webview.create_window(title, url, width=900, height=1000)
        if print_it:
            w.events.loaded += lambda: w.run_js('window.print()')


def _menu(api):
    def run(label):
        # menu callbacks may arrive on the UI thread; never block it waiting on JS
        threading.Thread(target=lambda: api._window.run_js(f'window.dzRun && window.dzRun({json.dumps(label)})'),
                         daemon=True).start()
    groups = {}
    for menu, label in commands():
        groups.setdefault(menu, []).append(MenuAction(label, partial(run, f'{menu}: {label}')))
    order = MENU_ORDER + [g for g in groups if g not in MENU_ORDER]
    return [Menu(g, groups[g]) for g in order if g in groups]


def _mac_tidy_menus():
    """pywebview's macOS defaults add their own Edit (cut/copy/paste) and View menus ahead of ours.
    Merge ours into them so each title appears once, then order the bar like RootsMagic's."""
    import AppKit
    bar = AppKit.NSApp.mainMenu()
    seen = {}
    for item in list(bar.itemArray())[1:]:
        title = item.submenu().title() if item.submenu() else item.title()
        if title in seen:
            dst, src = seen[title].submenu(), item.submenu()
            dst.addItem_(AppKit.NSMenuItem.separatorItem())
            for sub in list(src.itemArray()):
                src.removeItem_(sub)
                dst.addItem_(sub)
            bar.removeItem_(item)
        else:
            seen[title] = item
    for i, title in enumerate(t for t in MENU_ORDER if t in seen):
        item = seen[title]
        bar.removeItem_(item)
        bar.insertItem_atIndex_(item, i + 1)


def _bind(port, file):
    try:
        return server.start(port, file)
    except server.ApiError:  # unreadable file argument: start without it
        return _bind(port, None)
    except OSError:  # port in use (another Dzinde instance): take any free one
        if not port:
            raise
        return _bind(0, file)


def main(argv=None):
    if sys.stderr is None:  # windowed build on Windows: keep a log instead of crashing on writes
        os.makedirs(server.CONF_DIR, exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(server.CONF_DIR, 'desktop.log'), 'a', encoding='utf-8')
    args = [a for a in (sys.argv[1:] if argv is None else argv) if not a.startswith('-psn_')]  # macOS Finder launch arg
    file = next((a for a in args if a.lower().endswith(('.rmtree', '.rmgc'))), None)
    httpd = _bind(PORT, file)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    api = Api(base)

    geo = server.APP.conf.get('window') or {}
    # ponytail: position isn't restored (a window saved on an unplugged monitor would open off-screen)
    win = webview.create_window('Dzinde', base + '/', js_api=api, width=int(geo.get('width', 1280)), height=int(geo.get('height', 820)),
                                min_size=(900, 600), maximized=bool(geo.get('maximized')), text_select=True,
                                background_color='#F4F2EE')
    api._window = win
    size = {'maximized': bool(geo.get('maximized')), 'width': geo.get('width', 1280), 'height': geo.get('height', 820)}
    win.events.maximized += lambda: size.update(maximized=True)
    win.events.restored += lambda: size.update(maximized=False)
    win.events.resized += lambda w, h: size['maximized'] or size.update(width=w, height=h)

    def on_closed():
        for w in list(webview.windows):  # closing the main window quits, even with report windows open
            w.destroy()
    win.events.closed += on_closed
    if sys.platform == 'darwin':
        from PyObjCTools import AppHelper
        win.events.loaded += lambda: AppHelper.callAfter(_mac_tidy_menus)

    os.makedirs(server.CONF_DIR, exist_ok=True)
    webview.start(menu=_menu(api), private_mode=False, storage_path=os.path.join(server.CONF_DIR, 'webview'),
                  debug=bool(os.environ.get('DZINDE_DEBUG')))
    server.APP.conf['window'] = size
    server.APP.save_conf()
    httpd.shutdown()
    server.APP.close()
