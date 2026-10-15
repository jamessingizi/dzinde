"""Reports & charts. Each report: registry entry with option schema + render(ctx) -> HTML body.
The catalog mirrors RootsMagic 11's report list (ids recovered from the binary)."""
import calendar
import datetime
import math
from html import escape as E

from . import model as m, rmdate, tools
from .db import OWNER, row, rows

REPORTS = {}

OPT_PERSON = {'key': 'person', 'type': 'person', 'label': 'Start person'}
OPT_GENS = lambda d=4, mx=40: {'key': 'generations', 'type': 'int', 'label': 'Generations', 'default': d, 'min': 1, 'max': mx}
OPT_WHO = {'key': 'who', 'type': 'who', 'label': 'People to include', 'default': 'all'}
OPT_PRIV = [{'key': 'privatizeLiving', 'type': 'bool', 'label': 'Privatize living people', 'default': False},
            {'key': 'includePrivate', 'type': 'bool', 'label': 'Include private facts and notes', 'default': False}]
OPT_SOURCES = {'key': 'sources', 'type': 'select', 'label': 'Sources', 'default': 'endnotes',
               'choices': [['none', 'None'], ['endnotes', 'Endnotes'], ['footnotes', 'Footnotes (end of section)']]}
OPT_NOTES = {'key': 'notes', 'type': 'bool', 'label': 'Include notes', 'default': True}
OPT_TITLE = {'key': 'title', 'type': 'text', 'label': 'Report title', 'default': ''}


def report(rid, category, title, desc, options=()):
    def deco(fn):
        REPORTS[rid] = {'id': rid, 'category': category, 'title': title, 'description': desc,
                        'options': [OPT_TITLE] + list(options), 'fn': fn}
        return fn
    return deco


class Ctx:
    def __init__(self, con, opts):
        self.con, self.o = con, opts
        self.s = m.settings(con)
        self.fmt = self.s.get('dateFormat', 'dmy')
        self.notes = []          # endnotes
        self.note_index = {}
        self.index = {}          # person id -> set(labels)
        self._living = {}

    def opt(self, k, d=None):
        v = self.o.get(k)
        return d if v in (None, '') else v

    def living_hidden(self, pid):
        if not self.opt('privatizeLiving') or not pid:
            return False
        if pid not in self._living:
            r = row(self.con, 'SELECT Living FROM PersonTable WHERE PersonID=?', pid)
            self._living[pid] = bool(r and r['Living'])
        return self._living[pid]

    def name(self, pid, style=None, link=True):
        if not pid:
            return ''
        if self.living_hidden(pid):
            return 'Living ' + E(m.primary_name(self.con, pid).get('Surname', ''))
        return E(m.person_name(self.con, pid, style or self.s.get('nameFormat'), self.s.get('surnameCaps')))

    def idx(self, pid, where):
        if pid:
            self.index.setdefault(pid, set()).add(str(where))

    def date(self, enc):
        return E(rmdate.format(enc, self.fmt))

    def facts(self, owner, oid):
        out = []
        for f in m.facts_for(self.con, owner, oid, self.s, include_shared=False):
            if f['private'] and not self.opt('includePrivate'):
                continue
            out.append(f)
        return out

    def birth(self, pid):
        return m.first_event(self.con, pid, (1, 3, 7))

    def death(self, pid):
        return m.first_event(self.con, pid, (2, 4, 5))

    def life(self, pid):
        if self.living_hidden(pid):
            return ''
        b, d = self.birth(pid), self.death(pid)
        by = rmdate.year(b['Date']) if b else 0
        dy = rmdate.year(d['Date']) if d else 0
        return f'{by or ""}–{dy or ""}' if by or dy else ''

    def cite(self, otype, oid):
        """Endnote superscripts for an owner's citations."""
        mode = self.opt('sources', 'endnotes')
        if mode == 'none':
            return ''
        refs = []
        for c in m.citations_for(self.con, otype, oid):
            key = c['CitationID']
            if key not in self.note_index:
                self.notes.append(c['footnote'] or E(c['SourceName'] or ''))
                self.note_index[key] = len(self.notes)
            refs.append(self.note_index[key])
        return f'<sup class="cite">{",".join(map(str, sorted(set(refs))))}</sup>' if refs else ''

    def endnotes_html(self):
        if not self.notes:
            return ''
        items = ''.join(f'<li>{n}</li>' for n in self.notes)
        return f'<h2 class="endnotes">Endnotes</h2><ol class="notes">{items}</ol>'

    def index_html(self):
        if not self.index or not self.opt('index', True):
            return ''
        entries = sorted(((m.primary_name(self.con, p).get('Surname', ''), m.primary_name(self.con, p).get('Given', ''), p, w)
                          for p, w in self.index.items()), key=lambda t: (t[0].lower(), t[1].lower()))
        out = ['<h2>Index</h2><div class="index">']
        for sur, giv, p, where in entries:
            nm = f'{E(sur)}, {E(giv)}' if not self.living_hidden(p) else f'{E(sur)}, Living'
            out.append(f'<div>{nm} <span class="life">{self.life(p)}</span> — {", ".join(sorted(where, key=_natkey))}</div>')
        out.append('</div>')
        return ''.join(out)

    def people(self):
        """Resolve the 'who' option: all / group:<id> / ancestors:<pid> / descendants:<pid> / person:<pid>."""
        who = str(self.opt('who', 'all'))
        if who.startswith('group:'):
            return m.group_members(self.con, int(who[6:]))
        if who.startswith('ancestors:'):
            return list(tools.all_ancestors(self.con, int(who[10:])))
        if who.startswith('descendants:'):
            p = int(who[12:])
            return [p] + [c for c, _, _ in tools.descendants(self.con, p)]
        if who.startswith('person:'):
            return [int(who[7:])]
        return [r['PersonID'] for r in rows(self.con, 'SELECT PersonID FROM PersonTable')]

    def sorted_people(self, ids):
        def k(p):
            n = m.primary_name(self.con, p)
            return ((n.get('Surname') or '').lower(), (n.get('Given') or '').lower(), n.get('BirthYear') or 0)
        return sorted(ids, key=k)


def _natkey(s):
    import re
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', s)]


PAGE_CSS = """
@page { size: auto; margin: 16mm 14mm; }
body { font: 11pt/1.45 Georgia, 'Times New Roman', serif; color: #111; margin: 0; padding: 18px 26px; background: #fff; }
h1 { font-size: 20pt; margin: 0 0 4px; text-align: center; }
.sub { text-align: center; color: #555; margin-bottom: 18px; font-size: 10pt; }
h2 { font-size: 14pt; margin: 22px 0 8px; border-bottom: 1px solid #999; padding-bottom: 2px; break-after: avoid; }
h3 { font-size: 12pt; margin: 14px 0 6px; break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; }
th, td { border: 1px solid #bbb; padding: 3px 6px; text-align: left; vertical-align: top; }
th { background: #eee; }
table.plain td, table.plain th { border: none; padding: 2px 6px 2px 0; }
.life { color: #555; font-size: 0.9em; }
sup.cite { font-size: 0.7em; color: #333; }
ol.notes { font-size: 9.5pt; }
.index { columns: 2; font-size: 9.5pt; }
.person-block { break-inside: avoid; margin-bottom: 10px; }
.children { margin: 4px 0 8px 22px; }
.children td { border: none; padding: 1px 6px 1px 0; }
.gen { break-before: auto; }
.chart { width: 100%; height: auto; }
.prep { margin-top: 30px; font-size: 9pt; color: #555; border-top: 1px solid #ccc; padding-top: 6px; }
.fgs td.lbl { width: 110px; background: #f6f6f6; font-weight: bold; }
.labels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; }
.label { border: 1px dashed #ccc; padding: 10px 12px; height: 92px; overflow: hidden; font-size: 10pt; }
.photo { max-width: 160px; max-height: 200px; }
.scrap { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.scrap figure { margin: 0; break-inside: avoid; text-align: center; }
.scrap img { max-width: 100%; max-height: 260px; }
.cal { break-inside: avoid; margin-bottom: 18px; }
.cal td { height: 64px; width: 14%; font-size: 8.5pt; }
.cal td b { font-size: 10pt; }
.indent0 { margin-left: 0 } .muted { color: #666 }
@media print { .noprint { display: none } body { padding: 0 } }
"""


def run(con, rid, opts):
    r = REPORTS[rid]
    ctx = Ctx(con, opts or {})
    body = r['fn'](ctx)
    title = ctx.opt('title') or getattr(ctx, 'title', None) or r['title']
    prep = ctx.s.get('preparer') or {}
    prep_html = ''
    if prep.get('name'):
        prep_html = f'<div class="prep">Prepared by {E(prep["name"])}' + \
                    (f', {E(prep["address"])}' if prep.get('address') else '') + \
                    (f', {E(prep["email"])}' if prep.get('email') else '') + \
                    f' — {datetime.date.today():%d %b %Y}</div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{E(title)}</title>'
            f'<style>{PAGE_CSS}</style></head><body><h1>{E(title)}</h1>'
            f'<div class="sub">{E(getattr(ctx, "subtitle", ""))}</div>{body}{prep_html}</body></html>')


def catalog():
    return [{k: v for k, v in r.items() if k != 'fn'} for r in REPORTS.values()]


# ============================================================== SVG charts
def _box(ctx, pid, x, y, w, h, extra='', photo=False):
    if not pid:
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="#fafafa" stroke="#ccc" stroke-dasharray="3,3"/>'
    sex = (row(ctx.con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid) or {'Sex': 2})['Sex']
    fill = {0: '#e8f0fb', 1: '#fbe8ef'}.get(sex, '#f1f1f1')
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="#7a8796"/>']
    tx = x + 6
    if photo:
        ph = m.primary_photo(ctx.con, pid)
        if ph and not ctx.living_hidden(pid):
            out.append(f'<image href="/api/media/{ph["MediaID"]}/file" x="{x + 4}" y="{y + 4}" width="{h - 8}" height="{h - 8}" preserveAspectRatio="xMidYMid slice"/>')
        tx = x + h + 2
    fs = 11 if h >= 40 else 9
    out.append(f'<text x="{tx}" y="{y + fs + 4}" font-size="{fs}" font-weight="bold" font-family="Helvetica,Arial">{_clip(ctx.name(pid), int((w - (tx - x)) / (fs * 0.55)))}</text>')
    if not ctx.living_hidden(pid) and h >= 30:
        b, d = ctx.birth(pid), ctx.death(pid)
        lines = []
        if b:
            lines.append('b. ' + rmdate.format(b['Date'], ctx.fmt) + (', ' + m.place_name(ctx.con, b['PlaceID']).split(',')[0] if b['PlaceID'] and h >= 54 else ''))
        if d:
            lines.append('d. ' + rmdate.format(d['Date'], ctx.fmt) + (', ' + m.place_name(ctx.con, d['PlaceID']).split(',')[0] if d['PlaceID'] and h >= 54 else ''))
        for i, ln in enumerate(lines[:max(1, (h - 18) // 13)]):
            out.append(f'<text x="{tx}" y="{y + fs + 17 + i * 12}" font-size="9" font-family="Helvetica,Arial" fill="#333">{E(_clip(ln, int((w - (tx - x)) / 5)))}</text>')
    if extra:
        out.append(extra)
    return ''.join(out)


def _clip(s, n):
    return s if len(s) <= n else s[:max(1, n - 1)] + '…'


def _svg(w, h, inner):
    return f'<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="max-width:{w}px">{inner}</svg>'


def pedigree_svg(ctx, pid, gens, box_w=200, box_h=48, photo=False):
    anc = tools.ancestors(ctx.con, pid, gens)
    leaves = 2 ** (gens - 1)
    row_h = box_h + 10
    H = leaves * row_h + 10
    col_w = box_w + 30
    W = gens * col_w + 10
    out = []
    for g in range(gens):
        n_in_gen = 2 ** g
        for i in range(n_in_gen):
            num = n_in_gen + i
            span = H / n_in_gen
            y = span * i + span / 2 - box_h / 2
            x = 5 + g * col_w
            p = anc.get(num, 0)
            if g < gens - 1:
                for child in (2 * num, 2 * num + 1):
                    j = child - 2 * n_in_gen
                    cspan = H / (2 * n_in_gen)
                    cy = cspan * j + cspan / 2
                    out.append(f'<path d="M{x + box_w} {y + box_h / 2} H{x + box_w + 15} V{cy} H{x + col_w}" fill="none" stroke="#7a8796"/>')
            label = f'<text x="{x + box_w - 4}" y="{y + box_h - 4}" font-size="8" text-anchor="end" fill="#888">{num}</text>'
            out.append(_box(ctx, p, x, y, box_w, box_h, label, photo))
            if p:
                ctx.idx(p, 'chart')
    return _svg(W, H, ''.join(out))


def descendant_layout(ctx, pid, gens):
    """Tidy tree: returns nodes [(pid, gen, x, spouse)] with x in leaf units, and edges."""
    nodes, edges = [], []
    counter = [0]

    def place(p, g, parent_idx):
        kids = []
        if g < gens - 1:
            for f in m.spouse_families(ctx.con, p):
                kids += [(c, f['spouse']) for c in m.children_of(ctx.con, f['FamilyID'])]
        idx = len(nodes)
        nodes.append([p, g, 0, None])
        spouses = [f['spouse'] for f in m.spouse_families(ctx.con, p) if f['spouse']]
        nodes[idx][3] = spouses[0] if spouses else 0
        if parent_idx is not None:
            edges.append((parent_idx, idx))
        if not kids:
            nodes[idx][2] = counter[0]
            counter[0] += 1
        else:
            xs = [place(c, g + 1, idx) for c, _ in kids]
            nodes[idx][2] = (xs[0] + xs[-1]) / 2
        return nodes[idx][2]
    place(pid, 0, None)
    return nodes, edges, counter[0]


def descendant_svg(ctx, pid, gens, box_w=150, box_h=50, show_spouse=True):
    nodes, edges, leaves = descendant_layout(ctx, pid, gens)
    gap_x, gap_y = 14, 40
    bh = box_h * (2 if show_spouse else 1)
    W = max(1, leaves) * (box_w + gap_x) + 10
    H = (max(n[1] for n in nodes) + 1) * (bh + gap_y) + 10
    out = []
    pos = {}
    for i, (p, g, x, sp) in enumerate(nodes):
        X, Y = 5 + x * (box_w + gap_x), 5 + g * (bh + gap_y)
        pos[i] = (X, Y)
        out.append(_box(ctx, p, X, Y, box_w, box_h))
        ctx.idx(p, 'chart')
        if show_spouse and sp:
            out.append(_box(ctx, sp, X, Y + box_h, box_w, box_h))
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        mid = y1 + bh + gap_y / 2
        out.append(f'<path d="M{x1 + box_w / 2} {y1 + bh} V{mid} H{x2 + box_w / 2} V{y2}" fill="none" stroke="#7a8796"/>')
    return _svg(W, H, ''.join(out))


def fan_svg(ctx, pid, gens, degrees=270):
    anc = tools.ancestors(ctx.con, pid, gens)
    R0, ring = 60, 70
    Rmax = R0 + ring * (gens - 1)
    cx = cy = Rmax + 10
    span = math.radians(degrees)
    start = -math.pi / 2 - span / 2
    out = [f'<circle cx="{cx}" cy="{cy}" r="{R0}" fill="#e8f0fb" stroke="#7a8796"/>',
           f'<text x="{cx}" y="{cy}" font-size="11" text-anchor="middle" font-family="Helvetica" font-weight="bold">{_clip(ctx.name(pid), 18)}</text>',
           f'<text x="{cx}" y="{cy + 14}" font-size="9" text-anchor="middle" font-family="Helvetica">{ctx.life(pid)}</text>']
    ctx.idx(pid, 'chart')
    colors = ['#dbe9f6', '#f6e3db', '#e2f2df', '#f3eccf', '#e8def3', '#d9efef', '#f2dce8']
    for g in range(1, gens):
        n = 2 ** g
        r1, r2 = R0 + ring * (g - 1), R0 + ring * g
        for i in range(n):
            a1 = start + span * i / n
            a2 = start + span * (i + 1) / n
            p = anc.get(n + i, 0)
            large = 1 if a2 - a1 > math.pi else 0
            pts = [(cx + r1 * math.cos(a1), cy + r1 * math.sin(a1)), (cx + r2 * math.cos(a1), cy + r2 * math.sin(a1)),
                   (cx + r2 * math.cos(a2), cy + r2 * math.sin(a2)), (cx + r1 * math.cos(a2), cy + r1 * math.sin(a2))]
            d = (f'M{pts[0][0]:.1f} {pts[0][1]:.1f} L{pts[1][0]:.1f} {pts[1][1]:.1f} '
                 f'A{r2} {r2} 0 {large} 1 {pts[2][0]:.1f} {pts[2][1]:.1f} L{pts[3][0]:.1f} {pts[3][1]:.1f} '
                 f'A{r1} {r1} 0 {large} 0 {pts[0][0]:.1f} {pts[0][1]:.1f}Z')
            fill = colors[(g - 1) % len(colors)] if p else '#fafafa'
            out.append(f'<path d="{d}" fill="{fill}" stroke="#7a8796"/>')
            if p:
                ctx.idx(p, 'chart')
                am = (a1 + a2) / 2
                rm = (r1 + r2) / 2
                tx, ty = cx + rm * math.cos(am), cy + rm * math.sin(am)
                arc_len = rm * (a2 - a1)
                rot = math.degrees(am) + 90
                if arc_len < 60:  # narrow: radial text
                    rot = math.degrees(am)
                    if math.cos(am) < 0:
                        rot += 180
                    maxc = int(ring / 6)
                else:
                    if math.sin(am) > 0.2:
                        rot += 180
                    maxc = int(arc_len / 6)
                fs = 10 if g < 4 else 8 if g < 6 else 6
                out.append(f'<g transform="translate({tx:.1f},{ty:.1f}) rotate({rot:.1f})">'
                           f'<text font-size="{fs}" text-anchor="middle" font-family="Helvetica" y="-1">{_clip(ctx.name(p), maxc)}</text>'
                           f'<text font-size="{fs - 1}" text-anchor="middle" font-family="Helvetica" y="{fs}" fill="#444">{ctx.life(p)}</text></g>')
    H = cy + (Rmax * max(0.0, -math.cos(math.pi - span / 2)) if degrees > 180 else 0) + 20
    return _svg(2 * cx, max(H, cy + 60), ''.join(out))


# ============================================================== chart reports
@report('chartAncestor', 'Charts (Large format)', 'Ancestor Chart', 'A large chart of ancestors of a person in your file',
        [OPT_PERSON, OPT_GENS(6, 15), {'key': 'photos', 'type': 'bool', 'label': 'Show photos', 'default': False}] + OPT_PRIV)
def r_ancestor_chart(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Ancestor Chart for {m.person_name(ctx.con, pid)}'
    g = int(ctx.opt('generations', 6))
    return pedigree_svg(ctx, pid, g, 220 if g < 7 else 170, 52 if g < 6 else 30, bool(ctx.opt('photos')))


@report('chartDescendant', 'Charts (Large format)', 'Descendant Chart', 'A large chart of descendants of a person in your file',
        [OPT_PERSON, OPT_GENS(4, 20), {'key': 'spouses', 'type': 'bool', 'label': 'Show spouses', 'default': True}] + OPT_PRIV)
def r_descendant_chart(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Descendant Chart for {m.person_name(ctx.con, pid)}'
    return descendant_svg(ctx, pid, int(ctx.opt('generations', 4)), show_spouse=bool(ctx.opt('spouses', True)))


@report('chartAncestorFan', 'Charts (Large format)', 'Fan Chart', 'Circular chart of the ancestors of a person',
        [OPT_PERSON, OPT_GENS(5, 9), {'key': 'degrees', 'type': 'select', 'label': 'Fan shape', 'default': '270',
                                      'choices': [['180', 'Half circle'], ['270', 'Three-quarter'], ['360', 'Full circle']]}] + OPT_PRIV)
def r_fan(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Fan Chart for {m.person_name(ctx.con, pid)}'
    return fan_svg(ctx, pid, int(ctx.opt('generations', 5)), int(ctx.opt('degrees', 270)))


@report('chartHourglass', 'Charts (Large format)', 'Hourglass Chart', 'A large chart of the ancestors and descendants of a person in your file',
        [OPT_PERSON, {'key': 'ancGens', 'type': 'int', 'label': 'Ancestor generations', 'default': 3, 'min': 1, 'max': 10},
         {'key': 'descGens', 'type': 'int', 'label': 'Descendant generations', 'default': 3, 'min': 1, 'max': 10}] + OPT_PRIV)
def r_hourglass(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Hourglass Chart for {m.person_name(ctx.con, pid)}'
    ag, dg = int(ctx.opt('ancGens', 3)), int(ctx.opt('descGens', 3))
    # ancestors drawn top-down (oldest at top), centered
    anc = tools.ancestors(ctx.con, pid, ag)
    bw, bh, gx, gy = 150, 48, 10, 30
    width_leaves = 2 ** (ag - 1)
    nodes, edges, leaves = descendant_layout(ctx, pid, dg)
    W = max(width_leaves, leaves) * (bw + gx) + 10
    out = []
    for g in range(ag - 1, -1, -1):
        n = 2 ** g
        for i in range(n):
            num = n + i
            slot = W / n
            x = slot * i + slot / 2 - bw / 2
            y = (ag - 1 - g) * (bh + gy) + 5
            if num != 1:
                out.append(_box(ctx, anc.get(num, 0), x, y, bw, bh))
                child = num // 2
                cg = g - 1
                cslot = W / (2 ** cg)
                cx = cslot * (child - 2 ** cg) + cslot / 2
                out.append(f'<path d="M{x + bw / 2} {y + bh} V{y + bh + gy / 2} H{cx} V{y + bh + gy}" fill="none" stroke="#7a8796"/>')
    top = (ag - 1) * (bh + gy) + 5
    offset = (W - leaves * (bw + gx)) / 2
    pos = {}
    for i, (p, g, x, sp) in enumerate(nodes):
        X, Y = offset + 5 + x * (bw + gx), top + g * (bh + gy)
        if g == 0:
            X = W / 2 - bw / 2
        pos[i] = (X, Y)
        out.append(_box(ctx, p, X, Y, bw, bh))
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        out.append(f'<path d="M{x1 + bw / 2} {y1 + bh} V{y1 + bh + gy / 2} H{x2 + bw / 2} V{y2}" fill="none" stroke="#7a8796"/>')
    H = top + (max(n[1] for n in nodes) + 1) * (bh + gy) + 10
    return _svg(W, H, ''.join(out))


@report('rptPedigreeChart', 'Charts (Reports)', 'Pedigree Chart', "A chart of a person's ancestors",
        [OPT_PERSON, {'key': 'generations', 'type': 'select', 'label': 'Generations per page', 'default': '4',
                      'choices': [['4', '4'], ['5', '5'], ['6', '6']]},
         {'key': 'chained', 'type': 'bool', 'label': 'Continue on additional charts', 'default': False}] + OPT_PRIV)
def r_pedigree(ctx):
    pid = int(ctx.opt('person'))
    g = int(ctx.opt('generations', 4))
    ctx.title = f'Pedigree Chart for {m.person_name(ctx.con, pid)}'
    out = [f'<h3>Chart 1</h3>' if ctx.opt('chained') else '', pedigree_svg(ctx, pid, g, 230, 54 if g < 6 else 36)]
    if ctx.opt('chained'):
        anc = tools.ancestors(ctx.con, pid, g)
        last = [anc[k] for k in sorted(anc) if k >= 2 ** (g - 1)]
        for i, p in enumerate(last, 2):
            if tools.parents(ctx.con, p):
                out.append(f'<h3 style="break-before:page">Chart {i}: {ctx.name(p)}</h3>' + pedigree_svg(ctx, p, g, 230, 54 if g < 6 else 36))
    return ''.join(out)


@report('rptBoxChart', 'Charts (Reports)', 'Box Chart', 'An ancestor or descendant chart putting each person in a box',
        [OPT_PERSON, OPT_GENS(4, 10), {'key': 'direction', 'type': 'select', 'label': 'Chart type', 'default': 'descendants',
                                       'choices': [['descendants', 'Descendants'], ['ancestors', 'Ancestors']]}] + OPT_PRIV)
def r_box(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Box Chart for {m.person_name(ctx.con, pid)}'
    if ctx.opt('direction') == 'ancestors':
        return pedigree_svg(ctx, pid, int(ctx.opt('generations', 4)), 190, 46)
    return descendant_svg(ctx, pid, int(ctx.opt('generations', 4)), 140, 46, False)


@report('rptPhotoTree', 'Charts (Reports)', 'Photo Tree', 'A tree with pictures',
        [OPT_PERSON, {'key': 'generations', 'type': 'select', 'label': 'Generations', 'default': '3',
                      'choices': [['3', '3'], ['4', '4']]}] + OPT_PRIV)
def r_photo_tree(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Photo Tree for {m.person_name(ctx.con, pid)}'
    return pedigree_svg(ctx, pid, int(ctx.opt('generations', 3)), 260, 90, photo=True)


@report('rptRelationshipChart', 'Charts (Reports)', 'Relationship Chart', 'A chart showing the relationship between 2 people',
        [OPT_PERSON, {'key': 'person2', 'type': 'person', 'label': 'Second person'}] + OPT_PRIV)
def r_relationship_chart(ctx):
    a, b = int(ctx.opt('person')), int(ctx.opt('person2'))
    ca = tools.common_ancestors(ctx.con, a, b)
    ctx.title = f'Relationship Chart: {m.person_name(ctx.con, a)} and {m.person_name(ctx.con, b)}'
    if not ca:
        return '<p>No blood relationship was found between these people.</p>'
    anc, g1, g2 = ca[0]
    rel = tools.relationships(ctx.con, a, b)
    ctx.subtitle = f'{m.person_name(ctx.con, b)} is the {rel[0]["name"]} of {m.person_name(ctx.con, a)}' if rel else ''

    def path_down(start, target, gens):
        """Line of descent from ancestor `start` down to `target`."""
        line = [target]
        cur = target
        for _ in range(gens):
            for f, mo, _ in tools.parents(ctx.con, cur):
                anc_set = tools.all_ancestors(ctx.con, f) if f else {}
                if f and (f == start or start in anc_set):
                    cur = f
                    break
                if mo and (mo == start or start in tools.all_ancestors(ctx.con, mo)):
                    cur = mo
                    break
            line.append(cur)
        return list(reversed(line))
    la, lb = path_down(anc, a, g1), path_down(anc, b, g2)
    bw, bh, gy = 210, 48, 26
    rows_n = max(len(la), len(lb))
    W, H = 2 * bw + 80, rows_n * (bh + gy) + 10
    out = [_box(ctx, anc, W / 2 - bw / 2, 5, bw, bh)]
    for col, line in ((0, la), (1, lb)):
        x = 10 if col == 0 else W - bw - 10
        prev = (W / 2, 5 + bh)
        for i, p in enumerate(line[1:], 1):
            y = 5 + i * (bh + gy)
            out.append(f'<path d="M{prev[0]} {prev[1]} V{y - gy / 2} H{x + bw / 2} V{y}" fill="none" stroke="#7a8796"/>')
            out.append(_box(ctx, p, x, y, bw, bh))
            prev = (x + bw / 2, y + bh)
    if g1 == 0 or g2 == 0:  # direct line: single column
        line = lb if g1 == 0 else la
        out = []
        for i, p in enumerate(line):
            y = 5 + i * (bh + gy)
            out.append(_box(ctx, p, W / 2 - bw / 2, y, bw, bh))
            if i:
                out.append(f'<path d="M{W / 2} {y - gy} V{y}" stroke="#7a8796"/>')
    return _svg(W, H, ''.join(out))


# ============================================================== forms
def _fact_rows(ctx, owner, oid, cols=('date', 'place')):
    out = []
    for f in ctx.facts(owner, oid):
        desc = E(f['description'])
        place = E(', '.join(x for x in (f['placeDetails'], f['place']) if x))
        out.append(f'<tr><td>{E(f["typeName"])}</td><td>{E(f["date"])}</td><td>{place}{" — " + desc if desc and place else desc}'
                   f'{ctx.cite(2, f["id"])}</td></tr>')
    return ''.join(out)


@report('rptFGS', 'Forms', 'Family Group Sheet', 'A table view of a family',
        [{'key': 'family', 'type': 'family', 'label': 'Family'}, OPT_SOURCES, OPT_NOTES,
         {'key': 'allFamilies', 'type': 'bool', 'label': 'Print for everyone in "People to include"', 'default': False},
         OPT_WHO] + OPT_PRIV)
def r_fgs(ctx):
    fams = [int(ctx.opt('family'))] if not ctx.opt('allFamilies') else \
        sorted({f['FamilyID'] for p in ctx.people() for f in m.spouse_families(ctx.con, p)})
    out = []
    for i, fid in enumerate(fams):
        f = row(ctx.con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', fid)
        if not f:
            continue
        if len(fams) == 1:
            ctx.title = f'Family Group Sheet: {m.couple_name(ctx.con, f)}'
        sec = [f'<div class="fgs" style="{"break-before:page" if i else ""}">']
        for label, pid in (('Husband', f['FatherID']), ('Wife', f['MotherID'])):
            if not pid:
                continue
            ctx.idx(pid, 'FGS')
            fa, mo, _ = m.primary_parents(ctx.con, pid)
            sec.append(f'<h3>{label}: {ctx.name(pid)}{ctx.cite(0, pid)}</h3><table>')
            if not ctx.living_hidden(pid):
                sec.append(_fact_rows(ctx, 'person', pid))
            sec.append(f'<tr><td class="lbl">Father</td><td colspan=2>{ctx.name(fa)}</td></tr>'
                       f'<tr><td class="lbl">Mother</td><td colspan=2>{ctx.name(mo)}</td></tr>')
            others = [x['spouse'] for x in m.spouse_families(ctx.con, pid) if x['FamilyID'] != fid and x['spouse']]
            if others:
                sec.append(f'<tr><td class="lbl">Other spouses</td><td colspan=2>{", ".join(ctx.name(o) for o in others)}</td></tr>')
            sec.append('</table>')
        fam_facts = _fact_rows(ctx, 'family', fid)
        if fam_facts and not (ctx.living_hidden(f['FatherID']) or ctx.living_hidden(f['MotherID'])):
            sec.append(f'<h3>Family events{ctx.cite(1, fid)}</h3><table>{fam_facts}</table>')
        kids = m.children_of(ctx.con, fid)
        if kids:
            sec.append('<h3>Children</h3>')
        for n, c in enumerate(kids, 1):
            ctx.idx(c, 'FGS')
            sex = {0: 'M', 1: 'F'}.get((row(ctx.con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', c) or {}).get('Sex'), '?')
            sec.append(f'<table><tr><th colspan=3>{n}. {sex} {ctx.name(c)}{ctx.cite(0, c)}</th></tr>')
            if not ctx.living_hidden(c):
                sec.append(_fact_rows(ctx, 'person', c))
                for sf in m.spouse_families(ctx.con, c):
                    if sf['spouse']:
                        mar = m.first_event(ctx.con, sf['FamilyID'], (300,), owner=1)
                        sec.append(f'<tr><td class="lbl">Spouse</td><td colspan=2>{ctx.name(sf["spouse"])}'
                                   f'{" — m. " + ctx.date(mar["Date"]) if mar else ""}</td></tr>')
            sec.append('</table>')
        if ctx.opt('notes', True):
            notes = []
            for pid in (f['FatherID'], f['MotherID'], *kids):
                p = row(ctx.con, 'SELECT Note FROM PersonTable WHERE PersonID=?', pid) if pid else None
                if p and p['Note'] and not ctx.living_hidden(pid):
                    notes.append(f'<p><b>{ctx.name(pid)}</b>: {m.note_to_html(p["Note"])}</p>')
            if f['Note']:
                notes.append(f'<p><b>Family</b>: {m.note_to_html(f["Note"])}</p>')
            if notes:
                sec.append('<h3>Notes</h3>' + ''.join(notes))
        sec.append('</div>')
        out.append(''.join(sec))
    return ''.join(out) + ctx.endnotes_html()


@report('rptIndividualSummary', 'Forms', 'Individual Summary', 'A summary of information for a person in your file',
        [OPT_PERSON, OPT_SOURCES, OPT_NOTES, {'key': 'family', 'type': 'bool', 'label': 'Include family members', 'default': True}] + OPT_PRIV)
def r_indiv(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Individual Summary: {m.person_name(ctx.con, pid)}'
    out = []
    ph = m.primary_photo(ctx.con, pid)
    if ph:
        out.append(f'<img class="photo" style="float:right" src="/api/media/{ph["MediaID"]}/file">')
    p = row(ctx.con, 'SELECT * FROM PersonTable WHERE PersonID=?', pid)
    out.append(f'<table class="plain"><tr><th>Name</th><td>{ctx.name(pid, "full")}{ctx.cite(0, pid)}</td></tr>'
               f'<tr><th>Sex</th><td>{m.SEX.get(p["Sex"], "")}</td></tr>'
               f'<tr><th>Record #</th><td>{pid}</td></tr></table>')
    alts = rows(ctx.con, 'SELECT * FROM NameTable WHERE OwnerID=? AND IsPrimary=0', pid)
    if alts:
        out.append('<h3>Alternate names</h3><ul>' + ''.join(
            f'<li>{E(m.fmt_name(n, "full"))} {E(m.NAME_TYPES.get(n["NameType"], ""))}{ctx.cite(7, n["NameID"])}</li>' for n in alts) + '</ul>')
    out.append(f'<h3>Facts</h3><table><tr><th>Fact</th><th>Date</th><th>Place / description</th></tr>{_fact_rows(ctx, "person", pid)}</table>')
    if ctx.opt('family', True):
        fa, mo, _ = m.primary_parents(ctx.con, pid)
        out.append(f'<h3>Parents</h3><p>Father: {ctx.name(fa)} <span class="life">{ctx.life(fa)}</span><br>'
                   f'Mother: {ctx.name(mo)} <span class="life">{ctx.life(mo)}</span></p>')
        for f in m.spouse_families(ctx.con, pid):
            mar = m.first_event(ctx.con, f['FamilyID'], (300,), owner=1)
            out.append(f'<h3>Spouse: {ctx.name(f["spouse"])} <span class="life">{ctx.life(f["spouse"])}</span></h3>')
            if mar:
                out.append(f'<p>Married {ctx.date(mar["Date"])} {E(m.place_name(ctx.con, mar["PlaceID"]))}</p>')
            kids = m.children_of(ctx.con, f['FamilyID'])
            if kids:
                out.append('<ol>' + ''.join(f'<li>{ctx.name(c)} <span class="life">{ctx.life(c)}</span></li>' for c in kids) + '</ol>')
    if ctx.opt('notes', True) and p['Note']:
        out.append(f'<h3>Notes</h3><p>{m.note_to_html(p["Note"])}</p>')
    return ''.join(out) + ctx.endnotes_html()


@report('rptScrapbook', 'Forms', 'Scrapbook', 'Photos for a person, family, etc.',
        [OPT_PERSON, {'key': 'includeFacts', 'type': 'bool', 'label': "Include media on the person's facts", 'default': True}])
def r_scrapbook(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Scrapbook: {m.person_name(ctx.con, pid)}'
    owners = [(0, pid)]
    if ctx.opt('includeFacts', True):
        owners += [(2, f['id']) for f in ctx.facts('person', pid)]
        owners += [(1, f['FamilyID']) for f in m.spouse_families(ctx.con, pid)]
    out = ['<div class="scrap">']
    seen = set()
    for ot, oid in owners:
        for mm in rows(ctx.con, '''SELECT mm.*, l.Comments FROM MediaLinkTable l JOIN MultimediaTable mm ON mm.MediaID=l.MediaID
                                   WHERE l.OwnerType=? AND l.OwnerID=? ORDER BY l.SortOrder''', ot, oid):
            if mm['MediaID'] in seen:
                continue
            seen.add(mm['MediaID'])
            img = f'<img src="/api/media/{mm["MediaID"]}/file">' if mm['MediaType'] == 1 else f'<div class="muted">[{E(m.MEDIA_TYPES.get(mm["MediaType"], "File"))}: {E(mm["MediaFile"] or mm["URL"] or "")}]</div>'
            out.append(f'<figure>{img}<figcaption><b>{E(mm["Caption"] or "")}</b><br>{ctx.date(mm["Date"])} '
                       f'{E(m.strip_tags(mm["Description"] or ""))}</figcaption></figure>')
    out.append('</div>')
    return ''.join(out) if seen else '<p>No media is attached to this person.</p>'


@report('rptPhotograph', 'Forms', 'A photograph', 'Print a single photo with its caption',
        [{'key': 'media', 'type': 'media', 'label': 'Media item'}])
def r_photograph(ctx):
    mm = row(ctx.con, 'SELECT * FROM MultimediaTable WHERE MediaID=?', int(ctx.opt('media')))
    if not mm:
        return '<p>Media item not found.</p>'
    ctx.title = mm['Caption'] or 'Photograph'
    return (f'<div style="text-align:center"><img style="max-width:100%;max-height:80vh" src="/api/media/{mm["MediaID"]}/file">'
            f'<p>{ctx.date(mm["Date"])}</p><p>{m.note_to_html(mm["Description"] or "")}</p></div>')


@report('rptCalendar', 'Forms', 'Calendar', 'A calendar with birthdays and anniversaries',
        [{'key': 'year', 'type': 'int', 'label': 'Year', 'default': datetime.date.today().year},
         {'key': 'livingOnly', 'type': 'bool', 'label': 'Living people only', 'default': True},
         {'key': 'anniversaries', 'type': 'bool', 'label': 'Include anniversaries', 'default': True},
         {'key': 'deaths', 'type': 'bool', 'label': 'Include death anniversaries', 'default': False}, OPT_WHO])
def r_calendar(ctx):
    year = int(ctx.opt('year', datetime.date.today().year))
    ctx.title = f'Calendar {year}'
    events = _anniversaries(ctx, year)
    out = []
    for mo in range(1, 13):
        out.append(f'<div class="cal"><h3>{calendar.month_name[mo]} {year}</h3><table><tr>' +
                   ''.join(f'<th>{d}</th>' for d in ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')) + '</tr>')
        for week in calendar.Calendar(6).monthdayscalendar(year, mo):
            out.append('<tr>' + ''.join(
                f'<td><b>{d}</b><br>{"<br>".join(E(x) for x in events.get((mo, d), []))}</td>' if d else '<td></td>'
                for d in week) + '</tr>')
        out.append('</table></div>')
    return ''.join(out)


def _anniversaries(ctx, year):
    ids = set(ctx.people())
    out = {}
    for e in rows(ctx.con, "SELECT * FROM EventTable WHERE EventType IN (1,2,300) AND Date LIKE 'D.+%' "
                           "AND substr(Date,8,2)<>'00' AND substr(Date,10,2)<>'00'"):
        y, mo, d = rmdate.ymd(e['Date'])
        if e['EventType'] == 1 and e['OwnerType'] == 0 and e['OwnerID'] in ids:
            if ctx.opt('livingOnly', True) and not (row(ctx.con, 'SELECT Living FROM PersonTable WHERE PersonID=?', e['OwnerID']) or {}).get('Living'):
                continue
            out.setdefault((mo, d), []).append(f"{m.person_name(ctx.con, e['OwnerID'])} ({year - y})")
        elif e['EventType'] == 300 and ctx.opt('anniversaries', True):
            f = row(ctx.con, 'SELECT * FROM FamilyTable WHERE FamilyID=?', e['OwnerID'])
            if f and (f['FatherID'] in ids or f['MotherID'] in ids):
                if ctx.opt('livingOnly', True) and m.first_event(ctx.con, f['FatherID'], (2,)) or ctx.opt('livingOnly', True) and m.first_event(ctx.con, f['MotherID'], (2,)):
                    continue
                out.setdefault((mo, d), []).append(f"♥ {m.couple_name(ctx.con, f)} ({year - y})")
        elif e['EventType'] == 2 and ctx.opt('deaths') and e['OwnerID'] in ids:
            out.setdefault((mo, d), []).append(f"† {m.person_name(ctx.con, e['OwnerID'])}")
    return out


@report('rptHealthHistory', 'Forms', 'Family Health History', 'A family health history for a person in your file',
        [OPT_PERSON, OPT_GENS(3, 6)])
def r_health_history(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Family Health History for {m.person_name(ctx.con, pid)}'
    anc = tools.ancestors(ctx.con, pid, int(ctx.opt('generations', 3)))
    people = list(anc.values()) + m.siblings_of(ctx.con, pid)
    out = ['<table><tr><th>Relationship</th><th>Person</th><th>Born</th><th>Died (cause)</th><th>Conditions</th></tr>']
    for p in people:
        rel = tools.relationships(ctx.con, pid, p)
        d = ctx.death(p)
        cause = d['Details'] if d and d['Details'] else ''
        conds = rows(ctx.con, 'SELECT * FROM HealthTable WHERE OwnerID=?', p)
        ctext = '; '.join(E(m.HEALTH_CONDITIONS[c['Condition']] if 0 <= (c['Condition'] or 0) < len(m.HEALTH_CONDITIONS) else 'Other') +
                          (f' ({E(c["SubCondition"])})' if c['SubCondition'] else '') for c in conds)
        b = ctx.birth(p)
        out.append(f'<tr><td>{E(rel[0]["name"] if rel else "")}</td><td>{ctx.name(p)}</td><td>{ctx.date(b["Date"]) if b else ""}</td>'
                   f'<td>{ctx.date(d["Date"]) if d else ""} {E(cause)}</td><td>{ctext}</td></tr>')
    return ''.join(out) + '</table>'


@report('rptRelateCalc', 'Forms', 'Relationship Calculator', 'A list of ways 2 people are related',
        [OPT_PERSON, {'key': 'person2', 'type': 'person', 'label': 'Second person'}])
def r_relcalc(ctx):
    a, b = int(ctx.opt('person')), int(ctx.opt('person2'))
    ctx.title = 'Relationship Calculator'
    rels = tools.relationships(ctx.con, a, b)
    if not rels:
        return f'<p>{ctx.name(b)} is not related to {ctx.name(a)}.</p>'
    out = [f'<p>{ctx.name(b)} is related to {ctx.name(a)} as:</p><ul>']
    for r in rels:
        via = ' and '.join(ctx.name(x) for x in r['ancestors'])
        out.append(f'<li><b>{E(r["name"])}</b>' + (f' — common ancestor(s): {via}' if via else '') + '</li>')
    return ''.join(out) + '</ul>'


@report('rptProblemList', 'Forms', 'Problem List', 'A list of potential problems', [])
def r_problems(ctx):
    probs = tools.problem_list(ctx.con)
    out = ['<table><tr><th>Person</th><th>Problem</th></tr>']
    for p in probs:
        out.append(f'<tr><td>{E(p["person"]["name"])} <span class="life">[{p["person"]["id"]}]</span></td><td>{E(p["problem"])}</td></tr>')
    return ''.join(out) + '</table>' + f'<p>{len(probs)} problems found.</p>'


@report('rptLeedsReport', 'Forms', 'Leeds Method Report', 'Leeds Method of DNA Color Clustering',
        [OPT_PERSON, {'key': 'minCM', 'type': 'int', 'label': 'Minimum shared cM', 'default': 90},
         {'key': 'maxCM', 'type': 'int', 'label': 'Maximum shared cM', 'default': 400}])
def r_leeds(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Leeds Method Report for {m.person_name(ctx.con, pid)}'
    lo, hi = float(ctx.opt('minCM', 90)), float(ctx.opt('maxCM', 400))
    matches = rows(ctx.con, 'SELECT * FROM DNATable WHERE (ID1=? OR ID2=?) AND SharedCM BETWEEN ? AND ? ORDER BY SharedCM DESC', pid, pid, lo, hi)
    if not matches:
        return '<p>No DNA matches in that cM range. Add matches on the DNA tab of Edit Person.</p>'
    # cluster: matches that share a common ancestor recorded (CommonAnc) get the same color; otherwise greedy by shared match lists
    palette = ['#f8d7da', '#d1e7dd', '#cfe2ff', '#fff3cd', '#e2d9f3', '#d2f4ea', '#ffe5d0', '#e9ecef']
    clusters = {}
    out = ['<table><tr><th>Match</th><th>Shared cM</th><th>Segments</th><th>Relationship</th><th>Cluster</th></tr>']
    for mt in matches:
        other = mt['ID2'] if mt['ID1'] == pid else mt['ID1']
        key = mt['CommonAnc'] or ('?' + str(other))
        if key not in clusters:
            clusters[key] = palette[len(clusters) % len(palette)]
        label = m.person_name(ctx.con, mt['CommonAnc']) if mt['CommonAnc'] else 'unassigned'
        rel = tools.relationships(ctx.con, pid, other)
        out.append(f'<tr style="background:{clusters[key]}"><td>{ctx.name(other) or E(mt["Label2"] or "")}</td><td>{mt["SharedCM"]:.0f}</td>'
                   f'<td>{mt["SharedSegs"] or ""}</td><td>{E(rel[0]["name"]) if rel else ""}</td><td>{E(label)}</td></tr>')
    return ''.join(out) + '</table>'


@report('rptGenericList', 'Forms', 'List Report', 'A simple list of the people in the current view or group',
        [OPT_WHO, {'key': 'columns', 'type': 'text', 'label': 'Columns (comma separated: id,name,sex,birth,death,living)',
                   'default': 'id,name,birth,death'}] + OPT_PRIV)
def r_generic(ctx):
    cols = [c.strip() for c in ctx.opt('columns', 'id,name,birth,death').split(',') if c.strip()]
    out = ['<table><tr>' + ''.join(f'<th>{E(c.title())}</th>' for c in cols) + '</tr>']
    for p in ctx.sorted_people(ctx.people()):
        s = m.person_summary(ctx.con, p, ctx.s)
        cell = {'id': str(p), 'name': ctx.name(p), 'sex': m.SEX.get(s['sex'], ''), 'living': 'Yes' if s['living'] else '',
                'birth': '' if ctx.living_hidden(p) else E(_fb(s['birth'])), 'death': E(_fb(s['death']))}
        out.append('<tr>' + ''.join(f'<td>{cell.get(c, "")}</td>' for c in cols) + '</tr>')
    return ''.join(out) + '</table>'


def _fb(f):
    return ', '.join(x for x in (f['date'], f['place']) if x) if f else ''


# ============================================================== narratives
def person_narrative(ctx, pid, number=None, first=True):
    """Paragraph(s) describing a person: facts as sentences, with endnote refs."""
    if ctx.living_hidden(pid):
        return f'<p>{ctx.name(pid)} is living.</p>'
    sentences = []
    for i, f in enumerate(ctx.facts('person', pid)):
        s = m.fact_sentence(ctx.con, f['id'], ctx.s, subject=pid, first_mention=(i == 0))
        if s:
            sentences.append(s.rstrip('.') + '.' + ctx.cite(2, f['id']))
    if not sentences:
        sentences.append(f'{ctx.name(pid)}.')
    text = ' '.join(sentences)
    fa, mo, _ = m.primary_parents(ctx.con, pid)
    if fa or mo:
        sex = (row(ctx.con, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid) or {}).get('Sex', 2)
        word = {0: 'son', 1: 'daughter'}.get(sex, 'child')
        text += f' {m.PRONOUNS[sex][0].capitalize()} was the {word} of {" and ".join(ctx.name(x) for x in (fa, mo) if x)}.'
    for f in m.spouse_families(ctx.con, pid):
        mar = m.first_event(ctx.con, f['FamilyID'], (300,), owner=1)
        if mar:
            text += ' ' + m.fact_sentence(ctx.con, mar['EventID'], ctx.s, first_mention=True) + ctx.cite(2, mar['EventID'])
        elif f['spouse']:
            text += f' {ctx.name(pid)} was married to {ctx.name(f["spouse"])}.'
        if f['spouse']:
            ctx.idx(f['spouse'], number or '')
    out = f'<p>{text}</p>'
    if ctx.opt('notes', True):
        p = row(ctx.con, 'SELECT Note FROM PersonTable WHERE PersonID=?', pid)
        if p and p['Note']:
            out += f'<p class="muted">{m.note_to_html(p["Note"])}</p>'
    return out


def spouse_paragraph(ctx, spouse, where):
    if not spouse or ctx.living_hidden(spouse):
        return ''
    ctx.idx(spouse, where)
    b = ctx.birth(spouse)
    d = ctx.death(spouse)
    bits = []
    if b:
        bits.append(m.fact_sentence(ctx.con, b['EventID'], ctx.s, subject=spouse))
    if d:
        bits.append(m.fact_sentence(ctx.con, d['EventID'], ctx.s, subject=spouse, first_mention=not b))
    fa, mo, _ = m.primary_parents(ctx.con, spouse)
    if fa or mo:
        bits.append(f'{ctx.name(spouse)} was the child of {" and ".join(ctx.name(x) for x in (fa, mo) if x)}.')
    return f'<p class="muted">{" ".join(bits)}</p>' if bits else ''


ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii',
         'xviii', 'xix', 'xx']


@report('rptNarrativeReport', 'Narratives', 'Narrative Report',
        'A narrative ancestor or descendant genealogy where the program writes the sentences for you.',
        [OPT_PERSON, OPT_GENS(4, 30),
         {'key': 'style', 'type': 'select', 'label': 'Style', 'default': 'register',
          'choices': [['register', 'Descendants — Register (NEHGS)'], ['ngsq', 'Descendants — NGSQ'],
                      ['ancestors', 'Ancestors — Ahnentafel narrative']]},
         OPT_SOURCES, OPT_NOTES, {'key': 'index', 'type': 'bool', 'label': 'Include index', 'default': True},
         {'key': 'spouseDetails', 'type': 'bool', 'label': 'Include spouse details', 'default': True}] + OPT_PRIV)
def r_narrative(ctx):
    pid = int(ctx.opt('person'))
    gens = int(ctx.opt('generations', 4))
    style = ctx.opt('style', 'register')
    out = []
    if style == 'ancestors':
        ctx.title = f'Ancestors of {m.person_name(ctx.con, pid)}'
        anc = tools.ancestors(ctx.con, pid, gens)
        for g in range(gens):
            nums = [n for n in sorted(anc) if 2 ** g <= n < 2 ** (g + 1)]
            if not nums:
                break
            out.append(f'<h2 class="gen">Generation {g + 1}</h2>')
            for n in nums:
                p = anc[n]
                ctx.idx(p, n)
                out.append(f'<div class="person-block"><b>{n}. {ctx.name(p)}</b>{ctx.cite(0, p)}' + person_narrative(ctx, p, n) + '</div>')
                if n % 2 == 0 and n + 1 not in anc and ctx.opt('spouseDetails', True):
                    pass
        return ''.join(out) + ctx.endnotes_html() + ctx.index_html()
    ctx.title = f'Descendants of {m.person_name(ctx.con, pid)}'
    numbers = {pid: 1}
    counter = [1]
    queue = [(pid, 1)]
    by_gen = {}
    while queue:
        p, g = queue.pop(0)
        by_gen.setdefault(g, []).append(p)
        if g >= gens:
            continue
        for f in m.spouse_families(ctx.con, p):
            for c in m.children_of(ctx.con, f['FamilyID']):
                has_desc = g + 1 < gens and any(m.children_of(ctx.con, sf['FamilyID']) for sf in m.spouse_families(ctx.con, c))
                if c in numbers:
                    continue
                if style == 'ngsq' or has_desc:
                    counter[0] += 1
                    numbers[c] = counter[0]
                if has_desc:
                    queue.append((c, g + 1))
    for g in sorted(by_gen):
        out.append(f'<h2 class="gen">Generation {g}</h2>')
        for p in by_gen[g]:
            n = numbers[p]
            ctx.idx(p, n)
            out.append(f'<div class="person-block"><b>{n}. {ctx.name(p)}</b>{ctx.cite(0, p)}' + person_narrative(ctx, p, n))
            for f in m.spouse_families(ctx.con, p):
                if ctx.opt('spouseDetails', True):
                    out.append(spouse_paragraph(ctx, f['spouse'], n))
                kids = m.children_of(ctx.con, f['FamilyID'])
                if not kids:
                    continue
                parents = ' and '.join(ctx.name(x) for x in (p, f['spouse']) if x)
                out.append(f'<p>Children of {parents}:</p><table class="children">')
                for i, c in enumerate(kids):
                    ctx.idx(c, n)
                    num = numbers.get(c)
                    plus = '+' if num and any(c == q for q in by_gen.get(g + 1, [])) else ''
                    life = ctx.life(c)
                    out.append(f'<tr><td>{plus}</td><td>{num or ""}</td><td>{ROMAN[i] if i < len(ROMAN) else i + 1}.</td>'
                               f'<td>{ctx.name(c)} <span class="life">{life}</span></td></tr>')
                out.append('</table>')
            out.append('</div>')
    return ''.join(out) + ctx.endnotes_html() + ctx.index_html()


# ============================================================== lists
def _table(headers, data):
    return ('<table><tr>' + ''.join(f'<th>{E(h)}</th>' for h in headers) + '</tr>' +
            ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in data) + '</table>')


@report('rptAhnentafel', 'Lists', 'Ahnentafel', 'A list of ancestors', [OPT_PERSON, OPT_GENS(6, 40), OPT_SOURCES] + OPT_PRIV)
def r_ahnentafel(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Ahnentafel of {m.person_name(ctx.con, pid)}'
    anc = tools.ancestors(ctx.con, pid, int(ctx.opt('generations', 6)))
    out, gen = [], -1
    for n in sorted(anc):
        g = n.bit_length() - 1
        if g != gen:
            gen = g
            out.append(f'<h3>Generation {g + 1}</h3>')
        p = anc[n]
        bits = []
        for label, types in (('born', (1, 3)), ('died', (2,)), ('buried', (4,))):
            e = m.first_event(ctx.con, p, types)
            if e and not ctx.living_hidden(p):
                bits.append(f'{label} {ctx.date(e["Date"])} {E(m.place_name(ctx.con, e["PlaceID"]))}{ctx.cite(2, e["EventID"])}'.strip())
        if n % 2 == 0:
            for f in m.spouse_families(ctx.con, p):
                if f['spouse'] == anc.get(n + 1):
                    mar = m.first_event(ctx.con, f['FamilyID'], (300,), owner=1)
                    if mar:
                        bits.append(f'married {ctx.date(mar["Date"])} {E(m.place_name(ctx.con, mar["PlaceID"]))}'.strip())
        out.append(f'<p><b>{n}.</b> {ctx.name(p)}' + ('; ' + '; '.join(bits) if bits else '') + '.</p>')
        ctx.idx(p, n)
    return ''.join(out) + ctx.endnotes_html()


@report('rptDescendantList', 'Lists', 'Descendant List', 'An indented list of descendants of a person',
        [OPT_PERSON, OPT_GENS(6, 40), {'key': 'spouses', 'type': 'bool', 'label': 'Include spouses', 'default': True}] + OPT_PRIV)
def r_desc_list(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Descendants of {m.person_name(ctx.con, pid)}'
    out = [f'<div><b>1 {ctx.name(pid)}</b> <span class="life">{ctx.life(pid)}</span></div>']
    gens = int(ctx.opt('generations', 6))

    def walk(p, g):
        for f in m.spouse_families(ctx.con, p):
            if ctx.opt('spouses', True) and f['spouse']:
                out.append(f'<div style="margin-left:{(g - 1) * 22 + 10}px">+ {ctx.name(f["spouse"])} <span class="life">{ctx.life(f["spouse"])}</span></div>')
            if g >= gens:
                continue
            for c in m.children_of(ctx.con, f['FamilyID']):
                out.append(f'<div style="margin-left:{g * 22}px">{g + 1} {ctx.name(c)} <span class="life">{ctx.life(c)}</span></div>')
                walk(c, g + 1)
    walk(pid, 1)
    return ''.join(out)


@report('rptIndividualList', 'Lists', 'Individual List', 'A list of the people in your file',
        [OPT_WHO, {'key': 'showIds', 'type': 'bool', 'label': 'Show record numbers', 'default': True}] + OPT_PRIV)
def r_indiv_list(ctx):
    data = []
    for p in ctx.sorted_people(ctx.people()):
        s = m.person_summary(ctx.con, p, ctx.s)
        hide = ctx.living_hidden(p)
        data.append(([str(p)] if ctx.opt('showIds', True) else []) +
                    [ctx.name(p), m.SEX.get(s['sex'], ''), '' if hide else E(_fb(s['birth'])), '' if hide else E(_fb(s['death']))])
    return _table((['#'] if ctx.opt('showIds', True) else []) + ['Name', 'Sex', 'Birth', 'Death'], data) + f'<p>{len(data)} people</p>'


@report('rptMarriageList', 'Lists', 'Marriage List', 'A list of couples in your file', [OPT_WHO] + OPT_PRIV)
def r_marriage_list(ctx):
    ids = set(ctx.people())
    data = []
    for f in rows(ctx.con, 'SELECT * FROM FamilyTable'):
        if not (f['FatherID'] in ids or f['MotherID'] in ids):
            continue
        mar = m.first_event(ctx.con, f['FamilyID'], (300,), owner=1)
        hide = ctx.living_hidden(f['FatherID']) or ctx.living_hidden(f['MotherID'])
        data.append((m.primary_name(ctx.con, f['FatherID']).get('Surname', '') if f['FatherID'] else '',
                     [ctx.name(f['FatherID']), ctx.name(f['MotherID']),
                      '' if hide or not mar else ctx.date(mar['Date']), '' if hide or not mar else E(m.place_name(ctx.con, mar['PlaceID']))]))
    data.sort(key=lambda t: (t[0].lower(), t[1][0]))
    return _table(['Husband', 'Wife', 'Marriage date', 'Place'], [d for _, d in data])


@report('rptFactList', 'Lists', 'Fact List', 'A list of facts',
        [OPT_WHO, {'key': 'factTypes', 'type': 'facttypes', 'label': 'Fact types (blank = all)'},
         {'key': 'sort', 'type': 'select', 'label': 'Sort by', 'default': 'name',
          'choices': [['name', 'Name'], ['date', 'Date'], ['place', 'Place']]}, OPT_SOURCES] + OPT_PRIV)
def r_fact_list(ctx):
    ids = set(ctx.people())
    types = {int(x) for x in str(ctx.opt('factTypes', '')).split(',') if x.strip().isdigit()}
    data = []
    for e in rows(ctx.con, 'SELECT * FROM EventTable WHERE OwnerType=0'):
        if e['OwnerID'] not in ids or (types and e['EventType'] not in types) or ctx.living_hidden(e['OwnerID']):
            continue
        if e['IsPrivate'] and not ctx.opt('includePrivate'):
            continue
        ft = m.fact_type(ctx.con, e['EventType']) or {}
        pl = m.place_name(ctx.con, e['PlaceID'])
        data.append(((m.primary_name(ctx.con, e['OwnerID']).get('Surname', '') or '').lower(), e['SortDate'], pl,
                     [ctx.name(e['OwnerID']), E(ft.get('Name', '')), ctx.date(e['Date']), E(pl), E(e['Details'] or '') + ctx.cite(2, e['EventID'])]))
    key = {'name': lambda t: (t[0], t[3][0]), 'date': lambda t: t[1], 'place': lambda t: t[2]}[ctx.opt('sort', 'name')]
    data.sort(key=key)
    return _table(['Person', 'Fact', 'Date', 'Place', 'Description'], [d[3] for d in data]) + ctx.endnotes_html()


@report('rptPlaceList', 'Lists', 'Place List', 'A list of places and the events in those places',
        [{'key': 'events', 'type': 'bool', 'label': 'List events at each place', 'default': True},
         {'key': 'reverse', 'type': 'bool', 'label': 'Sort by reversed place name', 'default': False}] + OPT_PRIV)
def r_place_list(ctx):
    order = 'Reverse' if ctx.opt('reverse') else 'Name'
    out = []
    for p in rows(ctx.con, f'SELECT * FROM PlaceTable WHERE PlaceType=0 ORDER BY {order} COLLATE RMNOCASE'):
        evs = rows(ctx.con, 'SELECT * FROM EventTable WHERE PlaceID=? ORDER BY SortDate', p['PlaceID'])
        if not evs:
            continue
        name = p['Reverse'] if ctx.opt('reverse') else p['Name']
        coords = f' <span class="muted">({p["Latitude"] / 1e7:.4f}, {p["Longitude"] / 1e7:.4f})</span>' if p['Latitude'] or p['Longitude'] else ''
        out.append(f'<h3>{E(name)}{coords}</h3>')
        if ctx.opt('events', True):
            data = []
            for e in evs:
                if e['OwnerType'] == 0 and ctx.living_hidden(e['OwnerID']):
                    continue
                ft = m.fact_type(ctx.con, e['EventType']) or {}
                data.append([E(m.event_owner_name(ctx.con, e)), E(ft.get('Name', '')), ctx.date(e['Date']), E(m.place_name(ctx.con, e['SiteID']))])
            out.append(_table(['Person', 'Fact', 'Date', 'Place detail'], data))
    return ''.join(out)


@report('rptSourceList', 'Lists', 'Source List', 'A list of sources and their citations',
        [{'key': 'citations', 'type': 'bool', 'label': 'Include citations and what they cite', 'default': True}])
def r_source_list(ctx):
    out = []
    for s in rows(ctx.con, 'SELECT * FROM SourceTable ORDER BY Name COLLATE RMNOCASE'):
        out.append(f'<h3>{E(s["Name"])}</h3><p>{m.render_source_text(ctx.con, s, None, "Bibliography")}</p>')
        if s['ActualText']:
            out.append(f'<p class="muted">{m.note_to_html(s["ActualText"])}</p>')
        if ctx.opt('citations', True):
            data = []
            for c in rows(ctx.con, 'SELECT * FROM CitationTable WHERE SourceID=?', s['SourceID']):
                users = rows(ctx.con, 'SELECT OwnerType, OwnerID FROM CitationLinkTable WHERE CitationID=?', c['CitationID'])
                data.append([m.render_citation(ctx.con, c['CitationID']),
                             '<br>'.join(E(m.citation_owner_label(ctx.con, u['OwnerType'], u['OwnerID'])) for u in users)])
            if data:
                out.append(_table(['Citation', 'Used by'], data))
    return ''.join(out)


@report('rptRepositoryList', 'Lists', 'Repository List', 'A list of repositories and the sources in them', [])
def r_repo_list(ctx):
    out = []
    for a in rows(ctx.con, 'SELECT * FROM AddressTable WHERE AddressType=1 ORDER BY Name COLLATE RMNOCASE'):
        out.append(f'<h3>{E(a["Name"])}</h3><p>{_addr_html(a)}</p>')
        srcs = rows(ctx.con, '''SELECT s.Name, l.Details FROM AddressLinkTable l JOIN SourceTable s ON s.SourceID=l.OwnerID
                               WHERE l.OwnerType=3 AND l.AddressID=?''', a['AddressID'])
        if srcs:
            out.append('<ul>' + ''.join(f'<li>{E(s["Name"])}{" — call no. " + E(s["Details"]) if s["Details"] else ""}</li>' for s in srcs) + '</ul>')
    return ''.join(out) or '<p>No repositories.</p>'


def _addr_html(a):
    lines = [a.get('Street1'), a.get('Street2'), ' '.join(x for x in (a.get('City'), a.get('State'), a.get('Zip')) if x),
             a.get('Country'), a.get('Phone1') and 'Phone: ' + a['Phone1'], a.get('Email') and 'Email: ' + a['Email'],
             a.get('URL') and 'Website: ' + a['URL']]
    return '<br>'.join(E(x) for x in lines if x)


@report('rptAddressList', 'Lists', 'Address List', 'A list of the addresses in your file', [])
def r_address_list(ctx):
    data = [[E(a['Name']), _addr_html(a)] for a in rows(ctx.con, 'SELECT * FROM AddressTable WHERE AddressType=0 ORDER BY Name COLLATE RMNOCASE')]
    return _table(['Name', 'Address'], data)


@report('rptAddressLabels', 'Labels', 'Address Labels', 'Labels for addresses in your file', [])
def r_labels(ctx):
    out = ['<div class="labels">']
    for a in rows(ctx.con, 'SELECT * FROM AddressTable WHERE AddressType=0 ORDER BY Name COLLATE RMNOCASE'):
        lines = [a['Name'], a['Street1'], a['Street2'], ' '.join(x for x in (a['City'], a['State'], a['Zip']) if x), a['Country']]
        out.append('<div class="label">' + '<br>'.join(E(x) for x in lines if x) + '</div>')
    return ''.join(out) + '</div>'


@report('rptBirthdayList', 'Lists', 'Birthday and Anniversary List', 'A list of birthdays and anniversaries for people in your file',
        [{'key': 'livingOnly', 'type': 'bool', 'label': 'Living people only', 'default': True},
         {'key': 'anniversaries', 'type': 'bool', 'label': 'Include anniversaries', 'default': True}, OPT_WHO])
def r_birthdays(ctx):
    year = datetime.date.today().year
    ev = _anniversaries(ctx, year)
    out = []
    for mo in range(1, 13):
        days = sorted((d, x) for (mm, d), xs in ev.items() if mm == mo for x in xs)
        if days:
            out.append(f'<h3>{calendar.month_name[mo]}</h3>' + _table(['Day', 'Who (age/years in ' + str(year) + ')'],
                                                                    [[str(d), E(x)] for d, x in days]))
    return ''.join(out) or '<p>No dated birthdays found.</p>'


@report('rptCountTrees', 'Lists', 'Count Trees List', 'A list of the separate trees in your file', [])
def r_count_trees(ctx):
    trees = tools.count_trees(ctx.con)
    return _table(['Tree', 'People', 'Starting person'], [[str(i), str(t['size']), E(t['start']['name'])] for i, t in enumerate(trees, 1)])


@report('rptDuplicateList', 'Lists', 'Duplicate List', 'A list of possible duplicate people in your file',
        [{'key': 'minScore', 'type': 'int', 'label': 'Minimum match score', 'default': 60}])
def r_dup_list(ctx):
    d = tools.find_duplicates(ctx.con, int(ctx.opt('minScore', 60)))
    return _table(['Score', 'Person 1', 'Person 2'], [[str(x['score']), f"{E(x['a']['name'])} [{x['a']['id']}] {E(_fb(x['a']['birth']))}",
                                                       f"{E(x['b']['name'])} [{x['b']['id']}] {E(_fb(x['b']['birth']))}"] for x in d])


@report('rptKinshipList', 'Lists', 'Kinship List', 'A list of everyone related to an individual', [OPT_PERSON] + OPT_PRIV)
def r_kinship(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Kinship List for {m.person_name(ctx.con, pid)}'
    k = tools.kinship_list(ctx.con, pid)
    k.sort(key=lambda r: (r['person']['surname'].lower(), r['person']['given'].lower()))
    return _table(['Name', 'Life', 'Relationship'], [[ctx.name(r['person']['id']), ctx.life(r['person']['id']), E(r['relationship'])] for r in k])


@report('rptMissingInfoList', 'Lists', 'Missing Info List', 'A list of people missing information',
        [OPT_WHO, {'key': 'missing', 'type': 'select', 'label': 'List people missing', 'default': '1',
                   'choices': [['1', 'Birth'], ['2', 'Death'], ['300', 'Marriage'], ['4', 'Burial'], ['sources', 'Any source'],
                               ['parents', 'Parents'], ['place', 'Birth place']]}])
def r_missing(ctx):
    what = str(ctx.opt('missing', '1'))
    data = []
    for p in ctx.sorted_people(ctx.people()):
        miss = False
        if what == 'sources':
            miss = not row(ctx.con, '''SELECT 1 AS x FROM CitationLinkTable WHERE (OwnerType=0 AND OwnerID=?) OR
                                      (OwnerType=2 AND OwnerID IN (SELECT EventID FROM EventTable WHERE OwnerType=0 AND OwnerID=?))''', p, p)
        elif what == 'parents':
            miss = not m.parents_of(ctx.con, p)
        elif what == 'place':
            b = m.first_event(ctx.con, p, (1,))
            miss = not b or not b['PlaceID']
        elif what == '300':
            fams = m.spouse_families(ctx.con, p)
            miss = bool(fams) and not any(m.first_event(ctx.con, f['FamilyID'], (300,), owner=1) for f in fams)
        else:
            miss = not m.first_event(ctx.con, p, (int(what),))
        if miss:
            data.append([str(p), ctx.name(p), ctx.life(p)])
    return _table(['#', 'Name', 'Life'], data) + f'<p>{len(data)} people</p>'


@report('rptMultimediaList', 'Lists', 'Multimedia List', 'A list of the media in your file',
        [{'key': 'links', 'type': 'bool', 'label': 'Show what each item is linked to', 'default': True}])
def r_media_list(ctx):
    data = []
    for mm in rows(ctx.con, 'SELECT * FROM MultimediaTable ORDER BY Caption COLLATE RMNOCASE'):
        links = rows(ctx.con, 'SELECT OwnerType, OwnerID FROM MediaLinkTable WHERE MediaID=?', mm['MediaID'])
        data.append([E(mm['Caption'] or ''), E(mm['MediaFile'] or mm['URL'] or ''), ctx.date(mm['Date']),
                     '<br>'.join(E(m.citation_owner_label(ctx.con, l['OwnerType'], l['OwnerID']) or _owner_misc(ctx.con, l['OwnerType'], l['OwnerID'])) for l in links) if ctx.opt('links', True) else ''])
    return _table(['Caption', 'File', 'Date', 'Linked to'], data)


def _owner_misc(con, ot, oid):
    if ot == 3:
        s = row(con, 'SELECT Name FROM SourceTable WHERE SourceID=?', oid)
        return 'Source: ' + s['Name'] if s else ''
    if ot == 4:
        return 'Citation'
    if ot == 5:
        return 'Place: ' + m.place_name(con, oid)
    return ''


@report('rptOnThisDay', 'Lists', 'On This Day List', 'A list of events on a particular date',
        [{'key': 'month', 'type': 'int', 'label': 'Month', 'default': datetime.date.today().month, 'min': 1, 'max': 12},
         {'key': 'day', 'type': 'int', 'label': 'Day', 'default': datetime.date.today().day, 'min': 1, 'max': 31}])
def r_on_this_day(ctx):
    mo, d = int(ctx.opt('month', 1)), int(ctx.opt('day', 1))
    ctx.title = f'On This Day: {d} {calendar.month_name[mo]}'
    ev = tools.on_this_day(ctx.con, mo, d)
    return _table(['Year', 'Event', 'Who', 'Place'], [[str(e['year']), E(e['fact']), E(e['who']), E(e['place'])] for e in ev]) \
        if ev else '<p>No events in your file on this day.</p>'


@report('rptStatisticsList', 'Lists', 'Statistics List', 'A report of various statistics for your file', [])
def r_stats(ctx):
    st = tools.statistics(ctx.con)
    labels = {'people': 'People', 'males': 'Males', 'females': 'Females', 'unknownSex': 'Unknown sex', 'living': 'Living',
              'families': 'Families', 'events': 'Facts/events', 'places': 'Places', 'sources': 'Sources',
              'citations': 'Citations', 'repositories': 'Repositories', 'media': 'Media items', 'tasks': 'Tasks',
              'surnames': 'Distinct surnames', 'addresses': 'Addresses', 'associations': 'Associations',
              'averageLifespan': 'Average lifespan (years)', 'oldestAge': 'Oldest age at death',
              'earliestYear': 'Earliest year', 'latestYear': 'Latest year'}
    return _table(['Statistic', 'Value'], [[E(labels.get(k, k)), E(str(v if v is not None else ''))] for k, v in st.items()])


@report('rptSurnameStatistics', 'Lists', 'Surname Statistics', 'Statistics on the surnames in your file', [])
def r_surname_stats(ctx):
    return _table(['Surname', 'Total', 'Male', 'Female', 'Earliest', 'Latest'],
                  [[E(r['surname'] or '(none)'), str(r['total']), str(r['male']), str(r['female']), str(r['first'] or ''), str(r['last'] or '')]
                   for r in tools.surname_statistics(ctx.con)])


@report('rptTimelineList', 'Lists', 'Timeline List', 'A chronological timeline of events for a person or group of people.',
        [OPT_WHO, {'key': 'family', 'type': 'bool', 'label': 'Include family events of these people', 'default': True}] + OPT_PRIV)
def r_timeline(ctx):
    ids = set(ctx.people())
    evs = []
    for e in rows(ctx.con, "SELECT * FROM EventTable WHERE Date LIKE 'D%'"):
        if e['OwnerType'] == 0 and e['OwnerID'] in ids and not ctx.living_hidden(e['OwnerID']):
            evs.append(e)
        elif e['OwnerType'] == 1 and ctx.opt('family', True):
            f = row(ctx.con, 'SELECT FatherID, MotherID FROM FamilyTable WHERE FamilyID=?', e['OwnerID'])
            if f and (f['FatherID'] in ids or f['MotherID'] in ids):
                evs.append(e)
    evs.sort(key=lambda e: e['SortDate'])
    data = []
    for e in evs:
        ft = m.fact_type(ctx.con, e['EventType']) or {}
        age = ''
        if e['OwnerType'] == 0:
            b = ctx.birth(e['OwnerID'])
            age = rmdate.age_text(b['Date'], e['Date']) if b and b['EventID'] != e['EventID'] else ''
        data.append([ctx.date(e['Date']), E(ft.get('Name', '')), E(m.event_owner_name(ctx.con, e)), E(age), E(m.place_name(ctx.con, e['PlaceID']))])
    return _table(['Date', 'Event', 'Who', 'Age', 'Place'], data)


@report('rptWebTagsList', 'Lists', 'WebTags List', 'A list of WebTags in your file', [])
def r_webtags(ctx):
    data = []
    for u in rows(ctx.con, 'SELECT * FROM URLTable ORDER BY Name'):
        owner = m.citation_owner_label(ctx.con, u['OwnerType'], u['OwnerID']) or _owner_misc(ctx.con, u['OwnerType'], u['OwnerID'])
        data.append([E(owner), E(u['Name'] or ''), f'<a href="{E(m.safe_url(u["URL"]))}">{E(u["URL"] or "")}</a>'])
    return _table(['Owner', 'Name', 'URL'], data)


@report('rptWhoWasThereList', 'Lists', 'Who Was There List', 'A list of people who could have been in a particular location at a particular time',
        [{'key': 'place', 'type': 'text', 'label': 'Place contains', 'default': ''},
         {'key': 'from', 'type': 'int', 'label': 'From year', 'default': 1850},
         {'key': 'to', 'type': 'int', 'label': 'To year', 'default': 1900}])
def r_who_was_there(ctx):
    ps = tools.who_was_there(ctx.con, ctx.opt('place', ''), int(ctx.opt('from', 1850)), int(ctx.opt('to', 1900)))
    ctx.subtitle = f"{ctx.opt('place', '')} between {ctx.opt('from')} and {ctx.opt('to')}"
    return _table(['Name', 'Life'], [[E(p['name']), E(ctx.life(p['id']))] for p in ps])


@report('rptTaskList', 'Lists', 'Task List', 'A list of research tasks',
        [{'key': 'status', 'type': 'select', 'label': 'Status', 'default': 'open',
          'choices': [['all', 'All'], ['open', 'Open / in progress'], ['done', 'Completed']]}])
def r_tasks(ctx):
    st = ctx.opt('status', 'open')
    where = {'all': '', 'open': 'WHERE Status IN (0,1)', 'done': 'WHERE Status=2'}[st]
    data = []
    for t in rows(ctx.con, f'SELECT * FROM TaskTable {where} ORDER BY Priority, Name COLLATE RMNOCASE'):
        links = rows(ctx.con, 'SELECT OwnerType, OwnerID FROM TaskLinkTable WHERE TaskID=?', t['TaskID'])
        data.append([E(t['Name'] or ''), E(m.TASK_STATUS.get(t['Status'], '')), E(m.PRIORITY.get(t['Priority'], '')),
                     ctx.date(t['Date1']), '<br>'.join(E(m.citation_owner_label(ctx.con, l['OwnerType'], l['OwnerID']) or _owner_misc(ctx.con, l['OwnerType'], l['OwnerID'])) for l in links),
                     m.note_to_html(t['Details'] or '')])
    return _table(['Task', 'Status', 'Priority', 'Start', 'For', 'Details'], data)


@report('rptResearchLog', 'Lists', 'Research Log', 'Research log entries (tasks of type research log)', [])
def r_research_log(ctx):
    data = []
    for t in rows(ctx.con, 'SELECT * FROM TaskTable WHERE TaskType=1 ORDER BY SortDate1'):
        data.append([ctx.date(t['Date1']), E(t['Name'] or ''), m.note_to_html(t['Details'] or ''), m.note_to_html(t['Results'] or '')])
    return _table(['Date', 'Goal / source searched', 'Details', 'Results'], data)


@report('rptResearchNotes', 'Lists', 'Research Notes', 'All notes for a person: person, facts, names, and citations', [OPT_PERSON])
def r_research_notes(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Research Notes: {m.person_name(ctx.con, pid)}'
    out = []
    p = row(ctx.con, 'SELECT Note FROM PersonTable WHERE PersonID=?', pid)
    if p['Note']:
        out.append(f'<h3>General</h3><p>{m.note_to_html(p["Note"])}</p>')
    for f in m.facts_for(ctx.con, 'person', pid, ctx.s, False):
        if f['note']:
            out.append(f'<h3>{E(f["typeName"])} {E(f["date"])}</h3><p>{m.note_to_html(f["note"])}</p>')
        for c in m.citations_for(ctx.con, 2, f['id']):
            cc = row(ctx.con, 'SELECT Comments FROM CitationTable WHERE CitationID=?', c['CitationID'])
            if cc and cc['Comments']:
                out.append(f'<p class="muted"><b>Citation ({E(c["SourceName"] or "")})</b>: {m.note_to_html(cc["Comments"])}</p>')
    return ''.join(out) or '<p>No notes.</p>'


@report('rptFanList', 'Lists', 'Association List (Individual)', 'An indented list of associations (friends, neighbors, etc) of a person',
        [OPT_PERSON, {'key': 'depth', 'type': 'int', 'label': 'Levels', 'default': 2, 'min': 1, 'max': 5}])
def r_fan_list(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'Associations of {m.person_name(ctx.con, pid)}'
    out, seen = [], {pid}

    def walk(p, lvl):
        for a in rows(ctx.con, '''SELECT f.*, t.Name AS TypeName, t.Role1, t.Role2 FROM FANTable f
                                 LEFT JOIN FANTypeTable t ON t.FANTypeID=f.FanTypeID WHERE f.ID1=? OR f.ID2=?''', p, p):
            other = a['ID2'] if a['ID1'] == p else a['ID1']
            role = a['Role2'] if a['ID1'] == p else a['Role1']
            out.append(f'<div style="margin-left:{lvl * 22}px">{ctx.name(other)} — {E(role or a["TypeName"] or "")}'
                       f'{" (" + ctx.date(a["Date"]) + ")" if a["Date"] and a["Date"] != "." else ""}</div>')
            if other not in seen and lvl < int(ctx.opt('depth', 2)):
                seen.add(other)
                walk(other, lvl + 1)
    walk(pid, 0)
    return ''.join(out) or '<p>No associations.</p>'


@report('rptFanRelationship', 'Lists', 'Association List (Relationship)', 'A detailed report showing the association between 2 people',
        [OPT_PERSON, {'key': 'person2', 'type': 'person', 'label': 'Second person'}])
def r_fan_rel(ctx):
    a, b = int(ctx.opt('person')), int(ctx.opt('person2'))
    # BFS over associations
    prev, q = {a: None}, [a]
    while q:
        p = q.pop(0)
        if p == b:
            break
        for f in rows(ctx.con, 'SELECT * FROM FANTable WHERE ID1=? OR ID2=?', p, p):
            o = f['ID2'] if f['ID1'] == p else f['ID1']
            if o not in prev:
                prev[o] = (p, f)
                q.append(o)
    if b not in prev:
        return '<p>No chain of associations connects these people.</p>'
    chain, cur = [], b
    while prev[cur]:
        p, f = prev[cur]
        t = row(ctx.con, 'SELECT * FROM FANTypeTable WHERE FANTypeID=?', f['FanTypeID']) or {}
        chain.append(f'<li>{ctx.name(p)} → {ctx.name(cur)}: {E(t.get("Name", "association"))} {ctx.date(f["Date"])}<br>'
                     f'<span class="muted">{m.note_to_html(f["Note"] or "")}</span></li>')
        cur = p
    return '<ol>' + ''.join(reversed(chain)) + '</ol>'


@report('rptHealthCondition', 'Lists', 'Health Conditions List', 'A list of health conditions for a group of people', [OPT_WHO])
def r_health_list(ctx):
    ids = set(ctx.people())
    data = []
    for h in rows(ctx.con, 'SELECT * FROM HealthTable ORDER BY Condition'):
        if h['OwnerID'] in ids:
            cond = m.HEALTH_CONDITIONS[h['Condition']] if 0 <= (h['Condition'] or 0) < len(m.HEALTH_CONDITIONS) else 'Other'
            data.append([E(cond), E(h['SubCondition'] or ''), ctx.name(h['OwnerID']), m.note_to_html(h['Note'] or '')])
    return _table(['Condition', 'Detail', 'Person', 'Note'], data) or '<p>No health conditions recorded.</p>'


@report('rptDNATestList', 'Lists', 'DNA Kinship List', 'A list of DNA matches and predicted relationships for a person', [OPT_PERSON])
def r_dna_list(ctx):
    pid = int(ctx.opt('person'))
    ctx.title = f'DNA Matches for {m.person_name(ctx.con, pid)}'
    data = []
    for d in rows(ctx.con, 'SELECT * FROM DNATable WHERE ID1=? OR ID2=? ORDER BY SharedCM DESC', pid, pid):
        other = d['ID2'] if d['ID1'] == pid else d['ID1']
        rel = tools.relationships(ctx.con, pid, other)
        data.append([ctx.name(other), f'{d["SharedCM"] or 0:.1f}', f'{d["SharedPercent"] or 0:.2f}%', str(d['SharedSegs'] or ''),
                     f'{d["LargeSeg"] or 0:.1f}', E(rel[0]['name'] if rel else ''), E(predict_relationship(d['SharedCM'] or 0)),
                     E(m.DNA_PROVIDERS.get(d['DNAProvider'], ''))])
    return _table(['Match', 'Shared cM', '%', 'Segments', 'Largest', 'Known relationship', 'Predicted', 'Company'], data)


SHARED_CM = [(3400, 'parent/child'), (2300, 'full sibling'), (1300, 'grandparent, aunt/uncle, half sibling'),
             (575, 'first cousin, great-grandparent'), (215, 'first cousin once removed'), (75, 'second cousin'),
             (35, 'second cousin once removed / third cousin'), (15, 'third to fourth cousin'), (0, 'distant cousin')]


def predict_relationship(cm):
    """Rough shared-cM bands (Shared cM Project averages)."""
    for lo, label in SHARED_CM:
        if cm >= lo:
            return label
    return ''


@report('rptLDSList', 'Lists', 'LDS List', 'A list of LDS ordinances in your file', [OPT_WHO])
def r_lds(ctx):
    ids = set(ctx.people())
    data = []
    for e in rows(ctx.con, 'SELECT * FROM EventTable WHERE EventType IN (31,32,33,38,39,309) ORDER BY SortDate'):
        if e['OwnerType'] == 0 and e['OwnerID'] not in ids:
            continue
        ft = m.fact_type(ctx.con, e['EventType']) or {}
        data.append([E(m.event_owner_name(ctx.con, e)), E(ft.get('Name', '')), ctx.date(e['Date']), E(m.place_name(ctx.con, e['PlaceID'])), E(e['Details'] or '')])
    return _table(['Person', 'Ordinance', 'Date', 'Temple', 'Status'], data)


@report('rptCountyCheck', 'Lists', 'CountyCheck', 'Check place names for possible problems (county/state structure)', [])
def r_county_check(ctx):
    issues = tools.place_issues(ctx.con)
    data = [[E(i['name']), E(i['issue']), E(i['suggestion'])] for i in issues]
    for p in rows(ctx.con, 'SELECT * FROM PlaceTable WHERE PlaceType=0 ORDER BY Name'):
        parts = [x.strip() for x in (p['Name'] or '').split(',')]
        if parts and parts[-1] in ('USA', 'United States') and len(parts) < 4 and not parts[0].lower().endswith(('county', 'co.')):
            data.append([E(p['Name']), 'US place without city, county, state, country levels', ''])
    return _table(['Place', 'Issue', 'Suggestion'], data) if data else '<p>No issues found.</p>'


@report('rptCustomReport', 'Reports', 'Custom Report', 'A custom report where you define the fields, sort order, etc',
        [OPT_WHO, {'key': 'fields', 'type': 'text', 'label': 'Fields (id,name,surname,given,sex,birth,birthdate,birthplace,death,deathdate,deathplace,'
                                                            'father,mother,spouse,living,age,occupation,note)',
                   'default': 'id,name,birthdate,birthplace,deathdate,deathplace'},
         {'key': 'sortBy', 'type': 'text', 'label': 'Sort by field', 'default': 'surname'},
         {'key': 'filter', 'type': 'text', 'label': 'Only rows where a field contains (field=text)', 'default': ''}] + OPT_PRIV)
def r_custom(ctx):
    fields = [f.strip() for f in ctx.opt('fields', '').split(',') if f.strip()]
    rows_ = []
    flt = ctx.opt('filter', '')
    fk, _, fv = flt.partition('=')
    for p in ctx.people():
        rows_.append(custom_fields(ctx, p))
    if fk and fv:
        rows_ = [r for r in rows_ if fv.lower() in str(r.get(fk.strip(), '')).lower()]
    sk = ctx.opt('sortBy', 'surname')
    rows_.sort(key=lambda r: str(r.get(sk, '')).lower())
    return _table(fields, [[E(str(r.get(f, ''))) for f in fields] for r in rows_]) + f'<p>{len(rows_)} rows</p>'


def custom_fields(ctx, p):
    s = m.person_summary(ctx.con, p, ctx.s)
    hide = ctx.living_hidden(p)
    fa, mo, _ = m.primary_parents(ctx.con, p)
    sp = [f['spouse'] for f in m.spouse_families(ctx.con, p) if f['spouse']]
    occ = m.first_event(ctx.con, p, (26,))
    b, d = ctx.birth(p), ctx.death(p)
    age = rmdate.age_text(b['Date'], d['Date']) if b and d else ''
    return {'id': p, 'name': m.strip_tags(ctx.name(p)), 'surname': s['surname'], 'given': '' if hide else s['given'],
            'sex': m.SEX.get(s['sex'], ''), 'birth': '' if hide else _fb(s['birth']),
            'birthdate': '' if hide or not s['birth'] else s['birth']['date'], 'birthplace': '' if hide or not s['birth'] else s['birth']['place'],
            'death': _fb(s['death']), 'deathdate': s['death']['date'] if s['death'] else '', 'deathplace': s['death']['place'] if s['death'] else '',
            'father': m.person_name(ctx.con, fa), 'mother': m.person_name(ctx.con, mo),
            'spouse': '; '.join(m.person_name(ctx.con, x) for x in sp), 'living': 'Yes' if s['living'] else '',
            'age': age, 'occupation': (occ['Details'] if occ else '') if not hide else '',
            'note': '' if hide else m.strip_tags((row(ctx.con, 'SELECT Note FROM PersonTable WHERE PersonID=?', p) or {}).get('Note') or '')[:200]}
