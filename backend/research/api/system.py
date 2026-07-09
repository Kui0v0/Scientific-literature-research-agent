import os
import sys
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import AnalysisResult, ExperimentPlan, LiteratureRecord, Report, SearchTask, SystemLog, TodoItem
from ..services.llm import llm_config_status
from ..services.rag import rag_config_status
from ..services.serializers import task_to_dict
from .common import (
    api_error,
    api_ok,
    assign_role,
    auth_token_for_user,
    current_user,
    display_name,
    ensure_user_profile,
    format_datetime,
    log_action,
    normalize_role,
    parse_json,
    require_admin,
    role_for_user,
    user_payload,
)


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


def health(request):
    db_name = str(connection.settings_dict.get("NAME") or "")
    payload = {
        "status": "ok",
        "name": "scientific-literature-agent",
        "llm": llm_config_status(),
        "rag": rag_config_status(),
    }
    if settings.DEBUG:
        payload["runtime"] = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "db_engine": connection.settings_dict.get("ENGINE", ""),
            "db_name": os.path.basename(db_name) or db_name,
        }
    return api_ok(payload)


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
    return api_ok({"user": user_payload(user), "auth_token": auth_token_for_user(user)})


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
    return api_ok({"user": user_payload(user), "auth_token": auth_token_for_user(user)})


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    log_action(request, "logout", {}, user=current_user(request))
    logout(request)
    return api_ok({"message": "已退出登录"})


def me(request):
    user = current_user(request)
    return api_ok({"user": user_payload(user) if user else None, "auth_token": auth_token_for_user(user) if user else ""})


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
    source_distribution = record_qs.values("source").annotate(count=Count("id")).order_by("-count")
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
