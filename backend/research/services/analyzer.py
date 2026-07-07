from collections import Counter
import json
import re

from .llm import LLMError, chat_json, llm_enabled, set_llm_status
from .rag import env_int, format_evidence_pack, retrieve_evidence


HOTSPOT_LIMIT = 8
CURRENT_HOTSPOT_GENERATIONS = {"llm_keywords", "metadata_keywords"}


def analyze_records(records):
    try:
        return _analyze_with_pandas(records)
    except Exception:
        return _analyze_with_standard_library(records)


def hotspot_generation(hotspots):
    generations = {
        item.get("generation")
        for item in (hotspots or [])
        if isinstance(item, dict) and item.get("generation")
    }
    if "llm_keywords" in generations:
        return "llm_keywords"
    if "metadata_keywords" in generations:
        return "metadata_keywords"
    return "legacy_keywords"


def uses_legacy_hotspots(hotspots):
    return bool(hotspots) and hotspot_generation(hotspots) not in CURRENT_HOTSPOT_GENERATIONS


def _analyze_with_pandas(records):
    import pandas as pd

    rows = [_row(record) for record in records]
    df = pd.DataFrame(rows)
    if df.empty:
        return _empty_result()
    df["year"] = df["year"].fillna("未知")

    trends = [
        {"year": str(year), "count": int(count)}
        for year, count in df.groupby("year").size().sort_index().items()
    ]
    sources = [
        {"source": str(source), "count": int(count)}
        for source, count in df.groupby("source").size().sort_values(ascending=False).items()
    ]

    max_year = max([int(y) for y in df["year"] if str(y).isdigit()] or [0])
    keyword_counter, recent_counter, keyword_source = _topic_counters(records, max_year)
    hotspots = _build_hotspots(keyword_counter, keyword_source)
    gaps = _build_gaps(keyword_counter, recent_counter, records)
    summary = _summary_text(hotspots, trends, gaps)
    llm_result = _try_llm_analysis(records, hotspots, trends, gaps)
    if llm_result:
        gaps = llm_result.get("gaps") or gaps
        summary = llm_result.get("summary") or summary
    return {
        "hotspots": hotspots,
        "trends": trends,
        "source_distribution": sources,
        "gaps": gaps,
        "summary": summary,
    }


def _analyze_with_standard_library(records):
    if not records:
        return _empty_result()
    years = Counter()
    sources = Counter()
    max_year = max([_year(record) for record in records if _year(record)] or [0])
    keywords, recent, keyword_source = _topic_counters(records, max_year)
    for record in records:
        years[str(_year(record) or "未知")] += 1
        sources[record.get("source", "Unknown")] += 1
    hotspots = _build_hotspots(keywords, keyword_source)
    gaps = _build_gaps(keywords, recent, records)
    trends = [{"year": year, "count": count} for year, count in sorted(years.items())]
    sources = [{"source": source, "count": count} for source, count in sources.most_common()]
    summary = _summary_text(hotspots, trends, gaps)
    llm_result = _try_llm_analysis(records, hotspots, trends, gaps)
    if llm_result:
        gaps = llm_result.get("gaps") or gaps
        summary = llm_result.get("summary") or summary
    return {
        "hotspots": hotspots,
        "trends": trends,
        "source_distribution": sources,
        "gaps": gaps,
        "summary": summary,
    }


def _row(record):
    return {
        "title": record.get("title"),
        "source": record.get("source"),
        "year": str(_year(record) or "未知"),
        "keyword_count": len(record.get("keywords", [])),
    }


def _year(record):
    value = record.get("published_at")
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except Exception:
        return None


def _topic_counters(records, max_year):
    keyword_counter = Counter()
    recent_counter = Counter()
    topic_terms_by_record, keyword_source = _topic_terms_for_records(records)
    for record, topic_terms in zip(records, topic_terms_by_record):
        keyword_counter.update(topic_terms)
        year = _year(record)
        if year and max_year and year >= max_year - 1:
            recent_counter.update(topic_terms)
    return keyword_counter, recent_counter, keyword_source


def _topic_terms_for_records(records):
    if llm_enabled():
        terms_by_record = _extract_llm_topic_terms_batch(records)
        llm_record_count = sum(1 for terms in terms_by_record if terms)
        if not llm_record_count:
            terms_by_record = []
            for record in records:
                terms = _extract_llm_topic_terms(record)
                if terms:
                    llm_record_count += 1
                terms_by_record.append(terms)
        if llm_record_count:
            return terms_by_record, "llm"

    terms_by_record = []
    for record in records:
        terms = _fallback_topic_terms(record)
        if terms:
            terms = terms[:5]
        terms_by_record.append(terms)
    return terms_by_record, "metadata"


def _extract_llm_topic_terms_batch(records):
    items = []
    for index, record in enumerate(records or [], start=1):
        title = str(record.get("title") or "").strip()
        abstract = str(record.get("abstract") or "").strip()
        if not title and not abstract:
            continue
        items.append(
            {
                "index": index,
                "title": title[:260],
                "abstract": abstract[:1000],
            }
        )
    if not items:
        return [[] for _ in records]
    try:
        payload = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是科研文献主题词批量抽取助手。你会收到多篇文献的标题和摘要。"
                        "必须分别为每篇文献提取 3-5 个主题词。不要输出数据库分类号或元数据标签，"
                        "例如 cs.CL、cs.LG、q-bio、Biological science。不要输出 research、study、method、analysis 这类过泛词。"
                        "输出必须是合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"文献列表 JSON：{json.dumps(items, ensure_ascii=False)}\n\n"
                        "请只输出 JSON，不要 Markdown："
                        "{\"items\": [{\"index\": 1, \"keywords\": [\"主题词1\", \"主题词2\"]}]}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=env_int("LLM_KEYWORD_BATCH_MAX_TOKENS", 1200, minimum=500, maximum=3000),
        )
        by_index = _coerce_batch_topic_terms(payload)
        return [_clean_topic_terms(by_index.get(index, []))[:5] for index in range(1, len(records or []) + 1)]
    except (LLMError, Exception):
        return [[] for _ in records]


def _extract_llm_topic_terms(record):
    title = str(record.get("title") or "").strip()
    abstract = str(record.get("abstract") or "").strip()
    if not title and not abstract:
        return []
    try:
        payload = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是科研文献主题词抽取助手。只根据用户提供的标题和摘要提取主题词。"
                        "不要输出数据库分类号或元数据标签，例如 cs.CL、cs.LG、q-bio、Biological science。"
                        "不要输出 research、study、method、analysis 这类过泛词。"
                        "输出必须是合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"标题：{title}\n\n"
                        f"摘要：{abstract[:2200]}\n\n"
                        "请提取 3-5 个能够代表这篇文献主题的关键词或短语。"
                        "优先使用论文原文中的学术短语；英文文献用英文短语，中文文献用中文短语。"
                        "只输出 JSON：{\"keywords\": [\"主题词1\", \"主题词2\"]}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=env_int("LLM_KEYWORD_MAX_TOKENS", 260, minimum=120, maximum=800),
        )
        return _clean_topic_terms(_coerce_topic_terms(payload))[:5]
    except (LLMError, Exception):
        return []


def _coerce_batch_topic_terms(payload):
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ["items", "documents", "records", "results", "文献", "结果"]:
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        if items is None:
            items = []
            for key, value in payload.items():
                if str(key).isdigit():
                    items.append({"index": key, "keywords": value})
    else:
        items = []

    output = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(_first_present(item, "index", "id", "序号", "编号") or 0)
        except (TypeError, ValueError):
            index = 0
        if not index:
            continue
        terms = _coerce_topic_terms(item)
        if terms:
            output[index] = terms
    return output


def _coerce_topic_terms(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in [
        "keywords",
        "topic_keywords",
        "topic_terms",
        "terms",
        "themes",
        "topics",
        "主题词",
        "关键词",
        "主题",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for value in payload.values():
        if isinstance(value, dict):
            terms = _coerce_topic_terms(value)
            if terms:
                return terms
    return []


def _fallback_topic_terms(record):
    return _clean_topic_terms(record.get("keywords", []))[:5]


def _clean_topic_terms(terms):
    output = []
    seen = set()
    for term in terms or []:
        if isinstance(term, dict):
            term = _first_present(term, "keyword", "term", "name", "topic", "关键词", "主题词")
        value = _normalize_topic_term(term)
        key = value.lower()
        if not value or key in seen or _looks_like_metadata_keyword(value):
            continue
        output.append(value)
        seen.add(key)
        if len(output) >= 5:
            break
    return output


def _normalize_topic_term(term):
    value = str(term or "").strip()
    value = re.sub(r"^[\s,，;；:：\-—•\d.、]+", "", value)
    value = re.sub(r"[\s,，;；:：\-—•]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value[:80]


def _looks_like_metadata_keyword(value):
    text = str(value or "").strip()
    lowered = text.lower()
    if re.fullmatch(r"[a-z]+(\.[a-z0-9-]+)+", lowered):
        return True
    if lowered in {
        "biological science",
        "computer science",
        "programming language",
        "research",
        "study",
        "method",
        "analysis",
        "article",
        "paper",
    }:
        return True
    return False


def _build_hotspots(keyword_counter, keyword_source):
    if keyword_source == "llm":
        evidence_template = "由大模型基于每篇文献标题和摘要提取主题词后统计，出现在 {count} 篇文献中。"
        generation = "llm_keywords"
    else:
        evidence_template = "当前大模型不可用，使用文献来源返回的关键词字段统计，出现 {count} 次。"
        generation = "metadata_keywords"
    return [
        {
            "keyword": keyword,
            "count": count,
            "evidence": evidence_template.format(count=count),
            "generation": generation,
        }
        for keyword, count in keyword_counter.most_common(HOTSPOT_LIMIT)
    ]


def _try_llm_analysis(records, hotspots, trends, heuristic_gaps):
    if not llm_enabled():
        return {}
    try:
        evidence = retrieve_evidence(
            " ".join(item.get("keyword", "") for item in hotspots[:6]),
            records,
            limit=env_int("RAG_ANALYSIS_TOP_K", env_int("RAG_TOP_K", 5, minimum=1, maximum=20), minimum=1, maximum=20),
        )
        if not evidence:
            return {}
        payload = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是科研文献研究空白分析助手。只能依据证据包、统计热点和候选空白生成结论。"
                        "必须避免幻觉：不能编造不存在的论文、实验、数据集或引用；证据不足时写“证据不足”。"
                        "输出必须是合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "真实文献证据包：\n"
                        f"{format_evidence_pack(evidence)}\n\n"
                        f"统计热点：{hotspots[:8]}\n"
                        f"年份趋势：{trends}\n"
                        f"规则候选空白：{heuristic_gaps[:5]}\n\n"
                        "请只输出一个合法 JSON 对象，不要输出 Markdown，不要尾逗号。所有字符串必须使用英文双引号。格式为：\n"
                        "{\n"
                        '  "summary": "一句严谨总结，必须包含证据编号",\n'
                        '  "gaps": [\n'
                        "    {\n"
                        '      "title": "具体研究空白标题",\n'
                        '      "category": "验证与复现/评测基准/可解释性/数据覆盖/泛化迁移/方法落地/其他",\n'
                        '      "rationale": "基于证据编号说明为什么是空白",\n'
                        '      "suggested_question": "可执行研究问题",\n'
                        '      "confidence": "较高/中/初步",\n'
                        '      "evidence_count": 1\n'
                        "    }\n"
                        "  ]\n"
                        "}\n"
                        "最多 5 条 gaps，每条必须引用至少一个证据编号，如[R1]。"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=env_int("LLM_ANALYSIS_MAX_TOKENS", 1500, minimum=600, maximum=4000),
        )
        payload = _unwrap_payload(payload)
        raw_gaps = _extract_gap_items(payload)
        gaps = [_clean_llm_gap(item) for item in (raw_gaps or []) if isinstance(item, dict)]
        gaps = [item for item in gaps if item.get("title") and item.get("rationale")]
        if not gaps:
            set_llm_status("当前大模型返回 JSON 但缺少有效研究空白字段，已使用规则模板兜底。")
        summary = _first_present(payload, "summary", "conclusion", "分析总结", "总结") or ""
        return {"summary": summary, "gaps": gaps[:5]} if gaps else {}
    except (LLMError, Exception):
        return {}


def _clean_llm_gap(item):
    try:
        evidence_count = int(_first_present(item, "evidence_count", "evidenceCount", "证据条数", "证据数量") or 0)
    except (TypeError, ValueError):
        evidence_count = 0
    return {
        "title": str(_first_present(item, "title", "name", "标题", "研究空白标题", "具体研究空白标题") or "")[:180],
        "category": str(_first_present(item, "category", "type", "类别", "分类") or "其他")[:40],
        "rationale": str(_first_present(item, "rationale", "reason", "basis", "理由", "依据", "说明") or "")[:600],
        "suggested_question": str(_first_present(item, "suggested_question", "question", "research_question", "研究问题", "建议问题") or "")[:240],
        "confidence": str(_first_present(item, "confidence", "可信度", "置信度") or "初步")[:20],
        "evidence_count": evidence_count,
        "generation": "llm_rag",
    }


def _unwrap_payload(payload):
    if not isinstance(payload, dict):
        return {}
    for key in ["result", "data", "analysis", "output", "分析结果", "结果"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _extract_gap_items(payload):
    direct = _first_present(
        payload,
        "gaps",
        "research_gaps",
        "gap_analysis",
        "potential_gaps",
        "identified_gaps",
        "frontier_gaps",
        "gap_identification",
        "研究空白",
        "空白",
        "潜在研究空白",
        "研究空白分析",
        "空白识别",
    )
    items = _coerce_gap_items(direct)
    if items:
        return items
    if _looks_like_gap(payload):
        return [payload]
    if isinstance(payload, dict):
        for value in payload.values():
            items = _coerce_gap_items(value)
            if items:
                return items
            if isinstance(value, dict):
                nested = _extract_gap_items(value)
                if nested:
                    return nested
    return []


def _coerce_gap_items(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if _looks_like_gap(value):
            return [value]
        dict_values = [item for item in value.values() if isinstance(item, dict)]
        if dict_values and any(_looks_like_gap(item) for item in dict_values):
            return dict_values
    return []


def _looks_like_gap(value):
    if not isinstance(value, dict):
        return False
    keys = set(value.keys())
    return bool(
        keys
        & {
            "title",
            "name",
            "标题",
            "研究空白标题",
            "rationale",
            "reason",
            "理由",
            "依据",
            "suggested_question",
            "question",
            "研究问题",
        }
    )


def _first_present(payload, *names):
    if not isinstance(payload, dict):
        return None
    for name in names:
        value = payload.get(name)
        if value:
            return value
    return None


def _build_gaps(keyword_counter, recent_counter, records):
    records = records or []
    primary_keyword = _first_keyword(keyword_counter)
    candidates = []

    for index, (keyword, recent_count) in enumerate(recent_counter.most_common(3)):
        total = keyword_counter.get(keyword, 0)
        if total <= 2 or recent_count / max(total, 1) >= 0.5:
            candidates.append(_keyword_gap(keyword, recent_count, total, index))

    for group in _gap_signal_groups(primary_keyword):
        count = _count_records_with_signals(records, group["signals"])
        if count:
            candidates.append(
                {
                    "title": group["title"],
                    "rationale": group["rationale"].format(count=count),
                    "suggested_question": group["question"],
                    "confidence": _confidence(count, len(records)),
                    "category": group["category"],
                    "evidence_count": count,
                    "generation": "rules",
                    "score": group["priority"] + count,
                }
            )

    missing_abstract = sum(1 for record in records if not record.get("abstract"))
    missing_keywords = sum(1 for record in records if not record.get("keywords"))
    if missing_abstract or missing_keywords:
        candidates.append(
            {
                "title": "跨库元数据完整性不足",
                "rationale": (
                    f"当前检索结果中有 {missing_abstract} 篇缺少摘要、{missing_keywords} 篇缺少关键词，"
                    "会影响后续综述、热点分类和实验方案生成的稳定性。"
                ),
                "suggested_question": "如何结合 DOI、PMID、arXiv ID 对缺失元数据进行补全和可信度标注？",
                "confidence": _confidence(missing_abstract + missing_keywords, len(records)),
                "category": "数据质量",
                "evidence_count": missing_abstract + missing_keywords,
                "generation": "rules",
                "score": 65 + missing_abstract + missing_keywords,
            }
        )

    gaps = _dedupe_gap_candidates(candidates)
    if not gaps:
        gaps.append(
            {
                "title": "跨库数据质量与实验验证衔接不足",
                "rationale": "检索结果显示该主题已有一定研究基础，但从文献结论到可执行实验方案仍缺少统一流程。",
                "suggested_question": "如何将跨库文献证据自动转化为可审查的实验设计？",
                "confidence": "中",
                "category": "流程衔接",
                "evidence_count": len(records),
                "generation": "rules",
            }
        )
    return gaps[:5]


def _keyword_gap(keyword, recent_count, total, index):
    templates = [
        {
            "title": f"{keyword} 的外部验证证据不足",
            "rationale": (
                f"关键词“{keyword}”在近年结果中出现 {recent_count} 次，但当前样本内累计只有 {total} 条相关证据，"
                "更适合作为可重复实验或外部数据集验证方向。"
            ),
            "question": f"在独立数据集或真实应用场景中，{keyword} 的结论是否仍然稳定？",
            "category": "验证与复现",
        },
        {
            "title": f"{keyword} 的评价标准尚不统一",
            "rationale": (
                f"近期文献集中讨论“{keyword}”，但检索结果中可直接比较的指标、基准或实验协议仍然有限，"
                "容易导致不同研究之间结论难以横向对比。"
            ),
            "question": f"能否为 {keyword} 构建统一的评价指标和可复现实验流程？",
            "category": "评测基准",
        },
        {
            "title": f"{keyword} 的应用边界仍需明确",
            "rationale": (
                f"“{keyword}”作为热点主题出现较集中，但现有记录对适用场景、失败条件和泛化边界描述不足，"
                "后续可以围绕场景迁移和边界条件开展实验。"
            ),
            "question": f"{keyword} 在不同任务、数据来源或学科场景中的适用边界是什么？",
            "category": "泛化边界",
        },
    ]
    template = templates[index % len(templates)]
    return {
        "title": template["title"],
        "rationale": template["rationale"],
        "suggested_question": template["question"],
        "confidence": "中",
        "category": template["category"],
        "evidence_count": recent_count,
        "generation": "rules",
        "score": 90 - index,
    }


def _gap_signal_groups(primary_keyword):
    subject = primary_keyword or "该研究主题"
    return [
        {
            "category": "评测基准",
            "priority": 86,
            "signals": ["benchmark", "evaluation", "metric", "baseline", "protocol", "llm-as-a-judge", "automated evaluation"],
            "title": f"{subject} 的自动化评测基准不足",
            "rationale": "有 {count} 条真实文献记录涉及评测、指标或基准，但缺少统一对照协议会削弱结论可比性。",
            "question": f"如何为 {subject} 建立覆盖准确性、可靠性和人工一致性的综合评测基准？",
        },
        {
            "category": "可解释性",
            "priority": 82,
            "signals": ["interpretability", "explainable", "transparent", "trustworthy", "reliability", "faithfulness", "provenance", "grounding"],
            "title": f"{subject} 的可解释性与可信证据链不足",
            "rationale": "有 {count} 条记录涉及可信、可解释、溯源或一致性问题，说明该方向仍需要更清晰的证据链设计。",
            "question": f"如何让 {subject} 的判断过程、来源证据和错误边界可以被审查？",
        },
        {
            "category": "数据覆盖",
            "priority": 78,
            "signals": ["dataset", "corpus", "annotation", "metadata", "data quality", "sample size", "cohort"],
            "title": f"{subject} 的数据覆盖与样本代表性不足",
            "rationale": "有 {count} 条记录提到数据集、语料、标注或样本问题，提示现有研究可能受数据覆盖范围影响。",
            "question": f"不同数据来源、样本规模和标注质量会如何影响 {subject} 的研究结论？",
        },
        {
            "category": "泛化迁移",
            "priority": 74,
            "signals": ["domain", "generalization", "transfer", "cross-domain", "real-world", "deployment", "adaptation"],
            "title": f"{subject} 的跨场景泛化能力仍不清晰",
            "rationale": "有 {count} 条记录涉及领域迁移、真实场景或部署问题，但仍缺少跨任务、跨数据源的系统比较。",
            "question": f"{subject} 在不同学科、任务和真实场景中是否具备稳定泛化能力？",
        },
        {
            "category": "方法落地",
            "priority": 70,
            "signals": ["experiment", "workflow", "pipeline", "human review", "clinical", "application", "implementation"],
            "title": f"{subject} 从方法到可执行流程的衔接不足",
            "rationale": "有 {count} 条记录涉及实验、流程或实际应用，但从文献结论到可操作方案之间仍需要标准化转化步骤。",
            "question": f"如何把 {subject} 的文献证据转化为可复用、可审计的实验设计流程？",
        },
    ]


def _count_records_with_signals(records, signals):
    count = 0
    for record in records:
        text = _record_text(record)
        if any(signal in text for signal in signals):
            count += 1
    return count


def _record_text(record):
    keywords = " ".join(str(item) for item in record.get("keywords", []))
    return " ".join(
        [
            str(record.get("title") or ""),
            str(record.get("abstract") or ""),
            keywords,
            str(record.get("source") or ""),
        ]
    ).lower()


def _first_keyword(keyword_counter):
    for keyword, _ in keyword_counter.most_common(1):
        return keyword
    return ""


def _confidence(count, total):
    if total and count / total >= 0.45:
        return "较高"
    if count >= 2:
        return "中"
    return "初步"


def _dedupe_gap_candidates(candidates):
    selected = []
    used_titles = set()
    used_categories = set()
    for item in sorted(candidates, key=lambda row: row.get("score", 0), reverse=True):
        title = item.get("title", "")
        category = item.get("category", "")
        if title in used_titles:
            continue
        if category in used_categories and len(selected) >= 3:
            continue
        clean_item = dict(item)
        clean_item.pop("score", None)
        selected.append(clean_item)
        used_titles.add(title)
        used_categories.add(category)
        if len(selected) >= 5:
            break
    return selected


def _summary_text(hotspots, trends, gaps):
    top = "、".join(item["keyword"] for item in hotspots[:5]) or "暂无明显热点"
    years = [item["year"] for item in trends if item["year"] != "未知"]
    year_text = f"{min(years)} 到 {max(years)}" if years else "未知年份"
    gap_text = gaps[0]["title"] if gaps else "暂无明确空白"
    return (
        f"本次分析覆盖 {year_text} 的文献数据。热点方向主要包括 {top}。"
        f"从研究空白看，优先建议关注“{gap_text}”，并结合实验设计进行验证。"
    )


def _empty_result():
    return {
        "hotspots": [],
        "trends": [],
        "source_distribution": [],
        "gaps": [],
        "summary": "暂无可分析文献。",
    }
