import json
import math
import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..models import LiteratureRecord, SearchTask
from .common import api_ok, current_user


RESEARCH_AREAS = [
    {
        "id": "natural",
        "name": "自然科学",
        "english": "Natural Sciences",
        "color": "#3b73ff",
        "terms": [
            "physics", "chemistry", "biology", "biological", "molecular", "genomics", "genetics",
            "astronomy", "astrophysics", "earth science", "geology", "geoscience", "climate", "ecology",
            "environment", "evolution", "mathematics", "mathematical", "ocean", "atmospheric",
            "biodiversity", "quantum", "particle", "物理", "化学", "生物", "天文", "地球科学", "地质",
            "生态", "环境", "数学", "气候",
        ],
    },
    {
        "id": "engineering",
        "name": "工程与技术",
        "english": "Engineering & Technology",
        "color": "#8b5cf6",
        "terms": [
            "engineering", "technology", "computer science", "computer", "algorithm", "software", "hardware",
            "network", "machine learning", "deep learning", "artificial intelligence", "ai",
            "large language model", "llm", "natural language processing", "nlp", "robotics", "robot",
            "mechanical", "materials", "civil engineering", "electrical", "electronics", "automation",
            "control", "manufacturing", "semiconductor", "工程", "技术", "计算机", "算法", "软件",
            "人工智能", "机器学习", "深度学习", "大语言模型", "机器人", "机械", "材料", "土木", "电气",
        ],
    },
    {
        "id": "medicine",
        "name": "医学与健康",
        "english": "Medicine & Health Sciences",
        "color": "#18c29c",
        "terms": [
            "medicine", "medical", "clinical", "health", "disease", "therapy", "treatment", "drug",
            "pharmacology", "pharmacy", "public health", "epidemiology", "neuroscience", "neurology",
            "patient", "diagnosis", "cancer", "tumor", "immune", "immunology", "vaccine", "hospital",
            "医学", "临床", "健康", "疾病", "治疗", "药学", "公共卫生", "神经科学", "患者", "诊断",
            "肿瘤", "免疫", "疫苗",
        ],
    },
    {
        "id": "agriculture",
        "name": "农业科学",
        "english": "Agricultural Sciences",
        "color": "#ff8a2a",
        "terms": [
            "agriculture", "agricultural", "crop", "crops", "agronomy", "horticulture", "livestock",
            "animal husbandry", "veterinary", "forestry", "forest", "fisheries", "aquaculture",
            "plant breeding", "irrigation", "pest", "weed", "farm", "soil fertility", "农业", "农学",
            "作物", "园艺", "畜牧", "兽医", "林学", "水产", "灌溉", "育种", "农场",
        ],
    },
    {
        "id": "ssh",
        "name": "社会科学与人文",
        "english": "Social Sciences & Humanities",
        "color": "#ff4d6d",
        "terms": [
            "social sciences", "humanities", "economics", "psychology", "sociology", "language",
            "languages", "linguistic", "linguistics", "literature", "philosophy", "history", "education",
            "law", "management", "business", "political", "communication", "anthropology", "culture",
            "translation", "semantics", "phonology", "reading", "writing", "second language",
            "language acquisition", "discourse", "ssci", "社会科学", "人文", "经济", "心理学", "社会学",
            "语言", "语言学", "文学", "哲学", "历史", "教育", "法律", "管理", "传播", "文化", "翻译",
        ],
    },
]

RESEARCH_AREA_BY_ID = {area["id"]: area for area in RESEARCH_AREAS}
INNOVATION_SIGNALS = [
    "novel", "new", "emerging", "proposed", "innovative", "framework", "model", "approach",
    "paradigm", "新", "创新", "提出", "框架", "模型",
]
METHOD_SIGNALS = [
    "experiment", "experimental", "dataset", "evaluation", "simulation", "benchmark", "analysis",
    "method", "trial", "survey", "实验", "数据集", "评估", "仿真", "方法", "调查",
]
APPLICATION_SIGNALS = [
    "application", "applied", "clinical", "industry", "deployment", "practice", "platform", "system",
    "service", "education", "policy", "应用", "临床", "产业", "部署", "平台", "系统", "教育", "政策",
]
GAP_SIGNALS = [
    "limited", "lack", "unclear", "insufficient", "challenge", "bottleneck", "gap", "future work",
    "不足", "缺乏", "挑战", "瓶颈", "空白",
]


@require_http_methods(["GET"])
def trend_statistics(request):
    user = current_user(request)
    if not user:
        return api_ok(
            {
                "range": request.GET.get("range", "2m"),
                "is_real": True,
                "date_basis": "published_at_or_retrieved_at",
                "category_basis": "content_classification",
                "record_count": 0,
                "bucket_days": 0,
                "start_date": "",
                "end_date": "",
                "buckets": [],
                "categories": _category_payload(),
                "series": [],
            }
        )
    range_key = request.GET.get("range", "2m")
    days = 180 if range_key == "6m" else 60
    bucket_count = 12 if range_key == "6m" else 9
    end_date = timezone.localdate()
    start_date = end_date - timedelta(days=days - 1)
    bucket_days = max(1, math.ceil(days / bucket_count))
    buckets = []
    for index in range(bucket_count):
        bucket_start = start_date + timedelta(days=index * bucket_days)
        buckets.append({"label": bucket_start.strftime("%m-%d"), "start": bucket_start.isoformat()})

    records = list(
        LiteratureRecord.objects.filter(
            Q(published_at__gte=start_date, published_at__lte=end_date)
            | Q(created_at__date__gte=start_date, created_at__date__lte=end_date)
        )
        .filter(task__owner=user)
        .exclude(source__iexact="Demo")
        .select_related("task")
    )
    trend_records = []
    for record in records:
        trend_date = _trend_record_date(record, start_date, end_date)
        if trend_date:
            trend_records.append((record, trend_date, _classify_research_area(record)))

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
            "categories": _category_payload(),
            "series": series,
        }
    )


@require_http_methods(["GET"])
def gap_statistics(request):
    user = current_user(request)
    if not user:
        return api_ok(_empty_gap_statistics_payload())
    task = _gap_statistics_task(request)
    if not task:
        return api_ok(_empty_gap_statistics_payload())

    current_records = list(task.records.exclude(source__iexact="Demo").select_related("task"))
    query = (request.GET.get("query") or task.query).strip()
    area = _dominant_research_area(current_records, query)
    all_real_records = list(
        LiteratureRecord.objects.filter(task__owner=user).exclude(source__iexact="Demo").select_related("task")
    )
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


def _category_payload():
    return [
        {"id": area["id"], "name": area["name"], "english": area["english"], "color": area["color"]}
        for area in RESEARCH_AREAS
    ]


def _gap_statistics_task(request):
    user = current_user(request)
    if not user:
        return None
    task_id = request.GET.get("task_id")
    if not task_id:
        return None
    try:
        return SearchTask.objects.get(id=int(task_id), owner=user, status=SearchTask.Status.DONE)
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
