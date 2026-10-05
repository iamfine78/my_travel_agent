# ============================================
# 导出服务：行程 → Markdown / 中文 PDF
# 原理：
#   - Markdown：纯字符串拼接，结构清晰可二次编辑
#   - PDF：fpdf2 库 + 注册 Windows 系统黑体（simhei.ttf），
#     旅行手册风格排版：封面 / 分天章节卡片 / 预算条形图 / 建议页 / 页脚页码 / 景点图片
# 中文 PDF 关键点：
#   1) 必须先 add_font 注册中文字体（fpdf2 内置字体只有英文）
#   2) multi_cell 自动换行；emoji/生僻字可能缺字形（全部用中文/ASCII）
# ============================================
import logging
from io import BytesIO
from pathlib import Path

import httpx
from fpdf import FPDF

logger = logging.getLogger(__name__)

# Windows 中文字体候选（按优先级）
FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/simhei.ttf"),    # 黑体
    Path("C:/Windows/Fonts/msyh.ttc"),      # 微软雅黑
    Path("C:/Windows/Fonts/simsun.ttc"),    # 宋体
]

# 手册配色（与前端蓝紫主题一致）
C_MAIN = (99, 102, 241)      # 主色 indigo
C_ACCENT = (139, 92, 246)    # 辅色 violet
C_DARK = (49, 46, 129)       # 封面深底
C_LIGHT = (237, 233, 254)    # 时段标签浅紫底
C_TEXT = (40, 40, 50)        # 正文
C_GRAY = (120, 120, 130)     # 辅助灰
C_GREEN = (22, 163, 74)      # 免费
C_AMBER = (180, 83, 9)       # 收费


def find_chinese_font() -> str:
    """找可用的中文字体文件路径。"""
    for f in FONT_CANDIDATES:
        if f.exists():
            return str(f)
    return ""


# ---------- PDF 手册渲染 ----------
class ManualFPDF(FPDF):
    """手册风 PDF：自动页脚页码。"""

    def footer(self):
        if self.page_no() <= 1:
            return  # 封面不加页码
        self.set_y(-14)
        self.set_font("cn", "", 8)
        self.set_text_color(*C_GRAY)
        self.cell(0, 6, f"- {self.page_no() - 1} -", align="C")


def _fetch_image(url: str) -> BytesIO | None:
    """下载景点图片（失败返回 None，不阻塞导出）。"""
    try:
        r = httpx.get(url, timeout=5)
        if r.status_code == 200 and r.content[:3] in (b"\xff\xd8\xff", b"\x89PNG"):
            return BytesIO(r.content)
    except Exception:
        pass
    return None


def _parse_cost(c) -> str:
    """费用 → 展示文本（免费徽标 / 金额）。"""
    if isinstance(c, (int, float)):
        return "" if not c else f"约{c:.0f}元"
    s = str(c or "").strip()
    return s if s else ""


def _short_date(d: str) -> str:
    """'2026-10-08' → '10-08'（高德日期带年份，展示时截短）。"""
    s = str(d or "")
    return s[5:] if s.startswith("20") and len(s) > 6 else s


def _to_float(v) -> float:
    """宽松转 float：LLM 可能把预算写成字符串，转不动按 0 计。"""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _section_bar(pdf, label: str, value: float, total: float, y: float) -> None:
    """预算条形图：label + 金额 + 色块条。"""
    pdf.set_font("cn", "", 11)
    pdf.set_text_color(*C_TEXT)
    pdf.cell(24, 7, label, new_x="RIGHT")
    pdf.set_font("cn", "", 10)
    pdf.set_text_color(*C_MAIN)
    pdf.cell(28, 7, f"{value:.0f} 元", new_x="RIGHT")
    bar_w = 100 * (value / total) if total else 0
    pdf.set_fill_color(*C_ACCENT)
    pdf.rect(pdf.get_x() + 2, y + 1, bar_w, 5, style="F")
    pdf.ln(9)


def _cover_images(itinerary: dict, limit: int = 3) -> list[BytesIO]:
    """从行程中取前 N 个带图景点的图片（封面横带用）。"""
    got: list[BytesIO] = []
    for day in itinerary.get("days", []):
        for slot in ("morning", "afternoon", "evening"):
            for a in day.get(slot, []):
                if a.get("image_url") and len(got) < limit:
                    img = _fetch_image(a["image_url"])
                    if img:
                        got.append(img)
    return got


def _cover(pdf: FPDF, itinerary: dict, destination: str, weather: dict | None) -> None:
    """封面页：深色主视觉铺满大半页 + 内容垂直分布（无重叠、无大块空白）。"""
    pdf.set_fill_color(*C_DARK)
    pdf.rect(0, 0, 210, 250, style="F")
    pdf.set_text_color(255, 255, 255)

    days = itinerary.get("days", [])
    split = itinerary.get("budget_split") or {}
    total = sum(float(split.get(k) or 0) for k in ("transport", "lodging", "food", "tickets", "other"))

    # 标题区
    pdf.set_y(22)
    pdf.set_font("cn", "", 11)
    pdf.cell(0, 6, "SMART TRIP PLANNER", align="C")
    pdf.set_y(34)
    pdf.set_font("cn", "", 34)
    pdf.cell(0, 22, destination, align="C")  # 34pt 需要足够行高，否则与下一行重叠
    pdf.set_y(60)
    pdf.set_font("cn", "", 11)
    pdf.cell(0, 6, "旅行规划手册", align="C")
    pdf.set_y(68)
    pdf.cell(0, 6, f"行程 {len(days)} 天  |  预算约 {total:.0f} 元", align="C")

    # 景点图片带：3 张并排，固定高度（视觉主元素，放大）
    imgs = _cover_images(itinerary, 3)
    if imgs:
        img_y, img_h, gap = 90, 44, 5
        w = (210 - 14 * 2 - gap * (len(imgs) - 1)) / len(imgs)
        x = 14
        for img in imgs:
            try:
                pdf.image(img, x=x, y=img_y, w=w, h=img_h)
            except Exception:
                logger.warning("封面图片嵌入失败")
            x += w + gap
        summary_y = img_y + img_h + 12
    else:
        summary_y = 104

    # 摘要（白字，自动换行）
    summary = itinerary.get("summary", "")
    if summary:
        pdf.set_y(summary_y)
        pdf.set_font("cn", "", 10)
        pdf.multi_cell(0, 6, summary, align="C")

    # 天气预览（跟随摘要实际高度）
    forecasts = (weather or {}).get("forecasts", [])[:3]
    if forecasts:
        pdf.set_y(max(pdf.get_y() + 8, 168))
        pdf.set_font("cn", "", 9)
        row = "   ".join(
            f"{_short_date(c.get('date', ''))} {c.get('dayweather', '')} {c.get('daytemp', '')}~{c.get('nighttemp', '')}℃"
            for c in forecasts
        )
        pdf.cell(0, 6, row, align="C")

    # 署名（固定位置，在深色块内）
    pdf.set_y(222)
    pdf.set_font("cn", "", 8)
    pdf.set_text_color(190, 190, 220)
    pdf.cell(0, 6, "由智能旅行规划系统生成 · 价格与开放信息请出行前核实", align="C")


def _day_page(pdf: FPDF, day: dict) -> None:
    """分天章节：标题色块 + 上/下午/晚上卡片 + 住宿（不强制新页，由调用方决定换页）。"""
    y = pdf.get_y()
    # 标题色块（画在当前游标处）
    pdf.set_fill_color(*C_MAIN)
    pdf.rect(0, y, 210, 22, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(y + 5)
    pdf.set_font("cn", "", 16)
    pdf.cell(0, 8, f"第 {day.get('day', '')} 天", align="C")
    pdf.ln(9)
    pdf.set_font("cn", "", 9)
    pdf.cell(0, 6, day.get("date_hint", "") or "", align="C")

    pdf.set_y(y + 28)
    slot_names = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}
    for slot, label in slot_names.items():
        acts = day.get(slot, [])
        if not acts:
            continue
        # 时段标签（深紫实底白字，视觉层次更强）
        pdf.set_fill_color(*C_MAIN)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("cn", "", 11)
        pdf.rect(0, pdf.get_y(), 210, 8, style="F")
        pdf.set_x(14)
        pdf.cell(0, 8, label)
        pdf.ln(10)

        pdf.set_text_color(*C_TEXT)
        for a in acts:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("cn", "", 11)
            pdf.set_text_color(*C_TEXT)
            place = a.get("place", "")
            pdf.cell(90, 7, place)
            # 费用徽标：带底色圆角矩形（免费绿 / 收费琥珀），靠右
            cost = _parse_cost(a.get("cost"))
            if cost:
                pdf.set_font("cn", "", 9)
                pdf.set_text_color(255, 255, 255)
                pdf.set_fill_color(*C_GREEN) if "免费" in cost else pdf.set_fill_color(*C_AMBER)
                pdf.cell(0, 6, f"  {cost}  ", fill=True, align="R")
            pdf.ln(7)
            pdf.set_x(pdf.l_margin)
            # 地址（灰）
            addr = a.get("address", "")
            if addr:
                pdf.set_font("cn", "", 9)
                pdf.set_text_color(*C_GRAY)
                pdf.multi_cell(0, 5, f"地址：{addr}")
                pdf.set_x(pdf.l_margin)
            # 游玩建议（深紫）
            guide = a.get("play_guide", "")
            if guide:
                pdf.set_font("cn", "", 9)
                pdf.set_text_color(*C_ACCENT)
                pdf.multi_cell(0, 5, f"[怎么玩] {guide}")
                pdf.set_x(pdf.l_margin)
            pdf.set_text_color(*C_TEXT)
            # 景点图片（右对齐小图；页面剩余空间不足 20mm 时跳过，避免把内容挤到下一页）
            img = _fetch_image(a.get("image_url", "")) if a.get("image_url") else None
            if img:
                try:
                    img_h = 18
                    if pdf.get_y() + img_h + 6 < pdf.page_break_trigger:
                        pdf.image(img, x=210 - 14 - 24, y=pdf.get_y(), w=24, h=img_h)
                        pdf.set_y(pdf.get_y() + img_h)
                        pdf.set_x(pdf.l_margin)
                except Exception:
                    logger.warning(f"图片嵌入失败: {a.get('place')}")
            pdf.ln(1)

    # 餐饮 + 住宿 + 提示
    meals = day.get("meals", [])
    if meals:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("cn", "", 10)
        pdf.set_text_color(*C_TEXT)
        pdf.multi_cell(0, 6, "餐饮：" + "、".join(meals))
    lodging = day.get("lodging", "")
    if lodging:
        pdf.set_fill_color(*C_LIGHT)
        pdf.set_text_color(*C_MAIN)
        pdf.set_font("cn", "", 10)
        pdf.rect(0, pdf.get_y(), 210, 8, style="F")
        pdf.set_x(14)
        pdf.cell(0, 8, "[住宿]")
        pdf.ln(10)
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*C_TEXT)
        pdf.multi_cell(0, 6, lodging)
    note = day.get("note", "")
    if note:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("cn", "", 9)
        pdf.set_text_color(*C_GRAY)
        pdf.multi_cell(0, 5, f"[提示] {note}")


def _budget_page(pdf: FPDF, itinerary: dict) -> None:
    """预算页：5 项条形图 + 合计。"""
    pdf.add_page()
    pdf.set_fill_color(*C_MAIN)
    pdf.rect(0, 0, 210, 18, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(4)
    pdf.set_font("cn", "", 14)
    pdf.cell(0, 9, "预算拆分", align="C")

    split = itinerary.get("budget_split") or {}
    labels = {"transport": "交通", "lodging": "住宿", "food": "餐饮", "tickets": "门票", "other": "其他"}
    total = sum(float(split.get(k) or 0) for k in labels)
    pdf.set_y(34)
    for key, label in labels.items():
        _section_bar(pdf, label, float(split.get(key) or 0), total, pdf.get_y())

    pdf.set_font("cn", "", 12)
    pdf.set_text_color(*C_MAIN)
    pdf.cell(0, 8, f"合计：{total:.0f} 元", align="C")
    pdf.ln(8)
    pdf.set_font("cn", "", 9)
    pdf.set_text_color(*C_GRAY)
    pdf.cell(0, 6, "预算为模型估算，实际以出行消费为准", align="C")


def _tips_page(pdf: FPDF, itinerary: dict) -> None:
    """建议页（不强制新页，紧接预算页内容之后；空间不足时自动换页）。"""
    tips = itinerary.get("tips", [])
    if not tips:
        return
    y = pdf.get_y()
    if y + 40 > pdf.page_break_trigger:
        pdf.add_page()
        y = pdf.get_y()
    pdf.set_fill_color(*C_MAIN)
    pdf.rect(0, y, 210, 18, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(y + 4)
    pdf.set_font("cn", "", 14)
    pdf.cell(0, 9, "旅行建议", align="C")

    pdf.set_y(y + 22)
    pdf.set_text_color(*C_TEXT)
    for i, t in enumerate(tips, 1):
        pdf.set_font("cn", "", 11)
        # 序号圆点
        pdf.set_fill_color(*C_ACCENT)
        pdf.rect(pdf.get_x() + 2, pdf.get_y() + 1, 4, 4, style="F")
        pdf.set_x(24)
        pdf.multi_cell(0, 7, f"{i}. {t}")
        pdf.ln(2)


def itinerary_to_pdf_bytes(itinerary: dict, destination: str, weather: dict | None = None) -> bytes:
    """行程 → 中文旅行手册 PDF 字节流。"""
    font_path = find_chinese_font()
    if not font_path:
        raise RuntimeError("未找到中文字体（需要 Windows 系统字体 simhei.ttf）")

    pdf = ManualFPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_font("cn", "", font_path)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()  # 封面页

    _cover(pdf, itinerary, destination, weather)
    # 每日行程连续排布：封面后第 1 天起新页；后续若剩余空间不足 60mm 才换页，否则紧接上一内容
    for i, day in enumerate(itinerary.get("days", [])):
        if i == 0 or pdf.get_y() + 60 > pdf.page_break_trigger:
            pdf.add_page()
        _day_page(pdf, day)
    _budget_page(pdf, itinerary)
    _tips_page(pdf, itinerary)

    return bytes(pdf.output())


# ---------- Markdown 行程单 ----------
# 结构与 PDF 手册对齐（封面摘要 → 分天 → 预算 → 建议），沿用同一套中文标签与措辞，
# 让用户拿到的 .md 和 .pdf 读起来是同一个东西。相对 PDF 额外给出营业时间。
BUDGET_LABELS = {
    "transport": "交通",
    "lodging": "住宿",
    "food": "餐饮",
    "tickets": "门票",
    "other": "其他",
}

SLOT_LABELS = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}


def itinerary_to_markdown(itinerary: dict, destination: str, weather: dict | None = None) -> str:
    """行程 → Markdown 行程单（可保存、可二次编辑）。"""
    days = itinerary.get("days") or []
    split = itinerary.get("budget_split") or {}
    total = sum(_to_float(split.get(k)) for k in BUDGET_LABELS)

    out: list[str] = [f"# {destination} 旅行规划手册", ""]

    summary = str(itinerary.get("summary", "") or "").strip()
    if summary:
        out += [f"> {summary}", ""]

    meta = f"**行程 {len(days)} 天**"
    if total:
        meta += f" ｜ **预算约 {total:.0f} 元**"
    out += [meta, ""]

    weather_md = _md_weather(weather)
    if weather_md:
        out.append(weather_md)

    for day in days:
        out += ["---", ""]
        out += _md_day(day)

    if split:
        out += ["---", ""]
        out += _md_budget(split, total)

    tips = itinerary.get("tips") or []
    if tips:
        out += ["---", "", "## 旅行建议", ""]
        out += [f"{i}. {t}" for i, t in enumerate(tips, 1)]
        out.append("")

    out += ["---", "", "*由智能旅行规划系统生成 · 价格与开放信息请出行前核实*", ""]
    return "\n".join(out)


def _md_weather(weather: dict | None) -> str:
    """天气预览（最多 3 天），无数据返回空串。"""
    forecasts = (weather or {}).get("forecasts") or []
    if not forecasts:
        return ""
    lines = ["## 天气预报", "", "| 日期 | 天气 | 气温 |", "| :--- | :--- | ---: |"]
    for c in forecasts[:3]:
        day_w = str(c.get("dayweather", "") or "")
        night_w = str(c.get("nightweather", "") or "")
        weather_text = day_w if not night_w or night_w == day_w else f"{day_w}转{night_w}"
        day_t, night_t = c.get("daytemp", ""), c.get("nighttemp", "")
        temp = f"{day_t}~{night_t}℃" if day_t and night_t else ""
        lines.append(f"| {_short_date(c.get('date', ''))} | {weather_text} | {temp} |")
    lines.append("")
    return "\n".join(lines)


def _md_day(day: dict) -> list[str]:
    """一天：标题 + 三个时段 + 餐饮/住宿/提示。"""
    n = day.get("day", "")
    lines = [f"## 第 {n} 天", ""]

    # date_hint 常与标题重复（都是"第N天"），只有提供额外信息时才单列
    date_hint = str(day.get("date_hint", "") or "").strip()
    if date_hint and date_hint not in (f"第{n}天", f"第 {n} 天"):
        lines += [f"**{date_hint}**", ""]

    for slot, label in SLOT_LABELS.items():
        acts = day.get(slot) or []
        if not acts:
            continue
        lines += [f"### {label}", ""]
        for a in acts:
            lines += _md_activity(a)
        lines.append("")

    meals = day.get("meals") or []
    if meals:
        lines += [f"**餐饮**：{'、'.join(str(m) for m in meals)}", ""]

    lodging = str(day.get("lodging", "") or "").strip()
    if lodging:
        lines += [f"**住宿**：{lodging}", ""]

    note = str(day.get("note", "") or "").strip()
    if note:
        lines += [f"> 提示：{note}", ""]

    return lines


def _md_activity(a: dict) -> list[str]:
    """一个活动：加粗地名 + 费用，缩进列出说明/地址/营业时间/玩法。"""
    place = str(a.get("place", "") or "").strip() or "待定地点"
    cost = _parse_cost(a.get("cost"))
    lines = [f"- **{place}**" + (f" — {cost}" if cost else "")]

    desc = str(a.get("description", "") or "").strip()
    if desc:
        lines.append(f"  - {desc}")
    for label, key in (("地址", "address"), ("营业时间", "open_time"), ("怎么玩", "play_guide")):
        val = str(a.get(key, "") or "").strip()
        if val:
            lines.append(f"  - {label}：{val}")
    return lines


def _md_budget(split: dict, total: float) -> list[str]:
    """预算拆分表格 + 合计。"""
    lines = ["## 预算拆分", "", "| 项目 | 金额（元） |", "| :--- | ---: |"]
    for key, label in BUDGET_LABELS.items():
        lines.append(f"| {label} | {_to_float(split.get(key)):.0f} |")
    lines += [
        f"| **合计** | **{total:.0f}** |",
        "",
        "> 预算为模型估算，实际以出行消费为准",
        "",
    ]
    return lines
