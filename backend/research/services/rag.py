import hashlib
import json
import math
import os
import urllib.request


_RERANKER = None


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
        return []

    evidence = _finalize_evidence(_milvus_retrieve(query, documents, limit), limit)
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
        return "真实文献上下文约束（Milvus/embedding 暂未返回向量证据）"
    return "Milvus RAG 证据约束"


def _milvus_retrieve(query, documents, limit):
    if os.getenv("USE_MILVUS", "1") != "1":
        return []
    try:
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

        texts = [_document_text(doc) for doc in documents]
        vectors = _embed_texts([query] + texts)
        if len(vectors) != len(documents) + 1:
            return []
        query_vector = vectors[0]
        document_vectors = vectors[1:]
        dim = len(query_vector)
        collection_name = os.getenv("MILVUS_COLLECTION", "literature_rag_chunks")
        connect_kwargs = {
            "alias": "default",
            "host": os.getenv("MILVUS_HOST", "127.0.0.1"),
            "port": os.getenv("MILVUS_PORT", "19530"),
            "secure": os.getenv("MILVUS_SECURE", "0") == "1",
        }
        if os.getenv("MILVUS_USER"):
            connect_kwargs["user"] = os.getenv("MILVUS_USER")
        if os.getenv("MILVUS_PASSWORD"):
            connect_kwargs["password"] = os.getenv("MILVUS_PASSWORD")
        connections.connect(**connect_kwargs)
        collection_name = _collection_name_for_dimension(collection_name, dim, Collection, utility)
        if not utility.has_collection(collection_name):
            fields = [
                FieldSchema(name="pk", dtype=DataType.VARCHAR, max_length=96, is_primary=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="payload", dtype=DataType.JSON),
            ]
            schema = CollectionSchema(fields, description="Literature RAG evidence chunks")
            collection = Collection(collection_name, schema=schema)
            collection.create_index("vector", _milvus_index_params())
        else:
            collection = Collection(collection_name)
            if not collection.indexes:
                collection.create_index("vector", _milvus_index_params())

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
        if hasattr(collection, "upsert"):
            collection.upsert(rows)
        else:
            collection.insert(rows)
        collection.flush()
        collection.load()

        hits = collection.search(
            data=[query_vector],
            anns_field="vector",
            param=_milvus_search_params(),
            limit=min(_candidate_limit(limit), len(rows)),
            expr=_pk_filter_expr(row["pk"] for row in rows),
            output_fields=["payload"],
        )
        output = []
        for hit in hits[0]:
            payload = hit.entity.get("payload")
            if payload:
                doc = dict(payload)
                doc["vector_score"] = float(getattr(hit, "score", getattr(hit, "distance", 0.0)) or 0.0)
                output.append(doc)
        return _rerank_evidence(query, output, limit)
    except Exception:
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
    except Exception:
        if len(texts) == 1:
            return []
        vectors = []
        for text in texts:
            single = _embed_texts([text])
            if not single:
                return []
            vectors.extend(single)
        return vectors

    data = result.get("data") or []
    data = sorted(data, key=lambda item: item.get("index", 0))
    vectors = [_normalize_vector(item.get("embedding") or []) for item in data]
    return [vector for vector in vectors if vector]


def _normalize_vector(vector):
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _collection_name_for_dimension(collection_name, dim, Collection, utility):
    if not utility.has_collection(collection_name):
        return collection_name
    collection = Collection(collection_name)
    existing_dim = _collection_vector_dim(collection)
    if not existing_dim or existing_dim == dim:
        return collection_name
    return f"{collection_name}_{dim}"


def _collection_vector_dim(collection):
    for field in collection.schema.fields:
        if field.name != "vector":
            continue
        params = getattr(field, "params", {}) or {}
        try:
            return int(params.get("dim") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _milvus_metric_type():
    return os.getenv("MILVUS_METRIC_TYPE", "IP").upper()


def _milvus_index_params():
    return {
        "metric_type": _milvus_metric_type(),
        "index_type": os.getenv("MILVUS_INDEX_TYPE", "FLAT").upper(),
        "params": {},
    }


def _milvus_search_params():
    return {
        "metric_type": _milvus_metric_type(),
        "params": {},
    }


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
        item["retrieval"] = "文献上下文（Milvus 或 embedding 暂未返回向量证据）"
        item["retrieval_fallback"] = True
        output.append(item)
    return _finalize_evidence(output, limit)


def _retrieval_line(doc):
    parts = [f"召回：{doc.get('retrieval') or '文献上下文'}"]
    if doc.get("vector_score") is not None:
        parts.append(f"向量得分：{float(doc.get('vector_score')):.4f}")
    if doc.get("rerank_score") is not None:
        parts.append(f"精排得分：{float(doc.get('rerank_score')):.4f}")
    return "；".join(parts)
