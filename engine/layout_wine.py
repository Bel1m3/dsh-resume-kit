# -*- coding: utf-8 -*-
"""版式二：wine-ribbon（酒红绶带，对标一份建筑学专业的设计感简历）。

左栏浅灰底：照片 → 姓名 → 个人信息 → 技能进度条 → 能力雷达图。
右栏白底：酒红绶带标题 + 教育 / 实习 / 校园 / 竞赛 / 技能特长。
"""
from __future__ import annotations

import os
import tempfile

from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Cm, Pt

from build_resume import (PLUGIN_ROOT, add_photo, add_tabs, cell_margins, fixed_layout, no_borders,
                          para, plain, rich, row_height, set_fonts, shade, spacer,
                          table_in, trim_cell)
import radar

W = {
    "page_w": 21.0,
    "page_h": 29.7,
    "sidebar_w": 7.05,
    "row_h": 29.55,
    "side_pad_l": 0.62,
    "side_pad_r": 0.55,
    "main_pad_l": 0.0,
    "main_pad_r": 0.55,
    "ribbon_w": 4.18,
    "ribbon_h": 0.81,
    "bar_h": 0.15,
    "photo_w": 3.39,
    "photo_h": 3.72,
    "radar_w": 6.10,
}

T = {
    "side_bg": "F1F1F1",
    "accent": "A14747",
    "accent_dark": "960E0E",
    "bar_fill": "C96F6F",
    "bar_track": "E5E5E5",
    "ink": "22243D",
    "muted": "6B6B75",
    "label": "4A4A55",
    "white": "FFFFFF",
}

S = {
    "name": 17.0,
    "info": 8.5,
    "side_title": 10.5,
    "skill_label": 8.0,
    "skill_level": 7.5,
    "ribbon": 10.5,
    "head": 9.0,
    "body": 8.5,
    "award": 8.5,
}


def side_title(cell, text, before=20.0):
    p = para(cell, size=S["side_title"], color=T["accent"], bold=True,
             align=WD_ALIGN_PARAGRAPH.CENTER, before=before, after=6, line=15)
    rich(p, text, size=S["side_title"], color=T["accent"], bold=True)
    ppr = p._p.get_or_add_pPr()
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), T["accent"])
    borders.append(bottom)
    ppr.append(borders)
    return p


# 只给等级、不给百分比时按这张表折算（用户也可以直接给 percent 覆盖）
LEVEL_PERCENT = {
    "精通": 0.92, "擅长": 0.78, "熟练": 0.70, "掌握": 0.74,
    "熟悉": 0.66, "良好": 0.72, "一般": 0.50, "了解": 0.38, "入门": 0.25,
}


def level_to_percent(level):
    text = str(level or "").strip().strip("：: ")
    if text in LEVEL_PERCENT:
        return LEVEL_PERCENT[text]
    for key, value in LEVEL_PERCENT.items():
        if key in text:
            return value
    return 0.62


def skill_bar(cell, item):
    """一条技能：标签一行 + 进度条（填充/轨道）+ 等级文字。"""
    label = str(item.get("label", ""))
    level = str(item.get("level", ""))
    try:
        pct = float(item.get("percent", 0))
    except Exception:
        pct = 0.0
    if pct <= 0:
        pct = level_to_percent(level)
    if pct > 1:
        pct = pct / 100.0
    pct = max(0.02, min(1.0, pct))

    p = para(cell, size=S["skill_label"], color=T["label"], bold=True, before=15, after=0, line=10)
    rich(p, label, size=S["skill_label"], color=T["label"], bold=True)

    track_w = W["sidebar_w"] - W["side_pad_l"] - W["side_pad_r"] - 1.05
    fill_w = max(0.12, track_w * pct)
    rest_w = max(0.02, track_w - fill_w)
    table = table_in(cell, 3, [fill_w, rest_w, 1.0])
    row = table.rows[0]
    row_height(row, W["bar_h"])
    c0, c1, c2 = row.cells
    shade(c0, T["bar_fill"])
    shade(c1, T["bar_track"])
    p2 = plain(c2.paragraphs[0], line=8, align=WD_ALIGN_PARAGRAPH.RIGHT)
    rich(p2, level, size=S["skill_level"], color=T["muted"])
    for c in (c0, c1, c2):
        trim_cell(c)
    spacer(cell, 3)


def side_radar(cell, block):
    axes = block.get("radar") or block.get("axes") or []
    if not axes:
        return
    out = os.path.join(tempfile.gettempdir(), "dsh-radar-%d.png" % (abs(hash(str(axes))) % 100000))
    try:
        if not radar.draw_radar(out, axes, bg=T["side_bg"]):
            return
    except Exception:
        return
    p = para(cell, size=1, align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=0)
    p.add_run().add_picture(out, width=Cm(W["radar_w"]))


def render_sidebar(cell, basics):
    cell_margins(cell, left=W["side_pad_l"], right=W["side_pad_r"], top=0, bottom=0.4)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    shade(cell, T["side_bg"])
    trim_cell(cell)

    photo = basics.get("photo")
    if photo and os.path.exists(photo):
        p = para(cell, size=1, align=WD_ALIGN_PARAGRAPH.CENTER, before=26.0, after=0)
        add_photo(p, photo, W["photo_w"], W["photo_h"])

    if basics.get("name"):
        p = para(cell, size=S["name"], color=T["ink"], bold=True,
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=0, line=22)
        rich(p, basics["name"], size=S["name"], color=T["ink"], bold=True)

    fields = [f for f in (basics.get("fields") or []) if (f.get("label") or f.get("value"))]
    for item in fields:
        label = str(item.get("label", ""))
        value = str(item.get("value", ""))
        p = para(cell, size=S["info"], color=T["ink"], before=7.5, after=0, line=13.4)
        add_tabs(p, [(0.95, "left", None)])
        rich(p, str(item.get("icon", "")), size=S["info"], color=T["accent"])
        rich(p, "\t", size=S["info"], color=T["ink"])
        rich(p, label + "：", size=S["info"], color=T["label"])
        rich(p, value, size=S["info"], color=T["ink"])

    for block in (basics.get("sideSections") or []):
        title = block.get("title")
        style = block.get("style", "lines")
        lines = [ln for ln in (block.get("lines") or []) if ln.get("value") or ln.get("label")]
        bars = [b for b in (block.get("bars") or []) if b.get("label")]
        radar_axes = [a for a in (block.get("radar") or block.get("axes") or []) if a.get("label")]
        if style == "radar":
            if radar_axes:          # 删光了就不画，也不留标题
                side_radar(cell, block)
            continue
        if not (bars or lines):     # 条目删光了：整节跳过，不留空标题
            continue
        if title:
            side_title(cell, title, before=block.get("before", 36.0))
        if style == "bars":
            for b in bars:
                skill_bar(cell, b)
        for line in lines:
            p = para(cell, size=S["skill_label"], color=T["ink"], before=4, after=0, line=12.4)
            if line.get("label"):
                rich(p, "**%s：**" % line["label"], size=S["skill_label"], color=T["label"])
            rich(p, str(line.get("value", "")), size=S["skill_label"], color=T["ink"])
    trim_cell(cell)


def cell_table(cell, widths, rows):
    """在单元格里建一张无边框固定列宽的空表，用来对齐多列数据。"""
    table = cell.add_table(rows=rows, cols=len(widths))
    no_borders(table)
    fixed_layout(table, widths)
    for row in table.rows:
        for c in row.cells:
            cell_margins(c, 0, 0, 0, 0)
            c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return table


def ribbon(cell, title, inner_w):
    widths = [W["ribbon_w"], max(0.4, inner_w - W["ribbon_w"])]
    table = table_in(cell, 2, widths)
    row = table.rows[0]
    row_height(row, W["ribbon_h"])
    left, right = row.cells
    shade(left, T["accent"])
    p = plain(left.paragraphs[0], line=12, align=WD_ALIGN_PARAGRAPH.CENTER)
    rich(p, title, size=S["ribbon"], color=T["white"], bold=True)
    for c in (left, right):
        trim_cell(c)
    return table


def render_wine(doc, spec):
    basics = spec.get("basics") or {}
    inner_w = W["page_w"] - W["sidebar_w"] - W["main_pad_l"] - W["main_pad_r"]

    table = doc.add_table(rows=1, cols=2)
    no_borders(table)
    fixed_layout(table, [W["sidebar_w"], W["page_w"] - W["sidebar_w"]])
    row = table.rows[0]
    row_height(row, W["row_h"])

    render_sidebar(row.cells[0], basics)

    main = row.cells[1]
    cell_margins(main, left=W["main_pad_l"], right=W["main_pad_r"], top=0, bottom=0.4)
    main.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    trim_cell(main)

    first = True
    for section in (spec.get("sections") or []):
        kind = section.get("type", "text")
        items = section.get("items") or []
        paragraphs = section.get("paragraphs") or []
        if not items and not paragraphs:
            continue
        spacer(main, 9 if first else 26)
        first = False
        ribbon(main, section.get("title") or "小节", inner_w)
        spacer(main, 10)

        if kind in ("education", "experience"):
            for item in items:
                p = para(main, size=S["head"] + 0.5, color=T["accent_dark"], before=6, after=0, line=14)
                add_tabs(p, [(inner_w, "right", None)])
                rich(p, item.get("period", "") and (item.get("period") + "  ") or "",
                     size=S["head"], color=T["label"], bold=True)
                rich(p, item.get("org") or item.get("school") or "",
                     size=S["head"] + 0.5, color=T["accent_dark"], bold=True)
                right = item.get("role") or "　·　".join(
                    [x for x in (item.get("major"), item.get("degree")) if x])
                if right:
                    rich(p, "\t" + right, size=S["head"], color=T["label"], bold=True)
                for block in (item.get("blocks") or []):
                    bp = para(main, size=S["body"], color=T["ink"], before=3, after=0, line=12.6)
                    if block.get("label"):
                        rich(bp, "**%s：**" % block["label"], size=S["body"], color=T["ink"])
                    rich(bp, block.get("text", ""), size=S["body"], color=T["ink"])
                for line in (item.get("lines") or []):
                    bp = para(main, size=S["body"], color=T["ink"], before=2, after=0, line=12.6)
                    if line.get("label"):
                        rich(bp, "**%s：**" % line["label"], size=S["body"], color=T["ink"])
                    rich(bp, line.get("text", ""), size=S["body"], color=T["ink"])

        elif kind == "awards":
            widths = [8.10, 1.55, 1.45, max(1.2, inner_w - 11.10)]
            table = cell_table(main, widths, len(items))
            for r, line in enumerate(items):
                bold = bool(line.get("highlight"))
                color = T["accent_dark"] if bold else T["ink"]
                row_cells = table.rows[r].cells
                values = [
                    (str(line.get("year", "")) + str(line.get("name", "")), color, bold),
                    (str(line.get("level", "")), T["muted"] if not bold else color, bold),
                    (str(line.get("award", "")), color, bold),
                    ("团队：" + str(line["team"]) if line.get("team") else "", T["muted"] if not bold else color, bold),
                ]
                for c, (text, col, b) in zip(row_cells, values):
                    p = plain(c.paragraphs[0], line=15.5,
                              align=WD_ALIGN_PARAGRAPH.LEFT if c is row_cells[0] else WD_ALIGN_PARAGRAPH.CENTER)
                    rich(p, text, size=S["award"], color=col, bold=b)
                for c in row_cells:
                    trim_cell(c)

        else:
            for text in paragraphs:
                p = para(main, size=S["body"], color=T["ink"], before=3, after=0, line=13.4)
                rich(p, "**%s**" % text if False else text, size=S["body"], color=T["ink"])

    trim_cell(main)
    return doc


def render(doc, spec):
    return render_wine(doc, spec)
