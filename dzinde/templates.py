"""Template language used by fact sentences and source templates.

  [Field] / [Field:Mod]      value from the resolver
  <text [Field] text>        optional group: dropped if any field directly inside is empty
  <?[Field]|then|else>       conditional on Field being non-empty (else part optional)
  <#Var#singular|plural>     resolver('#Var') truthy -> plural
  <i> </i> <b> <u> <sup>...  literal HTML, passed through
"""
import re

HTML_TAG = re.compile(r'</?(?:i|b|u|sup|sub|br|em|strong)\s*/?>', re.I)


def _parse(s, i, stop):
    """Parse until a char in `stop` at this nesting level. Returns (nodes, index)."""
    nodes, buf = [], []
    while i < len(s):
        c = s[i]
        if c in stop:
            break
        if c == '<':
            m = HTML_TAG.match(s, i)
            if m:
                buf.append(m.group())
                i = m.end()
                continue
            if buf:
                nodes.append(''.join(buf))
                buf = []
            if s.startswith('<?', i):
                cond, i = _parse(s, i + 2, '|>')
                then, els = [], []
                if i < len(s) and s[i] == '|':
                    then, i = _parse(s, i + 1, '|>')
                    if i < len(s) and s[i] == '|':
                        els, i = _parse(s, i + 1, '>')
                nodes.append(('if', cond, then, els))
            elif s.startswith('<#', i):
                end = s.find('#', i + 2)
                var = s[i + 2:end]
                one, i = _parse(s, end + 1, '|>')
                many = []
                if i < len(s) and s[i] == '|':
                    many, i = _parse(s, i + 1, '>')
                nodes.append(('plural', var, one, many))
            else:
                inner, i = _parse(s, i + 1, '>')
                nodes.append(('group', inner))
            i += 1  # skip '>'
            continue
        if c == '[':
            end = s.find(']', i)
            if end < 0:
                buf.append(c)
                i += 1
                continue
            if buf:
                nodes.append(''.join(buf))
                buf = []
            name, _, mod = s[i + 1:end].partition(':')
            nodes.append(('field', name.strip(), mod.strip()))
            i = end + 1
            continue
        buf.append(c)
        i += 1
    if buf:
        nodes.append(''.join(buf))
    return nodes, i


_cache = {}


def compile(template):
    if template not in _cache:
        _cache[template] = _parse(template or '', 0, '')[0]
    return _cache[template]


def _eval(nodes, resolve):
    """Returns (text, all_fields_present)."""
    out, ok = [], True
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
        elif n[0] == 'field':
            v = resolve(n[1], n[2]) or ''
            ok = ok and bool(v.strip())
            out.append(v)
        elif n[0] == 'group':
            t, g_ok = _eval(n[1], resolve)
            if g_ok:
                out.append(t)
        elif n[0] == 'if':
            c, c_ok = _eval(n[1], resolve)
            t, _ = _eval(n[2] if c_ok and c.strip() else n[3], resolve)
            out.append(t)
        elif n[0] == 'plural':
            t, _ = _eval(n[3] if resolve('#' + n[1], '') else n[2], resolve)
            out.append(t)
    return ''.join(out), ok


def render(template, resolve):
    """Render template; resolve(name, modifier) -> str. Cleans doubled spaces/punctuation."""
    text, _ = _eval(compile(template), resolve)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\s+([.,;:])', r'\1', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\.\.+', '.', text)
    return text.strip()


def fields_in(template):
    return sorted({m.group(1) for m in re.finditer(r'\[([^\]:]+)', template or '')})


# ------------------------------------------------------------ value modifiers
def name_value(raw, mod=''):
    """Name field: 'John /van Durren/ Jr.' -> modifiers Full/Surname/Given/Reverse/Init."""
    raw = raw or ''
    m = re.match(r'\s*(.*?)\s*/(.*?)/\s*(.*)', raw)
    given, surname, suffix = (m[1], m[2], m[3]) if m else (' '.join(raw.split()[:-1]), (raw.split() or [''])[-1], '')
    if not raw.strip():
        return ''
    mod = mod.lower()
    if mod == 'surname':
        return surname
    if mod == 'given':
        return given
    if mod == 'reverse':
        return ', '.join(x for x in (surname, given) if x) + (f', {suffix}' if suffix else '')
    if mod in ('init', 'initials'):
        return ' '.join(w[0] + '.' for w in given.split()) + (' ' + surname if surname else '')
    return ' '.join(x for x in (given, surname, suffix) if x)


def article(word):
    if not word:
        return ''
    return ('an ' if word[0].lower() in 'aeiou' else 'a ') + word


def apply_text_mod(v, mod):
    """Generic modifiers for text values."""
    if not v:
        return ''
    mod_l = mod.lower()
    if '||' in v:  # 'long form||short form'
        long, short = v.split('||', 1)
        v = short if mod_l in ('abbrev', 'short') else long
    if mod_l == 'a':
        return article(v)
    if mod_l in ('caps', 'upper'):
        return v.upper()
    if mod_l == 'lower':
        return v.lower()
    if mod_l == 'cap':
        return v[:1].upper() + v[1:]
    return v


if __name__ == '__main__':
    vals = {'person': 'John Smith', 'Date': 'on 1 Jan 1850', 'Place': 'in Ohio', 'PlaceDetails': '', 'Desc': 'farmer'}

    def r(n, m):
        if n == '#Couple':
            return False
        v = vals.get(n, '')
        return article(v) if m == 'A' else v
    assert render('[person] was born< [Date]>< [PlaceDetails]>< [Place]>.', r) == 'John Smith was born on 1 Jan 1850 in Ohio.'
    assert render('[person] was [Desc:A]< [Missing]>.', r) == 'John Smith was a farmer.'
    assert render('[person] <#Couple#was|were> married.', r) == 'John Smith was married.'
    assert render('<i>Book</i><?[Desc]|, job [Desc]|, none>.', r) == '<i>Book</i>, job farmer.'
    assert render('<?[Nope]|x|y>', r) == 'y'
    assert render('<[Desc], <[Nope]>x>', r) == 'farmer, x'
    assert name_value('John /van Durren/ Jr.', 'Surname') == 'van Durren'
    assert name_value('John /van Durren/', 'Reverse') == 'van Durren, John'
    assert name_value('John Smith', '') == 'John Smith'
    assert fields_in('[A] <[B:Mod]>') == ['A', 'B']
    print('templates ok')
