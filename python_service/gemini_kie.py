import json
import os
import time

import httpx

from .deepseek import parse_json_content

KIE_API_KEY = os.getenv("KIE_API_KEY", "").strip()
GEMINI_KIE_URL = "https://api.kie.ai/gemini-3.1-pro/v1/chat/completions"


def chat_json(
    prompt: str,
    system_prompt: str = "",
    image_urls=None,
    endpoint_override: str = "",
    model_override: str = "",
) -> dict:
    if not KIE_API_KEY:
        raise RuntimeError("缺少 KIE_API_KEY")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    images = [url for url in (image_urls or []) if isinstance(url, str) and url.startswith("https://")]
    if images:
        content = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": url}}
            for url in images
        )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    if model_override:
        payload["model"] = model_override

    endpoint = endpoint_override or GEMINI_KIE_URL
    retryable_errors = (
        httpx.ConnectError,
        httpx.ReadError,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
    )
    response = None
    last_error = None
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=60.0, pool=20.0)
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(1, 4):
            try:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {KIE_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                break
            except retryable_errors as error:
                last_error = error
                if attempt >= 3:
                    raise RuntimeError(
                        f"KIE Gemini 连接连续 {attempt} 次被中断：{error}"
                    ) from error
                print(f"[gemini-kie] connection interrupted; retry {attempt}/2...")
                time.sleep(1.5 * attempt)

    if response is None:
        raise RuntimeError(f"KIE Gemini 请求未完成：{last_error or '未知连接错误'}")

    data = response.json()
    envelopes = [data]
    if isinstance(data.get("data"), dict):
        envelopes.append(data["data"])

    content = ""
    for envelope in envelopes:
        choices = envelope.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content", "")
            if content:
                break
        candidates = envelope.get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts") or [])
            content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
            if content:
                break
        content = envelope.get("output_text") or envelope.get("response") or ""
        if content:
            break

    if isinstance(content, list):
        content = "".join(
            str(item.get("text") or item.get("content") or "") if isinstance(item, dict) else str(item)
            for item in content
        )
    if isinstance(content, dict):
        return content
    if not content:
        provider_message = (
            data.get("message")
            or data.get("msg")
            or data.get("error")
            or (data.get("data") or {}).get("message")
            or ""
        )
        if isinstance(provider_message, dict):
            provider_message = provider_message.get("message") or json.dumps(provider_message, ensure_ascii=False)
        keys = ", ".join(sorted(str(key) for key in data.keys())) or "无"
        raise ValueError(
            f"Gemini KIE 未返回文本；响应字段：{keys}"
            + (f"；KIE 信息：{provider_message}" if provider_message else "")
        )
    return parse_json_content(str(content))
