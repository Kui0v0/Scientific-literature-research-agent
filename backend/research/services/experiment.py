from .llm import LLMError, chat_json, fallback_notice, generation_notice, llm_enabled, set_llm_status
from .rag import env_int, format_evidence_pack, retrieve_evidence


def build_experiment_plan(question, analysis_payload=None, records=None):
    analysis_payload = analysis_payload or {}
    records = records or []
    llm_plan = _try_llm_experiment_plan(question, analysis_payload, records)
    if llm_plan:
        return llm_plan

    hotspots = analysis_payload.get("hotspots", [])
    gaps = analysis_payload.get("gaps", [])
    top_keywords = "、".join(item.get("keyword", "") for item in hotspots[:4] if item.get("keyword"))
    gap_title = gaps[0]["title"] if gaps else "研究证据不足方向"

    goal = (
        f"围绕“{question}”构建一个可重复、可追踪的初步实验方案，验证 {gap_title}，"
        "并评估现有文献结论在真实数据或公开数据集上的稳定性。"
    )
    methods = [
        {
            "name": "系统文献证据整理",
            "reason": "先明确已有研究的样本、方法、指标和结论，减少重复实验。",
            "tool": "PubMed/arXiv 检索、结构化综述、证据表",
        },
        {
            "name": "对照实验或基线比较",
            "reason": "通过对照组、基线模型或公开方法比较，验证新方案是否真正有效。",
            "tool": "统计检验、消融实验、交叉验证",
        },
        {
            "name": "多指标评价",
            "reason": "避免只依赖单一指标，提高实验结论的可信度。",
            "tool": "准确率、召回率、F1、显著性检验、人工专家评估",
        },
        {
            "name": "可解释性与溯源分析",
            "reason": "科研场景需要说明结论来源，便于答辩和后续发表。",
            "tool": "引用追踪、关键词证据、结果可视化",
        },
    ]
    route = [
        "确定研究问题和纳入排除标准",
        "采集跨库文献或公开实验数据",
        "完成数据清洗、去重和字段标准化",
        "建立基线方法并设计对照实验",
        "运行实验并记录参数、结果和异常情况",
        "进行统计分析、可视化展示和误差分析",
        "根据实验结果撰写论文方法与讨论章节",
    ]
    expected_results = (
        f"预期能够形成关于“{question}”的可验证结论，明确 {top_keywords or '核心研究主题'} "
        "在当前方向中的作用，并给出后续研究可继续扩展的数据、方法和评价指标。"
    )
    risks = [
        {
            "risk": "数据质量不稳定",
            "solution": "设置字段完整性检查，对缺失摘要或重复文献进行过滤。",
        },
        {
            "risk": "生成内容存在偏差",
            "solution": "要求所有结论绑定文献证据，并保留人工审核环节。",
        },
        {
            "risk": "实验样本量不足",
            "solution": "优先选择公开数据集或扩大检索范围，同时报告样本限制。",
        },
    ]
    content_md = _plan_markdown(question, goal, methods, route, expected_results, risks)
    return {
        "question": question,
        "goal": goal,
        "methods": methods,
        "route": route,
        "expected_results": expected_results,
        "risks": risks,
        "content_md": content_md,
    }


def _try_llm_experiment_plan(question, analysis_payload, records):
    if not llm_enabled() or not records:
        return {}
    try:
        evidence = retrieve_evidence(
            question,
            records,
            limit=env_int("RAG_EXPERIMENT_TOP_K", env_int("RAG_TOP_K", 5, minimum=1, maximum=20), minimum=1, maximum=20),
        )
        if not evidence:
            return {}
        payload = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的科研实验方案设计助手。只能依据真实文献证据包和已有分析结果生成方案。"
                        "不得编造实验已完成、不得编造数据集、不得编造性能数字。证据不足时明确写“证据不足”。"
                        "输出必须是合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"研究问题：{question}\n\n"
                        f"真实文献证据包：\n{format_evidence_pack(evidence)}\n\n"
                        f"已有热点与空白分析：{analysis_payload}\n\n"
                        "请只输出一个合法 JSON 对象，不要输出 Markdown，不要尾逗号。所有字符串必须使用英文双引号。格式为：\n"
                        "{\n"
                        '  "goal": "研究目标，必须引用证据编号",\n'
                        '  "methods": [{"name": "方法名", "reason": "推荐原因，含证据编号", "tool": "工具/技术"}],\n'
                        '  "route": ["步骤1", "步骤2"],\n'
                        '  "expected_results": "预期结果，只能写预期，不得写已实现结果，含证据编号",\n'
                        '  "risks": [{"risk": "风险", "solution": "控制方案"}]\n'
                        "}\n"
                        "要求 methods 4 条左右，route 6-8 步，risks 3 条左右。"
                    ),
                },
            ],
            temperature=0.12,
            max_tokens=env_int("LLM_EXPERIMENT_MAX_TOKENS", 1600, minimum=600, maximum=4000),
        )
        payload = _unwrap_payload(payload)
        methods = _clean_methods(
            _first_present(payload, "methods", "recommended_methods", "method_recommendations", "推荐方法", "方法推荐", "方法")
        )
        route = _clean_route(
            _first_present(payload, "route", "technical_route", "steps", "workflow", "技术路线", "实验步骤", "步骤", "路线")
        )
        risks = _clean_risks(
            _first_present(payload, "risks", "risk_control", "risk_controls", "limitations", "风险控制", "风险", "局限性")
        )
        goal = str(_first_present(payload, "goal", "research_goal", "objective", "研究目标", "实验目标", "目标") or "").strip()
        expected_results = str(_first_present(payload, "expected_results", "expected_result", "expectation", "预期结果", "预期产出") or "").strip()
        if not goal or not methods or not route:
            set_llm_status("当前大模型返回 JSON 但缺少实验目标、推荐方法或技术路线字段，已使用规则模板兜底。")
            return {}
        content_md = _plan_markdown(
            question,
            goal,
            methods,
            route,
            expected_results,
            risks,
            notice=generation_notice(len(evidence)),
        )
        return {
            "question": question,
            "goal": goal,
            "methods": methods,
            "route": route,
            "expected_results": expected_results,
            "risks": risks,
            "content_md": content_md,
        }
    except (LLMError, Exception):
        return {}


def _clean_methods(items):
    output = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            name = item.strip()
            reason = "模型返回了方法名称，但缺少推荐原因，建议结合证据包人工复核。"
            tool = ""
        elif isinstance(item, dict):
            name = str(_first_present(item, "name", "method", "title", "方法名", "名称", "方法") or "").strip()
            reason = str(_first_present(item, "reason", "rationale", "description", "推荐原因", "原因", "依据", "说明") or "").strip()
            tool = str(_first_present(item, "tool", "technology", "technique", "工具", "技术", "推荐工具") or "").strip()
        else:
            continue
        if not name:
            continue
        output.append(
            {
                "name": name[:80],
                "reason": reason[:260],
                "tool": tool[:160],
            }
        )
    return output[:5]


def _clean_route(items):
    output = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(_first_present(item, "step", "title", "description", "步骤", "标题", "内容", "说明") or "").strip()
        else:
            text = ""
        if text:
            output.append(text[:160])
    return output[:8]


def _clean_risks(items):
    output = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            risk = item.strip()
            solution = "结合实验过程设置人工复核与异常记录。"
        elif isinstance(item, dict):
            risk = str(_first_present(item, "risk", "title", "name", "风险", "标题", "名称") or "").strip()
            solution = str(_first_present(item, "solution", "mitigation", "control", "控制方案", "解决方案", "缓解措施", "应对措施") or "").strip()
        else:
            continue
        if not risk:
            continue
        output.append(
            {
                "risk": risk[:120],
                "solution": solution[:240],
            }
        )
    return output[:4]


def _first_present(payload, *names):
    if not isinstance(payload, dict):
        return None
    for name in names:
        value = payload.get(name)
        if value:
            return value
    return None


def _unwrap_payload(payload):
    if not isinstance(payload, dict):
        return {}
    for key in ["result", "data", "plan", "experiment_plan", "output", "方案", "实验方案"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _plan_markdown(question, goal, methods, route, expected_results, risks, notice=None):
    method_text = "\n".join(
        f"- {item['name']}：{item['reason']} 推荐工具：{item['tool']}" for item in methods
    )
    route_text = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(route))
    risk_text = "\n".join(f"- {item['risk']}：{item['solution']}" for item in risks)
    return (
        (fallback_notice() if notice is None else notice) +
        f"# 实验方案设计：{question}\n\n"
        f"## 研究目标\n{goal}\n\n"
        f"## 推荐方法\n{method_text}\n\n"
        f"## 技术路线\n{route_text}\n\n"
        f"## 预期结果\n{expected_results}\n\n"
        f"## 风险控制\n{risk_text}\n"
    )
