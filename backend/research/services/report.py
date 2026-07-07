from .llm import LLMError, chat_completion, fallback_notice, generation_notice, llm_enabled, strip_generation_metadata
from .rag import env_int, format_evidence_pack, retrieve_evidence


def build_report(task, records, analysis=None, experiment=None, drafts=None):
    drafts = drafts or []
    analysis_payload = analysis or {}
    experiment_payload = experiment or {}
    title = f"{task.query} 研究报告"
    llm_content = _try_llm_report(task, records, analysis_payload, experiment_payload, drafts)
    if llm_content:
        payload = {
            "task_id": task.id,
            "record_count": len(records),
            "analysis": analysis_payload,
            "experiment": experiment_payload,
            "draft_count": len(drafts),
            "generation": "llm_rag",
        }
        return {"title": title, "payload": payload, "content_md": llm_content}

    literature_lines = "\n".join(
        f"- {record.title}（{record.source}，{record.published_at or '未知日期'}）"
        for record in records[:10]
    )
    hotspots = "\n".join(
        f"- {item.get('keyword')}：{item.get('evidence')}"
        for item in analysis_payload.get("hotspots", [])[:8]
    )
    gaps = "\n".join(
        f"- {item.get('title')}：{item.get('rationale')}"
        for item in analysis_payload.get("gaps", [])[:5]
    )
    drafts_text = "\n\n".join(
        f"## {draft.section}\n{strip_generation_metadata(draft.content)}" for draft in drafts
    )
    experiment_text = strip_generation_metadata(experiment_payload.get("content_md", ""))
    review_text = strip_generation_metadata(task.review_text)
    analysis_summary = strip_generation_metadata(analysis_payload.get("summary", "暂无分析结果"))
    content_md = (
        fallback_notice() +
        f"# {title}\n\n"
        f"## 一、研究主题\n{task.query}\n\n"
        f"## 二、文献检索结果\n共检索并整理 {len(records)} 篇文献。\n\n{literature_lines}\n\n"
        f"## 三、结构化文献综述\n{review_text}\n\n"
        f"## 四、热点趋势分析\n{analysis_summary}\n\n{hotspots}\n\n"
        f"## 五、研究空白\n{gaps or '暂无明确研究空白。'}\n\n"
        f"## 六、实验方案\n{experiment_text or '暂无实验方案。'}\n\n"
        f"## 七、论文写作草稿\n{drafts_text or '暂无草稿。'}\n\n"
        f"## 八、结论\n本报告由科学文献研究智能体自动生成，适合作为答辩展示、课题讨论和论文初稿整理的基础材料。"
    )
    payload = {
        "task_id": task.id,
        "record_count": len(records),
        "analysis": analysis_payload,
        "experiment": experiment_payload,
        "draft_count": len(drafts),
        "generation": "rules",
    }
    return {"title": title, "payload": payload, "content_md": content_md}


def _try_llm_report(task, records, analysis_payload, experiment_payload, drafts):
    if not llm_enabled() or not records:
        return ""
    try:
        evidence = retrieve_evidence(
            task.query,
            records,
            limit=env_int("RAG_REPORT_TOP_K", 6, minimum=1, maximum=20),
        )
        if not evidence:
            return ""
        drafts_text = "\n\n".join(f"## {draft.section}\n{strip_generation_metadata(draft.content)}" for draft in drafts)[:1200]
        clean_analysis_payload = _clean_payload(analysis_payload)
        clean_experiment_payload = _clean_payload(experiment_payload)
        content = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "你是科研项目报告撰写助手。只能基于证据包、分析结果、实验方案和已有草稿生成报告。"
                        "所有文献相关结论必须引用[R1]等证据编号；不得编造文献、实验数据、性能数字或结论。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"报告题目：{task.query} 研究报告\n\n"
                        f"真实文献证据包：\n{format_evidence_pack(evidence)}\n\n"
                        f"热点与研究空白分析：{clean_analysis_payload}\n\n"
                        f"实验方案：{clean_experiment_payload}\n\n"
                        f"已有章节草稿：{drafts_text or '暂无'}\n\n"
                        "请生成中文 Markdown 报告，总长度控制在 1000-1400 字，结构包含：\n"
                        "# 标题\n"
                        "## 一、研究主题\n"
                        "## 二、真实文献检索依据\n"
                        "## 三、结构化综述\n"
                        "## 四、热点趋势与研究空白\n"
                        "## 五、实验方案设计\n"
                        "## 六、论文写作建议\n"
                        "## 七、证据限制与后续工作\n"
                        "## 八、结论\n"
                    ),
                },
            ],
            temperature=0.16,
            max_tokens=env_int("LLM_REPORT_MAX_TOKENS", 1500, minimum=800, maximum=3200),
        )
        content = strip_generation_metadata(content)
        return generation_notice(len(evidence)) + content if content else ""
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
