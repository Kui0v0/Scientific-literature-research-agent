import json
import sys
import warnings

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from .rag import _milvus_retrieve, rag_status_message


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        documents = _milvus_retrieve(
            payload.get("query", ""),
            payload.get("documents") or [],
            int(payload.get("limit") or 5),
        )
        json.dump(
            {
                "ok": True,
                "documents": documents,
                "status": rag_status_message(),
            },
            sys.stdout,
            ensure_ascii=True,
        )
    except Exception as exc:
        json.dump(
            {
                "ok": False,
                "documents": [],
                "error": f"{type(exc).__name__}: {exc}",
                "status": rag_status_message(),
            },
            sys.stdout,
            ensure_ascii=True,
        )


if __name__ == "__main__":
    main()
