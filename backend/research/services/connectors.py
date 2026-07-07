import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date


class RetrievalError(RuntimeError):
    pass


DEMO_CORPUS = [
    {
        "title": "Single-cell transcriptomics reveals tumor immune microenvironment remodeling",
        "authors": ["Chen L", "Wang J", "Li M"],
        "abstract": (
            "Single-cell RNA sequencing enables high-resolution characterization of immune "
            "cell states in tumors. Current studies reveal exhausted T cell subsets, myeloid "
            "heterogeneity and therapy-associated immune remodeling, but validation cohorts "
            "and standardized computational pipelines remain limited."
        ),
        "source": "Demo",
        "published_at": "2024-03-11",
        "doi": "10.1000/demo-sc-tumor-immune",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["single-cell sequencing", "tumor immunity", "T cell exhaustion", "immunotherapy"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
    {
        "title": "Graph neural networks for biomedical literature-based discovery",
        "authors": ["Zhao Y", "Sun Q"],
        "abstract": (
            "Biomedical literature-based discovery benefits from graph neural networks that "
            "combine entities, citations and semantic relations. A key gap is the lack of "
            "interpretable evaluation protocols for translating predictions into experiments."
        ),
        "source": "Demo",
        "published_at": "2023-09-18",
        "doi": "",
        "url": "https://arxiv.org/",
        "keywords": ["graph neural network", "literature discovery", "biomedical AI", "interpretability"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
    {
        "title": "Large language model agents for scientific hypothesis generation",
        "authors": ["Liu H", "Kumar A", "Smith R"],
        "abstract": (
            "Agent-based large language models can decompose scientific research workflows "
            "into retrieval, critique, hypothesis generation and protocol drafting. Existing "
            "systems still require stronger grounding, provenance tracking and human review."
        ),
        "source": "Demo",
        "published_at": "2025-01-22",
        "doi": "",
        "url": "https://arxiv.org/",
        "keywords": ["large language model", "agent", "hypothesis generation", "scientific workflow"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
    {
        "title": "Systematic review automation in precision medicine",
        "authors": ["Garcia P", "Miller T"],
        "abstract": (
            "Automation tools accelerate screening and evidence extraction in precision "
            "medicine reviews. However, inconsistent metadata and limited domain adaptation "
            "reduce reliability for emerging research topics."
        ),
        "source": "Demo",
        "published_at": "2022-06-05",
        "doi": "10.1000/demo-review-automation",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["systematic review", "precision medicine", "evidence extraction", "automation"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
    {
        "title": "Benchmarking retrieval augmented generation for academic writing",
        "authors": ["Yang Z", "Hu K"],
        "abstract": (
            "Retrieval augmented generation improves citation-aware academic writing, but "
            "faithfulness varies across domains. Future work should integrate source quality "
            "scoring, citation tracing and structured revision."
        ),
        "source": "Demo",
        "published_at": "2024-11-02",
        "doi": "",
        "url": "https://arxiv.org/",
        "keywords": ["retrieval augmented generation", "academic writing", "citation", "faithfulness"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
    {
        "title": "Multi-omics experiment design for immune response prediction",
        "authors": ["Tang X", "Huang Y", "Roberts C"],
        "abstract": (
            "Multi-omics designs combine transcriptomics, proteomics and clinical features "
            "to predict immunotherapy response. Small sample sizes, batch effects and weak "
            "external validation remain important bottlenecks."
        ),
        "source": "Demo",
        "published_at": "2023-12-16",
        "doi": "10.1000/demo-multiomics-immune",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["multi-omics", "immunotherapy", "response prediction", "experimental design"],
        "raw_metadata": {"provider": "demo", "is_demo": True},
    },
]


SOURCE_HANDLERS = {
    "pubmed": ("PubMed", lambda query, limit: search_pubmed(query, limit)),
    "arxiv": ("arXiv", lambda query, limit: search_arxiv(query, limit)),
    "crossref": ("Crossref", lambda query, limit: search_crossref(query, limit)),
}


def search_literature(query, sources=None, limit=10, allow_demo=False):
    selected = sources or ["pubmed", "arxiv", "crossref"]
    source_groups = []
    errors = []
    per_source_limit = max(1, min(int(limit), 20))

    for source in selected:
        handler = SOURCE_HANDLERS.get(source)
        if not handler:
            errors.append(f"{source}: unsupported source")
            continue
        source_name, search_func = handler
        try:
            source_records = search_func(query, per_source_limit)
            real_records = [record for record in source_records if is_valid_real_record(record)]
            if real_records:
                source_groups.append(real_records)
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")

    records = deduplicate(_round_robin(source_groups))
    if records:
        return records[: int(limit)]

    if allow_demo:
        return demo_records(query, limit)

    reason = "；".join(errors) if errors else "所有已选择数据源均无匹配文献"
    raise RetrievalError(
        "真实学术数据库检索未返回有效结果。请确认网络可访问 PubMed/arXiv/Crossref，"
        f"或尝试使用英文关键词。详情：{reason}"
    )


def search_pubmed(query, limit=10):
    params = _ncbi_params(
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(limit),
            "sort": "relevance",
        }
    )
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    payload = json.loads(_get(search_url))
    ids = payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    fetch_params = _ncbi_params(
        {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
        }
    )
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(fetch_params)
    root = ET.fromstring(_get(fetch_url))
    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//PMID"))
        title = _text(article.find(".//ArticleTitle"))
        abstract = " ".join(_text(node) for node in article.findall(".//AbstractText") if _text(node))
        authors = []
        for author in article.findall(".//Author"):
            last = _text(author.find("LastName"))
            fore = _text(author.find("ForeName"))
            initials = _text(author.find("Initials"))
            name = " ".join(part for part in [fore, last] if part) or " ".join(part for part in [last, initials] if part)
            if name:
                authors.append(name)
        doi = ""
        for node in article.findall(".//ArticleId"):
            if node.attrib.get("IdType") == "doi":
                doi = _text(node)
        pub_date = _parse_pubmed_date(article)
        keywords = [_text(node) for node in article.findall(".//Keyword") if _text(node)]
        records.append(
            normalize_record(
                {
                    "title": title or "Untitled PubMed article",
                    "authors": authors,
                    "abstract": abstract,
                    "source": "PubMed",
                    "published_at": pub_date,
                    "doi": doi,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                    "keywords": keywords,
                    "raw_metadata": {"provider": "pubmed", "pmid": pmid, "source_id": pmid},
                }
            )
        )
    return records


def search_arxiv(query, limit=10):
    params = urllib.parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(limit),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    root = ET.fromstring(_get(url))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    records = []
    for entry in root.findall("atom:entry", ns):
        arxiv_url = _text(entry.find("atom:id", ns))
        arxiv_id = arxiv_url.rstrip("/").split("/")[-1] if arxiv_url else ""
        authors = [_text(node.find("atom:name", ns)) for node in entry.findall("atom:author", ns)]
        categories = [node.attrib.get("term", "") for node in entry.findall("atom:category", ns)]
        doi = _text(entry.find("arxiv:doi", {"arxiv": "http://arxiv.org/schemas/atom"}))
        records.append(
            normalize_record(
                {
                    "title": _text(entry.find("atom:title", ns)),
                    "authors": authors,
                    "abstract": _text(entry.find("atom:summary", ns)),
                    "source": "arXiv",
                    "published_at": (_text(entry.find("atom:published", ns)) or "")[:10],
                    "doi": doi,
                    "url": arxiv_url,
                    "keywords": categories,
                    "raw_metadata": {"provider": "arxiv", "arxiv_id": arxiv_id, "source_id": arxiv_id},
                }
            )
        )
    return records


def search_crossref(query, limit=10):
    params = {
        "query": query,
        "rows": str(limit),
        "sort": "score",
        "order": "desc",
    }
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    payload = json.loads(_get(url))
    items = payload.get("message", {}).get("items", [])
    records = []
    for item in items:
        doi = item.get("DOI", "")
        title = _first(item.get("title")) or "Untitled Crossref work"
        abstract = _clean_markup(item.get("abstract", ""))
        authors = [
            " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part)
            for author in item.get("author", [])
        ]
        keywords = item.get("subject") or item.get("container-title") or []
        records.append(
            normalize_record(
                {
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "source": "Crossref",
                    "published_at": _crossref_date(item),
                    "doi": doi,
                    "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                    "keywords": keywords[:8],
                    "raw_metadata": {
                        "provider": "crossref",
                        "doi": doi,
                        "source_id": doi,
                        "publisher": item.get("publisher", ""),
                        "container_title": _first(item.get("container-title")),
                    },
                }
            )
        )
    return records


def demo_records(query, limit=10):
    tokens = [token.lower() for token in re.findall(r"[A-Za-z\u4e00-\u9fa5]+", query)]
    scored = []
    for record in DEMO_CORPUS:
        haystack = " ".join(
            [record["title"], record["abstract"], " ".join(record.get("keywords", []))]
        ).lower()
        score = sum(1 for token in tokens if token in haystack)
        scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [normalize_record(record) for _, record in scored[: int(limit)]]


def deduplicate(records):
    seen = set()
    output = []
    for record in records:
        metadata = record.get("raw_metadata", {})
        key = (
            record.get("doi")
            or metadata.get("source_id")
            or record.get("url")
            or normalize_title(record.get("title", ""))
        ).lower()
        if key and key not in seen:
            output.append(record)
            seen.add(key)
    return output


def _round_robin(groups):
    output = []
    max_len = max([len(group) for group in groups] or [0])
    for index in range(max_len):
        for group in groups:
            if index < len(group):
                output.append(group[index])
    return output


def is_valid_real_record(record):
    metadata = record.get("raw_metadata", {})
    if metadata.get("is_demo"):
        return False
    if not record.get("title") or not record.get("url"):
        return False
    if record.get("source") == "PubMed":
        return bool(metadata.get("pmid"))
    if record.get("source") == "arXiv":
        return bool(metadata.get("arxiv_id"))
    if record.get("source") == "Crossref":
        return bool(record.get("doi") or metadata.get("source_id"))
    return False


def normalize_record(record):
    item = dict(record)
    item["title"] = _clean_markup(item.get("title") or "Untitled")
    item["abstract"] = _clean_markup(item.get("abstract") or "")
    item["authors"] = [name.strip() for name in item.get("authors", []) if name and name.strip()]
    item["keywords"] = [kw.strip() for kw in item.get("keywords", []) if kw and kw.strip()]
    item["published_at"] = _safe_date(item.get("published_at"))
    item.setdefault("doi", "")
    item.setdefault("url", "")
    item.setdefault("raw_metadata", {})
    return item


def normalize_title(title):
    return re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "", title.lower())


def _ncbi_params(params):
    values = dict(params)
    tool = os.getenv("NCBI_TOOL", "literature_agent_demo").strip()
    email = os.getenv("NCBI_EMAIL", "").strip()
    api_key = os.getenv("NCBI_API_KEY", "").strip()
    if tool:
        values["tool"] = tool
    if email:
        values["email"] = email
    if api_key:
        values["api_key"] = api_key
    return values


def _get(url):
    timeout = int(os.getenv("EXTERNAL_REQUEST_TIMEOUT", "15"))
    user_agent = os.getenv("HTTP_USER_AGENT", "literature-agent-demo/1.0")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    context = _ssl_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read().decode("utf-8", errors="ignore")


def _ssl_context():
    cert_file = os.getenv("SSL_CERT_FILE", "").strip()
    if cert_file:
        return ssl.create_default_context(cafile=cert_file)
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _text(node):
    if node is None or node.text is None:
        return ""
    return " ".join(node.itertext()).strip()


def _first(values):
    if isinstance(values, list) and values:
        return values[0]
    if isinstance(values, str):
        return values
    return ""


def _clean_markup(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_pubmed_date(article):
    year = _text(article.find(".//PubDate/Year"))
    month = _text(article.find(".//PubDate/Month")) or "01"
    day = _text(article.find(".//PubDate/Day")) or "01"
    month_map = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    month = month_map.get(month[:3], month)
    if not year:
        return None
    return _safe_date(f"{year}-{month}-{day}")


def _crossref_date(item):
    date_parts = (
        item.get("published-print", {}).get("date-parts")
        or item.get("published-online", {}).get("date-parts")
        or item.get("created", {}).get("date-parts")
        or []
    )
    if not date_parts or not date_parts[0]:
        return None
    parts = list(date_parts[0]) + [1, 1]
    return _safe_date(f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}")


def _safe_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        parts = str(value)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None
