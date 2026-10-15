# Dzinde ↔ RootsMagic 11 feature parity

Inventory source: the RootsMagic 11.5.0 macOS binary (Delphi FireMonkey). Recovered with static analysis:
- **103 main-menu actions** from the `TMainForm` action list (binary DFM resources),
- **378 dialog/frame forms** (e.g. `TEditPersonForm`, `TfrmMergeDuplicates`, `TfrmScarSettings`),
- **51 reports** (`rpt*` / `chart*` registrations with category, title, description),
- **the complete SQLite schema** (`CREATE TABLE … UTCModDate` literals) and default fact-type sentences.

Legend: ✅ implemented · ◐ implemented differently / partially (see note) · ✗ not implemented (reason given)

## File
| RootsMagic action | Dzinde | Notes |
|---|---|---|
| New file / Open file / Recent files | ✅ | Home page, command palette |
| Rename / Copy / Delete file, Properties | ✅ | File › Properties shows stats |
| Import data | ◐ | GEDCOM 5.5.1 (+5.5/7.0 tolerance, ANSEL, RM `_TMPLT`/`_SHAR`/`_UID` tags). No direct FTM/TMG/PAF/Legacy readers — export GEDCOM from those programs |
| Export (GEDCOM, privatize, selection) | ✅ | Everyone / ancestors / descendants / group; living privatized; private excluded |
| Backup / Restore | ✅ | `.rmbackup` zip, optional media |
| Database tools | ✅ | integrity, compact, reindex, phantom cleanup, unused places/sources |
| Compare files | ✅ | people only-in-A/B and differing facts |
| Import lists | ✅ | fact types, templates, places, sources+repositories, association types, roles |
| FamilySearch Central / TreeShare for Ancestry / MyRootsMagic / Save to Dropbox | ✗ | proprietary partner APIs that require RootsMagic’s credentials |
| RootsMagic ToGo / Shareable drive / Shareable CD | ✗ | packaging RootsMagic itself; Dzinde is a folder you can copy |

## Edit / Add
| RootsMagic action | Dzinde | Notes |
|---|---|---|
| Edit person (facts, names, notes, sources, media, tasks, DNA, health, associations, WebTags, groups, addresses, flags, 10 color sets) | ✅ | Edit Person dialog, all tabs |
| Fact editor (date parsing, place + place details, description, sentence preview/customize, primary/private/proof, citations, media, witnesses) | ✅ | |
| Shared facts / witnesses / roles | ✅ | share with people in file or unlinked witnesses; role sentences |
| Add individual / spouse / parents / child / association | ✅ | duplicate warning, “select existing person” |
| Delete person / family; unlink from spouse / parents / family | ✅ | |
| Swap couple; rearrange children / spouses | ✅ | |
| LDS ordinances | ◐ | LDS fact types + LDS list report; no FamilySearch ordinance reservation |
| Edit family (facts, notes, citations, media, child relationships birth/adopted/step/foster…) | ✅ | |

## View
| RootsMagic action | Dzinde | Notes |
|---|---|---|
| Pedigree (4–6 gen) | ✅ | click to navigate, empty slots add parents |
| Family view | ✅ | grandparents, multiple spouses, children with relationship badges |
| Descendants (2–7 gen) | ✅ | |
| Person list / Couple list / Association list | ✅ | sortable, filterable |
| Side info panel, name index (incl. alternate names) | ✅ | virtualized index scales to large files |
| Mapping | ✅ | Leaflet + OpenStreetMap (needs internet for tiles) |

## Lists
| RootsMagic list | Dzinde | Notes |
|---|---|---|
| Places (place details, geocode, merge, split, usage) | ✅ | geocoding via OpenStreetMap Nominatim |
| Sources & citations (templates, quality, reuse, memorize/paste, repositories) | ✅ | |
| Source templates (editor, template language `[F] <…> <?…|…> <#…#…|…>`) | ◐ | 9 starter templates written for Dzinde; RootsMagic’s 415 Evidence-Explained templates are importable from your own `rootsmagic.st` or any `.rmtree` |
| Fact types (sentences, GEDCOM tag, value/date/place) & roles | ✅ | |
| Media (gallery, tags, primary photo, fix broken links) | ◐ | no image cropping of face regions (`Rect*` columns preserved, not edited) |
| Tasks / research logs / correspondence | ✅ | |
| Addresses, repositories | ✅ | |
| Association (FAN) types, groups | ✅ | groups stored as RM ID ranges |

## Search
| RootsMagic action | Dzinde | Notes |
|---|---|---|
| Person search, advanced search criteria, saved searches | ✅ | 30 criteria incl. relationships, facts, groups |
| Find everywhere | ✅ | |
| Search and replace | ✅ | preview + per-field selection |
| Bookmarks, history, back/forward, root person, immediate family | ✅ | |
| WebSearch | ✅ | configurable providers |
| WebHints | ✗ | FamilySearch/Ancestry hint APIs |

## Tools
| RootsMagic tool | Dzinde | Notes |
|---|---|---|
| Problem list / Not-a-problem list | ✅ | 18 rules, adjustable thresholds |
| Duplicate search & merge, AutoMerge, Manual merge, Not-a-duplicate list | ✅ | side-by-side compare |
| DataClean (names, places) | ✅ | caps, nicknames, prefixes/suffixes, spacing, duplicate places |
| CountyCheck | ◐ | structural place checks; RM’s proprietary county database (`CountyCheckDB.dat`) not used |
| Gazetteer | ◐ | worldwide OpenStreetMap lookup instead of RM’s `PlaceDB.dat` |
| Count trees, Set living, Set relationships, Color coding | ✅ | |
| Date / Relationship / Soundex calculators, Calendar | ✅ | |
| Spell check | ◐ | browser spell checker in note editors |
| AI prompt builder | ✅ | builds prompt locally; nothing is sent |
| Character map | ✅ | in note editor |

## Reports (all 51 report ids from the binary)
All 51 are implemented and render to print-ready HTML (Print/Save PDF, open in tab, save HTML):
Ancestor chart, Descendant chart, Fan chart (180/270/360°), Hourglass chart, Pedigree chart (chained), Box chart, Photo tree,
Relationship chart, Family group sheet, Individual summary, Scrapbook, Photograph, Calendar, Family health history,
Relationship calculator, Problem list, Leeds method◐ (clusters by recorded common ancestor), List report, Narrative report
(Register, NGSQ, Ahnentafel narrative; endnotes; index), Ahnentafel, Descendant list, Individual list, Marriage list, Fact list,
Place list, Source list, Repository list, Address list, Address labels, Birthday & anniversary list, Count trees list,
Duplicate list, Kinship list, Missing info list, Multimedia list, On this day, Statistics, Surname statistics, Timeline,
WebTags list, Who was there, Task list, Research log, Research notes, Association list (individual), Association list
(relationship), Health conditions, DNA kinship list, LDS list, CountyCheck◐, Custom report◐ (field list instead of a drag-and-drop designer).

| Publish | Dzinde | Notes |
|---|---|---|
| Publisher (books: title page, TOC, report + text chapters) | ✅ | |
| HTML website | ✅ | static site; living privatized |
| Interactive large-chart editor (move boxes, borders, styles — `frmScar*`) | ◐ | charts are generated SVG; no per-box manual editing |

## Settings
Display (theme, text size, 7 date formats, name formats, surname caps), General, Folders, Preparer, Color names & 10 color sets,
LDS toggle, WebSearch providers — ✅. Program language selection — ✗ (English UI only).

## Application shell
Native desktop app on macOS, Windows and Linux (like RootsMagic's own app) — ✅ via pywebview: OS menu bar with
every command, native open/save/folder dialogs, print, remembered window size, `.rmtree` "Open with" registration.
Not done: re-opening a file double-clicked while the macOS app is already running (only at launch), code signing.

## File format
Dzinde’s database **is** the RootsMagic 11 schema (all 32 tables, `RMNOCASE` collation, `UTCModDate` as Delphi time,
groups as ID ranges, citation quality `~~~`/`OPD`, source/citation `Fields` XML, template `FieldDefs` XML).
Two encodings are implemented from community documentation and are **not yet verified** against RootsMagic’s own code
(tracked as REA unknowns): the 24-character `Date` string / 64-bit `SortDate` packing, and the IDs of built-in fact types
outside 1–39 / 300–311. Files written by Dzinde are internally consistent; please keep backups before editing RootsMagic files.
