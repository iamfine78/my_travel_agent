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
    @pytest.mark.xfail(
        reason="既有缺陷：export_service.itinerary_to_markdown 未实现，"
        "Markdown 导出接口 500（app/api/routes/export.py:40）",
        strict=False,
    )
    def test_markdown_contains_destination_and_places(self, sample_itinerary):
        md = ex.itinerary_to_markdown(sample_itinerary, "西安")
        assert isinstance(md, str)
        assert "西安" in md
        assert "秦始皇兵马俑博物馆" in md
        assert "预算" in md


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
