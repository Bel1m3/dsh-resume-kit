#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简历渲染引擎（resume-spec v2）

两套版式，全部用 Word 原生元素搭，文字都可编辑：
  dark-blue    深灰蓝双栏（对标一份国企/设计院方向的单页双栏简历）
  wine-ribbon  酒红绶带双栏（对标一份建筑学专业的设计感简历）

用法：
  python build_resume.py --input data.json --output out.docx [--template dark-blue]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

FONT = "微软雅黑"

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_photo(path, base_dirs=()):
    """照片路径支持相对：spec 所在目录 → 逐级向上 → 插件根目录 → 当前目录。"""
    if not path:
        return None
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    candidates = []
    for base in base_dirs:
        candidates.append(os.path.join(base, path))
        candidates.append(os.path.join(os.path.dirname(base), path))
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(base)), path))
    candidates.append(os.path.join(PLUGIN_ROOT, path))
    candidates.append(os.path.abspath(path))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


# ---------------------------------------------------------------- 通用工具


def prepare_photo(path, w_cm, h_cm):
    """按版式画框的比例居中裁切照片，返回可用路径（裁不动就原样返回）。"""
    target = w_cm / h_cm
    try:
        from PIL import Image
        img = Image.open(path)
        cur = img.width / float(img.height)
        if abs(cur - target) > 0.02:
            if cur > target:
                new_w = int(img.height * target)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))
            import tempfile
            out = os.path.join(tempfile.gettempdir(), "dsh-photo-%d-%d.jpg" % (
                abs(hash((path, w_cm, h_cm))) % 100000, int(w_cm * 100)))
            img.convert("RGB").save(out, quality=93)
            return out
    except Exception:
        pass
    return path


def add_photo(paragraph, path, w_cm, h_cm):
    paragraph.add_run().add_picture(prepare_photo(path, w_cm, h_cm),
                                    width=Cm(w_cm), height=Cm(h_cm))


def set_fonts(run, size=None, bold=None, color=None, italic=None, ea=None, latin=None):
    """中西文字体都要显式写，否则中文会回退宋体。ea 可单独指定中文字体。"""
    ea_font = ea or FONT
    latin_font = latin or ea_font
    run.font.name = latin_font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), latin_font)
    rfonts.set(qn("w:hAnsi"), latin_font)
    rfonts.set(qn("w:eastAsia"), ea_font)
    rfonts.set(qn("w:cs"), ea_font)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def shade(element, fill):
    target = element._tc if hasattr(element, "_tc") else element._p
    pr = target.get_or_add_tcPr() if hasattr(target, "get_or_add_tcPr") else target.get_or_add_pPr()
    for old in pr.findall(qn("w:shd")):
        pr.remove(old)
    pr.append(parse_xml('<w:shd {} w:val="clear" w:color="auto" w:fill="{}"/>'.format(
        nsdecls("w"), fill)))


def cell_margins(cell, left=0.0, right=0.0, top=0.0, bottom=0.0):
    tcpr = cell._tc.get_or_add_tcPr()
    mar = tcpr.find(qn("w:tcMar"))
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tcpr.append(mar)
    for tag, value in (("w:top", top), ("w:left", left), ("w:bottom", bottom), ("w:right", right)):
        node = mar.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            mar.append(node)
        node.set(qn("w:w"), str(int(round(value * 567))))
        node.set(qn("w:type"), "dxa")


def no_borders(table):
    tblpr = table._tbl.tblPr
    for old in tblpr.findall(qn("w:tblBorders")):
        tblpr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement("w:" + edge)
        node.set(qn("w:val"), "nil")
        borders.append(node)
    tblpr.append(borders)


def fixed_layout(table, widths_cm):
    table.autofit = False
    table.allow_autofit = False
    tblpr = table._tbl.tblPr
    for old in tblpr.findall(qn("w:tblLayout")):
        tblpr.remove(old)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
    for col, width in zip(table.columns, widths_cm):
        col.width = Cm(width)


def row_height(row, cm, rule=WD_ROW_HEIGHT_RULE.EXACTLY):
    row.height = Cm(cm)
    row.height_rule = rule


def para(container, size=9.0, color="000000", bold=False, align=None,
         before=0, after=0, line=None, indent=None, first_line=None):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = Pt(line)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    else:
        pf.line_spacing = 1.0
    if indent is not None:
        pf.left_indent = Cm(indent)
    if first_line is not None:
        pf.first_line_indent = Cm(first_line)
    if align is not None:
        p.alignment = align
    set_fonts(p.add_run(""), size=size, bold=bold, color=color)
    return p


TOKEN = re.compile(r"(\*\*.+?\*\*|\{\{.+?\}\})")


def rich(p, text, size=9.0, color="000000", bold=False, accent=None, accent_color="E80000",
         ea=None, latin=None):
    """**加粗** 与 {{强调色}}。accent 为 None 时强调色用 accent_color。"""
    accent = accent or accent_color
    for chunk in TOKEN.split(str(text or "")):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
            set_fonts(p.add_run(chunk[2:-2]), size=size, bold=True, color=color, ea=ea, latin=latin)
        elif chunk.startswith("{{") and chunk.endswith("}}") and len(chunk) > 4:
            set_fonts(p.add_run(chunk[2:-2]), size=size, bold=True, color=accent, ea=ea, latin=latin)
        else:
            set_fonts(p.add_run(chunk), size=size, bold=bold, color=color, ea=ea, latin=latin)
    return p


def trim_cell(cell):
    """把单元格里没有文字的空段落压到 1pt，否则嵌套表格会凭空多出一条空行。"""
    for p in cell.paragraphs:
        text = "".join(node.text or "" for node in p._p.iter(qn("w:t")))
        if text.strip():
            continue
        if p._p.find(".//" + qn("w:drawing")) is not None:
            continue
        ppr = p._p.find(qn("w:pPr"))
        if ppr is not None and ppr.find(qn("w:pBdr")) is not None:
            continue
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(1)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        for run in p.runs:
            set_fonts(run, size=1)


def plain(p, line=None, before=0, after=0, align=None):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = Pt(line)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    if align is not None:
        p.alignment = align
    return p


def spacer(container, pt=6):
    """纯间距段落：行高压到 1pt，用段前距撑开。"""
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(pt)
    pf.space_after = Pt(0)
    pf.line_spacing = Pt(1)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    set_fonts(p.add_run("\u200b"), size=1)
    return p


def add_tabs(p, stops):
    """stops: [(cm, 'left'|'right'|'center', 'dots'|None)]"""
    for pos, align, leader in stops:
        align_map = {"left": WD_TAB_ALIGNMENT.LEFT, "right": WD_TAB_ALIGNMENT.RIGHT,
                     "center": WD_TAB_ALIGNMENT.CENTER}
        leader_map = {None: WD_TAB_LEADER.SPACES, "dots": WD_TAB_LEADER.DOTS,
                      "line": WD_TAB_LEADER.LINES}
        p.paragraph_format.tab_stops.add_tab_stop(
            Cm(pos), align_map[align], leader_map.get(leader, WD_TAB_LEADER.SPACES))


def page_setup(doc, w=21.0, h=29.7):
    section = doc.sections[0]
    section.page_width = Cm(w)
    section.page_height = Cm(h)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, attr, Cm(0))
    section.header_distance = Cm(0)
    section.footer_distance = Cm(0)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(9)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0


def table_in(cell, cols, widths, heights=None):
    table = cell.add_table(rows=1, cols=cols)
    no_borders(table)
    fixed_layout(table, widths)
    for c in table.rows[0].cells:
        cell_margins(c, 0, 0, 0, 0)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return table


# ---------------------------------------------------------------- 版式一：dark-blue

DB = {
    "sidebar_w": 6.398,
    "page_w": 21.0,
    "page_h": 29.7,
    "row_h": 29.55,
    "side_pad_l": 0.40,
    "side_pad_r": 0.40,
    "side_pad_t": 0.0,
    "main_pad_l": 0.856,
    "main_pad_r": 0.755,
    "main_pad_t": 0.0,
    "bar_h": 0.921,
    "photo_w": 3.90,
    "photo_h": 5.50,
    "sizes": {
        "name": 23, "name_en": 10.5, "side_bar": 12.0, "info": 9.0, "side_body": 8.0,
        "bar": 12.5, "head": 9.0, "body": 9.0, "bullet": 9.0, "award": 9.0,
    },
}

DB_THEME = {
    "sidebar": "4A4E59",
    "accent": "1F92BA",
    "ink": "2A2F36",
    "body": "565B63",
    "muted": "8A9099",
    "side_label": "A9B4BF",
    "side_value": "FFFFFF",
    "side_body": "E1E6EC",
    "white": "FFFFFF",
}


def db_side_bar(cell, title, S, before=32.1, after=10.9):
    p = para(cell, size=S["side_bar"], color=DB_THEME["white"], bold=True,
             align=WD_ALIGN_PARAGRAPH.CENTER, before=before, after=after)
    p.paragraph_format.line_spacing = Cm(0.60)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    rich(p, title, size=S["side_bar"], color=DB_THEME["white"], bold=True)


def db_main_bar(cell, title, S, inner_w):
    """深色横幅：[细条][留白][深色标题块(居中)][accent 小方块][深色块]"""
    widths = [0.159, 0.141, 4.897, 0.339, inner_w - 0.159 - 0.141 - 4.897 - 0.339]
    table = table_in(cell, 5, widths)
    row = table.rows[0]
    row_height(row, DB["bar_h"])
    cells = row.cells
    for idx in (0, 2, 4):
        shade(cells[idx], DB_THEME["sidebar"])
    shade(cells[3], DB_THEME["accent"])
    p = plain(cells[2].paragraphs[0], line=13.5, align=WD_ALIGN_PARAGRAPH.CENTER)
    rich(p, title, size=S["bar"], color=DB_THEME["white"], bold=True)
    for c in cells:
        trim_cell(c)
    return table


def db_sidebar(cell, basics, S):
    cell_margins(cell, left=DB["side_pad_l"], right=DB["side_pad_r"], top=DB["side_pad_t"], bottom=0.4)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    shade(cell, DB_THEME["sidebar"])
    trim_cell(cell)

    photo = basics.get("photo")
    if photo and os.path.exists(photo):
        p = para(cell, size=1, align=WD_ALIGN_PARAGRAPH.CENTER, before=26.1, after=0)
        add_photo(p, photo, DB["photo_w"], DB["photo_h"])
    if basics.get("name"):
        p = para(cell, size=S["name"], color=DB_THEME["white"], bold=True,
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=19.5, after=0, line=26)
        rich(p, basics["name"], size=S["name"], color=DB_THEME["white"], bold=True)
    if basics.get("englishName"):
        p = para(cell, size=S["name_en"], color="C9D2DA",
                 align=WD_ALIGN_PARAGRAPH.CENTER, before=4.6, after=0, line=13)
        rich(p, basics["englishName"], size=S["name_en"], color="C9D2DA")

    fields = [f for f in (basics.get("fields") or []) if (f.get("label") or f.get("value"))]
    if fields:
        db_side_bar(cell, "基础信息", S, before=18.6, after=8.5)
        for item in fields:
            label = str(item.get("label", ""))
            value = str(item.get("value", ""))
            p = para(cell, size=S["info"], color=DB_THEME["side_value"], before=0, after=0, line=20.9)
            add_tabs(p, [(1.47, "left", None)])
            rich(p, label, size=S["info"], color=DB_THEME["side_label"])
            rich(p, "\t：" + value, size=S["info"], color=DB_THEME["side_value"])
        spacer(cell, 3.7)

    for block_index, block in enumerate(basics.get("sideSections") or []):
        lines = [ln for ln in (block.get("lines") or []) if ln.get("value") or ln.get("label")]
        title = block.get("title")
        if not lines:
            # 条目被删光了：整节跳过，别留一个空标题
            continue
        if title:
            # 第一个小节紧跟在「基础信息」后面，间距比后面几节小
            first_after_fields = block_index == 0 and bool(fields)
            db_side_bar(cell, title, S, before=(38.6 if first_after_fields else 32.1))
        for idx, line in enumerate(lines):
            p = para(cell, size=S["side_body"], color=DB_THEME["side_body"],
                     before=0 if idx == 0 else 4.0, after=0, line=13.2)
            label = line.get("label")
            if label:
                rich(p, "**%s：**" % label, size=S["side_body"], color=DB_THEME["white"])
            rich(p, str(line.get("value", "")), size=S["side_body"], color=DB_THEME["side_body"])
    trim_cell(cell)


def db_head_row(cell, left, mid, right, S, tab=3.36, width=13.0):
    """一行三段：期间 / 单位 / 角色，制表位对齐，不依赖表格。"""
    p = para(cell, size=S["head"], color=DB_THEME["ink"], before=0, after=0, line=13.4)
    add_tabs(p, [(tab, "left", None), (width, "right", None)])
    rich(p, left, size=S["head"], color=DB_THEME["ink"], bold=True)
    if mid:
        rich(p, "\t" + mid, size=S["head"], color=DB_THEME["accent"], bold=True)
    if right:
        rich(p, "\t" + right, size=S["head"], color=DB_THEME["accent"], bold=True)
    return p


def db_body(cell, label, text, S, before=3.0):
    p = para(cell, size=S["body"], color=DB_THEME["body"], before=before, after=0, line=13.1)
    if label:
        rich(p, "**%s：**" % label, size=S["body"], color=DB_THEME["body"])
    rich(p, text, size=S["body"], color=DB_THEME["body"])
    return p


def render_dark_blue(doc, spec):
    S = DB["sizes"]
    basics = spec.get("basics") or {}
    inner_w = DB["page_w"] - DB["sidebar_w"] - DB["main_pad_l"] - DB["main_pad_r"]

    table = doc.add_table(rows=1, cols=2)
    no_borders(table)
    fixed_layout(table, [DB["sidebar_w"], DB["page_w"] - DB["sidebar_w"]])
    row = table.rows[0]
    row_height(row, DB["row_h"])

    db_sidebar(row.cells[0], basics, S)

    main = row.cells[1]
    cell_margins(main, left=DB["main_pad_l"], right=DB["main_pad_r"], top=DB["main_pad_t"], bottom=0.4)
    main.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    trim_cell(main)

    spacer(main, 17.1)
    head = basics.get("headline") or {}
    if head.get("value") or head.get("label"):
        p = para(main, size=S["body"], color=DB_THEME["body"], before=0, after=0, line=13.4)
        if head.get("label"):
            rich(p, head["label"] + "　", size=S["body"], color=DB_THEME["accent"], bold=True)
        if head.get("value"):
            rich(p, head["value"], size=S["body"], color=DB_THEME["ink"], bold=True)
        if head.get("detail"):
            rich(p, "　·　", size=S["body"], color=DB_THEME["muted"])
            rich(p, head["detail"], size=S["body"], color=DB_THEME["body"])

    sections = [s for s in (spec.get("sections") or []) if (s.get("items") or s.get("paragraphs"))]
    for index, section in enumerate(sections):
        kind = section.get("type", "text")
        if index > 0:
            spacer(main, 12.8)
        else:
            spacer(main, 8.4)
        db_main_bar(main, section.get("title") or "小节", S, inner_w)
        spacer(main, 15.5)
        if kind == "education":
            for i, item in enumerate(section.get("items") or []):
                p = para(main, size=S["head"], color=DB_THEME["ink"], before=0, after=0, line=13.4)
                add_tabs(p, [(3.36, "left", None), (inner_w, "right", None)])
                rich(p, item.get("period", ""), size=S["head"], color=DB_THEME["ink"], bold=True)
                rich(p, "\t" + item.get("school", ""), size=S["head"], color=DB_THEME["accent"], bold=True)
                right = "　·　".join([x for x in (item.get("major"), item.get("degree")) if x])
                if right:
                    rich(p, "\t" + right, size=S["head"], color=DB_THEME["accent"], bold=True)
                for line in (item.get("lines") or []):
                    db_body(main, line.get("label"), line.get("text"), S, before=16.2)
                if i < len(section["items"]) - 1:
                    spacer(main, 6)
        elif kind == "experience":
            for i, item in enumerate(section.get("items") or []):
                db_head_row(main, item.get("period", ""), item.get("org", ""), item.get("role", ""), S)
                for block in (item.get("blocks") or []):
                    db_body(main, block.get("label"), block.get("text"), S, before=16.2)
                for bullet in (item.get("bullets") or []):
                    p = para(main, size=S["bullet"], color=DB_THEME["body"], before=1.2, after=0, line=13.3)
                    rich(p, bullet, size=S["bullet"], color=DB_THEME["body"])
                for block in (item.get("footBlocks") or []):
                    db_body(main, block.get("label"), block.get("text"), S, before=1.5)
                if i < len(section["items"]) - 1:
                    spacer(main, 5.8)

        elif kind == "bullets":
            for line in (section.get("items") or []):
                p = para(main, size=S["body"], color=DB_THEME["body"], before=0, after=0, line=15.1)
                add_tabs(p, [(0.25, "left", None)])
                rich(p, "▸", size=7.5, color="1F3B4D")
                rich(p, "\t" + str(line.get("text", "")), size=S["body"], color=DB_THEME["body"])
                if line.get("role"):
                    rich(p, "｜" + str(line["role"]), size=S["body"], color=DB_THEME["accent"], bold=True)

        elif kind == "awards":
            for line in (section.get("items") or []):
                p = para(main, size=S["award"], color=DB_THEME["body"], before=0, after=0, line=14.4)
                add_tabs(p, [(inner_w, "right", "dots")])
                rich(p, "▸", size=7.5, color="1F3B4D")
                if line.get("year"):
                    rich(p, str(line["year"]), size=S["award"], color=DB_THEME["ink"], bold=True)
                rich(p, str(line.get("name", "")), size=S["award"], color=DB_THEME["body"])
                rich(p, "\t" + str(line.get("award", "")), size=S["award"],
                     color=DB_THEME["accent"], bold=True)

        else:
            for text in (section.get("paragraphs") or []):
                p = para(main, size=S["body"], color=DB_THEME["body"], before=2, after=0, line=13.4)
                rich(p, text, size=S["body"], color=DB_THEME["body"])

    trim_cell(main)
    return doc


# ---------------------------------------------------------------- 版式二：wine-ribbon
# （下一版实现）
def render_wine_ribbon(doc, spec):
    from layout_wine import render as render_wine
    return render_wine(doc, spec)


# ---------------------------------------------------------------- 主流程

def render_single_ats(doc, spec):
    from layout_ats import render as render_ats
    return render_ats(doc, spec)


BUILDERS = {
    "dark-blue": render_dark_blue,
    "wine-ribbon": render_wine_ribbon,
    "single-ats": render_single_ats,
}


def build(spec, out_path, template=None, base_dirs=()):

    template = template or spec.get("template") or "dark-blue"
    if template not in BUILDERS:
        raise SystemExit(json.dumps({"ok": False, "error": "未知版式：%s" % template}, ensure_ascii=False))
    basics = spec.setdefault("basics", {})
    if basics.get("photo"):
        basics["photo"] = resolve_photo(basics["photo"], base_dirs) or basics["photo"]
    doc = Document()
    page_setup(doc)
    BUILDERS[template](doc, spec)
    doc.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--template", default=None)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as handle:
        spec = json.load(handle)

    if not (spec.get("basics") or {}).get("name"):
        print(json.dumps({"ok": False, "error": "basics.name 必填"}, ensure_ascii=False))
        return 2

    out = build(spec, args.output, args.template,
                base_dirs=[os.path.abspath(args.input), os.path.dirname(os.path.abspath(args.input))])
    print(json.dumps({"ok": True, "output": os.path.abspath(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
