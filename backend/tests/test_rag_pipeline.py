# ============================================
# RAG 链路测试（离线）
# 覆盖：攻略目录、Markdown 切块、规则级查询改写、规则级重排、攻略候选提取、一致性校验
# ============================================
import pytest
from langchain_core.documents import Document

from app.agents.tools import rag_tool
from app.rag import guide_catalog, knowledge_validation, vector_db
from app.rag import retriever
from app.services import fallback_candidates


class TestGuideCatalog:
    def test_all_guide_files_exist(self):
        for guide in guide_catalog.GUIDE_CATALOG:
            assert guide.exists, f"攻略文件缺失：{guide.file_name}"

    def test_guide_text_is_not_empty(self):
        for city in guide_catalog.all_settled_cities():
            assert len(guide_catalog.load_guide_text(city)) > 100

    def test_alias_lookup(self):
        assert guide_catalog.get_guide("长安").city == "西安"
        assert guide_catalog.get_guide("魔都").city == "上海"

    def test_unknown_guide_returns_none(self):
        assert guide_catalog.get_guide("大理") is None
        assert guide_catalog.load_guide_text("大理") == ""


class TestSplitMarkdown:
    def test_split_by_heading_keeps_city_metadata(self):
        text = "## 景点\n\n- 兵马俑：世界遗产\n\n## 美食\n\n- 肉夹馍：必吃"
        docs = vector_db.split_markdown(text, city="西安")
        assert len(docs) >= 2
        assert all(d.metadata["city"] == "西安" for d in docs)
        joined = "\n".join(d.page_content for d in docs)
        assert "兵马俑" in joined and "肉夹馍" in joined

    def test_heading_is_kept_in_block(self):
        docs = vector_db.split_markdown("## 交通\n\n地铁很方便", city="北京")
        assert docs
        assert "交通" in docs[0].page_content

    def test_long_block_is_split(self):
        # 50 个短段落，max_chars 调小 → 应切成多块
        text = "## 长攻略\n\n" + "\n\n".join(f"第{i}段介绍内容。" for i in range(50))
        docs = vector_db.split_markdown(text, city="杭州", max_chars=60)
        assert len(docs) > 1
        assert all(d.metadata["city"] == "杭州" for d in docs)

    def test_empty_text_gives_no_docs(self):
        assert vector_db.split_markdown("", city="西安") == []


class TestRuleRewrite:
    def test_expands_known_keywords(self):
        raw = "带小孩亲子游，想吃美食"
        result = rag_tool._rule_rewrite(raw)
        assert result["query"] == raw
        assert "亲子" in result["keywords"]
        assert "小孩" in result["keywords"]
        assert "美食" in result["keywords"]

    def test_keywords_are_deduplicated(self):
        result = rag_tool._rule_rewrite("美食 美食 人文")
        assert len(result["keywords"]) == len(set(result["keywords"]))

    def test_no_rule_hit_gives_empty_keywords(self):
        assert rag_tool._rule_rewrite("随便走走")["keywords"] == []


class TestRuleScore:
    def test_keyword_hits_rank_first(self):
        docs = [
            Document(page_content="西安城墙 门票54元", metadata={"city": "西安"}),
            Document(page_content="成都火锅推荐", metadata={"city": "成都"}),
        ]
        ranked = retriever._rule_score("西安 门票", docs)
        assert ranked[0][0] == 0  # 命中关键词的第 0 篇排第一
        assert ranked[0][1] > ranked[1][1]

    def test_city_bonus_applied(self):
        docs = [Document(page_content="通用介绍", metadata={"city": "西安"})]
        ranked = retriever._rule_score("西安", docs)
        assert ranked[0][1] >= 3  # 城市匹配加分


class TestFallbackCandidates:
    FIELD_LABELS = {"地址", "门票参考", "简介", "提示", "大交通", "市内"}

    def test_extract_from_real_guide_returns_spot_names(self):
        names = fallback_candidates.extract_from_guide("西安")
        assert names, "应能从西安攻略提取到候选地名"
        assert len(names) == len(set(names))  # 去重
        assert len(names) <= 15
        # 必须是真实景点名，而不是「- 地址：…」这类字段被误抽出来
        assert any("兵马俑" in n for n in names)
        assert not (self.FIELD_LABELS & set(names))

    @pytest.mark.parametrize("city", ["西安", "成都", "北京", "上海", "杭州", "重庆"])
    def test_every_guide_yields_spot_names(self, city):
        names = fallback_candidates.extract_from_guide(city)
        assert len(names) >= 5, f"{city} 攻略应至少抽到 5 个景点"
        assert not (self.FIELD_LABELS & set(names)), f"{city} 抽到了字段名：{self.FIELD_LABELS & set(names)}"

    def test_heading_extraction_strips_parenthetical(self):
        text = "## 必去景点\n\n### 故宫博物院（紫禁城）\n- 地址：东城区\n"
        assert fallback_candidates._extract_heading_names(text, 15) == ["故宫博物院"]

    def test_heading_extraction_respects_limit_and_dedup(self):
        text = "### 甲地\n### 乙地\n### 甲地\n"
        assert fallback_candidates._extract_heading_names(text, 1) == ["甲地"]
        assert fallback_candidates._extract_heading_names(text, 15) == ["甲地", "乙地"]

    def test_bullet_fallback_parses_name_colon_desc(self):
        # 仅在攻略没有标题结构时才走这条兜底路径
        text = "- 兵马俑：世界第八大奇迹\n- 华清宫——温泉遗址\n"
        assert fallback_candidates._extract_bullet_names(text, 15) == ["兵马俑", "华清宫"]

    def test_unknown_city_returns_empty(self):
        assert fallback_candidates.extract_from_guide("大理") == []

    def test_format_empty_returns_empty_string(self):
        assert fallback_candidates.format_guide_candidates([], "西安") == ""

    def test_format_contains_city_and_numbers(self):
        text = fallback_candidates.format_guide_candidates(["兵马俑", "华清宫"], "西安")
        assert "西安" in text
        assert "1. 兵马俑" in text
        assert "2. 华清宫" in text


class TestKnowledgeValidation:
    def test_validate_returns_list(self):
        assert isinstance(knowledge_validation.validate(), list)

    def test_guide_files_reported_missing_only_if_absent(self):
        problems = knowledge_validation.validate()
        missing = [p for p in problems if "攻略文件缺失" in p]
        assert missing == [], f"攻略文件不应缺失：{missing}"

    def test_validate_and_report_returns_bool(self):
        assert isinstance(knowledge_validation.validate_and_report(verbose=False), bool)
