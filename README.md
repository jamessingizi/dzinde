# Dzinde

A local, private genealogy application modelled feature-for-feature on RootsMagic 11, reading and writing the same
`.rmtree` SQLite database format. No dependencies beyond Python 3.10+ (standard library only) and a web browser.

```sh
python3 run.py                      # opens http://127.0.0.1:8642 in your browser
python3 run.py "~/Dzinde/My Family.rmtree" --port 9000 --no-browser
```

### Desktop app (macOS, Windows, Linux)
The same app in a native window with a real menu bar and native file dialogs:
```sh
pip install pywebview               # Linux: pip install "pywebview[qt]"
python3 run.py --desktop [file.rmtree]
```
Installers are built by `.github/workflows/desktop.yml` (push a `v*` tag or run it from the Actions tab):
`Dzinde-macOS-arm64.dmg` / `-x86_64.dmg`, `Dzinde-<version>-setup.exe`, `Dzinde-x86_64.AppImage`.
To build locally (only for the OS you're on): `pip install pyinstaller pillow pywebview && pyinstaller packaging/dzinde.spec`.
The builds are unsigned: on macOS right-click › Open the first time (or System Settings › Privacy & Security ›
Open Anyway); on Windows choose *More info › Run anyway*. Windows needs the Edge WebView2 runtime (built into
Windows 10/11).

First run: **Import a GEDCOM** (try `samples/hartwell.ged`) or **Create a new file**. Files live in `~/Dzinde` by default
(Settings › Folders). App config: `~/.dzinde/config.json`.

Press **F2** for the command palette (every menu command), **F1** for keyboard shortcuts
(Ctrl+Shift+S/P/C/I add spouse/parents/child/individual, Ctrl+1…6 views, Ctrl+S find person, Ctrl+P print…).

## What’s inside
| Path | Purpose |
|---|---|
| `dzinde/db.py` | RootsMagic-11 schema, `RMNOCASE` collation, seed fact types/roles/association types/templates |
| `dzinde/rmdate.py` | genealogical date parsing, RM `Date`/`SortDate` encoding, formatting, ages |
| `dzinde/templates.py` | sentence & source-template language |
| `dzinde/model.py` | people, families, facts, names, places, sources, citations, media, groups, sentences |
| `dzinde/gedcom.py` | GEDCOM import (UTF-8/ANSEL/ANSI) and export (privacy options) |
| `dzinde/tools.py` | relationships, kinship, duplicates/merge, problem list, DataClean, search/replace, DB tools, backup |
| `dzinde/reports.py` | the 51 reports and charts (HTML/SVG) |
| `dzinde/website.py` | static family-history website |
| `dzinde/server.py` | localhost JSON API + static UI |
| `dzinde/desktop.py` | native window, menu bar and file dialogs (pywebview) |
| `packaging/` | PyInstaller spec, icon, Windows installer (Inno Setup), Linux AppImage script |
| `web/` | browser UI (plain ES modules, no build step) |
| `FEATURES.md` | parity matrix against RootsMagic 11 |

## Tests
```sh
for t in tests/test_*.py; do python3 $t; done
```
Covers dates, schema, people/families/sentences, citations/templates, groups, GEDCOM round-trip & privacy, tools,
all 51 reports, the HTTP API (including the CSRF/DNS-rebinding guards), and the desktop shell (when pywebview is installed).

## Privacy & network
The server listens on 127.0.0.1 only and rejects cross-site requests. Nothing leaves your machine except when you
choose to: geocoding/gazetteer (OpenStreetMap Nominatim), map tiles and the Leaflet library (unpkg/OpenStreetMap),
and WebSearch links you open.

## RootsMagic templates
RootsMagic’s 415-template source library is copyrighted, so it is not bundled. If you own RootsMagic, import it:
Sources › Templates… › *Import RootsMagic template library* and choose
`RootsMagic 11.app/Contents/MacOS/rootsmagic.st`. Opening any `.rmtree` made by RootsMagic also brings its templates.
