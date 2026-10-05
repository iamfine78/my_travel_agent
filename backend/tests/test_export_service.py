# ============================================
# 导出服务测试
# 覆盖：费用文本格式化、中文字体探测、Markdown / PDF 导出
# PDF 依赖 Windows 系统字体；缺字体时自动跳过。
# ============================================
import pytest

from app.services import export_service as ex


class TestParseCost:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, ""),
            (50, "约50元"),
            (120.4, "约120元"),
            ("成人120元，儿童免费", "成人120元，儿童免费"),
            ("免费", "免费"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_format_cost(self, value, expected):
        assert ex._parse_cost(value) == expected


class TestChineseFont:
    def test_find_font_returns_existing_path_or_empty(self):
        path = ex.find_chinese_font()
        assert path == "" or __import__("pathlib").Path(path).exists()


class TestMarkdownExport:
    def test_title_and_summary(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert isinstance(md, str)
        assert md.startswith("# 西安 旅行规划手册")
        assert "> 西安两日人文美食之旅" in md
        assert "**行程 2 天**" in md

    def test_days_slots_and_activities(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "## 第 1 天" in md
        assert "## 第 2 天" in md
        assert "### 上午" in md and "### 下午" in md and "### 晚上" in md
        assert "- **秦始皇兵马俑博物馆** — 约120元" in md
        assert "  - 怎么玩：建议游玩 3 小时，先看一号坑" in md

    def test_cost_formats(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "约120元" in md          # 数字费用
        assert "人均60元" in md          # 文本费用
        assert "**陕西历史博物馆**\n" in md  # 免费（cost=0）不加费用后缀

    def test_meals_lodging_note(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "**餐饮**：肉夹馍、biangbiang面" in md
        assert "**住宿**：建议住钟楼附近，交通便利" in md
        assert "> 提示：兵马俑需提前预约" in md

    def test_budget_table_and_total(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "## 预算拆分" in md
        assert "| 交通 | 500 |" in md
        assert "| **合计** | **2000** |" in md

    def test_tips_section(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "## 旅行建议" in md
        assert "1. 春秋早晚温差大，注意添衣" in md

    def test_weather_table_when_provided(self, sample_itinerary):
        weather = {"forecasts": [{"date": "2026-10-08", "dayweather": "小雨",
                                  "nightweather": "阴", "daytemp": "18", "nighttemp": "12"}]}
        md = ex.itinerary_to_markdown(sample_itinerary, "西安", weather)
        assert "## 天气预报" in md
        assert "| 10-08 | 小雨转阴 | 18~12℃ |" in md

    def test_no_weather_section_without_data(self, sample_itinerary):
        assert "天气预报" not in ex.itinerary_to_markdown(sample_itinerary, "西安")

    def test_date_hint_shown_only_when_informative(self, sample_itinerary):
        # date_hint "第1天" 与标题重复 → 不单列
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert "**第1天**" not in md
        # 给出额外信息时应单列
        sample_itinerary["days"][0]["date_hint"] = "10月8日 周三"
        assert "**10月8日 周三**" in ex.itinerary_to_markdown(sample_itinerary, "西安")

    def test_empty_itinerary_does_not_crash(self):
        md = ex.itinerary_to_markdown({"days": []}, "未知城市")
        assert "# 未知城市 旅行规划手册" in md
        assert "**行程 0 天**" in md
        assert "预算拆分" not in md

    def test_missing_optional_fields_are_skipped(self):
        itin = {"days": [{"day": 1, "morning": [{"place": "某地"}]}]}
        md = ex.itinerary_to_markdown(itin, "某城")
        assert "- **某地**" in md
        assert "餐饮" not in md and "住宿" not in md


class TestPdfExport:
    def test_pdf_bytes_has_header(self, sample_itinerary):
        if not ex.find_chinese_font():
            pytest.skip("未找到中文字体，跳过 PDF 导出测试")
        data = ex.itinerary_to_pdf_bytes(sample_itinerary, "西安")
        assert isinstance(data, bytes)
        assert data[:4] == b"%PDF"
        assert len(data) > 1000

    def test_pdf_with_weather(self, sample_itinerary):
        if not ex.find_chinese_font():
            pytest.skip("未找到中文字体，跳过 PDF 导出测试")
        weather = {"forecasts": [{"date": "10月8日", "dayweather": "小雨", "daytemp": "18"}]}
        data = ex.itinerary_to_pdf_bytes(sample_itinerary, "西安", weather)
        assert data[:4] == b"%PDF"

    def test_empty_itinerary_still_renders(self):
        if not ex.find_chinese_font():
            pytest.skip("未找到中文字体，跳过 PDF 导出测试")
        data = ex.itinerary_to_pdf_bytes({"days": []}, "未知城市")
        assert data[:4] == b"%PDF"
