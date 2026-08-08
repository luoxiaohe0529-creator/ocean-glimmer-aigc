import os

import httpx

from .deepseek import parse_json_content


DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "").strip()
DOUBAO_API_URL = os.getenv(
    "DOUBAO_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/responses",
).strip()
DOUBAO_MODEL = os.getenv("DOUBAO_MODEL", "doubao-seed-2-1-pro-260628").strip()


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
        if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
            content.append({"type": "input_image", "image_url": image_url})
    content.append({"type": "input_text", "text": prompt})
    messages.append({"role": "user", "content": content})
    return messages


def chat_json(prompt: str, system_prompt: str = "", image_urls=None) -> dict:
    if not DOUBAO_API_KEY:
        raise RuntimeError("缺少 DOUBAO_API_KEY")

    payload = {
        "model": DOUBAO_MODEL,
        "input": _build_input(prompt, system_prompt, image_urls),
        "stream": False,
    }

    with httpx.Client(timeout=float(os.getenv("DOUBAO_TIMEOUT_SECONDS", "120"))) as client:
        response = client.post(
            DOUBAO_API_URL,
            headers={
                "Authorization": f"Bearer {DOUBAO_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    content = _response_text(response.json())
    if not content:
        raise ValueError("豆包 Responses API 没有返回文本")
    return parse_json_content(content)
