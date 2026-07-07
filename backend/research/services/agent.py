from research.models import AnalysisResult, ExperimentPlan, LiteratureRecord, Report, SearchTask, WritingDraft

from .analyzer import analyze_records
from .connectors import search_literature
from .experiment import build_experiment_plan
from .report import build_report
from .summarizer import generate_review
from .writer import generate_draft


def run_full_research_flow(query, sources, user=None):
    task = SearchTask.objects.create(owner=user, query=query, sources=sources, status=SearchTask.Status.RUNNING)
    try:
        records_payload = search_literature(query, sources=sources, limit=10)
        for payload in records_payload:
            LiteratureRecord.objects.create(task=task, **payload)
        task.result_count = len(records_payload)
        task.review_text = generate_review(query, records_payload)
        task.status = SearchTask.Status.DONE
        task.save(update_fields=["result_count", "review_text", "status", "updated_at"])
    except Exception as exc:
        task.status = SearchTask.Status.FAILED
        task.error_message = str(exc)
        task.save(update_fields=["status", "error_message", "updated_at"])
        raise

    analysis_payload = analyze_records(records_payload)
    analysis = AnalysisResult.objects.create(
        task=task,
        hotspots=analysis_payload["hotspots"],
        trends=analysis_payload["trends"],
        source_distribution=analysis_payload["source_distribution"],
        gaps=analysis_payload["gaps"],
        summary=analysis_payload["summary"],
    )

    question = analysis.gaps[0]["suggested_question"] if analysis.gaps else query
    plan_payload = build_experiment_plan(question, analysis_payload, records_payload)
    plan = ExperimentPlan.objects.create(owner=user, analysis=analysis, **plan_payload)

    drafts = []
    for section in ["abstract", "introduction", "methods", "results", "discussion"]:
        draft_payload = generate_draft(
            section,
            query,
            review_text=task.review_text,
            experiment_plan=plan_payload,
            records=records_payload,
            analysis_payload=analysis_payload,
        )
        drafts.append(WritingDraft.objects.create(owner=user, experiment=plan, **draft_payload))

    report_payload = build_report(
        task,
        list(task.records.all()),
        analysis=analysis_payload,
        experiment=plan_payload,
        drafts=drafts,
    )
    report = Report.objects.create(owner=user, task=task, **report_payload)
    return task, analysis, plan, drafts, report
