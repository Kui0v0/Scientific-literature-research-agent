from django.test import SimpleTestCase
from django.urls import resolve


class ApiRouteOrganizationTests(SimpleTestCase):
    def test_core_routes_resolve_to_split_api_modules(self):
        expected_modules = {
            "/api/health/": "research.api.system",
            "/api/literature/search/": "research.api.literature",
            "/api/tasks/1/": "research.api.literature",
            "/api/analysis/": "research.api.analysis",
            "/api/statistics/gaps/": "research.api.statistics",
            "/api/experiment/": "research.api.experiment",
            "/api/writing/": "research.api.writing",
            "/api/reports/": "research.api.reports",
            "/api/agent/run/": "research.api.agent",
            "/api/users/": "research.api.system",
        }

        for path, module_name in expected_modules.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).func.__module__, module_name)
