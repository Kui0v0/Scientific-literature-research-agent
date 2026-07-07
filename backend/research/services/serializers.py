from .llm import is_llm_rag_text, normalize_generation_notice


def record_to_dict(record):
    return {
        "id": record.id,
        "title": record.title,
        "authors": record.authors,
        "abstract": record.abstract,
        "source": record.source,
        "published_at": str(record.published_at) if record.published_at else "",
        "doi": record.doi,
        "url": record.url,
        "keywords": record.keywords,
        "raw_metadata": record.raw_metadata,
    }


def task_to_dict(task, include_records=True):
    payload = {
        "id": task.id,
        "query": task.query,
        "sources": task.sources,
        "status": task.status,
        "result_count": task.result_count,
        "review_text": normalize_generation_notice(task.review_text),
        "generation_mode": _text_generation_mode(task.review_text),
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else "",
    }
    if include_records:
        payload["records"] = [record_to_dict(record) for record in task.records.all()]
    return payload


def analysis_to_dict(analysis):
    gaps = analysis.gaps or []
    return {
        "id": analysis.id,
        "task_id": analysis.task_id,
        "hotspots": analysis.hotspots,
        "trends": analysis.trends,
        "source_distribution": analysis.source_distribution,
        "gaps": gaps,
        "summary": analysis.summary,
        "generation_mode": _analysis_generation_mode(gaps, analysis.summary),
        "created_at": analysis.created_at.isoformat() if analysis.created_at else "",
    }


def experiment_to_dict(plan):
    return {
        "id": plan.id,
        "analysis_id": plan.analysis_id,
        "question": plan.question,
        "goal": plan.goal,
        "methods": plan.methods,
        "route": plan.route,
        "expected_results": plan.expected_results,
        "risks": plan.risks,
        "content_md": normalize_generation_notice(plan.content_md),
        "generation_mode": _text_generation_mode(plan.content_md or plan.goal),
        "created_at": plan.created_at.isoformat() if plan.created_at else "",
    }


def draft_to_dict(draft):
    return {
        "id": draft.id,
        "experiment_id": draft.experiment_id,
        "section": draft.section,
        "style": draft.style,
        "content": normalize_generation_notice(draft.content),
        "generation_mode": "llm_rag" if "RAG" in (draft.style or "") or is_llm_rag_text(draft.content) else "rules",
        "created_at": draft.created_at.isoformat() if draft.created_at else "",
    }


def report_to_dict(report):
    content_md = normalize_generation_notice(report.content_md)
    text_generation = _text_generation_mode(content_md)
    payload_generation = report.payload.get("generation")
    generation_mode = text_generation if "生成方式" in content_md else payload_generation or text_generation
    return {
        "id": report.id,
        "title": report.title,
        "task_id": report.task_id,
        "payload": report.payload,
        "content_md": content_md,
        "generation_mode": generation_mode,
        "created_at": report.created_at.isoformat() if report.created_at else "",
    }


def _text_generation_mode(text):
    return "llm_rag" if is_llm_rag_text(text) else "rules"


def _analysis_generation_mode(gaps, summary):
    if any((item or {}).get("generation") == "llm_rag" for item in gaps):
        return "llm_rag"
    if is_llm_rag_text(summary) or any(is_llm_rag_text((item or {}).get("rationale")) for item in gaps):
        return "llm_rag"
    return "rules"
