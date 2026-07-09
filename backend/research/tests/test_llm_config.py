import os
from unittest import TestCase
from unittest.mock import patch

from research.services import llm


class LLMConfigTests(TestCase):
    def test_openai_compatible_config_ignores_deepseek_specific_variables(self):
        env = {
            "USE_LLM": "1",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://gateway.example/v1",
            "OPENAI_MODEL": "gpt-test",
            "DEEPSEEK_API_KEY": "deepseek-test",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            status = llm.llm_config_status()

        self.assertTrue(status["enabled"])
        self.assertEqual(status["provider"], "GPT")
        self.assertEqual(status["model"], "gpt-test")
        self.assertEqual(status["base_url"], "custom-configured")

    def test_deepseek_key_alone_does_not_enable_llm(self):
        env = {
            "USE_LLM": "1",
            "DEEPSEEK_API_KEY": "deepseek-test",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }

        with patch.dict(os.environ, env, clear=True):
            status = llm.llm_config_status()

        self.assertFalse(status["enabled"])
        self.assertFalse(status["has_api_key"])
        self.assertEqual(status["provider"], "")
        self.assertIn("OPENAI_API_KEY", status["status"])
