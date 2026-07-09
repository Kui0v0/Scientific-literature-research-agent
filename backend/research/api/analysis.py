from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import AnalysisResult, SearchTask
from ..services.analyzer import analyze_records, uses_legacy_hotspots
from ..services.serializers import analysis_to_dict, record_to_dict
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def analyze(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    task = get_object_or_404(SearchTask, id=data.get("task_id"), owner=user)
    analysis = run_analysis_for_task(task)
    log_action(request, "analysis.run", {"task_id": task.id, "gap_count": len(analysis.gaps)})
    return api_ok({"analysis": analysis_to_dict(analysis)})


def task_analysis(task):
    try:
        return task.analysis
    except AnalysisResult.DoesNotExist:
        return None


def analysis_for_response(task):
    analysis = task_analysis(task)
    return ensure_current_analysis(analysis) if analysis else None


def ensure_current_analysis(analysis):
    if uses_legacy_hotspots(analysis.hotspots):
        return run_analysis_for_task(analysis.task)
    return analysis


def run_analysis_for_task(task):
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
