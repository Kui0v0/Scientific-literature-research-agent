from django.conf import settings
from django.db import models


class SearchTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "等待中"
        RUNNING = "running", "运行中"
        DONE = "done", "已完成"
        FAILED = "failed", "失败"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_tasks",
    )
    query = models.CharField(max_length=255)
    sources = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    result_count = models.PositiveIntegerField(default=0)
    review_text = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.query} ({self.status})"


class LiteratureRecord(models.Model):
    task = models.ForeignKey(SearchTask, on_delete=models.CASCADE, related_name="records")
    title = models.CharField(max_length=600)
    authors = models.JSONField(default=list)
    abstract = models.TextField(blank=True)
    source = models.CharField(max_length=80)
    published_at = models.DateField(null=True, blank=True)
    doi = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=800, blank=True)
    keywords = models.JSONField(default=list)
    raw_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "title"]
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["published_at"]),
        ]

    def __str__(self):
        return self.title


class AnalysisResult(models.Model):
    task = models.OneToOneField(SearchTask, on_delete=models.CASCADE, related_name="analysis")
    hotspots = models.JSONField(default=list)
    trends = models.JSONField(default=list)
    source_distribution = models.JSONField(default=list)
    gaps = models.JSONField(default=list)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"分析结果：{self.task.query}"


class ExperimentPlan(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="experiment_plans",
    )
    analysis = models.ForeignKey(
        AnalysisResult,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="experiment_plans",
    )
    question = models.CharField(max_length=600)
    goal = models.TextField()
    methods = models.JSONField(default=list)
    route = models.JSONField(default=list)
    expected_results = models.TextField(blank=True)
    risks = models.JSONField(default=list)
    content_md = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question


class WritingDraft(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="writing_drafts",
    )
    experiment = models.ForeignKey(
        ExperimentPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drafts",
    )
    section = models.CharField(max_length=80)
    style = models.CharField(max_length=120, default="学术中文")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.section} 草稿"


class Report(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
    )
    title = models.CharField(max_length=255)
    task = models.ForeignKey(
        SearchTask,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
    )
    payload = models.JSONField(default=dict)
    content_md = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class SystemLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="system_logs",
    )
    action = models.CharField(max_length=120)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.action


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    avatar_text = models.CharField(max_length=8, blank=True)
    avatar_url = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.user.username


class TodoItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待完成"
        COMPLETED = "completed", "已完成"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="todo_items",
    )
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    due_date = models.DateField(null=True, blank=True)
    urgent = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return self.title
