"""Genealogical dates in the RootsMagic .rmtree encoding.

Date column: 24-char string, or 'T<text>' for unparseable text, '.' / '' for empty.
  [0]    'D'
  [1]    modifier   . none  B bef  A aft  F from  T to  R bet..and  S from..to
                    I since  U until  O or
  [2]    '+' AD / '-' BC
  [3:11] YYYYMMDD   (00 = unknown part)
  [11]   '/' double-date (1750/51) else '.'
  [12]   qualifier  . none  A abt  C circa  E est  L calc  ? maybe  P perhaps
                    Y apparently  K likely  O possibly  R probably  T certainly
                    1-4 quarter
  [13:24] second date for ranges, same layout as [2:13]

ponytail: the layout and SortDate packing follow community documentation of the
RM format, not verified against RootsMagic's own codec (Hopper was blocked).
Our own files round-trip exactly; RM-written single dates decode the same way.
"""
import re
from dataclasses import dataclass, field

EMPTY_SORT = 9223372036854775807
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']
MONTH_ABBR = {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)}
MONTH_ABBR.update({'sept': 9})

QUALIFIERS = {  # code -> (display word, accepted input words)
    'A': ('abt', ['abt', 'about', 'around', 'approx']),
    'C': ('ca', ['circa', 'circ', 'ca', 'c']),
    'E': ('est', ['est', 'estimated', 'estimate']),
    'L': ('calc', ['calc', 'cal', 'calculated', 'calculate']),
    '?': ('maybe', ['maybe']),
    'P': ('perhaps', ['perhaps', 'prhps']),
    'Y': ('apparently', ['apparently', 'apparent', 'appar']),
    'K': ('likely', ['likely', 'lkly']),
    'O': ('possibly', ['possibly', 'possible', 'poss']),
    'R': ('probably', ['probably', 'probable', 'prob']),
    'T': ('certainly', ['certainly', 'certain', 'cert']),
}
QUAL_WORDS = {w: c for c, (_, ws) in QUALIFIERS.items() for w in ws}
MODIFIERS = {  # single-date modifiers
    'B': ('bef', ['bef', 'before', 'by']),
    'A': ('aft', ['aft', 'after']),
    'F': ('from', ['from']),
    'T': ('to', ['to', 'through', 'thru']),
    'I': ('since', ['since']),
    'U': ('until', ['until', 'untl', 'till']),
}
MOD_WORDS = {w: c for c, (_, ws) in MODIFIERS.items() for w in ws}


@dataclass
class Part:
    year: int = 0
    month: int = 0
    day: int = 0
    bc: bool = False
    double: bool = False      # 1750/51 style
    qual: str = '.'

    def empty(self):
        return not (self.year or self.month or self.day)


@dataclass
class GDate:
    kind: str = ''            # '' empty, 'D' date, 'T' text
    mod: str = '.'
    p1: Part = field(default_factory=Part)
    p2: Part = field(default_factory=Part)
    text: str = ''

    @property
    def is_range(self):
        return self.mod in ('R', 'S', 'O')


def _valid(p):
    return p.month <= 12 and p.day <= 31 and not (p.day and not p.month)


def _parse_part(s):
    """Parse '12 Jan 1850', 'Jan 1850', '1850', '1850/51', 'Q2 1850', '1850-01-12', '12/1/1850'."""
    p = Part()
    words = s.strip().lower().replace(',', ' ').split()
    while words and words[0].rstrip('.') in QUAL_WORDS:
        p.qual = QUAL_WORDS[words.pop(0).rstrip('.')]
    if words and words[-1] in ('bc', 'b.c.', 'bce'):
        p.bc = True
        words.pop()
    if words and words[-1] in ('ad', 'a.d.', 'ce'):
        words.pop()
    if words and re.fullmatch(r'q[1-4]', words[0]):
        p.qual = words.pop(0)[1]
        p.month = (int(p.qual) - 1) * 3 + 1
    s = ' '.join(words).strip('.')
    if not s:
        return None
    m = re.fullmatch(r'(\d{3,4})-(\d{1,2})(?:-(\d{1,2}))?', s)
    if m:  # ISO
        p.year, p.month, p.day = int(m[1]), int(m[2]), int(m[3] or 0)
        return p if _valid(p) else None
    m = re.fullmatch(r'(\d{1,2})[/.](\d{1,2})[/.](\d{3,4})', s)
    if m:  # day/month/year
        p.day, p.month, p.year = int(m[1]), int(m[2]), int(m[3])
        return p if _valid(p) else None
    for t in s.split():
        t = t.strip('.')
        md = re.fullmatch(r'(\d{1,4})(?:/(\d{1,2}))?', t)
        mm = MONTH_ABBR.get(t[:4]) or MONTH_ABBR.get(t[:3])
        if t.isalpha() and mm:
            if p.month and p.qual not in '1234':
                return None
            p.month = mm
        elif md:
            n = int(md[1])
            if md[2] or n > 31 or len(md[1]) >= 3 or (p.day and not p.year):
                if p.year:
                    return None
                p.year, p.double = n, bool(md[2])
            elif not p.day and not p.year:
                p.day = n
            else:
                return None
        elif re.fullmatch(r'\d{1,2}(st|nd|rd|th)', t) and not p.day:
            p.day = int(t[:-2])
        else:
            return None
    if p.day and not p.year and not p.month:  # bare small number = year
        p.year, p.day = p.day, 0
    return p if _valid(p) else None


def parse(s):
    """Free text -> GDate. Unparseable text becomes a text date."""
    s = (s or '').strip()
    if not s or s == '.':
        return GDate()
    if is_encoded(s):
        return decode(s)
    low = s.lower()
    patterns = (
        (r'(?:bet|betw|between)\.?\s+(.+?)\s+(?:and|&)\s+(.+)', 'R'),
        (r'from\s+(.+?)\s+(?:to|until|thru|through)\s+(.+)', 'S'),
        (r'(.+?)\s+(?:-|to)\s+(.+)', 'S'),
        (r'(.+?)\s+or\s+(.+)', 'O'),
    )
    for rx, mod in patterns:
        m = re.fullmatch(rx, low)
        if m:
            a, b = _parse_part(m[1]), _parse_part(m[2])
            if a and b:
                return GDate(kind='D', mod=mod, p1=a, p2=b)
    g = GDate(kind='D')
    first, _, rest = s.partition(' ')
    if first.lower().rstrip('.') in MOD_WORDS and rest:
        g.mod = MOD_WORDS[first.lower().rstrip('.')]
    else:
        rest = s
    p = _parse_part(rest)
    if p is None:
        return GDate(kind='T', text=s)
    g.p1 = p
    return g


def _enc_part(p):
    return '%s%04d%02d%02d%s%s' % ('-' if p.bc else '+', p.year, p.month, p.day,
                                  '/' if p.double else '.', p.qual)


def encode(g):
    """GDate or free text -> RM Date column string."""
    if isinstance(g, str):
        g = parse(g)
    if g.kind == '':
        return '.'
    if g.kind == 'T':
        return 'T' + g.text
    return 'D' + g.mod + _enc_part(g.p1) + _enc_part(g.p2 if g.is_range else Part())


def is_encoded(s):
    return bool(re.fullmatch(r'D[.A-Z][+-]\d{8}[./][.A-Z?1-9][+-]\d{8}[./][.A-Z?1-9]', s or ''))


def _dec_part(s):
    return Part(year=int(s[1:5]), month=int(s[5:7]), day=int(s[7:9]), bc=s[0] == '-',
                double=s[9] == '/', qual=s[10])


def decode(s):
    """RM Date column string -> GDate (plain text is parsed as user input)."""
    s = s or ''
    if not s or s == '.':
        return GDate()
    if is_encoded(s):
        return GDate(kind='D', mod=s[1], p1=_dec_part(s[2:13]), p2=_dec_part(s[13:24]))
    if s[0] == 'T':
        return GDate(kind='T', text=s[1:])
    return parse(s)


def sort_date(g):
    """64-bit sort key: (Y1+10000)<<49 | M1<<45 | D1<<39 | second-date/flag bits."""
    if isinstance(g, str):
        g = decode(g)
    if g.kind != 'D' or g.p1.empty():
        return EMPTY_SORT
    p = g.p1
    y = -p.year if p.bc else p.year
    key = ((y + 10000) << 49) | (p.month << 45) | (p.day << 39)
    if g.is_range and not g.p2.empty():
        q = g.p2
        y2 = -q.year if q.bc else q.year
        key |= ((y2 + 10000) << 20) | (q.month << 16) | (q.day << 10)
    else:
        key |= (0x3FFF << 20) | {'B': 4, 'U': 8, 'I': 16, 'A': 20}.get(g.mod, 12)
    return key


# ---------------------------------------------------------------- formatting
def _mon(m, full=False, upper=False):
    s = MONTHS[m - 1] if full else MONTHS[m - 1][:3]
    return s.upper() if upper else s


FORMATS = {  # setting key -> (label, fn(day, month, yearstr))
    'dmy': ('12 Jan 1850', lambda d, m, y: ' '.join(x for x in (d and str(d), m and _mon(m), y) if x)),
    'dMy': ('12 January 1850', lambda d, m, y: ' '.join(x for x in (d and str(d), m and _mon(m, True), y) if x)),
    'dmyU': ('12 JAN 1850', lambda d, m, y: ' '.join(x for x in (d and str(d), m and _mon(m, upper=True), y) if x)),
    'mdy': ('Jan 12, 1850', lambda d, m, y: (m and _mon(m) + ' ' or '') + (d and f'{d}, ' or '') + y),
    'Mdy': ('January 12, 1850', lambda d, m, y: (m and _mon(m, True) + ' ' or '') + (d and f'{d}, ' or '') + y),
    'iso': ('1850-01-12', lambda d, m, y: y + (m and f'-{m:02d}' or '') + (d and f'-{d:02d}' or '')),
    'dmy.': ('12.01.1850', lambda d, m, y: (d and f'{d:02d}.' or '') + (m and f'{m:02d}.' or '') + y),
}


def _fmt_part(p, fmt):
    if p.empty():
        return ''
    y = str(p.year) if p.year else ''
    if p.double and p.year:
        y += '/%02d' % ((p.year + 1) % 100)
    if p.bc:
        y += ' BC'
    if p.qual in '1234':
        return f'Q{p.qual} {y}'
    s = FORMATS.get(fmt, FORMATS['dmy'])[1](p.day, p.month, y)
    if p.qual in QUALIFIERS:
        s = QUALIFIERS[p.qual][0] + ' ' + s
    return s


def format(value, fmt='dmy'):
    g = value if isinstance(value, GDate) else decode(value)
    if g.kind == '':
        return ''
    if g.kind == 'T':
        return g.text
    a = _fmt_part(g.p1, fmt)
    if g.mod == 'R':
        return f'bet {a} and {_fmt_part(g.p2, fmt)}'
    if g.mod == 'S':
        return f'from {a} to {_fmt_part(g.p2, fmt)}'
    if g.mod == 'O':
        return f'{a} or {_fmt_part(g.p2, fmt)}'
    if g.mod in MODIFIERS:
        return MODIFIERS[g.mod][0] + ' ' + a
    return a


SENTENCE_WORDS = {'abt': 'about', 'bef': 'before', 'aft': 'after', 'bet': 'between',
                  'est': 'estimated', 'calc': 'calculated', 'ca': 'circa'}


def sentence_form(value, fmt='dmy'):
    """Date as used inside narrative sentences: 'on 12 Jan 1850', 'in 1850', 'about 1850'."""
    g = value if isinstance(value, GDate) else decode(value)
    if g.kind == '':
        return ''
    if g.kind == 'T':
        return g.text
    s = format(g, fmt)
    head, _, tail = s.partition(' ')
    if head in SENTENCE_WORDS:
        return SENTENCE_WORDS[head] + ' ' + tail.replace(' and abt ', ' and about ')
    if g.mod == '.' and g.p1.qual == '.':
        return ('on ' if g.p1.day else 'in ') + s
    return s


def ymd(value):
    g = value if isinstance(value, GDate) else decode(value)
    if g.kind != 'D' or not g.p1.year:
        return None
    return (-g.p1.year if g.p1.bc else g.p1.year, g.p1.month, g.p1.day)


def year(value):
    t = ymd(value)
    return t[0] if t else 0


def age_between(d1, d2):
    """Age in (years, months, days) from d1 to d2; None if unknown or negative."""
    a, b = ymd(d1), ymd(d2)
    if not a or not b:
        return None
    y, m, d = b[0] - a[0], (b[1] or 1) - (a[1] or 1), (b[2] or 1) - (a[2] or 1)
    if d < 0:
        m, d = m - 1, d + 30
    if m < 0:
        y, m = y - 1, m + 12
    return (y, m, d) if y >= 0 else None


def age_text(d1, d2):
    a = age_between(d1, d2)
    if not a:
        return ''
    y, m, d = a
    if y:
        return str(y)
    if m:
        return f'{m} month' + ('s' if m > 1 else '')
    return f'{d} day' + ('s' if d != 1 else '')


if __name__ == '__main__':
    cases = {
        '12 Jan 1850': 'D.+18500112..+00000000..',
        'Jan 12, 1850': 'D.+18500112..+00000000..',
        'abt 1850': 'D.+18500000.A+00000000..',
        'bef Mar 1850': 'DB+18500300..+00000000..',
        'bet 1850 and 1860': 'DR+18500000..+18600000..',
        'from 1850 to 1860': 'DS+18500000..+18600000..',
        '1850 - 1860': 'DS+18500000..+18600000..',
        '1750/51': 'D.+17500000/.+00000000..',
        'Q2 1850': 'D.+18500400.2+00000000..',
        '1850-01-12': 'D.+18500112..+00000000..',
        'Christmas 1850': 'TChristmas 1850',
        '': '.',
    }
    for txt, enc in cases.items():
        assert encode(txt) == enc, (txt, encode(txt), enc)
        assert encode(decode(enc)) == enc, enc
    assert format('D.+18500112..+00000000..') == '12 Jan 1850'
    assert format('D.+18500112..+00000000..', 'Mdy') == 'January 12, 1850'
    assert format('DR+18500000..+18600000..') == 'bet 1850 and 1860'
    assert sort_date(encode('12 Jan 1850')) < sort_date(encode('13 Jan 1850')) < sort_date(encode('1851'))
    assert sort_date(encode('bef 1850')) < sort_date(encode('1850')) < sort_date(encode('aft 1850'))
    assert sort_date('') == EMPTY_SORT
    assert sort_date(encode('100 BC')) < sort_date(encode('1 AD'))
    assert age_text(encode('12 Jan 1850'), encode('11 Jan 1900')) == '49'
    assert sentence_form(encode('12 Jan 1850')) == 'on 12 Jan 1850'
    assert sentence_form(encode('abt 1850')) == 'about 1850'
    print('rmdate ok')
