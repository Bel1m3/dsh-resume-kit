# -*- coding: utf-8 -*-
"""能力雷达图：用 Pillow 画成高分辨率 PNG，嵌进 Word。

模板原图是 8 轴雷达；轴数与数值都由数据决定，数值支持 0—1 或 0—100。
白底输出（透明底在部分 PDF 转换里会变黑）。
"""
from __future__ import annotations

import math
import os

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = None

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_radar(path, axes, width_px=1400, rings=4,
               fill="C96F6F", stroke="A14747", grid="DCDCDC", spoke="E4E4E4",
               label_color="3A3A45", bg="FFFFFF"):
    """axes: [{"label": "数理逻辑", "value": 0.82}, ...]，从正上方顺时针排列。"""
    if Image is None or not axes:
        return None
    n = len(axes)
    cx = cy = width_px / 2.0
    radius = width_px * 0.255
    img = Image.new("RGB", (width_px, width_px), "#" + bg)
    d = ImageDraw.Draw(img)

    def point(i, r):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + r * math.cos(ang), cy + r * math.sin(ang))

    for k in range(1, rings + 1):
        d.polygon([point(i, radius * k / rings) for i in range(n)], outline="#" + grid)
    for i in range(n):
        d.line([(cx, cy), point(i, radius)], fill="#" + spoke, width=3)

    values = []
    for a in axes:
        try:
            v = float(a.get("value", 0))
        except Exception:
            v = 0.0
        if v > 1.0:
            v = v / 100.0
        values.append(max(0.05, min(1.0, v)))
    poly = [point(i, radius * values[i]) for i in range(n)]
    d.polygon(poly, fill="#" + fill, outline="#" + stroke)
    for p in poly:
        d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], fill="#" + stroke)

    font = _font(int(width_px * 0.038))
    for i, a in enumerate(axes):
        px, py = point(i, radius + width_px * 0.088)
        text = str(a.get("label", ""))
        try:
            box = d.textbbox((0, 0), text, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
        except Exception:
            tw, th = len(text) * 14, 24
        x = min(max(4, px - tw / 2), width_px - tw - 4)
        y = min(max(4, py - th / 2), width_px - th - 4)
        d.text((x, y), text, font=font, fill="#" + label_color)

    img = img.resize((width_px // 2, width_px // 2), Image.LANCZOS)
    img.save(path, dpi=(300, 300))
    return path
