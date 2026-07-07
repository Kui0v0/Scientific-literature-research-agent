import json
import os
import re
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


_LAST_LLM_STATUS = ""


def llm_enabled():
    return os.getenv("USE_LLM", "0") == "1" and bool(_api_key())


def llm_status_message():
    if os.getenv("USE_LLM", "0") != "1":
        return "USE_LLM 未设置为 1，后端未启用大模型。"
    if not _api_key():
        return "未读取到当前 LLM_PROVIDER 对应的 API Key，请检查 backend/.env 并重启后端。"
    return _LAST_LLM_STATUS or "大模型已配置，但本次调用未返回有效内容。"


def llm_config_status():
    return {
        "enabled": llm_enabled(),
        "provider": _provider_label() if _api_key() else "",
        "model": _model_name() if _api_key() else "",
        "base_url": _base_url_status() if _api_key() else "",
        "has_api_key": bool(_api_key()),
        "use_llm": os.getenv("USE_LLM", "0"),
        "status": llm_status_message(),
    }


def generation_notice(evidence_count=0):
    provider = _provider_label()
    model = _model_name()
    return f"> 生成方式：{provider} + Milvus RAG 证据约束；模型：{model}；证据文献：{evidence_count} 条。\n\n"


def fallback_notice(reason=None):
    reason = reason or _fallback_reason_from_status()
    hint = "请稍后重试，或调低生成字数、增加 `LLM_REQUEST_TIMEOUT`。"
    if os.getenv("USE_LLM", "0") != "1" or not _api_key():
        hint = "配置 `USE_LLM=1` 和当前大模型 API Key 后重新生成可启用大模型。"
    return f"> 生成方式：规则模板兜底；原因：{reason}。{hint}\n\n"


def is_llm_rag_text(text):
    value = str(text or "")
    if "生成方式：规则模板兜底" in value:
        return False
    return bool(re.search(r"(DeepSeek|OpenAI|GPT|大模型)\s*\+\s*(?:Milvus\s+)?RAG", value)) or bool(re.search(r"\[R\d+\]", value))


def normalize_generation_notice(text):
    value = str(text or "")
    stale_reasons = [
        "生成方式：规则模板兜底；原因：DeepSeek 调用成功。。",
        "生成方式：规则模板兜底；原因：DeepSeek 调用成功。",
        "生成方式：规则模板兜底；原因：OpenAI 调用成功。。",
        "生成方式：规则模板兜底；原因：OpenAI 调用成功。",
        "生成方式：规则模板兜底；原因：GPT 调用成功。。",
        "生成方式：规则模板兜底；原因：GPT 调用成功。",
    ]
    replacement = "生成方式：规则模板兜底；原因：大模型已返回内容，但内容为空、被截断或未通过当前模块的结构校验，已使用规则模板保证页面可用。"
    for reason in stale_reasons:
        value = value.replace(reason, replacement)
    return keep_first_generation_notice(value)


def strip_generation_metadata(text):
    value = str(text or "")
    lines = []
    for line in value.splitlines():
        if _is_generation_notice_line(line):
            continue
        lines.append(_remove_inline_generation_notice(line))
    return "\n".join(lines).strip()


def keep_first_generation_notice(text):
    value = str(text or "")
    lines = []
    seen_notice = False
    for line in value.splitlines():
        if _is_generation_notice_line(line):
            if not seen_notice:
                lines.append(line)
                seen_notice = True
            continue
        lines.append(_remove_inline_generation_notice(line))
    return "\n".join(lines).strip()


def set_llm_status(message):
    global _LAST_LLM_STATUS
    _LAST_LLM_STATUS = str(message or "")


def chat_completion(messages, temperature=0.2, max_tokens=None, response_format=None):
    global _LAST_LLM_STATUS
    if not llm_enabled():
        _LAST_LLM_STATUS = llm_status_message()
        return ""

    payload = {
        "model": _model_name(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": int(max_tokens or os.getenv("LLM_MAX_TOKENS", "1600")),
    }
    if response_format:
        payload["response_format"] = response_format
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _chat_url(),
        data=data,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": os.getenv("LLM_ACCEPT_LANGUAGE", "zh-CN,zh;q=0.9,en;q=0.8"),
            "User-Agent": os.getenv(
                "LLM_HTTP_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            ),
        },
        method="POST",
    )
    try:
        timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "60"))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as exc:
        detail = _sanitize_error_detail(exc.read().decode("utf-8", errors="ignore"))
        _LAST_LLM_STATUS = f"{_provider_label()} API 返回 HTTP {exc.code}：{detail}"
        raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        _LAST_LLM_STATUS = f"{_provider_label()} 请求失败：{_sanitize_error_detail(str(exc))}"
        raise LLMError(_LAST_LLM_STATUS) from exc

    choices = result.get("choices") or []
    if not choices:
        _LAST_LLM_STATUS = f"{_provider_label()} API 响应中没有 choices 内容。"
        return ""
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    _LAST_LLM_STATUS = f"{_provider_label()} 调用成功。" if content else f"{_provider_label()} API 返回空文本。"
    return content


def chat_json(messages, temperature=0.1, max_tokens=None):
    global _LAST_LLM_STATUS
    use_json_mode = os.getenv("LLM_USE_JSON_MODE", "0") == "1"
    content = chat_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"} if use_json_mode else None,
    )
    if not content:
        return {}
    payload = _parse_json_object(content)
    if payload:
        return payload

    _LAST_LLM_STATUS = f"{_provider_label()} 返回内容不是合法 JSON，正在尝试自动修正。"
    repaired = chat_completion(
        messages
        + [
            {"role": "assistant", "content": content[:3500]},
            {
                "role": "user",
                "content": "上一条内容无法被系统解析为合法 JSON。请只输出一个合法 JSON 对象，不要 Markdown、不要解释、不要尾逗号。",
            },
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    payload = _parse_json_object(repaired)
    if payload:
        return payload
    _LAST_LLM_STATUS = f"{_provider_label()} 返回内容不是合法 JSON，自动修正后仍无法解析。"
    return {}


def _api_key():
    provider = _selected_provider()
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", "")
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "")
    return ""


def _model_name():
    provider = _selected_provider()
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-5.5")
    return ""


def _base_url():
    provider = _selected_provider()
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if provider == "openai":
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return ""


def _base_url_status():
    provider = _selected_provider()
    base_url = _base_url()
    official_defaults = {
        "deepseek": "https://api.deepseek.com",
        "openai": "https://api.openai.com/v1",
    }
    if not base_url:
        return ""
    return "official" if base_url == official_defaults.get(provider) else "custom-configured"


def _provider_label():
    provider = _selected_provider()
    if provider == "deepseek":
        return "DeepSeek"
    if provider == "openai":
        return os.getenv("LLM_PROVIDER_NAME", "GPT").strip() or "GPT"
    return "大模型"


def _selected_provider():
    requested = os.getenv("LLM_PROVIDER", "").strip().lower().replace("-", "_")
    if requested in {"openai", "gpt", "openai_compatible", "openai_compat"}:
        return "openai"
    if requested == "deepseek":
        return "deepseek"
    if os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"):
        return "openai"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return ""


def _chat_url():
    base_url = _base_url()
    return base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"


def _strip_json_fence(content):
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json_object(content):
    text = _strip_json_fence(content or "")
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        candidates.append(match.group(0))

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _fallback_reason_from_status():
    status = llm_status_message()
    if "调用成功" in status:
        return "大模型已返回内容，但内容为空、被截断或未通过当前模块的结构校验，已使用规则模板保证页面可用"
    return status


def _sanitize_error_detail(detail):
    text = re.sub(r"sk-[A-Za-z0-9]+", "sk-***", str(detail or ""))
    return text.replace("\n", " ")[:500]


def _is_generation_notice_line(line):
    return bool(re.match(r"^\s*>\s*生成方式：", str(line or "")))


def _remove_inline_generation_notice(line):
    return re.sub(r"\s*>\s*生成方式：.*$", "", str(line or "")).rstrip()
