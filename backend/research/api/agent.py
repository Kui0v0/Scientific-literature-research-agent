from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..services.agent import run_full_research_flow
from ..services.connectors import RetrievalError
from ..services.serializers import analysis_to_dict, draft_to_dict, experiment_to_dict, report_to_dict, task_to_dict
from .common import api_error, api_ok, current_user, log_action, parse_json


@csrf_exempt
@require_http_methods(["POST"])
def agent_run(request):
    user = current_user(request)
    if not user:
        return api_error("请先登录", status=401)
    data = parse_json(request)
    query = data.get("query", "").strip()
    if not query:
        return api_error("研究主题不能为空", status=400)
    try:
        task, analysis, plan, drafts, item = run_full_research_flow(
            query,
            data.get("sources") or ["pubmed", "arxiv", "crossref"],
            user=user,
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
