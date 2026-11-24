# -*- coding: utf-8 -*-
"""版式三：single-ats（单栏，对标一份蓝色大标 + 青色小节色块的 Word 简历）。

原模板的观感：
  · 顶部「求职简历」大标（微软雅黑 27.5pt，#31859C 蓝）
  · 下面 2 列信息网格（宋体 10pt，#262626），右上角一张 3.55×5.33cm 照片
  · 每个小节 = 一条细横线 + 一个 96.3×20.2pt 的青色块（#31849B），块里白色粗体标题
  · 正文宋体，强调色 #0070C0

取向：**紧凑优先、尽量一页**。基础字号比原文档略小（9.5pt），并支持
`layoutScale` 整体微缩——插件发现排版超过一页时会自动按 0.95 / 0.90 再排一次。

与原模板的两处刻意差异（都是为了「机器筛读得到」）：
  1. 小节标题原本放在文本框/形状里，解析器读不到；这里改成同尺寸同配色的表格色块，
     文字仍然在正文流里，长相一样。
  2. 列表原本用小图标图片；这里改成文字项目符号。

全文没有分栏、没有嵌套表格、没有文本框；照片是浮动图片，可选。
"""
from __future__ import annotations

import os

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt

from build_resume import (add_tabs, para, plain, prepare_photo, rich, row_height,
                          shade, table_in, trim_cell)

A = {
    "page_w": 21.0,
    "pad_l": 1.40,
    "pad_r": 1.50,
    "pad_t": 1.00,
    "pad_b": 0.90,
    "tag_w": 3.40,
    "tag_h": 0.713,
    "photo_w": 3.55,
    "photo_h": 5.33,
    "photo_top": 0.36,
    "photo_gap": 0.30,
}

T = {
    "title": "31859C",
    "tag": "31849B",
    "ink": "262626",
    "muted": "595959",
    "rule": "C9CED6",
    "accent": "0070C0",
}

# 基础字号（紧凑档）；layoutScale 会整体微缩
BASE_S = {
    "title": 27.5,
    "info": 9.5,
    "tag": 11.5,
    "head": 10.0,
    "body": 9.5,
}
BASE_LINE = {
    "info": 13.8,
    "body": 12.2,
    "entry": 13.4,
}
BASE_GAP = {
    "section": 6.5,
    "section_first": 8.5,
}

EA = "宋体"
LATIN = "Times New Roman"
EA_HEAD = "微软雅黑"

_cur = {"scale": 1.0}


def sz(key):
    value = BASE_S[key] * _cur["scale"]
    if key == "title":          # 标题不要缩太狠，字太小反而不像原件
        return round(max(24.0, value), 1)
    if key == "tag":
        return round(max(10.5, value), 1)
    return round(value, 1)


def ln(key):
    return round(BASE_LINE[key] * _cur["scale"], 1)


def gap(key):
    return round(BASE_GAP[key] * _cur["scale"], 1)


def inner_width():
    return A["page_w"] - A["pad_l"] - A["pad_r"]


def add_floating_photo(paragraph, path, w_cm, h_cm, x_cm, y_cm):
    """照片放成「浮于文字下方」的绝对定位图片，不打断文字流。"""
    run = paragraph.add_run()
    run.add_picture(prepare_photo(path, w_cm, h_cm), width=Cm(w_cm), height=Cm(h_cm))
    drawing = run._element.find(qn("w:drawing"))
    if drawing is None:
        return
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        return
    graphic = inline.find(qn("a:graphic"))
    extent = inline.find(qn("wp:extent"))
    cx = extent.get("cx") if extent is not None else str(int(Cm(w_cm)))
    cy = extent.get("cy") if extent is not None else str(int(Cm(h_cm)))
    anchor = parse_xml(
        '<wp:anchor {ns} distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        'relativeHeight="1" behindDoc="1" locked="0" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page"><wp:posOffset>{x}</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="page"><wp:posOffset>{y}</wp:posOffset></wp:positionV>'
        '<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:wrapNone/>'
        '<wp:docPr id="1" name="photo"/>'
        '</wp:anchor>'.format(ns=nsdecls("wp", "a", "pic", "r"),
                              x=int(Cm(x_cm)), y=int(Cm(y_cm)), cx=cx, cy=cy)
    )
    if graphic is not None:
        anchor.append(graphic)
    drawing.remove(inline)
    drawing.append(anchor)


def rule(p, color=T["rule"], size=6):
    ppr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    ppr.append(borders)


def pad_label(text):
    """把「姓名」补成「姓　名」，让 2 字标签和 4 字标签的冒号对齐。"""
    text = str(text or "").strip()
    if len(text) == 2:
        return text[0] + "\u3000" + text[1]
    return text


def section_header(doc, title, first=False):
    """细横线 + 青色色块标题（文字在表格里，解析器读得到）。"""
    line = para(doc, size=1, before=gap("section_first") if first else gap("section"), after=2, line=1)
    rule(line)

    widths = [A["tag_w"], max(0.5, inner_width() - A["tag_w"])]
    table = table_in(doc, 2, widths)
    row = table.rows[0]
    row_height(row, A["tag_h"])
    tag, rest = row.cells
    shade(tag, T["tag"])
    p = plain(tag.paragraphs[0], line=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    rich(p, title, size=sz("tag"), color="FFFFFF", bold=True, ea=EA_HEAD)
    for c in (tag, rest):
        trim_cell(c)
    return table


def body_para(doc, before=1.2, after=0, line=None, indent=None, first_line=None):
    return para(doc, size=sz("body"), color=T["ink"], before=before, after=after,
                line=line or ln("body"), indent=indent, first_line=first_line)


def head_para(doc, before=1.2, after=0):
    return para(doc, size=sz("head"), color=T["ink"], before=before, after=after, line=ln("entry"))


def header_block(doc, basics, has_photo):
    """大标题 + 2 列信息网格 + 擅长软件行。"""
    right_indent = Cm(A["photo_w"] + A["photo_gap"]) if has_photo else Cm(0)

    title_p = para(doc, size=sz("title"), color=T["title"], bold=True, before=0, after=5, line=32)
    title_p.paragraph_format.right_indent = right_indent
    rich(title_p, basics.get("resumeTitle") or "求职简历", size=sz("title"),
         color=T["title"], bold=True, ea=EA_HEAD)

    fields = [f for f in (basics.get("fields") or []) if f.get("label") or f.get("value")]
    for start in range(0, len(fields), 2):
        chunk = fields[start:start + 2]
        p = para(doc, size=sz("info"), color=T["ink"], before=0, after=0, line=ln("info"))
        p.paragraph_format.right_indent = right_indent
        add_tabs(p, [(7.30, "left", None), (10.50, "left", None)])
        rich(p, pad_label(chunk[0].get("label", "")) + "：", size=sz("info"),
             color=T["ink"], ea=EA, latin=LATIN)
        rich(p, str(chunk[0].get("value", "")), size=sz("info"), color=T["ink"], ea=EA, latin=LATIN)
        if len(chunk) > 1:
            rich(p, "\t" + pad_label(chunk[1].get("label", "")) + "：", size=sz("info"),
                 color=T["ink"], ea=EA, latin=LATIN)
            rich(p, str(chunk[1].get("value", "")), size=sz("info"), color=T["ink"], ea=EA, latin=LATIN)

    skills = basics.get("skillsLine")
    if not skills:
        # 优先进「专业软件/技能」这一行，其次才拼短句；别把自我评价整段拼进来
        blocks = [b for b in (basics.get("sideSections") or [])
                  if any(kw in str(b.get("title") or "") for kw in ("技能", "证书", "软件", "特长"))]
        preferred = []
        for block in blocks:
            for line in (block.get("lines") or []):
                label = str(line.get("label") or "")
                if any(kw in label for kw in ("软件", "技能", "语言", "工具")) and line.get("value"):
                    preferred.append(str(line["value"]))
        if preferred:
            skills = "、".join(preferred[:2])
        else:
            parts = []
            for block in blocks:
                for bar in (block.get("bars") or []):
                    if bar.get("label"):
                        parts.append(str(bar["label"]).rstrip("：:"))
                for line in (block.get("lines") or []):
                    value = str(line.get("value") or "")
                    if value and len(value) <= 34:
                        parts.append(value)
                if parts:
                    break
            skills = "、".join(parts) if parts else ""
    if skills:
        p = para(doc, size=sz("info"), color=T["ink"], before=0, after=0, line=ln("info"))
        p.paragraph_format.right_indent = right_indent
        rich(p, pad_label("擅长软件") + "：", size=sz("info"), color=T["ink"], ea=EA, latin=LATIN)
        rich(p, str(skills), size=sz("info"), color=T["ink"], ea=EA, latin=LATIN)


def education_item(doc, item):
    p = head_para(doc, before=1.5)
    bits = []
    if item.get("period"):
        bits.append(str(item["period"]))
    for key in ("school", "college", "major", "degree"):
        if item.get(key):
            bits.append(str(item[key]))
    rich(p, "，".join(bits) + ("；" if bits else ""), size=sz("head"), color=T["ink"], ea=EA)
    for line in (item.get("lines") or []):
        bp = body_para(doc, before=0.8)
        if line.get("label"):
            rich(bp, "**%s：**" % pad_label(line["label"]), size=sz("body"), color=T["ink"], ea=EA)
        rich(bp, line.get("text", ""), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)


def experience_item(doc, item):
    p = head_para(doc, before=1.8)
    if item.get("period"):
        rich(p, str(item["period"]) + "　 ", size=sz("head"), color=T["ink"], ea=EA, latin=LATIN)
    if item.get("org"):
        rich(p, str(item["org"]), size=sz("head"), color=T["ink"], bold=True, ea=EA)
    if item.get("role"):
        rich(p, "　" + str(item["role"]), size=sz("head"), color=T["muted"], ea=EA)
    for block in (item.get("blocks") or []):
        bp = body_para(doc, before=0.8)
        if block.get("label"):
            rich(bp, "**%s：**" % block["label"], size=sz("body"), color=T["ink"], ea=EA)
        rich(bp, block.get("text", ""), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    for bullet in (item.get("bullets") or []):
        text = str(bullet)
        for prefix in ("（1）", "（2）", "（3）", "（4）", "（5）", "（6）",
                       "(1)", "(2)", "(3)", "(4)", "(5)", "(6)"):
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        bp = body_para(doc, before=0.4, indent=0.42, first_line=-0.42)
        rich(bp, "· ", size=sz("body"), color=T["muted"], ea=EA)
        rich(bp, text, size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    for block in (item.get("footBlocks") or []):
        bp = body_para(doc, before=0.8)
        if block.get("label"):
            rich(bp, "**%s：**" % block["label"], size=sz("body"), color=T["ink"], ea=EA)
        rich(bp, block.get("text", ""), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)


def bullet_item(doc, item):
    p = body_para(doc, before=0.5, indent=0.42, first_line=-0.42)
    rich(p, "· ", size=sz("body"), color=T["muted"], ea=EA)
    rich(p, str(item.get("text", "")), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    if item.get("role"):
        rich(p, "　｜" + str(item["role"]), size=sz("body"), color=T["accent"], bold=True, ea=EA)


def award_item(doc, item):
    p = body_para(doc, before=0.5, indent=0.42, first_line=-0.42)
    rich(p, "· ", size=sz("body"), color=T["muted"], ea=EA)
    if item.get("year"):
        rich(p, str(item["year"]).strip() + "，", size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    rich(p, str(item.get("name", "")), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    tail = [str(item.get(k)) for k in ("level", "award") if item.get(k)]
    if tail:
        rich(p, " " + " ".join(tail), size=sz("body"), color=T["ink"], bold=True, ea=EA)
    if item.get("team"):
        rich(p, "（团队 %s）" % item["team"], size=sz("body"), color=T["muted"], ea=EA)


def sidebar_sections(doc, basics, first):
    for block in (basics.get("sideSections") or []):
        style = block.get("style", "lines")
        lines = [x for x in (block.get("lines") or []) if x.get("label") or x.get("value")]
        bars = [b for b in (block.get("bars") or []) if b.get("label")]
        radar = [a for a in (block.get("radar") or block.get("axes") or []) if a.get("label")]
        if not (lines or bars or radar):
            continue
        section_header(doc, block.get("title") or "技能证书", first=first)
        first = False
        if style == "bars":
            for bar in bars:
                p = body_para(doc, before=0.5, indent=0.42, first_line=-0.42)
                rich(p, "· ", size=sz("body"), color=T["muted"], ea=EA)
                rich(p, "**%s**" % str(bar["label"]).rstrip("：:"), size=sz("body"), color=T["ink"], ea=EA)
                if bar.get("level"):
                    rich(p, "：" + str(bar["level"]), size=sz("body"), color=T["muted"], ea=EA)
        elif style == "radar":
            p = body_para(doc, before=0.5, indent=0.42, first_line=-0.42)
            rich(p, "· ", size=sz("body"), color=T["muted"], ea=EA)
            rich(p, "**能力维度：**", size=sz("body"), color=T["ink"], ea=EA)
            rich(p, "、".join(str(a["label"]) for a in radar), size=sz("body"), color=T["muted"], ea=EA)
        else:
            for line in lines:
                p = body_para(doc, before=0.5, indent=0.42, first_line=-0.42)
                rich(p, "· ", size=sz("body"), color=T["muted"], ea=EA)
                if line.get("label"):
                    rich(p, "**%s：**" % line["label"], size=sz("body"), color=T["ink"], ea=EA)
                rich(p, str(line.get("value", "")), size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)
    return first


def render_ats(doc, spec):
    try:
        scale = float(spec.get("layoutScale") or 1.0)
    except Exception:
        scale = 1.0
    _cur["scale"] = max(0.82, min(1.0, scale))

    section = doc.sections[0]
    section.left_margin = Cm(A["pad_l"])
    section.right_margin = Cm(A["pad_r"])
    section.top_margin = Cm(A["pad_t"])
    section.bottom_margin = Cm(A["pad_b"])

    basics = spec.get("basics") or {}
    photo = basics.get("photo") if basics.get("photo") and os.path.exists(basics["photo"]) else None
    header_block(doc, basics, bool(photo))

    first = True
    for sec in (spec.get("sections") or []):
        kind = sec.get("type", "text")
        items = sec.get("items") or []
        paragraphs = sec.get("paragraphs") or []
        if not items and not paragraphs:
            continue
        section_header(doc, sec.get("title") or "小节", first=first)
        first = False
        if kind == "education":
            for item in items:
                education_item(doc, item)
        elif kind == "experience":
            for item in items:
                experience_item(doc, item)
        elif kind == "bullets":
            for item in items:
                bullet_item(doc, item)
        elif kind == "awards":
            for item in items:
                award_item(doc, item)
        else:
            for text in paragraphs:
                p = body_para(doc, before=0.8)
                rich(p, text, size=sz("body"), color=T["ink"], ea=EA, latin=LATIN)

    first = sidebar_sections(doc, basics, first)

    if photo:
        x = A["page_w"] - A["pad_r"] - A["photo_w"]
        add_floating_photo(doc.paragraphs[0], photo, A["photo_w"], A["photo_h"],
                           x, A["photo_top"])
    return doc


def render(doc, spec):
    return render_ats(doc, spec)
