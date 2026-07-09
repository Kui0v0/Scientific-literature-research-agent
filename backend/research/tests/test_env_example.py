from pathlib import Path

from django.test import SimpleTestCase


class EnvExampleTests(SimpleTestCase):
    def test_env_example_keeps_only_common_runtime_settings(self):
        env_example = Path(__file__).resolve().parents[3] / ".env.example"
        content = env_example.read_text(encoding="utf-8")

        required_names = [
            "DJANGO_SECRET_KEY=",
            "MYSQL_PASSWORD=",
            "MYSQL_ROOT_PASSWORD=",
            "USE_LLM=",
            "OPENAI_API_KEY=",
            "OPENAI_BASE_URL=",
            "OPENAI_MODEL=",
            "USE_MILVUS=",
            "RAG_EMBEDDING_BASE_URL=",
            "RAG_EMBEDDING_MODEL=",
        ]
        for name in required_names:
            with self.subTest(name=name):
                self.assertIn(name, content)

        noisy_names = [
            "DEEPSEEK_",
            "LLM_PROVIDER",
            "LLM_PROVIDER_NAME",
            "LLM_HTTP_USER_AGENT",
            "LLM_ACCEPT_LANGUAGE",
            "LLM_USE_JSON_MODE",
            "RAG_RERANK_",
            "MILVUS_TOKEN",
            "MILVUS_USER",
            "MILVUS_PASSWORD",
            "MILVUS_SECURE",
        ]
        for name in noisy_names:
            with self.subTest(name=name):
                self.assertNotIn(name, content)
