from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import ExperimentPlan, WritingDraft
from ..services.serializers import analysis_to_dict, draft_to_dict, experiment_to_dict, record_to_dict
from ..services.writer import generate_draft
from .analysis import ensure_current_analysis
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def writing(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    plan = get_object_or_404(ExperimentPlan, id=data.get("experiment_id"), owner=user)
    if plan.analysis:
        plan.analysis = ensure_current_analysis(plan.analysis)
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
    draft = WritingDraft.objects.create(owner=user, experiment=plan, **draft_payload)
    log_action(request, "writing.generate", {"experiment_id": plan.id, "section": draft.section})
    return api_ok({"draft": draft_to_dict(draft)})
