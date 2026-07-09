import json

from django.contrib.auth.models import Group, User
from django.core import signing
from django.http import JsonResponse
from django.utils import timezone

from ..models import SystemLog, UserProfile


ROLE_NAMES = ["管理员", "运营人员", "分析师"]


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


def current_user(request):
    if request.user.is_authenticated:
        return request.user
    token = request.headers.get("X-Research-Auth") or request.GET.get("auth_token") or ""
    if not token:
        return None
    try:
        payload = signing.loads(token, salt="research-agent-auth", max_age=60 * 60 * 24 * 7)
        user_id = int(payload.get("user_id"))
    except Exception:
        return None
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return None


def auth_token_for_user(user):
    if not user:
        return ""
    return signing.dumps({"user_id": user.id}, salt="research-agent-auth")


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


def format_datetime(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
