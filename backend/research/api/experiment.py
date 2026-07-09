from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import AnalysisResult, ExperimentPlan
from ..services.experiment import build_experiment_plan
from ..services.serializers import analysis_to_dict, experiment_to_dict, record_to_dict
from .analysis import ensure_current_analysis
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def experiment(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    analysis = get_object_or_404(AnalysisResult, id=data.get("analysis_id"), task__owner=user)
    analysis = ensure_current_analysis(analysis)
    analysis_payload = analysis_to_dict(analysis)
    default_question = analysis.gaps[0]["suggested_question"] if analysis.gaps else analysis.task.query
    question = data.get("question") or default_question
    records_payload = [record_to_dict(record) for record in analysis.task.records.all()]
    plan_payload = build_experiment_plan(question, analysis_payload, records_payload)
    plan = ExperimentPlan.objects.create(owner=user, analysis=analysis, **plan_payload)
    log_action(request, "experiment.create", {"analysis_id": analysis.id, "question": question})
    return api_ok({"experiment": experiment_to_dict(plan)})
