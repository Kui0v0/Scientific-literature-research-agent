from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("auth/register/", views.register),
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me),
    path("profile/", views.profile_view),
    path("dashboard/", views.dashboard),
    path("users/", views.users),
    path("users/<int:user_id>/", views.user_detail),
    path("logs/", views.logs),
    path("activity/", views.activity),
    path("notifications/", views.notifications),
    path("todos/", views.todos),
    path("todos/<int:todo_id>/", views.todo_detail),
    path("statistics/trends/", views.trend_statistics),
    path("statistics/gaps/", views.gap_statistics),
    path("literature/search/", views.search),
    path("tasks/<int:task_id>/", views.task_detail),
    path("analysis/", views.analyze),
    path("experiment/", views.experiment),
    path("writing/", views.writing),
    path("reports/", views.report),
    path("reports/<int:report_id>/", views.report_detail),
    path("reports/<int:report_id>/download/", views.report_download),
    path("reports/<int:report_id>/markdown/", views.report_markdown),
    path("agent/run/", views.agent_run),
]
