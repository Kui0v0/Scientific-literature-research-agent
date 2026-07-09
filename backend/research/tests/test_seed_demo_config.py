import os
from unittest import TestCase
from unittest.mock import patch

from research.management.commands.seed_demo import demo_password


class SeedDemoConfigTests(TestCase):
    def test_member_accounts_can_share_analyst_demo_password(self):
        env = {
            "DEMO_ADMIN_PASSWORD": "admin-pass",
            "DEMO_ANALYST_PASSWORD": "analyst-pass",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(demo_password("DEMO_XICHUNYU_PASSWORD", "分析师"), "analyst-pass")
            self.assertEqual(demo_password("DEMO_WANGXIANGQIAN_PASSWORD", "运营人员"), "analyst-pass")
            self.assertEqual(demo_password("DEMO_MENGYONGQI_PASSWORD", "管理员"), "admin-pass")

    def test_member_specific_password_overrides_shared_password(self):
        env = {
            "DEMO_ANALYST_PASSWORD": "analyst-pass",
            "DEMO_XICHUNYU_PASSWORD": "member-pass",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(demo_password("DEMO_XICHUNYU_PASSWORD", "分析师"), "member-pass")
