import os

import httpx

from .deepseek import parse_json_content

KIE_API_KEY = os.getenv("KIE_API_KEY", "").strip()
GEMINI_KIE_URL = "https://api.kie.ai/gemini-3.1-pro/v1/chat/completions"


def chat_json(prompt: str, system_prompt: str = "") -> dict:
    if not KIE_API_KEY:
        raise RuntimeError("缺少 KIE_API_KEY")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=180) as client:
        response = client.post(
            GEMINI_KIE_URL,
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Gemini KIE 没有返回结果")

    content = choices[0].get("message", {}).get("content", "")
    return parse_json_content(content)
