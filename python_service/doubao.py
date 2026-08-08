import json
import os
import time

import httpx

from .deepseek import parse_json_content


DEFAULT_DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_DOUBAO_MODEL = "doubao-seed-2-1-pro-260628"
DEFAULT_DOUBAO_FALLBACK_MODEL = "doubao-seed-2-0-lite-260215"


class DoubaoTimeoutError(RuntimeError):
    """Raised when a Doubao response exceeds the caller's latency budget."""


def _response_text(data: dict) -> str:
    """Read Responses API output while tolerating minor provider shape changes."""
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("value")
            if isinstance(text, str) and text.strip():
                return text

    choices = data.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content", "")
        if isinstance(content, str):
            return content

    return ""


def _stream_response_text(lines, deadline_seconds: float = 0) -> str:
    """Collect Responses API SSE text deltas into one JSON string."""
    started_at = time.monotonic()
    deltas = []
    done_text = ""
    completed_response = {}

    for raw_line in lines:
        if deadline_seconds > 0 and time.monotonic() - started_at > deadline_seconds:
            raise DoubaoTimeoutError(f"豆包生成超过 {deadline_seconds:g} 秒时间预算")
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        raw_data = line[5:].strip()
        if not raw_data or raw_data == "[DONE]":
            continue
        try:
            event = json.loads(raw_data)
        except json.JSONDecodeError:
            continue

        event_type = str(event.get("type") or "")
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
        elif event_type == "response.output_text.done":
            text = event.get("text")
            if isinstance(text, str):
                done_text = text
        elif event_type == "response.completed":
            candidate = event.get("response")
            if isinstance(candidate, dict):
                completed_response = candidate
        elif event_type in {"error", "response.failed", "response.incomplete"}:
            error = event.get("error") or event.get("response") or event
            raise RuntimeError(f"豆包 Responses API 流式生成失败：{error}")
        elif not event_type:
            # Some compatible gateways emit a complete Responses object as a
            # data event even when stream=true.
            candidate_text = _response_text(event)
            if candidate_text:
                done_text = candidate_text

    if deltas:
        return "".join(deltas)
    if done_text:
        return done_text
    if completed_response:
        return _response_text(completed_response)
    return ""


def _build_input(prompt: str, system_prompt: str = "", image_urls=None) -> list[dict]:
    messages = []
    if system_prompt:
        messages.append({
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        })

    content = []
    for image_url in image_urls or []:
        if isinstance(image_url, dict):
            image_url = image_url.get("url") or image_url.get("image_url") or image_url.get("public_url")
        if isinstance(image_url, str) and image_url.startswith("https://"):
            content.append({"type": "input_image", "image_url": image_url})
    content.append({"type": "input_text", "text": prompt})
    messages.append({"role": "user", "content": content})
    return messages


def chat_json(
    prompt: str,
    system_prompt: str = "",
    image_urls=None,
    *,
    model_override: str = "",
    deadline_seconds: float | None = None,
    max_output_tokens_override: int | None = None,
) -> dict:
    # Read configuration at call time so a process started after loading .env
    # (or a test that temporarily changes the environment) always uses the
    # current local configuration. The key never belongs in source code.
    api_key = os.getenv("DOUBAO_API_KEY", "").strip()
    api_url = os.getenv("DOUBAO_API_URL", DEFAULT_DOUBAO_API_URL).strip()
    model = model_override.strip() or os.getenv("DOUBAO_MODEL", DEFAULT_DOUBAO_MODEL).strip()
    if not api_key:
        raise RuntimeError("缺少 DOUBAO_API_KEY")

    thinking_mode = os.getenv("DOUBAO_THINKING", "disabled").strip().lower()
    max_output_tokens = (
        int(max_output_tokens_override)
        if max_output_tokens_override is not None
        else int(os.getenv("DOUBAO_MAX_OUTPUT_TOKENS", "6000"))
    )
    stream_enabled = os.getenv("DOUBAO_STREAM", "1").strip() != "0"
    payload = {
        "model": model,
        "input": _build_input(prompt, system_prompt, image_urls),
        "stream": stream_enabled,
    }
    if thinking_mode in {"disabled", "enabled", "auto"}:
        payload["thinking"] = {"type": thinking_mode}
    if max_output_tokens > 0:
        payload["max_output_tokens"] = max_output_tokens

    budget_seconds = float(
        deadline_seconds
        if deadline_seconds is not None
        else os.getenv("DOUBAO_PRIMARY_DEADLINE_SECONDS", "120")
    )
    idle_timeout_seconds = min(
        float(os.getenv("DOUBAO_TIMEOUT_SECONDS", "120")),
        budget_seconds,
    )
    timeout = httpx.Timeout(connect=15.0, read=idle_timeout_seconds, write=30.0, pool=10.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            if stream_enabled:
                with client.stream(
                    "POST",
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    content = _stream_response_text(response.iter_lines(), budget_seconds)
            else:
                response = client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                content = _response_text(response.json())
    except httpx.TimeoutException as error:
        raise DoubaoTimeoutError(f"豆包模型 {model} 在 {budget_seconds:g} 秒内未完成") from error

    if not content:
        raise ValueError("豆包 Responses API 没有返回文本")
    return parse_json_content(content)
