from .llm import LLMError, chat_completion, fallback_notice, generation_notice, llm_enabled, strip_generation_metadata
from .rag import env_int, evidence_generation_label, format_evidence_pack, retrieve_evidence


SECTION_TITLES = {
    "abstract": "摘要",
    "introduction": "引言",
    "methods": "方法",
    "results": "结果",
    "discussion": "讨论",
}


def generate_draft(section, query, review_text="", experiment_plan=None, notes="", records=None, analysis_payload=None):
    section = section or "introduction"
    title = SECTION_TITLES.get(section, section)
    experiment_plan = experiment_plan or {}
    records = records or []
    analysis_payload = analysis_payload or {}
    clean_review_text = strip_generation_metadata(review_text)
    llm_content = _try_llm_draft(section, title, query, review_text, experiment_plan, notes, records, analysis_payload)
    if llm_content:
        return {"section": title, "content": llm_content, "style": "大模型 + RAG 证据约束"}

    question = experiment_plan.get("question") or query
    goal = experiment_plan.get("goal", "")
    expected = experiment_plan.get("expected_results", "")
    route = experiment_plan.get("route", [])
    route_text = "、".join(route[:4])

    if section == "abstract":
        content = (
            f"本文围绕“{question}”开展研究，首先通过跨库文献检索与结构化综述梳理该方向的研究基础，"
            f"随后结合热点趋势和研究空白分析提出实验设计方案。研究目标是{goal or '提升科研流程中证据整理与方案生成的效率'}。"
            f"预期结果表明，系统化的文献证据、可解释的数据分析和可复核的实验路线能够为后续研究提供有效支撑。"
        )
    elif section == "introduction":
        content = (
            f"随着科研文献数量快速增长，研究者在进入“{question}”相关领域时，需要同时完成文献筛选、"
            "证据整理、热点判断和实验方案构思。传统人工方式效率较低，也容易受到检索范围和个人经验影响。"
            "因此，构建面向科研流程的智能体系统具有现实意义。基于前期文献综述可以看出，当前研究已经形成一定基础，"
            "但在跨库数据整合、结果可解释性和实验验证衔接方面仍存在改进空间。"
        )
    elif section == "methods":
        content = (
            "本研究采用前后端分离和智能体任务编排相结合的方法。首先，通过 PubMed、arXiv 等数据库获取相关文献，"
            "并对标题、作者、摘要、关键词和发布时间等字段进行统一处理。其次，使用 Pandas 对文献数据进行统计分析，"
            "包括关键词频次、年份趋势和来源分布。最后，结合研究空白分析结果生成实验方案。"
            f"本实验的主要技术路线包括：{route_text or '数据采集、清洗、分析、生成和人工审核'}。"
        )
    elif section == "results":
        content = (
            f"实验和系统演示结果显示，围绕“{question}”输入研究主题后，系统能够完成跨库检索、摘要生成、"
            "热点分析、研究空白提示和实验方案输出。可视化结果能够展示文献数量趋势、关键词热度和来源分布。"
            f"{expected or '生成结果可以作为后续科研讨论和论文写作的初始材料。'}"
        )
    else:
        content = (
            f"从结果来看，科学文献研究智能体能够有效降低“{question}”相关文献调研和实验设计的启动成本。"
            "但系统仍需要人工审核来保证研究结论的可靠性，尤其是在文献质量判断、实验条件约束和领域知识细节方面。"
            "后续可进一步引入向量数据库、引用格式管理和更多学术数据库，以提升检索覆盖率和生成内容的可信度。"
        )

    if notes:
        content += f"\n\n补充说明：{notes}"
    if clean_review_text and section in {"introduction", "discussion"}:
        content += "\n\n文献依据：" + clean_review_text[:260].replace("\n", " ")
    return {"section": title, "content": fallback_notice() + content, "style": "规则模板兜底"}


def _try_llm_draft(section, title, query, review_text, experiment_plan, notes, records, analysis_payload):
    if not llm_enabled() or not records:
        return ""
    try:
        evidence = retrieve_evidence(
            query,
            records,
            limit=env_int("RAG_WRITING_TOP_K", env_int("RAG_TOP_K", 5, minimum=1, maximum=20), minimum=1, maximum=20),
        )
        if not evidence:
            return ""
        section_rules = {
            "abstract": "写 180-260 字摘要，包含背景、方法、预期贡献和证据限制。",
            "introduction": "写 300-450 字引言，说明研究背景、问题价值、已有研究和本文切入点。",
            "methods": "写 300-450 字方法章节，强调检索来源、证据整理、统计分析和实验方案，不编造已完成实验。",
            "results": "写 280-420 字结果章节草稿，只描述系统检索、统计和方案生成结果，不编造模型性能数字。",
            "discussion": "写 300-450 字讨论章节，分析意义、局限、风险和后续工作。",
        }
        clean_review_text = strip_generation_metadata(review_text)
        clean_experiment_plan = _clean_payload(experiment_plan)
        clean_analysis_payload = _clean_payload(analysis_payload)
        content = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "你是论文写作助手。必须基于证据包、综述和实验方案写作，关键判断标注[R1]等证据编号。"
                        "不得编造作者、文献、实验结果、性能指标或已经完成的实验。证据不足要明确说明。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"研究主题：{query}\n"
                        f"章节：{title}\n"
                        f"写作要求：{section_rules.get(section, '写成严谨学术中文草稿。')}\n\n"
                        f"真实文献证据包：\n{format_evidence_pack(evidence)}\n\n"
                        f"结构化综述：{clean_review_text[:800]}\n\n"
                        f"研究空白分析：{clean_analysis_payload}\n\n"
                        f"实验方案：{clean_experiment_plan}\n\n"
                        f"用户补充笔记：{notes or '无'}\n\n"
                        "请直接输出该章节正文，不要输出无关解释。"
                    ),
                },
            ],
            temperature=0.18,
            max_tokens=env_int("LLM_WRITING_MAX_TOKENS", 950, minimum=500, maximum=2200),
        )
        content = strip_generation_metadata(content)
        return generation_notice(len(evidence), evidence_generation_label(evidence)) + content if content else ""
    except (LLMError, Exception):
        return ""


def _clean_payload(value):
    if isinstance(value, dict):
        return {
            key: _clean_payload(item)
            for key, item in value.items()
            if key not in {"generation", "generation_mode"}
        }
    if isinstance(value, list):
        return [_clean_payload(item) for item in value]
    if isinstance(value, str):
        return strip_generation_metadata(value)
    return value
