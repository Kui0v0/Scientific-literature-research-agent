from django.contrib import admin

from .models import (
    AnalysisResult,
    ExperimentPlan,
    LiteratureRecord,
    Report,
    SearchTask,
    SystemLog,
    WritingDraft,
)


@admin.register(SearchTask)
class SearchTaskAdmin(admin.ModelAdmin):
    list_display = ("query", "status", "result_count", "owner", "created_at")
    search_fields = ("query",)
    list_filter = ("status", "created_at")


@admin.register(LiteratureRecord)
class LiteratureRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "published_at")
    search_fields = ("title", "abstract", "doi")
    list_filter = ("source", "published_at")


admin.site.register(AnalysisResult)
admin.site.register(ExperimentPlan)
admin.site.register(WritingDraft)
admin.site.register(Report)
admin.site.register(SystemLog)

