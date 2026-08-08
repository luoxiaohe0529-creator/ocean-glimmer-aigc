import json
import os
import re

import httpx


def parse_json_content(content: str) -> dict:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        try:
            from json_repair import repair_json
            repaired = repair_json(match.group(0) if match else text)
            return json.loads(repaired)
        except Exception:
            if not match:
                raise ValueError("模型没有返回可解析的 JSON，且无法自动修复")
            raise


def chat_json(prompt: str, lang: str = "中文") -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    endpoint = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    is_en = lang in ("英文", "english", "en", "English")
    sys_msg = "You ONLY output valid JSON. All content must be in English." if is_en else "你只输出严格合法的 JSON。"
    payload = {
        "model": model,
        "temperature": 0.65,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=90) as client:
        response = client.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    return parse_json_content(data["choices"][0]["message"]["content"])
