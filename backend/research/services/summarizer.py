from collections import Counter

from .llm import LLMError, chat_completion, fallback_notice, generation_notice, llm_enabled, set_llm_status
from .rag import env_int, format_evidence_pack, retrieve_evidence


def generate_review(query, records):
    llm_text = _try_llm_review(query, records)
    if llm_text:
        return llm_text
    return _heuristic_review(query, records)


def _try_llm_review(query, records):
    if not llm_enabled():
        return ""
    try:
        evidence = retrieve_evidence(
            query,
            records,
            limit=env_int("RAG_REVIEW_TOP_K", env_int("RAG_TOP_K", 5, minimum=1, maximum=20), minimum=1, maximum=20),
        )
        if not evidence:
            return ""
        docs = format_evidence_pack(evidence)
        messages = _review_messages(query, docs)
        max_tokens = env_int("LLM_REVIEW_MAX_TOKENS", 2800, minimum=1200, maximum=5000)
        content = chat_completion(
            messages,
            temperature=0.15,
            max_tokens=max_tokens,
        )
        if content and _looks_incomplete_review(content):
            set_llm_status("当前大模型综述输出过短或疑似截断，已自动请求续写。")
            continuation = chat_completion(
                messages
                + [
                    {"role": "assistant", "content": content[:3000]},
                    {
                        "role": "user",
                        "content": "上一条综述过短或疑似中断。请从中断处继续补全文献综述，补齐缺失小节，不要重复已经写过的内容，仍然必须引用证据编号。",
                    },
                ],
                temperature=0.12,
                max_tokens=1600,
            )
            if continuation:
                content = f"{content.rstrip()}\n\n{continuation.lstrip()}"
        return generation_notice(len(evidence)) + content if content else ""
    except (LLMError, Exception):
        return ""


def _review_messages(query, docs):
    return [
        {
            "role": "system",
            "content": (
                "你是严谨但表达自然的科研文献 RAG 助手。只能基于用户提供的 Milvus 召回证据包回答；"
                "所有关键判断都要标注证据编号，如[R1]。不要写空泛套话，不要机械套用固定综述模板。"
                "如果证据只能支持有限结论，就直接说明“证据不足”。不得编造论文、作者、DOI、PMID、实验结果或引用。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"研究主题：{query}\n\n"
                f"Milvus RAG 召回证据包：\n{docs}\n\n"
                "请用中文 Markdown 回答，控制在 700-1200 字，风格像基于检索资料给研究者解释，不要像通用模板。\n"
                "结构如下：\n"
                "## 直接回答\n"
                "先用 2-4 句话回答这个主题目前从证据中能看出什么，必须引用证据编号。\n"
                "## 证据依据\n"
                "按证据自然展开 3-5 个要点，每个要点说明“哪条证据支持了什么”，不要逐篇机械罗列。\n"
                "## 证据边界\n"
                "说明当前检索证据还不能证明什么，以及后续最值得继续查证的问题。\n"
                "最后一句必须完整结束，不要中途停止。"
            ),
        },
    ]


def _looks_incomplete_review(content):
    text = str(content or "").strip()
    required = ["## 直接回答", "## 证据依据", "## 证据边界"]
    if len(text) < 380:
        return True
    if any(section not in text for section in required):
        return True
    return text[-1] not in "。.!！?？）)]》”’`"


def _heuristic_review(query, records):
    keywords = Counter()
    sources = Counter()
    years = []
    for item in records:
        keywords.update(item.get("keywords", []))
        sources[item.get("source", "Unknown")] += 1
        if item.get("published_at"):
            years.append(str(item["published_at"])[:4])

    top_keywords = "、".join([kw for kw, _ in keywords.most_common(8)]) or "暂无关键词"
    source_text = "，".join(f"{name} {count} 篇" for name, count in sources.items())
    year_text = f"{min(years)}-{max(years)}" if years else "未知时间范围"
    representative = records[:3]
    rep_text = "\n".join(
        f"- {item['title']}：{_first_sentence(item.get('abstract', ''))}"
        for item in representative
    )

    return (
        fallback_notice() +
        f"## 结构化文献综述：{query}\n\n"
        f"### 研究背景\n"
        f"本次检索覆盖 {len(records)} 篇相关文献，来源包括 {source_text or '演示数据'}，"
        f"时间范围主要集中在 {year_text}。文献显示，该主题正在与 {top_keywords} 等方向发生交叉。\n\n"
        f"### 主要方法\n"
        f"现有研究多采用文献挖掘、统计分析、机器学习建模、实验验证和多源数据整合等方法，"
        f"其中高频关键词反映了当前技术路线和应用场景。\n\n"
        f"### 代表性成果\n{rep_text}\n\n"
        f"### 局限性\n"
        f"当前研究仍存在样本规模有限、跨数据库元数据不一致、实验验证不足和结果可解释性不强等问题。\n\n"
        f"### 简明摘要\n"
        f"总体来看，{query} 具有较强研究价值。后续工作可以围绕高频主题进行系统比较，"
        f"并针对低覆盖但增长明显的方向设计验证实验。"
    )


def _first_sentence(text):
    text = (text or "").strip()
    if not text:
        return "该文献与当前主题相关，但摘要信息较少。"
    for sep in [". ", "。"]:
        if sep in text:
            return text.split(sep)[0].strip() + ("。" if sep == "。" else ".")
    return text[:140]
