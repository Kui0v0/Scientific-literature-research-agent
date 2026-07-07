# API 接口说明

后端基础地址：`http://127.0.0.1:8000/api`

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/health/` | GET | 健康检查 |
| `/auth/register/` | POST | 注册用户并分配角色 |
| `/auth/login/` | POST | 用户登录 |
| `/auth/logout/` | POST | 用户退出 |
| `/auth/me/` | GET | 获取当前登录用户 |
| `/dashboard/` | GET | 获取任务、文献、分析和报告统计 |
| `/statistics/trends/` | GET | 基于真实文献记录的五大学科热点趋势统计 |
| `/statistics/gaps/` | GET | 基于检索关键词和真实文献记录的研究空白雷达统计 |
| `/literature/search/` | POST | 跨库文献检索与结构化摘要 |
| `/tasks/<id>/` | GET | 获取检索任务详情 |
| `/analysis/` | POST | 生成热点趋势和研究空白分析 |
| `/experiment/` | POST | 生成实验方案设计建议 |
| `/writing/` | POST | 生成论文章节草稿 |
| `/reports/` | POST | 生成研究报告 |
| `/reports/<id>/` | GET | 获取研究报告详情 |
| `/reports/<id>/markdown/` | GET | 下载 Markdown 报告 |
| `/agent/run/` | POST | 一键执行完整科研智能体流程 |

## 一键流程请求示例

```json
{
  "query": "科学文献研究智能体 从综述到实验设计",
  "sources": ["pubmed", "arxiv"]
}
```

## 研究空白雷达统计

请求示例：

```http
GET /api/statistics/gaps/?task_id=1
```

返回内容包含当前检索任务的真实记录数量、所属学科领域、同领域真实文献数量，以及研究热度、文献数量、创新性、可行性、应用价值、研究成熟度六个维度的当前值和同领域均值。

该接口必须传入真实检索完成后的 `task_id`。未传 `task_id` 或任务不存在时返回空统计，前端首页不会使用最近一次历史检索自动填充雷达图。

## 一键流程返回内容

```json
{
  "ok": true,
  "task": {},
  "analysis": {},
  "experiment": {},
  "drafts": [],
  "report": {}
}
```
