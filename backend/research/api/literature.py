from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import LiteratureRecord, SearchTask
from ..services.connectors import RetrievalError, search_literature
from ..services.rag import env_int
from ..services.serializers import analysis_to_dict, task_to_dict
from ..services.summarizer import generate_review
from .analysis import analysis_for_response
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def search(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录后再使用检索功能", status=401)
    data = parse_json(request)
    query = data.get("query", "").strip()
    sources = data.get("sources") or ["pubmed", "arxiv", "crossref"]
    if not query:
        return api_error("研究主题不能为空", status=400)

    task = SearchTask.objects.create(
        owner=user,
        query=query,
        sources=sources,
        status=SearchTask.Status.RUNNING,
    )
    try:
        records_payload = search_literature(query, sources=sources, limit=int(data.get("limit", 10)))
        for payload in records_payload:
            LiteratureRecord.objects.create(task=task, **payload)
        task.result_count = len(records_payload)
        task.review_text = generate_review(
            query,
            records_payload,
            timeout_seconds=env_int("SEARCH_REVIEW_TIMEOUT", 45, minimum=5, maximum=120),
        )
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
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    task = get_object_or_404(SearchTask, id=task_id, owner=user)
    payload = {"task": task_to_dict(task)}
    analysis = analysis_for_response(task)
    if analysis:
        payload["analysis"] = analysis_to_dict(analysis)
    return api_ok(payload)
