# -*- coding: utf-8 -*-
"""用 layout JSON 粗略重绘 PDF 为 PNG —— 只为核对排版，不是高保真渲染器。"""
import json
import sys
from PIL import Image, ImageDraw, ImageFont

FONTS = {
    'bold': r'C:\Windows\Fonts\msyhbd.ttc',
    'regular': r'C:\Windows\Fonts\msyh.ttc',
}


def load_font(kind, size_px):
    path = FONTS.get(kind) or FONTS['regular']
    try:
        return ImageFont.truetype(path, size_px)
    except Exception:
        return ImageFont.load_default()


def render(layout, out_path, scale=2.0, img_dir=None):
    import os
    page = layout['pages'][0]
    W = int(page['width'] * scale)
    H = int(page['height'] * scale)
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)

    for r in page['rects']:
        x0 = r['x'] * scale
        x1 = (r['x'] + r['w']) * scale
        y0 = H - (r['y'] + r['h']) * scale
        y1 = H - r['y'] * scale
        if r.get('fill'):
            d.rectangle([x0, y0, x1, y1], fill='#' + r['fill'])
        if r.get('stroke'):
            d.rectangle([x0, y0, x1, y1], outline='#' + r['stroke'])

    def Y(y):
        return H - y * scale

    for r in page['rects']:
        x0 = r['x'] * scale
        x1 = (r['x'] + r['w']) * scale
        y0 = H - (r['y'] + r['h']) * scale
        y1 = H - r['y'] * scale
        if r.get('fill'):
            d.rectangle([x0, y0, x1, y1], fill='#' + r['fill'])
        if r.get('stroke'):
            d.rectangle([x0, y0, x1, y1], outline='#' + r['stroke'])

    for im in page['images']:
        name = im.get('file')
        if not name or not img_dir:
            continue
        full = os.path.join(img_dir, name)
        if not os.path.exists(full):
            continue
        try:
            sub = Image.open(full).convert('RGB')
        except Exception:
            continue
        mask_name = im.get('mask')
        if mask_name:
            mpath = os.path.join(img_dir, mask_name)
            if os.path.exists(mpath):
                alpha_bytes = open(mpath, 'rb').read()
                sw, sh = sub.size
                if len(alpha_bytes) >= sw * sh:
                    mask = Image.frombytes('L', (sw, sh), alpha_bytes[:sw * sh])
                    sub = sub.convert('RGBA')
                    sub.putalpha(mask)
        target = (max(1, int(im['w'] * scale)), max(1, int(im['h'] * scale)))
        sub = sub.resize(target)
        img.paste(sub, (int(im['x'] * scale), int(H - (im['y'] + im['h']) * scale)), sub if sub.mode == 'RGBA' else None)

    for t in page['texts']:
        kind = 'bold' if 'Bo' in t['font'] or 'Bold' in t['font'] else 'regular'
        size_px = max(6, int(round(t['size'] * scale)))
        font = load_font(kind, size_px)
        d.text((t['x'] * scale, Y(t['y'])), t['text'], font=font, fill='#' + t['color'], anchor='ls')

    img.save(out_path)
    print('rendered', out_path, img.size)


if __name__ == '__main__':
    layout = json.load(open(sys.argv[1], encoding='utf-8'))
    render(layout, sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 2.0,
           sys.argv[4] if len(sys.argv) > 4 else None)
