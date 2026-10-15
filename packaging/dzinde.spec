# PyInstaller spec for the desktop app. Run from the repo root:  pyinstaller packaging/dzinde.spec
# Output: dist/Dzinde.app (macOS) or dist/Dzinde/ (Windows, Linux). PyInstaller only builds for the OS it runs on.
import os
import sys

ROOT = os.path.dirname(SPECPATH)
sys.path.insert(0, ROOT)
from dzinde import __version__  # noqa: E402

ICON = os.path.join(SPECPATH, 'icon.png')  # converted to .icns/.ico by Pillow at build time
MAC = sys.platform == 'darwin'

a = Analysis([os.path.join(SPECPATH, 'app.py')], pathex=[ROOT], datas=[(os.path.join(ROOT, 'web'), 'web')],
             excludes=['tkinter'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Dzinde', console=False, icon=ICON,
          argv_emulation=MAC)  # macOS: turns a Finder "open this .rmtree" at launch into argv
coll = COLLECT(exe, a.binaries, a.datas, name='Dzinde')
if MAC:
    app = BUNDLE(coll, name='Dzinde.app', icon=ICON, bundle_identifier='org.dzinde.desktop', version=__version__,
                 info_plist={
                     'NSHighResolutionCapable': True,
                     'CFBundleShortVersionString': __version__,
                     'LSApplicationCategoryType': 'public.app-category.reference',
                     'CFBundleDocumentTypes': [{
                         'CFBundleTypeName': 'RootsMagic Database',
                         'CFBundleTypeExtensions': ['rmtree', 'rmgc'],
                         'CFBundleTypeRole': 'Editor',
                         'LSHandlerRank': 'Alternate',  # don't take the file type away from an installed RootsMagic
                     }],
                 })
