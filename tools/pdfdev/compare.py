# -*- coding: utf-8 -*-
"""把两版 PDF 的文字行按左上角顺序对齐，报坐标差 —— 用来核对“排版有没有跑”。"""
import json
import sys

A = json.load(open(sys.argv[1], encoding='utf-8'))['pages'][0]
B = json.load(open(sys.argv[2], encoding='utf-8'))['pages'][0]
out = sys.argv[3]

def lines(page):
    rows = {}
    for t in page['texts']:
        key = round(t['y'] / 3.0)
        rows.setdefault(key, []).append(t)
    result = []
    for key in sorted(rows, reverse=True):
        items = sorted(rows[key], key=lambda t: t['x'])
        text = ''.join(i['text'] for i in items)
        result.append({
            'y': items[0]['y'],
            'x': items[0]['x'],
            'size': items[0]['size'],
            'color': items[0]['color'],
            'text': text.strip(),
        })
    return result

la, lb = lines(A), lines(B)
report = []
report.append('A(texts=%d, rects=%d, images=%d)  B(texts=%d, rects=%d, images=%d)' % (
    len(A['texts']), len(A['rects']), len(A['images']),
    len(B['texts']), len(B['rects']), len(B['images'])))
report.append('')
report.append('--- 行对齐（按顺序配对，dy = B.y - A.y，正数=我方更低；dx = B.x - A.x）---')

used = set()
pairs = []
for i, a in enumerate(la):
    if not a['text']:
        continue
    norm = ''.join(a['text'].split())[:14]
    best, best_score = None, 0
    for j, b in enumerate(lb):
        if j in used or not b['text']:
            continue
        nb = ''.join(b['text'].split())
        if not nb:
            continue
        head = norm[:8]
        score = 0
        if head and head in nb:
            score = len(head) + (8 if abs(a['y'] - b['y']) < 30 else 0)
        if score > best_score:
            best, best_score = j, score
    if best is None:
        report.append('  ✗ A 无对应: %7.1f %5.1f %s' % (a['y'], a['x'], a['text'][:42]))
        continue
    used.add(best)
    b = lb[best]
    pairs.append((a, b))
    report.append('  %7.1f→%7.1f dy=%+7.1f dx=%+6.1f size %4.1f/%4.1f  %s' % (
        a['y'], b['y'], b['y'] - a['y'], b['x'] - a['x'], a['size'], b['size'], a['text'][:40]))
for j, b in enumerate(lb):
    if j not in used and b['text']:
        report.append('  + B 多出: %7.1f %5.1f %s' % (b['y'], b['x'], b['text'][:42]))

report.append('')
report.append('--- 文本框（横幅）对比 ---')
def bars(page):
    out2 = []
    for r in page['rects']:
        if r['w'] > 20 and 20 < r['h'] < 40:
            out2.append(r)
    uniq = []
    for r in sorted(out2, key=lambda r: (-r['y'], r['x'])):
        if not uniq or abs(uniq[-1]['y'] - r['y']) > 1 or abs(uniq[-1]['x'] - r['x']) > 1:
            uniq.append(r)
    return uniq
for r in bars(A):
    report.append('  A bar x=%6.1f y=%6.1f w=%6.1f h=%5.1f fill=%s' % (r['x'], r['y'], r['w'], r['h'], r['fill']))
for r in bars(B):
    report.append('  B bar x=%6.1f y=%6.1f w=%6.1f h=%5.1f fill=%s' % (r['x'], r['y'], r['w'], r['h'], r['fill']))

if pairs:
    dy = [b['y'] - a['y'] for a, b in pairs]
    dx = [b['x'] - a['x'] for a, b in pairs]
    report.append('')
    report.append('dy 平均 %+.1f  最大偏差 %.1f  |  dx 平均 %+.1f  最大偏差 %.1f' % (
        sum(dy) / len(dy), max(abs(v) for v in dy), sum(dx) / len(dx), max(abs(v) for v in dx)))

open(out, 'w', encoding='utf-8').write('\n'.join(report))
print('wrote', out, len(report), 'lines')
