from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import ExperimentPlan, Report, SearchTask
from ..services.exporters import report_filename, render_report_docx, render_report_pdf
from ..services.report import build_report
from ..services.serializers import analysis_to_dict, experiment_to_dict, report_to_dict
from .analysis import analysis_for_response
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def report(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    task = get_object_or_404(SearchTask, id=data.get("task_id"), owner=user)
    analysis = analysis_for_response(task)
    analysis_payload = analysis_to_dict(analysis) if analysis else {}
    plan = None
    if data.get("experiment_id"):
        plan = get_object_or_404(ExperimentPlan, id=data.get("experiment_id"), owner=user)
    elif analysis:
        plan = analysis.experiment_plans.filter(owner=user).order_by("-created_at").first()
    drafts = list(plan.drafts.all()) if plan else []
    report_payload = build_report(
        task,
        list(task.records.all()),
        analysis=analysis_payload,
        experiment=experiment_to_dict(plan) if plan else {},
        drafts=drafts,
    )
    item = Report.objects.create(owner=user, task=task, **report_payload)
    log_action(request, "report.create", {"task_id": task.id, "report_id": item.id})
    return api_ok({"report": report_to_dict(item)})


def report_detail(request, report_id):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    item = get_object_or_404(Report, id=report_id, owner=user)
    return api_ok({"report": report_to_dict(item)})


def report_markdown(request, report_id):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    item = get_object_or_404(Report, id=report_id, owner=user)
    response = HttpResponse(item.content_md, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="report-{item.id}.md"'
    return response


def report_download(request, report_id):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    item = get_object_or_404(Report, id=report_id, owner=user)
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
