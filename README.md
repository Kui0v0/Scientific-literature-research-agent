# 科学文献研究智能体

面向科研文献调研的 Django + Vue 项目，支持跨库检索、Milvus RAG 证据召回、大模型综述、研究空白分析、实验方案设计、论文写作辅助和报告导出。

## 功能概览

- 文献检索：接入 PubMed、arXiv、Crossref，返回真实 PMID、arXiv ID、DOI 或原文链接。
- GPT + Milvus RAG：用 embedding 接口生成向量，写入 Milvus 后召回证据，再交给大模型生成回答。
- 研究空白：对每篇文献的标题和摘要调用大模型抽取 3-5 个主题词，统计前 8 个热点，并生成潜在研究空白。
- 实验方案：根据研究空白生成研究目标、路线、方法推荐和风险控制。
- 论文写作：生成摘要、引言、方法、结果、讨论草稿。
- 报告导出：生成 Markdown，并支持 PDF、Word 下载。
- 用户系统：支持登录、角色权限、日志、通知和待办。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 | Django、PyMySQL、Pandas |
| 前端 | Vue 3、Vite、Element Plus |
| 向量数据库 | Milvus |
| 生成模型 | GPT / OpenAI 兼容接口 |
| RAG | OpenAI/Ollama 兼容 embeddings、Milvus 向量召回、可选 BGE rerank |
| 导出 | ReportLab、python-docx |
| 部署 | Docker Compose 或本地开发环境 |

## 目录结构

```text
.
├── backend/
│   ├── literature_agent/       # Django 配置
│   ├── research/               # 业务应用
│   │   ├── services/
│   │   │   ├── connectors.py   # PubMed / arXiv / Crossref 检索
│   │   │   ├── llm.py          # 大模型调用
│   │   │   ├── rag.py          # Milvus RAG 召回
│   │   │   ├── rag_worker.py   # 隔离执行 Milvus 召回
│   │   │   ├── analyzer.py     # 热点与研究空白
│   │   │   ├── experiment.py   # 实验方案
│   │   │   ├── writer.py       # 论文草稿
│   │   │   └── report.py       # 报告生成
│   │   ├── models.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   ├── package.json
│   └── .env.example
├── docker-compose.yml
└── README.md
```

## 从 GitHub 拉取并启动

### 方式一：Docker Compose 推荐

适合快速启动完整环境，包含 MySQL、后端、前端和 Milvus。

1. 克隆项目：

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

2. 复制环境变量：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

3. 编辑根目录 `.env`：

```env
DJANGO_SECRET_KEY=<set-a-random-secret>
MYSQL_PASSWORD=<set-mysql-password>
MYSQL_ROOT_PASSWORD=<set-root-password>

USE_LLM=1
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

USE_MILVUS=1
RAG_EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1
RAG_EMBEDDING_MODEL=embeddinggemma
```

如果使用第三方 OpenAI 兼容网关，把 `OPENAI_BASE_URL` 写在你本地 `.env` 里即可，不要写进 README、截图或 GitHub。

4. 启动 embedding 服务，例如 Ollama：

```bash
ollama pull embeddinggemma
ollama serve
```

5. 启动项目：

```bash
docker compose --profile milvus up --build
```

6. 访问：

- 前端：http://127.0.0.1:5173
- 后端健康检查：http://127.0.0.1:8000/api/health/

### 方式二：本地开发启动

适合需要改代码调试。需要自己准备 MySQL、Milvus 和 embedding 服务。

1. 后端：

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000
```

Windows PowerShell：

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 0.0.0.0:8000
```

2. 前端：

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Windows PowerShell：

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

默认前端会访问 `http://127.0.0.1:8000/api`。

## 关键环境变量

| 变量 | 说明 |
| --- | --- |
| `USE_LLM` | `1` 启用大模型，`0` 使用规则兜底 |
| `OPENAI_API_KEY` | OpenAI 或兼容接口 Key，仅放本地 `.env` |
| `OPENAI_BASE_URL` | OpenAI 或兼容接口地址，仅放本地 `.env` |
| `OPENAI_MODEL` | 生成模型名 |
| `USE_MILVUS` | `1` 启用 Milvus RAG |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 地址和端口 |
| `RAG_EMBEDDING_BASE_URL` | OpenAI/Ollama 兼容 embedding 接口地址 |
| `RAG_EMBEDDING_MODEL` | embedding 模型名，默认建议 `embeddinggemma` |
| `NCBI_EMAIL` / `CROSSREF_MAILTO` | 建议填写，用于学术接口礼貌访问 |

高级超时、token 上限、rerank 等参数已经放在代码默认值里；普通启动不需要填写。

## RAG 工作流

1. 检索 PubMed、arXiv、Crossref 真实文献。
2. 对当前任务文献生成 embedding。
3. 将文献向量和元数据写入 Milvus。
4. 用 Milvus 召回与问题最相关的证据。
5. 可选使用本地 BGE rerank 精排。
6. 将证据包传给大模型，要求所有结论引用 `[R1]`、`[R2]` 等证据编号。
7. 如果大模型失败，后端返回规则兜底结果，页面不会崩溃。

## 常用命令

```bash
# 后端检查
python manage.py check

# 后端迁移
python manage.py migrate

# 初始化演示账号和基础数据
python manage.py seed_demo

# 前端构建
npm run build
```

## 账号与权限

`seed_demo` 会根据本地环境变量初始化演示账号。请在 `.env` 中设置演示账号密码，例如：

```env
DEMO_ADMIN_PASSWORD=<set-demo-admin-password>
DEMO_ANALYST_PASSWORD=<set-demo-analyst-password>
```

不要把真实密码写进 README 或提交到 GitHub。

## 安全与提交规则

- `.env`、`backend/.env`、`frontend/.env` 是本地配置文件，不要提交。
- API Key、数据库密码、私有 Base URL 只放在本地 `.env` 或服务器环境变量中。
- `.env.example` 只能写占位符或公开默认值。
- 提交前建议执行：

```bash
rg "sk-|api_key|OPENAI_API_KEY|MYSQL_PASSWORD|OPENAI_BASE_URL"
```

确认没有真实密钥或私有地址出现在准备提交的文件里。

## 排错

- 前端页面无数据：确认已登录，并检查后端 `http://127.0.0.1:8000/api/health/`。
- 显示规则兜底：通常是 `USE_LLM=0`、API Key 未配置、模型接口超时或 Milvus/embedding 服务不可用。
- Milvus 召回为空：确认 Milvus 端口、embedding 服务地址和 `RAG_EMBEDDING_MODEL` 是否正确。
- Docker 后端连不上 MySQL：等待 `db` healthcheck 通过，或检查根目录 `.env` 中的 MySQL 密码。

## 说明

本项目用于课程实习和科研流程演示。生成内容需要人工复核，不能直接替代正式学术判断。
