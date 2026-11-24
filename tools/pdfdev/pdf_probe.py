# -*- coding: utf-8 -*-
"""极简 PDF 探针：抽文字（坐标/字号/颜色/字体）、矩形、线、图片 → layout JSON，
并可粗略渲染成 PNG 用肉眼核对排版。仅用标准库 + Pillow。"""
import re
import os
import sys
import zlib
import json

WS = b'\x00\t\n\x0c\r '
NUM = re.compile(rb'[-+]?[0-9]*\.?[0-9]+')
DELIM = b'()<>[]{}/%'


class Lexer:
    def __init__(self, data, i=0):
        self.d = data
        self.i = i

    def skip_ws(self):
        d, n = self.d, len(self.d)
        while self.i < n:
            c = d[self.i:self.i + 1]
            if c in (b' ', b'\n', b'\r', b'\t', b'\x00', b'\x0c'):
                self.i += 1
            elif c == b'%':
                while self.i < n and d[self.i:self.i + 1] not in (b'\n', b'\r'):
                    self.i += 1
            else:
                break

    def token(self):
        self.skip_ws()
        d, n = self.d, len(self.d)
        if self.i >= n:
            return ('eof', None)
        c = d[self.i:self.i + 1]
        if c == b'/':
            j = self.i + 1
            while j < n and d[j:j + 1] not in WS and d[j:j + 1] not in DELIM:
                j += 1
            name = d[self.i + 1:j].decode('latin-1')
            self.i = j
            return ('name', name)
        if c == b'(':
            self.i += 1
            depth = 1
            out = bytearray()
            while self.i < n:
                ch = d[self.i:self.i + 1]
                if ch == b'\\':
                    nxt = d[self.i + 1:self.i + 2]
                    mapping = {b'n': 10, b'r': 13, b't': 9, b'b': 8, b'f': 12,
                               b'(': 40, b')': 41, b'\\': 92}
                    if nxt in mapping:
                        out.append(mapping[nxt])
                        self.i += 2
                        continue
                    if nxt.isdigit():
                        oct_digits = b''
                        self.i += 1
                        while len(oct_digits) < 3 and d[self.i:self.i + 1].isdigit():
                            oct_digits += d[self.i:self.i + 1]
                            self.i += 1
                        try:
                            out.append(int(oct_digits, 8) & 0xFF)
                        except ValueError:
                            out += oct_digits
                        continue
                    self.i += 2
                    continue
                if ch == b'(':
                    depth += 1
                elif ch == b')':
                    depth -= 1
                    if depth == 0:
                        self.i += 1
                        break
                out += ch
                self.i += 1
            return ('str', bytes(out))
        if c == b'<':
            if d[self.i:self.i + 2] == b'<<':
                self.i += 2
                return ('op', '<<')
            j = d.find(b'>', self.i)
            if j < 0:
                j = n
            hexs = re.sub(rb'[^0-9A-Fa-f]', b'', d[self.i + 1:j])
            if len(hexs) % 2:
                hexs += b'0'
            self.i = j + 1
            return ('str', bytes.fromhex(hexs.decode()))
        if c == b'>':
            if d[self.i:self.i + 2] == b'>>':
                self.i += 2
                return ('op', '>>')
            self.i += 1
            return ('op', '>')
        if c in b'[]{}':
            self.i += 1
            return ('op', c.decode())
        m = NUM.match(d, self.i)
        if m:
            self.i = m.end()
            return ('num', float(m.group(0)))
        j = self.i
        while j < n and d[j:j + 1] not in WS and d[j:j + 1] not in DELIM:
            j += 1
        if j == self.i:
            j = self.i + 1
        op = d[self.i:j].decode('latin-1')
        self.i = j
        return ('op', op)


def tokenize(data):
    lex = Lexer(data)
    out = []
    while True:
        t = lex.token()
        if t[0] == 'eof':
            return out
        out.append(t)


def group(tokens, i):
    """从 i 开始读一个完整对象（字典/数组/简单值），返回 (value, next_i)。"""
    kind, val = tokens[i]
    if (kind, val) == ('op', '<<'):
        depth, k, items = 0, i, []
        while k < len(tokens):
            if tokens[k] == ('op', '<<'):
                depth += 1
            elif tokens[k] == ('op', '>>'):
                depth -= 1
                if depth == 0:
                    break
            items.append(tokens[k])
            k += 1
        inner = items[1:]
        out, cur = {}, 0
        while cur < len(inner):
            if inner[cur][0] == 'name':
                key = inner[cur][1]
                if cur + 1 < len(inner):
                    if inner[cur + 1] == ('op', '<<'):
                        sub = inner[cur + 1:len(inner)]
                        subval, used = group([('op', '<<')] + sub, 0)
                        out[key] = subval
                        c2, depth2 = 1, 0
                        kk = cur + 2
                        while kk < len(inner):
                            if inner[kk] == ('op', '<<'):
                                depth2 += 1
                            elif inner[kk] == ('op', '>>'):
                                depth2 -= 1
                                if depth2 == 0:
                                    break
                            kk += 1
                        cur = kk + 1
                        continue
                    if inner[cur + 1] == ('op', '['):
                        depth2, kk = 0, cur + 1
                        while kk < len(inner):
                            if inner[kk] == ('op', '['):
                                depth2 += 1
                            elif inner[kk] == ('op', ']'):
                                depth2 -= 1
                                if depth2 == 0:
                                    break
                            kk += 1
                        arr, _ = group(inner[cur + 1:kk + 1], 0)
                        out[key] = arr
                        cur = kk + 1
                        continue
                    if (inner[cur + 1][0] == 'num' and cur + 3 < len(inner)
                            and inner[cur + 2][0] == 'num' and inner[cur + 3] == ('op', 'R')):
                        out[key] = ('ref', (int(inner[cur + 1][1]), int(inner[cur + 2][1])))
                        cur += 4
                        continue
                    out[key] = inner[cur + 1]
                    cur += 2
                    continue
            cur += 1
        return out, k + 1
    if (kind, val) == ('op', '['):
        depth, k = 0, i
        while k < len(tokens):
            if tokens[k] == ('op', '['):
                depth += 1
            elif tokens[k] == ('op', ']'):
                depth -= 1
                if depth == 0:
                    break
            k += 1
        items, cur, out = tokens[i + 1:k], 0, []
        while cur < len(items):
            value, nxt = group(items, cur)
            out.append(value)
            cur = nxt
        return out, k + 1
    return val, i + 1


def normalize(value):
    """把词法层的 (kind, value) 元组压成普通 Python 值；保留 ref。"""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, tuple):
        if len(value) == 2 and value[0] == 'ref':
            return value
        if len(value) == 2 and value[0] in ('name', 'num', 'str'):
            return value[1] if value[0] != 'name' else value[1]
        return value
    return value


class Pdf:
    def __init__(self, path):
        self.raw = open(path, 'rb').read()
        self.objs = {}
        self.offsets = {}
        for m in re.finditer(rb'(?<![0-9])(\d+)\s+\d+\s+obj\b', self.raw):
            num = int(m.group(1))
            start = m.end()
            if num in self.objs:
                continue
            end = self.raw.find(b'endobj', start)
            self.offsets[num] = start
            self.objs[num] = self.raw[start:end if end > 0 else len(self.raw)]
        self._stream_cache = {}
        self._dict_cache = {}

    def _dict_bytes(self, num):
        body = self.objs.get(num, b'')
        idx = body.find(b'stream')
        return body if idx < 0 else body[:idx]

    def obj_dict(self, num):
        if num not in self._dict_cache:
            toks = tokenize(self._dict_bytes(num))
            if toks and toks[0] == ('op', '<<'):
                value, _ = group(toks, 0)
                self._dict_cache[num] = normalize(value)
            else:
                self._dict_cache[num] = {}
        return self._dict_cache[num]

    def stream(self, num):
        if num in self._stream_cache:
            return self._stream_cache[num]
        body = self.objs.get(num, b'')
        idx = body.find(b'stream')
        if idx < 0:
            self._stream_cache[num] = None
            return None
        head = body[:idx]
        d = self.obj_dict(num)
        length = d.get('Length')
        if isinstance(length, tuple) and length[0] == 'ref':
            target = self._dict_bytes(length[1][0]).strip()
            lm = re.search(rb'(\d+)\s*$', target)
            length = int(lm.group(1)) if lm else None
        elif isinstance(length, float):
            length = int(length)
        else:
            length = None
        base = self.offsets.get(num, 0)
        start = base + idx + 6
        while start < len(self.raw) and self.raw[start] in b'\r\n':
            start += 1
        if length and start + length <= len(self.raw):
            data = self.raw[start:start + length]
        else:
            end = self.raw.find(b'endstream', base + idx)
            data = self.raw[start:end if end > 0 else len(self.raw)]
        filters = d.get('Filter')
        if isinstance(filters, str):
            names = [filters]
        elif isinstance(filters, list):
            names = [f for f in filters if isinstance(f, str)]
        else:
            names = []
        for name in names:
            if name == 'FlateDecode':
                try:
                    data = zlib.decompress(data)
                except Exception:
                    try:
                        data = zlib.decompressobj().decompress(data)
                    except Exception:
                        data = b''
        self._stream_cache[num] = data
        return data

    def resolve(self, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, tuple) and value and value[0] == 'ref':
            return self.obj_dict(value[1][0])
        if isinstance(value, str):
            return {'name': value}
        if isinstance(value, float):
            return {'num': value}
        if isinstance(value, tuple):
            return {'ref': value[1]}
        return {}

    def resolved_num(self, value, default=0.0):
        if isinstance(value, float):
            return value
        if isinstance(value, tuple) and value and value[0] == 'ref':
            d = self.obj_dict(value[1][0])
            return float(d.get('num', default)) if isinstance(d.get('num'), float) else default
        return default

    def pages(self):
        out = []
        for num in self.objs:
            d = self.obj_dict(num)
            if d.get('Type') == 'Page':
                out.append(num)
        return out

    def page_dict(self, num):
        return self.obj_dict(num)


# ---------------------------------------------------------------- 字体

class Font:
    def __init__(self, pdf, num):
        self.pdf = pdf
        d = pdf.obj_dict(num)
        self.d = d
        self.base = d.get('BaseFont', '')
        if isinstance(self.base, str):
            self.base = self.base
        self.subtype = d.get('Subtype', '')
        self.two_byte = self.subtype == 'Type0'
        widths = d.get('Widths')
        self.first = int(d.get('FirstChar', 0) or 0) if isinstance(d.get('FirstChar'), float) else 0
        self.widths = {}
        if isinstance(widths, list):
            wcur = 0
            for item in widths:
                if isinstance(item, float):
                    self.widths[self.first + wcur] = item
                    wcur += 1
        descendant = d.get('DescendantFonts')
        self.scale = 1.0
        if isinstance(descendant, list) and descendant:
            dd = pdf.resolve(descendant[0])
            dw = dd.get('DW')
            if isinstance(dw, float):
                self.default_width = dw
            w2 = dd.get('W')
            if isinstance(w2, list):
                i = 0
                while i < len(w2):
                    a = w2[i]
                    if i + 1 < len(w2) and isinstance(w2[i + 1], list):
                        cid = int(a) if isinstance(a, float) else 0
                        for k, wv in enumerate(w2[i + 1]):
                            if isinstance(wv, float):
                                self.widths[cid + k] = wv
                        i += 2
                    elif i + 2 < len(w2):
                        lo = int(a) if isinstance(a, float) else 0
                        hi = int(w2[i + 1]) if isinstance(w2[i + 1], float) else lo
                        wv = w2[i + 2] if isinstance(w2[i + 2], float) else 0
                        for c in range(lo, min(hi, lo + 2048) + 1):
                            self.widths[c] = wv
                        i += 3
                    else:
                        break
        else:
            self.default_width = 500
        if not hasattr(self, 'default_width'):
            self.default_width = 500
        self.encoding = d.get('Encoding')
        self.tounicode = {}
        tu = d.get('ToUnicode')
        if isinstance(tu, tuple) and tu and tu[0] == 'ref':
            data = pdf.stream(tu[1][0]) or b''
            self.tounicode = self._parse_cmap(data)

    def _parse_cmap(self, data):
        mapping = {}
        for m in re.finditer(rb'beginbfchar(.*?)endbfchar', data, re.S):
            for src, dst in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', m.group(1)):
                code = int(src, 16)
                try:
                    mapping[code] = ''.join(chr(int(dst[k:k + 4], 16))
                                            for k in range(0, len(dst), 4))
                except Exception:
                    pass
        for m in re.finditer(rb'beginbfrange(.*?)endbfrange', data, re.S):
            for lo, hi, dst in re.findall(
                    rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', m.group(1)):
                l, h, d0 = int(lo, 16), int(hi, 16), int(dst, 16)
                for k in range(l, min(h, l + 1024) + 1):
                    try:
                        mapping[k] = chr(d0 + (k - l))
                    except Exception:
                        pass
            for lo, hi, arr in re.findall(
                    rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]', m.group(1), re.S):
                l = int(lo, 16)
                for k, dst in enumerate(re.findall(rb'<([0-9A-Fa-f]+)>', arr)):
                    try:
                        mapping[l + k] = ''.join(chr(int(dst[m2:m2 + 4], 16))
                                                 for m2 in range(0, len(dst), 4))
                    except Exception:
                        pass
        return mapping

    def decode(self, data):
        out = []
        codes = []
        if self.two_byte:
            for k in range(0, len(data) - 1, 2):
                codes.append((data[k] << 8) | data[k + 1])
        else:
            codes = list(data)
        for code in codes:
            ch = self.tounicode.get(code)
            if ch is None:
                ch = chr(code) if 32 <= code < 127 else ''
            out.append(ch)
        return ''.join(out), codes

    def width_of(self, codes):
        total = 0.0
        for code in codes:
            total += self.widths.get(code, self.default_width)
        return total


# ---------------------------------------------------------------- 内容流解析

def mat_mul(a, b):
    return [
        a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
    ]


def cmyk_to_rgb(c, m, y, k):
    return (round(255 * (1 - c) * (1 - k)), round(255 * (1 - m) * (1 - k)),
            round(255 * (1 - y) * (1 - k)))


def parse_content(pdf, data, resources, ctm=None, depth=0):
    """返回 (texts, rects, lines, images)。坐标已转成 PDF 用户空间（左下原点）。"""
    texts, rects, lines, images = [], [], [], []
    if depth > 6:
        return texts, rects, lines, images
    ctm = list(ctm or [1, 0, 0, 1, 0, 0])
    stack = []
    tm = lm = [1, 0, 0, 1, 0, 0]
    font = None
    font_size = 12.0
    leading = 0.0
    char_space = word_space = horiz = 0.0
    rise = 0.0
    fill = (0, 0, 0)
    stroke = (0, 0, 0)
    font_name = ''
    path = []
    cur = None
    toks = tokenize(data)
    operands = []
    i = 0

    def font_resources():
        res = pdf.resolve(resources)
        fonts = res.get('Font') if res else None
        if isinstance(fonts, tuple) and fonts and fonts[0] == 'ref':
            fonts = pdf.obj_dict(fonts[1][0])
        return fonts if isinstance(fonts, dict) else {}

    while i < len(toks):
        kind, val = toks[i]
        if kind in ('num', 'str', 'name') or (kind == 'op' and val in ('[', '<<')):
            if kind == 'op':
                value, nxt = group(toks, i)
                operands.append(value)
                i = nxt
                continue
            operands.append(val)
            i += 1
            continue
        op = val
        i += 1
        try:
            if op == 'q':
                stack.append((list(ctm), fill, stroke))
            elif op == 'Q':
                if stack:
                    ctm, fill, stroke = stack.pop()
                    ctm = list(ctm)
            elif op == 'cm' and len(operands) >= 6:
                m = [float(x) for x in operands[-6:]]
                ctm = mat_mul(m, ctm)
            elif op == 'BT':
                tm = [1, 0, 0, 1, 0, 0]
                lm = [1, 0, 0, 1, 0, 0]
            elif op == 'ET':
                pass
            elif op == 'Tf' and len(operands) >= 2:
                fname, font_size = operands[-2], float(operands[-1])
                fonts = font_resources()
                ref = fonts.get(fname)
                if isinstance(ref, tuple) and ref and ref[0] == 'ref':
                    font = Font(pdf, ref[1][0])
                    font_name = font.base
                else:
                    font = None
            elif op == 'TL' and operands:
                leading = float(operands[-1])
            elif op == 'Tc' and operands:
                char_space = float(operands[-1])
            elif op == 'Tw' and operands:
                word_space = float(operands[-1])
            elif op == 'Tz' and operands:
                horiz = float(operands[-1]) / 100.0
            elif op == 'Ts' and operands:
                rise = float(operands[-1])
            elif op == 'Td' and len(operands) >= 2:
                tx, ty = float(operands[-2]), float(operands[-1])
                lm = mat_mul([1, 0, 0, 1, tx, ty], lm)
                tm = list(lm)
            elif op == 'TD' and len(operands) >= 2:
                tx, ty = float(operands[-2]), float(operands[-1])
                leading = -ty
                lm = mat_mul([1, 0, 0, 1, tx, ty], lm)
                tm = list(lm)
            elif op == 'Tm' and len(operands) >= 6:
                lm = [float(x) for x in operands[-6:]]
                tm = list(lm)
            elif op == 'T*':
                lm = mat_mul([1, 0, 0, 1, 0, -leading], lm)
                tm = list(lm)
            elif op in ('Tj', 'TJ', "'", '"'):
                if op == "'":
                    lm = mat_mul([1, 0, 0, 1, 0, -leading], lm)
                    tm = list(lm)
                text_parts = []
                codes = []
                if op in ('Tj', "'", '"'):
                    raw = operands[-1]
                    if isinstance(raw, bytes):
                        text_parts.append(raw)
                elif isinstance(operands[-1], list):
                    for item in operands[-1]:
                        if isinstance(item, bytes):
                            text_parts.append(item)
                joined = b''.join(text_parts)
                decoded, codes = (font.decode(joined) if font else (joined.decode('latin-1'), list(joined)))
                trm = mat_mul(tm, ctm)
                x, y = trm[4], trm[5]
                eff_size = font_size * (abs(trm[3]) if trm[3] else 1)
                if decoded.strip():
                    texts.append({
                        'text': decoded,
                        'x': round(x, 2),
                        'y': round(y, 2),
                        'size': round(abs(font_size * (trm[3] or 1)), 2),
                        'rawSize': font_size,
                        'color': '%02X%02X%02X' % fill,
                        'font': font_name,
                    })
                adv = (font.width_of(codes) if font else 500.0 * len(codes)) / 1000.0 * font_size
                adv += char_space * len(codes)
                adv *= horiz if horiz else 1.0
                tm = mat_mul([1, 0, 0, 1, adv, 0], tm)
                lm = list(tm)
            elif op == 're' and len(operands) >= 4:
                x, y, w, h = [float(v) for v in operands[-4:]]
                path.append(('re', x, y, w, h))
            elif op == 'm' and len(operands) >= 2:
                cur = (float(operands[-2]), float(operands[-1]))
                path.append(('m', cur))
            elif op == 'l' and len(operands) >= 2:
                p = (float(operands[-2]), float(operands[-1]))
                if cur:
                    path.append(('l', cur, p))
                cur = p
            elif op in ('c', 'v', 'y'):
                cur = None
            elif op in ('S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*'):
                fill_it = op in ('f', 'F', 'f*', 'B', 'B*', 'b', 'b*')
                stroke_it = op in ('S', 's', 'B', 'B*', 'b', 'b*')
                for item in path:
                    if item[0] == 're':
                        _, x, y, w, h = item
                        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                    else:
                        continue
                    tx = [mat_mul([1, 0, 0, 1, px, py], ctm)[4:6] for px, py in pts]
                    xs = [p[0] for p in tx]
                    ys = [p[1] for p in tx]
                    rects.append({
                        'x': round(min(xs), 2), 'y': round(min(ys), 2),
                        'w': round(max(xs) - min(xs), 2), 'h': round(max(ys) - min(ys), 2),
                        'fill': '%02X%02X%02X' % fill if fill_it else None,
                        'stroke': '%02X%02X%02X' % stroke if stroke_it else None,
                        'sw': round(abs(1 * ctm[0]), 2),
                    })
                path = []
                cur = None
            elif op == 'n':
                path = []
                cur = None
            elif op in ('rg',) and len(operands) >= 3:
                fill = tuple(int(round(float(v) * 255)) for v in operands[-3:])
            elif op == 'RG' and len(operands) >= 3:
                stroke = tuple(int(round(float(v) * 255)) for v in operands[-3:])
            elif op == 'g' and operands:
                v = int(round(float(operands[-1]) * 255))
                fill = (v, v, v)
            elif op == 'G' and operands:
                v = int(round(float(operands[-1]) * 255))
                stroke = (v, v, v)
            elif op == 'k' and len(operands) >= 4:
                fill = cmyk_to_rgb(*[float(v) for v in operands[-4:]])
            elif op == 'K' and len(operands) >= 4:
                stroke = cmyk_to_rgb(*[float(v) for v in operands[-4:]])
            elif op == 'Do' and operands:
                xres = pdf.resolve(pdf.resolve(resources).get('XObject') or {})
                ref = xres.get(operands[-1]) if isinstance(xres, dict) else None
                if isinstance(ref, tuple) and ref and ref[0] == 'ref':
                    xo = pdf.obj_dict(ref[1][0])
                    if xo.get('Subtype') == 'Image':
                        m = mat_mul([1, 0, 0, 1, 0, 0], ctm)
                        w = abs(ctm[0]) or 1
                        h = abs(ctm[3]) or 1
                        images.append({'x': round(m[4], 2), 'y': round(m[5], 2),
                                       'w': round(w, 2), 'h': round(h, 2),
                                       'wh': [xo.get('Width'), xo.get('Height')],
                                       'obj': ref[1][0],
                                       'filter': str(xo.get('Filter'))})
                    elif xo.get('Subtype') == 'Form':
                        data2 = pdf.stream(ref[1][0]) or b''
                        sub = pdf.resolve(xo.get('Resources') or {})
                        t2, r2, l2, i2 = parse_content(pdf, data2, sub if sub else resources,
                                                      ctm=ctm, depth=depth + 1)
                        texts += t2
                        rects += r2
                        lines += l2
                        images += i2
        except Exception:
            pass
        operands = []
    return texts, rects, lines, images


def load(path):
    pdf = Pdf(path)
    out = {'pages': [], 'fonts': {}, 'meta': {}}
    for num in pdf.pages():
        page = pdf.page_dict(num)
        media = page.get('MediaBox')
        if isinstance(media, list) and len(media) == 4:
            box = [float(v) for v in media]
        else:
            ref = media[1][0] if isinstance(media, tuple) else None
            d = pdf.obj_dict(ref) if ref else {}
            arr = d.get('arr') if isinstance(d, dict) else None
            box = [float(v) for v in arr] if isinstance(d, list) and len(d) == 4 else [0, 0, 595, 842]
        contents = page.get('Contents')
        data = b''
        if isinstance(contents, tuple) and contents and contents[0] == 'ref':
            data = pdf.stream(contents[1][0]) or b''
        elif isinstance(contents, list):
            for item in contents:
                if isinstance(item, tuple) and item and item[0] == 'ref':
                    data += (pdf.stream(item[1][0]) or b'') + b'\n'
        res = page.get('Resources') or {}
        texts, rects, lines, images = parse_content(pdf, data, res)
        out['pages'].append({
            'width': box[2] - box[0], 'height': box[3] - box[1],
            'texts': texts, 'rects': rects, 'lines': lines, 'images': images,
        })
    return out


if __name__ == '__main__':
    path = sys.argv[1]
    pdf = Pdf(path)
    result = load(path)
    json.dump(result, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if len(sys.argv) > 3:
        img_dir = sys.argv[3]
        os.makedirs(img_dir, exist_ok=True)
        for page in result['pages']:
            for im in page['images']:
                num = im.get('obj')
                if num is None:
                    continue
                body = pdf.objs.get(num, b'')
                idx = body.find(b'stream')
                start = pdf.offsets[num] + idx + 6
                while pdf.raw[start] in b'\r\n':
                    start += 1
                d = pdf.obj_dict(num)
                length = d.get('Length')
                if isinstance(length, tuple):
                    length = int(pdf._dict_bytes(length[1][0]).strip())
                data = pdf.raw[start:start + int(length)]
                ext = 'jpg' if 'DCT' in str(d.get('Filter')) else 'bin'
                with open(os.path.join(img_dir, 'img_%s.%s' % (num, ext)), 'wb') as fh:
                    fh.write(data)
                im['file'] = 'img_%s.%s' % (num, ext)
                # 有 SMask 说明这张图带透明度，单独把蒙版存下来，渲染时合成
                smask = d.get('SMask')
                if isinstance(smask, tuple):
                    raw = pdf.stream(smask[1][0]) or b''
                    if raw:
                        with open(os.path.join(img_dir, 'img_%s.%s.mask' % (num, ext)), 'wb') as fh:
                            fh.write(raw)
                        im['mask'] = 'img_%s.%s.mask' % (num, ext)
        json.dump(result, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for idx, page in enumerate(result['pages']):
        print(f"page {idx + 1}: {page['width']}x{page['height']}  texts={len(page['texts'])} rects={len(page['rects'])} images={len(page['images'])}")
