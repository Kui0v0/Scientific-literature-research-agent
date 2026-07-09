import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from research.models import AnalysisResult, ExperimentPlan, LiteratureRecord, Report, SearchTask, UserProfile, WritingDraft
from research.services.analyzer import analyze_records
from research.services.connectors import demo_records
from research.services.experiment import build_experiment_plan
from research.services.report import build_report
from research.services.summarizer import generate_review
from research.services.writer import generate_draft


ROLES = ["管理员", "运营人员", "分析师"]
MEMBER_ACCOUNTS = [
    ("mengyongqi", "孟永琪", "管理员", "DEMO_MENGYONGQI_PASSWORD"),
    ("xichunyu", "郗纯瑜", "分析师", "DEMO_XICHUNYU_PASSWORD"),
    ("yangzhipeng", "杨志鹏", "分析师", "DEMO_YANGZHIPENG_PASSWORD"),
    ("zhangzhiyong", "张智勇", "分析师", "DEMO_ZHANGZHIYONG_PASSWORD"),
    ("wangxiangqian", "王向前", "运营人员", "DEMO_WANGXIANGQIAN_PASSWORD"),
]


class Command(BaseCommand):
    help = "Create database-backed demo users and a complete research workflow."

    def handle(self, *args, **options):
        for role in ROLES:
            Group.objects.get_or_create(name=role)

        users = {}
        for username, name, role, password_env in MEMBER_ACCOUNTS:
            user, created = User.objects.get_or_create(username=username)
            password = demo_password(password_env, role)
            if password:
                user.set_password(password)
            elif created:
                user.set_unusable_password()
            user.first_name = name
            user.email = ""
            user.is_staff = role == "管理员"
            user.is_superuser = role == "管理员"
            user.save()
            assign_role(user, role)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.display_name = name
            profile.avatar_text = name[:1]
            profile.save(update_fields=["display_name", "avatar_text", "updated_at"])
            users[username] = user

        # Optional generic local admin account. Its password is also env-only.
        admin, created = User.objects.get_or_create(username="admin")
        admin_password = os.getenv("DEMO_ADMIN_PASSWORD")
        if admin_password:
            admin.set_password(admin_password)
        elif created:
            admin.set_unusable_password()
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        assign_role(admin, "管理员")

        if SearchTask.objects.exists():
            self.stdout.write(self.style.WARNING("Demo workflow data already exists."))
            return

        owner = users.get("xichunyu") or admin
        query = "科学文献研究智能体：从综述到实验设计"
        records_payload = demo_records(query, 6)
        task = SearchTask.objects.create(
            owner=owner,
            query=query,
            sources=["pubmed", "arxiv"],
            status=SearchTask.Status.DONE,
            result_count=len(records_payload),
            review_text=generate_review(query, records_payload),
        )
        for payload in records_payload:
            LiteratureRecord.objects.create(task=task, **payload)

        analysis_payload = analyze_records(records_payload)
        analysis = AnalysisResult.objects.create(
            task=task,
            hotspots=analysis_payload["hotspots"],
            trends=analysis_payload["trends"],
            source_distribution=analysis_payload["source_distribution"],
            gaps=analysis_payload["gaps"],
            summary=analysis_payload["summary"],
        )
        question = analysis.gaps[0]["suggested_question"]
        plan_payload = build_experiment_plan(question, analysis_payload)
        plan = ExperimentPlan.objects.create(owner=owner, analysis=analysis, **plan_payload)

        drafts = []
        for section in ["abstract", "introduction", "methods", "results", "discussion"]:
            draft_payload = generate_draft(
                section,
                query,
                review_text=task.review_text,
                experiment_plan=plan_payload,
            )
            drafts.append(WritingDraft.objects.create(owner=owner, experiment=plan, **draft_payload))

        report_payload = build_report(task, list(task.records.all()), analysis_payload, plan_payload, drafts)
        Report.objects.create(owner=owner, task=task, **report_payload)

        self.stdout.write(self.style.SUCCESS("Database demo users and workflow data created."))
        self.stdout.write("Demo passwords are loaded from environment variables only; no password is stored in source code.")


def assign_role(user, role):
    for name in ROLES:
        group = Group.objects.get(name=name)
        if name == role:
            user.groups.add(group)
        else:
            user.groups.remove(group)


def demo_password(password_env, role):
    role_default = "DEMO_ADMIN_PASSWORD" if role == "管理员" else "DEMO_ANALYST_PASSWORD"
    return os.getenv(password_env) or os.getenv(role_default)
