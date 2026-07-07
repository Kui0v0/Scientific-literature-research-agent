import json
import math
import os
import re
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User
from django.db import connection
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    AnalysisResult,
    ExperimentPlan,
    LiteratureRecord,
    Report,
    SearchTask,
    SystemLog,
    TodoItem,
    UserProfile,
    WritingDraft,
)
from .services.agent import run_full_research_flow
from .services.analyzer import analyze_records, uses_legacy_hotspots
from .services.connectors import RetrievalError, search_literature
from .services.experiment import build_experiment_plan
from .services.exporters import report_filename, render_report_docx, render_report_pdf
from .services.llm import llm_config_status
from .services.report import build_report
from .services.serializers import (
    analysis_to_dict,
    draft_to_dict,
    experiment_to_dict,
    record_to_dict,
    report_to_dict,
    task_to_dict,
)
from .services.summarizer import generate_review
from .services.writer import generate_draft


RESEARCH_AREAS = [
    {
        "id": "natural",
        "name": "自然科学",
        "english": "Natural Sciences",
        "color": "#3b73ff",
        "terms": [
            "physics",
            "chemistry",
            "biology",
            "biological",
            "molecular",
            "genomics",
            "genetics",
            "astronomy",
            "astrophysics",
            "earth science",
            "geology",
            "geoscience",
            "climate",
            "ecology",
            "environment",
            "evolution",
            "mathematics",
            "mathematical",
            "ocean",
            "atmospheric",
            "biodiversity",
            "quantum",
            "particle",
            "物理",
            "化学",
            "生物",
            "天文",
            "地球科学",
            "地质",
            "生态",
            "环境",
            "数学",
            "气候",
        ],
    },
    {
        "id": "engineering",
        "name": "工程与技术",
        "english": "Engineering & Technology",
        "color": "#8b5cf6",
        "terms": [
            "engineering",
            "technology",
            "computer science",
            "computer",
            "algorithm",
            "software",
            "hardware",
            "network",
            "machine learning",
            "deep learning",
            "artificial intelligence",
            "ai",
            "large language model",
            "llm",
            "natural language processing",
            "nlp",
            "robotics",
            "robot",
            "mechanical",
            "materials",
            "civil engineering",
            "electrical",
            "electronics",
            "automation",
            "control",
            "manufacturing",
            "semiconductor",
            "工程",
            "技术",
            "计算机",
            "算法",
            "软件",
            "人工智能",
            "机器学习",
            "深度学习",
            "大语言模型",
            "机器人",
            "机械",
            "材料",
            "土木",
            "电气",
        ],
    },
    {
        "id": "medicine",
        "name": "医学与健康",
        "english": "Medicine & Health Sciences",
        "color": "#18c29c",
        "terms": [
            "medicine",
            "medical",
            "clinical",
            "health",
            "disease",
            "therapy",
            "treatment",
            "drug",
            "pharmacology",
            "pharmacy",
            "public health",
            "epidemiology",
            "neuroscience",
            "neurology",
            "patient",
            "diagnosis",
            "cancer",
            "tumor",
            "immune",
            "immunology",
            "vaccine",
            "hospital",
            "医学",
            "临床",
            "健康",
            "疾病",
            "治疗",
            "药学",
            "公共卫生",
            "神经科学",
            "患者",
            "诊断",
            "肿瘤",
            "免疫",
            "疫苗",
        ],
    },
    {
        "id": "agriculture",
        "name": "农业科学",
        "english": "Agricultural Sciences",
        "color": "#ff8a2a",
        "terms": [
            "agriculture",
            "agricultural",
            "crop",
            "crops",
            "agronomy",
            "horticulture",
            "livestock",
            "animal husbandry",
            "veterinary",
            "forestry",
            "forest",
            "fisheries",
            "aquaculture",
            "plant breeding",
            "irrigation",
            "pest",
            "weed",
            "farm",
            "soil fertility",
            "农业",
            "农学",
            "作物",
            "园艺",
            "畜牧",
            "兽医",
            "林学",
            "水产",
            "灌溉",
            "育种",
            "农场",
        ],
    },
    {
        "id": "ssh",
        "name": "社会科学与人文",
        "english": "Social Sciences & Humanities",
        "color": "#ff4d6d",
        "terms": [
            "social sciences",
            "humanities",
            "economics",
            "psychology",
            "sociology",
            "language",
            "languages",
            "linguistic",
            "linguistics",
            "literature",
            "philosophy",
            "history",
            "education",
            "law",
            "management",
            "business",
            "political",
            "communication",
            "anthropology",
            "culture",
            "translation",
            "semantics",
            "phonology",
            "reading",
            "writing",
            "second language",
            "language acquisition",
            "discourse",
            "ssci",
            "社会科学",
            "人文",
            "经济",
            "心理学",
            "社会学",
            "语言",
            "语言学",
            "文学",
            "哲学",
            "历史",
            "教育",
            "法律",
            "管理",
            "传播",
            "文化",
            "翻译",
        ],
    },
]

RESEARCH_AREA_BY_ID = {area["id"]: area for area in RESEARCH_AREAS}
INNOVATION_SIGNALS = [
    "novel",
    "new",
    "emerging",
    "proposed",
    "innovative",
    "framework",
    "model",
    "approach",
    "paradigm",
    "新",
    "创新",
    "提出",
    "框架",
    "模型",
]
METHOD_SIGNALS = [
    "experiment",
    "experimental",
    "dataset",
    "evaluation",
    "simulation",
    "benchmark",
    "analysis",
    "method",
    "trial",
    "survey",
    "实验",
    "数据集",
    "评估",
    "仿真",
    "方法",
    "调查",
]
APPLICATION_SIGNALS = [
    "application",
    "applied",
    "clinical",
    "industry",
    "deployment",
    "practice",
    "platform",
    "system",
    "service",
    "education",
    "policy",
    "应用",
    "临床",
    "产业",
    "部署",
    "平台",
    "系统",
    "教育",
    "政策",
]
GAP_SIGNALS = [
    "limited",
    "lack",
    "unclear",
    "insufficient",
    "challenge",
    "bottleneck",
    "gap",
    "future work",
    "不足",
    "缺乏",
    "挑战",
    "瓶颈",
    "空白",
]


def health(request):
    db_name = str(connection.settings_dict.get("NAME") or "")
    payload = {
        "status": "ok",
        "name": "scientific-literature-agent",
        "llm": llm_config_status(),
    }
    if settings.DEBUG:
        payload["runtime"] = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "db_engine": connection.settings_dict.get("ENGINE", ""),
            "db_name": os.path.basename(db_name) or db_name,
        }
    return api_ok(payload)


@require_http_methods(["GET"])
def trend_statistics(request):
    range_key = request.GET.get("range", "2m")
    days = 180 if range_key == "6m" else 60
    bucket_count = 12 if range_key == "6m" else 9
    end_date = timezone.localdate()
    start_date = end_date - timedelta(days=days - 1)
    bucket_days = max(1, math.ceil(days / bucket_count))
    buckets = []
    for index in range(bucket_count):
        bucket_start = start_date + timedelta(days=index * bucket_days)
        buckets.append(
            {
                "label": bucket_start.strftime("%m-%d"),
                "start": bucket_start.isoformat(),
            }
        )

    records = list(
        LiteratureRecord.objects.filter(
            Q(published_at__gte=start_date, published_at__lte=end_date)
            | Q(created_at__date__gte=start_date, created_at__date__lte=end_date)
        )
        .exclude(source__iexact="Demo")
        .select_related("task")
    )
    trend_records = []
    for record in records:
        trend_date = _trend_record_date(record, start_date, end_date)
        if not trend_date:
            continue
        area = _classify_research_area(record)
        trend_records.append((record, trend_date, area))

    series_map = {area["id"]: [0 for _ in buckets] for area in RESEARCH_AREAS}
    for record, trend_date, area in trend_records:
        bucket_index = min(max((trend_date - start_date).days // bucket_days, 0), bucket_count - 1)
        series_map[area["id"]][bucket_index] += 1

    series = [
        {
            "id": area["id"],
            "name": area["name"],
            "english": area["english"],
            "color": area["color"],
            "values": values,
            "total": sum(values),
        }
        for area in RESEARCH_AREAS
        for values in [series_map[area["id"]]]
        if sum(values) > 0
    ]
    return api_ok(
        {
            "range": range_key,
            "is_real": True,
            "date_basis": "published_at_or_retrieved_at",
            "category_basis": "content_classification",
            "record_count": len(trend_records),
            "bucket_days": bucket_days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "buckets": buckets,
            "categories": [
                {"id": area["id"], "name": area["name"], "english": area["english"], "color": area["color"]}
                for area in RESEARCH_AREAS
            ],
            "series": series,
        }
    )


@require_http_methods(["GET"])
def gap_statistics(request):
    task = _gap_statistics_task(request)
    if not task:
        return api_ok(_empty_gap_statistics_payload())

    current_records = []
    current_records = list(task.records.exclude(source__iexact="Demo").select_related("task"))

    query = (request.GET.get("query") or task.query).strip()
    area = _dominant_research_area(current_records, query)
    all_real_records = list(LiteratureRecord.objects.exclude(source__iexact="Demo").select_related("task"))
    field_records = [record for record in all_real_records if _classify_research_area(record)["id"] == area["id"]]
    if current_records and not field_records:
        field_records = current_records

    current_values = _gap_radar_values(current_records, area, field_records)
    average_values = _field_average_radar_values(field_records, area)
    labels = ["研究热度", "文献数量", "创新性", "可行性", "应用价值", "研究成熟度"]
    keys = ["heat", "volume", "innovation", "feasibility", "application", "maturity"]
    descriptions = [
        "依据近年真实文献占比、同领域记录规模和检索结果活跃度计算。",
        "依据该关键词真实返回文献数量相对同领域记录规模计算。",
        "依据近年文献比例、新方法/新框架信号和不足/空白信号计算。",
        "依据 DOI/URL/摘要完整度、方法类信号和来源多样性计算。",
        "依据应用、临床、产业、数据集、部署等应用信号计算。",
        "依据年份跨度、非近期文献比例、来源多样性和同领域沉淀量计算。",
    ]
    metrics = [
        {
            "key": key,
            "label": label,
            "current": current_values[index],
            "average": average_values[index],
            "description": descriptions[index],
        }
        for index, (key, label) in enumerate(zip(keys, labels))
    ]
    return api_ok(
        {
            "is_real": True,
            "task_id": task.id if task else None,
            "query": query,
            "research_area": {"id": area["id"], "name": area["name"], "english": area["english"], "color": area["color"]},
            "record_count": len(current_records),
            "field_record_count": len(field_records),
            "source_count": len({record.source for record in current_records if record.source}),
            "metrics": metrics,
            "current_values": current_values,
            "average_values": average_values,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def search(request):
    data = parse_json(request)
    query = data.get("query", "").strip()
    sources = data.get("sources") or ["pubmed", "arxiv", "crossref"]
    if not query:
        return api_error("研究主题不能为空", status=400)

    task = SearchTask.objects.create(
        owner=current_user(request),
        query=query,
        sources=sources,
        status=SearchTask.Status.RUNNING,
    )
    try:
        records_payload = search_literature(query, sources=sources, limit=int(data.get("limit", 10)))
        for payload in records_payload:
            LiteratureRecord.objects.create(task=task, **payload)
        task.result_count = len(records_payload)
        task.review_text = generate_review(query, records_payload)
        task.status = SearchTask.Status.DONE
        task.save(update_fields=["result_count", "review_text", "status", "updated_at"])
        log_action(request, "literature.search", {"query": query, "sources": sources, "count": task.result_count})
        return api_ok({"task": task_to_dict(task)})
    except RetrievalError as exc:
        task.status = SearchTask.Status.FAILED
        task.error_message = str(exc)
        task.save(update_fields=["status", "error_message", "updated_at"])
        return api_error(str(exc), status=424)
    except Exception as exc:
        task.status = SearchTask.Status.FAILED
        task.error_message = str(exc)
        task.save(update_fields=["status", "error_message", "updated_at"])
        return api_error(f"检索服务异常：{exc}", status=500)


def task_detail(request, task_id):
    task = get_object_or_404(SearchTask, id=task_id)
    payload = {"task": task_to_dict(task)}
    analysis = _analysis_for_response(task)
    if analysis:
        payload["analysis"] = analysis_to_dict(analysis)
    return api_ok(payload)


@csrf_exempt
@require_http_methods(["POST"])
def analyze(request):
    data = parse_json(request)
    task = get_object_or_404(SearchTask, id=data.get("task_id"))
    analysis = _run_analysis_for_task(task)
    log_action(request, "analysis.run", {"task_id": task.id, "gap_count": len(analysis.gaps)})
    return api_ok({"analysis": analysis_to_dict(analysis)})


def _task_analysis(task):
    try:
        return task.analysis
    except AnalysisResult.DoesNotExist:
        return None


def _analysis_for_response(task):
    analysis = _task_analysis(task)
    return _ensure_current_analysis(analysis) if analysis else None


def _ensure_current_analysis(analysis):
    if uses_legacy_hotspots(analysis.hotspots):
        return _run_analysis_for_task(analysis.task)
    return analysis


def _run_analysis_for_task(task):
    records_payload = [record_to_dict(record) for record in task.records.all()]
    result = analyze_records(records_payload)
    analysis, _ = AnalysisResult.objects.update_or_create(
        task=task,
        defaults={
            "hotspots": result["hotspots"],
            "trends": result["trends"],
            "source_distribution": result["source_distribution"],
            "gaps": result["gaps"],
            "summary": result["summary"],
        },
    )
    return analysis


@csrf_exempt
@require_http_methods(["POST"])
def experiment(request):
    data = parse_json(request)
    analysis = get_object_or_404(AnalysisResult, id=data.get("analysis_id"))
    analysis = _ensure_current_analysis(analysis)
    analysis_payload = analysis_to_dict(analysis)
    default_question = analysis.gaps[0]["suggested_question"] if analysis.gaps else analysis.task.query
    question = data.get("question") or default_question
    records_payload = [record_to_dict(record) for record in analysis.task.records.all()]
    plan_payload = build_experiment_plan(question, analysis_payload, records_payload)
    plan = ExperimentPlan.objects.create(owner=current_user(request), analysis=analysis, **plan_payload)
    log_action(request, "experiment.create", {"analysis_id": analysis.id, "question": question})
    return api_ok({"experiment": experiment_to_dict(plan)})


@csrf_exempt
@require_http_methods(["POST"])
def writing(request):
    data = parse_json(request)
    plan = get_object_or_404(ExperimentPlan, id=data.get("experiment_id"))
    if plan.analysis:
        plan.analysis = _ensure_current_analysis(plan.analysis)
    query = plan.analysis.task.query if plan.analysis else plan.question
    records_payload = [record_to_dict(record) for record in plan.analysis.task.records.all()] if plan.analysis else []
    analysis_payload = analysis_to_dict(plan.analysis) if plan.analysis else {}
    draft_payload = generate_draft(
        data.get("section", "introduction"),
        query,
        review_text=plan.analysis.task.review_text if plan.analysis else "",
        experiment_plan=experiment_to_dict(plan),
        notes=data.get("notes", ""),
        records=records_payload,
        analysis_payload=analysis_payload,
    )
    draft = WritingDraft.objects.create(owner=current_user(request), experiment=plan, **draft_payload)
    log_action(request, "writing.generate", {"experiment_id": plan.id, "section": draft.section})
    return api_ok({"draft": draft_to_dict(draft)})


@csrf_exempt
@require_http_methods(["POST"])
def report(request):
    data = parse_json(request)
    task = get_object_or_404(SearchTask, id=data.get("task_id"))
    analysis = _analysis_for_response(task)
    analysis_payload = analysis_to_dict(analysis) if analysis else {}
    plan = None
    if data.get("experiment_id"):
        plan = get_object_or_404(ExperimentPlan, id=data.get("experiment_id"))
    elif analysis:
        plan = analysis.experiment_plans.order_by("-created_at").first()
    drafts = list(plan.drafts.all()) if plan else []
    report_payload = build_report(
        task,
        list(task.records.all()),
        analysis=analysis_payload,
        experiment=experiment_to_dict(plan) if plan else {},
        drafts=drafts,
    )
    item = Report.objects.create(owner=current_user(request), task=task, **report_payload)
    log_action(request, "report.create", {"task_id": task.id, "report_id": item.id})
    return api_ok({"report": report_to_dict(item)})


def report_detail(request, report_id):
    item = get_object_or_404(Report, id=report_id)
    return api_ok({"report": report_to_dict(item)})


def report_markdown(request, report_id):
    item = get_object_or_404(Report, id=report_id)
    response = HttpResponse(item.content_md, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="report-{item.id}.md"'
    return response


def report_download(request, report_id):
    item = get_object_or_404(Report, id=report_id)
    export_format = (request.GET.get("format") or "markdown").strip().lower()
    if export_format in {"md", "markdown"}:
        response = HttpResponse(item.content_md, content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report_filename(item, "md")}"'
        return response
    if export_format in {"pdf"}:
        try:
            content = render_report_pdf(item)
        except RuntimeError as exc:
            return api_error(str(exc), status=501)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_filename(item, "pdf")}"'
        return response
    if export_format in {"word", "docx"}:
        try:
            content = render_report_docx(item)
        except RuntimeError as exc:
            return api_error(str(exc), status=501)
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{report_filename(item, "docx")}"'
        return response
    return api_error("不支持的报告格式，请选择 Markdown、PDF 或 Word。", status=400)


@csrf_exempt
@require_http_methods(["POST"])
def agent_run(request):
    data = parse_json(request)
    query = data.get("query", "").strip()
    if not query:
        return api_error("研究主题不能为空", status=400)
    try:
        task, analysis, plan, drafts, item = run_full_research_flow(
            query,
            data.get("sources") or ["pubmed", "arxiv", "crossref"],
            user=current_user(request),
        )
    except RetrievalError as exc:
        return api_error(str(exc), status=424)
    except Exception as exc:
        return api_error(f"智能体运行失败：{exc}", status=500)
    log_action(request, "agent.run", {"query": query, "task_id": task.id, "report_id": item.id})
    return api_ok(
        {
            "task": task_to_dict(task),
            "analysis": analysis_to_dict(analysis),
            "experiment": experiment_to_dict(plan),
            "drafts": [draft_to_dict(draft) for draft in drafts],
            "report": report_to_dict(item),
        }
    )


def parse_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def api_ok(payload=None, status=200):
    return JsonResponse({"ok": True, **(payload or {})}, status=status, json_dumps_params={"ensure_ascii": False})


def api_error(message, status=400):
    return JsonResponse(
        {"ok": False, "error": message},
        status=status,
        json_dumps_params={"ensure_ascii": False},
    )


def _gap_statistics_task(request):
    task_id = request.GET.get("task_id")
    if not task_id:
        return None
    try:
        return SearchTask.objects.get(id=int(task_id), status=SearchTask.Status.DONE)
    except (SearchTask.DoesNotExist, TypeError, ValueError):
        return None


def _empty_gap_statistics_payload():
    return {
        "is_real": True,
        "task_id": None,
        "query": "",
        "research_area": None,
        "record_count": 0,
        "field_record_count": 0,
        "source_count": 0,
        "metrics": [],
        "current_values": [],
        "average_values": [],
    }


def _dominant_research_area(records, query=""):
    if records:
        scores = {area["id"]: 0 for area in RESEARCH_AREAS}
        for record in records:
            scores[_classify_research_area(record)["id"]] += 1
        best_area = max(RESEARCH_AREAS, key=lambda area: (scores[area["id"]], -RESEARCH_AREAS.index(area)))
        if scores[best_area["id"]]:
            return best_area
    return _classify_query_area(query)


def _classify_query_area(query):
    text = str(query or "").lower()
    scores = {area["id"]: 0 for area in RESEARCH_AREAS}
    for area in RESEARCH_AREAS:
        for term in area["terms"]:
            scores[area["id"]] += _term_hit_count(text, term)
    best_area = max(RESEARCH_AREAS, key=lambda area: (scores[area["id"]], -RESEARCH_AREAS.index(area)))
    return best_area if scores[best_area["id"]] else RESEARCH_AREA_BY_ID["natural"]


def _field_average_radar_values(records, area):
    grouped = {}
    for record in records:
        grouped.setdefault(record.task_id or record.id, []).append(record)
    if not grouped:
        return [0, 0, 0, 0, 0, 0]
    values = [_gap_radar_values(group_records, area, records) for group_records in grouped.values()]
    return [_bounded_score(sum(item[index] for item in values) / len(values)) for index in range(6)]


def _gap_radar_values(records, area, field_records=None):
    records = list(records or [])
    field_records = list(field_records or records)
    if not records:
        return [0, 0, 0, 0, 0, 0]

    texts = [_record_research_text(record) for record in records]
    years = [_record_year(record) for record in records if _record_year(record)]
    current_year = timezone.localdate().year
    recent_ratio = _ratio(sum(1 for year in years if year >= current_year - 3), len(records))
    older_ratio = _ratio(sum(1 for year in years if year < current_year - 3), len(records))
    source_diversity = min(len({record.source for record in records if record.source}) / 3, 1)
    metadata_ratio = _ratio(
        sum(1 for record in records if record.doi or record.url or record.abstract or record.keywords),
        len(records),
    )
    method_ratio = _signal_ratio(texts, METHOD_SIGNALS)
    innovation_ratio = max(_signal_ratio(texts, INNOVATION_SIGNALS), _signal_ratio(texts, GAP_SIGNALS))
    application_ratio = _signal_ratio(texts, APPLICATION_SIGNALS)
    field_size = max(len(field_records), len(records), 1)
    year_span = (max(years) - min(years) + 1) if years else 1

    heat = 35 + recent_ratio * 38 + min(len(records) / max(field_size, 1), 1) * 17 + source_diversity * 10
    volume = 25 + min(len(records) / max(field_size, 8), 1) * 75
    innovation = 35 + innovation_ratio * 38 + recent_ratio * 20 + min(len(records), 10) * 0.7
    feasibility = 30 + metadata_ratio * 25 + method_ratio * 25 + source_diversity * 20
    application = 30 + application_ratio * 45 + method_ratio * 10 + _area_application_bonus(area) + source_diversity * 8
    maturity = 25 + min(math.log(len(records) + 1, 2) / 5, 1) * 25 + older_ratio * 22 + min(year_span / 8, 1) * 18 + source_diversity * 10

    return [_bounded_score(value) for value in [heat, volume, innovation, feasibility, application, maturity]]


def _record_research_text(record):
    keywords = " ".join(str(item) for item in (record.keywords or []))
    metadata = json.dumps(record.raw_metadata or {}, ensure_ascii=False)
    return " ".join([_record_query(record), record.title or "", record.abstract or "", keywords, metadata]).lower()


def _record_year(record):
    if record.published_at:
        return record.published_at.year
    if record.created_at:
        return timezone.localtime(record.created_at).year
    return None


def _signal_ratio(texts, signals):
    if not texts:
        return 0
    hits = sum(1 for text in texts if any(signal in text for signal in signals))
    return hits / len(texts)


def _ratio(count, total):
    return count / total if total else 0


def _bounded_score(value):
    return int(max(0, min(100, round(value))))


def _area_application_bonus(area):
    if area["id"] in {"medicine", "engineering", "agriculture"}:
        return 7
    if area["id"] == "ssh":
        return 5
    return 2


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _trend_record_date(record, start_date, end_date):
    if record.published_at and start_date <= record.published_at <= end_date:
        return record.published_at
    if record.created_at:
        created_date = timezone.localtime(record.created_at).date()
        if start_date <= created_date <= end_date:
            return created_date
    return None


def _classify_research_area(record):
    query = _record_query(record).strip().lower()
    if re.fullmatch(r"(language|languages|linguistics|语言|语言学)", query):
        return RESEARCH_AREA_BY_ID["ssh"]

    scores = {area["id"]: 0 for area in RESEARCH_AREAS}
    for text, weight in _classification_sections(record):
        lowered = text.lower()
        if not lowered:
            continue
        for area in RESEARCH_AREAS:
            for term in area["terms"]:
                scores[area["id"]] += _term_hit_count(lowered, term) * weight

    for token in _record_category_tokens(record):
        area_id = _area_from_category_token(token)
        if area_id:
            scores[area_id] += 8

    source = (record.source or "").lower()
    if source == "pubmed":
        scores["medicine"] += 2
    elif source == "arxiv":
        scores["natural"] += 1

    best_area = max(RESEARCH_AREAS, key=lambda area: (scores[area["id"]], -RESEARCH_AREAS.index(area)))
    if scores[best_area["id"]] <= 0:
        return RESEARCH_AREA_BY_ID["natural"]
    return best_area


def _classification_sections(record):
    keywords = " ".join(str(item) for item in (record.keywords or []))
    metadata = json.dumps(record.raw_metadata or {}, ensure_ascii=False)
    authors = " ".join(str(item) for item in (record.authors or []))
    return [
        (_record_query(record), 5),
        (record.title or "", 4),
        (keywords, 4),
        (record.abstract or "", 1),
        (metadata, 1),
        (authors, 1),
    ]


def _record_query(record):
    if not record.task_id:
        return ""
    try:
        return record.task.query or ""
    except Exception:
        return ""


def _record_category_tokens(record):
    tokens = []
    for keyword in record.keywords or []:
        tokens.append(str(keyword))
    metadata = record.raw_metadata or {}
    for key in ["provider", "container_title", "publisher", "source_id", "arxiv_id"]:
        value = metadata.get(key)
        if value:
            tokens.append(str(value))
    return tokens


def _area_from_category_token(token):
    value = str(token or "").strip().lower()
    if not value:
        return None
    if value.startswith(("cs.", "eess.", "stat.ml")):
        return "engineering"
    if value.startswith(("astro-ph", "cond-mat", "gr-qc", "hep-", "math", "nlin", "nucl", "physics", "quant-ph")):
        return "natural"
    if value.startswith(("q-bio",)):
        return "natural"
    if value.startswith(("q-fin", "econ")):
        return "ssh"
    return None


def _term_hit_count(text, term):
    needle = str(term or "").lower()
    if not needle:
        return 0
    if re.fullmatch(r"[a-z0-9+#.-]+", needle):
        return len(re.findall(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text))
    return text.count(needle)


ROLE_NAMES = ["管理员", "运营人员", "分析师"]
BUSINESS_ACTIONS = {
    "literature.search",
    "analysis.run",
    "experiment.create",
    "writing.generate",
    "report.create",
    "agent.run",
}
ACTION_ICONS = {
    "literature.search": ("Search", "blue"),
    "analysis.run": ("MagicStick", "purple"),
    "experiment.create": ("Operation", "orange"),
    "writing.generate": ("EditPen", "purple"),
    "report.create": ("Document", "green"),
    "agent.run": ("DataAnalysis", "green"),
    "login": ("User", "blue"),
    "logout": ("User", "gray"),
    "register": ("User", "green"),
    "profile.update": ("User", "blue"),
    "todo.create": ("Files", "blue"),
    "todo.update": ("Files", "orange"),
    "todo.delete": ("Files", "gray"),
    "user.create": ("User", "green"),
    "user.update": ("User", "blue"),
    "user.delete": ("User", "red"),
}


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    data = parse_json(request)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip()
    if not username or not password:
        return api_error("用户名和密码不能为空", status=400)
    if len(password) < 6:
        return api_error("密码至少需要 6 位", status=400)
    if User.objects.filter(username=username).exists():
        return api_error("用户名已存在", status=400)

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=name,
        email=data.get("email", "").strip(),
    )
    assign_role(user, "分析师")
    profile = ensure_user_profile(user)
    profile.display_name = name or username
    profile.avatar_text = (profile.display_name or username)[:1]
    profile.save(update_fields=["display_name", "avatar_text", "updated_at"])
    log_action(request, "register", {"username": username, "role": "分析师"}, user=user)
    login(request, user)
    return api_ok({"user": user_payload(user)})


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    data = parse_json(request)
    user = authenticate(
        request,
        username=data.get("username", ""),
        password=data.get("password", ""),
    )
    if not user:
        return api_error("用户名或密码错误", status=401)
    if not user.is_active:
        return api_error("该账号已停用", status=403)
    login(request, user)
    log_action(request, "login", {"username": user.username}, user=user)
    return api_ok({"user": user_payload(user)})


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    log_action(request, "logout", {}, user=current_user(request))
    logout(request)
    return api_ok({"message": "已退出登录"})


def me(request):
    user = current_user(request)
    return api_ok({"user": user_payload(user) if user else None})


@csrf_exempt
@require_http_methods(["PATCH", "PUT"])
def profile_view(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    name = data.get("name", "").strip() or display_name(user)
    email = data.get("email", "").strip()
    avatar_text = (data.get("avatarText") or data.get("avatar_text") or name[:1] or user.username[:1]).strip()[:2]
    avatar_url = data.get("avatarUrl") or data.get("avatar_url") or ""

    user.first_name = name
    user.email = email
    user.save(update_fields=["first_name", "email"])
    profile = ensure_user_profile(user)
    profile.display_name = name
    profile.avatar_text = avatar_text
    profile.avatar_url = avatar_url
    profile.save(update_fields=["display_name", "avatar_text", "avatar_url", "updated_at"])
    log_action(request, "profile.update", {"username": user.username}, user=user)
    return api_ok({"user": user_payload(user)})


def dashboard(request):
    user = current_user(request)
    task_qs = SearchTask.objects.filter(owner=user) if user else SearchTask.objects.none()
    record_qs = LiteratureRecord.objects.filter(task__owner=user) if user else LiteratureRecord.objects.none()
    analysis_qs = AnalysisResult.objects.filter(task__owner=user) if user else AnalysisResult.objects.none()
    report_qs = Report.objects.filter(owner=user) if user else Report.objects.none()
    experiment_qs = ExperimentPlan.objects.filter(owner=user) if user else ExperimentPlan.objects.none()
    recent_tasks = task_qs[:6]
    source_distribution = (
        record_qs.values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    return api_ok(
        {
            "stats": {
                "tasks": task_qs.count(),
                "literature": record_qs.count(),
                "analyses": analysis_qs.count(),
                "experiments": experiment_qs.count(),
                "reports": report_qs.count(),
                "summaries": task_qs.exclude(review_text="").count(),
                "logs": SystemLog.objects.filter(user=user).count() if user else 0,
            },
            "recent_tasks": [task_to_dict(task, include_records=False) for task in recent_tasks],
            "source_distribution": list(source_distribution),
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def users(request):
    denied = require_admin(request)
    if denied:
        return denied
    if request.method == "GET":
        return api_ok({"users": [managed_user_payload(user) for user in User.objects.order_by("id")]})

    data = parse_json(request)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip()
    role = normalize_role(data.get("role"))
    if not username or not password:
        return api_error("账号和密码不能为空", status=400)
    if len(password) < 6:
        return api_error("密码至少需要 6 位", status=400)
    if User.objects.filter(username=username).exists():
        return api_error("账号已存在", status=400)

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=name,
        email=data.get("email", "").strip(),
    )
    user.is_staff = role == "管理员"
    user.save(update_fields=["is_staff"])
    assign_role(user, role)
    profile = ensure_user_profile(user)
    profile.display_name = name or username
    profile.avatar_text = (profile.display_name or username)[:1]
    profile.save(update_fields=["display_name", "avatar_text", "updated_at"])
    log_action(request, "user.create", {"username": username, "role": role})
    return api_ok({"user": managed_user_payload(user)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH", "PUT", "DELETE"])
def user_detail(request, user_id):
    denied = require_admin(request)
    if denied:
        return denied
    target = get_object_or_404(User, id=user_id)
    if request.method == "DELETE":
        if target.id == request.user.id:
            return api_error("不能删除当前登录账号", status=400)
        if is_last_admin(target):
            return api_error("至少需要保留一个管理员账号", status=400)
        username = target.username
        target.delete()
        log_action(request, "user.delete", {"username": username})
        return api_ok({"message": "用户已删除"})

    data = parse_json(request)
    name = data.get("name", "").strip() or display_name(target)
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    requested_role = normalize_role(data.get("role"))

    target.first_name = name
    target.email = email
    if password:
        if len(password) < 6:
            return api_error("密码至少需要 6 位", status=400)
        target.set_password(password)
    if not is_role_locked(target):
        target.is_staff = requested_role == "管理员"
        assign_role(target, requested_role)
    target.save()
    profile = ensure_user_profile(target)
    profile.display_name = name
    profile.avatar_text = (profile.avatar_text or name[:1] or target.username[:1])[:2]
    profile.save(update_fields=["display_name", "avatar_text", "updated_at"])
    log_action(request, "user.update", {"username": target.username, "role": role_for_user(target)})
    return api_ok({"user": managed_user_payload(target)})


@require_http_methods(["GET"])
def logs(request):
    denied = require_admin(request)
    if denied:
        return denied
    rows = [log_payload(item) for item in SystemLog.objects.select_related("user")[:300]]
    return api_ok({"logs": rows})


@require_http_methods(["GET"])
def activity(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    rows = []
    for item in SystemLog.objects.filter(user=user).select_related("user")[:100]:
        payload = activity_payload(item)
        if payload:
            rows.append(payload)
    return api_ok({"activities": rows})


@require_http_methods(["GET"])
def notifications(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    items = []
    for item in SystemLog.objects.filter(user=user).select_related("user")[:30]:
        payload = notification_payload(item)
        if payload:
            items.append(payload)
    if not items:
        items.append(
            {
                "id": f"welcome-{user.id}",
                "username": user.username,
                "text": f"{display_name(user)}，欢迎使用科学文献研究智能体。你的账号数据会从后端数据库读取，前端不会保存明文密码。",
                "time": format_datetime(timezone.now()),
                "icon": "Bell",
                "tone": "blue",
            }
        )
    return api_ok({"notifications": items})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def todos(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    if request.method == "GET":
        ensure_default_todos(user)
        items = [todo_payload(item) for item in user.todo_items.all()]
        return api_ok({"todos": items})

    data = parse_json(request)
    title = data.get("title", "").strip()
    if not title:
        return api_error("待办标题不能为空", status=400)
    item = TodoItem.objects.create(
        owner=user,
        title=title,
        description=data.get("desc", data.get("description", "")).strip(),
        due_date=parse_due_date(data.get("dueDate") or data.get("due_date")),
        urgent=bool(data.get("urgent")),
    )
    log_action(request, "todo.create", {"todo_id": item.id, "title": item.title}, user=user)
    return api_ok({"todo": todo_payload(item)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH", "PUT", "DELETE"])
def todo_detail(request, todo_id):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    item = get_object_or_404(TodoItem, id=todo_id, owner=user)
    if request.method == "DELETE":
        title = item.title
        item.delete()
        log_action(request, "todo.delete", {"todo_id": todo_id, "title": title}, user=user)
        return api_ok({"message": "待办已删除"})

    if todo_status(item) == "expired":
        return api_error("已过期待办不能恢复到未完成或已完成", status=400)
    data = parse_json(request)
    if "title" in data:
        item.title = data.get("title", "").strip() or item.title
    if "desc" in data or "description" in data:
        item.description = data.get("desc", data.get("description", "")).strip()
    if "dueDate" in data or "due_date" in data:
        item.due_date = parse_due_date(data.get("dueDate") or data.get("due_date"))
    if "urgent" in data:
        item.urgent = bool(data.get("urgent"))
    if "status" in data:
        status = data.get("status")
        if status not in [TodoItem.Status.PENDING, TodoItem.Status.COMPLETED]:
            return api_error("待办状态不正确", status=400)
        item.status = status
    item.save()
    log_action(request, "todo.update", {"todo_id": item.id, "title": item.title, "status": todo_status(item)}, user=user)
    return api_ok({"todo": todo_payload(item)})


def current_user(request):
    if request.user.is_authenticated:
        return request.user
    return None


def user_payload(user):
    if not user:
        return None
    profile = ensure_user_profile(user)
    role = role_for_user(user)
    return {
        "id": user.id,
        "username": user.username,
        "name": display_name(user),
        "email": user.email,
        "role": role,
        "roles": list(user.groups.values_list("name", flat=True)),
        "avatarText": profile.avatar_text or display_name(user)[:1],
        "avatarUrl": profile.avatar_url,
        "canManageSystem": role == "管理员",
        "canManageUsers": role == "管理员",
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def log_action(request, action, detail=None, user=None):
    try:
        SystemLog.objects.create(
            user=user or current_user(request),
            action=action,
            ip_address=_client_ip(request),
            detail=detail or {},
        )
    except Exception:
        pass


def require_admin(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    if role_for_user(user) != "管理员":
        return api_error("只有管理员可以访问该功能", status=403)
    return None


def ensure_user_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": user.first_name or user.get_full_name() or user.username,
            "avatar_text": (user.first_name or user.username)[:1],
        },
    )
    return profile


def display_name(user):
    profile = getattr(user, "research_profile", None)
    if profile and profile.display_name:
        return profile.display_name
    return user.first_name or user.get_full_name() or user.username


def role_for_user(user):
    group_names = set(user.groups.values_list("name", flat=True))
    if user.is_superuser or "管理员" in group_names:
        return "管理员"
    if "运营人员" in group_names:
        return "运营人员"
    return "分析师"


def normalize_role(role):
    return role if role in ROLE_NAMES else "分析师"


def assign_role(user, role):
    role = normalize_role(role)
    for name in ROLE_NAMES:
        group, _ = Group.objects.get_or_create(name=name)
        if name == role:
            user.groups.add(group)
        else:
            user.groups.remove(group)


def role_scope(role):
    return "核心功能、用户与权限管理、系统日志、系统设置" if role == "管理员" else "核心功能、系统设置"


def managed_user_payload(user):
    payload = user_payload(user)
    role = payload["role"]
    return {
        **payload,
        "scope": role_scope(role),
        "source": "数据库",
        "sourceType": "database",
        "status": "启用" if user.is_active else "停用",
        "deleteLocked": user.is_superuser or is_last_admin(user),
        "roleLocked": is_role_locked(user),
    }


def is_last_admin(user):
    if role_for_user(user) != "管理员":
        return False
    return sum(1 for item in User.objects.all() if role_for_user(item) == "管理员") <= 1


def is_role_locked(user):
    return user.is_superuser or is_last_admin(user)


def log_payload(item):
    icon, tone = ACTION_ICONS.get(item.action, ("Files", "gray"))
    return {
        "id": item.id,
        "time": format_datetime(item.created_at),
        "actor": display_name(item.user) if item.user else "系统",
        "username": item.user.username if item.user else "",
        "action": action_label(item),
        "actionCode": item.action,
        "status": "成功",
        "detail": item.detail or {},
        "icon": icon,
        "tone": tone,
    }


def activity_payload(item):
    if item.action not in BUSINESS_ACTIONS:
        return None
    icon, tone = ACTION_ICONS.get(item.action, ("Files", "gray"))
    return {
        "id": item.id,
        "time": format_datetime(item.created_at),
        "actor": display_name(item.user) if item.user else "系统",
        "username": item.user.username if item.user else "",
        "text": activity_text(item),
        "actionCode": item.action,
        "icon": icon,
        "tone": tone,
    }


def notification_payload(item):
    if item.action not in BUSINESS_ACTIONS and item.action not in {"profile.update", "todo.create", "todo.update", "todo.delete"}:
        return None
    icon, tone = ACTION_ICONS.get(item.action, ("Bell", "blue"))
    return {
        "id": f"log-{item.id}",
        "username": item.user.username if item.user else "",
        "text": notification_text(item),
        "time": format_datetime(item.created_at),
        "icon": icon,
        "tone": tone,
    }


def action_label(item):
    detail = item.detail or {}
    action = item.action
    if action == "literature.search":
        return f"检索文献：{detail.get('query', '')}（{detail.get('count', 0)} 篇）"
    if action == "analysis.run":
        return f"运行研究热点与空白分析：任务 {detail.get('task_id', '')}"
    if action == "experiment.create":
        return f"生成实验方案：{detail.get('question', '')}"
    if action == "writing.generate":
        return f"生成论文章节草稿：{detail.get('section', '')}"
    if action == "report.create":
        return f"生成可视化研究报告：任务 {detail.get('task_id', '')}"
    if action == "agent.run":
        return f"运行完整科研智能体流程：{detail.get('query', '')}"
    if action == "login":
        return "登录系统"
    if action == "logout":
        return "退出登录"
    if action == "register":
        return f"注册账号：{detail.get('username', '')}"
    if action == "profile.update":
        return "更新个人资料与头像"
    if action == "todo.create":
        return f"添加待办：{detail.get('title', '')}"
    if action == "todo.update":
        return f"修改待办：{detail.get('title', '')}"
    if action == "todo.delete":
        return f"删除待办：{detail.get('title', '')}"
    if action == "user.create":
        return f"新增用户：{detail.get('username', '')}"
    if action == "user.update":
        return f"修改用户权限：{detail.get('username', '')} -> {detail.get('role', '')}"
    if action == "user.delete":
        return f"删除用户：{detail.get('username', '')}"
    return action


def activity_text(item):
    detail = item.detail or {}
    if item.action == "literature.search":
        return f"检索了关键词“{detail.get('query', '')}”，返回 {detail.get('count', 0)} 篇真实文献"
    if item.action == "analysis.run":
        return "生成了研究热点与研究空白分析"
    if item.action == "experiment.create":
        return "生成了实验方案设计建议"
    if item.action == "writing.generate":
        return f"生成了论文章节草稿：{detail.get('section', '')}"
    if item.action == "report.create":
        return "生成了可视化研究报告"
    if item.action == "agent.run":
        return f"运行了完整科研智能体流程：{detail.get('query', '')}"
    return action_label(item)


def notification_text(item):
    if item.action in BUSINESS_ACTIONS:
        return activity_text(item)
    return action_label(item)


def ensure_default_todos(user):
    if user.todo_items.exists():
        return
    today = timezone.localdate()
    defaults = [
        ("完成一次文献检索", "输入关键词并查看真实检索结果", 3, True),
        ("查看研究空白", "根据检索结果运行热点与空白分析", 7, False),
        ("生成实验方案", "体验实验设计建议和方法推荐", 12, False),
        ("导出研究报告", "生成并下载 Markdown 报告", 18, False),
    ]
    TodoItem.objects.bulk_create(
        [
            TodoItem(
                owner=user,
                title=title,
                description=description,
                due_date=today + timedelta(days=days),
                urgent=urgent,
            )
            for title, description, days, urgent in defaults
        ]
    )


def todo_payload(item):
    status = todo_status(item)
    return {
        "id": item.id,
        "title": item.title,
        "desc": item.description,
        "dueDate": item.due_date.isoformat() if item.due_date else "",
        "time": f"{item.due_date.isoformat()} 到期" if item.due_date else "未设置到期日期",
        "urgent": item.urgent,
        "status": status,
        "createdAt": format_datetime(item.created_at),
        "updatedAt": format_datetime(item.updated_at),
    }


def todo_status(item):
    if item.status == TodoItem.Status.COMPLETED:
        return "completed"
    if item.due_date and item.due_date < timezone.localdate():
        return "expired"
    return "pending"


def parse_due_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def format_datetime(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")
