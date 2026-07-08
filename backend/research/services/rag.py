import base64
import hashlib
import json
import math
import os
import subprocess
import socket
import sys
import urllib.request
from pathlib import Path


_RERANKER = None
_LAST_RAG_STATUS = "尚未执行 Milvus 向量召回"


def env_int(name, default, minimum=None, maximum=None):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def retrieve_evidence(query, records, limit=None):
    limit = env_int("RAG_TOP_K", 5, minimum=1, maximum=20) if limit is None else max(1, int(limit))
    documents = [_document_from_record(record, index) for index, record in enumerate(records or [], start=1)]
    documents = [doc for doc in documents if doc["title"] or doc["abstract"]]
    if not documents:
        _set_rag_status("没有可用于向量召回的文献标题或摘要")
        return []

    evidence = _finalize_evidence(_safe_milvus_retrieve(query, documents, limit), limit)
    if evidence:
        return evidence
    if os.getenv("RAG_RECORD_CONTEXT_FALLBACK", "1") != "1":
        return []
    return _record_context_evidence(documents, limit)


def format_evidence_pack(documents, max_abstract_chars=None):
    if max_abstract_chars is None:
        max_abstract_chars = env_int("RAG_ABSTRACT_CHARS", 480, minimum=160, maximum=1200)
    lines = []
    for doc in documents:
        identifier = doc.get("identifier") or doc.get("url") or "无编号"
        keywords = "、".join(doc.get("keywords", [])[:8]) or "无关键词"
        abstract = (doc.get("abstract") or "无摘要").replace("\n", " ")[:max_abstract_chars]
        lines.append(
            "\n".join(
                [
                    f"[{doc['ref']}] {doc['title']}",
                    f"来源：{doc.get('source') or 'Unknown'}；日期：{doc.get('published_at') or '未知'}；编号：{identifier}",
                    _retrieval_line(doc),
                    f"关键词：{keywords}",
                    f"摘要：{abstract}",
                    f"链接：{doc.get('url') or '无'}",
                ]
            )
        )
    return "\n\n".join(lines)


def evidence_reference_note(documents):
    return "；".join(
        f"[{doc['ref']}] {doc['title']}（{doc.get('source') or 'Unknown'}）" for doc in documents
    )


def evidence_generation_label(documents):
    if documents and all(doc.get("retrieval_fallback") for doc in documents):
        return f"真实文献上下文约束（{rag_status_message()}）"
    return "Milvus RAG 证据约束"


def rag_status_message():
    return _LAST_RAG_STATUS


def rag_config_status():
    host = os.getenv("MILVUS_HOST", "127.0.0.1")
    port = os.getenv("MILVUS_PORT", "19530")
    enabled = os.getenv("USE_MILVUS", "1") == "1"
    return {
        "use_milvus": enabled,
        "host": host,
        "port": port,
        "collection": os.getenv("MILVUS_COLLECTION", "literature_rag_chunks"),
        "reachable": _tcp_available(host, port) if enabled else False,
        "embedding_model": _embedding_model(),
        "embedding_base_url": _embedding_base_url(),
        "last_status": rag_status_message(),
    }


def _safe_milvus_retrieve(query, documents, limit):
    if os.getenv("RAG_MILVUS_ISOLATE", "1") != "1":
        return _milvus_retrieve(query, documents, limit)
    return _isolated_milvus_retrieve(query, documents, limit)


def _isolated_milvus_retrieve(query, documents, limit):
    timeout = env_int("RAG_MILVUS_TIMEOUT", 35, minimum=5, maximum=180)
    backend_dir = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONWARNINGS"] = "ignore"
    payload = json.dumps(
        {
            "query": query,
            "documents": documents,
            "limit": limit,
        },
        ensure_ascii=False,
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "research.services.rag_worker"],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            cwd=str(backend_dir),
            env=env,
        )
    except subprocess.TimeoutExpired:
        _set_rag_status(f"Milvus 子进程超过 {timeout} 秒未返回，已使用真实文献上下文兜底。")
        return []
    except Exception as exc:
        _set_rag_status(f"Milvus 子进程启动失败：{type(exc).__name__}: {_safe_error_detail(exc)}")
        return []

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        detail = _safe_error_detail(stderr or stdout or f"exit code {completed.returncode}")
        _set_rag_status(f"Milvus 子进程异常退出：{detail}")
        return []
    try:
        result = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        detail = _safe_error_detail(stderr or stdout or "empty response")
        _set_rag_status(f"Milvus 子进程返回内容无法解析：{detail}")
        return []
    if result.get("status"):
        _set_rag_status(result.get("status"))
    if result.get("ok") is False:
        _set_rag_status(result.get("status") or result.get("error") or "Milvus 子进程召回失败")
        return []
    return result.get("documents") or []


def _milvus_retrieve(query, documents, limit):
    if os.getenv("USE_MILVUS", "1") != "1":
        _set_rag_status("USE_MILVUS 未启用")
        return []
    try:
        texts = [_document_text(doc) for doc in documents]
        vectors = _embed_texts([query] + texts)
        if len(vectors) != len(documents) + 1:
            _set_rag_status(f"embedding 返回数量不匹配：期望 {len(documents) + 1} 条，实际 {len(vectors)} 条")
            return []
        query_vector = vectors[0]
        document_vectors = vectors[1:]
        dim = len(query_vector)
        collection_name = os.getenv("MILVUS_COLLECTION", "literature_rag_chunks")
        rpc_timeout = env_int("MILVUS_RPC_TIMEOUT", 12, minimum=2, maximum=60)
        collection_name = _collection_name_for_dimension_rest(collection_name, dim, rpc_timeout)
        if not _milvus_rest_has_collection(collection_name, rpc_timeout):
            _milvus_rest_create_collection(collection_name, dim, rpc_timeout)

        rows = [
            {
                "pk": _stable_pk(doc),
                "vector": vector,
                "payload": {
                    **doc,
                    "embedding_model": _embedding_model(),
                    "retrieval": "Milvus vector",
                    "milvus_collection": collection_name,
                },
            }
            for doc, vector in zip(documents, document_vectors)
        ]
        _milvus_rest_request(
            "entities/upsert",
            {"collectionName": collection_name, "data": rows},
            timeout=rpc_timeout,
        )
        _milvus_rest_request(
            "collections/load",
            {"collectionName": collection_name},
            timeout=rpc_timeout,
        )

        result = _milvus_rest_request(
            "entities/search",
            {
                "collectionName": collection_name,
                "data": [query_vector],
                "annsField": "vector",
                "searchParams": _milvus_rest_search_params(),
                "limit": min(_candidate_limit(limit), len(rows)),
                "filter": _pk_filter_expr(row["pk"] for row in rows),
                "outputFields": ["payload"],
            },
            timeout=rpc_timeout,
        )
        hits = result.get("data") or []
        output = []
        for hit in hits:
            entity = hit.get("entity") or hit
            payload = _decode_milvus_payload(entity.get("payload"))
            if payload:
                doc = dict(payload)
                doc["vector_score"] = float(hit.get("score", hit.get("distance", 0.0)) or 0.0)
                output.append(doc)
        if output:
            _set_rag_status(f"Milvus 向量召回成功：{len(output)} 条，集合 {collection_name}")
        else:
            _set_rag_status(f"Milvus 查询成功，但当前文献集合没有命中结果：{collection_name}")
        return _rerank_evidence(query, output, limit)
    except Exception as exc:
        _set_rag_status(f"Milvus 向量召回失败：{type(exc).__name__}: {_safe_error_detail(exc)}")
        return []


def _document_from_record(record, index):
    def get(name, default=""):
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    raw_metadata = get("raw_metadata", {}) or {}
    doi = get("doi", "") or raw_metadata.get("doi", "")
    pmid = raw_metadata.get("pmid", "")
    arxiv_id = raw_metadata.get("arxiv_id", "")
    identifier = doi or (f"PMID:{pmid}" if pmid else "") or (f"arXiv:{arxiv_id}" if arxiv_id else "")
    published_at = get("published_at", "")
    if published_at:
        published_at = str(published_at)[:10]

    return {
        "ref": f"R{index}",
        "record_id": str(get("id", "") or ""),
        "title": str(get("title", "") or ""),
        "authors": list(get("authors", []) or []),
        "abstract": str(get("abstract", "") or ""),
        "source": str(get("source", "") or ""),
        "published_at": published_at,
        "doi": str(doi or ""),
        "url": str(get("url", "") or ""),
        "keywords": [str(keyword) for keyword in (get("keywords", []) or []) if keyword],
        "identifier": identifier,
    }


def _document_text(doc):
    return " ".join(
        [
            doc.get("title", ""),
            doc.get("abstract", ""),
            " ".join(doc.get("keywords", [])),
            doc.get("source", ""),
            doc.get("identifier", ""),
        ]
    )


def _embedding_model():
    return (
        os.getenv("RAG_EMBEDDING_MODEL")
        or os.getenv("OLLAMA_EMBED_MODEL")
        or os.getenv("OPENAI_EMBEDDING_MODEL")
        or "embeddinggemma"
    )


def _embedding_base_url():
    return (
        os.getenv("RAG_EMBEDDING_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "http://127.0.0.1:11434/v1"
    ).rstrip("/")


def _embedding_api_key():
    return (
        os.getenv("RAG_EMBEDDING_API_KEY")
        or os.getenv("OLLAMA_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or "ollama"
    )


def _embedding_url():
    base_url = _embedding_base_url()
    return base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"


def _milvus_uri():
    scheme = "https" if os.getenv("MILVUS_SECURE", "0") == "1" else "http"
    host = os.getenv("MILVUS_HOST", "127.0.0.1")
    port = os.getenv("MILVUS_PORT", "19530")
    return f"{scheme}://{host}:{port}"


def _milvus_rest_request(endpoint, body, timeout=None):
    url = f"{_milvus_uri().rstrip('/')}/v2/vectordb/{endpoint.lstrip('/')}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = os.getenv("MILVUS_TOKEN", "").strip()
    user = os.getenv("MILVUS_USER", "").strip()
    password = os.getenv("MILVUS_PASSWORD", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif user and password:
        headers["Authorization"] = f"Bearer {user}:{password}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body or {}, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout or env_int("MILVUS_RPC_TIMEOUT", 12, minimum=2, maximum=60)) as response:
        result = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    if int(result.get("code", 0) or 0) != 0:
        raise RuntimeError(result.get("message") or result.get("error") or f"Milvus REST {endpoint} failed")
    return result


def _milvus_rest_has_collection(collection_name, timeout):
    result = _milvus_rest_request("collections/has", {"collectionName": collection_name}, timeout=timeout)
    data = result.get("data")
    if isinstance(data, dict):
        return bool(data.get("has"))
    return bool(data)


def _milvus_rest_describe_collection(collection_name, timeout):
    return _milvus_rest_request("collections/describe", {"collectionName": collection_name}, timeout=timeout).get("data") or {}


def _milvus_rest_create_collection(collection_name, dim, timeout):
    metric_type = _milvus_metric_type()
    index_type = os.getenv("MILVUS_INDEX_TYPE", "FLAT").upper()
    _milvus_rest_request(
        "collections/create",
        {
            "collectionName": collection_name,
            "schema": {
                "autoId": False,
                "enableDynamicField": False,
                "description": "Literature RAG evidence chunks",
                "fields": [
                    {
                        "fieldName": "pk",
                        "dataType": "VarChar",
                        "isPrimary": True,
                        "elementTypeParams": {"max_length": "96"},
                    },
                    {
                        "fieldName": "vector",
                        "dataType": "FloatVector",
                        "elementTypeParams": {"dim": str(dim)},
                    },
                    {"fieldName": "payload", "dataType": "JSON"},
                ],
            },
            "indexParams": [
                {
                    "fieldName": "vector",
                    "indexName": "vector",
                    "metricType": metric_type,
                    "indexType": index_type,
                    "params": {},
                }
            ],
        },
        timeout=timeout,
    )


def _milvus_rest_search_params():
    return {
        "metricType": _milvus_metric_type(),
        "params": {},
    }


def _decode_milvus_payload(payload):
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="ignore")
    if not isinstance(payload, str):
        return {}
    for candidate in (payload, _try_base64_decode(payload)):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def _try_base64_decode(value):
    try:
        return base64.b64decode(value).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _embed_texts(texts):
    texts = [str(text or "") for text in texts]
    if not texts:
        return []
    payload = json.dumps(
        {
            "model": _embedding_model(),
            "input": texts,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": os.getenv("RAG_EMBEDDING_USER_AGENT", "literature-agent-rag/1.0"),
    }
    if _embedding_api_key():
        headers["Authorization"] = f"Bearer {_embedding_api_key()}"
    request = urllib.request.Request(_embedding_url(), data=payload, headers=headers, method="POST")
    try:
        timeout = env_int("RAG_EMBEDDING_TIMEOUT", 30, minimum=3, maximum=180)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception as exc:
        detail = _safe_error_detail(exc)
        if len(texts) == 1:
            _set_rag_status(f"embedding 请求失败：{detail}")
            return []
        vectors = []
        for text in texts:
            single = _embed_texts([text])
            if not single:
                _set_rag_status(f"embedding 请求失败：{detail}")
                return []
            vectors.extend(single)
        return vectors

    data = result.get("data") or []
    data = sorted(data, key=lambda item: item.get("index", 0))
    vectors = [_normalize_vector(item.get("embedding") or []) for item in data]
    vectors = [vector for vector in vectors if vector]
    if len(vectors) != len(texts) and len(texts) > 1:
        output = []
        for text in texts:
            single = _embed_texts([text])
            if not single:
                _set_rag_status(
                    f"embedding 批量返回数量不匹配，且单条重试失败：期望 {len(texts)} 条，实际 {len(vectors)} 条"
                )
                return []
            output.extend(single)
        return output
    return vectors


def _normalize_vector(vector):
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _collection_name_for_dimension_rest(collection_name, dim, timeout):
    if not _milvus_rest_has_collection(collection_name, timeout):
        return collection_name
    existing_dim = _collection_vector_dim_from_description(
        _milvus_rest_describe_collection(collection_name, timeout)
    )
    if not existing_dim or existing_dim == dim:
        return collection_name
    return f"{collection_name}_{dim}"


def _collection_vector_dim_from_description(description):
    for field in (description or {}).get("fields", []):
        if (field.get("name") or field.get("fieldName")) != "vector":
            continue
        params = field.get("params") or field.get("elementTypeParams") or {}
        if isinstance(params, list):
            params = {
                str(item.get("key")): item.get("value")
                for item in params
                if isinstance(item, dict) and item.get("key") is not None
            }
        try:
            return int(params.get("dim") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _milvus_metric_type():
    return os.getenv("MILVUS_METRIC_TYPE", "IP").upper()


def _candidate_limit(limit):
    configured = env_int("RAG_VECTOR_TOP_K", max(8, int(limit)), minimum=1, maximum=50)
    return max(int(limit), configured)


def _rerank_evidence(query, documents, limit):
    reranker = _load_reranker()
    if not reranker or not documents:
        return documents[:limit]
    tokenizer, model, device, torch = reranker
    pairs = [[query, _document_text(doc)] for doc in documents]
    try:
        with torch.no_grad():
            inputs = tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=env_int("RAG_RERANK_MAX_LENGTH", 512, minimum=128, maximum=2048),
                return_tensors="pt",
            ).to(device)
            outputs = model(**inputs)
            scores = outputs.logits.view(-1).detach().cpu().float().tolist()
    except Exception:
        return documents[:limit]

    reranked = []
    for doc, score in zip(documents, scores):
        item = dict(doc)
        item["rerank_score"] = float(score)
        item["rerank_reason"] = "BGE reranker"
        reranked.append(item)
    reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
    return reranked[:limit]


def _load_reranker():
    global _RERANKER
    if os.getenv("RAG_RERANK_ENABLED", "0") != "1":
        return None
    if os.getenv("RAG_RERANK_ALLOW_TORCH", "0") != "1":
        _RERANKER = False
        return None
    if _RERANKER is False:
        return None
    if _RERANKER is not None:
        return _RERANKER
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_path = os.getenv("RAG_RERANK_MODEL_PATH") or os.getenv("BGE_RERANK_MODEL_PATH")
        local_only = os.getenv("RAG_RERANK_LOCAL_ONLY", "1") == "1"
        if not model_path and local_only:
            _RERANKER = False
            return None
        model_path = model_path or "BAAI/bge-reranker-v2-m3"
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=local_only)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_path,
            local_files_only=local_only,
            low_cpu_mem_usage=True,
        )
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
        _RERANKER = (tokenizer, model, device, torch)
        return _RERANKER
    except Exception:
        _RERANKER = False
        return None


def _stable_pk(doc):
    stable_identity = {
        "record_id": doc.get("record_id") or "",
        "identifier": doc.get("identifier") or "",
        "doi": doc.get("doi") or "",
        "url": doc.get("url") or "",
        "title": doc.get("title") or "",
        "source": doc.get("source") or "",
        "published_at": doc.get("published_at") or "",
    }
    payload = json.dumps(stable_identity, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _pk_filter_expr(pks):
    quoted = ", ".join(f'"{pk}"' for pk in pks)
    return f"pk in [{quoted}]"


def _finalize_evidence(documents, limit):
    output = []
    for index, doc in enumerate((documents or [])[:limit], start=1):
        item = dict(doc)
        item["ref"] = f"R{index}"
        output.append(item)
    return output


def _record_context_evidence(documents, limit):
    output = []
    for doc in documents[:limit]:
        item = dict(doc)
        item["retrieval"] = f"文献上下文兜底（{rag_status_message()}）"
        item["retrieval_fallback"] = True
        output.append(item)
    return _finalize_evidence(output, limit)


def _set_rag_status(message):
    global _LAST_RAG_STATUS
    _LAST_RAG_STATUS = str(message or "").strip()[:500] or "Milvus 向量召回状态未知"


def _tcp_available(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=1.5):
            return True
    except Exception:
        return False


def _safe_error_detail(exc):
    return str(exc).replace("\n", " ")[:240]


def _retrieval_line(doc):
    parts = [f"召回：{doc.get('retrieval') or '文献上下文'}"]
    if doc.get("vector_score") is not None:
        parts.append(f"向量得分：{float(doc.get('vector_score')):.4f}")
    if doc.get("rerank_score") is not None:
        parts.append(f"精排得分：{float(doc.get('rerank_score')):.4f}")
    return "；".join(parts)
